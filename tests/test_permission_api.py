"""Tests for permission approval and denial endpoints."""

from __future__ import annotations

from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from synapse.a2a_compat import Message, TextPart, create_a2a_router, task_store


def _make_app() -> FastAPI:
    controller = MagicMock()
    controller.status = "WAITING"
    controller.agent_ready = True
    controller.wait_until_ready.return_value = True
    controller.get_context.return_value = "Allow Bash: rm -rf /tmp/test? [Y/n]"
    controller.write.return_value = True

    app = FastAPI()
    app.state.router_controller = controller
    app.include_router(
        create_a2a_router(
            controller,
            "codex",
            8120,
            "\n",
            agent_id="synapse-codex-8120",
            approve_response="y\r",
            deny_response="\x1b",
        )
    )
    return app


def _create_input_required_task() -> str:
    task = task_store.create(
        Message(parts=[TextPart(text="Run command")]),
        metadata={"permission": {"pty_context": "Allow Bash", "agent_type": "codex"}},
    )
    task_store.update_status(task.id, "input_required")
    return task.id


def test_permission_approve_returns_200_and_writes_runtime_response():
    app = _make_app()
    client = TestClient(app)
    task_id = _create_input_required_task()

    response = client.post(f"/tasks/{task_id}/permission/approve")

    assert response.status_code == 200
    assert response.json() == {"status": "approved", "task_id": task_id}
    app.state.router_controller.write.assert_called_once_with("y\r", submit_seq="\n")
    updated = task_store.get(task_id)
    assert updated is not None
    assert updated.status == "working"


def test_permission_deny_returns_200_and_writes_deny_response():
    app = _make_app()
    client = TestClient(app)
    task_id = _create_input_required_task()

    response = client.post(f"/tasks/{task_id}/permission/deny")

    assert response.status_code == 200
    assert response.json() == {"status": "denied", "task_id": task_id}
    app.state.router_controller.write.assert_called_once_with("\x1b", submit_seq="\n")
    updated = task_store.get(task_id)
    assert updated is not None
    assert updated.status == "working"


def test_permission_approve_or_deny_returns_404_for_missing_task():
    app = _make_app()
    client = TestClient(app)

    approve = client.post("/tasks/missing-task/permission/approve")
    deny = client.post("/tasks/missing-task/permission/deny")

    assert approve.status_code == 404
    assert deny.status_code == 404


def test_permission_approve_or_deny_returns_400_for_non_input_required_task():
    app = _make_app()
    client = TestClient(app)
    task = task_store.create(Message(parts=[TextPart(text="Run command")]))
    task_store.update_status(task.id, "working")

    approve = client.post(f"/tasks/{task.id}/permission/approve")
    deny = client.post(f"/tasks/{task.id}/permission/deny")

    assert approve.status_code == 400
    assert deny.status_code == 400
