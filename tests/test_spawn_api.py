"""Tests for POST /spawn A2A endpoint — agent-initiated single-agent spawning.

Test-first development: these tests define the expected API behavior
for the POST /spawn endpoint that allows agents to spawn a single
other agent programmatically via the A2A protocol.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app_client():
    """Create a FastAPI test client with the A2A router."""
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
    return TestClient(app)


# ============================================================
# TestSpawnEndpoint - Core endpoint behavior
# ============================================================


class TestSpawnEndpoint:
    """Tests for POST /spawn endpoint."""

    def test_spawn_returns_200(self, app_client) -> None:
        """POST /spawn with valid profile should return 200."""
        from synapse.spawn import SpawnResult

        mock_result = SpawnResult(
            agent_id="synapse-gemini-8110",
            port=8110,
            terminal_used="tmux",
            status="submitted",
        )

        with patch("synapse.spawn.spawn_agent", return_value=mock_result):
            response = app_client.post(
                "/spawn",
                json={"profile": "gemini"},
            )
        assert response.status_code == 200

    def test_spawn_response_format(self, app_client) -> None:
        """Response should contain agent_id, port, terminal_used, status."""
        from synapse.spawn import SpawnResult

        mock_result = SpawnResult(
            agent_id="synapse-gemini-8110",
            port=8110,
            terminal_used="tmux",
            status="submitted",
        )

        with patch("synapse.spawn.spawn_agent", return_value=mock_result):
            response = app_client.post(
                "/spawn",
                json={"profile": "gemini"},
            )
        data = response.json()
        assert data["agent_id"] == "synapse-gemini-8110"
        assert data["port"] == 8110
        assert data["terminal_used"] == "tmux"
        assert data["status"] == "submitted"

    def test_spawn_with_explicit_port(self, app_client) -> None:
        """Explicit port should be passed to spawn_agent."""
        from synapse.spawn import SpawnResult

        mock_result = SpawnResult(
            agent_id="synapse-gemini-8115",
            port=8115,
            terminal_used="tmux",
            status="submitted",
        )

        with patch("synapse.spawn.spawn_agent", return_value=mock_result) as mock_fn:
            response = app_client.post(
                "/spawn",
                json={"profile": "gemini", "port": 8115},
            )
        assert response.status_code == 200
        mock_fn.assert_called_once_with(
            profile="gemini",
            port=8115,
            name=None,
            role=None,
            skill_set=None,
            terminal=None,
        )

    def test_spawn_failure_returns_status_failed(self, app_client) -> None:
        """When spawn_agent raises, response should have status=failed."""
        with patch(
            "synapse.spawn.spawn_agent",
            side_effect=RuntimeError("No available ports"),
        ):
            response = app_client.post(
                "/spawn",
                json={"profile": "claude"},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "failed"
        assert "No available ports" in data["reason"]

    def test_spawn_name_and_role_passed(self, app_client) -> None:
        """name and role should be passed through to spawn_agent."""
        from synapse.spawn import SpawnResult

        mock_result = SpawnResult(
            agent_id="synapse-claude-8100",
            port=8100,
            terminal_used="tmux",
            status="submitted",
        )

        with patch("synapse.spawn.spawn_agent", return_value=mock_result) as mock_fn:
            response = app_client.post(
                "/spawn",
                json={
                    "profile": "claude",
                    "name": "Helper",
                    "role": "assistant",
                },
            )
        assert response.status_code == 200
        mock_fn.assert_called_once_with(
            profile="claude",
            port=None,
            name="Helper",
            role="assistant",
            skill_set=None,
            terminal=None,
        )

    def test_spawn_missing_profile_returns_422(self, app_client) -> None:
        """Missing profile field should return 422 (validation error)."""
        response = app_client.post(
            "/spawn",
            json={},
        )
        assert response.status_code == 422
