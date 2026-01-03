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

from synapse.agent_context import (
    build_bootstrap_message,
)
from synapse.config import (
    IDENTITY_WAIT_TIMEOUT,
    IDLE_CHECK_WINDOW,
    OUTPUT_BUFFER_MAX,
    OUTPUT_IDLE_THRESHOLD,
    POST_WRITE_IDLE_DELAY,
    STARTUP_DELAY,
    WRITE_PROCESSING_DELAY,
)
from synapse.input_router import InputRouter
from synapse.registry import AgentRegistry
from synapse.utils import format_a2a_message


class TerminalController:
    def __init__(
        self,
        command: str,
        idle_regex: str,
        env: dict | None = None,
        registry: AgentRegistry | None = None,
        agent_id: str | None = None,
        agent_type: str | None = None,
        submit_seq: str | None = None,
        startup_delay: int | None = None,
        args: list | None = None,
        port: int | None = None,
    ):
        self.command = command
        self.args = args or []
        # Handle special pattern names for TUI apps
        # BRACKETED_PASTE_MODE detects when ESC[?2004h is emitted (TUI ready for input)
        if idle_regex == "BRACKETED_PASTE_MODE":
            self.idle_regex = re.compile(b"\x1b\\[\\?2004h")
        else:
            self.idle_regex = re.compile(idle_regex.encode("utf-8"))
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
        self.status = "STARTING"
        self.lock = threading.Lock()
        self.running = False
        self.thread: threading.Thread | None = None
        self.registry = registry or AgentRegistry()
        self.interactive = False
        self.agent_id = agent_id
        self.agent_type = agent_type
        self.port = port or 8100  # Default port for Agent Card URL
        self._identity_sent = False
        self._submit_seq = submit_seq or "\n"
        self._startup_delay = startup_delay or STARTUP_DELAY
        self._last_output_time: float | None = (
            None  # Track last output for idle detection
        )
        self._output_idle_threshold = OUTPUT_IDLE_THRESHOLD

        # InputRouter for parsing agent output and routing @Agent commands
        self.input_router = InputRouter(
            registry=self.registry,
            self_agent_id=agent_id,
            self_agent_type=agent_type,
            self_port=port,
        )

    def start(self):
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
        self.status = "BUSY"

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

    def _monitor_output(self):
        """Monitor and process output from the controlled process PTY."""
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
                    # We process decoded text, but we don't modify the data stream here
                    # because in start() mode, the subprocess stdout is already redirected
                    # to the log file by Popen. _monitor_output just "snoops".
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

    def _check_idle_state(self, new_data):
        """Check if the output matches the idle regex pattern and update status."""
        # We match against the end of the buffer to see if we reached a prompt
        with self.lock:
            search_window = self.output_buffer[-IDLE_CHECK_WINDOW:]
            match = self.idle_regex.search(search_window)

            if match:
                was_busy = self.status != "IDLE"
                self.status = "IDLE"
                # On first IDLE, send initial instructions via A2A Task format
                if was_busy and not self._identity_sent and self.agent_id:
                    self._identity_sent = True
                    threading.Thread(
                        target=self._send_identity_instruction, daemon=True
                    ).start()
            else:
                self.status = "BUSY"

    def _send_identity_instruction(self):
        """
        Send full initial instructions to the agent on first IDLE.

        Per README design: sends A2A Task with complete instructions including
        identity, @Agent routing, available agents, and reply instructions.

        Format: [A2A:<task_id>:synapse-system] <full_instructions>
        """
        if not self.agent_id:
            return

        # Wait for master_fd to be available (set by read_callback in interactive mode)
        waited = 0.0
        while self.master_fd is None and waited < IDENTITY_WAIT_TIMEOUT:
            time.sleep(0.1)
            waited += 0.1

        if self.master_fd is None:
            print(
                f"\x1b[31m[Synapse] Error: master_fd not available after {IDENTITY_WAIT_TIMEOUT}s\x1b[0m"
            )
            return

        # Build bootstrap message with agent identity and commands
        bootstrap = build_bootstrap_message(self.agent_id, self.port)

        # Format as A2A Task: [A2A:<task_id>:synapse-system] <instructions>
        task_id = str(uuid.uuid4())[:8]
        prefixed = format_a2a_message(task_id, "synapse-system", bootstrap)

        # Wait for agent to be fully ready
        time.sleep(POST_WRITE_IDLE_DELAY)

        try:
            self.write(prefixed, self._submit_seq)
        except Exception as e:
            logging.error(f"Failed to send initial instructions: {e}")

    def write(self, data: str, submit_seq: str | None = None):
        """Write data to the controlled process PTY with optional submit sequence."""
        if not self.running:
            return

        if self.master_fd is None:
            raise ValueError(f"master_fd is None (interactive={self.interactive})")

        with self.lock:
            self.status = "BUSY"

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

    def interrupt(self):
        """Send SIGINT to interrupt the controlled process."""
        if not self.running or not self.process:
            return

        # Send SIGINT to the process group
        os.killpg(os.getpgid(self.process.pid), signal.SIGINT)
        with self.lock:
            self.status = "BUSY"  # Interruption might cause output/processing

    def get_context(self) -> str:
        """Get the current output context from the controlled process."""
        with self.lock:
            return "".join(self._render_buffer)

    def stop(self):
        """Stop the controlled process and clean up resources."""
        self.running = False
        if self.process:
            self.process.terminate()
        # Only close master_fd if we opened it (non-interactive mode)
        # In interactive mode, pty.spawn() manages the fd
        if self.master_fd and not self.interactive:
            os.close(self.master_fd)

    def run_interactive(self):
        """
        Run in interactive mode with input routing.
        Human's input is monitored for @Agent patterns.
        Uses pty.spawn() for robust terminal handling.
        """
        self.interactive = True
        self.running = True

        # Note: Initial instructions are sent via cli.py -> server.send_initial_instructions()
        # which uses A2A Task format with [A2A:id:sender] prefix

        def sync_pty_window_size():
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

        def handle_winch(signum, frame):
            sync_pty_window_size()

        def read_callback(fd):
            """Called when there's data to read from the PTY."""
            # Capture master_fd for API server to use
            if self.master_fd is None:
                self.master_fd = fd
                sync_pty_window_size()

            data = os.read(fd, 1024)
            if data:
                # DEBUG: Uncomment to log raw data
                # import sys; sys.stderr.write(f"[RAW] {repr(data[:80])}\n")

                # Update last output time for idle detection
                self._last_output_time = time.time()

                self._append_output(data)
                self._check_idle_state(data)

                # Pass output through directly - AI uses a2a.py tool for routing
                return data

            return data

        def input_callback(fd):
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

    def _handle_interactive_input(self, data: bytes):
        """Pass through human input directly to PTY. AI handles routing decisions."""
        if self.master_fd is not None:
            os.write(self.master_fd, data)

    def _append_output(self, data: bytes) -> None:
        """Append output to buffers, normalizing carriage returns for display context."""
        text = self._decoder.decode(data)
        with self.lock:
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
