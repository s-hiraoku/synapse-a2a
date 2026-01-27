"""Tests for Synapse A2A Server - endpoint compliance."""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

# ============================================================
# Server App Tests
# ============================================================


class TestServerApp:
    """Test server application factory."""

    @pytest.fixture
    def mock_controller(self):
        """Create mock TerminalController."""
        controller = MagicMock()
        controller.status = "IDLE"
        controller.get_context.return_value = "Sample context output"
        return controller

    @pytest.fixture
    def mock_registry(self):
        """Create mock AgentRegistry."""
        registry = MagicMock()
        return registry

    @pytest.fixture
    def app(self, mock_controller, mock_registry):
        """Create test application."""
        from synapse.server import create_app

        return create_app(
            ctrl=mock_controller,
            reg=mock_registry,
            agent_id="test-agent-id",
            port=8000,
            submit_seq="\n",
            agent_type="test-agent",
        )

    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return TestClient(app)


# ============================================================
# A2A Endpoint Tests
# ============================================================


class TestA2AEndpoints(TestServerApp):
    """Test Google A2A compatible endpoints."""

    def test_agent_card_available(self, client):
        """GET /.well-known/agent.json should return Agent Card."""
        response = client.get("/.well-known/agent.json")

        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "capabilities" in data

    def test_tasks_send_endpoint(self, client, mock_controller):
        """POST /tasks/send should create task."""
        payload = {
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": "Hello A2A"}],
            }
        }

        response = client.post("/tasks/send", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert "task" in data
        assert data["task"]["status"] in ["submitted", "working"]

    def test_tasks_send_priority_endpoint(self, client, mock_controller):
        """POST /tasks/send-priority should handle priority."""
        payload = {
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": "Priority message"}],
            }
        }

        response = client.post("/tasks/send-priority?priority=5", json=payload)

        assert response.status_code == 200
        mock_controller.interrupt.assert_called()

    def test_status_endpoint(self, client, mock_controller):
        """GET /status should return agent status."""
        response = client.get("/status")

        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "context" in data


# ============================================================
# Error Handling Tests
# ============================================================


class TestErrorHandling(TestServerApp):
    """Test error handling."""

    def test_tasks_send_invalid_message(self, client):
        """Should reject invalid message format."""
        # Empty parts
        payload = {"message": {"role": "user", "parts": []}}
        response = client.post("/tasks/send", json=payload)
        assert response.status_code == 400

    def test_get_nonexistent_task(self, client):
        """Should return 404 for nonexistent task."""
        response = client.get("/tasks/nonexistent-id")
        assert response.status_code == 404


# ============================================================
# Integration Tests
# ============================================================


class TestIntegration(TestServerApp):
    """Integration tests for full workflow."""

    def test_full_a2a_workflow(self, client, mock_controller):
        """Test complete A2A workflow: create -> poll -> complete."""
        # 1. Create task via A2A
        create_response = client.post(
            "/tasks/send",
            json={
                "message": {
                    "role": "user",
                    "parts": [{"type": "text", "text": "test command"}],
                }
            },
        )
        assert create_response.status_code == 200
        task_id = create_response.json()["task"]["id"]

        # 2. Poll for status (still working)
        mock_controller.status = "BUSY"
        poll_response = client.get(f"/tasks/{task_id}")
        assert poll_response.json()["status"] == "working"

        # 3. Complete (controller becomes IDLE)
        mock_controller.status = "IDLE"
        mock_controller.get_context.return_value = "Command completed successfully"
        complete_response = client.get(f"/tasks/{task_id}")
        assert complete_response.json()["status"] == "completed"
        assert len(complete_response.json()["artifacts"]) > 0
