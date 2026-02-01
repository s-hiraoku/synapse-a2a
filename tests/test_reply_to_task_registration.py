"""Tests for --reply-to task registration fix.

This module tests the fix where sender_task_id is created on the sender's
server (via /tasks/create) instead of in the CLI process's memory.
"""

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from synapse.a2a_compat import (
    create_a2a_router,
)
from synapse.tools.a2a import build_sender_info

# ============================================================
# /tasks/create Endpoint Tests
# ============================================================


class TestCreateTaskEndpoint:
    """Tests for POST /tasks/create endpoint."""

    @pytest.fixture
    def mock_controller(self):
        """Create a mock TerminalController."""
        controller = MagicMock()
        controller.status = "IDLE"
        controller.get_context.return_value = ""
        return controller

    @pytest.fixture
    def app(self, mock_controller):
        """Create test application with A2A router."""
        app = FastAPI()
        router = create_a2a_router(
            mock_controller,
            "claude",
            8100,
            "\n",
            agent_id="synapse-claude-8100",
        )
        app.include_router(router)
        return app

    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return TestClient(app)

    def test_create_task_returns_task_id(self, client):
        """POST /tasks/create should return a task with an ID."""
        payload = {
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": "Test message"}],
            }
        }

        response = client.post("/tasks/create", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert "task" in data
        assert "id" in data["task"]
        assert len(data["task"]["id"]) == 36  # UUID format

    def test_create_task_has_working_status(self, client):
        """POST /tasks/create should create task in 'working' status."""
        payload = {
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": "Test message"}],
            }
        }

        response = client.post("/tasks/create", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["task"]["status"] == "working"

    def test_create_task_does_not_call_controller(self, client, mock_controller):
        """POST /tasks/create should NOT send to PTY."""
        payload = {
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": "Test message"}],
            }
        }

        response = client.post("/tasks/create", json=payload)

        assert response.status_code == 200
        mock_controller.write.assert_not_called()

    def test_create_task_with_metadata(self, client):
        """POST /tasks/create should accept metadata."""
        payload = {
            "message": {"role": "user", "parts": [{"type": "text", "text": "Test"}]},
            "metadata": {
                "response_expected": True,
                "direction": "outgoing",
                "target_endpoint": "http://localhost:8120",
            },
        }

        response = client.post("/tasks/create", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["task"]["metadata"]["response_expected"] is True
        assert data["task"]["metadata"]["direction"] == "outgoing"

    def test_created_task_can_receive_reply_to(self, client, mock_controller):
        """Task created via /tasks/create can receive --reply-to."""
        # 1. Create task via /tasks/create
        create_payload = {
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": "Question?"}],
            },
            "metadata": {"response_expected": True},
        }
        create_response = client.post("/tasks/create", json=create_payload)
        task_id = create_response.json()["task"]["id"]

        # 2. Send reply with in_reply_to
        reply_payload = {
            "message": {
                "role": "agent",
                "parts": [{"type": "text", "text": "Answer!"}],
            },
            "metadata": {"in_reply_to": task_id},
        }
        reply_response = client.post("/tasks/send", json=reply_payload)

        # 3. Verify reply completed the task
        assert reply_response.status_code == 200
        data = reply_response.json()
        assert data["task"]["id"] == task_id
        assert data["task"]["status"] == "completed"
        assert data["task"]["artifacts"][0]["data"]["content"] == "Answer!"

        # 4. Controller.write should NOT be called (reply doesn't go to PTY)
        mock_controller.write.assert_not_called()


# ============================================================
# build_sender_info Tests
# ============================================================


class TestBuildSenderInfoWithEndpointInfo:
    """Tests for build_sender_info including sender_endpoint and sender_uds_path."""

    def test_explicit_sender_looks_up_endpoint_from_registry(self, monkeypatch):
        """Explicit sender should look up endpoint from registry."""
        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = {
            "synapse-claude-8100": {
                "agent_id": "synapse-claude-8100",
                "agent_type": "claude",
                "endpoint": "http://localhost:8100",
                "uds_path": "/tmp/synapse-claude-8100.sock",
            }
        }
        monkeypatch.setattr("synapse.tools.a2a.AgentRegistry", lambda: mock_registry)

        result = build_sender_info("synapse-claude-8100")

        assert result["sender_id"] == "synapse-claude-8100"
        assert result["sender_type"] == "claude"
        assert result["sender_endpoint"] == "http://localhost:8100"
        assert result["sender_uds_path"] == "/tmp/synapse-claude-8100.sock"

    def test_explicit_sender_agent_type_returns_error(self, monkeypatch):
        """Explicit sender with agent type should return error with hint."""
        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = {
            "synapse-claude-8100": {
                "agent_id": "synapse-claude-8100",
                "agent_type": "claude",
                "endpoint": "http://localhost:8100",
                "uds_path": "/tmp/synapse-claude-8100.sock",
            }
        }
        monkeypatch.setattr("synapse.tools.a2a.AgentRegistry", lambda: mock_registry)

        result = build_sender_info("claude")

        # Should return error string with hint to use proper ID
        assert isinstance(result, str)
        assert "Error" in result
        assert "synapse-claude-8100" in result

    def test_explicit_sender_invalid_format_returns_error(self, monkeypatch):
        """Explicit sender with invalid format returns error."""
        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = {}
        monkeypatch.setattr("synapse.tools.a2a.AgentRegistry", lambda: mock_registry)

        result = build_sender_info("external-agent")

        # Should return error string since format is invalid
        assert isinstance(result, str)
        assert "Error" in result

    def test_pid_matching_includes_endpoint_and_uds_path(self, monkeypatch):
        """PID matching should include endpoint and uds_path."""
        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = {
            "synapse-gemini-8110": {
                "agent_id": "synapse-gemini-8110",
                "agent_type": "gemini",
                "pid": 12345,
                "endpoint": "http://localhost:8110",
                "uds_path": "/tmp/synapse-gemini-8110.sock",
            }
        }
        monkeypatch.setattr("synapse.tools.a2a.AgentRegistry", lambda: mock_registry)
        monkeypatch.setattr(
            "synapse.tools.a2a.is_descendant_of", lambda child, parent: True
        )
        monkeypatch.setattr("os.getpid", lambda: 12346)

        result = build_sender_info(None)

        assert result["sender_id"] == "synapse-gemini-8110"
        assert result["sender_type"] == "gemini"
        assert result["sender_endpoint"] == "http://localhost:8110"
        assert result["sender_uds_path"] == "/tmp/synapse-gemini-8110.sock"


# ============================================================
# send_to_local Task Creation Flow Tests
# ============================================================


class TestSendToLocalTaskCreation:
    """Tests for send_to_local creating task on sender's server."""

    def test_response_expected_creates_task_on_sender_server_via_uds(self, monkeypatch):
        """When response_expected, should create task on sender's server via UDS."""
        from synapse.a2a_client import A2AClient

        # Track calls
        uds_calls = []

        # Mock httpx for UDS
        class MockHttpxClient:
            def __init__(self, **kwargs):
                self.transport = kwargs.get("transport")

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def post(self, url, json=None):
                if "/tasks/create" in url:
                    uds_calls.append({"url": url, "json": json})
                    mock_resp = MagicMock()
                    mock_resp.json.return_value = {
                        "task": {"id": "sender-task-123", "status": "working"}
                    }
                    mock_resp.raise_for_status = MagicMock()
                    return mock_resp
                elif "/tasks/send-priority" in url:
                    mock_resp = MagicMock()
                    mock_resp.json.return_value = {
                        "task": {"id": "receiver-task-456", "status": "working"}
                    }
                    mock_resp.raise_for_status = MagicMock()
                    return mock_resp
                raise ValueError(f"Unexpected URL: {url}")

        # Mock Path.exists for UDS path check
        from pathlib import Path

        original_exists = Path.exists

        def mock_exists(self):
            if str(self).endswith(".sock"):
                return True
            return original_exists(self)

        monkeypatch.setattr(Path, "exists", mock_exists)
        monkeypatch.setattr("httpx.Client", MockHttpxClient)
        monkeypatch.setattr("httpx.HTTPTransport", lambda uds: MagicMock())

        client = A2AClient()
        client.send_to_local(
            endpoint="http://localhost:8120",
            message="Test message",
            priority=1,
            sender_info={
                "sender_id": "synapse-claude-8100",
                "sender_endpoint": "http://localhost:8100",
                "sender_uds_path": "/tmp/synapse-claude-8100.sock",
            },
            response_expected=True,
            uds_path="/tmp/synapse-codex-8120.sock",
        )

        # Verify task was created on sender's server via UDS
        assert len(uds_calls) == 1
        assert uds_calls[0]["url"] == "http://localhost/tasks/create"
        assert uds_calls[0]["json"]["metadata"]["response_expected"] is True

    def test_response_expected_falls_back_to_http_when_uds_fails(self, monkeypatch):
        """When UDS fails, should fallback to HTTP for /tasks/create."""
        import httpx

        from synapse.a2a_client import A2AClient

        http_create_calls = []

        # Mock httpx to fail for UDS
        class MockHttpxClient:
            def __init__(self, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def post(self, url, json=None):
                if "/tasks/create" in url:
                    raise httpx.HTTPError("UDS connection failed")
                elif "/tasks/send-priority" in url:
                    mock_resp = MagicMock()
                    mock_resp.json.return_value = {
                        "task": {"id": "receiver-task-456", "status": "working"}
                    }
                    mock_resp.raise_for_status = MagicMock()
                    return mock_resp
                raise ValueError(f"Unexpected URL: {url}")

        # Mock requests for HTTP fallback
        def mock_requests_post(url, json=None, timeout=None):
            if "/tasks/create" in url:
                http_create_calls.append({"url": url, "json": json})
                mock_resp = MagicMock()
                mock_resp.json.return_value = {
                    "task": {"id": "sender-task-http-123", "status": "working"}
                }
                mock_resp.raise_for_status = MagicMock()
                return mock_resp
            elif "/tasks/send-priority" in url:
                mock_resp = MagicMock()
                mock_resp.json.return_value = {
                    "task": {"id": "receiver-task-456", "status": "working"}
                }
                mock_resp.raise_for_status = MagicMock()
                return mock_resp
            raise ValueError(f"Unexpected URL: {url}")

        from pathlib import Path

        original_exists = Path.exists

        def mock_exists(self):
            if str(self).endswith(".sock"):
                return True
            return original_exists(self)

        monkeypatch.setattr(Path, "exists", mock_exists)
        monkeypatch.setattr("httpx.Client", MockHttpxClient)
        monkeypatch.setattr("httpx.HTTPTransport", lambda uds: MagicMock())
        monkeypatch.setattr("requests.post", mock_requests_post)

        client = A2AClient()
        client.send_to_local(
            endpoint="http://localhost:8120",
            message="Test message",
            priority=1,
            sender_info={
                "sender_id": "synapse-claude-8100",
                "sender_endpoint": "http://localhost:8100",
                "sender_uds_path": "/tmp/synapse-claude-8100.sock",
            },
            response_expected=True,
            uds_path="/tmp/synapse-codex-8120.sock",
        )

        # Verify HTTP fallback was used
        assert len(http_create_calls) == 1
        assert "http://localhost:8100/tasks/create" in http_create_calls[0]["url"]

    def test_no_sender_endpoint_skips_task_creation(self, monkeypatch):
        """When sender_endpoint is missing, should skip task creation."""

        from synapse.a2a_client import A2AClient

        send_calls = []

        def mock_requests_post(url, json=None, timeout=None):
            send_calls.append({"url": url, "json": json})
            mock_resp = MagicMock()
            mock_resp.json.return_value = {
                "task": {"id": "receiver-task-456", "status": "working"}
            }
            mock_resp.raise_for_status = MagicMock()
            return mock_resp

        monkeypatch.setattr("requests.post", mock_requests_post)

        client = A2AClient()
        client.send_to_local(
            endpoint="http://localhost:8120",
            message="Test message",
            priority=1,
            sender_info={
                "sender_id": "synapse-claude-8100",
                # No sender_endpoint or sender_uds_path
            },
            response_expected=True,
        )

        # Verify only send-priority was called, no /tasks/create
        assert len(send_calls) == 1
        assert "/tasks/send-priority" in send_calls[0]["url"]
        # sender_task_id should NOT be in metadata since task creation was skipped
        assert "sender_task_id" not in send_calls[0]["json"].get("metadata", {})


# ============================================================
# Integration Test: Full Reply-to Flow
# ============================================================


class TestReplyToFlowIntegration:
    """Integration test for the full --reply-to flow."""

    @pytest.fixture
    def claude_app(self):
        """Create Claude agent app."""
        controller = MagicMock()
        controller.status = "IDLE"
        controller.get_context.return_value = ""
        app = FastAPI()
        router = create_a2a_router(
            controller,
            "claude",
            8100,
            "\n",
            agent_id="synapse-claude-8100",
        )
        app.include_router(router)
        return app, controller

    @pytest.fixture
    def codex_app(self):
        """Create Codex agent app."""
        controller = MagicMock()
        controller.status = "IDLE"
        controller.get_context.return_value = ""
        app = FastAPI()
        router = create_a2a_router(
            controller,
            "codex",
            8120,
            "\n",
            agent_id="synapse-codex-8120",
        )
        app.include_router(router)
        return app, controller

    def test_full_reply_to_flow(self, claude_app, codex_app):
        """Test the complete --reply-to flow between two agents."""
        claude_fastapi, claude_controller = claude_app
        codex_fastapi, codex_controller = codex_app

        claude_client = TestClient(claude_fastapi)
        codex_client = TestClient(codex_fastapi)

        # Step 1: Create task on Claude's server (simulating --response flag)
        create_payload = {
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": "Please help me"}],
            },
            "metadata": {
                "response_expected": True,
                "direction": "outgoing",
                "target_endpoint": "http://localhost:8120",
            },
        }
        create_response = claude_client.post("/tasks/create", json=create_payload)
        assert create_response.status_code == 200
        sender_task_id = create_response.json()["task"]["id"]

        # Step 2: Send message to Codex with sender_task_id
        send_payload = {
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": "Please help me"}],
            },
            "metadata": {
                "sender": {
                    "sender_id": "synapse-claude-8100",
                    "sender_endpoint": "http://localhost:8100",
                },
                "response_expected": True,
                "sender_task_id": sender_task_id,
            },
        }
        send_response = codex_client.post(
            "/tasks/send-priority?priority=3", json=send_payload
        )
        assert send_response.status_code == 200
        codex_controller.write.assert_called_once()

        # Verify A2A prefixed message is displayed with [REPLY EXPECTED] marker
        # when response_expected is True
        write_call = codex_controller.write.call_args[0][0]
        assert write_call == "A2A: [REPLY EXPECTED] Please help me"

        # Step 3: Codex replies via --reply-to
        reply_payload = {
            "message": {
                "role": "agent",
                "parts": [{"type": "text", "text": "Here is my help!"}],
            },
            "metadata": {
                "sender": {"sender_id": "synapse-codex-8120"},
                "in_reply_to": sender_task_id,
            },
        }
        reply_response = claude_client.post("/tasks/send", json=reply_payload)

        # Step 4: Verify the reply completed the original task
        assert reply_response.status_code == 200
        data = reply_response.json()
        assert data["task"]["id"] == sender_task_id
        assert data["task"]["status"] == "completed"
        assert data["task"]["artifacts"][0]["data"]["content"] == "Here is my help!"

        # Claude's controller should NOT have write called (reply goes to task, not PTY)
        claude_controller.write.assert_not_called()
