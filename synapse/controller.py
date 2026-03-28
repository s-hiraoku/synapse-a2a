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
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from synapse.file_safety import FileSafetyManager
    from synapse.observation import ObservationCollector

from synapse.config import (
    IDENTITY_WAIT_TIMEOUT,
    IDLE_CHECK_WINDOW,
    OUTPUT_BUFFER_MAX,
    POST_WRITE_IDLE_DELAY,
    STARTUP_DELAY,
    TASK_PROTECTION_TIMEOUT,
    WAITING_EXPIRY_SECONDS,
    WRITE_PROCESSING_DELAY,
)
from synapse.long_message import format_file_reference, get_long_message_store
from synapse.mcp.server import MCP_INSTRUCTIONS_DEFAULT_URI
from synapse.registry import AgentRegistry
from synapse.settings import get_settings
from synapse.skills import load_skill_sets
from synapse.status import DONE_TIMEOUT_SECONDS
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


class TerminalController:
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
        self.idle_strategy = self.idle_config.get("strategy", "pattern")

        # Compile pattern regex if strategy uses it
        self.idle_regex = None
        self._pattern_detected = False

        if self.idle_strategy in ("pattern", "hybrid"):
            pattern = self.idle_config.get("pattern", "")
            try:
                if pattern == "BRACKETED_PASTE_MODE":
                    self.idle_regex = re.compile(b"\x1b\\[\\?2004h")
                elif pattern:
                    self.idle_regex = re.compile(pattern.encode("utf-8"))
            except re.error as e:
                logger.error(
                    f"Invalid idle detection pattern '{pattern}': {e}. "
                    f"Falling back to timeout-based idle detection."
                )
                self.idle_regex = None
            except Exception as e:
                logger.error(
                    f"Unexpected error compiling pattern '{pattern}': {e}. "
                    f"Falling back to timeout-based idle detection."
                )
                self.idle_regex = None

        # Timeout settings
        timeout = self.idle_config.get("timeout", 1.5)
        self._output_idle_threshold = timeout

        # WAITING detection configuration (regex-based)
        self.waiting_config = waiting_detection or {}
        self._waiting_regex: re.Pattern[str] | None = None
        waiting_regex_str = self.waiting_config.get("regex")
        if waiting_regex_str:
            try:
                # Use MULTILINE flag so ^ and $ match per-line in multi-line outputs
                self._waiting_regex = re.compile(waiting_regex_str, re.MULTILINE)
            except re.error as e:
                logger.error(
                    f"Invalid waiting_detection regex '{waiting_regex_str}': {e}"
                )
        self._waiting_require_idle: bool = self.waiting_config.get("require_idle", True)
        self._waiting_idle_timeout: float = float(
            self.waiting_config.get("idle_timeout", 0.5)
        )
        self._waiting_pattern_time: float | None = None  # When pattern was last seen
        self._waiting_expiry: float = float(
            self.waiting_config.get("waiting_expiry", WAITING_EXPIRY_SECONDS)
        )

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
        self._write_lock = threading.Lock()
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

    def on_status_change(self, callback: Callable[[str, str], None]) -> None:
        """Register a callback invoked on status transitions.

        Args:
            callback: Called with (old_status, new_status) on a daemon thread.
        """
        self._status_callbacks.append(callback)

    def _dispatch_status_callbacks(self, old_status: str, new_status: str) -> None:
        """Run registered status callbacks without blocking the caller."""
        if not self._status_callbacks:
            return

        cbs = list(self._status_callbacks)

        def _fire_callbacks() -> None:
            for cb in cbs:
                try:
                    cb(old_status, new_status)
                except Exception:
                    logger.exception("Status callback error")

        threading.Thread(target=_fire_callbacks, daemon=True).start()

    def attach_observation_collector(
        self, collector: ObservationCollector | None
    ) -> None:
        """Attach an observation collector and status-change hook."""
        self._observation_collector = collector
        if self._observation_attached or not collector:
            return

        def _record_status(old_status: str, new_status: str) -> None:
            self.record_status_change(old_status, new_status, "status_transition")

        self.on_status_change(_record_status)
        self._observation_attached = True

    def _ensure_observation_collector(self) -> ObservationCollector | None:
        """Lazily initialize the observation collector from environment."""
        if self._observation_collector is None:
            try:
                from synapse.observation import ObservationCollector

                self.attach_observation_collector(ObservationCollector.from_env())
            except Exception:
                logger.exception("Failed to initialize observation collector")
                return None
        return self._observation_collector

    def record_status_change(
        self, old_status: str, new_status: str, trigger: str
    ) -> None:
        """Record a controller status transition if observation is enabled."""
        collector = self._ensure_observation_collector()
        if not collector or not self.agent_id:
            return
        collector.record_status_change(
            agent_id=self.agent_id,
            agent_type=self.agent_type,
            from_status=old_status,
            to_status=new_status,
            trigger=trigger,
        )

    def record_task_received(
        self,
        message: str,
        sender: str | None,
        priority: int,
    ) -> None:
        """Record a received task if observation is enabled."""
        collector = self._ensure_observation_collector()
        if not collector or not self.agent_id:
            return
        collector.record_task_received(
            agent_id=self.agent_id,
            agent_type=self.agent_type,
            message=message,
            sender=sender,
            priority=priority,
        )

    def record_task_completed(
        self,
        task_id: str,
        duration: float | None,
        status: str,
        output_summary: str,
    ) -> None:
        """Record a completed task if observation is enabled."""
        collector = self._ensure_observation_collector()
        if not collector or not self.agent_id:
            return
        collector.record_task_completed(
            agent_id=self.agent_id,
            agent_type=self.agent_type,
            task_id=task_id,
            duration=duration,
            status=status,
            output_summary=output_summary,
        )

    def record_error(
        self,
        error_type: str,
        error_message: str,
        recovery_action: str | None = None,
    ) -> None:
        """Record an error if observation is enabled."""
        collector = self._ensure_observation_collector()
        if not collector or not self.agent_id:
            return
        collector.record_error(
            agent_id=self.agent_id,
            agent_type=self.agent_type,
            error_type=error_type,
            error_message=error_message,
            recovery_action=recovery_action,
        )

    @staticmethod
    def task_duration_seconds(created_at: str | None) -> float | None:
        """Return elapsed seconds since task creation timestamp."""
        if not created_at:
            return None
        try:
            created_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except ValueError:
            return None
        return max(
            0.0,
            (
                datetime.now(timezone.utc) - created_dt.astimezone(timezone.utc)
            ).total_seconds(),
        )

    def set_task_active(self) -> None:
        """Increment task active count (suppresses READY while > 0)."""
        with self.lock:
            self._task_active_count += 1
            self._task_active_since = time.time()

    def clear_task_active(self) -> None:
        """Decrement task active count (allows READY when reaches 0)."""
        with self.lock:
            self._task_active_count = max(0, self._task_active_count - 1)
            if self._task_active_count == 0:
                self._task_active_since = None

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
        if self.idle_strategy not in ("pattern", "hybrid") or not self.idle_regex:
            return False

        pattern_use = self.idle_config.get("pattern_use", "always")
        should_check = pattern_use == "always" or (
            pattern_use == "startup_only" and not self._pattern_detected
        )
        if not should_check:
            return False

        search_window = self.output_buffer[-IDLE_CHECK_WINDOW:]
        if self.idle_regex.search(search_window):
            self._pattern_detected = True
            return True
        return False

    def _check_timeout_idle(self) -> bool:
        """Check for timeout-based idle detection. Must be called with lock held."""
        if self.idle_strategy not in ("timeout", "hybrid"):
            return False

        # For hybrid mode, only use timeout after pattern detected
        if self.idle_strategy == "hybrid" and not self._pattern_detected:
            return False

        if not self._last_output_time:
            return False

        elapsed: float = time.time() - self._last_output_time
        return bool(elapsed >= self._output_idle_threshold)

    def _evaluate_idle_status(self, pattern_match: bool, timeout_idle: bool) -> bool:
        """Evaluate idle status based on strategy and detection results."""
        strategy_map = {
            "pattern": pattern_match,
            "timeout": timeout_idle,
            "hybrid": pattern_match or timeout_idle,
        }
        return strategy_map.get(self.idle_strategy, False)

    def _determine_new_status(self, is_idle: bool, is_waiting: bool) -> str:
        """Determine the new status based on idle and waiting state.

        Args:
            is_idle: Whether the agent is idle (ready for input).
            is_waiting: Whether the agent is showing a selection UI.

        Returns:
            New status string: "READY", "WAITING", "PROCESSING", or "DONE".
        """
        # Base status from idle/waiting detection
        if is_waiting:
            base_status = "WAITING"
        elif is_idle:
            base_status = "READY"
        else:
            base_status = "PROCESSING"

        # Compound signal: suppress READY when task/locks active (#314)
        if base_status == "READY" and (
            self._is_task_protection_active() or self._has_file_locks()
        ):
            base_status = "PROCESSING"

        # Handle DONE state transitions
        if self.status != "DONE":
            return base_status

        # In DONE state: check for transition conditions
        if not is_idle and not is_waiting:
            # New activity detected
            self._done_time = None
            return "PROCESSING"

        if is_waiting:
            # WAITING takes priority over DONE
            self._done_time = None
            return "WAITING"

        done_timeout_expired = self._done_time and (
            time.time() - self._done_time >= DONE_TIMEOUT_SECONDS
        )
        if done_timeout_expired:
            self._done_time = None
            return "READY"

        # Stay in DONE state
        return "DONE"

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
        if not self._waiting_regex:
            return False

        # Check new_data only for pattern (fixes false positive from stale buffer)
        new_text = new_data.decode("utf-8", errors="replace") if new_data else ""
        pattern_in_new = bool(new_text and self._waiting_regex.search(new_text))

        if pattern_in_new:
            # Fresh pattern match — update timestamp
            self._waiting_pattern_time = time.time()
        elif self._waiting_pattern_time is None:
            # No fresh match and no prior match — not waiting
            return False

        # Auto-expire: if pattern was seen too long ago, do a lightweight
        # re-check of the buffer tail.  If the pattern is still present
        # (e.g., selection UI still on screen), refresh the timestamp
        # instead of expiring.  This avoids false READY when a user is
        # still looking at a prompt beyond the expiry window (#140 review).
        if self._waiting_pattern_time is not None:
            elapsed = time.time() - self._waiting_pattern_time
            if elapsed > self._waiting_expiry:
                # Lightweight re-check: last 512 bytes of buffer
                tail = self.output_buffer[-512:].decode("utf-8", errors="replace")
                if self._waiting_regex.search(tail):
                    # Pattern still visible — refresh timestamp
                    self._waiting_pattern_time = time.time()
                else:
                    self._waiting_pattern_time = None
                    return False

        # Check if waiting conditions are met
        if not self._waiting_require_idle:
            return True

        if not (self._waiting_pattern_time and self._last_output_time):
            return False

        time_since_output = time.time() - self._last_output_time
        return time_since_output >= self._waiting_idle_timeout

    def _check_idle_state(self, new_data: bytes) -> None:
        """Check idle state using configured strategy (pattern, timeout, or hybrid)."""
        with self.lock:
            pattern_match = self._check_pattern_idle()
            timeout_idle = self._check_timeout_idle()

            # Determine idle status based on strategy
            # READY = idle, ready for input
            # PROCESSING = actively working
            is_idle = self._evaluate_idle_status(pattern_match, timeout_idle)

            # Check for WAITING state (user input prompt)
            is_waiting = self._check_waiting_state(new_data)

            # Determine new status based on idle state
            new_status = self._determine_new_status(is_idle, is_waiting)

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
        if not self._input_ready_pattern:
            logger.info(
                f"[{self.agent_id}] No input_ready_pattern configured, "
                "using timeout-based detection"
            )
            return "none"

        timeout = 10.0
        interval = 0.5
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
        """Write all bytes to the PTY, retrying on partial writes.

        In interactive mode (pty.spawn), writes go through the inject pipe
        so that pty._copy's select loop picks them up correctly.  In
        background mode, writes go directly to master_fd.

        Args:
            data: The bytes to write.

        Raises:
            OSError: If ``os.write`` returns 0 (fd closed).
        """
        # Use inject pipe when available (interactive / pty.spawn mode)
        fd = self._inject_write_fd or self.master_fd
        assert fd is not None
        total = len(data)
        written = 0
        while written < total:
            n = os.write(fd, data[written:])
            if n == 0:
                raise OSError("os.write returned 0, fd may be closed")
            written += n

    def _should_type_input(self, data: str, submit_seq: str | None) -> bool:
        """Whether to emulate real typing instead of bracketed paste."""
        return bool(
            self.agent_type != "copilot"
            and submit_seq
            and self._typing_max_chars > 0
            and len(data) <= self._typing_max_chars
            and "\n" not in data
            and "\r" not in data
        )

    def _write_typed_text(self, data: str) -> None:
        """Write text character-by-character to emulate actual keyboard input."""
        typing_delay = self._typing_char_delay
        for idx, char in enumerate(data):
            self._write_all(char.encode("utf-8"))
            if typing_delay > 0 and idx + 1 < len(data):
                time.sleep(typing_delay)

    def _is_long_submit_message(self, data: str) -> bool:
        """Whether Copilot confirmation should use long-message heuristics."""
        if self.agent_type != "copilot":
            return False
        return "\n" in data or "\r" in data

    def _pending_submit_markers(self, data: str) -> list[str]:
        """Extract visible markers that indicate Copilot input still remains."""
        data_stripped = data.strip()
        if not data_stripped:
            return []

        markers: list[str] = [data_stripped]
        if "[LONG MESSAGE - FILE ATTACHED]" in data_stripped:
            markers.extend(
                [
                    "[LONG MESSAGE - FILE ATTACHED]",
                    "Please read this file",
                ]
            )
        elif self._is_long_submit_message(data):
            lines = [line.strip() for line in data.splitlines() if line.strip()]
            for line in lines:
                if len(line) >= 8 and line not in markers:
                    markers.append(line)

        return markers

    @staticmethod
    def _tail_text(text: str, limit: int = 4000) -> str:
        """Keep only the most recent visible context for prompt checks."""
        return text[-limit:]

    def _has_copilot_pending_placeholder(self, current_tail: str) -> bool:
        """Whether Copilot still shows a paste placeholder after submit.

        Copilot can reuse placeholder labels such as ``[Paste #1 - 12 lines]``
        across consecutive sends.  If the previous placeholder is still visible
        after we inject a new message, that still means the current send has
        not been confirmed yet even though the count did not increase.
        """
        return any(
            p.search(current_tail)
            for p in (_COPILOT_COMPACT_PASTE_RE, _COPILOT_SAVED_PASTE_RE)
        )

    def _wait_for_copilot_paste_echo(self, pre_paste_context: str) -> None:
        """Wait for Copilot's Ink TUI to reflect the pasted text before Enter.

        After bracketed paste, React's usePaste hook triggers a state update.
        The TUI re-renders and writes new output to PTY (echo, placeholder, or
        re-drawn prompt).  We poll PTY output until it changes from the
        pre-paste snapshot, which signals that React's render cycle completed.

        After detecting the echo, we add a small stabilization delay because
        Ink updates the screen *before* committing the pasted text into its
        internal input buffer (setState is asynchronous in React).  Without
        this settle window, CR can arrive while the buffer is still empty.

        Falls back to write_delay if no change is detected within the timeout.
        """
        deadline = time.monotonic() + _COPILOT_PASTE_ECHO_TIMEOUT
        while time.monotonic() < deadline:
            current = self._tail_text(strip_ansi(self.get_context()))
            if current != pre_paste_context:
                elapsed = _COPILOT_PASTE_ECHO_TIMEOUT - (deadline - time.monotonic())
                logger.debug(
                    f"[{self.agent_id}] paste echo detected after {elapsed:.3f}s, "
                    f"settling {_COPILOT_PASTE_ECHO_SETTLE}s for React state commit"
                )
                time.sleep(_COPILOT_PASTE_ECHO_SETTLE)
                return
            time.sleep(_COPILOT_PASTE_ECHO_POLL)
        logger.info(
            f"[{self.agent_id}] paste echo not detected within "
            f"{_COPILOT_PASTE_ECHO_TIMEOUT}s, falling back to write_delay"
        )
        if self._write_delay > 0:
            time.sleep(self._write_delay)

    def write(
        self,
        data: str,
        submit_seq: str | None = None,
    ) -> bool:
        """Write data to the controlled process PTY with optional submit sequence.

        Data and submit_seq are written as separate os.write() calls with a
        delay between them so the submit sequence arrives *outside* any
        bracketed paste boundary and is treated as a keypress, not literal
        text.

        When ``_bracketed_paste`` is enabled, data is explicitly wrapped in
        ``ESC[200~`` ... ``ESC[201~`` markers so Ink-based TUIs (e.g.
        Copilot CLI) route it through ``usePaste`` as a single event.

        Args:
            data: The data to write.
            submit_seq: Optional submit sequence (e.g., Enter key).

        Returns:
            True if write succeeded, False if process not running.
        """
        if not self.running:
            return False

        if self.master_fd is None:
            raise ValueError(f"master_fd is None (interactive={self.interactive})")

        with self.lock:
            previous_status = self.status
            self.status = "PROCESSING"

        with self._write_lock:
            try:
                # Copilot: replace line-start '/' with fullwidth solidus to
                # prevent slash-command autocomplete.  Only target line-start
                # slashes; interior slashes (URLs, paths) are left intact.
                # Skipped when bracketed paste is enabled (1.0.12+) because
                # pasted text goes through usePaste, not useInput.
                if (
                    self.agent_type == "copilot"
                    and not self._bracketed_paste
                    and "/" in data
                ):
                    data = "".join(
                        ("\uff0f" + line[1:]) if line.startswith("/") else line
                        for line in data.splitlines(keepends=True)
                    )
                pre_paste_context = self._tail_text(strip_ansi(self.get_context()))
                pre_submit_context = (
                    pre_paste_context
                    if self._should_confirm_submit(
                        data, submit_seq and submit_seq.encode("utf-8") or b""
                    )
                    else ""
                )
                use_typed_input = self._should_type_input(data, submit_seq)
                if use_typed_input:
                    self._write_typed_text(data)
                else:
                    data_bytes = data.encode("utf-8")
                    if self._bracketed_paste:
                        data_bytes = b"\x1b[200~" + data_bytes + b"\x1b[201~"
                    self._write_all(data_bytes)
                    # Drain the master fd to ensure the complete bracketed
                    # paste payload (including close marker ESC[201~) has been
                    # delivered to the slave before we start waiting for echo
                    # or sending CR.  Without this, the OS may split a large
                    # write and deliver the close marker in a separate read(),
                    # confusing Ink's paste boundary detection.
                    if self._bracketed_paste and self.master_fd is not None:
                        with contextlib.suppress(termios.error, OSError):
                            termios.tcdrain(self.master_fd)
                if submit_seq:
                    submit_bytes = submit_seq.encode("utf-8")
                    if self.agent_type == "copilot" and self._bracketed_paste:
                        self._wait_for_copilot_paste_echo(pre_paste_context)
                    elif self._write_delay > 0:
                        time.sleep(self._write_delay)
                    # Ensure ICRNL is disabled before sending submit bytes.
                    # Ink-based TUIs (Copilot) call process.stdin.setRawMode(true)
                    # on startup which may re-enable ICRNL, converting \r→\n.
                    # Ink maps \r to key.return (submit) but \n to key.enter
                    # (different event), so ICRNL must be off.
                    if (
                        submit_bytes == b"\r"
                        and not self._icrnl_cleared
                        and self.master_fd is not None
                    ):
                        try:
                            attrs = termios.tcgetattr(self.master_fd)
                            iflag = attrs[0]
                            if iflag & termios.ICRNL:
                                attrs[0] = iflag & ~termios.ICRNL
                                termios.tcsetattr(
                                    self.master_fd, termios.TCSANOW, attrs
                                )
                                logger.debug(
                                    f"[{self.agent_id}] ICRNL disabled for submit"
                                )
                            self._icrnl_cleared = True
                        except (termios.error, OSError):
                            pass
                    self._write_all(submit_bytes)
                    if (
                        self._submit_retry_delay is not None
                        and not use_typed_input
                        and self.agent_type != "copilot"
                    ):
                        time.sleep(self._submit_retry_delay)
                        self._write_all(submit_bytes)
                    if pre_submit_context:
                        with self.lock:
                            self.status = previous_status
                    self._confirm_submit_if_needed(
                        data,
                        submit_bytes,
                        previous_status,
                        previous_context=pre_submit_context,
                    )
                return True
            except OSError as e:
                logger.error(f"Write to PTY failed: {e}")
                raise

    def _should_confirm_submit(self, data: str, submit_bytes: bytes) -> bool:
        """Whether submit confirmation should run for this write."""
        retries = self._submit_confirm_retries
        if self._is_long_submit_message(data) and self._long_submit_confirm_retries:
            retries = self._long_submit_confirm_retries
        return bool(
            data
            and submit_bytes
            and self.agent_type == "copilot"
            and self._submit_confirm_timeout is not None
            and self._submit_confirm_poll_interval is not None
            and retries > 0
        )

    def _copilot_submit_nudge_delay(self, data: str) -> float | None:
        """Return the short pre-confirmation Enter retry delay for Copilot."""
        if self.agent_type != "copilot":
            return None
        if (
            self._submit_confirm_timeout is None
            or self._submit_confirm_poll_interval is None
        ):
            return None
        return (
            _COPILOT_LONG_SUBMIT_NUDGE_DELAY
            if self._is_long_submit_message(data)
            else _COPILOT_SUBMIT_NUDGE_DELAY
        )

    def _submit_confirmed(
        self, data: str, initial_status: str, previous_context: str
    ) -> bool:
        """Best-effort submit confirmation for Copilot PTY injections."""
        plain = strip_ansi(self.get_context())
        current_tail = self._tail_text(plain)
        markers = self._pending_submit_markers(data)
        pending = any(marker in current_tail for marker in markers)
        if not pending and self.agent_type == "copilot":
            pending = self._has_copilot_pending_placeholder(current_tail)

        current_status = self.status
        if initial_status == "READY" and current_status != "READY":
            return not pending
        if current_status in {"PROCESSING", "DONE"}:
            return not pending
        if current_status == "WAITING" and initial_status != "WAITING":
            return not pending

        if not markers:
            return True

        return not pending

    def _confirm_submit_if_needed(
        self,
        data: str,
        submit_bytes: bytes,
        initial_status: str,
        previous_context: str,
    ) -> None:
        """Retry submit for Copilot when injected text appears to remain pending."""
        if not self._should_confirm_submit(data, submit_bytes):
            return

        assert self._submit_confirm_timeout is not None
        assert self._submit_confirm_poll_interval is not None
        confirm_timeout = self._submit_confirm_timeout
        confirm_retries = self._submit_confirm_retries
        if self._is_long_submit_message(data):
            if self._long_submit_confirm_timeout is not None:
                confirm_timeout = self._long_submit_confirm_timeout
            if self._long_submit_confirm_retries is not None:
                confirm_retries = self._long_submit_confirm_retries

        poll_limit = max(
            1,
            math.ceil(confirm_timeout / self._submit_confirm_poll_interval),
        )
        nudge_delay = self._copilot_submit_nudge_delay(data)
        if nudge_delay is not None:
            time.sleep(nudge_delay)
            if not self._submit_confirmed(data, initial_status, previous_context):
                self._write_all(submit_bytes)

        for attempt in range(confirm_retries + 1):
            for _ in range(poll_limit):
                if self._submit_confirmed(data, initial_status, previous_context):
                    return
                time.sleep(self._submit_confirm_poll_interval)

            if attempt < confirm_retries:
                self._write_all(submit_bytes)

        # Dump diagnostic info on failure
        plain = strip_ansi(self.get_context())
        tail = self._tail_text(plain)
        markers = self._pending_submit_markers(data)
        has_placeholder = self._has_copilot_pending_placeholder(tail)
        message = (
            f"[{self.agent_id}] submit confirmation failed after "
            f"{confirm_retries} retries"
        )
        logger.warning(message)
        logger.debug(
            f"[{self.agent_id}] submit_diag: "
            f"markers={markers!r} "
            f"has_placeholder={has_placeholder} "
            f"status={self.status} "
            f"tail_last200={tail[-200:]!r}"
        )
        self._log_inject(
            "WARN",
            f"submit confirmation failed retries={confirm_retries}",
        )

    def interrupt(self) -> None:
        """Send SIGINT to interrupt the controlled process."""
        if not self.running or not self.process:
            return

        # Send SIGINT to the process group
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
            raw = "".join(self._render_buffer)
        return strip_ansi(raw)

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

    def stop(self) -> None:
        """Stop the controlled process and clean up resources."""
        self.running = False
        if self.process:
            self.process.terminate()
        # Only close master_fd if we opened it (non-interactive mode)
        # In interactive mode, pty.spawn() manages the fd
        if self.master_fd and not self.interactive:
            os.close(self.master_fd)

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
