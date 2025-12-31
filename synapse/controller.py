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
import tty
import uuid
from typing import Callable, Optional

from synapse.registry import AgentRegistry
from synapse.agent_context import (
    AgentContext,
    build_initial_instructions,
)
from synapse.input_router import InputRouter


class TerminalController:
    def __init__(self, command: str, idle_regex: str, env: Optional[dict] = None,
                 registry: Optional[AgentRegistry] = None,
                 agent_id: Optional[str] = None, agent_type: Optional[str] = None,
                 submit_seq: Optional[str] = None, startup_delay: Optional[int] = None,
                 args: Optional[list] = None, port: Optional[int] = None):
        self.command = command
        self.args = args or []
        self.idle_regex = re.compile(idle_regex.encode('utf-8'))
        self.env = env or os.environ.copy()
        self.master_fd = None
        self.slave_fd = None
        self.process = None
        self.output_buffer = b""
        self.status = "STARTING"
        self.lock = threading.Lock()
        self.running = False
        self.thread = None
        self.registry = registry or AgentRegistry()
        self.interactive = False
        self.agent_id = agent_id
        self.agent_type = agent_type
        self.port = port or 8100  # Default port for Agent Card URL
        self._identity_sent = False
        self._submit_seq = submit_seq or "\n"
        self._startup_delay = startup_delay or 3  # Default 3 seconds
        self._last_output_time = None  # Track last output for idle detection
        self._output_idle_threshold = 1.5  # Seconds of no output = ready for input

        # InputRouter for parsing agent output and routing @Agent commands
        self.input_router = InputRouter(
            registry=self.registry,
            self_agent_id=agent_id,
            self_agent_type=agent_type,
            self_port=port
        )

    def start(self):
        self.master_fd, self.slave_fd = pty.openpty()

        # Build command list: command + args
        cmd_list = [self.command] + self.args

        self.process = subprocess.Popen(
            cmd_list,
            stdin=self.slave_fd,
            stdout=self.slave_fd,
            stderr=self.slave_fd,
            env=self.env,
            preexec_fn=os.setsid, # Create new session
            close_fds=True
        )
        
        # Close slave_fd in parent as it's now attached to child
        os.close(self.slave_fd)
        
        self.running = True
        self.thread = threading.Thread(target=self._monitor_output)
        self.thread.daemon = True
        self.thread.start()
        self.status = "BUSY"

    def _execute_a2a_action(self, action_func: Callable[[], bool], agent_name: str) -> None:
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
        while self.running and self.process.poll() is None:
            r, _, _ = select.select([self.master_fd], [], [], 0.1)
            if self.master_fd in r:
                try:
                    data = os.read(self.master_fd, 1024)
                    if not data:
                        break
                    
                    with self.lock:
                        self.output_buffer += data
                        # Keep buffer size manageable, mainly for regex matching context
                        if len(self.output_buffer) > 10000:
                             self.output_buffer = self.output_buffer[-10000:]
                    
                    self._check_idle_state(data)

                    # Process output through InputRouter to detect @Agent commands
                    # We process decoded text, but we don't modify the data stream here
                    # because in start() mode, the subprocess stdout is already redirected 
                    # to the log file by Popen. _monitor_output just "snoops".
                    text = data.decode('utf-8', errors='replace')
                    for char in text:
                        _, action = self.input_router.process_char(char)
                        if action:
                            # Execute action in thread
                            threading.Thread(
                                target=self._execute_a2a_action,
                                args=(action, self.input_router.pending_agent),
                                daemon=True
                            ).start()
                    
                    # For debugging/logging locally
                    # print(data.decode(errors='replace'), end='', flush=True)
                    
                except OSError:
                    break

    def _check_idle_state(self, new_data):
        # We match against the end of the buffer to see if we reached a prompt
        with self.lock:
            # Simple check: does the end of buffer match the regex?
            search_window = self.output_buffer[-1000:]
            match = self.idle_regex.search(search_window)

            if match:
                was_busy = self.status != "IDLE"
                self.status = "IDLE"
                # On first IDLE, send initial instructions via A2A Task format
                if was_busy and not self._identity_sent and self.agent_id:
                    self._identity_sent = True
                    # Run in thread to avoid blocking
                    threading.Thread(
                        target=self._send_identity_instruction,
                        daemon=True
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
        max_wait = 10  # seconds
        waited = 0
        while self.master_fd is None and waited < max_wait:
            time.sleep(0.1)
            waited += 0.1

        if self.master_fd is None:
            print(f"\x1b[31m[Synapse] Error: master_fd not available after {max_wait}s\x1b[0m")
            return

        # Build initial instructions (agents use 'list' command to discover others)
        ctx = AgentContext(
            agent_id=self.agent_id,
            agent_type=self.agent_type or "unknown",
            port=self.port,
        )
        instructions = build_initial_instructions(ctx)

        # Format as A2A Task: [A2A:<task_id>:synapse-system] <instructions>
        task_id = str(uuid.uuid4())[:8]
        prefixed = f"[A2A:{task_id}:synapse-system] {instructions}"

        # Small delay to ensure agent is ready
        time.sleep(0.5)
        try:
            self.write(prefixed, self._submit_seq)
        except Exception as e:
            print(f"\x1b[31m[Synapse] Error sending initial instructions: {e}\x1b[0m")

    def write(self, data: str, submit_seq: str = None):
        if not self.running:
            return

        if self.master_fd is None:
            raise ValueError(f"master_fd is None (interactive={self.interactive})")

        with self.lock:
            self.status = "BUSY"

        try:
            if submit_seq and self.interactive:
                # For TUI apps (Ink-based), send message and submit sequence separately
                # with a small delay to allow the app to process input
                os.write(self.master_fd, data.encode('utf-8'))
                time.sleep(0.1)
                os.write(self.master_fd, submit_seq.encode('utf-8'))
            else:
                # Standard write: content + submit sequence together
                full_data = data + (submit_seq or '')
                os.write(self.master_fd, full_data.encode('utf-8'))
        except OSError as e:
            raise
        # Assuming writing triggers activity, so we are BUSY until regex matches again.

    def interrupt(self):
        if not self.running or not self.process:
            return
            
        # Send SIGINT to the process group
        os.killpg(os.getpgid(self.process.pid), signal.SIGINT)
        with self.lock:
            self.status = "BUSY" # Interruption might cause output/processing

    def get_context(self) -> str:
        with self.lock:
            return self.output_buffer.decode('utf-8', errors='replace')

    def stop(self):
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

                # Update output buffer
                with self.lock:
                    self.output_buffer += data
                    if len(self.output_buffer) > 10000:
                        self.output_buffer = self.output_buffer[-10000:]
                self._check_idle_state(data)

                # Pass output through directly - AI uses a2a.py tool for routing
                return data

            return data

        def input_callback(fd):
            """Called when there's data from stdin. Pass through to PTY."""
            data = os.read(fd, 1024)
            return data  # AI handles @agent routing based on initial Task instructions

        # Use pty.spawn for robust handling
        signal.signal(signal.SIGWINCH, handle_winch)

        # Build command list: command + args
        cmd_list = [self.command] + self.args

        # pty.spawn() inherits current environment, so update os.environ
        # to pass SYNAPSE_* vars to child process for sender identification
        os.environ.update(self.env)

        pty.spawn(
            cmd_list,
            read_callback,
            input_callback
        )

    def _handle_interactive_input(self, data: bytes):
        """Pass through human input directly to PTY. AI handles routing decisions."""
        if self.master_fd is not None:
            os.write(self.master_fd, data)
