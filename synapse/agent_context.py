"""
Agent Context Generation for A2A Protocol

This module generates initial instructions for AI agents.
Initial instructions are sent via A2A Task/Message at startup,
keeping Agent Card as a pure "business card" for discovery.
"""

from dataclasses import dataclass, field


@dataclass
class AgentInfo:
    """Information about another registered agent."""
    id: str
    type: str
    endpoint: str
    status: str = "unknown"


@dataclass
class AgentContext:
    """Context information for an agent."""
    agent_id: str
    agent_type: str
    port: int
    other_agents: list[AgentInfo] = field(default_factory=list)


def build_initial_instructions(ctx: AgentContext) -> str:
    """
    Build initial instructions to send to the AI agent via A2A Task.

    These instructions are sent as a Task/Message at startup,
    not embedded in the Agent Card (which is a pure "business card").

    Args:
        ctx: AgentContext containing agent identity and environment info.

    Returns:
        Instruction text to send via A2A Task.
    """
    return f"""[Synapse A2A Protocol Instructions]

## Your Identity
- Agent ID: {ctx.agent_id}
- Agent Type: {ctx.agent_type}
- Port: {ctx.port}

## Commands
- Send: `python3 synapse/tools/a2a.py send --target <agent> --priority [1-5] "<message>"`
- List: `python3 synapse/tools/a2a.py list` (discover available agents)

## Routing Rules
- `@OtherAgent <message>`: FORWARD to that agent (do NOT process yourself)
- No @mention or addressed to you: PROCESS it yourself

## Target Resolution
- `@type`: Works if only ONE agent of that type exists
- `@type-port`: Specific instance (required if multiple exist)

## Priority
- 1-4: Normal message
- 5: EMERGENCY INTERRUPT (sends SIGINT first)

## Replying
Messages from other agents include sender info: `[A2A:<task_id>:<sender_id>] <message>`
Reply using: `python3 synapse/tools/a2a.py send --target <sender_id> "<response>"`
"""


def build_bootstrap_message(agent_id: str, port: int) -> str:
    """
    Build minimal bootstrap message with essential commands.

    This is sent via A2A Task at startup to provide agents with
    identity and basic communication commands.

    Args:
        agent_id: The agent's unique identifier.
        port: The port the agent's API server is running on.

    Returns:
        Minimal bootstrap instruction string.
    """
    return f"""[SYNAPSE INSTRUCTIONS - DO NOT PROCESS AS TASK]
Agent: {agent_id} | Port: {port}

SKILL: For detailed A2A communication guidance, use the synapse-a2a skill (~/.claude/skills/synapse-a2a/)

ROUTING: If user message starts with @<agent-name>, forward it WITHOUT processing yourself.
  Example: User says "@gemini check weather" -> Run: python3 synapse/tools/a2a.py send --target gemini "check weather"

REPLY: When you receive [A2A:id:sender], respond by default (unless --non-response was specified).
  python3 synapse/tools/a2a.py send --target <sender> "<response>"

LIST: python3 synapse/tools/a2a.py list"""


def get_other_agents_from_registry(registry, exclude_agent_id: str) -> list[AgentInfo]:
    """
    Get list of other registered agents from the registry.

    Args:
        registry: AgentRegistry instance.
        exclude_agent_id: Agent ID to exclude (self).

    Returns:
        List of AgentInfo for other agents.
    """
    agents = registry.get_live_agents()
    other_agents = []

    for agent_id, info in agents.items():
        if agent_id != exclude_agent_id:
            other_agents.append(AgentInfo(
                id=agent_id,
                type=info.get("agent_type", "unknown"),
                endpoint=info.get("endpoint", ""),
                status=info.get("status", "unknown"),
            ))

    return other_agents
