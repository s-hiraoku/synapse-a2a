"""Tests for /team/start A2A endpoint — agent-initiated team spawning.

Test-first development: these tests define the expected API behavior
for the POST /team/start endpoint that allows agents to spawn teams
of other agents programmatically via the A2A protocol.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

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
# TestTeamStartEndpoint - Core endpoint behavior
# ============================================================


class TestTeamStartEndpoint:
    """Tests for POST /team/start endpoint."""

    def test_team_start_returns_200(self, app_client):
        """POST /team/start with valid agents should return 200."""
        with (
            patch("synapse.a2a_compat.detect_terminal_app", return_value=None),
            patch("subprocess.Popen"),
        ):
            response = app_client.post(
                "/team/start",
                json={"agents": ["claude", "gemini"]},
            )
        assert response.status_code == 200

    def test_team_start_response_format(self, app_client):
        """Response should contain started list and terminal_used."""
        with (
            patch("synapse.a2a_compat.detect_terminal_app", return_value=None),
            patch("subprocess.Popen"),
        ):
            response = app_client.post(
                "/team/start",
                json={"agents": ["claude", "gemini"], "layout": "split"},
            )
        data = response.json()
        assert "started" in data
        assert "terminal_used" in data
        assert len(data["started"]) == 2

    def test_team_start_agents_marked_submitted(self, app_client):
        """Each agent should be marked as 'submitted' on success."""
        with (
            patch("synapse.a2a_compat.detect_terminal_app", return_value=None),
            patch("subprocess.Popen"),
        ):
            response = app_client.post(
                "/team/start",
                json={"agents": ["claude", "gemini", "codex"]},
            )
        data = response.json()
        assert all(s["status"] == "submitted" for s in data["started"])
        assert [s["agent_type"] for s in data["started"]] == [
            "claude",
            "gemini",
            "codex",
        ]

    def test_team_start_empty_agents_returns_error(self, app_client):
        """Empty agents list should return 422 (validation error)."""
        response = app_client.post(
            "/team/start",
            json={"agents": []},
        )
        assert response.status_code == 422

    def test_team_start_default_layout(self, app_client):
        """Default layout should be 'split'."""
        with (
            patch("synapse.a2a_compat.detect_terminal_app", return_value=None),
            patch("subprocess.Popen"),
        ):
            response = app_client.post(
                "/team/start",
                json={"agents": ["claude"]},
            )
        assert response.status_code == 200


# ============================================================
# TestTeamStartTerminalDetection - Terminal auto-detection
# ============================================================


class TestTeamStartTerminalDetection:
    """Tests for terminal detection in /team/start."""

    def test_tmux_detected_uses_pane_commands(self, app_client):
        """When TMUX is set, should use create_panes with tmux."""
        mock_commands = ["tmux split-window 'synapse gemini'"]
        with (
            patch("synapse.a2a_compat.detect_terminal_app", return_value="tmux"),
            patch(
                "synapse.a2a_compat.create_panes",
                return_value=mock_commands,
            ) as mock_create,
            patch("subprocess.run") as mock_run,
        ):
            response = app_client.post(
                "/team/start",
                json={"agents": ["gemini"], "layout": "split"},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["terminal_used"] == "tmux"
        mock_create.assert_called_once_with(["gemini"], "split", "tmux", tool_args=None)
        mock_run.assert_called_once()

    def test_no_terminal_falls_back_to_background(self, app_client):
        """When no terminal detected, should spawn agents in background."""
        with (
            patch("synapse.a2a_compat.detect_terminal_app", return_value=None),
            patch("subprocess.Popen") as mock_popen,
        ):
            response = app_client.post(
                "/team/start",
                json={"agents": ["claude", "gemini"]},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["terminal_used"] is None
        assert mock_popen.call_count == 2

    def test_explicit_terminal_overrides_detection(self, app_client):
        """Explicit terminal param should override auto-detection."""
        mock_commands = ["tmux split-window 'synapse codex'"]
        with (
            patch(
                "synapse.a2a_compat.create_panes",
                return_value=mock_commands,
            ) as mock_create,
            patch("subprocess.run"),
        ):
            response = app_client.post(
                "/team/start",
                json={
                    "agents": ["codex"],
                    "terminal": "tmux",
                },
            )
        assert response.status_code == 200
        # Should not call detect_terminal_app, use explicit terminal
        mock_create.assert_called_once_with(["codex"], "split", "tmux", tool_args=None)

    def test_terminal_with_empty_commands_falls_back(self, app_client):
        """If terminal detected but create_panes returns empty, fall back."""
        with (
            patch("synapse.a2a_compat.detect_terminal_app", return_value="Ghostty"),
            patch(
                "synapse.a2a_compat.create_panes",
                return_value=[],
            ),
            patch("subprocess.Popen") as mock_popen,
        ):
            response = app_client.post(
                "/team/start",
                json={"agents": ["claude"]},
            )
        assert response.status_code == 200
        data = response.json()
        # Falls back to background spawn
        assert data["terminal_used"] is None
        assert mock_popen.call_count == 1


# ============================================================
# TestTeamStartValidation - Input validation
# ============================================================


class TestTeamStartValidation:
    """Tests for request validation in /team/start."""

    def test_invalid_agent_type_marked_failed(self, app_client):
        """Invalid agent type should be marked as 'failed' in response."""
        with (
            patch("synapse.a2a_compat.detect_terminal_app", return_value=None),
            patch(
                "synapse.server.load_profile",
                side_effect=FileNotFoundError("Profile nonexistent not found"),
            ),
        ):
            response = app_client.post(
                "/team/start",
                json={"agents": ["nonexistent"]},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["started"][0]["status"] == "failed"
        assert "unknown agent type" in data["started"][0]["reason"].lower()

    def test_mixed_valid_and_invalid_agents(self, app_client):
        """Mix of valid/invalid agents should report per-agent status."""

        def mock_load(name):
            if name == "invalid_agent":
                raise FileNotFoundError(f"Profile {name} not found")
            return {"name": name}

        with (
            patch("synapse.a2a_compat.detect_terminal_app", return_value=None),
            patch("synapse.server.load_profile", side_effect=mock_load),
            patch("subprocess.Popen"),
        ):
            response = app_client.post(
                "/team/start",
                json={"agents": ["claude", "invalid_agent", "gemini"]},
            )
        data = response.json()
        statuses = {s["agent_type"]: s["status"] for s in data["started"]}
        assert statuses["claude"] == "submitted"
        assert statuses["invalid_agent"] == "failed"
        assert statuses["gemini"] == "submitted"

    def test_invalid_layout_rejected(self, app_client):
        """Invalid layout value should return 422."""
        response = app_client.post(
            "/team/start",
            json={"agents": ["claude"], "layout": "diagonal"},
        )
        assert response.status_code == 422


# ============================================================
# TestTeamStartPaneCreation - Pane creation integration
# ============================================================


class TestTeamStartPaneCreation:
    """Tests for pane creation via /team/start."""

    def test_tmux_commands_executed_in_order(self, app_client):
        """Tmux commands should be executed sequentially via shlex.split."""
        import shlex

        mock_commands = [
            "tmux split-window -h 'synapse gemini'",
            "tmux split-window -v 'synapse codex'",
        ]
        executed = []

        def track_run(cmd, **kwargs):
            executed.append(cmd)
            return MagicMock(returncode=0)

        with (
            patch("synapse.a2a_compat.detect_terminal_app", return_value="tmux"),
            patch(
                "synapse.a2a_compat.create_panes",
                return_value=mock_commands,
            ),
            patch("subprocess.run", side_effect=track_run),
        ):
            response = app_client.post(
                "/team/start",
                json={"agents": ["gemini", "codex"], "layout": "split"},
            )
        assert response.status_code == 200
        # Commands are split via shlex before execution (shell=False)
        expected = [shlex.split(cmd) for cmd in mock_commands]
        assert executed == expected

    def test_all_agents_submitted_via_panes(self, app_client):
        """All agents should appear as submitted when panes are created."""
        with (
            patch("synapse.a2a_compat.detect_terminal_app", return_value="tmux"),
            patch(
                "synapse.a2a_compat.create_panes",
                return_value=["tmux cmd1", "tmux cmd2"],
            ),
            patch("subprocess.run"),
        ):
            response = app_client.post(
                "/team/start",
                json={"agents": ["claude", "gemini", "codex"]},
            )
        data = response.json()
        assert len(data["started"]) == 3
        assert all(s["status"] == "submitted" for s in data["started"])
        assert data["terminal_used"] == "tmux"

    def test_background_spawn_uses_popen(self, app_client):
        """Background fallback should use Popen with start_new_session."""
        with (
            patch("synapse.a2a_compat.detect_terminal_app", return_value=None),
            patch("subprocess.Popen") as mock_popen,
        ):
            response = app_client.post(
                "/team/start",
                json={"agents": ["claude"]},
            )
        assert response.status_code == 200
        mock_popen.assert_called_once()
        call_kwargs = mock_popen.call_args
        assert call_kwargs[1].get("start_new_session") is True
