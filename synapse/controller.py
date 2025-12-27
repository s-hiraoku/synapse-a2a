import os
import pty
import select
import subprocess
import sys
import termios
import threading
import tty
import re
import signal
import time
import fcntl
import struct
import shutil
from typing import Optional, Callable

from synapse.input_router import InputRouter
from synapse.registry import AgentRegistry


class TerminalController:
    def __init__(self, command: str, idle_regex: str, env: Optional[dict] = None,
                 registry: Optional[AgentRegistry] = None):
        self.command = command
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
        self.input_router = InputRouter(self.registry)
        self.interactive = False

    def start(self):
        self.master_fd, self.slave_fd = pty.openpty()
        
        self.process = subprocess.Popen(
            self.command.split(),
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
                    
                    # For debugging/logging locally
                    # print(data.decode(errors='replace'), end='', flush=True)
                    
                except OSError:
                    break

    def _check_idle_state(self, new_data):
        # We match against the end of the buffer to see if we reached a prompt
        with self.lock:
            # Simple check: does the end of buffer match the regex?
            # We might want to look at the last N bytes.
            search_window = self.output_buffer[-1000:]
            if self.idle_regex.search(search_window):
                self.status = "IDLE"
            else:
                self.status = "BUSY"

    def write(self, data: str, submit_seq: str = None):
        if not self.running:
            print(f"[Controller] write() called but not running")
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
            print(f"[Controller] os.write failed: {e}, master_fd={self.master_fd}")
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
                # Update output buffer
                with self.lock:
                    self.output_buffer += data
                    if len(self.output_buffer) > 10000:
                        self.output_buffer = self.output_buffer[-10000:]
                self._check_idle_state(data)
            return data

        def input_callback(fd):
            """Called when there's data from stdin."""
            data = os.read(fd, 1024)
            if not data:
                return data

            # Process through input router
            text = data.decode('utf-8', errors='replace')
            output_bytes = b""

            for char in text:
                output, action = self.input_router.process_char(char)

                if action:
                    # Clear the child's input line (Ctrl+U) since we intercepted the command
                    # The text was already sent character-by-character, so we need to clear it
                    # Return Ctrl+U + newline to be written to the child process
                    output_bytes += b"\x15\n"  # Ctrl+U clears input line, \n completes readline

                    # Clear the displayed text (move to line start, clear to end)
                    os.write(sys.stdout.fileno(), b"\r\x1b[K")

                    # Execute A2A action
                    success = action()
                    agent = self.input_router.pending_agent or "agent"
                    feedback = self.input_router.get_feedback_message(agent, success)
                    os.write(sys.stdout.fileno(), feedback.encode())
                elif output:
                    output_bytes += output.encode()

            return output_bytes

        # Use pty.spawn for robust handling
        signal.signal(signal.SIGWINCH, handle_winch)
        pty.spawn(
            self.command.split(),
            read_callback,
            input_callback
        )

    def _handle_interactive_input(self, data: bytes):
        """Process human input through the input router."""
        text = data.decode('utf-8', errors='replace')

        for char in text:
            output, action = self.input_router.process_char(char)

            if action:
                # Execute A2A action
                success = action()
                # Show feedback
                agent = self.input_router.pending_agent or "agent"
                feedback = self.input_router.get_feedback_message(agent, success)
                os.write(sys.stdout.fileno(), feedback.encode())
            elif output:
                # Pass through to PTY
                os.write(self.master_fd, output.encode())
