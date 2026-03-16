"""Tests for Canvas Admin API endpoints.

Test-first development: these tests define the expected behavior
for the Admin Command Center feature (Issue #393).
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
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


# ============================================================
# GET /api/admin/agents
# ============================================================


class TestAdminAgents:
    """Tests for GET /api/admin/agents."""

    def test_returns_agent_list(self, client, tmp_path, monkeypatch):
        """Should return list of live agents from registry."""
        registry_dir = tmp_path / "registry"
        registry_dir.mkdir()
        agent_file = registry_dir / "synapse-claude-8100.json"
        agent_file.write_text(
            json.dumps(
                {
                    "agent_id": "synapse-claude-8100",
                    "agent_type": "claude",
                    "name": "TestAgent",
                    "port": 8100,
                    "status": "READY",
                    "pid": 12345,
                    "endpoint": "http://localhost:8100",
                    "working_dir": "/tmp/test",
                }
            )
        )
        monkeypatch.setattr(
            "os.path.expanduser",
            lambda p: str(tmp_path) if "~/.a2a/registry" in p else p,
        )
        # Patch the registry dir used in system_panel as well
        monkeypatch.setenv("HOME", str(tmp_path.parent))

        with patch(
            "synapse.canvas.server._get_registry_dir", return_value=str(registry_dir)
        ):
            resp = client.get("/api/admin/agents")

        assert resp.status_code == 200
        data = resp.json()
        assert "agents" in data
        assert isinstance(data["agents"], list)

    def test_returns_empty_when_no_agents(self, client, tmp_path, monkeypatch):
        """Should return empty list when no agents are registered."""
        registry_dir = tmp_path / "empty_registry"
        registry_dir.mkdir()

        with patch(
            "synapse.canvas.server._get_registry_dir", return_value=str(registry_dir)
        ):
            resp = client.get("/api/admin/agents")

        assert resp.status_code == 200
        data = resp.json()
        assert data["agents"] == []


# ============================================================
# POST /api/admin/send
# ============================================================


class TestAdminSend:
    """Tests for POST /api/admin/send."""

    def test_send_message_success(self, client):
        """Should forward message to target agent and return task_id."""
        mock_response = httpx.Response(
            200,
            json={
                "id": "task-123",
                "status": {"state": "working"},
                "contextId": "ctx-1",
            },
            request=httpx.Request("POST", "http://localhost:8100/tasks/send"),
        )

        with (
            patch(
                "synapse.canvas.server._resolve_agent_endpoint",
                return_value="http://localhost:8100",
            ),
            patch(
                "httpx.AsyncClient.post",
                new_callable=AsyncMock,
                return_value=mock_response,
            ),
        ):
            resp = client.post(
                "/api/admin/send",
                json={"target": "synapse-claude-8100", "message": "Hello agent"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert "task_id" in data
        # task_id is a pre-generated UUID (sender_task_id), not the agent's task ID
        assert len(data["task_id"]) == 36  # UUID format

    def test_send_message_agent_not_found(self, client):
        """Should return 404 when target agent is not found."""
        with patch("synapse.canvas.server._resolve_agent_endpoint", return_value=None):
            resp = client.post(
                "/api/admin/send",
                json={"target": "nonexistent-agent", "message": "Hello"},
            )

        assert resp.status_code == 404
        data = resp.json()
        assert "not found" in data["detail"].lower() or "detail" in data

    def test_send_message_missing_fields(self, client):
        """Should return 422 when required fields are missing."""
        resp = client.post("/api/admin/send", json={"target": ""})
        assert resp.status_code == 400

        resp = client.post("/api/admin/send", json={"message": "hello"})
        assert resp.status_code == 400


# ============================================================
# GET /api/admin/tasks/{task_id}
# ============================================================


class TestAdminTaskProxy:
    """Tests for GET /api/admin/tasks/{task_id}."""

    def test_proxy_task_completed(self, client):
        """Should return task data when proxied to agent endpoint."""
        mock_response = httpx.Response(
            200,
            json={
                "id": "task-123",
                "status": {"state": "completed"},
                "artifacts": [
                    {
                        "parts": [{"type": "text", "text": "Done!"}],
                    }
                ],
            },
            request=httpx.Request("GET", "http://localhost:8100/tasks/task-123"),
        )

        with (
            patch(
                "synapse.canvas.server._resolve_agent_endpoint",
                return_value="http://localhost:8100",
            ),
            patch(
                "httpx.AsyncClient.get",
                new_callable=AsyncMock,
                return_value=mock_response,
            ),
        ):
            resp = client.get(
                "/api/admin/tasks/task-123",
                params={"target": "synapse-claude-8100"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert data["output"] == "Done!"

    def test_proxy_task_working(self, client):
        """Should return working status."""
        mock_response = httpx.Response(
            200,
            json={
                "id": "task-123",
                "status": {"state": "working"},
            },
            request=httpx.Request("GET", "http://localhost:8100/tasks/task-123"),
        )

        with (
            patch(
                "synapse.canvas.server._resolve_agent_endpoint",
                return_value="http://localhost:8100",
            ),
            patch(
                "httpx.AsyncClient.get",
                new_callable=AsyncMock,
                return_value=mock_response,
            ),
        ):
            resp = client.get(
                "/api/admin/tasks/task-123",
                params={"target": "synapse-claude-8100"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "working"

    def test_proxy_task_target_missing(self, client):
        """Should return 400 when target query param is missing."""
        resp = client.get("/api/admin/tasks/task-123")
        assert resp.status_code == 400

    def test_proxy_task_multiple_artifacts_concatenated(self, client):
        """Should concatenate text from multiple artifacts."""
        mock_response = httpx.Response(
            200,
            json={
                "id": "task-multi",
                "status": {"state": "completed"},
                "artifacts": [
                    {"parts": [{"type": "text", "text": "Line 1"}]},
                    {"parts": [{"type": "text", "text": "Line 2"}]},
                    {"data": {"content": "Line 3"}},
                ],
            },
            request=httpx.Request("GET", "http://localhost:8100/tasks/task-multi"),
        )

        with (
            patch(
                "synapse.canvas.server._resolve_agent_endpoint",
                return_value="http://localhost:8100",
            ),
            patch(
                "httpx.AsyncClient.get",
                new_callable=AsyncMock,
                return_value=mock_response,
            ),
        ):
            resp = client.get(
                "/api/admin/tasks/task-multi",
                params={"target": "synapse-claude-8100"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert "Line 1" in data["output"]
        assert "Line 2" in data["output"]
        assert "Line 3" in data["output"]

    def test_proxy_task_format2_data_string(self, client):
        """Should extract output from artifact data as plain string."""
        mock_response = httpx.Response(
            200,
            json={
                "id": "task-str",
                "status": {"state": "completed"},
                "artifacts": [
                    {"data": "Plain string output"},
                ],
            },
            request=httpx.Request("GET", "http://localhost:8100/tasks/task-str"),
        )

        with (
            patch(
                "synapse.canvas.server._resolve_agent_endpoint",
                return_value="http://localhost:8100",
            ),
            patch(
                "httpx.AsyncClient.get",
                new_callable=AsyncMock,
                return_value=mock_response,
            ),
        ):
            resp = client.get(
                "/api/admin/tasks/task-str",
                params={"target": "synapse-claude-8100"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["output"] == "Plain string output"


class TestAdminReplies:
    """Tests for reply ingestion and retrieval."""

    def test_reply_receive_endpoint_exists(self, client):
        """POST /tasks/send should accept reply payloads for the admin inbox."""
        resp = client.post(
            "/tasks/send",
            json={
                "message": {
                    "role": "agent",
                    "parts": [{"type": "text", "text": "Reply text"}],
                },
                "metadata": {"sender_task_id": "task-123"},
            },
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["task"]["status"] == "completed"

    def test_replies_can_be_polled_by_task_id(self, client):
        """Replies for a task should be retrievable via admin polling endpoint."""
        client.post(
            "/tasks/send",
            json={
                "message": {
                    "role": "agent",
                    "parts": [{"type": "text", "text": "Structured reply"}],
                },
                "metadata": {"sender_task_id": "task-xyz"},
            },
        )

        resp = client.get("/api/admin/replies/task-xyz")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert data["output"] == "Structured reply"

    def test_admin_send_includes_sender_endpoint(self, client):
        """Forwarded admin messages should include sender_endpoint metadata."""
        mock_response = httpx.Response(
            200,
            json={
                "id": "task-123",
                "status": {"state": "working"},
                "contextId": "ctx-1",
            },
            request=httpx.Request("POST", "http://localhost:8100/tasks/send"),
        )

        async def mock_post(self, url, json=None, **kwargs):  # noqa: ARG001
            assert json is not None
            sender = json["metadata"]["sender"]
            assert sender["sender_id"] == "canvas-admin"
            assert sender["sender_name"] == "Admin"
            assert sender["sender_endpoint"] == "http://localhost:3000"
            return mock_response

        with (
            patch(
                "synapse.canvas.server._resolve_agent_endpoint",
                return_value="http://localhost:8100",
            ),
            patch("httpx.AsyncClient.post", new=mock_post),
        ):
            resp = client.post(
                "/api/admin/send",
                json={"target": "synapse-claude-8100", "message": "Hello agent"},
            )

        assert resp.status_code == 200


# ============================================================
# _strip_terminal_junk tests
# ============================================================


class TestStripTerminalJunk:
    """Tests for the _strip_terminal_junk helper."""

    def test_preserves_multiline_text_with_trailing_numbers(self):
        """Should not strip trailing numbers from normal multi-line text."""
        from synapse.canvas.server import _strip_terminal_junk

        text = "Step 1\nStep 2\nStep 3"
        assert _strip_terminal_junk(text) == "Step 1\nStep 2\nStep 3"

    def test_strips_bel_and_csi_remnants(self):
        """Should strip content after BEL and trailing CSI digits."""
        from synapse.canvas.server import _strip_terminal_junk

        text = "Hello7\x07status bar junk"
        result = _strip_terminal_junk(text)
        assert result == "Hello"
        assert "\x07" not in result

    def test_strips_ansi_sequences(self):
        """Should remove ANSI escape sequences."""
        from synapse.canvas.server import _strip_terminal_junk

        text = "\x1b[32mGreen\x1b[0m text"
        result = _strip_terminal_junk(text)
        assert result == "Green text"

    def test_preserves_japanese_text(self):
        """Should preserve multi-byte characters like Japanese."""
        from synapse.canvas.server import _strip_terminal_junk

        text = "完了しました"
        assert _strip_terminal_junk(text) == "完了しました"


# ============================================================
# POST /api/admin/start — Administrator start
# ============================================================


class TestAdminStart:
    """Tests for POST /api/admin/start."""

    def test_start_administrator(self, client):
        """Should start administrator agent from config."""
        mock_popen = MagicMock()
        mock_popen.pid = 99999
        mock_popen.poll.return_value = None

        with patch(
            "synapse.canvas.server._start_administrator",
            return_value={"status": "started", "pid": 99999},
        ):
            resp = client.post("/api/admin/start")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "started"

    def test_stop_administrator(self, client):
        """Should stop administrator agent."""
        with patch(
            "synapse.canvas.server._stop_administrator",
            return_value={"status": "stopped"},
        ):
            resp = client.post("/api/admin/stop")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "stopped"


# ============================================================
# POST /api/admin/agents/spawn — Agent lifecycle
# ============================================================


class TestAdminAgentLifecycle:
    """Tests for agent spawn/stop endpoints."""

    def test_spawn_agent(self, client):
        """Should spawn a new agent from profile."""
        with patch(
            "synapse.canvas.server._spawn_agent",
            return_value={
                "status": "started",
                "agent_id": "synapse-claude-8100",
                "pid": 11111,
            },
        ):
            resp = client.post(
                "/api/admin/agents/spawn",
                json={"profile": "claude"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "started"
        assert "agent_id" in data

    def test_stop_agent(self, client):
        """Should stop an agent by ID."""
        with patch(
            "synapse.canvas.server._stop_agent",
            return_value={"status": "stopped", "agent_id": "synapse-claude-8100"},
        ):
            resp = client.delete("/api/admin/agents/synapse-claude-8100")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "stopped"

    def test_spawn_agent_missing_profile(self, client):
        """Should return 400 when profile is missing."""
        resp = client.post("/api/admin/agents/spawn", json={})
        assert resp.status_code == 400


# ============================================================
# Settings — Administrator config
# ============================================================


class TestAdministratorConfig:
    """Tests for administrator configuration."""

    def test_get_administrator_config_defaults(self):
        """Should return default administrator config."""
        from synapse.settings import SynapseSettings

        settings = SynapseSettings.from_defaults()
        config = settings.get_administrator_config()
        assert config["profile"] == "claude"
        assert config["port"] == 8150
        assert config["auto_start"] is False

    def test_get_administrator_config_from_file(self, tmp_path):
        """Should load administrator config from settings file."""
        settings_file = tmp_path / "settings.json"
        settings_file.write_text(
            json.dumps(
                {
                    "administrator": {
                        "profile": "gemini",
                        "name": "MyAdmin",
                        "port": 8151,
                        "auto_start": True,
                    }
                }
            )
        )
        from synapse.settings import SynapseSettings

        settings = SynapseSettings.load(
            user_path=tmp_path / "nonexistent.json",
            project_path=settings_file,
            local_path=tmp_path / "nonexistent2.json",
        )
        config = settings.get_administrator_config()
        assert config["profile"] == "gemini"
        assert config["name"] == "MyAdmin"
        assert config["port"] == 8151
        assert config["auto_start"] is True


# ============================================================
# Port Manager — Admin port range
# ============================================================


class TestAdminJump:
    """Tests for POST /api/admin/jump/{agent_id}."""

    def test_jump_success(self, client):
        """Should call jump_to_terminal and return ok=True."""
        agent_data = {
            "agent_id": "synapse-claude-8100",
            "agent_type": "claude",
            "tty_device": "/dev/ttys001",
        }
        mock_registry = MagicMock()
        mock_registry.get_agent.return_value = agent_data

        with (
            patch(
                "synapse.registry.AgentRegistry",
                return_value=mock_registry,
            ),
            patch(
                "synapse.terminal_jump.jump_to_terminal", return_value=True
            ) as mock_jump,
        ):
            resp = client.post("/api/admin/jump/synapse-claude-8100")

        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        mock_jump.assert_called_once()
        assert mock_jump.call_args[0][0]["agent_id"] == "synapse-claude-8100"

    def test_jump_agent_not_found(self, client):
        """Should return ok=False when agent doesn't exist."""
        mock_registry = MagicMock()
        mock_registry.get_agent.return_value = None

        with patch(
            "synapse.registry.AgentRegistry",
            return_value=mock_registry,
        ):
            resp = client.post("/api/admin/jump/nonexistent")

        assert resp.status_code == 200
        assert resp.json()["ok"] is False

    def test_jump_failure(self, client):
        """Should return ok=False when jump_to_terminal fails."""
        agent_data = {"agent_id": "synapse-claude-8100"}
        mock_registry = MagicMock()
        mock_registry.get_agent.return_value = agent_data

        with (
            patch(
                "synapse.registry.AgentRegistry",
                return_value=mock_registry,
            ),
            patch("synapse.terminal_jump.jump_to_terminal", return_value=False),
        ):
            resp = client.post("/api/admin/jump/synapse-claude-8100")

        assert resp.status_code == 200
        assert resp.json()["ok"] is False


class TestAdminPortRange:
    """Tests for admin port range in PortManager."""

    def test_admin_port_range_defined(self):
        """Admin port range should be 8150-8159."""
        from synapse.port_manager import PORT_RANGES

        assert "admin" in PORT_RANGES
        assert PORT_RANGES["admin"] == (8150, 8159)
