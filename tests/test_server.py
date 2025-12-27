"""Tests for Synapse A2A Server - endpoint compliance."""
import pytest
from unittest.mock import MagicMock, patch
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
            agent_type="test-agent"
        )

    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return TestClient(app)


# ============================================================
# Legacy /message Endpoint Tests
# ============================================================

class TestLegacyMessageEndpoint(TestServerApp):
    """Test deprecated /message endpoint."""

    def test_message_endpoint_exists(self, client):
        """POST /message should be available."""
        response = client.post("/message", json={"priority": 1, "content": "test"})
        assert response.status_code == 200

    def test_message_creates_task(self, client):
        """POST /message should create A2A task internally."""
        response = client.post("/message", json={"priority": 1, "content": "test"})

        data = response.json()
        assert "task_id" in data
        assert data["status"] == "sent"
        assert data["priority"] == 1

    def test_message_with_priority_5_interrupts(self, client, mock_controller):
        """POST /message with priority 5 should interrupt first."""
        response = client.post("/message", json={"priority": 5, "content": "urgent"})

        assert response.status_code == 200
        mock_controller.interrupt.assert_called_once()
        mock_controller.write.assert_called_once()

    def test_message_writes_to_controller(self, client, mock_controller):
        """POST /message should write content to controller."""
        response = client.post("/message", json={"priority": 1, "content": "hello world"})

        assert response.status_code == 200
        mock_controller.write.assert_called_once_with("hello world", submit_seq="\n")

    def test_message_endpoint_is_deprecated(self, app):
        """POST /message should be marked as deprecated."""
        # Check OpenAPI schema for deprecated flag
        openapi = app.openapi()
        message_path = openapi["paths"]["/message"]["post"]
        assert message_path.get("deprecated") is True


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
                "parts": [{"type": "text", "text": "Hello A2A"}]
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
                "parts": [{"type": "text", "text": "Priority message"}]
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
# Backward Compatibility Tests
# ============================================================

class TestBackwardCompatibility(TestServerApp):
    """Test backward compatibility with legacy clients."""

    def test_legacy_response_format(self, client):
        """Legacy /message response should include old fields."""
        response = client.post("/message", json={"priority": 1, "content": "test"})

        data = response.json()
        # Old format fields
        assert "status" in data
        assert data["status"] == "sent"
        assert "priority" in data
        # New field (task_id) added for tracking
        assert "task_id" in data

    def test_legacy_clients_still_work(self, client):
        """Legacy clients using /message should continue to work."""
        # Simulate old client behavior
        payload = {"priority": 1, "content": "legacy message"}

        response = client.post("/message", json=payload)

        assert response.status_code == 200
        assert response.json()["status"] == "sent"

    def test_both_apis_work_simultaneously(self, client, mock_controller):
        """Both /message and /tasks/send should work."""
        # Legacy API
        legacy_response = client.post("/message", json={"priority": 1, "content": "legacy"})
        assert legacy_response.status_code == 200

        # New A2A API
        a2a_response = client.post("/tasks/send", json={
            "message": {"role": "user", "parts": [{"type": "text", "text": "a2a"}]}
        })
        assert a2a_response.status_code == 200

        # Both should have written to controller
        assert mock_controller.write.call_count == 2


# ============================================================
# Error Handling Tests
# ============================================================

class TestErrorHandling(TestServerApp):
    """Test error handling."""

    def test_message_without_controller(self, mock_registry):
        """Should return 503 when controller not available."""
        from synapse.server import create_app
        app = create_app(
            ctrl=None,  # No controller
            reg=mock_registry,
            agent_id="test",
            port=8000
        )
        client = TestClient(app)

        response = client.post("/message", json={"priority": 1, "content": "test"})
        assert response.status_code == 503

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
        create_response = client.post("/tasks/send", json={
            "message": {"role": "user", "parts": [{"type": "text", "text": "test command"}]}
        })
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

    def test_legacy_to_a2a_migration_path(self, client, mock_controller):
        """Test migration path from legacy to A2A API."""
        # Old way: /message - now returns task_id for tracking
        legacy_response = client.post("/message", json={"priority": 1, "content": "old style"})
        assert legacy_response.status_code == 200
        assert "task_id" in legacy_response.json()

        # New way: /tasks/send - full A2A workflow
        a2a_response = client.post("/tasks/send", json={
            "message": {"role": "user", "parts": [{"type": "text", "text": "new style"}]}
        })
        assert a2a_response.status_code == 200
        task_id = a2a_response.json()["task"]["id"]

        # Can track A2A tasks via /tasks/{id}
        task_response = client.get(f"/tasks/{task_id}")
        assert task_response.status_code == 200
        assert task_response.json()["id"] == task_id
