"""Tests for A2A Compatibility Layer - Google A2A protocol compliance."""
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from synapse.a2a_compat import (
    TaskStore,
    Task,
    Message,
    TextPart,
    FilePart,
    DataPart,
    Artifact,
    SendMessageRequest,
    create_a2a_router,
    map_synapse_status_to_a2a
)


# ============================================================
# Message/Part Model Tests
# ============================================================

class TestMessageModels:
    """Test A2A Message and Part models."""

    def test_text_part_structure(self):
        """TextPart should have correct structure."""
        part = TextPart(text="Hello, World!")
        assert part.type == "text"
        assert part.text == "Hello, World!"

    def test_file_part_structure(self):
        """FilePart should have correct structure."""
        part = FilePart(file={"uri": "file:///test.txt", "mimeType": "text/plain"})
        assert part.type == "file"
        assert part.file["uri"] == "file:///test.txt"

    def test_data_part_structure(self):
        """DataPart should have correct structure."""
        part = DataPart(data={"key": "value", "number": 42})
        assert part.type == "data"
        assert part.data["key"] == "value"

    def test_message_with_text_part(self):
        """Message should accept TextPart."""
        msg = Message(
            role="user",
            parts=[TextPart(text="Test message")]
        )
        assert msg.role == "user"
        assert len(msg.parts) == 1
        assert msg.parts[0].text == "Test message"

    def test_message_default_role(self):
        """Message default role should be 'user'."""
        msg = Message(parts=[TextPart(text="test")])
        assert msg.role == "user"

    def test_message_agent_role(self):
        """Message should accept 'agent' role."""
        msg = Message(role="agent", parts=[TextPart(text="response")])
        assert msg.role == "agent"


# ============================================================
# TaskStore Tests
# ============================================================

class TestTaskStore:
    """Test TaskStore for task lifecycle management."""

    @pytest.fixture
    def task_store(self):
        """Create a fresh TaskStore for each test."""
        return TaskStore()

    def test_create_task(self, task_store):
        """Should create task with correct initial state."""
        message = Message(role="user", parts=[TextPart(text="Test")])
        task = task_store.create(message)

        assert task.id is not None
        assert len(task.id) == 36  # UUID format
        assert task.status == "submitted"
        assert task.message == message
        assert task.artifacts == []
        assert task.created_at is not None
        assert task.updated_at is not None

    def test_create_task_with_context_id(self, task_store):
        """Should create task with context_id."""
        message = Message(parts=[TextPart(text="Test")])
        task = task_store.create(message, context_id="conversation-123")

        assert task.context_id == "conversation-123"

    def test_get_task(self, task_store):
        """Should retrieve task by ID."""
        message = Message(parts=[TextPart(text="Test")])
        created = task_store.create(message)

        retrieved = task_store.get(created.id)
        assert retrieved is not None
        assert retrieved.id == created.id

    def test_get_nonexistent_task(self, task_store):
        """Should return None for nonexistent task."""
        result = task_store.get("nonexistent-id")
        assert result is None

    def test_update_status(self, task_store):
        """Should update task status."""
        message = Message(parts=[TextPart(text="Test")])
        task = task_store.create(message)

        updated = task_store.update_status(task.id, "working")
        assert updated is not None
        assert updated.status == "working"
        assert updated.updated_at != task.created_at

    def test_update_status_to_completed(self, task_store):
        """Should update to completed status."""
        message = Message(parts=[TextPart(text="Test")])
        task = task_store.create(message)
        task_store.update_status(task.id, "working")

        updated = task_store.update_status(task.id, "completed")
        assert updated.status == "completed"

    def test_update_status_to_failed(self, task_store):
        """Should update to failed status."""
        message = Message(parts=[TextPart(text="Test")])
        task = task_store.create(message)

        updated = task_store.update_status(task.id, "failed")
        assert updated.status == "failed"

    def test_add_artifact(self, task_store):
        """Should add artifact to task."""
        message = Message(parts=[TextPart(text="Test")])
        task = task_store.create(message)

        artifact = Artifact(type="text", data="Output result")
        updated = task_store.add_artifact(task.id, artifact)

        assert updated is not None
        assert len(updated.artifacts) == 1
        assert updated.artifacts[0].type == "text"
        assert updated.artifacts[0].data == "Output result"

    def test_list_tasks(self, task_store):
        """Should list all tasks."""
        msg = Message(parts=[TextPart(text="Test")])
        task_store.create(msg)
        task_store.create(msg)
        task_store.create(msg)

        tasks = task_store.list_tasks()
        assert len(tasks) == 3

    def test_list_tasks_by_context(self, task_store):
        """Should filter tasks by context_id."""
        msg = Message(parts=[TextPart(text="Test")])
        task_store.create(msg, context_id="ctx-1")
        task_store.create(msg, context_id="ctx-1")
        task_store.create(msg, context_id="ctx-2")

        ctx1_tasks = task_store.list_tasks(context_id="ctx-1")
        assert len(ctx1_tasks) == 2

    def test_create_task_with_metadata(self, task_store):
        """Should create task with metadata (including sender info)."""
        msg = Message(parts=[TextPart(text="Test")])
        metadata = {
            "sender": {
                "sender_id": "synapse-claude-8100",
                "sender_type": "claude",
                "sender_endpoint": "http://localhost:8100"
            }
        }
        task = task_store.create(msg, metadata=metadata)

        assert task.metadata == metadata
        assert task.metadata["sender"]["sender_id"] == "synapse-claude-8100"
        assert task.metadata["sender"]["sender_type"] == "claude"
        assert task.metadata["sender"]["sender_endpoint"] == "http://localhost:8100"

    def test_create_task_metadata_defaults_to_empty(self, task_store):
        """Should default to empty metadata when not provided."""
        msg = Message(parts=[TextPart(text="Test")])
        task = task_store.create(msg)

        assert task.metadata == {}

    def test_create_task_with_partial_sender_info(self, task_store):
        """Should accept partial sender info in metadata."""
        msg = Message(parts=[TextPart(text="Test")])
        metadata = {
            "sender": {
                "sender_id": "external-agent"
            }
        }
        task = task_store.create(msg, metadata=metadata)

        assert task.metadata["sender"]["sender_id"] == "external-agent"
        assert "sender_type" not in task.metadata["sender"]


# ============================================================
# Status Mapping Tests
# ============================================================

class TestStatusMapping:
    """Test Synapse to A2A status mapping."""

    def test_map_starting_to_submitted(self):
        """STARTING should map to submitted."""
        assert map_synapse_status_to_a2a("STARTING") == "submitted"

    def test_map_busy_to_working(self):
        """BUSY should map to working."""
        assert map_synapse_status_to_a2a("BUSY") == "working"

    def test_map_idle_to_completed(self):
        """IDLE should map to completed."""
        assert map_synapse_status_to_a2a("IDLE") == "completed"

    def test_map_not_started_to_submitted(self):
        """NOT_STARTED should map to submitted."""
        assert map_synapse_status_to_a2a("NOT_STARTED") == "submitted"

    def test_map_unknown_to_working(self):
        """Unknown status should default to working."""
        assert map_synapse_status_to_a2a("UNKNOWN") == "working"


# ============================================================
# A2A Router Endpoint Tests
# ============================================================

class TestA2ARouterEndpoints:
    """Test A2A Router HTTP endpoints."""

    @pytest.fixture
    def mock_controller(self):
        """Create a mock TerminalController."""
        controller = MagicMock()
        controller.status = "IDLE"
        controller.get_context.return_value = "Sample output context"
        return controller

    @pytest.fixture
    def app(self, mock_controller):
        """Create test application with A2A router."""
        from fastapi import FastAPI
        app = FastAPI()
        router = create_a2a_router(mock_controller, "test-agent", 8000, "\n")
        app.include_router(router)
        return app

    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return TestClient(app)

    def test_agent_card_endpoint(self, client):
        """/.well-known/agent.json should return Agent Card."""
        response = client.get("/.well-known/agent.json")

        assert response.status_code == 200
        data = response.json()
        assert "test-agent" in data["name"].lower()  # Name contains agent type
        assert "capabilities" in data
        assert "skills" in data

    def test_tasks_send_endpoint(self, client, mock_controller):
        """POST /tasks/send should create task."""
        payload = {
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": "Hello"}]
            }
        }

        response = client.post("/tasks/send", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert "task" in data
        assert data["task"]["status"] in ["submitted", "working"]
        mock_controller.write.assert_called_once()

    def test_tasks_send_priority_endpoint(self, client, mock_controller):
        """POST /tasks/send-priority should handle priority."""
        payload = {
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": "Urgent!"}]
            }
        }

        response = client.post("/tasks/send-priority?priority=5", json=payload)

        assert response.status_code == 200
        mock_controller.interrupt.assert_called_once()
        mock_controller.write.assert_called_once()

    def test_tasks_get_endpoint(self, client, mock_controller):
        """GET /tasks/{id} should return task status."""
        # First create a task
        payload = {
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": "Test"}]
            }
        }
        create_response = client.post("/tasks/send", json=payload)
        task_id = create_response.json()["task"]["id"]

        # Then get task status
        response = client.get(f"/tasks/{task_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == task_id

    def test_tasks_list_endpoint(self, client, mock_controller):
        """GET /tasks should list all tasks."""
        # Create some tasks
        payload = {"message": {"role": "user", "parts": [{"type": "text", "text": "Test"}]}}
        client.post("/tasks/send", json=payload)
        client.post("/tasks/send", json=payload)

        response = client.get("/tasks")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 2

    def test_tasks_cancel_endpoint(self, client, mock_controller):
        """POST /tasks/{id}/cancel should cancel task."""
        # First create a task
        payload = {"message": {"role": "user", "parts": [{"type": "text", "text": "Test"}]}}
        create_response = client.post("/tasks/send", json=payload)
        task_id = create_response.json()["task"]["id"]

        # Cancel the task
        response = client.post(f"/tasks/{task_id}/cancel")

        assert response.status_code == 200
        mock_controller.interrupt.assert_called()

    def test_tasks_send_empty_message_rejected(self, client):
        """POST /tasks/send should reject empty message."""
        payload = {
            "message": {
                "role": "user",
                "parts": []
            }
        }

        response = client.post("/tasks/send", json=payload)
        assert response.status_code == 400

    def test_task_completion_adds_artifact(self, client, mock_controller):
        """Task should get artifact when completed."""
        mock_controller.status = "IDLE"
        mock_controller.get_context.return_value = "Command output here"

        # Create and retrieve task
        payload = {"message": {"role": "user", "parts": [{"type": "text", "text": "Test"}]}}
        create_response = client.post("/tasks/send", json=payload)
        task_id = create_response.json()["task"]["id"]

        # Get task - should trigger completion check
        response = client.get(f"/tasks/{task_id}")

        data = response.json()
        assert data["status"] == "completed"
        assert len(data["artifacts"]) > 0


# ============================================================
# Integration Tests
# ============================================================

class TestAgentCardSynapseExtension:
    """Test synapse extension in Agent Card (pure business card format)."""

    @pytest.fixture
    def mock_controller(self):
        controller = MagicMock()
        controller.status = "IDLE"
        controller.get_context.return_value = ""
        return controller

    @pytest.fixture
    def client(self, mock_controller):
        from fastapi import FastAPI
        app = FastAPI()
        router = create_a2a_router(
            mock_controller, "claude", 8100, "\n",
            agent_id="synapse-claude-8100",
            registry=None
        )
        app.include_router(router)
        return TestClient(app)

    def test_agent_card_has_synapse_extension(self, client):
        """Agent Card should contain synapse extension."""
        response = client.get("/.well-known/agent.json")

        assert response.status_code == 200
        data = response.json()
        assert "synapse" in data["extensions"]

    def test_agent_card_no_x_synapse_context(self, client):
        """Agent Card should NOT contain x-synapse-context (moved to Task/Message)."""
        response = client.get("/.well-known/agent.json")
        data = response.json()

        # x-synapse-context should NOT be in Agent Card anymore
        assert "x-synapse-context" not in data["extensions"]

    def test_synapse_extension_has_agent_id(self, client):
        """synapse extension should have agent_id field."""
        response = client.get("/.well-known/agent.json")
        synapse = response.json()["extensions"]["synapse"]

        assert synapse["agent_id"] == "synapse-claude-8100"

    def test_synapse_extension_has_pty_wrapped(self, client):
        """synapse extension should have pty_wrapped field."""
        response = client.get("/.well-known/agent.json")
        synapse = response.json()["extensions"]["synapse"]

        assert synapse["pty_wrapped"] is True

    def test_synapse_extension_has_priority_interrupt(self, client):
        """synapse extension should have priority_interrupt field."""
        response = client.get("/.well-known/agent.json")
        synapse = response.json()["extensions"]["synapse"]

        assert synapse["priority_interrupt"] is True

    def test_synapse_extension_has_at_agent_syntax(self, client):
        """synapse extension should have at_agent_syntax field."""
        response = client.get("/.well-known/agent.json")
        synapse = response.json()["extensions"]["synapse"]

        assert synapse["at_agent_syntax"] is True

    def test_synapse_extension_has_addressable_as(self, client):
        """synapse extension should have addressable_as patterns."""
        response = client.get("/.well-known/agent.json")
        synapse = response.json()["extensions"]["synapse"]

        assert "addressable_as" in synapse
        assert "@synapse-claude-8100" in synapse["addressable_as"]
        assert "@claude" in synapse["addressable_as"]

    def test_agent_card_is_pure_business_card(self, client):
        """Agent Card should only contain discovery info, no internal instructions."""
        response = client.get("/.well-known/agent.json")
        data = response.json()

        # Should have basic discovery fields
        assert "name" in data
        assert "description" in data
        assert "url" in data
        assert "capabilities" in data
        assert "skills" in data

        # Should NOT have instruction-related fields in synapse extension
        synapse = data["extensions"]["synapse"]
        assert "routing_rules" not in synapse
        assert "available_agents" not in synapse
        assert "examples" not in synapse


class TestA2ACompliance:
    """Test full Google A2A protocol compliance."""

    @pytest.fixture
    def mock_controller(self):
        controller = MagicMock()
        controller.status = "BUSY"
        controller.get_context.return_value = ""
        return controller

    @pytest.fixture
    def client(self, mock_controller):
        from fastapi import FastAPI
        app = FastAPI()
        router = create_a2a_router(mock_controller, "test", 8000, "\n")
        app.include_router(router)
        return TestClient(app)

    def test_task_lifecycle(self, client, mock_controller):
        """Test complete task lifecycle: submitted -> working -> completed."""
        # 1. Create task (submitted -> working)
        payload = {"message": {"role": "user", "parts": [{"type": "text", "text": "Test"}]}}
        response = client.post("/tasks/send", json=payload)
        assert response.status_code == 200
        task_id = response.json()["task"]["id"]
        assert response.json()["task"]["status"] == "working"

        # 2. Check status while working
        mock_controller.status = "BUSY"
        response = client.get(f"/tasks/{task_id}")
        assert response.json()["status"] == "working"

        # 3. Simulate completion
        mock_controller.status = "IDLE"
        mock_controller.get_context.return_value = "Task completed successfully"
        response = client.get(f"/tasks/{task_id}")
        assert response.json()["status"] == "completed"
        assert len(response.json()["artifacts"]) > 0

    def test_message_format_compliance(self, client):
        """Test that message format complies with Google A2A spec."""
        payload = {
            "message": {
                "role": "user",
                "parts": [
                    {"type": "text", "text": "First part"},
                    {"type": "text", "text": "Second part"}
                ]
            },
            "context_id": "conv-123",
            "metadata": {"custom": "value"}
        }

        response = client.post("/tasks/send", json=payload)
        assert response.status_code == 200

        task = response.json()["task"]
        assert "id" in task
        assert "status" in task
        assert "message" in task
        assert "artifacts" in task
        assert "created_at" in task
        assert "updated_at" in task
