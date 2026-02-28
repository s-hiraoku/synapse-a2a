"""Tests for Shared Memory — API endpoints.

Test-first development: these tests define the expected A2A API behavior
for /memory/* endpoints.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app_client(tmp_path):
    """Create a FastAPI test client with shared memory enabled."""
    os.environ["SYNAPSE_SHARED_MEMORY_DB_PATH"] = str(tmp_path / "memory.db")
    os.environ["SYNAPSE_SHARED_MEMORY_ENABLED"] = "true"

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

    os.environ.pop("SYNAPSE_SHARED_MEMORY_DB_PATH", None)
    os.environ.pop("SYNAPSE_SHARED_MEMORY_ENABLED", None)


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


# --------------------------------------------------------
# #286: MemorySaveRequest.notify field should trigger broadcast
# --------------------------------------------------------


class TestMemorySaveNotify:
    """Tests for POST /memory/save with notify=True (#286)."""

    def test_save_with_notify_calls_broadcast(self, app_client):
        """POST /memory/save with notify=True should trigger broadcast."""
        with patch("synapse.a2a_compat._memory_broadcast_notify_api") as mock_broadcast:
            response = app_client.post(
                "/memory/save",
                json={
                    "key": "shared-info",
                    "content": "Important knowledge",
                    "author": "claude",
                    "notify": True,
                },
            )
            assert response.status_code == 200
            mock_broadcast.assert_called_once_with("shared-info")

    def test_save_without_notify_does_not_broadcast(self, app_client):
        """POST /memory/save with notify=False should NOT trigger broadcast."""
        with patch("synapse.a2a_compat._memory_broadcast_notify_api") as mock_broadcast:
            response = app_client.post(
                "/memory/save",
                json={
                    "key": "quiet-info",
                    "content": "No broadcast needed",
                    "author": "claude",
                    "notify": False,
                },
            )
            assert response.status_code == 200
            mock_broadcast.assert_not_called()

    def test_save_default_notify_is_false(self, app_client):
        """POST /memory/save without notify field should default to no broadcast."""
        with patch("synapse.a2a_compat._memory_broadcast_notify_api") as mock_broadcast:
            response = app_client.post(
                "/memory/save",
                json={
                    "key": "default-info",
                    "content": "Uses default",
                    "author": "claude",
                },
            )
            assert response.status_code == 200
            mock_broadcast.assert_not_called()


# --------------------------------------------------------
# #287: Consistent 503 handling across /memory/* endpoints
# --------------------------------------------------------


@pytest.fixture
def disabled_client(tmp_path):
    """Create a FastAPI test client with shared memory DISABLED."""
    os.environ["SYNAPSE_SHARED_MEMORY_DB_PATH"] = str(tmp_path / "memory.db")
    os.environ["SYNAPSE_SHARED_MEMORY_ENABLED"] = "false"

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

    os.environ.pop("SYNAPSE_SHARED_MEMORY_DB_PATH", None)
    os.environ.pop("SYNAPSE_SHARED_MEMORY_ENABLED", None)


class TestMemoryDisabled503:
    """All /memory/* endpoints should return 503 when disabled (#287)."""

    def test_save_returns_503(self, disabled_client):
        """POST /memory/save should return 503 when disabled."""
        response = disabled_client.post(
            "/memory/save",
            json={"key": "k", "content": "v", "author": "claude"},
        )
        assert response.status_code == 503

    def test_list_returns_503(self, disabled_client):
        """GET /memory/list should return 503 when disabled."""
        response = disabled_client.get("/memory/list")
        assert response.status_code == 503

    def test_search_returns_503(self, disabled_client):
        """GET /memory/search should return 503 when disabled."""
        response = disabled_client.get("/memory/search?q=test")
        assert response.status_code == 503

    def test_get_returns_503(self, disabled_client):
        """GET /memory/{key} should return 503 when disabled."""
        response = disabled_client.get("/memory/some-key")
        assert response.status_code == 503

    def test_delete_returns_503(self, disabled_client):
        """DELETE /memory/{key} should return 503 when disabled."""
        response = disabled_client.delete("/memory/some-key")
        assert response.status_code == 503


# --------------------------------------------------------
# #288: Input validation on /memory/list limit and tags
# --------------------------------------------------------


class TestMemoryListValidation:
    """Tests for limit/tags validation on GET /memory/list (#288)."""

    def test_limit_zero_clamped_to_1(self, app_client):
        """limit=0 should be clamped to 1."""
        app_client.post(
            "/memory/save",
            json={"key": "k1", "content": "v1", "author": "claude"},
        )
        app_client.post(
            "/memory/save",
            json={"key": "k2", "content": "v2", "author": "claude"},
        )
        response = app_client.get("/memory/list?limit=0")
        assert response.status_code == 200
        assert len(response.json()["memories"]) >= 1

    def test_negative_limit_clamped_to_1(self, app_client):
        """limit=-5 should be clamped to 1."""
        app_client.post(
            "/memory/save",
            json={"key": "k1", "content": "v1", "author": "claude"},
        )
        response = app_client.get("/memory/list?limit=-5")
        assert response.status_code == 200
        assert len(response.json()["memories"]) >= 1

    def test_huge_limit_clamped_to_100(self, app_client):
        """limit=999999 should be clamped to 100."""
        app_client.post(
            "/memory/save",
            json={"key": "k1", "content": "v1", "author": "claude"},
        )
        response = app_client.get("/memory/list?limit=999999")
        assert response.status_code == 200

    def test_tags_with_whitespace_trimmed(self, app_client):
        """tags with whitespace should be trimmed."""
        app_client.post(
            "/memory/save",
            json={
                "key": "k1",
                "content": "v1",
                "author": "claude",
                "tags": ["arch"],
            },
        )
        response = app_client.get("/memory/list?tags= arch , ")
        assert response.status_code == 200
        data = response.json()
        assert len(data["memories"]) == 1

    def test_tags_empty_strings_filtered(self, app_client):
        """Trailing commas in tags should not produce empty strings."""
        app_client.post(
            "/memory/save",
            json={
                "key": "k1",
                "content": "v1",
                "author": "claude",
                "tags": ["security"],
            },
        )
        response = app_client.get("/memory/list?tags=security,")
        assert response.status_code == 200
        data = response.json()
        assert len(data["memories"]) == 1
