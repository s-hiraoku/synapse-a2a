"""Tests for Canvas Server — FastAPI endpoints and SSE.

Test-first development: these tests define the expected behavior
for the Canvas server before implementation.
"""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def canvas_app(tmp_path):
    """Create a Canvas FastAPI test app."""
    from synapse.canvas.server import create_app

    app = create_app(db_path=str(tmp_path / "canvas.db"))
    return app


@pytest.fixture
def client(canvas_app):
    """Create a test client."""
    return TestClient(canvas_app)


@pytest.fixture
def a2a_canvas_client(tmp_path, monkeypatch):
    """Create a test client with the A2A router and a temp Canvas DB."""
    from synapse.a2a_compat import create_a2a_router

    monkeypatch.setenv("SYNAPSE_CANVAS_DB_PATH", str(tmp_path / "canvas.db"))

    app = FastAPI()
    router = create_a2a_router(
        controller=None,
        agent_type="claude",
        port=8100,
        agent_id="synapse-claude-8100",
    )
    app.include_router(router)
    return TestClient(app)


# ============================================================
# TestHealthEndpoint
# ============================================================


class TestHealthEndpoint:
    """Tests for GET /api/health."""

    def test_health_returns_ok(self, client):
        """Health endpoint should return status ok."""
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "cards" in data


class TestSystemPanelRegistryErrors:
    """Tests for registry error reporting in GET /api/system."""

    def test_system_panel_collects_invalid_utf8_registry_files(
        self, client, tmp_path, monkeypatch
    ):
        """Invalid UTF-8 registry files should be reported instead of crashing the endpoint."""
        registry_dir = tmp_path / "registry"
        registry_dir.mkdir()
        bad_file = registry_dir / "broken.json"
        bad_file.write_bytes(b"\xff\xfe\xfa")

        monkeypatch.setattr(
            "synapse.canvas.server.os.path.expanduser",
            lambda path: str(registry_dir) if path == "~/.a2a/registry" else path,
        )

        resp = client.get("/api/system")

        assert resp.status_code == 200
        data = resp.json()
        assert data["registry_errors"] == [
            {
                "source": "broken.json",
                "message": "'utf-8' codec can't decode byte 0xff in position 0: invalid start byte",
            }
        ]


# ============================================================
# TestCanvasRouting
# ============================================================


class TestCanvasRouting:
    """Tests for SPA routing at GET /."""

    def test_root_returns_index_shell_with_main_views(self, client):
        """GET / should return the SPA shell with canvas and dashboard views."""
        resp = client.get("/")
        assert resp.status_code == 200
        assert "nav-menu" in resp.text
        assert "canvas-view" in resp.text
        assert "dashboard-view" in resp.text

    def test_root_includes_canvas_and_dashboard_nav_links(self, client):
        """GET / should include nav links for the canvas and dashboard routes."""
        resp = client.get("/")
        assert resp.status_code == 200
        assert 'data-route="canvas"' in resp.text
        assert 'data-route="dashboard"' in resp.text


# ============================================================
# TestCreateCard
# ============================================================


class TestCreateCard:
    """Tests for POST /api/cards."""

    def test_create_card(self, client):
        """Should create a card and return it."""
        resp = client.post(
            "/api/cards",
            json={
                "type": "render",
                "content": {"format": "mermaid", "body": "graph TD; A-->B"},
                "agent_id": "synapse-claude-8103",
                "agent_name": "Gojo",
                "title": "Auth Flow",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["card_id"] is not None
        assert data["title"] == "Auth Flow"
        assert data["agent_id"] == "synapse-claude-8103"

    def test_create_card_with_card_id(self, client):
        """Should accept user-specified card_id."""
        resp = client.post(
            "/api/cards",
            json={
                "type": "render",
                "content": {"format": "mermaid", "body": "graph TD; A-->B"},
                "agent_id": "synapse-claude-8103",
                "title": "Flow",
                "card_id": "auth-flow",
            },
        )
        assert resp.status_code == 201
        assert resp.json()["card_id"] == "auth-flow"

    def test_upsert_updates_existing(self, client):
        """POST with same card_id should update, not duplicate."""
        client.post(
            "/api/cards",
            json={
                "type": "render",
                "content": {"format": "mermaid", "body": "v1"},
                "agent_id": "synapse-claude-8103",
                "title": "Flow v1",
                "card_id": "auth-flow",
            },
        )
        resp = client.post(
            "/api/cards",
            json={
                "type": "render",
                "content": {"format": "mermaid", "body": "v2"},
                "agent_id": "synapse-claude-8103",
                "title": "Flow v2",
                "card_id": "auth-flow",
            },
        )
        assert resp.status_code == 200  # Updated, not 201

        # Only one card should exist
        list_resp = client.get("/api/cards")
        assert len(list_resp.json()) == 1

    def test_upsert_rejects_different_agent(self, client):
        """POST with card_id owned by different agent should fail."""
        client.post(
            "/api/cards",
            json={
                "type": "render",
                "content": {"format": "mermaid", "body": "v1"},
                "agent_id": "synapse-claude-8103",
                "title": "Flow",
                "card_id": "auth-flow",
            },
        )
        resp = client.post(
            "/api/cards",
            json={
                "type": "render",
                "content": {"format": "mermaid", "body": "v2"},
                "agent_id": "synapse-gemini-8110",
                "title": "Flow",
                "card_id": "auth-flow",
            },
        )
        assert resp.status_code == 403

    def test_create_card_validation_error(self, client):
        """Invalid message should return 422."""
        resp = client.post(
            "/api/cards",
            json={
                "type": "invalid_type",
                "content": {"format": "mermaid", "body": "graph TD; A-->B"},
                "agent_id": "synapse-claude-8103",
            },
        )
        assert resp.status_code == 422

    def test_create_composite_card(self, client):
        """Should store composite card content as the expected JSON string."""
        content = [
            {"format": "markdown", "body": "## Overview"},
            {"format": "mermaid", "body": "graph TD; A-->B"},
            {
                "format": "table",
                "body": {
                    "headers": ["service", "status"],
                    "rows": [["auth", "ready"]],
                },
            },
        ]

        resp = client.post(
            "/api/cards",
            json={
                "type": "render",
                "content": content,
                "agent_id": "synapse-claude-8103",
                "agent_name": "Gojo",
                "title": "Composite Flow",
                "card_id": "composite-flow",
            },
        )

        assert resp.status_code == 201
        data = resp.json()
        assert data["card_id"] == "composite-flow"
        assert data["content"] == json.dumps(content, ensure_ascii=False)


# ============================================================
# TestListCards
# ============================================================


class TestListCards:
    """Tests for GET /api/cards."""

    def _add_cards(self, client):
        for i, (agent, fmt) in enumerate(
            [
                ("synapse-claude-8103", "mermaid"),
                ("synapse-gemini-8110", "table"),
                ("synapse-claude-8103", "markdown"),
            ]
        ):
            client.post(
                "/api/cards",
                json={
                    "type": "render",
                    "content": {"format": fmt, "body": f"content-{i}"},
                    "agent_id": agent,
                    "title": f"Card {i}",
                },
            )

    def test_list_all(self, client):
        """Should return all cards."""
        self._add_cards(client)
        resp = client.get("/api/cards")
        assert resp.status_code == 200
        assert len(resp.json()) == 3

    def test_list_filter_by_agent(self, client):
        """Should filter by agent_id query param."""
        self._add_cards(client)
        resp = client.get("/api/cards?agent_id=synapse-claude-8103")
        assert resp.status_code == 200
        cards = resp.json()
        assert len(cards) == 2
        assert all(c["agent_id"] == "synapse-claude-8103" for c in cards)

    def test_list_filter_by_type(self, client):
        """Should filter by content type."""
        self._add_cards(client)
        resp = client.get("/api/cards?type=mermaid")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_list_filter_by_search(self, client):
        """Should search by title."""
        self._add_cards(client)
        resp = client.get("/api/cards?search=Card 0")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_list_includes_composite_card_content(self, client):
        """Composite card content should round-trip through GET /api/cards."""
        content = [
            {"format": "markdown", "body": "## Overview"},
            {"format": "mermaid", "body": "graph TD; A-->B"},
            {
                "format": "table",
                "body": {
                    "headers": ["service", "status"],
                    "rows": [["auth", "ready"]],
                },
            },
        ]
        expected_content = json.dumps(content, ensure_ascii=False)

        client.post(
            "/api/cards",
            json={
                "type": "render",
                "content": content,
                "agent_id": "synapse-claude-8103",
                "agent_name": "Gojo",
                "title": "Composite Flow",
                "card_id": "composite-flow",
            },
        )

        resp = client.get("/api/cards")
        assert resp.status_code == 200
        cards = resp.json()
        composite = next(card for card in cards if card["card_id"] == "composite-flow")
        assert composite["content"] == expected_content


# ============================================================
# TestGetCard
# ============================================================


class TestGetCard:
    """Tests for GET /api/cards/{card_id}."""

    def test_get_existing(self, client):
        """Should return card by card_id."""
        client.post(
            "/api/cards",
            json={
                "type": "render",
                "content": {"format": "mermaid", "body": "graph TD; A-->B"},
                "agent_id": "synapse-claude-8103",
                "title": "Flow",
                "card_id": "auth-flow",
            },
        )
        resp = client.get("/api/cards/auth-flow")
        assert resp.status_code == 200
        assert resp.json()["title"] == "Flow"

    def test_get_nonexistent(self, client):
        """Should return 404 for nonexistent card."""
        resp = client.get("/api/cards/nonexistent")
        assert resp.status_code == 404


# ============================================================
# TestDeleteCard
# ============================================================


class TestDeleteCard:
    """Tests for DELETE /api/cards/{card_id}."""

    def test_delete_own_card(self, client):
        """Should delete own card."""
        client.post(
            "/api/cards",
            json={
                "type": "render",
                "content": {"format": "mermaid", "body": "v1"},
                "agent_id": "synapse-claude-8103",
                "title": "Flow",
                "card_id": "auth-flow",
            },
        )
        resp = client.delete(
            "/api/cards/auth-flow",
            headers={"X-Agent-Id": "synapse-claude-8103"},
        )
        assert resp.status_code == 200

    def test_delete_other_agent_forbidden(self, client):
        """Should reject deletion by different agent."""
        client.post(
            "/api/cards",
            json={
                "type": "render",
                "content": {"format": "mermaid", "body": "v1"},
                "agent_id": "synapse-claude-8103",
                "title": "Flow",
                "card_id": "auth-flow",
            },
        )
        resp = client.delete(
            "/api/cards/auth-flow",
            headers={"X-Agent-Id": "synapse-gemini-8110"},
        )
        assert resp.status_code == 403

    def test_delete_nonexistent(self, client):
        """Should return 404 for nonexistent card."""
        resp = client.delete(
            "/api/cards/nonexistent",
            headers={"X-Agent-Id": "synapse-claude-8103"},
        )
        assert resp.status_code == 404


# ============================================================
# TestClearCards
# ============================================================


class TestClearCards:
    """Tests for DELETE /api/cards."""

    def test_clear_all(self, client):
        """Should clear all cards."""
        for i in range(3):
            client.post(
                "/api/cards",
                json={
                    "type": "render",
                    "content": {"format": "mermaid", "body": f"v{i}"},
                    "agent_id": "synapse-claude-8103",
                    "title": f"Card {i}",
                },
            )
        resp = client.delete("/api/cards")
        assert resp.status_code == 200
        assert resp.json()["cleared"] == 3

    def test_clear_by_agent(self, client):
        """Should clear only specified agent's cards."""
        client.post(
            "/api/cards",
            json={
                "type": "render",
                "content": {"format": "mermaid", "body": "v1"},
                "agent_id": "synapse-claude-8103",
                "title": "Claude Card",
            },
        )
        client.post(
            "/api/cards",
            json={
                "type": "render",
                "content": {"format": "mermaid", "body": "v2"},
                "agent_id": "synapse-gemini-8110",
                "title": "Gemini Card",
            },
        )
        resp = client.delete("/api/cards?agent_id=synapse-claude-8103")
        assert resp.status_code == 200
        assert resp.json()["cleared"] == 1

        remaining = client.get("/api/cards").json()
        assert len(remaining) == 1
        assert remaining[0]["agent_id"] == "synapse-gemini-8110"


# ============================================================
# TestFormatsEndpoint
# ============================================================


class TestFormatsEndpoint:
    """Tests for GET /api/formats."""

    def test_list_formats(self, client):
        """Should return all registered formats."""
        resp = client.get("/api/formats")
        assert resp.status_code == 200
        formats = resp.json()
        assert "mermaid" in formats
        assert "markdown" in formats
        assert "html" in formats


# ============================================================
# TestCanvasProxy
# ============================================================


class TestCanvasProxy:
    """Tests for the A2A Canvas proxy endpoints."""

    def test_post_canvas_card_creates_card(self, a2a_canvas_client):
        """POST /canvas/cards should create a card."""
        resp = a2a_canvas_client.post(
            "/canvas/cards",
            json={
                "type": "render",
                "content": {"format": "mermaid", "body": "graph TD; Proxy-->Canvas"},
                "agent_id": "synapse-claude-8100",
                "title": "Proxy Flow",
                "card_id": "proxy-flow",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["card_id"] == "proxy-flow"
        assert data["title"] == "Proxy Flow"

    def test_get_canvas_cards_lists_cards(self, a2a_canvas_client):
        """GET /canvas/cards should return the current cards."""
        a2a_canvas_client.post(
            "/canvas/cards",
            json={
                "type": "render",
                "content": {"format": "markdown", "body": "## Proxy"},
                "agent_id": "synapse-claude-8100",
                "title": "Proxy Card",
                "card_id": "proxy-card",
            },
        )

        resp = a2a_canvas_client.get("/canvas/cards")
        assert resp.status_code == 200
        cards = resp.json()
        assert len(cards) == 1
        assert cards[0]["card_id"] == "proxy-card"

    def test_get_canvas_card_returns_single_card(self, a2a_canvas_client):
        """GET /canvas/cards/{card_id} should return one card."""
        a2a_canvas_client.post(
            "/canvas/cards",
            json={
                "type": "render",
                "content": {"format": "json", "body": {"ok": True}},
                "agent_id": "synapse-claude-8100",
                "title": "Single Proxy Card",
                "card_id": "single-proxy-card",
            },
        )

        resp = a2a_canvas_client.get("/canvas/cards/single-proxy-card")
        assert resp.status_code == 200
        data = resp.json()
        assert data["card_id"] == "single-proxy-card"
        assert data["title"] == "Single Proxy Card"

    def test_delete_canvas_card_removes_card(self, a2a_canvas_client):
        """DELETE /canvas/cards/{card_id} should delete the card."""
        a2a_canvas_client.post(
            "/canvas/cards",
            json={
                "type": "render",
                "content": {
                    "format": "code",
                    "body": "print('proxy')",
                    "lang": "python",
                },
                "agent_id": "synapse-claude-8100",
                "title": "Delete Proxy Card",
                "card_id": "delete-proxy-card",
            },
        )

        resp = a2a_canvas_client.delete(
            "/canvas/cards/delete-proxy-card",
            headers={"X-Agent-Id": "synapse-claude-8100"},
        )
        assert resp.status_code == 200
        assert resp.json() == {"deleted": "delete-proxy-card"}

        list_resp = a2a_canvas_client.get("/canvas/cards")
        assert list_resp.status_code == 200
        assert list_resp.json() == []


# ============================================================
# TestNewFormats — Phase 5 format roundtrip via API
# ============================================================


class TestNewFormats:
    """Tests for new format types via POST /api/cards + GET."""

    def _post_card(self, client, fmt, body, title="Test", card_id=None):
        payload = {
            "type": "render",
            "content": {"format": fmt, "body": body},
            "agent_id": "synapse-claude-8100",
            "title": title,
        }
        if card_id:
            payload["card_id"] = card_id
        return client.post("/api/cards", json=payload)

    def test_log_format(self, client):
        """log format should accept array of log entries."""
        body = [
            {"level": "INFO", "ts": "2026-03-07T10:00:00Z", "msg": "Server started"},
            {
                "level": "ERROR",
                "ts": "2026-03-07T10:01:00Z",
                "msg": "Connection failed",
            },
        ]
        resp = self._post_card(client, "log", body, "Server Log", "log-1")
        assert resp.status_code == 201
        data = resp.json()
        content = json.loads(data["content"])
        assert content["format"] == "log"

    def test_status_format(self, client):
        """status format should accept status object."""
        body = {"state": "success", "label": "Build", "detail": "All 42 tests pass"}
        resp = self._post_card(client, "status", body, "Build Status", "status-1")
        assert resp.status_code == 201

    def test_metric_format(self, client):
        """metric format should accept metric object."""
        body = {"value": 98.5, "unit": "%", "label": "Test Coverage"}
        resp = self._post_card(client, "metric", body, "Coverage", "metric-1")
        assert resp.status_code == 201

    def test_checklist_format(self, client):
        """checklist format should accept list of items."""
        body = [
            {"text": "Write tests", "checked": True},
            {"text": "Implement feature", "checked": False},
            {"text": "Code review", "checked": False},
        ]
        resp = self._post_card(client, "checklist", body, "Sprint Tasks", "check-1")
        assert resp.status_code == 201

    def test_timeline_format(self, client):
        """timeline format should accept list of events."""
        body = [
            {"ts": "2026-03-07T10:00:00Z", "event": "Task created", "agent": "claude"},
            {"ts": "2026-03-07T10:05:00Z", "event": "Tests written", "agent": "codex"},
        ]
        resp = self._post_card(client, "timeline", body, "Task Progress", "tl-1")
        assert resp.status_code == 201

    def test_alert_format(self, client):
        """alert format should accept alert object."""
        body = {
            "severity": "error",
            "message": "CI pipeline failed",
            "source": "github",
        }
        resp = self._post_card(client, "alert", body, "CI Alert", "alert-1")
        assert resp.status_code == 201

    def test_file_preview_format(self, client):
        """file-preview format should accept file info object."""
        body = {
            "path": "synapse/server.py",
            "lang": "python",
            "snippet": "def create_app():\n    pass",
            "start_line": 42,
        }
        resp = self._post_card(client, "file-preview", body, "File Preview", "fp-1")
        assert resp.status_code == 201

    def test_trace_format(self, client):
        """trace format should accept trace spans."""
        body = [
            {
                "name": "send_task",
                "duration_ms": 150,
                "status": "ok",
                "children": [
                    {"name": "validate", "duration_ms": 5, "status": "ok"},
                    {"name": "pty_write", "duration_ms": 120, "status": "ok"},
                ],
            },
        ]
        resp = self._post_card(client, "trace", body, "A2A Trace", "trace-1")
        assert resp.status_code == 201

    def test_task_board_format(self, client):
        """task-board format should accept kanban columns."""
        body = {
            "columns": [
                {
                    "name": "Todo",
                    "items": [
                        {"id": "1", "subject": "Write tests", "assignee": "codex"},
                    ],
                },
                {
                    "name": "Doing",
                    "items": [
                        {
                            "id": "2",
                            "subject": "Implement feature",
                            "assignee": "claude",
                        },
                    ],
                },
                {"name": "Done", "items": []},
            ]
        }
        resp = self._post_card(client, "task-board", body, "Sprint Board", "board-1")
        assert resp.status_code == 201


# ============================================================
# TestSystemPanel — GET /api/system endpoint
# ============================================================


class TestSystemPanel:
    """Tests for the system panel data endpoint."""

    def test_system_endpoint_returns_data(self, client):
        """GET /api/system should return system panel data."""
        resp = client.get("/api/system")
        assert resp.status_code == 200
        data = resp.json()
        assert "agents" in data
        assert "tasks" in data
        assert "file_locks" in data
        assert isinstance(data["agents"], list)
        assert isinstance(data["tasks"], dict)

    def test_system_tasks_has_columns(self, client):
        """Tasks in system panel should have status groups."""
        resp = client.get("/api/system")
        data = resp.json()
        tasks = data["tasks"]
        assert "pending" in tasks
        assert "in_progress" in tasks
        assert "completed" in tasks


# ============================================================
# TestSSE — Server-Sent Events
# ============================================================


class TestSSE:
    """Tests for GET /api/stream (SSE)."""

    @pytest.mark.skip(
        reason="SSE with asyncio.Queue requires async test client — deferred to Phase 3"
    )
    def test_sse_card_created_event(self, client):
        """SSE stream should emit card_created event when card is posted."""
        pass
