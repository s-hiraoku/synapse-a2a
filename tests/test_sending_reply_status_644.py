"""Tests for surfacing reply-send stalls as observable status (#644)."""

from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from synapse.a2a_client import A2ATask
from synapse.commands.status import StatusCommand
from synapse.history import HistoryManager
from synapse.status import (
    ALL_STATUSES,
    DONE,
    PROCESSING,
    RATE_LIMITED,
    READY,
    SHUTTING_DOWN,
    STATUS_STYLES,
    WAITING_FOR_INPUT,
)
from synapse.tools.a2a import cmd_reply, cmd_send


def _send_args() -> argparse.Namespace:
    return argparse.Namespace(
        target="claude",
        message="hello",
        priority=3,
        sender="synapse-codex-8121",
        response_mode="notify",
        force=True,
        local_only=False,
        attach=None,
    )


def _reply_args() -> argparse.Namespace:
    return argparse.Namespace(message="done", fail=None, to=None)


def _agent(status: str = PROCESSING) -> dict[str, object]:
    return {
        "agent_id": "synapse-claude-8104",
        "agent_type": "claude",
        "port": 8104,
        "pid": 1234,
        "endpoint": "http://localhost:8104",
        "status": status,
        "working_dir": str(Path.cwd()),
    }


def _sender(status: str = PROCESSING) -> dict[str, object]:
    return {
        "agent_id": "synapse-codex-8121",
        "agent_type": "codex",
        "port": 8121,
        "pid": 4321,
        "endpoint": "http://localhost:8121",
        "status": status,
        "working_dir": str(Path.cwd()),
    }


def _mock_registry(current_status: str) -> MagicMock:
    registry = MagicMock()
    registry.list_agents.return_value = {
        "synapse-claude-8104": _agent(),
        "synapse-codex-8121": _sender(current_status),
    }
    registry.get_agent.return_value = _sender(current_status)
    return registry


def _reply_stack_responses() -> list[MagicMock]:
    list_response = MagicMock(status_code=200)
    list_response.json.return_value = {
        "sender_ids": ["synapse-claude-8104"],
        "targets": [{"sender_id": "synapse-claude-8104"}],
    }
    get_response = MagicMock(status_code=200)
    get_response.json.return_value = {
        "sender_endpoint": "http://localhost:8104",
        "sender_task_id": "parent-task",
        "receiver_task_id": "child-task",
    }
    pop_response = MagicMock(status_code=200)
    return [list_response, get_response, pop_response]


def test_sending_reply_constant_exists_in_status_module() -> None:
    import synapse.status as status

    assert status.SENDING_REPLY == "SENDING_REPLY"
    assert status.SENDING_REPLY in ALL_STATUSES
    assert status.SENDING_REPLY in STATUS_STYLES


def test_send_toggles_status_to_sending_reply_during_post() -> None:
    registry = _mock_registry(PROCESSING)
    captured_statuses: list[str] = []

    def send_to_local(**_kwargs: object) -> A2ATask:
        captured_statuses.extend(
            call.args[1] for call in registry.update_status.mock_calls
        )
        return A2ATask(id="task-123", status="working")

    with (
        patch("synapse.tools.a2a.AgentRegistry", return_value=registry),
        patch("synapse.tools.a2a.is_process_running", return_value=True),
        patch("synapse.tools.a2a.is_port_open", return_value=True),
        patch(
            "synapse.tools.a2a.build_sender_info",
            return_value={"sender_id": "synapse-codex-8121"},
        ),
        patch("synapse.tools.a2a.A2AClient") as client_cls,
    ):
        client_cls.return_value.send_to_local.side_effect = send_to_local
        cmd_send(_send_args())

    assert captured_statuses == ["SENDING_REPLY"]
    assert ("synapse-codex-8121", PROCESSING) in [
        call.args for call in registry.update_status.call_args_list
    ]


def test_reply_toggles_status_to_sending_reply_during_post() -> None:
    registry = _mock_registry(WAITING_FOR_INPUT)
    captured_statuses: list[str] = []

    def send_to_local(**_kwargs: object) -> A2ATask:
        captured_statuses.extend(
            call.args[1] for call in registry.update_status.mock_calls
        )
        return A2ATask(id="reply-task", status="completed")

    local_reply_response = MagicMock(status_code=200)
    with (
        patch("synapse.tools.a2a.AgentRegistry", return_value=registry),
        patch(
            "synapse.tools.a2a.build_sender_info",
            return_value={
                "sender_id": "synapse-codex-8121",
                "sender_endpoint": "http://localhost:8121",
            },
        ),
        patch("synapse.tools.a2a.requests.get") as requests_get,
        patch("synapse.tools.a2a.requests.post", return_value=local_reply_response),
        patch("synapse.tools.a2a.clear_reply_target"),
        patch("synapse.tools.a2a.A2AClient") as client_cls,
    ):
        requests_get.side_effect = _reply_stack_responses()
        client_cls.return_value.send_to_local.side_effect = send_to_local
        cmd_reply(_reply_args())

    assert captured_statuses == ["SENDING_REPLY"]
    assert ("synapse-codex-8121", WAITING_FOR_INPUT) in [
        call.args for call in registry.update_status.call_args_list
    ]


@pytest.mark.parametrize("current_status", [DONE, SHUTTING_DOWN, RATE_LIMITED])
def test_sending_reply_does_not_overwrite_terminal_status(current_status: str) -> None:
    registry = _mock_registry(current_status)

    with (
        patch("synapse.tools.a2a.AgentRegistry", return_value=registry),
        patch("synapse.tools.a2a.is_process_running", return_value=True),
        patch("synapse.tools.a2a.is_port_open", return_value=True),
        patch(
            "synapse.tools.a2a.build_sender_info",
            return_value={"sender_id": "synapse-codex-8121"},
        ),
        patch("synapse.tools.a2a.A2AClient") as client_cls,
    ):
        client_cls.return_value.send_to_local.return_value = A2ATask(
            id="task-123", status="working"
        )
        cmd_send(_send_args())

    assert ("synapse-codex-8121", "SENDING_REPLY") not in [
        call.args for call in registry.update_status.call_args_list
    ]


def test_sending_reply_restores_status_on_http_failure() -> None:
    registry = _mock_registry(READY)

    with (
        patch("synapse.tools.a2a.AgentRegistry", return_value=registry),
        patch("synapse.tools.a2a.is_process_running", return_value=True),
        patch("synapse.tools.a2a.is_port_open", return_value=True),
        patch(
            "synapse.tools.a2a.build_sender_info",
            return_value={"sender_id": "synapse-codex-8121"},
        ),
        patch("synapse.tools.a2a.A2AClient") as client_cls,
    ):
        client_cls.return_value.send_to_local.return_value = None
        with pytest.raises(SystemExit):
            cmd_send(_send_args())

    assert registry.update_status.call_args_list[-1].args == (
        "synapse-codex-8121",
        READY,
    )


def _history(tmp_path: Path) -> HistoryManager:
    return HistoryManager(str(tmp_path / "history.db"))


def _save_history(
    history: HistoryManager,
    *,
    task_id: str,
    metadata: dict[str, object],
    agent_name: str = "codex",
) -> None:
    history.save_observation(
        task_id=task_id,
        agent_name=agent_name,
        session_id="test",
        input_text=f"input {task_id}",
        output_text=f"output {task_id}",
        status="completed",
        metadata=metadata,
    )


def test_recent_messages_filtered_by_sender_or_recipient(tmp_path: Path) -> None:
    history = _history(tmp_path)
    _save_history(
        history,
        task_id="task-a-out",
        metadata={"sender": {"sender_id": "synapse-codex-8121"}},
    )
    _save_history(
        history,
        task_id="task-b-internal",
        metadata={
            "sender": {"sender_id": "synapse-codex-8122"},
            "target_agent_id": "synapse-codex-8123",
        },
    )

    messages = StatusCommand(MagicMock(), history_manager=history)._get_history(
        {"agent_id": "synapse-codex-8121", "agent_type": "codex"}
    )

    assert [message["task_id"] for message in messages] == ["task-a-out"]


def test_recent_messages_includes_both_inbound_and_outbound_for_target(
    tmp_path: Path,
) -> None:
    history = _history(tmp_path)
    _save_history(
        history,
        task_id="outbound",
        metadata={"sender": {"sender_id": "synapse-codex-8121"}},
    )
    _save_history(
        history,
        task_id="inbound",
        metadata={
            "sender": {"sender_id": "synapse-claude-8104"},
            "target_agent_id": "synapse-codex-8121",
        },
    )

    messages = StatusCommand(MagicMock(), history_manager=history)._get_history(
        {"agent_id": "synapse-codex-8121", "agent_type": "codex"}
    )

    assert {message["task_id"] for message in messages} == {"outbound", "inbound"}


def test_recent_messages_empty_when_no_match(tmp_path: Path) -> None:
    history = _history(tmp_path)
    _save_history(
        history,
        task_id="other",
        metadata={
            "sender": {"sender_id": "synapse-claude-8104"},
            "target_agent_id": "synapse-gemini-8110",
        },
    )

    messages = StatusCommand(MagicMock(), history_manager=history)._get_history(
        {"agent_id": "synapse-codex-8121", "agent_type": "codex"}
    )

    assert messages == []
