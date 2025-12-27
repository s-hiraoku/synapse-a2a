"""Input Router - Detects @Agent patterns and routes to other agents."""

import os
import re
import requests
from datetime import datetime
from typing import Optional, Tuple
from synapse.registry import AgentRegistry

# Simple file-based logging
LOG_DIR = os.path.expanduser("~/.synapse/logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "input_router.log")

def log(level: str, msg: str):
    """Write log message to file."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a") as f:
        f.write(f"{timestamp} - {level} - {msg}\n")


class InputRouter:
    """
    Monitors input and routes @Agent commands to other agents.

    Usage:
        router = InputRouter(registry)
        for char in input_data:
            output, action = router.process_char(char)
            if action:
                action()  # Execute A2A send
            if output:
                pty.write(output)
    """

    # Pattern: @AgentName [--response] message
    # --response: return response to sender's terminal
    A2A_PATTERN = re.compile(r'^@(\w+)(\s+--response)?\s+(.+)$', re.IGNORECASE)

    # Control characters that should clear the buffer
    CONTROL_CHARS = {'\x03', '\x04', '\x1a'}  # Ctrl+C, Ctrl+D, Ctrl+Z

    def __init__(self, registry: Optional[AgentRegistry] = None):
        self.registry = registry or AgentRegistry()
        self.line_buffer = ""
        self.in_escape_sequence = False
        self.pending_command: Optional[Tuple[str, str, bool]] = None
        self.pending_agent: Optional[str] = None  # Track last agent for feedback

    def process_char(self, char: str) -> Tuple[str, Optional[callable]]:
        """
        Process a single character of input.

        Returns:
            Tuple of (output_to_pty, action_callback)
            - output_to_pty: String to write to the PTY (for echo)
            - action_callback: Function to call for A2A action, or None
        """
        # Handle escape sequences (arrow keys, etc.)
        if char == '\x1b':
            self.in_escape_sequence = True
            return (char, None)

        if self.in_escape_sequence:
            # End of escape sequence (simplified)
            if char.isalpha():
                self.in_escape_sequence = False
            return (char, None)

        # Handle control characters
        if char in self.CONTROL_CHARS:
            self.line_buffer = ""
            return (char, None)

        # Handle backspace
        if char == '\x7f' or char == '\b':
            if self.line_buffer:
                self.line_buffer = self.line_buffer[:-1]
            return (char, None)

        # Handle Enter (line complete)
        if char in ('\r', '\n'):
            line = self.line_buffer
            self.line_buffer = ""

            match = self.A2A_PATTERN.match(line)
            if match:
                agent = match.group(1).lower()
                want_response = bool(match.group(2))
                message = match.group(3).strip()
                # Remove surrounding quotes if present
                if (message.startswith("'") and message.endswith("'")) or \
                   (message.startswith('"') and message.endswith('"')):
                    message = message[1:-1]

                self.pending_agent = agent

                # Create action callback
                def send_action():
                    return self.send_to_agent(agent, message, want_response)

                # Return empty string - don't send anything to PTY
                # The feedback will be shown separately
                return ("", send_action)
            else:
                # Normal input - pass through with newline
                return (char, None)

        # Normal character - add to buffer and echo
        self.line_buffer += char
        return (char, None)

    def process_input(self, data: str) -> list[Tuple[str, Optional[callable]]]:
        """Process multiple characters at once."""
        results = []
        for char in data:
            results.append(self.process_char(char))
        return results

    def send_to_agent(self, agent_name: str, message: str, want_response: bool = False) -> bool:
        """Send a message to another agent via A2A."""
        log("INFO", f"Sending to {agent_name}: {message}")
        agents = self.registry.list_agents()
        log("DEBUG", f"Available agents: {[info.get('agent_type') for info in agents.values()]}")

        # Find agent by name/type
        target = None
        for agent_id, info in agents.items():
            if info.get("agent_type", "").lower() == agent_name:
                target = info
                break

        if not target:
            log("ERROR", f"Agent '{agent_name}' not found")
            self.last_response = None
            return False

        endpoint = target.get("endpoint")
        if not endpoint:
            log("ERROR", f"No endpoint for agent '{agent_name}'")
            self.last_response = None
            return False

        try:
            log("INFO", f"POST {endpoint}/message")
            # Send the message
            response = requests.post(
                f"{endpoint}/message",
                json={"content": message, "priority": 1},
                timeout=10
            )
            response.raise_for_status()
            log("INFO", f"Response: {response.status_code}")

            if want_response:
                # Wait for response by polling status
                self.last_response = self._wait_for_response(endpoint, agent_name)
            else:
                self.last_response = None

            return True
        except requests.exceptions.RequestException as e:
            log("ERROR", f"Request failed: {e}")
            self.last_response = None
            return False

    def _wait_for_response(self, endpoint: str, agent_name: str, timeout: int = 60) -> Optional[str]:
        """Wait for agent to become IDLE and capture response."""
        import time

        start_time = time.time()
        initial_context = ""

        # Get initial context
        try:
            resp = requests.get(f"{endpoint}/status", timeout=5)
            initial_context = resp.json().get("context", "")
        except:
            pass

        # Poll for IDLE status
        while time.time() - start_time < timeout:
            try:
                resp = requests.get(f"{endpoint}/status", timeout=5)
                data = resp.json()
                status = data.get("status", "")
                context = data.get("context", "")

                if status == "IDLE":
                    # Extract new content since our message
                    new_content = context[len(initial_context):] if initial_context else context
                    # Clean ANSI escape codes
                    clean = re.sub(r'\x1b\[[0-9;]*m', '', new_content)
                    return clean.strip() if clean.strip() else None

                time.sleep(1)
            except:
                time.sleep(1)

        return None

    def get_feedback_message(self, agent: str, success: bool) -> str:
        """Generate feedback message for the user."""
        if success:
            if hasattr(self, 'last_response') and self.last_response:
                # Include response from agent
                return (f"\x1b[32m[→ {agent}]\x1b[0m\n"
                        f"\x1b[36m[← {agent}]\x1b[0m\n"
                        f"{self.last_response}\n")
            else:
                return f"\x1b[32m[→ {agent}]\x1b[0m\n"  # Green
        else:
            return f"\x1b[31m[✗ {agent} not found]\x1b[0m\n"  # Red

    def reset(self):
        """Reset the router state."""
        self.line_buffer = ""
        self.in_escape_sequence = False
        self.pending_command = None
