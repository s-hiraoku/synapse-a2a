"""Instructions command implementation for Synapse CLI."""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from synapse.port_manager import PORT_RANGES
from synapse.registry import AgentRegistry
from synapse.settings import SynapseSettings, get_settings

if TYPE_CHECKING:
    from synapse.a2a_client import A2AClient


# Known profile names
KNOWN_PROFILES = set(PORT_RANGES.keys())

# Pattern to match agent IDs like "synapse-claude-8100"
AGENT_ID_PATTERN = re.compile(r"^synapse-(\w+)-(\d+)$")


class InstructionsCommand:
    """Manage and send initial instructions to agents."""

    def __init__(
        self,
        settings_factory: Callable[[], SynapseSettings] | None = None,
        registry_factory: Callable[[], AgentRegistry] | None = None,
        a2a_client_factory: Callable[[], A2AClient] | None = None,
        print_func: Callable[[str], None] = print,
    ) -> None:
        """
        Initialize InstructionsCommand.

        Args:
            settings_factory: Factory to create SynapseSettings instance.
            registry_factory: Factory to create AgentRegistry instance.
            a2a_client_factory: Factory to create A2AClient instance.
            print_func: Function to use for output (for testing).
        """
        self._settings_factory = settings_factory or get_settings
        self._registry_factory = registry_factory or AgentRegistry
        self._a2a_client_factory = a2a_client_factory
        self._print = print_func

    def _get_a2a_client(self) -> A2AClient:
        """Get or create A2A client."""
        if self._a2a_client_factory:
            return self._a2a_client_factory()
        from synapse.a2a_client import get_client

        return get_client()

    def _parse_target(self, target: str) -> tuple[str | None, str | None]:
        """
        Parse target string to determine profile and agent_id.

        Args:
            target: Either a profile name (claude, gemini, codex) or
                   an agent ID (synapse-claude-8100).

        Returns:
            Tuple of (profile, agent_id). If target is a profile name,
            agent_id will be None. If target is invalid, both will be None.
        """
        # Check if it's a known profile name
        if target in KNOWN_PROFILES:
            return (target, None)

        # Check if it's an agent ID pattern
        match = AGENT_ID_PATTERN.match(target)
        if match:
            profile = match.group(1)
            if profile in KNOWN_PROFILES:
                return (profile, target)

        return (None, None)

    def _find_agent(
        self, target: str
    ) -> tuple[dict[str, Any] | None, str | None, str | None]:
        """
        Find a running agent matching the target.

        Args:
            target: Profile name or agent ID.

        Returns:
            Tuple of (agent_info, agent_id, profile). All None if not found.
        """
        registry = self._registry_factory()
        agents = registry.list_agents()

        profile, agent_id = self._parse_target(target)

        if profile is None:
            return (None, None, None)

        # If specific agent ID was provided, look for it
        if agent_id:
            info = agents.get(agent_id)
            if info:
                return (info, agent_id, profile)
            return (None, None, None)

        # Find first agent of the given profile type
        for aid, info in agents.items():
            if info.get("agent_type") == profile:
                return (info, aid, profile)

        return (None, None, profile)

    def show(self, agent_type: str | None = None) -> None:
        """
        Show instruction content for an agent type.

        Args:
            agent_type: Agent type (claude, gemini, codex). If None, shows default.
        """
        settings = self._settings_factory()
        effective_type = agent_type or "default"

        # For display purposes, use placeholder values
        agent_id = f"synapse-{effective_type}-XXXX"
        port = 0

        instruction = settings.get_instruction(effective_type, agent_id, port)

        if not instruction:
            self._print(f"No instruction configured for '{effective_type}'.")
            self._print("")
            self._print("Configure instructions in .synapse/settings.json:")
            self._print('  {"instructions": {"default": "default.md"}}')
            return

        self._print(f"Instruction for '{effective_type}':")
        self._print("-" * 60)
        self._print(instruction)
        self._print("-" * 60)

    def files(self, agent_type: str | None = None) -> None:
        """
        List instruction files for an agent type.

        Args:
            agent_type: Agent type (claude, gemini, codex). If None, shows default.
        """
        settings = self._settings_factory()
        effective_type = agent_type or "default"

        files = settings.get_instruction_files(effective_type)

        if not files:
            self._print(f"No instruction files configured for '{effective_type}'.")
            self._print("")
            self._print("Configure instructions in .synapse/settings.json:")
            self._print('  {"instructions": {"default": "default.md"}}')
            return

        self._print(f"Instruction files for '{effective_type}':")
        for f in files:
            self._print(f"  - .synapse/{f}")

    def send(self, target: str, preview: bool = False) -> bool:
        """
        Send initial instructions to a running agent.

        Args:
            target: Profile name (claude, gemini, codex) or agent ID.
            preview: If True, show what would be sent without actually sending.

        Returns:
            True if successful (or preview), False otherwise.
        """
        # Find the target agent
        agent_info, agent_id, profile = self._find_agent(target)

        if profile is None:
            self._print(f"Error: '{target}' is not a valid profile or agent ID.")
            self._print(f"Valid profiles: {', '.join(sorted(KNOWN_PROFILES))}")
            return False

        if agent_info is None:
            self._print(f"Error: No running agent found for '{target}'.")
            self._print("")
            self._print("Start an agent first:")
            self._print(f"  synapse {profile}")
            self._print("")
            self._print("Or check running agents:")
            self._print("  synapse list")
            return False

        # Get instruction content
        settings = self._settings_factory()
        port = agent_info.get("port", 0)
        # profile and agent_id are guaranteed to be non-None here (checked above)
        assert profile is not None
        assert agent_id is not None
        instruction = settings.get_instruction(profile, agent_id, port)

        if not instruction:
            self._print(f"Error: No instruction configured for '{profile}'.")
            return False

        # Get instruction files for the message prefix
        files = settings.get_instruction_files(profile)

        # Build the message (same format as controller._send_identity_instruction)
        task_id = str(uuid.uuid4())[:8]
        if files:
            # Send compact message pointing to files
            message = (
                f"[SYNAPSE A2A AGENT CONFIGURATION]\n"
                f"Agent: {agent_id} | Port: {port}\n\n"
                f"IMPORTANT: Read your full instructions from these files:\n"
            )
            for f in files:
                message += f"  - .synapse/{f}\n"
            message += (
                f"\nRead these files NOW to get your delegation rules, "
                f"A2A protocol, and other guidelines.\n"
                f"Replace {{{{agent_id}}}} with {agent_id} and "
                f"{{{{port}}}} with {port} when following instructions."
            )
        else:
            # Send full instruction content
            message = instruction

        if preview:
            self._print("Preview mode - would send the following:")
            self._print("-" * 60)
            self._print(f"Target: {agent_id} (port {port})")
            self._print(f"Task ID: {task_id}")
            self._print("-" * 60)
            self._print(message)
            self._print("-" * 60)
            return True

        # Send via A2A protocol
        endpoint = f"http://localhost:{port}"
        client = self._get_a2a_client()

        # Format with A2A prefix
        prefixed_message = f"[A2A:{task_id}:synapse-system] {message}"

        task = client.send_to_local(
            endpoint=endpoint,
            message=prefixed_message,
            priority=3,  # Normal priority
            sender_info={
                "sender_id": "synapse-system",
                "sender_type": "system",
            },
        )

        if task:
            self._print(f"Instructions sent to {agent_id} successfully.")
            self._print(f"  Task ID: {task.id}")
            return True
        else:
            self._print(f"Error: Failed to send instructions to {agent_id}.")
            self._print("The agent may not be responding. Check with:")
            self._print("  synapse list")
            return False
