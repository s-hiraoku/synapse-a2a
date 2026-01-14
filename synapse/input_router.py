"""Input Router - Detects @Agent patterns and routes to other agents."""

import os
import re
from collections.abc import Callable
from datetime import datetime

from synapse.a2a_client import A2AClient, get_client
from synapse.registry import (
    AgentRegistry,
    get_valid_uds_path,
    is_port_open,
    is_process_running,
)
from synapse.settings import get_settings

# Simple file-based logging
LOG_DIR = os.path.expanduser("~/.synapse/logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "input_router.log")


def log(level: str, msg: str) -> None:
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

    # Pattern: @AgentName message
    # Response behavior is controlled by a2a.flow setting
    # Agent name can include hyphens, numbers, and colons (e.g., gemini:8110)
    A2A_PATTERN = re.compile(r"^@([\w:-]+)\s+(.+)$", re.IGNORECASE)

    # Control characters that should clear the buffer
    CONTROL_CHARS = {"\x03", "\x04", "\x1a"}  # Ctrl+C, Ctrl+D, Ctrl+Z

    def __init__(
        self,
        registry: AgentRegistry | None = None,
        a2a_client: A2AClient | None = None,
        self_agent_id: str | None = None,
        self_agent_type: str | None = None,
        self_port: int | None = None,
    ):
        self.registry = registry or AgentRegistry()
        self.a2a_client = a2a_client or get_client()
        self.line_buffer = ""
        self.in_escape_sequence = False
        self.pending_command: tuple[str, str, bool] | None = None
        self.pending_agent: str | None = None  # Track last agent for feedback
        self.is_external_agent: bool = False  # Track if last agent was external
        self.ambiguous_matches: list[str] | None = None  # Track ambiguous agent matches
        self.last_response: str | None = None  # Track last response from agent

        # Self-identification for sender info in A2A messages
        self.self_agent_id = self_agent_id
        self.self_agent_type = self_agent_type
        self.self_port = self_port

    def parse_at_mention(self, line: str) -> tuple[str, str] | None:
        """
        Parse a line for @Agent mention.

        Returns:
            Tuple of (agent_name, message) or None.
        """
        match = self.A2A_PATTERN.match(line)
        if not match:
            return None

        agent = match.group(1).lower()
        message = match.group(2).strip()

        # Remove surrounding quotes if present
        if (message.startswith("'") and message.endswith("'")) or (
            message.startswith('"') and message.endswith('"')
        ):
            message = message[1:-1]

        return (agent, message)

    def process_char(self, char: str) -> tuple[str, Callable | None]:
        """
        Process a single character of input.

        Returns:
            Tuple of (output_to_pty, action_callback)
            - output_to_pty: String to write to the PTY (for echo)
            - action_callback: Function to call for A2A action, or None
        """
        # Handle escape sequences (arrow keys, etc.)
        if char == "\x1b":
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
        if char == "\x7f" or char == "\b":
            if self.line_buffer:
                self.line_buffer = self.line_buffer[:-1]
            return (char, None)

        # Handle Enter (line complete)
        if char in ("\r", "\n"):
            line = self.line_buffer
            self.line_buffer = ""

            result = self.parse_at_mention(line)
            if result:
                agent, message = result
                self.pending_agent = agent

                # Create action callback
                def send_action() -> bool:
                    return self.route_to_agent(agent, message)

                # Return empty string - don't send anything to PTY
                # The feedback will be shown separately
                return ("", send_action)
            else:
                # Normal input - pass through with newline
                return (char, None)

        # Normal character - add to buffer and echo
        self.line_buffer += char
        return (char, None)

    def process_input(self, data: str) -> list[tuple[str, Callable | None]]:
        """Process multiple characters at once."""
        results = []
        for char in data:
            results.append(self.process_char(char))
        return results

    def route_to_agent(self, agent_name: str, message: str) -> bool:
        """Send a message to another agent via A2A."""
        log("INFO", f"Sending to {agent_name}: {message}")
        self.is_external_agent = False

        # Determine response_expected based on a2a.flow setting
        settings = get_settings()
        flow = settings.get_a2a_flow()
        response_expected = flow != "oneway"  # roundtrip or auto both expect response

        log("DEBUG", f"flow={flow}, response_expected={response_expected}")

        # First, try local agents
        agents = self.registry.list_agents()
        log("DEBUG", f"Available local agents: {list(agents.keys())}")

        # Find agent by agent_id or agent_type in local registry
        # Matching priority:
        # 1. Exact match on agent_id (e.g., synapse-claude-8100)
        # 2. Match on type-port shorthand (e.g., claude-8100)
        # 3. Match on agent_type if only one exists (e.g., claude)
        target = None
        agent_name_lower = agent_name.lower()

        # First, try exact match on agent_id
        for agent_id, info in agents.items():
            if agent_id.lower() == agent_name_lower:
                target = info
                log("DEBUG", f"Matched by agent_id: {agent_id}")
                break

        # If not found, try match on type-port shorthand (e.g., codex-8120)
        if not target:
            type_port_match = re.match(r"^(\w+)-(\d+)$", agent_name_lower)
            if type_port_match:
                target_type = type_port_match.group(1)
                target_port = int(type_port_match.group(2))
                for _agent_id, info in agents.items():
                    if (
                        info.get("agent_type", "").lower() == target_type
                        and info.get("port") == target_port
                    ):
                        target = info
                        log(
                            "DEBUG",
                            f"Matched by type-port: {target_type}-{target_port}",
                        )
                        break

        # If not found, try match on agent_type (only if single match)
        if not target:
            matching_agents = [
                (agent_id, info)
                for agent_id, info in agents.items()
                if info.get("agent_type", "").lower() == agent_name_lower
            ]
            if len(matching_agents) == 1:
                target = matching_agents[0][1]
                log("DEBUG", f"Matched by agent_type (single): {matching_agents[0][0]}")
            elif len(matching_agents) > 1:
                # Multiple agents of same type - require specific identifier
                options = [
                    f"@{info.get('agent_type')}-{info.get('port')}"
                    for _, info in matching_agents
                ]
                log("ERROR", f"Multiple agents of type '{agent_name}': {options}")
                self.ambiguous_matches = options
                self.last_response = None
                return False

        # If not found locally, check external A2A agents
        if not target:
            external_agent = self.a2a_client.registry.get(agent_name)
            if external_agent:
                log(
                    "INFO",
                    f"Found external agent: {agent_name} at {external_agent.url}",
                )
                return self._send_to_external_agent(external_agent, message)

        if not target:
            log("ERROR", f"Agent '{agent_name}' not found (local or external)")
            self.last_response = None
            return False

        # Pre-connection validation
        pid = target.get("pid")
        port = target.get("port")
        agent_id = target.get("agent_id", agent_name)
        uds_path = get_valid_uds_path(target.get("uds_path"))
        # Allow HTTP fallback if UDS fails (don't set local_only=True)
        local_only = False

        # Check if process is still alive
        if pid and not is_process_running(pid):
            log("ERROR", f"Agent '{agent_id}' process (PID {pid}) is no longer running")
            # Auto-cleanup stale registry entry
            self.registry.unregister(agent_id)
            self.last_response = None
            return False

        # Check if port is reachable (fast 1-second check)
        if not uds_path and port and not is_port_open("localhost", port, timeout=1.0):
            log("ERROR", f"Agent '{agent_id}' server on port {port} is not responding")
            self.last_response = None
            return False

        endpoint = target.get("endpoint")
        if not endpoint:
            log("ERROR", f"No endpoint for agent '{agent_name}'")
            self.last_response = None
            return False

        try:
            log("INFO", f"POST {endpoint}/tasks/send-priority (A2A)")

            # Build sender info if self-identification is available
            sender_info = None
            if self.self_agent_id:
                sender_info = {
                    "sender_id": self.self_agent_id,
                }
                if self.self_agent_type:
                    sender_info["sender_type"] = self.self_agent_type
                if self.self_port:
                    sender_info["sender_endpoint"] = (
                        f"http://localhost:{self.self_port}"
                    )

            # Send using A2A protocol
            task = self.a2a_client.send_to_local(
                endpoint=endpoint,
                message=message,
                priority=1,
                wait_for_completion=response_expected,
                timeout=60,
                sender_info=sender_info,
                response_expected=response_expected,
                uds_path=uds_path if isinstance(uds_path, str) else None,
                local_only=local_only,
                registry=self.registry,
                sender_agent_id=self.self_agent_id,
                target_agent_id=agent_id,
            )

            if task:
                log("INFO", f"Task created: {task.id}, status: {task.status}")
                if response_expected and task.artifacts:
                    self.last_response = self._extract_text_from_artifacts(
                        task.artifacts
                    )
                else:
                    self.last_response = None
                return True
            else:
                log("ERROR", "Failed to create task")
                self.last_response = None
                return False

        except Exception as e:
            log("ERROR", f"Request failed: {e}")
            self.last_response = None
            return False

    def send_to_agent(self, agent_name: str, message: str) -> bool:
        """Alias for route_to_agent."""
        return self.route_to_agent(agent_name, message)

    def _send_to_external_agent(self, agent: "object", message: str) -> bool:
        """Send a message to an external Google A2A agent."""
        self.is_external_agent = True

        # Determine response_expected based on a2a.flow setting
        settings = get_settings()
        flow = settings.get_a2a_flow()
        should_wait = flow != "oneway"  # roundtrip or auto both wait

        try:
            task = self.a2a_client.send_message(
                agent.alias,  # type: ignore[attr-defined]
                message,
                wait_for_completion=should_wait,
                timeout=60,
            )

            if task:
                if should_wait and task.artifacts:
                    self.last_response = self._extract_text_from_artifacts(
                        task.artifacts
                    )
                else:
                    self.last_response = None
                return True
            else:
                self.last_response = None
                return False

        except Exception as e:
            log("ERROR", f"External agent request failed: {e}")
            self.last_response = None
            return False

    def _extract_text_from_artifacts(self, artifacts: list) -> str | None:
        """Extract text content from A2A artifacts."""
        responses = []
        for artifact in artifacts:
            if isinstance(artifact, dict) and artifact.get("type") == "text":
                responses.append(str(artifact.get("data", "")))
        return "\n".join(responses) if responses else None

    def get_feedback_message(self, agent: str, success: bool) -> str:
        """Generate feedback message for the user."""
        # Use different indicator for external agents
        agent_type = "ext" if self.is_external_agent else "local"
        color = (
            "\x1b[35m" if self.is_external_agent else "\x1b[32m"
        )  # Magenta for external, Green for local

        if success:
            if hasattr(self, "last_response") and self.last_response:
                # Include response from agent
                return (
                    f"{color}[→ {agent} ({agent_type})]\x1b[0m\n"
                    f"\x1b[36m[← {agent}]\x1b[0m\n"
                    f"{self.last_response}\n"
                )
            else:
                return f"{color}[→ {agent} ({agent_type})]\x1b[0m\n"
        else:
            # Check for ambiguous matches
            if hasattr(self, "ambiguous_matches") and self.ambiguous_matches:
                options = ", ".join(self.ambiguous_matches)
                msg = f"\x1b[33m[⚠ Multiple '{agent}' agents found. Use: {options}]\x1b[0m\n"
                self.ambiguous_matches = None  # Clear after showing
                return msg
            return f"\x1b[31m[✗ {agent} not found]\x1b[0m\n"  # Red

    def reset(self) -> None:
        """Reset the router state."""
        self.line_buffer = ""
        self.in_escape_sequence = False
        self.pending_command = None
        self.is_external_agent = False
