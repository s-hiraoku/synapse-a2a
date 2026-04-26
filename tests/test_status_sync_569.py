"""Tests for issue #569: status sync between controller and task_store.

The core bug: when the controller transitions WAITING → READY (e.g., the
permission prompt disappears because the user accepted), the task_store
does not revert from ``input_required`` back to ``working``. This makes
``GET /tasks/{id}`` return a stale ``input_required`` and causes the
Approval Gate loop to re-escalate.

Additionally, the ``GET /tasks/{id}`` handler itself was a rogue writer:
it called ``task_store.update_status(task_id, "input_required")`` when
``is_input_required(context)`` was True, even when ``controller.status``
was already READY. A GET handler should be side-effect-free.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from synapse.a2a_compat import create_a2a_router
from synapse.a2a_models import Message, TextPart
from synapse.status import WAITING_FOR_INPUT
from synapse.task_store import TaskStore


@pytest.fixture
def mock_controller() -> MagicMock:
    c = MagicMock()
    c.status = "PROCESSING"
    c.get_context.return_value = "Working on task..."
    return c


@pytest.fixture
def task_store_instance() -> TaskStore:
    return TaskStore()


@pytest.fixture
def app(mock_controller: MagicMock, task_store_instance: TaskStore) -> FastAPI:
    app = FastAPI()
    router = create_a2a_router(mock_controller, "codex", 8126, "\n")
    app.include_router(router)
    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


class TestWaitingToReadyRevertsTaskStore:
    """Fix 1: _on_status_change must revert input_required → working
    when controller exits WAITING to any state, not just PROCESSING.
    """

    def test_waiting_to_ready_reverts_input_required_tasks(
        self, mock_controller: MagicMock
    ) -> None:
        """When controller goes WAITING → READY (permission accepted and
        new output arrived), all input_required tasks must become working
        again. Pre-fix: only WAITING → PROCESSING was handled."""
        app = FastAPI()
        router = create_a2a_router(mock_controller, "codex", 8126, "\n")
        app.include_router(router)
        client = TestClient(app)

        # Grab the task_store from the router closure — send a task
        # to create one in the store.
        resp = client.post(
            "/tasks/send",
            json={
                "message": {"role": "user", "parts": [{"text": "hello"}]},
            },
        )
        assert resp.status_code == 200
        task_id = resp.json()["task"]["id"]

        # Import the task_store singleton used by the router:
        from synapse.a2a_compat import task_store

        # Simulate the controller going WAITING
        mock_controller.status = "WAITING"
        callbacks = mock_controller.on_status_change.call_args_list
        # The router registered a callback via controller.on_status_change
        assert len(callbacks) >= 1
        status_callback = callbacks[0][0][0]

        status_callback("PROCESSING", "WAITING")
        task = task_store.get(task_id)
        assert task is not None
        assert task.status == "input_required"

        # Now simulate WAITING → READY (the missing path pre-fix)
        mock_controller.status = "READY"
        mock_controller.get_context.return_value = "New output after prompt cleared"
        status_callback("WAITING", "READY")

        task = task_store.get(task_id)
        assert task is not None
        assert task.status != "input_required", (
            "task_store must revert from input_required when controller "
            "exits WAITING to READY"
        )

    def test_waiting_to_done_reverts_input_required_tasks(
        self, mock_controller: MagicMock
    ) -> None:
        """WAITING → DONE should also revert input_required tasks."""
        app = FastAPI()
        router = create_a2a_router(mock_controller, "codex", 8126, "\n")
        app.include_router(router)
        client = TestClient(app)

        resp = client.post(
            "/tasks/send",
            json={
                "message": {"role": "user", "parts": [{"text": "hello"}]},
            },
        )
        task_id = resp.json()["task"]["id"]

        from synapse.a2a_compat import task_store

        callbacks = mock_controller.on_status_change.call_args_list
        status_callback = callbacks[0][0][0]

        mock_controller.status = "WAITING"
        status_callback("PROCESSING", "WAITING")
        assert task_store.get(task_id).status == "input_required"

        mock_controller.status = "DONE"
        mock_controller.get_context.return_value = "Task completed"
        status_callback("WAITING", "DONE")

        task = task_store.get(task_id)
        assert task is not None
        assert task.status != "input_required"


class TestGetTasksNoRogueWrite:
    """Fix 2: GET /tasks/{id} must not write to task_store.

    Pre-fix, the handler called
    ``task_store.update_status(task_id, "input_required")`` when
    ``is_input_required(context)`` returned True, even when the
    controller had already exited WAITING. A GET handler should be
    side-effect-free.
    """

    def test_get_task_does_not_set_input_required(
        self, mock_controller: MagicMock
    ) -> None:
        app = FastAPI()
        router = create_a2a_router(mock_controller, "codex", 8126, "\n")
        app.include_router(router)
        client = TestClient(app)

        # Create a task
        resp = client.post(
            "/tasks/send",
            json={
                "message": {"role": "user", "parts": [{"text": "hello"}]},
            },
        )
        task_id = resp.json()["task"]["id"]

        from synapse.a2a_compat import task_store

        # Controller is READY but context still has permission remnant
        mock_controller.status = "READY"
        mock_controller.get_context.return_value = (
            "Some old text with › 1. Yes, proceed remnant"
        )

        # GET the task — must NOT write input_required
        resp = client.get(f"/tasks/{task_id}")

        assert resp.status_code == 200
        # Verify task_store was NOT updated to input_required
        task = task_store.get(task_id)
        assert task is not None
        assert task.status != "input_required", (
            "GET /tasks/{id} must not set input_required — it is a read-only endpoint"
        )


class TestTerminalTasksDemoteRegistry:
    """Fix 3: terminal-only task_store should demote stale registry states."""

    agent_id = "synapse-test-agent-8126"

    def setup_method(self) -> None:
        from synapse.a2a_compat import task_store

        with task_store._lock:
            task_store._tasks.clear()

    def _register_callback(self, mock_controller: MagicMock, mock_registry: MagicMock):
        create_a2a_router(
            mock_controller,
            "codex",
            8126,
            "\n",
            agent_id=self.agent_id,
            registry=mock_registry,
        )
        return mock_controller.on_status_change.call_args.args[0]

    def test_terminal_only_tasks_demote_processing_to_ready(
        self, mock_controller: MagicMock
    ) -> None:
        from synapse.a2a_compat import task_store

        mock_controller.status = "READY"
        mock_controller.get_context.return_value = "Task completed"
        mock_controller.last_waiting_source = "none"
        mock_registry = MagicMock()
        mock_registry.get_agent.return_value = {"status": "PROCESSING"}
        status_callback = self._register_callback(mock_controller, mock_registry)

        task = task_store.create(Message(parts=[TextPart(text="hello")]))
        task_store.update_status(task.id, "working")

        status_callback("PROCESSING", "READY")

        mock_registry.update_status.assert_any_call(self.agent_id, "READY")

    def test_working_task_keeps_processing(self, mock_controller: MagicMock) -> None:
        from synapse.a2a_compat import task_store

        mock_controller.status = "PROCESSING"
        mock_controller.last_waiting_source = "none"
        mock_registry = MagicMock()
        mock_registry.get_agent.return_value = {"status": "PROCESSING"}
        status_callback = self._register_callback(mock_controller, mock_registry)

        task = task_store.create(Message(parts=[TextPart(text="hello")]))
        task_store.update_status(task.id, "working")

        status_callback("READY", "PROCESSING")

        assert (self.agent_id, "READY") not in [
            call.args for call in mock_registry.update_status.call_args_list
        ]

    def test_input_required_task_does_not_demote(
        self, mock_controller: MagicMock
    ) -> None:
        from synapse.a2a_compat import task_store

        mock_controller.status = "PROCESSING"
        mock_controller.last_waiting_source = "none"
        mock_registry = MagicMock()
        mock_registry.get_agent.return_value = {"status": "PROCESSING"}
        status_callback = self._register_callback(mock_controller, mock_registry)

        task = task_store.create(Message(parts=[TextPart(text="confirm?")]))
        task_store.update_status(task.id, "input_required")

        status_callback("READY", "PROCESSING")

        mock_registry.update_status.assert_any_call(self.agent_id, WAITING_FOR_INPUT)
        assert (self.agent_id, "READY") not in [
            call.args for call in mock_registry.update_status.call_args_list
        ]

    def test_empty_task_store_does_not_demote(self, mock_controller: MagicMock) -> None:
        mock_controller.status = "PROCESSING"
        mock_controller.last_waiting_source = "none"
        mock_registry = MagicMock()
        mock_registry.get_agent.return_value = {"status": "PROCESSING"}
        status_callback = self._register_callback(mock_controller, mock_registry)

        status_callback("READY", "PROCESSING")

        assert (self.agent_id, "READY") not in [
            call.args for call in mock_registry.update_status.call_args_list
        ]

    def test_demotion_does_not_touch_controller_status(
        self, mock_controller: MagicMock
    ) -> None:
        from synapse.a2a_compat import task_store

        mock_controller.status = "PROCESSING"
        mock_controller.get_context.return_value = "Task completed"
        mock_controller.last_waiting_source = "none"
        mock_registry = MagicMock()
        mock_registry.get_agent.return_value = {"status": "PROCESSING"}
        status_callback = self._register_callback(mock_controller, mock_registry)

        task = task_store.create(Message(parts=[TextPart(text="hello")]))
        task_store.update_status(task.id, "working")

        status_callback("PROCESSING", "READY")

        assert mock_controller.status == "PROCESSING"
        mock_registry.update_status.assert_any_call(self.agent_id, "READY")
