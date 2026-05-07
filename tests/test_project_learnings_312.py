"""Tests for project-adaptive agent learnings (#312)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock


def test_append_project_learning_uses_agent_definition_id(tmp_path: Path) -> None:
    """Learnings should be stored under .synapse/learnings/<definition-id>.md."""
    from synapse.learnings import append_project_learning, load_project_learnings

    path = append_project_learning(
        "wise-strategist",
        "Freeze time when testing token expiry.",
        project_root=tmp_path,
    )

    assert path == tmp_path / ".synapse" / "learnings" / "wise-strategist.md"
    assert "Freeze time" in load_project_learnings(
        "wise-strategist",
        project_root=tmp_path,
    )


def test_append_project_learning_compacts_to_max_lines(tmp_path: Path) -> None:
    """Oversized learning files should keep the newest compact set of lines."""
    from synapse.learnings import append_project_learning

    for index in range(5):
        append_project_learning(
            "wise-strategist",
            f"Learning {index}",
            project_root=tmp_path,
            max_lines=3,
        )

    lines = (
        (tmp_path / ".synapse" / "learnings" / "wise-strategist.md")
        .read_text(encoding="utf-8")
        .splitlines()
    )

    assert len(lines) == 3
    assert "Learning 4" in lines[-1]


def test_identity_message_includes_saved_agent_learnings(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Initial instructions should include learnings for the saved agent ID."""
    from synapse.controller import TerminalController
    from synapse.learnings import append_project_learning

    monkeypatch.chdir(tmp_path)
    append_project_learning(
        "wise-strategist",
        "Run uv tests before reporting completion.",
        project_root=tmp_path,
    )
    registry = Mock()
    registry.get_live_agents.return_value = {}
    ctrl = TerminalController(
        command="echo test",
        idle_regex=r"\$",
        registry=registry,
        agent_id="synapse-claude-8100",
        agent_type="claude",
        submit_seq="\r",
        agent_definition_id="wise-strategist",
        port=8100,
    )

    message = ctrl._build_identity_message([".synapse/default.md"])

    assert "Project learnings for wise-strategist" in message
    assert "Run uv tests before reporting completion." in message
