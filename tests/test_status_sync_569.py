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
