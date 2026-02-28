"""Tests for Shared Memory — API endpoints.

Test-first development: these tests define the expected A2A API behavior
for /memory/* endpoints.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    """Create a FastAPI test client with shared memory enabled."""
    monkeypatch.setenv("SYNAPSE_SHARED_MEMORY_DB_PATH", str(tmp_path / "memory.db"))
    monkeypatch.setenv("SYNAPSE_SHARED_MEMORY_ENABLED", "true")

    from fastapi import FastAPI

    from synapse.a2a_compat import create_a2a_router

    app = FastAPI()
    router = create_a2a_router(
        controller=None,
        agent_type="claude",
        port=8100,
        agent_id="synapse-claude-8100",
    )
    app.include_router(router)
    yield TestClient(app)


class TestMemoryListEndpoint:
    """Tests for GET /memory/list."""

    def test_list_empty(self, app_client):
        """GET /memory/list should return empty list initially."""
        response = app_client.get("/memory/list")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        assert "memories" in data
        assert len(data["memories"]) == 0

    def test_list_after_save(self, app_client):
        """GET /memory/list should return saved memories."""
        app_client.post(
            "/memory/save",
            json={"key": "test", "content": "value", "author": "claude"},
        )
        response = app_client.get("/memory/list")
        assert response.status_code == 200
        data = response.json()
        assert len(data["memories"]) == 1

    def test_list_filter_author(self, app_client):
        """GET /memory/list?author=... should filter by author."""
        app_client.post(
            "/memory/save",
            json={"key": "k1", "content": "v1", "author": "claude"},
        )
        app_client.post(
            "/memory/save",
            json={"key": "k2", "content": "v2", "author": "gemini"},
        )
        response = app_client.get("/memory/list?author=claude")
        assert response.status_code == 200
        data = response.json()
        assert len(data["memories"]) == 1
        assert data["memories"][0]["author"] == "claude"


class TestMemorySaveEndpoint:
    """Tests for POST /memory/save."""

    def test_save_basic(self, app_client):
        """POST /memory/save should create a memory."""
        response = app_client.post(
            "/memory/save",
            json={
                "key": "auth-pattern",
                "content": "Use OAuth2 with PKCE",
                "author": "synapse-claude-8100",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["key"] == "auth-pattern"
        assert "id" in data

    def test_save_with_tags(self, app_client):
        """POST /memory/save with tags should store them."""
        response = app_client.post(
            "/memory/save",
            json={
                "key": "db-choice",
                "content": "PostgreSQL",
                "author": "claude",
                "tags": ["arch", "db"],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["tags"] == ["arch", "db"]

    def test_save_upsert(self, app_client):
        """POST /memory/save with existing key should update."""
        app_client.post(
            "/memory/save",
            json={"key": "k1", "content": "v1", "author": "claude"},
        )
        response = app_client.post(
            "/memory/save",
            json={"key": "k1", "content": "v2", "author": "gemini"},
        )
        assert response.status_code == 200
        assert response.json()["content"] == "v2"


class TestMemorySearchEndpoint:
    """Tests for GET /memory/search."""

    def test_search(self, app_client):
        """GET /memory/search?q=... should find matching memories."""
        app_client.post(
            "/memory/save",
            json={"key": "auth", "content": "OAuth2 PKCE", "author": "claude"},
        )
        app_client.post(
            "/memory/save",
            json={"key": "db", "content": "PostgreSQL", "author": "claude"},
        )
        response = app_client.get("/memory/search?q=OAuth2")
        assert response.status_code == 200
        data = response.json()
        assert len(data["memories"]) >= 1

    def test_search_no_results(self, app_client):
        """GET /memory/search?q=... should return empty for no matches."""
        response = app_client.get("/memory/search?q=nonexistent")
        assert response.status_code == 200
        assert len(response.json()["memories"]) == 0


class TestMemoryGetEndpoint:
    """Tests for GET /memory/{id_or_key}."""

    def test_get_by_key(self, app_client):
        """GET /memory/{key} should return the memory."""
        app_client.post(
            "/memory/save",
            json={"key": "test-key", "content": "value", "author": "claude"},
        )
        response = app_client.get("/memory/test-key")
        assert response.status_code == 200
        assert response.json()["content"] == "value"

    def test_get_not_found(self, app_client):
        """GET /memory/{key} should return 404 for nonexistent."""
        response = app_client.get("/memory/nonexistent")
        assert response.status_code == 404


class TestMemoryDeleteEndpoint:
    """Tests for DELETE /memory/{id_or_key}."""

    def test_delete(self, app_client):
        """DELETE /memory/{key} should remove the memory."""
        app_client.post(
            "/memory/save",
            json={"key": "to-delete", "content": "bye", "author": "claude"},
        )
        response = app_client.delete("/memory/to-delete")
        assert response.status_code == 200
        assert response.json()["deleted"] is True

    def test_delete_not_found(self, app_client):
        """DELETE /memory/{key} should return 404 for nonexistent."""
        response = app_client.delete("/memory/nonexistent")
        assert response.status_code == 404
