from __future__ import annotations

import codecs
import contextlib
import fcntl
import logging
import math
import os
import pty
import re
import select
import shutil
import signal
import struct
import subprocess
import termios
import threading
import time
import tty
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from synapse.file_safety import FileSafetyManager
    from synapse.observation import ObservationCollector

from synapse.config import (
    AUTO_APPROVE_COOLDOWN,
    AUTO_APPROVE_MAX_CONSECUTIVE,
    AUTO_APPROVE_STABILIZE_DELAY,
    IDENTITY_WAIT_TIMEOUT,
    IDLE_CHECK_WINDOW,
    OUTPUT_BUFFER_MAX,
    POST_WRITE_IDLE_DELAY,
    STARTUP_DELAY,
    TASK_PROTECTION_TIMEOUT,
    WRITE_PROCESSING_DELAY,
)
from synapse.controller_status import StatusObserverMixin
from synapse.idle_detector import IdleDetector
from synapse.long_message import format_file_reference, get_long_message_store
from synapse.mcp.server import MCP_INSTRUCTIONS_DEFAULT_URI
from synapse.pty_renderer import PtyRenderer
from synapse.registry import AgentRegistry
from synapse.settings import get_settings
from synapse.skills import load_skill_sets
from synapse.terminal_writer import TerminalWriter
from synapse.utils import (
    RoleFileNotFoundError,
    format_a2a_message,
    format_role_section,
    format_skill_set_section,
    get_role_content,
)

logger = logging.getLogger(__name__)

_ANSI_ESCAPE_RE = re.compile(
    r"\x1b"
    r"(?:"
    r"\[[?]?[0-9;]*[a-zA-Z]"  # CSI sequences
    r"|\][^\x07\x1b]*(?:\x07|\x1b\\)"  # OSC sequences (terminated)
    r"|\][^\x07\x1b]*$"  # OSC sequences (unterminated at end of string)
    r"|[()][AB0-2]"  # Character set selection
    r"|[>=]"  # Keypad mode
    r")"
)
_ORPHAN_SGR_RE = re.compile(r"(?<![a-zA-Z])\[[0-9;]+m")
_ORPHAN_SGR_BARE_RE = re.compile(r"(?<![a-zA-Z0-9\[])[0-9]+(?:;[0-9]+)+m(?![a-zA-Z])")
_COPILOT_COMPACT_PASTE_RE = re.compile(r"\[Paste #\d+(?: - \d+ lines)?\]")
_COPILOT_SAVED_PASTE_RE = re.compile(
    r"\[Saved pasted content to workspace \([^)]+\) id=\d+\]"
)
# Kitty Keyboard Protocol (KKP) — Copilot CLI enables this on startup.
# When active, terminals encode Enter as CSI 13 u instead of \r, which
# can cause our injected \r to be ignored.  We detect KKP activation
# in PTY output and immediately disable it by popping the mode stack.
_KKP_ENABLE_RE = re.compile(rb"\x1b\[>[0-9;]*u")
_KKP_DISABLE_SEQ = b"\x1b[<u"  # Pop keyboard mode (restore previous)
_COPILOT_SUBMIT_NUDGE_DELAY = 0.1
_COPILOT_LONG_SUBMIT_NUDGE_DELAY = 0.2
_COPILOT_PASTE_ECHO_POLL = 0.05
_COPILOT_PASTE_ECHO_TIMEOUT = 3.0
# Stabilization delay after paste echo is detected.  Ink's React render cycle
# updates the screen (PTY output) before committing the paste into the internal
# input buffer via usePaste → setState.  Sending CR immediately after the screen
# change can race with that state commit, causing Enter to fire on an empty
# buffer.  This delay gives React one extra tick to finish the state update.
_COPILOT_PASTE_ECHO_SETTLE = 0.15


def strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from text.

    Three-stage removal:
    1. Full ANSI sequences (ESC + CSI/OSC/charset/keypad)
    2. Orphaned SGR fragments like ``[38;5;178m`` (ESC was overwritten by \\r)
    3. Bare SGR fragments like ``38;5;178m`` (bracket also overwritten)
    """
    text = _ANSI_ESCAPE_RE.sub("", text)
    text = _ORPHAN_SGR_RE.sub("", text)
    text = _ORPHAN_SGR_BARE_RE.sub("", text)
    return text


class TerminalController(StatusObserverMixin):
    def __init__(
        self,
        command: str,
        idle_regex: str | None = None,
        idle_detection: dict | None = None,
        waiting_detection: dict | None = None,
        env: dict | None = None,
        registry: AgentRegistry | None = None,
        agent_id: str | None = None,
        agent_type: str | None = None,
        submit_seq: str | None = None,
        startup_delay: int | None = None,
        args: list | None = None,
        port: int | None = None,
        skip_initial_instructions: bool = False,
        mcp_bootstrap: bool = False,
        input_ready_pattern: str | None = None,
        name: str | None = None,
        role: str | None = None,
        delegate_mode: bool = False,
        skill_set: str | None = None,
        write_delay: float | None = None,
        submit_retry_delay: float | None = None,
        bracketed_paste: bool = False,
        typing_char_delay: float | None = None,
        typing_max_chars: int | None = None,
        submit_confirm_timeout: float | None = None,
        submit_confirm_poll_interval: float | None = None,
        submit_confirm_retries: int | None = None,
        long_submit_confirm_timeout: float | None = None,
        long_submit_confirm_retries: int | None = None,
        auto_approve: dict | None = None,
    ):
        self.command = command
        self.args = args or []
        self.delegate_mode = delegate_mode

        # Handle multi-strategy idle detection configuration
        # DEPRECATED: idle_regex parameter is deprecated in favor of idle_detection dict
        # Backward compatibility: convert legacy idle_regex to new format
        # This fallback will be removed in a future version. Use idle_detection instead.
        if idle_detection is None and idle_regex is not None:
            idle_detection = {
                "strategy": "pattern",
                "pattern": idle_regex,
                "timeout": 1.5,
            }

        self.idle_config = idle_detection or {"strategy": "timeout", "timeout": 1.5}
        self._pattern_detected = False
        self._pty_renderer = PtyRenderer(columns=120, rows=40)
        self._idle_detector = IdleDetector(
            idle_detection=self.idle_config,
            waiting_detection=waiting_detection,
            strip_ansi_fn=strip_ansi,
            renderer=self._pty_renderer,
        )
        self.idle_strategy = self._idle_detector.idle_strategy
        self.idle_regex = self._idle_detector.idle_regex
        self._output_idle_threshold = self._idle_detector.output_idle_threshold
        self.waiting_config = self._idle_detector.waiting_config
        self._waiting_regex = self._idle_detector.waiting_regex
        self._waiting_require_idle = self._idle_detector.waiting_require_idle
        self._waiting_idle_timeout = self._idle_detector.waiting_idle_timeout
        self._waiting_pattern_time: float | None = None  # When pattern was last seen
        self._waiting_expiry = self._idle_detector.waiting_expiry
        self.last_waiting_confidence = 0.0
        self.last_waiting_source = "none"

        # Compound signal: task_active flag (#314)
        self._task_active_count: int = 0
        self._task_active_since: float | None = None
        self._task_protection_timeout: float = float(
            self.idle_config.get("task_protection_timeout", TASK_PROTECTION_TIMEOUT)
        )
        self._file_safety_manager: FileSafetyManager | None = None

        self.env = env.copy() if env is not None else os.environ.copy()
        # Unset CLAUDECODE to prevent nested-session detection when
        # launching Claude Code from within a Claude Code session.
        self.env.pop("CLAUDECODE", None)
        self.master_fd: int | None = None
        self.slave_fd: int | None = None
        self.process: subprocess.Popen[bytes] | None = None
        self.output_buffer = b""
        self._render_buffer: list[str] = []
        self._render_cursor = 0
        self._render_line_start = 0
        self._pending_cr = False
        self._max_buffer = OUTPUT_BUFFER_MAX
        self._decoder = codecs.getincrementaldecoder("utf-8")("replace")
        self.status = "PROCESSING"
        self.lock = threading.Lock()
        self._write_lock = threading.RLock()
        self.running = False
        self.thread: threading.Thread | None = None
        self.registry = registry or AgentRegistry()
        self.interactive = False
        self.agent_id = agent_id
        self.agent_type = agent_type
        self.port = port or 8100  # Default port for Agent Card URL
        self._identity_sent = False
        self._identity_sending = False
        self._agent_ready = False
        self._agent_ready_event = threading.Event()
        self._submit_seq = submit_seq or "\n"
        self._startup_delay = startup_delay or STARTUP_DELAY
        self._last_output_time: float | None = (
            None  # Track last output for idle detection
        )
        self._done_time: float | None = None  # Track when DONE status was set
        self._status_callbacks: list[Callable[[str, str], None]] = []
        self._observation_collector: ObservationCollector | None = None
        self._observation_attached = False
        if skip_initial_instructions and mcp_bootstrap:
            raise ValueError(
                "skip_initial_instructions and mcp_bootstrap are mutually exclusive"
            )
        self._skip_initial_instructions = skip_initial_instructions
        self._mcp_bootstrap = mcp_bootstrap
        self._input_ready_pattern = input_ready_pattern
        self.name = name
        self.role = role
        self.skill_set = skill_set
        if write_delay is not None:
            try:
                write_delay = float(write_delay)
            except (TypeError, ValueError):
                raise ValueError(
                    f"write_delay must be a numeric value, got {write_delay!r}"
                ) from None
            if write_delay < 0:
                raise ValueError(f"write_delay must be non-negative, got {write_delay}")
            self._write_delay = write_delay
        else:
            self._write_delay = WRITE_PROCESSING_DELAY

        # Optional retry delay: send submit_seq twice with this gap.
        # Required for Copilot CLI v0.0.300+ where the first CR flushes
        # the Ink async paste buffer and the second CR triggers submit.
        self._submit_retry_delay: float | None = None
        # Inject pipe write fd for interactive mode (set by run_interactive)
        self._inject_write_fd: int | None = None
        # Whether ICRNL has been cleared on the PTY (avoid repeated syscalls)
        self._icrnl_cleared = False
        # Whether Kitty Keyboard Protocol has been disabled on the PTY
        self._kkp_disabled = False
        if submit_retry_delay is not None:
            try:
                submit_retry_delay = float(submit_retry_delay)
            except (TypeError, ValueError):
                raise ValueError(
                    f"submit_retry_delay must be numeric, got {submit_retry_delay!r}"
                ) from None
            if submit_retry_delay < 0:
                raise ValueError(
                    f"submit_retry_delay must be non-negative, got {submit_retry_delay}"
                )
            self._submit_retry_delay = submit_retry_delay

        # Wrap data in bracketed paste markers for Ink-based TUIs (Copilot CLI).
        self._bracketed_paste = bracketed_paste
        self._typing_char_delay = 0.0
        if typing_char_delay is not None:
            try:
                typing_char_delay = float(typing_char_delay)
            except (TypeError, ValueError):
                raise ValueError(
                    f"typing_char_delay must be numeric, got {typing_char_delay!r}"
                ) from None
            if typing_char_delay < 0:
                raise ValueError(
                    f"typing_char_delay must be non-negative, got {typing_char_delay}"
                )
            self._typing_char_delay = typing_char_delay
        self._typing_max_chars = 0
        if typing_max_chars is not None:
            try:
                typing_max_chars = int(typing_max_chars)
            except (TypeError, ValueError):
                raise ValueError(
                    f"typing_max_chars must be an integer, got {typing_max_chars!r}"
                ) from None
            if typing_max_chars < 0:
                raise ValueError(
                    f"typing_max_chars must be non-negative, got {typing_max_chars}"
                )
            self._typing_max_chars = typing_max_chars
        self._submit_confirm_timeout: float | None = None
        if submit_confirm_timeout is not None:
            try:
                submit_confirm_timeout = float(submit_confirm_timeout)
            except (TypeError, ValueError):
                raise ValueError(
                    "submit_confirm_timeout must be numeric, "
                    f"got {submit_confirm_timeout!r}"
                ) from None
            if submit_confirm_timeout <= 0:
                raise ValueError(
                    "submit_confirm_timeout must be positive, "
                    f"got {submit_confirm_timeout}"
                )
            self._submit_confirm_timeout = submit_confirm_timeout

        self._submit_confirm_poll_interval: float | None = None
        if submit_confirm_poll_interval is not None:
            try:
                submit_confirm_poll_interval = float(submit_confirm_poll_interval)
            except (TypeError, ValueError):
                raise ValueError(
                    "submit_confirm_poll_interval must be numeric, "
                    f"got {submit_confirm_poll_interval!r}"
                ) from None
            if submit_confirm_poll_interval <= 0:
                raise ValueError(
                    "submit_confirm_poll_interval must be positive, "
                    f"got {submit_confirm_poll_interval}"
                )
            self._submit_confirm_poll_interval = submit_confirm_poll_interval

        self._submit_confirm_retries: int = 0
        if submit_confirm_retries is not None:
            try:
                submit_confirm_retries = int(submit_confirm_retries)
            except (TypeError, ValueError):
                raise ValueError(
                    "submit_confirm_retries must be an integer, "
                    f"got {submit_confirm_retries!r}"
                ) from None
            if submit_confirm_retries < 0:
                raise ValueError(
                    "submit_confirm_retries must be non-negative, "
                    f"got {submit_confirm_retries}"
                )
            self._submit_confirm_retries = submit_confirm_retries

        self._long_submit_confirm_timeout: float | None = None
        if long_submit_confirm_timeout is not None:
            try:
                long_submit_confirm_timeout = float(long_submit_confirm_timeout)
            except (TypeError, ValueError):
                raise ValueError(
                    "long_submit_confirm_timeout must be numeric, "
                    f"got {long_submit_confirm_timeout!r}"
                ) from None
            if long_submit_confirm_timeout <= 0:
                raise ValueError(
                    "long_submit_confirm_timeout must be positive, "
                    f"got {long_submit_confirm_timeout}"
                )
            self._long_submit_confirm_timeout = long_submit_confirm_timeout

        self._long_submit_confirm_retries: int | None = None
        if long_submit_confirm_retries is not None:
            try:
                long_submit_confirm_retries = int(long_submit_confirm_retries)
            except (TypeError, ValueError):
                raise ValueError(
                    "long_submit_confirm_retries must be an integer, "
                    f"got {long_submit_confirm_retries!r}"
                ) from None
            if long_submit_confirm_retries < 0:
                raise ValueError(
                    "long_submit_confirm_retries must be non-negative, "
                    f"got {long_submit_confirm_retries}"
                )
            self._long_submit_confirm_retries = long_submit_confirm_retries

        # Auto-approve: automatically respond to WAITING (permission prompts)
        self._auto_approve_config = auto_approve or {}
        self._auto_approve_enabled = bool(
            auto_approve and auto_approve.get("runtime_response")
        )
        if self._auto_approve_enabled:
            raw_response = auto_approve.get("runtime_response", "")  # type: ignore[union-attr]
            # Decode YAML escape sequences (e.g., "\r" -> actual CR)
            self._auto_approve_response: str = (
                raw_response.encode().decode("unicode_escape") if raw_response else ""
            )
            self._auto_approve_max: int = int(
                auto_approve.get("max_consecutive", AUTO_APPROVE_MAX_CONSECUTIVE)  # type: ignore[union-attr]
            )
            self._auto_approve_cooldown: float = float(
                auto_approve.get("cooldown", AUTO_APPROVE_COOLDOWN)  # type: ignore[union-attr]
            )
        else:
            self._auto_approve_response = ""
            self._auto_approve_max = AUTO_APPROVE_MAX_CONSECUTIVE
            self._auto_approve_cooldown = AUTO_APPROVE_COOLDOWN
        self._auto_approve_count: int = 0
        self._auto_approve_last_time: float | None = None
        self._auto_approve_stopped: bool = False
        self._auto_approve_lock = threading.Lock()
        self._terminal_writer = TerminalWriter(
            self,
            agent_id=self.agent_id,
            agent_type=self.agent_type,
            write_delay=self._write_delay,
            submit_retry_delay=self._submit_retry_delay,
            bracketed_paste=self._bracketed_paste,
            typing_char_delay=self._typing_char_delay,
            typing_max_chars=self._typing_max_chars,
            submit_confirm_timeout=self._submit_confirm_timeout,
            submit_confirm_poll_interval=self._submit_confirm_poll_interval,
            submit_confirm_retries=self._submit_confirm_retries,
            long_submit_confirm_timeout=self._long_submit_confirm_timeout,
            long_submit_confirm_retries=self._long_submit_confirm_retries,
            copilot_compact_paste_re=_COPILOT_COMPACT_PASTE_RE,
            copilot_saved_paste_re=_COPILOT_SAVED_PASTE_RE,
            kkp_disable_seq=_KKP_DISABLE_SEQ,
            copilot_submit_nudge_delay=_COPILOT_SUBMIT_NUDGE_DELAY,
            copilot_long_submit_nudge_delay=_COPILOT_LONG_SUBMIT_NUDGE_DELAY,
            copilot_paste_echo_poll=_COPILOT_PASTE_ECHO_POLL,
            copilot_paste_echo_timeout=_COPILOT_PASTE_ECHO_TIMEOUT,
            copilot_paste_echo_settle=_COPILOT_PASTE_ECHO_SETTLE,
            strip_ansi=strip_ansi,
            logger=logger,
            os_module=os,
            time_module=time,
            termios_module=termios,
            contextlib_module=contextlib,
            math_module=math,
        )

        if self._auto_approve_enabled:
            self.on_status_change(self._handle_auto_approve)

    def _handle_auto_approve(self, old_status: str, new_status: str) -> None:
        """Auto-approve callback: send approval response on WAITING transitions.

        Runs on a daemon thread (dispatched by _dispatch_status_callbacks).
        All mutable state is guarded by _auto_approve_lock.
        """
        with self._auto_approve_lock:
            if new_status != "WAITING":
                return

            if self._auto_approve_stopped:
                return

            now = time.time()

            if (
                self._auto_approve_last_time is not None
                and (now - self._auto_approve_last_time) < self._auto_approve_cooldown
            ):
                logger.debug(
                    "[%s] Auto-approve cooldown active, skipping",
                    self.agent_id,
                )
                return

            if (
                self._auto_approve_max > 0
                and self._auto_approve_count >= self._auto_approve_max
            ):
                logger.warning(
                    "[%s] Auto-approve max consecutive reached (%d), stopping",
                    self.agent_id,
                    self._auto_approve_max,
                )
                self._auto_approve_stopped = True
                return

            self._auto_approve_count += 1
            self._auto_approve_last_time = time.time()

        # Sleep and write outside the lock to avoid blocking other callbacks
        time.sleep(AUTO_APPROVE_STABILIZE_DELAY)
        logger.info(
            "[%s] Auto-approve #%d: sending approval response",
            self.agent_id,
            self._auto_approve_count,
        )
        self.write(self._auto_approve_response)

    def set_file_safety_manager(self, manager: FileSafetyManager) -> None:
        """Set FileSafetyManager for compound signal file lock detection."""
        self._file_safety_manager = manager

    def _is_task_protection_active(self) -> bool:
        """Check if task protection is active (within timeout). Lock must be held."""
        if self._task_active_count <= 0 or self._task_active_since is None:
            return False
        elapsed = time.time() - self._task_active_since
        return elapsed < self._task_protection_timeout

    def _has_file_locks(self) -> bool:
        """Check if this agent holds any active file locks. Lock must be held."""
        if self._file_safety_manager is None or not self.agent_id:
            return False
        try:
            locks = self._file_safety_manager.list_locks(
                agent_name=self.agent_id, include_stale=False
            )
            return bool(locks)
        except Exception:
            return False

    def start(self) -> None:
        """Start the controlled process in background mode with PTY."""
        self.master_fd, self.slave_fd = pty.openpty()

        # Set slave PTY to raw mode before spawning the child process.
        # Default PTY modes include ICRNL which translates \r→\n.  Ink-based
        # TUIs (Copilot CLI) expect literal \r for Enter.  If Ink hasn't
        # configured raw mode on the slave yet when we send CR through the
        # master, the line discipline translates it to \n, which Ink may not
        # recognize as a submit key.  Setting raw mode on the slave here
        # ensures \r passes through verbatim regardless of child startup timing.
        with contextlib.suppress(termios.error):
            tty.setraw(self.slave_fd)

        # Build command list: command + args
        cmd_list = [self.command] + self.args

        self.process = subprocess.Popen(
            cmd_list,
            stdin=self.slave_fd,
            stdout=self.slave_fd,
            stderr=self.slave_fd,
            env=self.env,
            preexec_fn=os.setsid,  # Create new session
            close_fds=True,
        )
        # Capture PGID immediately after spawn so stop() never needs to
        # re-query it (avoids race when the process has already exited).
        self._pgid: int | None = os.getpgid(self.process.pid)

        # Close slave_fd in parent as it's now attached to child
        os.close(self.slave_fd)

        self.running = True
        self.thread = threading.Thread(target=self._monitor_output)
        self.thread.daemon = True
        self.thread.start()
        self.status = "PROCESSING"

        # Initialize last output time for timeout-based idle detection
        with self.lock:
            self._last_output_time = time.time()

    def _monitor_output(self) -> None:
        """Monitor and process output from the controlled process PTY."""
        try:
            if self.master_fd is None or self.process is None:
                return
            while self.running and self.process.poll() is None:
                r, _, _ = select.select([self.master_fd], [], [], 0.1)
                if self.master_fd in r:
                    try:
                        data = os.read(self.master_fd, 1024)
                        if not data:
                            break

                        self._append_output(data)

                        self._check_idle_state(data)

                        # Detect and disable Kitty Keyboard Protocol.
                        # Copilot CLI enables KKP on startup which changes
                        # how Enter is encoded, causing our \r to be ignored.
                        # Always check — Copilot can re-push KKP after we
                        # pop it (e.g. after processing a prompt).
                        if self.agent_type == "copilot" and _KKP_ENABLE_RE.search(data):
                            self._disable_kkp(
                                "re-disabled via pop"
                                if self._kkp_disabled
                                else "disabled via pop",
                                force=True,
                            )
                            # Ink may also re-enable ICRNL when it re-pushes
                            # KKP, so reset the cache so the next submit
                            # re-checks termios.
                            self._icrnl_cleared = False

                        # Debug logging for PTY output analysis
                        # Enable with SYNAPSE_DEBUG_PTY=1 to see raw PTY output
                        if os.environ.get("SYNAPSE_DEBUG_PTY"):
                            text = data.decode("utf-8", errors="replace")
                            self._log_pty_output(data, text)

                    except OSError:
                        break
                else:
                    # Periodically check idle state (timeout-based detection)
                    self._check_idle_state(b"")
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            logger.error(f"Error in _monitor_output for {self.agent_id}: {err}")

    def _check_pattern_idle(self) -> bool:
        """Check for pattern-based idle detection. Must be called with lock held."""
        search_window = self.output_buffer[-IDLE_CHECK_WINDOW:]
        if self._idle_detector.check_pattern_idle(
            search_window, self._pattern_detected
        ):
            self._pattern_detected = True
            return True
        return False

    def _check_timeout_idle(self) -> bool:
        """Check for timeout-based idle detection. Must be called with lock held."""
        return self._idle_detector.check_timeout_idle(
            last_output_time=self._last_output_time,
            pattern_detected=self._pattern_detected,
        )

    def _evaluate_idle_status(self, pattern_match: bool, timeout_idle: bool) -> bool:
        """Evaluate idle status based on strategy and detection results."""
        return self._idle_detector.evaluate_idle_status(pattern_match, timeout_idle)

    def _determine_new_status(self, is_idle: bool, is_waiting: bool) -> str:
        """Determine the new status based on idle and waiting state.

        Args:
            is_idle: Whether the agent is idle (ready for input).
            is_waiting: Whether the agent is showing a selection UI.

        Returns:
            New status string: "READY", "WAITING", "PROCESSING", "DONE",
            or "SHUTTING_DOWN".
        """
        decision = self._idle_detector.determine_new_status(
            current_status=self.status,
            is_idle=is_idle,
            is_waiting=is_waiting,
            done_time=self._done_time,
            task_protection_active=self._is_task_protection_active(),
            has_file_locks=self._has_file_locks(),
        )
        if decision.clear_done_time:
            self._done_time = None
        return decision.new_status

    def _check_waiting_state(self, new_data: bytes) -> bool:
        """Check if agent is in WAITING state (user input prompt).

        WAITING is detected when:
        1. A regex pattern matches *new data* (not the full buffer — fixes #140)
        2. No new output for waiting_idle_timeout (if require_idle is True)
        3. Pattern was seen within waiting_expiry seconds (auto-clears stale WAITING)

        Args:
            new_data: New data from PTY.

        Returns:
            True if in WAITING state, False otherwise.
        """
        (
            is_waiting,
            self._waiting_pattern_time,
            waiting_confidence,
            waiting_source,
        ) = self._idle_detector.check_waiting_state(
            new_data=new_data,
            output_buffer=self.output_buffer,
            last_output_time=self._last_output_time,
            waiting_pattern_time=self._waiting_pattern_time,
        )
        if is_waiting:
            self.last_waiting_confidence = waiting_confidence
            self.last_waiting_source = waiting_source
        else:
            self.last_waiting_confidence = 0.0
            self.last_waiting_source = "none"
        return is_waiting

    def _check_idle_state(self, new_data: bytes) -> None:
        """Check idle state using configured strategy (pattern, timeout, or hybrid)."""
        with self.lock:
            try:
                evaluation = self._idle_detector.check_idle_state(
                    new_data=new_data,
                    output_buffer=self.output_buffer[-IDLE_CHECK_WINDOW:],
                    last_output_time=self._last_output_time,
                    pattern_detected=self._pattern_detected,
                    waiting_pattern_time=self._waiting_pattern_time,
                    current_status=self.status,
                    done_time=self._done_time,
                    task_protection_active=self._is_task_protection_active(),
                    has_file_locks=self._has_file_locks(),
                )
            except Exception:
                logger.warning(
                    "[%s] Idle-state detection failed; keeping current status",
                    self.agent_id,
                    exc_info=True,
                )
                if new_data and self.status not in {"PROCESSING", "SHUTTING_DOWN"}:
                    old_status = self.status
                    self.status = "PROCESSING"
                    if self.agent_id:
                        self.registry.update_status(self.agent_id, self.status)
                    self._dispatch_status_callbacks(old_status, self.status)
                return
            self._pattern_detected = evaluation.pattern_detected
            self._waiting_pattern_time = evaluation.waiting_pattern_time
            if evaluation.is_waiting:
                self.last_waiting_confidence = evaluation.waiting_confidence
                self.last_waiting_source = evaluation.waiting_source
            else:
                self.last_waiting_confidence = 0.0
                self.last_waiting_source = "none"
            if evaluation.clear_done_time:
                self._done_time = None
            is_idle = evaluation.is_idle
            new_status = evaluation.new_status

            # Update status and sync to registry (only if changed)
            if new_status != self.status:
                old_status = self.status
                self.status = new_status

                elapsed = (
                    time.time() - self._last_output_time
                    if self._last_output_time
                    else 0
                )
                logger.debug(
                    f"[{self.agent_id}] Status: {old_status} -> {new_status} "
                    f"(strategy={self.idle_strategy}, elapsed={elapsed:.2f}s)"
                )

                # Sync to registry
                if self.agent_id:
                    success = self.registry.update_status(self.agent_id, self.status)
                    if not success:
                        logger.debug(
                            f"Failed to sync status to registry: {self.agent_id}"
                            f" -> {self.status}"
                        )

                self._dispatch_status_callbacks(old_status, new_status)

            # Send initial instructions on first READY (agent is idle)
            if (
                is_idle
                and self.status == "READY"
                and not self._identity_sent
                and not self._identity_sending
                and self.agent_id
            ):
                self._identity_sending = True
                threading.Thread(
                    target=self._send_identity_instruction, daemon=True
                ).start()

    def _mark_agent_ready(self) -> None:
        """Signal that agent initialization is complete and ready for tasks."""
        self._agent_ready = True
        self._agent_ready_event.set()
        # Non-blocking session_id detection after readiness gate opens
        if self.agent_id and self.agent_type:
            threading.Thread(
                target=self._detect_and_store_session_id, daemon=True
            ).start()

    def _detect_and_store_session_id(self) -> None:
        """Detect the CLI session ID from the filesystem and store it.

        Precondition: self.agent_id and self.agent_type are non-None
        (guaranteed by _mark_agent_ready guard).
        """
        try:
            from synapse.session_id_detector import detect_session_id

            assert self.agent_id is not None  # guaranteed by _mark_agent_ready guard
            session_id = detect_session_id(self.agent_type, os.getcwd())
            if session_id:
                self.registry.update_session_id(self.agent_id, session_id)
                logger.info("[%s] session_id detected: %s", self.agent_id, session_id)
        except Exception:
            logger.debug(
                "session_id detection failed for %s",
                self.agent_id,
                exc_info=True,
            )

    @property
    def agent_ready(self) -> bool:
        """Whether the agent has completed initialization."""
        return self._agent_ready

    def wait_until_ready(self, timeout: float) -> bool:
        """Block until the agent is ready or timeout expires.

        Args:
            timeout: Maximum seconds to wait.

        Returns:
            True if agent became ready, False if timeout expired.
        """
        return self._agent_ready_event.wait(timeout=timeout)

    def _log_inject(self, category: str, msg: str) -> None:
        """Emit a structured injection observability log line.

        All injection logs use a consistent ``[agent_id] INJECT/<category>:``
        prefix so they can be filtered with ``grep INJECT``.
        """
        logger.info(f"[{self.agent_id}] INJECT/{category}: {msg}")

    def _wait_for_input_ready(self) -> str:
        """Wait for the agent's input prompt to appear in PTY output.

        Returns:
            A short description of the wait result for observability logging.
        """
        timeout = 10.0
        interval = 0.5

        if not self._input_ready_pattern:
            logger.info(
                f"[{self.agent_id}] No input_ready_pattern configured, "
                "using timeout-based idle fallback"
            )
            return self._wait_for_timeout_idle(timeout, interval)

        waited = 0.0
        pattern_bytes = self._input_ready_pattern.encode()

        logger.info(
            f"[{self.agent_id}] Waiting for input pattern: "
            f"{self._input_ready_pattern!r} (bytes: {pattern_bytes!r})"
        )

        while waited < timeout:
            time.sleep(interval)
            waited += interval

            with self.lock:
                recent_output = self.output_buffer[-2000:]

            if pattern_bytes in recent_output:
                logger.info(
                    f"[{self.agent_id}] Input prompt "
                    f"'{self._input_ready_pattern}' "
                    f"detected after {waited:.1f}s"
                )
                return f"pattern_found({waited:.1f}s)"

        logger.warning(
            f"[{self.agent_id}] Input prompt "
            f"'{self._input_ready_pattern}' "
            f"not detected after {timeout}s, proceeding anyway"
        )
        return f"timeout({timeout:.1f}s)"

    def _wait_for_timeout_idle(self, timeout: float, interval: float) -> str:
        """Wait for timeout-based idle detection during input readiness."""
        waited = 0.0
        while waited < timeout:
            with self.lock:
                if self._check_timeout_idle():
                    logger.info(
                        f"[{self.agent_id}] Timeout idle detected after {waited:.1f}s"
                    )
                    return f"timeout_idle({waited:.1f}s)"
            time.sleep(interval)
            waited += interval

        logger.warning(
            f"[{self.agent_id}] Timeout idle not detected after "
            f"{timeout:.1f}s, proceeding anyway"
        )
        return f"timeout({timeout:.1f}s)"

    def _build_identity_message(self, instruction_file_paths: list[str]) -> str:
        """Build the identity instruction message for the agent.

        Returns:
            The formatted A2A message string ready to send.
        """
        file_list = "\n".join(f"  - {f}" for f in instruction_file_paths)
        display_name = self.name or self.agent_id

        message = (
            f"[SYNAPSE A2A AGENT CONFIGURATION]\n"
            f"Agent: {display_name} | Port: {self.port} | ID: {self.agent_id}\n"
        )

        if self.role:
            try:
                role_content = get_role_content(self.role)
                if role_content:
                    message += format_role_section(role_content)
            except RoleFileNotFoundError as e:
                logger.error(f"Role file not found: {e} (role={self.role})")

        if self.skill_set:
            try:
                skill_sets = load_skill_sets()
                ss_def = skill_sets.get(self.skill_set)
                if ss_def:
                    message += format_skill_set_section(
                        ss_def.name, ss_def.description, ss_def.skills
                    )
                else:
                    logger.warning(
                        f"Skill set '{self.skill_set}' not found in definitions"
                    )
            except Exception as e:
                logger.error(f"Failed to load skill set info: {e}")

        message += (
            f"\nIMPORTANT: Read your full instructions from these files:\n"
            f"{file_list}\n\n"
            f"Read these files NOW to get your "
            f"A2A protocol guidelines and other instructions.\n"
            f"Replace {{{{agent_id}}}} with {self.agent_id}, "
            f"{{{{agent_name}}}} with {display_name}, and "
            f"{{{{port}}}} with {self.port} when following instructions.\n"
            f"Use $SYNAPSE_AGENT_ID (already set to {self.agent_id}) for "
            f"--from flags in synapse send/reply commands."
        )

        return format_a2a_message(message)

    def _build_mcp_bootstrap_message(self) -> str:
        """Build a minimal PTY bootstrap for MCP-configured clients."""
        message = (
            "[SYNAPSE MCP BOOTSTRAP]\n"
            f"ID {self.agent_id} port {self.port}.\n"
            f"Read {MCP_INSTRUCTIONS_DEFAULT_URI}.\n"
            "Call bootstrap_agent().\n"
            "Read returned instruction_resources before work.\n"
            "Use $SYNAPSE_AGENT_ID for --from."
        )
        return format_a2a_message(message)

    def _send_identity_instruction(self) -> None:
        """
        Send full initial instructions to the agent on first IDLE.

        Uses .synapse/settings.json for customizable instructions.
        Falls back to default if no settings found.

        Format: [A2A:<task_id>:synapse-system] <full_instructions>

        If skip_initial_instructions is True (resume mode), this method
        marks instructions as sent without actually sending them.
        """
        if not self.agent_id:
            return

        # Skip if in resume mode (e.g., --continue, --resume flags)
        if self._skip_initial_instructions:
            self._log_inject("DECISION", "action=skip_resume")
            self._log_inject(
                "SUMMARY", "initial_instructions=skipped reason=resume_mode"
            )
            self._identity_sent = True
            self._mark_agent_ready()
            return

        logger.debug(
            f"[{self.agent_id}] Waiting for master_fd "
            f"(timeout={IDENTITY_WAIT_TIMEOUT}s, interactive={self.interactive})"
        )

        # Wait for master_fd to be available (set by read_callback in interactive mode)
        waited = 0.0
        while self.master_fd is None and waited < IDENTITY_WAIT_TIMEOUT:
            time.sleep(0.1)
            waited += 0.1

        if self.master_fd is None:
            logger.error(
                f"[{self.agent_id}] master_fd timeout after {IDENTITY_WAIT_TIMEOUT}s. "
                f"Agent may not have produced output yet."
            )
            msg = (
                f"[Synapse] Error: master_fd not available after"
                f" {IDENTITY_WAIT_TIMEOUT}s"
            )
            print(f"\x1b[31m{msg}\x1b[0m")
            self._log_inject("DECISION", "action=abort_master_fd_timeout")
            self._log_inject(
                "SUMMARY",
                "initial_instructions=failed reason=master_fd_timeout",
            )
            self._identity_sending = False
            return

        logger.info(
            f"[{self.agent_id}] Sending initial instructions "
            f"(master_fd={self.master_fd}, waited={waited:.1f}s)"
        )

        agent_type = self.agent_type or "unknown"
        if self._mcp_bootstrap:
            self._log_inject(
                "RESOLVE",
                f"agent_type={agent_type} cwd={os.getcwd()} mode=mcp_bootstrap",
            )
            self._log_inject("DECISION", "action=send_mcp_bootstrap")
            pty_message = self._build_mcp_bootstrap_message()
        else:
            settings = get_settings()
            instruction_file_paths = settings.get_instruction_file_paths(agent_type)

            has_agent_specific = bool(settings.instructions.get(agent_type))
            fallback = "none" if has_agent_specific else "default"
            self._log_inject(
                "RESOLVE",
                f"agent_type={agent_type} cwd={os.getcwd()} "
                f"files={instruction_file_paths} fallback={fallback}",
            )

            if not instruction_file_paths:
                self._log_inject("DECISION", "action=skip_no_files")
                self._log_inject(
                    "SUMMARY", "initial_instructions=skipped reason=no_files"
                )
                self._identity_sent = True
                self._mark_agent_ready()
                self._identity_sending = False
                return

            self._log_inject("DECISION", "action=send")
            prefixed = self._build_identity_message(instruction_file_paths)

            # Use file storage for long identity messages to avoid TUI paste
            # issues.  Ink TUI (Copilot, Claude Code) collapses large paste
            # into a shortcut display and ignores the CR submit sequence.
            # By storing the full message in a file and sending only a short
            # reference, the PTY write stays small enough to be submitted
            # reliably.
            pty_message = prefixed
            try:
                store = get_long_message_store()
                if store.needs_file_storage(prefixed):
                    task_id = f"identity-{self.agent_id}"
                    file_path = store.store_message(task_id, prefixed)
                    reference = format_file_reference(file_path)
                    pty_message = format_a2a_message(reference)
                    logger.info(
                        f"[{self.agent_id}] Identity message stored to {file_path} "
                        f"(original={len(prefixed)} chars)"
                    )
            except Exception as e:
                logger.error(
                    f"[{self.agent_id}] File storage failed, sending identity inline: {e}"
                )

        logger.info(
            f"[{self.agent_id}] Sending identity instruction: "
            f"pty_size={len(pty_message)} mode={'mcp_bootstrap' if self._mcp_bootstrap else 'full'}"
        )

        input_ready_desc = self._wait_for_input_ready()

        # Additional delay to ensure TUI is stable
        time.sleep(POST_WRITE_IDLE_DELAY)

        try:
            result = self.write(pty_message, self._submit_seq)
            self._log_inject(
                "DELIVER",
                f"input_ready={input_ready_desc} write_size={len(pty_message)} result=ok",
            )
            logger.info(f"[{self.agent_id}] Write result: {result}")
            self._identity_sent = True
            self._mark_agent_ready()
            self._log_inject("SUMMARY", "initial_instructions=sent")
        except Exception as e:
            self._log_inject(
                "DELIVER",
                f"input_ready={input_ready_desc} "
                f"write_size={len(pty_message)} result=error",
            )
            logger.error(f"Failed to send initial instructions: {e}")
            self._log_inject(
                "SUMMARY",
                "initial_instructions=failed reason=write_exception",
            )
        finally:
            self._identity_sending = False

    def _write_all(self, data: bytes) -> None:
        """Write all bytes to the PTY, retrying on partial writes."""
        self._terminal_writer._write_all(data)

    @staticmethod
    def _writer_os_module() -> Any:
        return os

    @staticmethod
    def _writer_time_module() -> Any:
        return time

    @staticmethod
    def _writer_termios_module() -> Any:
        return termios

    @staticmethod
    def _writer_contextlib_module() -> Any:
        return contextlib

    @staticmethod
    def _writer_math_module() -> Any:
        return math

    def _should_type_input(self, data: str, submit_seq: str | None) -> bool:
        """Whether to emulate real typing instead of bracketed paste."""
        return self._terminal_writer._should_type_input(data, submit_seq)

    def _write_typed_text(self, data: str) -> None:
        """Write text character-by-character to emulate actual keyboard input."""
        self._terminal_writer._write_typed_text(data)

    def _is_long_submit_message(self, data: str) -> bool:
        """Whether Copilot confirmation should use long-message heuristics."""
        return self._terminal_writer._is_long_submit_message(data)

    def _pending_submit_markers(self, data: str) -> list[str]:
        """Extract visible markers that indicate Copilot input still remains."""
        return self._terminal_writer._pending_submit_markers(data)

    @staticmethod
    def _tail_text(text: str, limit: int = 4000) -> str:
        """Keep only the most recent visible context for prompt checks."""
        return TerminalWriter._tail_text(text, limit=limit)

    def _has_copilot_pending_placeholder(self, current_tail: str) -> bool:
        """Whether Copilot still shows a paste placeholder after submit."""
        return self._terminal_writer._has_copilot_pending_placeholder(current_tail)

    def _disable_kkp(self, reason: str, *, force: bool = False) -> None:
        """Disable Kitty Keyboard Protocol on the PTY."""
        self._terminal_writer._disable_kkp(reason, force=force)

    def _ensure_icrnl_disabled(self, submit_bytes: bytes) -> None:
        """Clear ICRNL on the PTY if sending CR and not already cleared."""
        self._terminal_writer._ensure_icrnl_disabled(submit_bytes)

    def _wait_for_copilot_paste_echo(self, pre_paste_context: str) -> None:
        """Wait for Copilot's Ink TUI to reflect the pasted text before Enter."""
        self._terminal_writer._wait_for_copilot_paste_echo(pre_paste_context)

    def write(
        self,
        data: str,
        submit_seq: str | None = None,
    ) -> bool:
        """Write data to the controlled process PTY with optional submit sequence."""
        return self._terminal_writer.write(data, submit_seq=submit_seq)

    def _should_confirm_submit(self, data: str, submit_bytes: bytes) -> bool:
        """Whether submit confirmation should run for this write."""
        return self._terminal_writer._should_confirm_submit(data, submit_bytes)

    def _copilot_submit_nudge_delay(self, data: str) -> float | None:
        """Return the short pre-confirmation Enter retry delay for Copilot."""
        return self._terminal_writer._copilot_submit_nudge_delay(data)

    def _submit_confirmed(
        self, data: str, initial_status: str, previous_context: str
    ) -> bool:
        """Best-effort submit confirmation for Copilot PTY injections."""
        return self._terminal_writer._submit_confirmed(
            data,
            initial_status,
            previous_context,
        )

    def _confirm_submit_if_needed(
        self,
        data: str,
        submit_bytes: bytes,
        initial_status: str,
        previous_context: str,
    ) -> None:
        """Retry submit for Copilot when injected text appears to remain pending."""
        self._terminal_writer._confirm_submit_if_needed(
            data,
            submit_bytes,
            initial_status,
            previous_context,
        )

    def interrupt(self) -> None:
        """Send SIGINT to interrupt the controlled process."""
        if not self.running or not self.process:
            return

        # Send SIGINT to the process group using the saved PGID.
        pgid = getattr(self, "_pgid", None)
        if pgid is not None:
            with contextlib.suppress(ProcessLookupError, OSError):
                os.killpg(pgid, signal.SIGINT)
        else:
            with contextlib.suppress(ProcessLookupError, OSError):
                os.killpg(os.getpgid(self.process.pid), signal.SIGINT)
        with self.lock:
            old_status = self.status
            self.status = "PROCESSING"  # Interruption might cause output/processing
            if self.agent_id:
                self.registry.update_status(self.agent_id, self.status)
        if old_status != self.status:
            self._dispatch_status_callbacks(old_status, self.status)

    def get_context(self) -> str:
        """Get the current output context from the controlled process."""
        with self.lock:
            if self._pending_cr:
                self._apply_bare_cr()
                self._pending_cr = False
            raw = "".join(self._render_buffer)
        return strip_ansi(raw)

    def pty_snapshot(self) -> dict[str, Any]:
        """Return the rendered virtual terminal state.

        Exposes the pyte-backed screen so debug and diagnostic callers
        (e.g. ``GET /debug/pty``) can inspect what waiting_detection
        evaluates against without reaching into private attributes.
        """
        with self.lock:
            return self._pty_renderer.snapshot()

    def set_done(self) -> None:
        """Set status to DONE (task completed).

        The status will automatically transition to READY after DONE_TIMEOUT_SECONDS
        or when new activity is detected.
        """
        with self.lock:
            old_status = self.status
            self.status = "DONE"
            self._done_time = time.time()

            logger.debug(f"[{self.agent_id}] Status: {old_status} -> DONE")

            # Sync to registry
            if self.agent_id:
                self.registry.update_status(self.agent_id, self.status)
        if old_status != self.status:
            self._dispatch_status_callbacks(old_status, self.status)

    def stop(self, *, timeout: float = 30.0) -> None:
        """Stop the controlled process and clean up resources.

        Sends SIGTERM to the process group (using the PGID captured at
        spawn time), waits up to *timeout* seconds, then escalates to
        SIGKILL if the process is still alive.
        """
        self.running = False
        with self.lock:
            self.status = "SHUTTING_DOWN"

        proc = self.process
        pgid = getattr(self, "_pgid", None)

        if proc:
            # Send SIGTERM to the entire process group so child processes
            # (e.g. spawned CLI tools) are also terminated.
            if pgid is not None:
                with contextlib.suppress(ProcessLookupError, OSError):
                    os.killpg(pgid, signal.SIGTERM)
            else:
                with contextlib.suppress(ProcessLookupError):
                    proc.terminate()

            # Wait for the entire process group to exit, not just the
            # parent.  os.killpg(pgid, 0) raises ProcessLookupError
            # when no process in the group remains.
            if pgid is not None:
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    try:
                        os.killpg(pgid, 0)
                    except (ProcessLookupError, OSError):
                        break  # Group is gone
                    time.sleep(0.2)
                else:
                    # Timeout — escalate to SIGKILL on the whole group.
                    with contextlib.suppress(ProcessLookupError, OSError):
                        os.killpg(pgid, signal.SIGKILL)
                    # Brief grace period after SIGKILL.
                    for _ in range(10):
                        try:
                            os.killpg(pgid, 0)
                        except (ProcessLookupError, OSError):
                            break
                        time.sleep(0.2)
                    logger.warning(
                        f"[{self.agent_id}] process group {pgid} required "
                        f"SIGKILL after {timeout}s timeout"
                    )
            else:
                # No pgid — fall back to waiting on the main process only.
                try:
                    proc.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    with contextlib.suppress(ProcessLookupError):
                        proc.kill()
                    with contextlib.suppress(Exception):
                        proc.wait(timeout=2)

            # Reap the main process to avoid zombies.
            with contextlib.suppress(Exception):
                proc.wait(timeout=2)

            # Clear references to prevent re-entry and PID-reuse issues.
            self.process = None
            self._pgid = None

        # Only close master_fd if we opened it (non-interactive mode).
        # In interactive mode, pty.spawn() manages the fd.
        # Use ``is not None`` so fd=0 is not skipped.
        if self.master_fd is not None and not self.interactive:
            with contextlib.suppress(OSError):
                os.close(self.master_fd)
            self.master_fd = None

    def run_interactive(self) -> None:
        """
        Run in interactive mode.
        Includes background thread for periodic idle detection.
        """
        self.interactive = True
        self.running = True
        with self.lock:
            self._last_output_time = (
                None  # Don't start timeout detection until first output
            )

        # Start background thread for periodic idle checking
        # This ensures timeout-based idle detection works in interactive mode
        def periodic_idle_checker() -> None:
            """Background thread: check idle state periodically (every 100ms)."""
            while self.running and self.interactive:
                time.sleep(0.1)
                # Call _check_idle_state with no data to trigger timeout-based detection
                if self.running:
                    self._check_idle_state(b"")

        checker_thread = threading.Thread(target=periodic_idle_checker, daemon=True)
        checker_thread.start()

        # Note: Initial instructions sent via cli.py (A2A Task format)

        def sync_pty_window_size() -> None:
            """Sync current terminal size to the PTY master for TUI apps."""
            if self.master_fd is None:
                return

            try:
                size = shutil.get_terminal_size(fallback=(80, 24))
                rows = size.lines
                cols = size.columns
                winsize = struct.pack("HHHH", rows, cols, 0, 0)
                fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, winsize)
            except Exception:
                # Best-effort; ignore failures to avoid breaking interaction
                pass

        def handle_winch(signum: int, frame: object) -> None:
            sync_pty_window_size()

        def read_callback(fd: int) -> bytes:
            """Called when there's data to read from the PTY."""
            # Capture master_fd for API server to use
            if self.master_fd is None:
                self.master_fd = fd
                logger.debug(f"[{self.agent_id}] master_fd initialized to {fd}")
                sync_pty_window_size()

                # Get TTY device name and update registry for terminal jump
                try:
                    tty_device = os.ttyname(fd)
                    if self.agent_id:
                        self.registry.update_tty_device(self.agent_id, tty_device)
                        logger.debug(
                            f"[{self.agent_id}] TTY device registered: {tty_device}"
                        )
                except OSError:
                    # ttyname may fail if fd is not a TTY
                    pass

            data = os.read(fd, 1024)
            if data:
                # Update last output time for idle detection
                with self.lock:
                    self._last_output_time = time.time()

                self._append_output(data)
                self._check_idle_state(data)

                # Detect KKP re-activation in interactive mode too.
                # _monitor_output handles this for background mode; here
                # we mirror the same check for pty.spawn's read path.
                if self.agent_type == "copilot" and _KKP_ENABLE_RE.search(data):
                    self._disable_kkp(
                        "re-disabled via pop (interactive)"
                        if self._kkp_disabled
                        else "disabled via pop (interactive)",
                        force=True,
                    )
                    self._icrnl_cleared = False

                # Pass output through directly - AI uses a2a.py tool for routing
                return data
            else:
                # No data available
                return data

        # Inject pipe: allows write() to feed data into pty._copy's select
        # loop.  _copy monitors STDIN_FILENO; direct os.write(master_fd)
        # from another thread bypasses _copy and data is lost.
        #
        # Strategy: replace STDIN_FILENO with a merge-pipe.  A background
        # thread reads real-stdin + inject-pipe and writes to the merge-pipe.
        # _copy sees the merge-pipe as STDIN_FILENO and processes all input.
        # Inject pipe setup and pty.spawn are wrapped in a single try/finally
        # so partial initialization (raw mode set, fds opened) is always cleaned up.
        inject_r = inject_w = real_stdin_fd = -1
        original_stdin_attrs = None

        def input_callback(fd: int) -> bytes:
            """Called by pty._copy when STDIN_FILENO is readable."""
            return os.read(fd, 1024)

        use_input_callback = (
            os.environ.get("SYNAPSE_INTERACTIVE_PASSTHROUGH") != "1"
            and self.agent_type != "claude"
        )

        try:
            inject_r, inject_w = os.pipe()
            self._inject_write_fd = inject_w

            real_stdin_fd = os.dup(pty.STDIN_FILENO)
            # Set real stdin to raw mode so the merge thread receives
            # single keypresses without line buffering.  pty.spawn()
            # would normally do this on STDIN_FILENO, but we replaced it.
            try:
                original_stdin_attrs = termios.tcgetattr(real_stdin_fd)
                tty.setraw(real_stdin_fd)
            except (termios.error, OSError):
                pass  # not a tty (e.g., piped stdin)

            merge_r, merge_w = os.pipe()
            os.dup2(merge_r, pty.STDIN_FILENO)
            os.close(merge_r)  # STDIN_FILENO is now the read end

            def _stdin_merge_thread() -> None:
                """Merge real stdin and inject pipe into STDIN_FILENO."""
                import select as _sel

                try:
                    while self.running:
                        ready, _, _ = _sel.select(
                            [real_stdin_fd, inject_r], [], [], 0.1
                        )
                        for rfd in ready:
                            chunk = os.read(rfd, 4096)
                            if chunk:
                                os.write(merge_w, chunk)
                except OSError:
                    pass
                finally:
                    with contextlib.suppress(OSError):
                        os.close(merge_w)

            merge_thread = threading.Thread(target=_stdin_merge_thread, daemon=True)
            merge_thread.start()

            # Use pty.spawn for robust handling
            signal.signal(signal.SIGWINCH, handle_winch)

            cmd_list = [self.command] + self.args
            os.environ.update(self.env)
            os.environ.pop("CLAUDECODE", None)

            if use_input_callback:
                pty.spawn(cmd_list, read_callback, input_callback)
            else:
                pty.spawn(cmd_list, read_callback)
        finally:
            # Clean up inject pipe fds and restore STDIN_FILENO
            self.running = False
            self._inject_write_fd = None
            if original_stdin_attrs is not None:
                with contextlib.suppress(termios.error, OSError):
                    termios.tcsetattr(
                        real_stdin_fd, termios.TCSAFLUSH, original_stdin_attrs
                    )
            if real_stdin_fd >= 0:
                with contextlib.suppress(OSError):
                    os.dup2(real_stdin_fd, pty.STDIN_FILENO)
            for fd in (inject_r, inject_w, real_stdin_fd):
                if fd >= 0:
                    with contextlib.suppress(OSError):
                        os.close(fd)

    def _handle_interactive_input(self, data: bytes) -> None:
        """Pass through human input directly to PTY. AI handles routing decisions."""
        if self.master_fd is not None:
            os.write(self.master_fd, data)

    def _append_output(self, data: bytes) -> None:
        """Append output to buffers, normalizing carriage returns."""
        text = self._decoder.decode(data)
        with self.lock:
            # Update last output time for idle detection
            self._last_output_time = time.time()

            self.output_buffer += data
            if len(self.output_buffer) > self._max_buffer:
                self.output_buffer = self.output_buffer[-self._max_buffer :]

            # If a \r was deferred from the previous chunk, resolve it now.
            if self._pending_cr:
                self._pending_cr = False
                if text and text[0] == "\n":
                    # It was CRLF split across chunks — skip the \r,
                    # \n will be handled normally below.
                    pass
                else:
                    # Bare \r confirmed — clear current line.
                    self._apply_bare_cr()

            for idx, ch in enumerate(text):
                if ch == "\r":
                    if idx + 1 < len(text):
                        # If followed by \n (CRLF), skip — \n handles the newline
                        if text[idx + 1] == "\n":
                            pass
                        else:
                            # Bare \r: clear current line to prevent stale text
                            self._apply_bare_cr()
                    else:
                        # \r at end of chunk — defer until next chunk
                        self._pending_cr = True
                    continue
                if ch == "\b":
                    if self._render_cursor > self._render_line_start:
                        self._render_cursor -= 1
                    continue

                if self._render_cursor == len(self._render_buffer):
                    self._render_buffer.append(ch)
                else:
                    self._render_buffer[self._render_cursor] = ch
                self._render_cursor += 1

                if ch == "\n":
                    self._render_line_start = self._render_cursor

            if len(self._render_buffer) > self._max_buffer:
                remove = len(self._render_buffer) - self._max_buffer
                del self._render_buffer[:remove]
                self._render_cursor = max(0, self._render_cursor - remove)
                if self._render_cursor > len(self._render_buffer):
                    self._render_cursor = len(self._render_buffer)

                self._render_line_start = 0
                for i in range(self._render_cursor - 1, -1, -1):
                    if self._render_buffer[i] == "\n":
                        self._render_line_start = i + 1
                        break

    def _apply_bare_cr(self) -> None:
        """Clear the current line content for a bare carriage return.

        Must be called while ``self.lock`` is held.
        """
        line_end = len(self._render_buffer)
        for i in range(self._render_line_start, len(self._render_buffer)):
            if self._render_buffer[i] == "\n":
                line_end = i
                break
        del self._render_buffer[self._render_line_start : line_end]
        self._render_cursor = self._render_line_start

    def _log_pty_output(self, raw_data: bytes, text: str) -> None:
        """Log PTY output for debugging WAITING detection patterns.

        Enable with SYNAPSE_DEBUG_PTY=1 environment variable.
        Logs to ~/.synapse/logs/pty_debug.log

        Args:
            raw_data: Raw bytes from PTY.
            text: Decoded text.
        """
        from pathlib import Path

        log_dir = Path.home() / ".synapse" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "pty_debug.log"

        # Detect potential WAITING indicators
        waiting_indicators = []
        if "❯" in text:
            waiting_indicators.append("❯ (selection cursor)")
        if "☐" in text or "☑" in text:
            waiting_indicators.append("☐/☑ (checkbox)")
        if "[Y/n]" in text or "[y/N]" in text:
            waiting_indicators.append("[Y/n] prompt")
        if "Type something" in text:
            waiting_indicators.append("Type something")
        if "?" in text and len(text.strip()) < 100:
            waiting_indicators.append("? (question mark)")

        with open(log_file, "a") as f:
            import datetime

            ts = datetime.datetime.now().isoformat()
            f.write(f"\n{'=' * 60}\n")
            f.write(f"[{ts}] Agent: {self.agent_id}\n")
            f.write(f"Status: {self.status}\n")
            if waiting_indicators:
                f.write(f"WAITING indicators: {', '.join(waiting_indicators)}\n")
            f.write(f"Raw bytes ({len(raw_data)}): {raw_data!r}\n")
            f.write(f"Text: {text!r}\n")
