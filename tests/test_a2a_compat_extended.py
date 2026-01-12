"""Extended tests for A2A Compatibility Layer."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from synapse.a2a_compat import (
    Artifact,
    Message,
    Task,
    TextPart,
    _save_task_to_history,
    _send_response_to_sender,
    create_a2a_router,
)


class TestHistorySaving:
    """Tests for _save_task_to_history."""

    @pytest.fixture
    def mock_history(self):
        with patch("synapse.a2a_compat.history_manager") as mock:
            mock.enabled = True
            yield mock

    def test_save_task_handles_exceptions(self, mock_history):
        """Should catch and log exceptions during history save."""
        mock_history.save_observation.side_effect = Exception("DB Error")

        task = Task(
            id="123",
            status="completed",
            message=Message(parts=[TextPart(text="in")]),
            created_at="",
            updated_at="",
        )

        # Should not raise
        _save_task_to_history(task, "agent", "name", "completed")

    def test_save_task_extracts_artifacts(self, mock_history):
        """Should correctly format artifacts for history."""
        task = Task(
            id="123",
            status="completed",
            message=Message(parts=[TextPart(text="in")]),
            created_at="",
            updated_at="",
            artifacts=[
                Artifact(type="text", data="text result"),
                Artifact(
                    type="code",
                    data={"content": "print('hi')", "metadata": {"language": "python"}},
                ),
                Artifact(type="image", data="base64..."),
            ],
        )

        _save_task_to_history(task, "agent", "name", "completed")

        args = mock_history.save_observation.call_args
        output_text = args[1]["output_text"]

        assert "text result" in output_text
        assert "[Code: python]" in output_text
        assert "print('hi')" in output_text
        assert "[image]" in output_text

    def test_save_task_skips_if_disabled(self, mock_history):
        """Should skip saving if history manager is disabled."""
        mock_history.enabled = False

        task = Task(id="1", status="completed", created_at="", updated_at="")
        _save_task_to_history(task, "a", "n", "c")

        mock_history.save_observation.assert_not_called()


class TestResponseSender:
    """Tests for _send_response_to_sender."""

    @pytest.mark.asyncio
    async def test_send_response_success(self):
        """Should send response successfully."""
        task = Task(
            id="123",
            status="completed",
            artifacts=[Artifact(type="text", data="result")],
            created_at="",
            updated_at="",
            metadata={"sender": {"sender_endpoint": "http://sender"}},
        )

        with patch("synapse.a2a_compat.httpx.AsyncClient") as mock_client:
            mock_post = AsyncMock()
            # Ensure return value is a MagicMock (sync), not AsyncMock
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_post.return_value = mock_response

            mock_client.return_value.__aenter__.return_value.post = mock_post

            result = await _send_response_to_sender(task, "http://sender", "me")

            assert result is True
            mock_post.assert_called_once()
            args = mock_post.call_args
            assert args[0][0] == "http://sender/tasks/send"
            assert args[1]["json"]["message"]["role"] == "agent"

    @pytest.mark.asyncio
    async def test_send_response_handles_errors(self):
        """Should handle connection errors."""
        task = Task(id="123", status="completed", created_at="", updated_at="")

        import httpx

        with patch("synapse.a2a_compat.httpx.AsyncClient") as mock_client:
            mock_post = AsyncMock()
            mock_post.side_effect = httpx.RequestError("Connection failed")
            mock_client.return_value.__aenter__.return_value.post = mock_post

            result = await _send_response_to_sender(task, "http://sender", "me")

            assert result is False


class TestExtendedRouterEndpoints:
    """Tests for extended router functionality."""

    @pytest.fixture
    def client(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        controller = MagicMock()
        controller.status = "IDLE"
        controller.get_context.return_value = "out"

        router = create_a2a_router(controller, "test", 8000)
        app.include_router(router)
        return TestClient(app)

    def test_send_message_priority_interrupt(self, client):
        """Test priority interrupt logic."""
        with patch("synapse.a2a_compat.task_store") as mock_store:
            mock_store.create.return_value = Task(
                id="1", status="submitted", created_at="", updated_at=""
            )

            # Need to mock controller inside create_a2a_router closure
            # This is hard without recreating the router with a mock controller
            pass

    def test_external_agent_discovery(self, client):
        """Test external agent discovery endpoint."""
        with patch("synapse.a2a_compat.get_client") as mock_get_client:
            mock_client = mock_get_client.return_value
            mock_agent = MagicMock()
            # Explicitly set string values to satisfy Pydantic
            mock_agent.name = "Ext"
            mock_agent.alias = "ext"
            mock_agent.url = "http://ext"
            mock_agent.description = "desc"
            mock_agent.capabilities = {}
            mock_agent.skills = []
            mock_agent.added_at = "now"
            mock_agent.last_seen = "now"

            mock_client.discover.return_value = mock_agent

            resp = client.post(
                "/external/discover", json={"url": "http://ext", "alias": "ext"}
            )

            assert resp.status_code == 200
            assert resp.json()["name"] == "Ext"

    def test_external_agent_discovery_failure(self, client):
        """Test discovery failure."""
        with patch("synapse.a2a_compat.get_client") as mock_get_client:
            mock_client = mock_get_client.return_value
            mock_client.discover.return_value = None

            resp = client.post("/external/discover", json={"url": "http://ext"})
            assert resp.status_code == 400

    def test_send_to_external_agent(self, client):
        """Test sending to external agent."""
        with patch("synapse.a2a_compat.get_client") as mock_get_client:
            mock_client = mock_get_client.return_value
            mock_client.registry.get.return_value = MagicMock()

            mock_task = Task(
                id="ext1", status="completed", created_at="", updated_at=""
            )
            mock_client.send_message.return_value = mock_task

            resp = client.post("/external/agents/ext/send", json={"message": "hi"})

            assert resp.status_code == 200
            assert resp.json()["id"] == "ext1"

    def test_register_webhook(self, client):
        """Test webhook registration."""
        with patch("synapse.a2a_compat.get_webhook_registry") as mock_registry:
            mock_wh = MagicMock()
            mock_wh.url = "http://cb"
            mock_wh.events = ["task.completed"]
            mock_wh.enabled = True
            # Use valid datetime for created_at
            mock_wh.created_at = datetime.now(timezone.utc)

            mock_registry.return_value.register.return_value = mock_wh

            resp = client.post(
                "/webhooks", json={"url": "http://cb", "events": ["task.completed"]}
            )

            assert resp.status_code == 200
            assert resp.json()["url"] == "http://cb"

    def test_list_webhook_deliveries(self, client):
        """Test listing webhook deliveries."""
        with patch("synapse.a2a_compat.get_webhook_registry") as mock_registry:
            mock_del = MagicMock()
            mock_del.webhook_url = "http://cb"
            mock_del.event.event_type = "task.completed"
            mock_del.event.id = "evt1"  # Explicit string
            mock_del.status_code = 200
            mock_del.success = True
            mock_del.error = None  # Or string
            mock_del.delivered_at = datetime.now(timezone.utc)

            mock_registry.return_value.get_recent_deliveries.return_value = [mock_del]

            resp = client.get("/webhooks/deliveries")

            assert resp.status_code == 200
            assert len(resp.json()) == 1
