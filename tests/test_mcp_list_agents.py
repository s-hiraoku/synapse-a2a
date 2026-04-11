"""Tests for MCP list_agents tool."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from synapse.mcp.server import SynapseMCPServer
from synapse.registry import AgentRegistry


def create_registry(
    agents: dict[str, dict[str, object]] | None = None,
    transports: dict[str, str | None] | None = None,
) -> MagicMock:
    """Create a registry mock for MCP server tests."""
    registry = MagicMock(spec=AgentRegistry)
    registry.list_agents.return_value = agents or {}
    transport_map = transports or {}
    registry.get_transport_display.side_effect = lambda agent_id: transport_map.get(
        agent_id
    )
    return registry


def make_agent(
    *,
    agent_type: str,
    port: int,
    status: str,
    name: str | None = None,
    role: str | None = None,
    skill_set: str | None = None,
    pid: int = 12345,
    working_dir: str = "/tmp/work",
    endpoint: str | None = None,
    current_task_preview: str | None = None,
    task_received_at: float | None = None,
) -> dict[str, object]:
    """Build registry agent info."""
    return {
        "agent_type": agent_type,
        "name": name,
        "role": role,
        "skill_set": skill_set,
        "port": port,
        "status": status,
        "pid": pid,
        "working_dir": working_dir,
        "endpoint": endpoint or f"http://localhost:{port}",
        "current_task_preview": current_task_preview,
        "task_received_at": task_received_at,
        "summary": None,
    }


def test_list_agents_tool_in_tools_list() -> None:
    registry = create_registry()
    server = SynapseMCPServer(registry_factory=lambda: registry)

    tools = server.list_tools()

    assert any(tool.name == "list_agents" for tool in tools)


def test_list_agents_empty_registry() -> None:
    registry = create_registry()
    server = SynapseMCPServer(registry_factory=lambda: registry)

    payload = server.call_tool("list_agents", {})

    assert payload == {"agents": []}


def test_list_agents_returns_agents() -> None:
    agents = {
        "synapse-claude-8100": make_agent(
            agent_type="claude",
            port=8100,
            status="READY",
            name="Claud",
            role="reviewer",
            skill_set="code-review",
            pid=1001,
            working_dir="/repo/a",
            current_task_preview="Review issue #380",
            task_received_at=1710000000.0,
        ),
        "synapse-gemini-8110": make_agent(
            agent_type="gemini",
            port=8110,
            status="PROCESSING",
            name="Gem",
            role="tester",
            skill_set="test-first",
            pid=1002,
            working_dir="/repo/b",
            current_task_preview="Write MCP tests",
            task_received_at=1710000100.0,
        ),
    }
    registry = create_registry(
        agents=agents,
        transports={
            "synapse-claude-8100": "UDS→",
            "synapse-gemini-8110": "TCP→",
        },
    )
    server = SynapseMCPServer(registry_factory=lambda: registry)

    payload = server.call_tool("list_agents", {})

    assert payload == {
        "agents": [
            {
                "agent_id": "synapse-claude-8100",
                "agent_type": "claude",
                "name": "Claud",
                "role": "reviewer",
                "skill_set": "code-review",
                "port": 8100,
                "status": "READY",
                "pid": 1001,
                "working_dir": "/repo/a",
                "endpoint": "http://localhost:8100",
                "transport": "UDS→",
                "current_task_preview": "Review issue #380",
                "task_received_at": 1710000000.0,
                "summary": None,
            },
            {
                "agent_id": "synapse-gemini-8110",
                "agent_type": "gemini",
                "name": "Gem",
                "role": "tester",
                "skill_set": "test-first",
                "port": 8110,
                "status": "PROCESSING",
                "pid": 1002,
                "working_dir": "/repo/b",
                "endpoint": "http://localhost:8110",
                "transport": "TCP→",
                "current_task_preview": "Write MCP tests",
                "task_received_at": 1710000100.0,
                "summary": None,
            },
        ]
    }


def test_list_agents_filter_by_status() -> None:
    agents = {
        "synapse-claude-8100": make_agent(
            agent_type="claude",
            port=8100,
            status="READY",
        ),
        "synapse-gemini-8110": make_agent(
            agent_type="gemini",
            port=8110,
            status="PROCESSING",
        ),
    }
    registry = create_registry(agents=agents)
    server = SynapseMCPServer(registry_factory=lambda: registry)

    payload = server.call_tool("list_agents", {"status": "READY"})

    assert payload == {
        "agents": [
            {
                "agent_id": "synapse-claude-8100",
                "agent_type": "claude",
                "name": None,
                "role": None,
                "skill_set": None,
                "port": 8100,
                "status": "READY",
                "pid": 12345,
                "working_dir": "/tmp/work",
                "endpoint": "http://localhost:8100",
                "transport": "-",
                "current_task_preview": None,
                "task_received_at": None,
                "summary": None,
            }
        ]
    }


def test_list_agents_returns_error_payload_on_registry_oserror() -> None:
    registry = create_registry()
    registry.list_agents.side_effect = OSError("registry unavailable")
    server = SynapseMCPServer(registry_factory=lambda: registry)

    payload = server.call_tool("list_agents", {})

    assert payload == {"agents": [], "error": "registry unavailable"}


def test_list_agents_skips_malformed_agent_entries() -> None:
    registry = create_registry(agents={"synapse-claude-8100": object()})
    server = SynapseMCPServer(registry_factory=lambda: registry)

    payload = server.call_tool("list_agents", {})

    assert payload == {"agents": []}


def test_list_agents_via_handle_request() -> None:
    agents = {
        "synapse-codex-8120": make_agent(
            agent_type="codex",
            port=8120,
            status="READY",
            name="Coder",
            role="implementer",
            skill_set="refactoring",
            pid=2001,
            working_dir="/repo/c",
        )
    }
    registry = create_registry(
        agents=agents,
        transports={"synapse-codex-8120": "UDS→"},
    )
    server = SynapseMCPServer(registry_factory=lambda: registry)

    response = server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "list_agents",
                "arguments": {"status": "READY"},
            },
        }
    )

    assert response is not None
    result = response["result"]
    assert result["content"][0]["type"] == "text"
    payload = json.loads(result["content"][0]["text"])
    assert payload == {
        "agents": [
            {
                "agent_id": "synapse-codex-8120",
                "agent_type": "codex",
                "name": "Coder",
                "role": "implementer",
                "skill_set": "refactoring",
                "port": 8120,
                "status": "READY",
                "pid": 2001,
                "working_dir": "/repo/c",
                "endpoint": "http://localhost:8120",
                "transport": "UDS→",
                "current_task_preview": None,
                "task_received_at": None,
                "summary": None,
            }
        ]
    }
