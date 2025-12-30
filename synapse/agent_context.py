"""
Agent Context Generation for A2A Protocol

This module generates the x-synapse-context extension for Agent Cards,
providing system context to AI agents without visible PTY output.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


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
    other_agents: List[AgentInfo] = field(default_factory=list)


def build_agent_card_context(ctx: AgentContext) -> Dict[str, Any]:
    """
    Build the x-synapse-context extension for Agent Card.

    This context is embedded in the Agent Card and can be retrieved
    by the AI agent via HTTP, avoiding visible PTY output.

    Args:
        ctx: AgentContext containing agent identity and environment info.

    Returns:
        Dictionary to be included in Agent Card as x-synapse-context.
    """
    # Build available agents list
    available_agents = [
        {
            "id": agent.id,
            "type": agent.type,
            "endpoint": agent.endpoint,
            "status": agent.status,
        }
        for agent in ctx.other_agents
    ]

    return {
        "x-synapse-context": {
            "identity": ctx.agent_id,
            "agent_type": ctx.agent_type,
            "port": ctx.port,
            "routing_rules": {
                "self_patterns": [
                    f"@{ctx.agent_id}",
                    f"@{ctx.agent_type}",
                ],
                "forward_command": 'python3 synapse/tools/a2a.py send --target <agent_id> --priority 1 "<message>"',
                "instructions": {
                    "ja": f"@{ctx.agent_id} または @{ctx.agent_type} 宛てのメッセージはあなた宛てです。他のエージェント宛てのメッセージは forward_command を使って転送してください。",
                    "en": f"Messages addressed to @{ctx.agent_id} or @{ctx.agent_type} are for you. Forward messages for other agents using the forward_command.",
                },
            },
            "available_agents": available_agents,
            "priority_levels": {
                "1": "Normal message (info/chat)",
                "5": "EMERGENCY INTERRUPT (sends SIGINT before message)",
            },
            "examples": {
                "send_message": f'python3 synapse/tools/a2a.py send --target synapse-gemini-8110 --priority 1 "Hello from {ctx.agent_id}"',
                "emergency_interrupt": f'python3 synapse/tools/a2a.py send --target synapse-gemini-8110 --priority 5 "Stop immediately!"',
                "list_agents": "python3 synapse/tools/a2a.py list",
            },
        }
    }


def build_bootstrap_message(agent_id: str, port: int) -> str:
    """
    Build minimal bootstrap message to send to PTY.

    This message instructs the AI to query its Agent Card for full context,
    keeping visible PTY output minimal.

    Args:
        agent_id: The agent's unique identifier.
        port: The port the agent's API server is running on.

    Returns:
        Minimal bootstrap instruction string.
    """
    return f"""[SYNAPSE A2A] Your ID: {agent_id}
Retrieve your system context:
curl -s http://localhost:{port}/.well-known/agent.json | python3 -c "import sys,json; d=json.load(sys.stdin); print(json.dumps(d.get('x-synapse-context', {{}}), indent=2, ensure_ascii=False))"
"""


def get_other_agents_from_registry(registry, exclude_agent_id: str) -> List[AgentInfo]:
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
