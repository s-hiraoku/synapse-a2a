"""Tests for the MCP canvas_post tool."""

from __future__ import annotations

import json
from pathlib import Path

from synapse.canvas.store import CanvasStore
from synapse.mcp.server import SynapseMCPServer


def test_list_tools_includes_canvas_post() -> None:
    server = SynapseMCPServer(agent_type="codex", agent_id="synapse-codex-8120")

    tools = {tool.name: tool for tool in server.list_tools()}

    assert "canvas_post" in tools
    assert tools["canvas_post"].inputSchema == {
        "type": "object",
        "properties": {
            "format": {
                "type": "string",
                "description": "Canvas content format",
            },
            "body": {
                "type": "string",
                "description": "Content body (JSON string for structured formats).",
            },
            "title": {
                "type": "string",
                "description": "Optional card title.",
            },
            "tags": {
                "type": "string",
                "description": "Optional comma-separated tags.",
            },
        },
        "required": ["format", "body"],
    }


def test_canvas_post_tool_writes_card_and_broadcasts(
    tmp_path: Path, monkeypatch
) -> None:
    db_path = tmp_path / "canvas.db"
    monkeypatch.setenv("SYNAPSE_CANVAS_DB_PATH", str(db_path))

    events: list[tuple[str, dict[str, object]]] = []

    def _broadcast(event_type: str, data: dict[str, object]) -> None:
        events.append((event_type, data))

    monkeypatch.setattr("synapse.canvas.server._broadcast_event", _broadcast)

    server = SynapseMCPServer(
        agent_type="codex",
        agent_id="synapse-codex-8120",
        port=8120,
    )

    payload = server.call_tool(
        "canvas_post",
        {
            "format": "table",
            "body": json.dumps(
                {
                    "headers": ["Name", "Score"],
                    "rows": [["Alice", 95], ["Bob", 87]],
                }
            ),
            "title": "Leaderboard",
            "tags": "ai, canvas",
        },
    )

    assert payload["title"] == "Leaderboard"
    assert payload["agent_id"] == "synapse-codex-8120"
    assert payload["tags"] == ["ai", "canvas"]

    content = json.loads(payload["content"])
    assert content["format"] == "table"
    assert content["body"]["headers"] == ["Name", "Score"]
    assert content["body"]["rows"] == [["Alice", 95], ["Bob", 87]]

    assert events
    assert events[0][0] == "card_created"
    assert events[0][1]["card_id"] == payload["card_id"]

    store = CanvasStore(db_path=str(db_path))
    card = store.get_card(payload["card_id"])
    assert card is not None
    assert card["title"] == "Leaderboard"
    assert card["agent_id"] == "synapse-codex-8120"
    assert json.loads(card["content"])["body"]["rows"][1][0] == "Bob"
