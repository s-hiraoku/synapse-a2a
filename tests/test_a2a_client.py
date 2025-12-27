"""Tests for A2A Client - Google A2A protocol compliance."""
import pytest
import responses
import json
from synapse.a2a_client import (
    A2AClient,
    A2AMessage,
    A2ATask,
    ExternalAgent,
    ExternalAgentRegistry
)
from pathlib import Path
import shutil


# ============================================================
# A2AMessage Tests
# ============================================================

class TestA2AMessage:
    """Test A2A Message structure."""

    def test_from_text_creates_valid_message(self):
        """Message from text should have correct structure."""
        msg = A2AMessage.from_text("Hello, World!")

        assert msg.role == "user"
        assert len(msg.parts) == 1
        assert msg.parts[0]["type"] == "text"
        assert msg.parts[0]["text"] == "Hello, World!"

    def test_from_text_preserves_special_characters(self):
        """Message should preserve special characters."""
        msg = A2AMessage.from_text("こんにちは\n改行あり")

        assert msg.parts[0]["text"] == "こんにちは\n改行あり"

    def test_default_role_is_user(self):
        """Default role should be 'user'."""
        msg = A2AMessage()
        assert msg.role == "user"


# ============================================================
# ExternalAgentRegistry Tests
# ============================================================

@pytest.fixture
def external_registry():
    """Create a temporary external agent registry."""
    registry = ExternalAgentRegistry()
    registry.registry_dir = Path("/tmp/a2a_test_external")
    registry.registry_dir.mkdir(parents=True, exist_ok=True)
    registry._cache = {}  # Clear cache
    yield registry
    shutil.rmtree(registry.registry_dir, ignore_errors=True)


class TestExternalAgentRegistry:
    """Test external agent registry."""

    def test_add_and_get_agent(self, external_registry):
        """Should add and retrieve an agent."""
        agent = ExternalAgent(
            name="Test Agent",
            url="http://localhost:8000",
            alias="test"
        )
        external_registry.add(agent)

        retrieved = external_registry.get("test")
        assert retrieved is not None
        assert retrieved.name == "Test Agent"
        assert retrieved.url == "http://localhost:8000"

    def test_remove_agent(self, external_registry):
        """Should remove an agent."""
        agent = ExternalAgent(name="ToDelete", url="http://example.com", alias="delete")
        external_registry.add(agent)

        result = external_registry.remove("delete")
        assert result is True
        assert external_registry.get("delete") is None

    def test_list_agents(self, external_registry):
        """Should list all agents."""
        external_registry.add(ExternalAgent(name="Agent1", url="http://a1.com", alias="a1"))
        external_registry.add(ExternalAgent(name="Agent2", url="http://a2.com", alias="a2"))

        agents = external_registry.list_agents()
        assert len(agents) == 2
        aliases = [a.alias for a in agents]
        assert "a1" in aliases
        assert "a2" in aliases


# ============================================================
# A2AClient Tests
# ============================================================

@pytest.fixture
def a2a_client(external_registry):
    """Create A2A client with test registry."""
    return A2AClient(registry=external_registry)


class TestA2AClientDiscover:
    """Test agent discovery."""

    @responses.activate
    def test_discover_agent_success(self, a2a_client):
        """Should discover agent from Agent Card."""
        agent_card = {
            "name": "Remote Agent",
            "description": "A remote A2A agent",
            "url": "http://remote.example.com",
            "capabilities": {"streaming": False},
            "skills": []
        }

        responses.add(
            responses.GET,
            "http://remote.example.com/.well-known/agent.json",
            json=agent_card,
            status=200
        )

        agent = a2a_client.discover("http://remote.example.com", alias="remote")

        assert agent is not None
        assert agent.name == "Remote Agent"
        assert agent.alias == "remote"

    @responses.activate
    def test_discover_agent_not_found(self, a2a_client):
        """Should return None when agent not found."""
        responses.add(
            responses.GET,
            "http://invalid.com/.well-known/agent.json",
            status=404
        )

        agent = a2a_client.discover("http://invalid.com")
        assert agent is None


class TestA2AClientSendToLocal:
    """Test send_to_local method for local agent communication."""

    @responses.activate
    def test_send_to_local_success(self, a2a_client):
        """Should send message to local agent using A2A protocol."""
        task_response = {
            "task": {
                "id": "task-123",
                "status": "working",
                "message": {"role": "user", "parts": [{"type": "text", "text": "test"}]},
                "artifacts": [],
                "created_at": "2025-01-01T00:00:00Z",
                "updated_at": "2025-01-01T00:00:00Z"
            }
        }

        responses.add(
            responses.POST,
            "http://localhost:8001/tasks/send-priority?priority=1",
            json=task_response,
            status=200
        )

        task = a2a_client.send_to_local(
            endpoint="http://localhost:8001",
            message="Hello",
            priority=1
        )

        assert task is not None
        assert task.id == "task-123"
        assert task.status == "working"

    @responses.activate
    def test_send_to_local_with_priority(self, a2a_client):
        """Should include priority in URL."""
        responses.add(
            responses.POST,
            "http://localhost:8001/tasks/send-priority?priority=5",
            json={"task": {"id": "t-1", "status": "working"}},
            status=200
        )

        task = a2a_client.send_to_local(
            endpoint="http://localhost:8001",
            message="Urgent!",
            priority=5
        )

        assert task is not None
        # Verify the URL included priority=5
        assert responses.calls[0].request.url == "http://localhost:8001/tasks/send-priority?priority=5"

    @responses.activate
    def test_send_to_local_request_format(self, a2a_client):
        """Should send message in Google A2A format."""
        responses.add(
            responses.POST,
            "http://localhost:8001/tasks/send-priority?priority=1",
            json={"task": {"id": "t-1", "status": "working"}},
            status=200
        )

        a2a_client.send_to_local(
            endpoint="http://localhost:8001",
            message="Test message"
        )

        # Verify request body format
        request_body = json.loads(responses.calls[0].request.body)
        assert "message" in request_body
        assert request_body["message"]["role"] == "user"
        assert request_body["message"]["parts"][0]["type"] == "text"
        assert request_body["message"]["parts"][0]["text"] == "Test message"

    @responses.activate
    def test_send_to_local_failure(self, a2a_client):
        """Should return None on failure."""
        responses.add(
            responses.POST,
            "http://localhost:8001/tasks/send-priority?priority=1",
            status=500
        )

        task = a2a_client.send_to_local(
            endpoint="http://localhost:8001",
            message="Test"
        )

        assert task is None


class TestA2AClientSendMessage:
    """Test send_message method for external agents."""

    @responses.activate
    def test_send_message_to_external_agent(self, a2a_client, external_registry):
        """Should send message to external agent."""
        # Register external agent
        external_registry.add(ExternalAgent(
            name="External",
            url="http://external.example.com",
            alias="ext"
        ))

        responses.add(
            responses.POST,
            "http://external.example.com/tasks/send",
            json={"task": {"id": "ext-task-1", "status": "submitted"}},
            status=200
        )

        task = a2a_client.send_message("ext", "Hello external!")

        assert task is not None
        assert task.id == "ext-task-1"

    def test_send_message_agent_not_found(self, a2a_client):
        """Should return None when agent not found."""
        task = a2a_client.send_message("nonexistent", "Hello")
        assert task is None


class TestA2AClientWaitForCompletion:
    """Test polling for task completion."""

    @responses.activate
    def test_wait_for_local_completion(self, a2a_client):
        """Should poll until task completes."""
        # First poll: working
        responses.add(
            responses.GET,
            "http://localhost:8001/tasks/task-1",
            json={"id": "task-1", "status": "working", "artifacts": []},
            status=200
        )
        # Second poll: completed
        responses.add(
            responses.GET,
            "http://localhost:8001/tasks/task-1",
            json={"id": "task-1", "status": "completed", "artifacts": [{"type": "text", "data": "Result"}]},
            status=200
        )

        task = a2a_client._wait_for_local_completion(
            endpoint="http://localhost:8001",
            task_id="task-1",
            timeout=5
        )

        assert task is not None
        assert task.status == "completed"
        assert len(task.artifacts) == 1


# ============================================================
# A2ATask Tests
# ============================================================

class TestA2ATask:
    """Test A2A Task structure."""

    def test_task_creation(self):
        """Should create task with all fields."""
        task = A2ATask(
            id="test-id",
            status="working",
            message={"role": "user", "parts": []},
            artifacts=[{"type": "text", "data": "output"}],
            created_at="2025-01-01T00:00:00Z",
            updated_at="2025-01-01T00:00:01Z"
        )

        assert task.id == "test-id"
        assert task.status == "working"
        assert len(task.artifacts) == 1
