"""Regression tests for permission notification context and dedupe."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from synapse.a2a_compat import Message, TextPart, create_a2a_router, task_store


class _Controller:
    def __init__(self, context: str = "", rendered_context: str | None = None) -> None:
        self.context = context
        self.rendered_context = rendered_context
        self.status = "PROCESSING"
        self.agent_ready = True
        self.callback = None

    def wait_until_ready(self, timeout: float | None = None) -> bool:
        return True

    def get_context(self) -> str:
        return self.context

    def get_rendered_context(self) -> str:
        if self.rendered_context is None:
            raise AttributeError("rendered context unavailable")
        return self.rendered_context

    def write(self, text: str) -> bool:
        return True

    def on_status_change(self, callback) -> None:
        self.callback = callback


def _register_status_callback(controller: _Controller):
    router = create_a2a_router(
        controller,
        "codex",
        8120,
        "\n",
        agent_id="synapse-codex-8120",
    )
    assert router is not None
    assert controller.callback is not None
    return controller.callback


def _create_working_task(
    *,
    current_task_preview: str | None = None,
    sent_message: str | None = None,
):
    metadata = {
        "response_mode": "notify",
        "sender": {
            "sender_id": "synapse-claude-8106",
            "sender_endpoint": "http://localhost:8106",
            "sender_task_id": "sender-task-1",
        },
    }
    if current_task_preview is not None:
        metadata["current_task_preview"] = current_task_preview
    if sent_message is not None:
        metadata["_sent_message"] = sent_message
    task = task_store.create(
        Message(parts=[TextPart(text="Run command")]),
        metadata=metadata,
    )
    task_store.update_status(task.id, "working")
    return task


def _permission_context(task_id: str) -> str:
    task = task_store.get(task_id)
    assert task is not None
    return task.metadata["permission"]["pty_context"]


def _emit_waiting(callback, *, now: float = 1000.0) -> AsyncMock:
    with (
        patch("synapse.a2a_compat.time.time", return_value=now),
        patch(
            "synapse.a2a_compat._send_response_to_sender",
            new_callable=AsyncMock,
        ) as mock_send,
    ):
        callback("PROCESSING", "WAITING")
    return mock_send


def test_pty_context_stripped_of_ansi_sequences():
    raw = "\x1b[31mAllow Bash\x1b[0m\r\n\x1b[2K1. Yes, proceed"
    controller = _Controller(raw)
    callback = _register_status_callback(controller)
    task = _create_working_task()

    _emit_waiting(callback)

    context = _permission_context(task.id)
    assert "\x1b[" not in context
    assert "\r" not in context
    assert "Allow Bash" in context
    assert "1. Yes, proceed" in context


def test_pty_context_truncation_does_not_leave_mid_ansi():
    raw = "A" * 520 + "\x1b[31mAllow Bash\x1b[0m\n1. Yes, proceed"
    controller = _Controller(raw)
    callback = _register_status_callback(controller)
    task = _create_working_task()

    _emit_waiting(callback)

    context = _permission_context(task.id)
    assert "\x1b[" not in context
    assert not context.startswith("[31m")
    assert "Allow Bash" in context


def test_notification_fallback_to_task_preview_when_context_empty():
    controller = _Controller("")
    callback = _register_status_callback(controller)
    task = _create_working_task(current_task_preview="Approve shell command")

    _emit_waiting(callback)

    assert _permission_context(task.id) == "Approve shell command"


def test_notification_fallback_to_sent_message_when_context_still_empty():
    controller = _Controller("")
    callback = _register_status_callback(controller)
    task = _create_working_task(sent_message="Run pytest for permission workflow")

    _emit_waiting(callback)

    assert _permission_context(task.id) == "Run pytest for permission workflow"


def test_notification_placeholder_when_all_fallbacks_empty():
    controller = _Controller("")
    callback = _register_status_callback(controller)
    task = _create_working_task()

    _emit_waiting(callback)

    assert _permission_context(task.id) == "[permission context unavailable]"


def test_permission_notification_dedup_by_hash_within_window():
    controller = _Controller("Allow Bash\n1. Yes, proceed")
    callback = _register_status_callback(controller)
    task = _create_working_task()

    first_send = _emit_waiting(callback, now=1000.0)
    callback("WAITING", "READY")
    second_send = _emit_waiting(callback, now=1001.0)

    first_send.assert_called_once()
    second_send.assert_not_called()
    updated = task_store.get(task.id)
    assert updated is not None
    assert updated.metadata["permission"]["notifications_sent"] == 1


def test_permission_notification_dedup_by_time_even_when_hash_differs():
    controller = _Controller("Allow Bash\n1. Yes, proceed")
    callback = _register_status_callback(controller)
    task = _create_working_task()

    first_send = _emit_waiting(callback, now=1000.0)
    callback("WAITING", "READY")
    controller.context = "Allow Read\n1. Yes, proceed"
    second_send = _emit_waiting(callback, now=1002.0)

    first_send.assert_called_once()
    second_send.assert_not_called()
    updated = task_store.get(task.id)
    assert updated is not None
    assert updated.metadata["permission"]["notifications_sent"] == 1


def test_permission_notification_counter_increments_once_per_emit():
    controller = _Controller("Allow Bash\n1. Yes, proceed")
    callback = _register_status_callback(controller)
    task = _create_working_task()

    _emit_waiting(callback, now=1000.0)

    updated = task_store.get(task.id)
    assert updated is not None
    assert updated.metadata["permission"]["notifications_sent"] == 1


def test_permission_notification_reemits_after_window_expires():
    controller = _Controller("Allow Bash\n1. Yes, proceed")
    callback = _register_status_callback(controller)
    task = _create_working_task()

    first_send = _emit_waiting(callback, now=1000.0)
    callback("WAITING", "READY")
    controller.context = "Allow Read\n1. Yes, proceed"
    second_send = _emit_waiting(callback, now=1006.0)

    first_send.assert_called_once()
    second_send.assert_called_once()
    updated = task_store.get(task.id)
    assert updated is not None
    assert updated.metadata["permission"]["notifications_sent"] == 2


@pytest.mark.parametrize(
    "context",
    [
        "\x1b[31mred\x1b[0m",
        "\x00\x01\x02Allow Bash\x7f",
    ],
)
def test_permission_context_removes_residual_control_bytes(context: str):
    controller = _Controller(context)
    callback = _register_status_callback(controller)
    task = _create_working_task()

    _emit_waiting(callback)

    sanitized = _permission_context(task.id)
    assert "\x1b[" not in sanitized
    assert "\x00" not in sanitized
    assert "\x7f" not in sanitized
