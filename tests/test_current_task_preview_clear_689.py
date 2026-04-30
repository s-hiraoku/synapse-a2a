"""Regression tests for clearing stale current task previews (#689)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from synapse.a2a_compat import create_a2a_router, task_store
from synapse.status import SENDING_REPLY

AGENT_ID = "synapse-codex-8126"


class _Transport:
    def deliver(
        self,
        task_id: str,
        message: str,
        *,
        response_mode: str,
        sender_id: str | None = None,
        sender_name: str | None = None,
    ) -> bool:
        return True


@pytest.fixture(autouse=True)
def clear_task_store() -> None:
    with task_store._lock:
        task_store._tasks.clear()


@pytest.fixture
def controller() -> MagicMock:
    c = MagicMock()
    c.status = "PROCESSING"
    c.agent_ready = True
    c.wait_until_ready.return_value = True
    c.get_context.return_value = "working..."
    c.write.return_value = True
    return c


@pytest.fixture
def registry() -> MagicMock:
    reg = MagicMock()
    reg.get_agent.return_value = {"status": "PROCESSING"}
    return reg


@pytest.fixture
def client(controller: MagicMock, registry: MagicMock) -> TestClient:
    app = FastAPI()
    app.include_router(
        create_a2a_router(
            controller,
            "codex",
            8126,
            "\n",
            agent_id=AGENT_ID,
            registry=registry,
            transport=_Transport(),
        )
    )
    return TestClient(app)


def _send_task(client: TestClient, text: str = "Implement issue #689") -> str:
    response = client.post(
        "/tasks/send",
        json={
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": text}],
            }
        },
    )
    assert response.status_code == 200
    return str(response.json()["task"]["id"])


def _assert_preview_cleared(registry: MagicMock) -> None:
    registry.update_current_task.assert_any_call(AGENT_ID, None)


def test_preview_cleared_on_task_completed(
    client: TestClient, registry: MagicMock
) -> None:
    task_id = _send_task(client)

    response = client.post(f"/tasks/{task_id}/reply", json={"message": "Done"})

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    _assert_preview_cleared(registry)


def test_preview_cleared_on_task_failed(
    client: TestClient, registry: MagicMock
) -> None:
    task_id = _send_task(client)

    response = client.post(
        f"/tasks/{task_id}/reply",
        json={
            "message": "Failed",
            "status": "failed",
            "error": {"code": "TASK_FAILED", "message": "Failed"},
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    _assert_preview_cleared(registry)


def test_preview_cleared_on_task_canceled(
    client: TestClient, registry: MagicMock
) -> None:
    task_id = _send_task(client)

    response = client.post(f"/tasks/{task_id}/cancel")

    assert response.status_code == 200
    assert response.json()["status"] == "canceled"
    _assert_preview_cleared(registry)


def test_preview_persists_during_processing(
    client: TestClient, registry: MagicMock
) -> None:
    _send_task(client, "Keep working")

    registry.update_current_task.assert_any_call(AGENT_ID, "Keep working")
    assert (AGENT_ID, None) not in [
        call.args for call in registry.update_current_task.call_args_list
    ]


def test_preview_persists_during_sending_reply(
    client: TestClient, registry: MagicMock
) -> None:
    task_id = _send_task(client, "Reply to sender")
    registry.get_agent.return_value = {"status": SENDING_REPLY}

    response = client.post(f"/tasks/{task_id}/reply", json={"message": "Done"})

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert (AGENT_ID, None) not in [
        call.args for call in registry.update_current_task.call_args_list
    ]


def test_task_received_at_cleared_with_preview(
    client: TestClient, registry: MagicMock
) -> None:
    task_id = _send_task(client)

    response = client.post(f"/tasks/{task_id}/reply", json={"message": "Done"})

    assert response.status_code == 200
    _assert_preview_cleared(registry)
