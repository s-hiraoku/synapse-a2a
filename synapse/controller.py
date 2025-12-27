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

    def write(self, data: str):
        if not self.running:
            return
        
        with self.lock:
            self.status = "BUSY"
            
        bs = data.encode('utf-8')
        os.write(self.master_fd, bs)
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
        if self.master_fd:
            os.close(self.master_fd)

    def run_interactive(self):
        """
        Run in interactive mode with input routing.
        Human's input is monitored for @Agent patterns.
        """
        self.interactive = True
        self.start()

        # Save terminal settings and switch to raw mode
        stdin_fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(stdin_fd)

        try:
            tty.setraw(stdin_fd)

            while self.running and self.process.poll() is None:
                # Monitor both stdin (human input) and PTY output
                r, _, _ = select.select([sys.stdin, self.master_fd], [], [], 0.1)

                # Handle human input
                if sys.stdin in r:
                    data = os.read(stdin_fd, 1024)
                    if not data:
                        break
                    self._handle_interactive_input(data)

                # Handle PTY output (display to human)
                if self.master_fd in r:
                    try:
                        data = os.read(self.master_fd, 1024)
                        if not data:
                            break

                        # Update output buffer
                        with self.lock:
                            self.output_buffer += data
                            if len(self.output_buffer) > 10000:
                                self.output_buffer = self.output_buffer[-10000:]

                        self._check_idle_state(data)

                        # Display to human
                        os.write(sys.stdout.fileno(), data)

                    except OSError:
                        break

        except KeyboardInterrupt:
            pass
        finally:
            # Restore terminal settings
            termios.tcsetattr(stdin_fd, termios.TCSADRAIN, old_settings)
            self.stop()

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

