"""
Agent Context Generation for A2A Protocol

This module generates initial instructions for AI agents.
Initial instructions are sent via A2A Task/Message at startup,
keeping Agent Card as a pure "business card" for discovery.
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
    # Build available agents list
    agents_list = ""
    if ctx.other_agents:
        agents_list = "\n".join([
            f"  - {agent.id} ({agent.type}): {agent.endpoint}"
            for agent in ctx.other_agents
        ])
    else:
        agents_list = "  (No other agents currently registered)"

    return f"""[Synapse A2A Protocol Instructions]

You are participating in a multi-agent environment connected via the Synapse A2A Protocol.

## Your Identity
- Agent ID: {ctx.agent_id}
- Agent Type: {ctx.agent_type}
- Port: {ctx.port}

## How to Forward Messages (@Agent)

**IMPORTANT**: When you receive a message starting with `@AgentName` (e.g., `@gemini`, `@claude`),
you must FORWARD it to that agent **WITHOUT processing it yourself**. Do NOT execute the task - just deliver the message.

```bash
python3 synapse/tools/a2a.py send --target <agent_id> --priority [1-5] "<message>"
```

Example: If you receive `@gemini 天気を調べて`, run:
```bash
python3 synapse/tools/a2a.py send --target gemini --priority 1 "天気を調べて"
```

- Priority 1: Normal message
- Priority 5: EMERGENCY INTERRUPT (sends SIGINT first)

### Target Resolution
- `@type` (e.g., `@codex`): Works if only ONE agent of that type exists
- `@type-port` (e.g., `@codex-8120`): Specific instance (required if multiple exist)
- `@agent_id` (e.g., `@synapse-codex-8120`): Full agent ID

### When to Process vs Forward
- Message starts with `@OtherAgent`: **FORWARD** to that agent (do NOT process)
- Message addressed to you (or no @mention): **PROCESS** it yourself

## Available Agents
{agents_list}

## Sender Identification & Replying

When you receive a message from another agent, it includes sender info:
```
[A2A:<task_id>:<sender_id>] <message>
```

### How to Reply
If the message asks for a response, use the sender_id to reply:

```bash
python3 synapse/tools/a2a.py send --target <sender_id> --priority 1 "<your response>"
```

Example: If you receive `[A2A:abc123:synapse-claude-8100] What is 2+2?`
```bash
python3 synapse/tools/a2a.py send --target synapse-claude-8100 --priority 1 "The answer is 4"
```

**IMPORTANT**: When a message explicitly asks you to reply or return results, you MUST use the a2a.py tool to send your response back to the sender.

## List Agents
```bash
python3 synapse/tools/a2a.py list
```
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

ROUTING: If user message starts with @<agent-name>, forward it WITHOUT processing yourself.
  Example: User says "@gemini check weather" -> Run: python3 synapse/tools/a2a.py send --target gemini "check weather"

REPLY: When you receive [A2A:id:sender], reply using:
  python3 synapse/tools/a2a.py send --target <sender> "<response>"

LIST: python3 synapse/tools/a2a.py list"""


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
