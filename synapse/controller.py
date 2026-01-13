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
import sys
import termios
import threading
import time
import uuid
from collections.abc import Callable

from synapse.config import (
    IDENTITY_WAIT_TIMEOUT,
    IDLE_CHECK_WINDOW,
    OUTPUT_BUFFER_MAX,
    POST_WRITE_IDLE_DELAY,
    STARTUP_DELAY,
    WRITE_PROCESSING_DELAY,
)
from synapse.input_router import InputRouter
from synapse.registry import AgentRegistry
from synapse.settings import get_settings
from synapse.utils import format_a2a_message

logger = logging.getLogger(__name__)


class TerminalController:
    def __init__(
        self,
        command: str,
        idle_regex: str | None = None,
        idle_detection: dict | None = None,
        env: dict | None = None,
        registry: AgentRegistry | None = None,
        agent_id: str | None = None,
        agent_type: str | None = None,
        submit_seq: str | None = None,
        startup_delay: int | None = None,
        args: list | None = None,
        port: int | None = None,
        skip_initial_instructions: bool = False,
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
                self._pattern_detected = False
            except Exception as e:
                logging.error(
                    f"Unexpected error compiling idle pattern '{pattern}': {e}. "
                    f"Falling back to timeout-based idle detection."
                )
                self.idle_regex = None
                self._pattern_detected = False

        # Timeout settings
        timeout = self.idle_config.get("timeout", 1.5)
        self._output_idle_threshold = timeout

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
        self._skip_initial_instructions = skip_initial_instructions

        # InputRouter for parsing agent output and routing @Agent commands
        self.input_router = InputRouter(
            registry=self.registry,
            self_agent_id=agent_id,
            self_agent_type=agent_type,
            self_port=port,
        )

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

    def _execute_a2a_action(
        self, action_func: Callable[[], bool], agent_name: str
    ) -> None:
        """Execute A2A action in a thread and write feedback to PTY."""
        try:
            success = action_func()
            feedback = self.input_router.get_feedback_message(agent_name, success)

            # Log the feedback for debugging
            logging.debug(f"A2A action for {agent_name}: success={success}")

            # In interactive mode, write feedback to stdout so user can see it
            if self.interactive and feedback:
                sys.stdout.write(feedback)
                sys.stdout.flush()

        except Exception as e:
            logging.error(f"A2A action failed for {agent_name}: {e}")

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

                        # Process output through InputRouter to detect @Agent commands
                        # Don't modify data stream - subprocess output is redirected
                        text = data.decode("utf-8", errors="replace")
                        for char in text:
                            _, action = self.input_router.process_char(char)
                            if action:
                                # Execute action in thread
                                threading.Thread(
                                    target=self._execute_a2a_action,
                                    args=(action, self.input_router.pending_agent),
                                    daemon=True,
                                ).start()

                        # For debugging/logging locally
                        # print(data.decode(errors='replace'), end='', flush=True)

                    except OSError:
                        break
                else:
                    # Periodically check idle state (timeout-based detection)
                    self._check_idle_state(b"")
        except Exception as e:
            logger.error(
                f"Error in _monitor_output for {self.agent_id}: {type(e).__name__}: {e}",
                exc_info=True,
            )

    def _check_idle_state(self, new_data: bytes) -> None:
        """Check idle state using configured strategy (pattern, timeout, or hybrid)."""
        with self.lock:
            pattern_match = False
            timeout_idle = False

            # 1. Pattern-based detection (if strategy uses it)
            if self.idle_strategy in ("pattern", "hybrid") and self.idle_regex:
                # Check pattern only if appropriate for the mode
                pattern_use = self.idle_config.get("pattern_use", "always")
                should_check_pattern = pattern_use == "always" or (
                    pattern_use == "startup_only" and not self._pattern_detected
                )

                if should_check_pattern:
                    # For pattern strategy: check if pattern is in the buffer
                    # The pattern indicates the agent is idle/ready
                    search_window = self.output_buffer[-IDLE_CHECK_WINDOW:]
                    match = self.idle_regex.search(search_window)
                    if match:
                        pattern_match = True
                        self._pattern_detected = True

            # 2. Timeout-based detection (if strategy uses it)
            if self.idle_strategy in ("timeout", "hybrid"):
                # For hybrid mode, only use timeout after pattern detected
                should_check_timeout = self.idle_strategy == "timeout" or (
                    self.idle_strategy == "hybrid" and self._pattern_detected
                )

                if should_check_timeout and self._last_output_time:
                    elapsed = time.time() - self._last_output_time
                    if elapsed >= self._output_idle_threshold:
                        timeout_idle = True

            # 3. Determine new status based on strategy
            strategy_idle_map = {
                "pattern": pattern_match,
                "timeout": timeout_idle,
                "hybrid": pattern_match or timeout_idle,
            }
            is_idle = strategy_idle_map.get(self.idle_strategy, False)

            new_status = "READY" if is_idle else "PROCESSING"

            # 4. Update status and sync to registry (only if changed)
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

            # 5. Send initial instructions on first READY
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
        settings = get_settings()
        agent_type = self.agent_type or "unknown"
        instruction_files = settings.get_instruction_files(agent_type)

        # Skip if no instruction files configured
        if not instruction_files:
            logging.info(
                f"[{self.agent_id}] No initial instructions configured, skipping."
            )
            self._identity_sent = True
            self._identity_sending = False
            return

        # Build a short message pointing to the instruction files
        # This avoids PTY paste buffer issues with large inputs
        task_id = str(uuid.uuid4())[:8]

        file_list = "\n".join(f"  - .synapse/{f}" for f in instruction_files)
        short_message = (
            f"[SYNAPSE A2A AGENT CONFIGURATION]\n"
            f"Agent: {self.agent_id} | Port: {self.port}\n\n"
            f"IMPORTANT: Read your full instructions from these files:\n"
            f"{file_list}\n\n"
            f"Read these files NOW to get your delegation rules, "
            f"A2A protocol, and other guidelines.\n"
            f"Replace {{{{agent_id}}}} with {self.agent_id} and "
            f"{{{{port}}}} with {self.port} when following instructions."
        )
        prefixed = format_a2a_message(task_id, "synapse-system", short_message)

        logging.info(
            f"[{self.agent_id}] Sending file reference instruction: {instruction_files}"
        )

        # Wait for agent to be fully ready
        time.sleep(POST_WRITE_IDLE_DELAY)

        try:
            self.write(prefixed, self._submit_seq)
            self._identity_sent = True
        except Exception as e:
            logging.error(f"Failed to send initial instructions: {e}")
        finally:
            self._identity_sending = False

    def write(self, data: str, submit_seq: str | None = None) -> None:
        """Write data to the controlled process PTY with optional submit sequence."""
        if not self.running:
            return

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
        Run in interactive mode with input routing.
        Human's input is monitored for @Agent patterns.
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
