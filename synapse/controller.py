import codecs
import fcntl
import logging
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

from synapse.config import (
    IDENTITY_WAIT_TIMEOUT,
    IDLE_CHECK_WINDOW,
    OUTPUT_BUFFER_MAX,
    POST_WRITE_IDLE_DELAY,
    STARTUP_DELAY,
    WRITE_PROCESSING_DELAY,
)
from synapse.registry import AgentRegistry
from synapse.settings import get_settings
from synapse.status import DONE_TIMEOUT_SECONDS
from synapse.utils import format_a2a_message, format_role_section

logger = logging.getLogger(__name__)


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
        input_ready_pattern: str | None = None,
        name: str | None = None,
        role: str | None = None,
    ):
        self.command = command
        self.args = args or []

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
                logging.error(
                    f"Invalid idle detection pattern '{pattern}': {e}. "
                    f"Falling back to timeout-based idle detection."
                )
                self.idle_regex = None
            except Exception as e:
                logging.error(
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
                logging.error(
                    f"Invalid waiting_detection regex '{waiting_regex_str}': {e}"
                )
        self._waiting_require_idle: bool = self.waiting_config.get("require_idle", True)
        self._waiting_idle_timeout: float = float(
            self.waiting_config.get("idle_timeout", 0.5)
        )
        self._waiting_pattern_time: float | None = None  # When pattern was last seen

        self.env = env or os.environ.copy()
        self.master_fd: int | None = None
        self.slave_fd: int | None = None
        self.process: subprocess.Popen[bytes] | None = None
        self.output_buffer = b""
        self._render_buffer: list[str] = []
        self._render_cursor = 0
        self._render_line_start = 0
        self._max_buffer = OUTPUT_BUFFER_MAX
        self._decoder = codecs.getincrementaldecoder("utf-8")("replace")
        self.status = "PROCESSING"
        self.lock = threading.Lock()
        self.running = False
        self.thread: threading.Thread | None = None
        self.registry = registry or AgentRegistry()
        self.interactive = False
        self.agent_id = agent_id
        self.agent_type = agent_type
        self.port = port or 8100  # Default port for Agent Card URL
        self._identity_sent = False
        self._identity_sending = False
        self._submit_seq = submit_seq or "\n"
        self._startup_delay = startup_delay or STARTUP_DELAY
        self._last_output_time: float | None = (
            None  # Track last output for idle detection
        )
        self._done_time: float | None = None  # Track when DONE status was set
        self._skip_initial_instructions = skip_initial_instructions
        self._input_ready_pattern = input_ready_pattern
        self.name = name
        self.role = role

    def start(self) -> None:
        """Start the controlled process in background mode with PTY."""
        self.master_fd, self.slave_fd = pty.openpty()

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
        1. A regex pattern matches recent output (selection UI structure)
        2. No new output for waiting_idle_timeout (if require_idle is True)

        Args:
            new_data: New data from PTY.

        Returns:
            True if in WAITING state, False otherwise.
        """
        if not self._waiting_regex:
            return False

        # Decode recent output for regex matching (last 2KB for multi-line UIs)
        text = self.output_buffer[-2048:].decode("utf-8", errors="replace")
        pattern_found = bool(self._waiting_regex.search(text))

        if not pattern_found:
            self._waiting_pattern_time = None
            return False

        # Update pattern timestamp
        self._update_waiting_pattern_time(new_data)

        # Check if waiting conditions are met
        if not self._waiting_require_idle:
            return True

        if not (self._waiting_pattern_time and self._last_output_time):
            return False

        time_since_output = time.time() - self._last_output_time
        return time_since_output >= self._waiting_idle_timeout

    def _update_waiting_pattern_time(self, new_data: bytes) -> None:
        """Update waiting pattern timestamp based on new data."""
        if self._waiting_pattern_time is None:
            self._waiting_pattern_time = time.time()
        elif new_data and self._waiting_regex:
            new_text = new_data.decode("utf-8", errors="replace")
            if self._waiting_regex.search(new_text):
                self._waiting_pattern_time = time.time()

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
                logging.debug(
                    f"[{self.agent_id}] Status: {old_status} -> {new_status} "
                    f"(strategy={self.idle_strategy}, elapsed={elapsed:.2f}s)"
                )

                # Sync to registry
                if self.agent_id:
                    success = self.registry.update_status(self.agent_id, self.status)
                    if not success:
                        logging.warning(
                            f"Failed to sync status to registry: {self.agent_id}"
                            f" -> {self.status}"
                        )

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
            logger.info(
                f"[{self.agent_id}] Skipping initial instructions (resume mode)"
            )
            self._identity_sent = True
            return

        logging.debug(
            f"[{self.agent_id}] Waiting for master_fd "
            f"(timeout={IDENTITY_WAIT_TIMEOUT}s, interactive={self.interactive})"
        )

        # Wait for master_fd to be available (set by read_callback in interactive mode)
        waited = 0.0
        while self.master_fd is None and waited < IDENTITY_WAIT_TIMEOUT:
            time.sleep(0.1)
            waited += 0.1

        if self.master_fd is None:
            logging.error(
                f"[{self.agent_id}] master_fd timeout after {IDENTITY_WAIT_TIMEOUT}s. "
                f"Agent may not have produced output yet."
            )
            msg = (
                f"[Synapse] Error: master_fd not available after"
                f" {IDENTITY_WAIT_TIMEOUT}s"
            )
            print(f"\x1b[31m{msg}\x1b[0m")
            self._identity_sending = False
            return

        logging.info(
            f"[{self.agent_id}] Sending initial instructions "
            f"(master_fd={self.master_fd}, waited={waited:.1f}s)"
        )

        # Get instruction files to read from settings
        # Use get_instruction_file_paths to get correct paths for project/user directories
        settings = get_settings()
        agent_type = self.agent_type or "unknown"
        instruction_file_paths = settings.get_instruction_file_paths(agent_type)

        # Skip if no instruction files configured
        if not instruction_file_paths:
            logging.info(
                f"[{self.agent_id}] No initial instructions configured, skipping."
            )
            self._identity_sent = True
            self._identity_sending = False
            return

        # Build a short message pointing to the instruction files
        # This avoids PTY paste buffer issues with large inputs
        # Paths already include directory prefix (.synapse/ or ~/.synapse/)
        file_list = "\n".join(f"  - {f}" for f in instruction_file_paths)
        # Use custom name for display, fall back to agent_id
        display_name = self.name if self.name else self.agent_id
        short_message = (
            f"[SYNAPSE A2A AGENT CONFIGURATION]\n"
            f"Agent: {display_name} | Port: {self.port} | ID: {self.agent_id}\n"
        )
        # Include role section if role is set (critical for agent behavior)
        if self.role:
            short_message += format_role_section(self.role)
        short_message += (
            f"\nIMPORTANT: Read your full instructions from these files:\n"
            f"{file_list}\n\n"
            f"Read these files NOW to get your delegation rules, "
            f"A2A protocol, and other guidelines.\n"
            f"Replace {{{{agent_id}}}} with {self.agent_id}, "
            f"{{{{agent_name}}}} with {display_name}, and "
            f"{{{{port}}}} with {self.port} when following instructions."
        )
        prefixed = format_a2a_message(short_message)

        logging.info(
            f"[{self.agent_id}] Sending file reference instruction: {instruction_file_paths}"
        )

        # Wait for agent to be fully ready
        # For TUI apps, we need to wait until the input prompt appears
        if self._input_ready_pattern:
            # Pattern-based detection: wait for specific prompt character
            input_ready_timeout = 10.0  # Max wait time for input area
            input_ready_wait = 0.0
            input_ready_interval = 0.5

            pattern_bytes = self._input_ready_pattern.encode()
            logging.info(
                f"[{self.agent_id}] Waiting for input pattern: {self._input_ready_pattern!r} "
                f"(bytes: {pattern_bytes!r})"
            )

            while input_ready_wait < input_ready_timeout:
                time.sleep(input_ready_interval)
                input_ready_wait += input_ready_interval

                # Check if input prompt is visible in recent output
                with self.lock:
                    recent_output = self.output_buffer[-2000:]

                # Check for the configured pattern
                if pattern_bytes in recent_output:
                    logging.info(
                        f"[{self.agent_id}] Input prompt '{self._input_ready_pattern}' "
                        f"detected after {input_ready_wait:.1f}s"
                    )
                    break
            else:
                logging.warning(
                    f"[{self.agent_id}] Input prompt '{self._input_ready_pattern}' "
                    f"not detected after {input_ready_timeout}s, proceeding anyway"
                )
        else:
            # No pattern configured: use timeout-based detection (e.g., OpenCode)
            # The IDLE detection already waited, just add a small stabilization delay
            logging.info(
                f"[{self.agent_id}] No input_ready_pattern configured, "
                "using timeout-based detection"
            )

        # Additional delay to ensure TUI is stable
        time.sleep(POST_WRITE_IDLE_DELAY)

        try:
            result = self.write(prefixed, self._submit_seq)
            logging.info(f"[{self.agent_id}] Write result: {result}")
            self._identity_sent = True
        except Exception as e:
            logging.error(f"Failed to send initial instructions: {e}")
        finally:
            self._identity_sending = False

    def write(
        self,
        data: str,
        submit_seq: str | None = None,
    ) -> bool:
        """Write data to the controlled process PTY with optional submit sequence.

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
            self.status = "PROCESSING"

        try:
            # Write data first
            data_encoded = data.encode("utf-8")
            os.write(self.master_fd, data_encoded)

            # For TUI apps, wait for input to be processed before sending Enter
            if submit_seq:
                time.sleep(WRITE_PROCESSING_DELAY)
                submit_encoded = submit_seq.encode("utf-8")
                os.write(self.master_fd, submit_encoded)
            return True
        except OSError as e:
            logging.error(f"Write to PTY failed: {e}")
            raise
        # Assuming writing triggers activity, so we are BUSY until regex matches again.

    def interrupt(self) -> None:
        """Send SIGINT to interrupt the controlled process."""
        if not self.running or not self.process:
            return

        # Send SIGINT to the process group
        os.killpg(os.getpgid(self.process.pid), signal.SIGINT)
        with self.lock:
            self.status = "PROCESSING"  # Interruption might cause output/processing

    def get_context(self) -> str:
        """Get the current output context from the controlled process."""
        with self.lock:
            return "".join(self._render_buffer)

    def set_done(self) -> None:
        """Set status to DONE (task completed).

        The status will automatically transition to READY after DONE_TIMEOUT_SECONDS
        or when new activity is detected.
        """
        with self.lock:
            old_status = self.status
            self.status = "DONE"
            self._done_time = time.time()

            logging.debug(f"[{self.agent_id}] Status: {old_status} -> DONE")

            # Sync to registry
            if self.agent_id:
                self.registry.update_status(self.agent_id, self.status)

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
                logging.debug(f"[{self.agent_id}] master_fd initialized to {fd}")
                sync_pty_window_size()

                # Get TTY device name and update registry for terminal jump
                try:
                    tty_device = os.ttyname(fd)
                    if self.agent_id:
                        self.registry.update_tty_device(self.agent_id, tty_device)
                        logging.debug(
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

        def input_callback(fd: int) -> bytes:
            """Called when there's data from stdin. Pass through to PTY."""
            data = os.read(fd, 1024)
            return data

        use_input_callback = (
            os.environ.get("SYNAPSE_INTERACTIVE_PASSTHROUGH") != "1"
            and self.agent_type != "claude"
        )

        # Use pty.spawn for robust handling
        signal.signal(signal.SIGWINCH, handle_winch)

        # Build command list: command + args
        cmd_list = [self.command] + self.args

        # pty.spawn() inherits current environment, so update os.environ
        # to pass SYNAPSE_* vars to child process for sender identification
        os.environ.update(self.env)

        if use_input_callback:
            pty.spawn(cmd_list, read_callback, input_callback)
        else:
            pty.spawn(cmd_list, read_callback)

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

            for ch in text:
                if ch == "\r":
                    self._render_cursor = self._render_line_start
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
