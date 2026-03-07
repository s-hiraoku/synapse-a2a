"""Tests for Canvas Server — FastAPI endpoints and SSE.

Test-first development: these tests define the expected behavior
for the Canvas server before implementation.
"""

from __future__ import annotations

import json

import pytest


@pytest.fixture
def canvas_app(tmp_path):
    """Create a Canvas FastAPI test app."""
    from synapse.canvas.server import create_app

    app = create_app(db_path=str(tmp_path / "canvas.db"))
    return app


@pytest.fixture
def client(canvas_app):
    """Create a test client."""
    from fastapi.testclient import TestClient

    return TestClient(canvas_app)


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
