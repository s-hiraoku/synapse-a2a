"""Regression tests for parent-side sent-message history output (#660)."""

from pathlib import Path
from unittest.mock import patch

from synapse.a2a_compat import Artifact, _format_artifact_text
from synapse.history import HistoryManager
from synapse.tools.a2a_helpers import _record_sent_message


def _history_manager(tmp_path: Path) -> HistoryManager:
    return HistoryManager(db_path=str(tmp_path / "history.db"))


def _record_parent_send(history: HistoryManager) -> dict:
    target_agent = {
        "agent_id": "synapse-codex-8124",
        "agent_type": "codex",
    }

    with patch("synapse.tools.a2a_helpers._get_history_manager", return_value=history):
        _record_sent_message(
            task_id="task-660",
            target_agent=target_agent,
            message="implement issue 660",
            priority=3,
            sender_info={
                "sender_id": "synapse-claude-8104",
                "sender_type": "claude",
                "sender_endpoint": "http://localhost:8104",
            },
        )

    observations = history.list_observations(limit=1)
    assert len(observations) == 1
    return observations[0]


def test_send_observation_uses_empty_output_text(tmp_path: Path):
    observation = _record_parent_send(_history_manager(tmp_path))

    assert observation["output"] == ""


def test_send_observation_metadata_marks_send_placeholder(tmp_path: Path):
    observation = _record_parent_send(_history_manager(tmp_path))

    assert observation["metadata"]["output_kind"] == "send_placeholder"


def test_send_observation_preserves_input_text_format(tmp_path: Path):
    observation = _record_parent_send(_history_manager(tmp_path))

    assert observation["input"] == "@codex implement issue 660"


def test_send_observation_preserves_target_agent_id_in_metadata(tmp_path: Path):
    observation = _record_parent_send(_history_manager(tmp_path))

    assert observation["metadata"]["target_agent_id"] == "synapse-codex-8124"


def test_task_artifact_output_formatting_remains_unchanged():
    artifact = Artifact(type="text", data={"content": "raw PTY remnant"})

    assert _format_artifact_text(artifact) == "raw PTY remnant"
