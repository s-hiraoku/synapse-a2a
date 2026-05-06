"""Tests for `synapse graph` task visualization (issue #609)."""

from argparse import Namespace
from pathlib import Path

from synapse.history import HistoryManager


def test_cmd_graph_outputs_mermaid_edges_for_sender_and_recipient(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    db_path = tmp_path / "history.db"
    manager = HistoryManager(str(db_path), enabled=True)
    manager.save_observation(
        task_id="task-1",
        agent_name="codex",
        session_id="session-1",
        input_text="Please review this",
        output_text="Reviewed",
        status="completed",
        metadata={
            "sender_id": "synapse-claude-8100",
            "recipient_id": "synapse-codex-8120",
        },
    )
    monkeypatch.setenv("SYNAPSE_HISTORY_DB_PATH", str(db_path))

    from synapse.commands.history import cmd_graph

    cmd_graph(Namespace(limit=50, format="mermaid"))

    output = capsys.readouterr().out
    assert "graph TD" in output
    assert '"synapse-claude-8100" --> "synapse-codex-8120"' in output
    assert "task-1" in output


def test_graph_help_is_available() -> None:
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-m", "synapse.cli", "graph", "--help"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "Visualize A2A task flow" in result.stdout
    assert "--format" in result.stdout
