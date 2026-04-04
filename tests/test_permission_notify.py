"""Tests for WAITING -> input_required permission notifications."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from synapse.a2a_compat import (
    Message,
    TextPart,
    create_a2a_router,
    map_synapse_status_to_a2a,
    task_store,
)


def _make_controller(context: str) -> MagicMock:
    controller = MagicMock()
    controller.status = "PROCESSING"
    controller.agent_ready = True
    controller.wait_until_ready.return_value = True
    controller.get_context.return_value = context
    controller.write.return_value = True
    return controller


def _register_status_callback(controller: MagicMock):
    router = create_a2a_router(
        controller,
        "codex",
        8120,
        "\n",
        agent_id="synapse-codex-8120",
    )
    assert router is not None
    return controller.on_status_change.call_args.args[0]


def _create_working_task():
    task = task_store.create(
        Message(parts=[TextPart(text="Run command")]),
        metadata={
            "response_mode": "notify",
            "sender": {
                "sender_id": "synapse-claude-8106",
                "sender_endpoint": "http://localhost:8106",
                "sender_task_id": "sender-task-1",
            },
        },
    )
    task_store.update_status(task.id, "working")
    return task


def test_map_waiting_to_input_required():
    assert map_synapse_status_to_a2a("WAITING") == "input_required"


def test_on_status_change_waiting_updates_working_tasks_to_input_required():
    controller = _make_controller("Allow Bash: rm -rf /tmp/test? [Y/n]")
    callback = _register_status_callback(controller)
    task = _create_working_task()

    callback("PROCESSING", "WAITING")

    updated = task_store.get(task.id)
    assert updated is not None
    assert updated.status == "input_required"


def test_on_status_change_waiting_sends_notification_to_sender():
    context = "Allow Bash: rm -rf /tmp/test? [Y/n]"
    controller = _make_controller(context)
    callback = _register_status_callback(controller)
    task = _create_working_task()

    with patch(
        "synapse.a2a_compat._send_response_to_sender",
        new_callable=AsyncMock,
    ) as mock_send:
        callback("PROCESSING", "WAITING")

    mock_send.assert_called_once()
    sent_task = mock_send.call_args.args[0]
    assert sent_task.status == "input_required"
    assert sent_task.artifacts
    artifact = sent_task.artifacts[0]
    text = artifact.data["content"]
    assert task.id in text
    assert "input_required" in text
    assert context in text
    assert f"http://localhost:8120/tasks/{task.id}/permission/approve" in text
    assert f"http://localhost:8120/tasks/{task.id}/permission/deny" in text


def test_on_status_change_waiting_adds_permission_metadata_to_task():
    context = "Allow Bash: rm -rf /tmp/test? [Y/n]"
    controller = _make_controller(context)
    callback = _register_status_callback(controller)
    task = _create_working_task()

    with patch(
        "synapse.a2a_compat._send_response_to_sender",
        new_callable=AsyncMock,
    ):
        callback("PROCESSING", "WAITING")

    updated = task_store.get(task.id)
    assert updated is not None
    permission = updated.metadata["permission"]
    assert permission["pty_context"] == context
    assert permission["agent_type"] == "codex"
    assert isinstance(permission["detected_at"], float)
