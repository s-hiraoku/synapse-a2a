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

from synapse.registry import AgentRegistry
from synapse.agent_context import build_bootstrap_message
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

    def _execute_a2a_action(self, action_func, agent_name):
        """Execute A2A action in a thread and write feedback to PTY."""
        try:
            success = action_func()
            feedback = self.input_router.get_feedback_message(agent_name, success)
            # Write feedback back to the agent's input (if applicable) or log it?
            # For background mode (_monitor_output), we can't easily inject into the output stream
            # that is being read by the logger, unless we write to the log explicitly.
            # But _monitor_output reads from master_fd (output of agent).
            # The feedback is for the USER (or the log).
            
            # Since _monitor_output does not write to stdout/log file itself (subprocess does),
            # we can only log it or write to master_fd (which would be INPUT to agent).
            # Writing to master_fd means the agent sees the feedback as user input.
            # That might be useful: "Message sent".
            
            # However, usually feedback is for the human operator.
            # In background mode, we should probably just log it.
            pass
        except Exception as e:
            # log error
            pass

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
            # We might want to look at the last N bytes.
            search_window = self.output_buffer[-1000:]
            match = self.idle_regex.search(search_window)
            if match:
                was_busy = self.status != "IDLE"
                self.status = "IDLE"
                # Send identity instruction on first IDLE
                if was_busy and not self._identity_sent and self.agent_id:
                    self._identity_sent = True
                    # Schedule instruction send outside the lock
                    threading.Thread(
                        target=self._send_identity_instruction,
                        daemon=True
                    ).start()
            else:
                self.status = "BUSY"

    def _send_identity_instruction(self):
        """
        Send minimal bootstrap instruction to the agent on first IDLE.

        Instead of sending full routing instructions via PTY (visible to user),
        we send a minimal bootstrap message that instructs the AI to query
        its Agent Card for full system context. This keeps PTY output clean
        while still providing necessary context via A2A protocol.
        """
        if not self.agent_id:
            return

        # Use minimal bootstrap message - full context is in Agent Card
        bootstrap = build_bootstrap_message(self.agent_id, self.port)

        # Small delay to ensure agent is ready
        time.sleep(0.5)
        try:
            self.write(bootstrap, self._submit_seq)
        except Exception:
            pass  # Silently fail if write fails

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

        # Monitor output and send identity instruction when output stops
        # This is more reliable than a fixed timer for TUI apps with varying startup times
        if self.agent_id and not self._identity_sent:
            def monitor_output_idle():
                # Wait minimum startup delay first
                time.sleep(self._startup_delay)

                while self.running and not self._identity_sent:
                    if self._last_output_time is not None:
                        elapsed = time.time() - self._last_output_time
                        if elapsed >= self._output_idle_threshold:
                            # Output has stopped, agent is ready for input
                            self._identity_sent = True
                            self._send_identity_instruction()
                            break
                    time.sleep(0.2)  # Check every 200ms

            threading.Thread(target=monitor_output_idle, daemon=True).start()

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
                # Update last output time for idle detection
                self._last_output_time = time.time()

                # Update output buffer
                with self.lock:
                    self.output_buffer += data
                    if len(self.output_buffer) > 10000:
                        self.output_buffer = self.output_buffer[-10000:]
                self._check_idle_state(data)

                # Process output through InputRouter to detect @Agent commands
                text = data.decode('utf-8', errors='replace')
                processed_output = []
                
                for char in text:
                    out_char, action = self.input_router.process_char(char)
                    processed_output.append(out_char)
                    
                    if action:
                        # Execute action in thread
                        threading.Thread(
                            target=self._execute_a2a_action,
                            args=(action, self.input_router.pending_agent),
                            daemon=True
                        ).start()
                
                # If InputRouter modifies output (e.g. swallows command line),
                # we should return the modified version.
                # However, pty.spawn writes the return value of read_callback to STDOUT.
                
                # Note: processed_output contains characters echoed by InputRouter.
                # If InputRouter.process_char swallows the command line (returns "" for \n),
                # then the user won't see the command.
                # But previously, InputRouter returned chars as they were typed (buffered).
                
                return "".join(processed_output).encode('utf-8')

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
