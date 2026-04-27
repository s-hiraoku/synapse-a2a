"""Tests for true PTY-level task cancellation interrupt behavior (#647)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from synapse.a2a_compat import create_a2a_router, task_store
from synapse.controller import TerminalController
from synapse.server import load_profile


@pytest.fixture(autouse=True)
def clear_task_store() -> None:
    """Keep global task_store state isolated between endpoint tests."""
    with task_store._lock:
        task_store._tasks.clear()


def test_interrupt_via_pty_writes_etx_to_master_fd(monkeypatch: pytest.MonkeyPatch):
    controller = TerminalController.__new__(TerminalController)
    controller.master_fd = 99
    writes: list[tuple[int, bytes]] = []

    monkeypatch.setattr(
        "synapse.controller.os.write",
        lambda fd, data: writes.append((fd, data)) or len(data),
    )

    assert controller.interrupt_via_pty() is True
    assert writes == [(99, b"\x03")]


def test_interrupt_via_pty_repeat_writes_multiple_bytes(
    monkeypatch: pytest.MonkeyPatch,
):
    controller = TerminalController.__new__(TerminalController)
    controller.master_fd = 99
    writes: list[tuple[int, bytes]] = []

    monkeypatch.setattr(
        "synapse.controller.os.write",
        lambda fd, data: writes.append((fd, data)) or len(data),
    )
    monkeypatch.setattr("synapse.controller.time.sleep", lambda _interval: None)

    assert controller.interrupt_via_pty(repeat=2) is True
    assert writes == [(99, b"\x03"), (99, b"\x03")]


def test_interrupt_via_pty_returns_false_when_master_fd_is_none():
    controller = TerminalController.__new__(TerminalController)
    controller.master_fd = None

    assert controller.interrupt_via_pty() is False


def _client_for_controller(
    controller: MagicMock, agent_type: str = "claude"
) -> TestClient:
    app = FastAPI()
    app.include_router(create_a2a_router(controller, agent_type, 8000, "\n"))
    return TestClient(app)


def _create_task(client: TestClient) -> str:
    response = client.post(
        "/tasks/send",
        json={"message": {"role": "user", "parts": [{"type": "text", "text": "hi"}]}},
    )
    assert response.status_code == 200
    return str(response.json()["task"]["id"])


def _mock_controller(profile: str = "claude") -> MagicMock:
    controller = MagicMock()
    controller.status = "IDLE"
    controller.agent_type = profile
    controller.interrupt_config = load_profile(profile).get("interrupt")
    controller.get_context.return_value = ""
    return controller


@pytest.mark.parametrize(
    ("profile", "mode", "expected_interrupt", "expected_repeat"),
    [
        ("claude", "pty", "pty", 1),
        ("claude", "signal", "signal", None),
        ("claude", "auto", "pty", 1),
        ("codex", "auto", "signal", None),
        ("copilot", "auto", "pty", 2),
    ],
)
def test_cancel_task_interrupt_mode(
    profile: str,
    mode: str,
    expected_interrupt: str,
    expected_repeat: int | None,
):
    controller = _mock_controller(profile)
    client = _client_for_controller(controller, profile)
    task_id = _create_task(client)

    response = client.post(f"/tasks/{task_id}/cancel?mode={mode}")

    assert response.status_code == 200
    if expected_interrupt == "pty":
        controller.interrupt_via_pty.assert_called_once_with(repeat=expected_repeat)
        controller.interrupt.assert_not_called()
    else:
        controller.interrupt.assert_called_once_with()
        controller.interrupt_via_pty.assert_not_called()
