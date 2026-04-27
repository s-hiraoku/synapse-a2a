"""Regression tests for status recent message history (#659)."""

from pathlib import Path

import pytest

from synapse.commands.status import StatusCommand
from synapse.history import HistoryManager

TARGET_AGENT_ID = "synapse-codex-8121"


@pytest.fixture
def history_manager(tmp_path: Path) -> HistoryManager:
    return HistoryManager(db_path=str(tmp_path / "history.db"))


@pytest.fixture
def status_command(history_manager: HistoryManager) -> StatusCommand:
    return StatusCommand(registry=None, history_manager=history_manager)  # type: ignore[arg-type]


def _save_observation(
    history_manager: HistoryManager,
    *,
    task_id: str,
    agent_name: str,
    input_text: str,
    metadata: dict[str, object] | None = None,
) -> None:
    history_manager.save_observation(
        task_id=task_id,
        agent_name=agent_name,
        session_id=f"session-{task_id}",
        input_text=input_text,
        output_text="done",
        status="completed",
        metadata=metadata,
    )


def _task_ids(observations: list[dict[str, object]]) -> set[str]:
    return {str(observation["task_id"]) for observation in observations}


def test_get_history_includes_parent_side_send_observation(
    history_manager: HistoryManager, status_command: StatusCommand
) -> None:
    _save_observation(
        history_manager,
        task_id="parent-send",
        agent_name="claude",
        input_text="synapse send codex fix bug",
        metadata={"target_agent_id": TARGET_AGENT_ID},
    )
    _save_observation(
        history_manager,
        task_id="child-task",
        agent_name="codex",
        input_text="fix bug",
        metadata={"recipient_agent_id": TARGET_AGENT_ID},
    )

    observations = status_command._get_history(
        {"agent_id": TARGET_AGENT_ID, "agent_type": "codex"}
    )

    assert _task_ids(observations) == {"parent-send", "child-task"}


def test_get_history_includes_child_reply_observation(
    history_manager: HistoryManager, status_command: StatusCommand
) -> None:
    _save_observation(
        history_manager,
        task_id="child-reply",
        agent_name="codex",
        input_text="reply complete",
        metadata={"sender": {"sender_id": TARGET_AGENT_ID}},
    )

    observations = status_command._get_history(
        {"agent_id": TARGET_AGENT_ID, "agent_type": "codex"}
    )

    assert _task_ids(observations) == {"child-reply"}


def test_get_history_excludes_unrelated_agents(
    history_manager: HistoryManager, status_command: StatusCommand
) -> None:
    _save_observation(
        history_manager,
        task_id="target-send",
        agent_name="claude",
        input_text="targeted send",
        metadata={"target_agent_id": TARGET_AGENT_ID},
    )
    _save_observation(
        history_manager,
        task_id="other-send",
        agent_name="claude",
        input_text="unrelated send",
        metadata={"target_agent_id": "synapse-codex-8122"},
    )
    _save_observation(
        history_manager,
        task_id="probe-leftover",
        agent_name="hello",
        input_text="hello",
        metadata={"sender_id": "synapse-codex-8122"},
    )

    observations = status_command._get_history(
        {"agent_id": TARGET_AGENT_ID, "agent_type": "codex"}
    )

    assert _task_ids(observations) == {"target-send"}


def test_get_history_falls_back_to_agent_name_when_no_agent_id(
    history_manager: HistoryManager, status_command: StatusCommand
) -> None:
    _save_observation(
        history_manager,
        task_id="legacy-codex",
        agent_name="codex",
        input_text="legacy codex message",
        metadata={"target_agent_id": "synapse-codex-8122"},
    )
    _save_observation(
        history_manager,
        task_id="parent-send",
        agent_name="claude",
        input_text="parent side send",
        metadata={"target_agent_id": TARGET_AGENT_ID},
    )

    observations = status_command._get_history({"agent_type": "codex"})

    assert _task_ids(observations) == {"legacy-codex"}


def test_get_history_handles_empty_history_gracefully(
    status_command: StatusCommand,
) -> None:
    assert (
        status_command._get_history(
            {"agent_id": TARGET_AGENT_ID, "agent_type": "codex"}
        )
        == []
    )
