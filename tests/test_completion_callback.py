"""Tests for completion callback feature (Issue #285)."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from synapse.a2a_compat import Message, Task, TextPart, create_a2a_router
from synapse.history import HistoryManager


class TestHistoryUpdate:
    """Tests for HistoryManager.update_observation_status()."""

    @pytest.fixture
    def history_manager(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "history.db"
            yield HistoryManager(db_path=str(db_path))

    def test_update_observation_status_updates_status_and_output(self, history_manager):
        history_manager.save_observation(
            task_id="task-1",
            agent_name="claude",
            session_id="a2a-send",
            input_text="hello",
            output_text="Task sent",
            status="sent",
            metadata={"direction": "sent", "priority": 1},
        )

        updated = history_manager.update_observation_status(
            task_id="task-1",
            status="completed",
            output_text="Task completed",
            metadata_update={"completion_callback": True},
        )

        assert updated is True
        observation = history_manager.get_observation("task-1")
        assert observation is not None
        assert observation["status"] == "completed"
        assert observation["output"] == "Task completed"
        assert observation["metadata"]["direction"] == "sent"
        assert observation["metadata"]["completion_callback"] is True

    def test_update_observation_status_returns_false_for_missing_task(
        self, history_manager
    ):
        updated = history_manager.update_observation_status(
            task_id="missing-task",
            status="completed",
        )

        assert updated is False


class TestHistoryUpdateEndpoint:
    """Tests for POST /history/update endpoint."""

    @pytest.fixture
    def app(self):
        controller = MagicMock()
        controller.status = "READY"
        controller.get_context.return_value = "done"

        app = FastAPI()
        router = create_a2a_router(controller, "test-agent", 8121, "\n")
        app.include_router(router)
        return app

    @pytest.fixture
    def client(self, app):
        return TestClient(app)

    def test_history_update_endpoint_returns_200(self, client):
        with patch("synapse.a2a_compat.history_manager") as mock_history:
            mock_history.enabled = True
            mock_history.update_observation_status.return_value = True

            response = client.post(
                "/history/update",
                json={
                    "task_id": "task-123",
                    "status": "completed",
                    "output_summary": "done",
                },
            )

        assert response.status_code == 200

    def test_history_update_endpoint_returns_404_for_missing_task(self, client):
        with patch("synapse.a2a_compat.history_manager") as mock_history:
            mock_history.enabled = True
            mock_history.update_observation_status.return_value = False

            response = client.post(
                "/history/update",
                json={
                    "task_id": "missing",
                    "status": "completed",
                    "output_summary": "done",
                },
            )

        assert response.status_code == 404


class TestCompletionNotification:
    """Tests for --silent completion callback behavior."""

    @pytest.fixture
    def app(self):
        controller = MagicMock()
        controller.status = "READY"
        controller.get_context.return_value = "task done successfully"

        app = FastAPI()
        router = create_a2a_router(controller, "test-agent", 8121, "\n")
        app.include_router(router)
        return app

    @pytest.fixture
    def client(self, app):
        return TestClient(app)

    def test_silent_task_triggers_completion_notification(self, client):
        """When response_mode='silent', send best-effort notification on completion."""
        send_response = client.post(
            "/tasks/send",
            json={
                "message": {"role": "user", "parts": [{"type": "text", "text": "run"}]},
                "metadata": {
                    "response_mode": "silent",
                    "sender": {
                        "sender_id": "synapse-claude-8100",
                        "sender_endpoint": "http://localhost:8100",
                        "sender_uds_path": "/tmp/sender.sock",
                    },
                },
            },
        )
        assert send_response.status_code == 200
        task_id = send_response.json()["task"]["id"]

        with (
            patch(
                "synapse.a2a_compat._notify_sender_completion",
                new_callable=AsyncMock,
                create=True,
            ) as mock_notify,
            patch(
                "synapse.a2a_compat._send_response_to_sender", new_callable=AsyncMock
            ) as mock_send,
        ):
            get_response = client.get(f"/tasks/{task_id}")

        assert get_response.status_code == 200
        mock_notify.assert_called_once()
        mock_send.assert_not_called()

    def test_notify_task_sends_full_response(self, client):
        """When response_mode='notify', send full response on completion (non-blocking)."""
        send_response = client.post(
            "/tasks/send",
            json={
                "message": {"role": "user", "parts": [{"type": "text", "text": "run"}]},
                "metadata": {
                    "response_mode": "notify",
                    "sender": {
                        "sender_id": "synapse-claude-8100",
                        "sender_endpoint": "http://localhost:8100",
                    },
                },
            },
        )
        assert send_response.status_code == 200
        task_id = send_response.json()["task"]["id"]

        with (
            patch(
                "synapse.a2a_compat._send_response_to_sender", new_callable=AsyncMock
            ) as mock_send,
            patch(
                "synapse.a2a_compat._notify_sender_completion",
                new_callable=AsyncMock,
                create=True,
            ) as mock_notify,
        ):
            get_response = client.get(f"/tasks/{task_id}")

        assert get_response.status_code == 200
        mock_send.assert_called_once()
        mock_notify.assert_not_called()

    def test_response_mode_wait_flow_still_sends_response(self, client):
        send_response = client.post(
            "/tasks/send",
            json={
                "message": {"role": "user", "parts": [{"type": "text", "text": "run"}]},
                "metadata": {
                    "response_mode": "wait",
                    "sender": {
                        "sender_id": "synapse-claude-8100",
                        "sender_endpoint": "http://localhost:8100",
                        "sender_task_id": "sender-task-1",
                    },
                },
            },
        )
        assert send_response.status_code == 200
        task_id = send_response.json()["task"]["id"]

        with (
            patch(
                "synapse.a2a_compat._send_response_to_sender", new_callable=AsyncMock
            ) as mock_send,
            patch(
                "synapse.a2a_compat._notify_sender_completion",
                new_callable=AsyncMock,
                create=True,
            ) as mock_notify,
        ):
            get_response = client.get(f"/tasks/{task_id}")

        assert get_response.status_code == 200
        mock_send.assert_called_once()
        mock_notify.assert_not_called()

    @pytest.mark.asyncio
    async def test_notify_sender_completion_is_best_effort(self):
        import synapse.a2a_compat as compat

        assert hasattr(compat, "_notify_sender_completion")

        task = Task(
            id="task-abc",
            status="completed",
            message=Message(parts=[TextPart(text="in")]),
            created_at="",
            updated_at="",
        )

        with patch("synapse.a2a_compat.httpx.AsyncClient") as mock_client:
            mock_post = AsyncMock()
            import httpx

            mock_post.side_effect = httpx.RequestError("boom")
            mock_client.return_value.__aenter__.return_value.post = mock_post

            result = await compat._notify_sender_completion(
                task=task,
                sender_endpoint="http://localhost:8100",
                sender_uds_path=None,
                sender_task_id="task-abc",
                status="completed",
            )

        assert result is False
