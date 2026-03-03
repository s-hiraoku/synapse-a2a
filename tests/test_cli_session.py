"""Tests for CLI session commands (synapse/commands/session.py)."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest


def _make_args(**kwargs: Any) -> argparse.Namespace:
    """Build an argparse.Namespace with sensible defaults."""
    defaults = {
        "session_name": "test-session",
        "scope": None,
        "user": False,
        "project": False,
        "workdir": None,
        "force": False,
        "worktree": None,
        "tool_args": [],
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


@pytest.fixture()
def session_dirs(tmp_path: Path) -> tuple[Path, Path]:
    project = tmp_path / ".synapse" / "sessions"
    user = tmp_path / "home" / ".synapse" / "sessions"
    return project, user


def _fake_agents(working_dir: str) -> dict[str, dict]:
    """Return fake registry agents for testing."""
    return {
        "synapse-claude-8100": {
            "agent_id": "synapse-claude-8100",
            "agent_type": "claude",
            "port": 8100,
            "name": "Reviewer",
            "role": "code reviewer",
            "skill_set": "review-set",
            "working_dir": working_dir,
            "worktree_path": "/repo/.synapse/worktrees/rev",
        },
        "synapse-gemini-8110": {
            "agent_id": "synapse-gemini-8110",
            "agent_type": "gemini",
            "port": 8110,
            "name": "Gem",
            "role": None,
            "skill_set": None,
            "working_dir": working_dir,
        },
    }


# ── cmd_session_save ─────────────────────────────────────────


def test_save_filters_by_cwd(
    tmp_path: Path, session_dirs: tuple[Path, Path], capsys: pytest.CaptureFixture
) -> None:
    """save should only include agents whose working_dir matches CWD (--project)."""
    from synapse.commands.session import cmd_session_save

    cwd = str(tmp_path)
    agents = _fake_agents(cwd)
    # Add an agent in a different directory
    agents["synapse-codex-8120"] = {
        "agent_id": "synapse-codex-8120",
        "agent_type": "codex",
        "port": 8120,
        "name": "Coder",
        "role": None,
        "skill_set": None,
        "working_dir": "/other/project",
    }

    project_dir, user_dir = session_dirs
    args = _make_args(session_name="team")

    with (
        patch("synapse.commands.session.AgentRegistry") as MockReg,
        patch("synapse.commands.session.os.getcwd", return_value=cwd),
        patch(
            "synapse.commands.session._get_session_store",
            return_value=_make_store(project_dir, user_dir),
        ),
    ):
        MockReg.return_value.get_live_agents.return_value = agents
        cmd_session_save(args)

    # Verify saved session only has 2 agents (matching CWD)
    saved = json.loads((project_dir / "team.json").read_text())
    assert len(saved["agents"]) == 2
    profiles = {a["profile"] for a in saved["agents"]}
    assert profiles == {"claude", "gemini"}


def test_save_user_scope_captures_all(
    tmp_path: Path, session_dirs: tuple[Path, Path], capsys: pytest.CaptureFixture
) -> None:
    """save --user should capture all agents regardless of CWD."""
    from synapse.commands.session import cmd_session_save

    cwd = str(tmp_path)
    agents = _fake_agents(cwd)
    agents["synapse-codex-8120"] = {
        "agent_id": "synapse-codex-8120",
        "agent_type": "codex",
        "port": 8120,
        "working_dir": "/other/project",
    }

    project_dir, user_dir = session_dirs
    args = _make_args(session_name="all-agents", user=True)

    with (
        patch("synapse.commands.session.AgentRegistry") as MockReg,
        patch("synapse.commands.session.os.getcwd", return_value=cwd),
        patch(
            "synapse.commands.session._get_session_store",
            return_value=_make_store(project_dir, user_dir),
        ),
    ):
        MockReg.return_value.get_live_agents.return_value = agents
        cmd_session_save(args)

    saved = json.loads((user_dir / "all-agents.json").read_text())
    assert len(saved["agents"]) == 3


def test_save_no_agents_exits(tmp_path: Path, session_dirs: tuple[Path, Path]) -> None:
    """save should exit with error when no matching agents found."""
    from synapse.commands.session import cmd_session_save

    project_dir, user_dir = session_dirs
    args = _make_args(session_name="empty")

    with (
        patch("synapse.commands.session.AgentRegistry") as MockReg,
        patch("synapse.commands.session.os.getcwd", return_value=str(tmp_path)),
        patch(
            "synapse.commands.session._get_session_store",
            return_value=_make_store(project_dir, user_dir),
        ),
        pytest.raises(SystemExit, match="1"),
    ):
        MockReg.return_value.get_live_agents.return_value = {}
        cmd_session_save(args)


def test_save_workdir_filter(tmp_path: Path, session_dirs: tuple[Path, Path]) -> None:
    """save --workdir should filter by specified directory."""
    from synapse.commands.session import cmd_session_save

    target_dir = "/my/project"
    agents = _fake_agents(target_dir)
    agents["synapse-codex-8120"] = {
        "agent_id": "synapse-codex-8120",
        "agent_type": "codex",
        "port": 8120,
        "working_dir": "/other",
    }

    project_dir, user_dir = session_dirs
    args = _make_args(session_name="filtered", workdir=target_dir)

    with (
        patch("synapse.commands.session.AgentRegistry") as MockReg,
        patch("synapse.commands.session.os.getcwd", return_value=str(tmp_path)),
        patch(
            "synapse.commands.session._get_session_store",
            return_value=_make_store(project_dir, user_dir),
        ),
    ):
        MockReg.return_value.get_live_agents.return_value = agents
        cmd_session_save(args)

    saved = json.loads((project_dir / "filtered.json").read_text())
    assert len(saved["agents"]) == 2


def test_save_workdir_uses_workdir_project_store(tmp_path: Path) -> None:
    """save --workdir should build SessionStore rooted at that workdir."""
    from synapse.commands.session import cmd_session_save

    target_dir = tmp_path / "target"
    target_dir.mkdir(parents=True)
    args = _make_args(session_name="team", workdir=str(target_dir))
    agents = _fake_agents(str(target_dir))

    with (
        patch("synapse.commands.session.AgentRegistry") as MockReg,
        patch("synapse.commands.session.SessionStore") as MockStore,
    ):
        MockReg.return_value.get_live_agents.return_value = agents
        MockStore.return_value.save.return_value = (
            target_dir / ".synapse" / "sessions" / "team.json"
        )
        cmd_session_save(args)

    MockStore.assert_called_once_with(project_dir=target_dir / ".synapse" / "sessions")


# ── cmd_session_list ─────────────────────────────────────────


def test_list_shows_sessions(
    tmp_path: Path, session_dirs: tuple[Path, Path], capsys: pytest.CaptureFixture
) -> None:
    """list should display saved sessions."""
    from synapse.commands.session import cmd_session_list
    from synapse.session import Session, SessionAgent

    project_dir, user_dir = session_dirs
    store = _make_store(project_dir, user_dir)
    store.save(
        Session(
            session_name="team-a",
            agents=[SessionAgent(profile="claude"), SessionAgent(profile="gemini")],
            working_dir="/p",
            created_at=time.time(),
            scope="project",
        )
    )

    args = _make_args()
    with patch(
        "synapse.commands.session._get_session_store",
        return_value=store,
    ):
        cmd_session_list(args)

    captured = capsys.readouterr()
    assert "team-a" in captured.out
    assert "2" in captured.out  # agent count


def test_list_workdir_uses_workdir_project_store(tmp_path: Path) -> None:
    """list --workdir should read sessions from that workdir's project scope."""
    from synapse.commands.session import cmd_session_list

    target_dir = tmp_path / "target"
    target_dir.mkdir(parents=True)
    args = _make_args(workdir=str(target_dir))

    with patch("synapse.commands.session.SessionStore") as MockStore:
        MockStore.return_value.list_sessions.return_value = []
        cmd_session_list(args)

    MockStore.assert_called_once_with(project_dir=target_dir / ".synapse" / "sessions")


# ── cmd_session_show ─────────────────────────────────────────


def test_show_displays_details(
    tmp_path: Path, session_dirs: tuple[Path, Path], capsys: pytest.CaptureFixture
) -> None:
    """show should display session details."""
    from synapse.commands.session import cmd_session_show
    from synapse.session import Session, SessionAgent

    project_dir, user_dir = session_dirs
    store = _make_store(project_dir, user_dir)
    store.save(
        Session(
            session_name="detail",
            agents=[
                SessionAgent(
                    profile="claude", name="Rev", role="reviewer", skill_set="rs"
                )
            ],
            working_dir="/proj",
            created_at=1700000000.0,
            scope="project",
        )
    )

    args = _make_args(session_name="detail")
    with patch(
        "synapse.commands.session._get_session_store",
        return_value=store,
    ):
        cmd_session_show(args)

    captured = capsys.readouterr()
    assert "detail" in captured.out
    assert "claude" in captured.out
    assert "Rev" in captured.out


def test_show_not_found(tmp_path: Path, session_dirs: tuple[Path, Path]) -> None:
    """show should exit with error for non-existent session."""
    from synapse.commands.session import cmd_session_show

    project_dir, user_dir = session_dirs
    store = _make_store(project_dir, user_dir)
    args = _make_args(session_name="ghost")

    with (
        patch(
            "synapse.commands.session._get_session_store",
            return_value=store,
        ),
        pytest.raises(SystemExit, match="1"),
    ):
        cmd_session_show(args)


# ── cmd_session_delete ───────────────────────────────────────


def test_delete_removes_session(
    tmp_path: Path, session_dirs: tuple[Path, Path], capsys: pytest.CaptureFixture
) -> None:
    """delete should remove the session file."""
    from synapse.commands.session import cmd_session_delete
    from synapse.session import Session, SessionAgent

    project_dir, user_dir = session_dirs
    store = _make_store(project_dir, user_dir)
    store.save(
        Session(
            session_name="victim",
            agents=[SessionAgent(profile="claude")],
            working_dir="/p",
            created_at=time.time(),
            scope="project",
        )
    )

    args = _make_args(session_name="victim", force=True)
    with patch(
        "synapse.commands.session._get_session_store",
        return_value=store,
    ):
        cmd_session_delete(args)

    assert store.load("victim") is None


def test_delete_not_found(tmp_path: Path, session_dirs: tuple[Path, Path]) -> None:
    """delete should exit with error for non-existent session."""
    from synapse.commands.session import cmd_session_delete

    project_dir, user_dir = session_dirs
    store = _make_store(project_dir, user_dir)
    args = _make_args(session_name="ghost", force=True)

    with (
        patch(
            "synapse.commands.session._get_session_store",
            return_value=store,
        ),
        pytest.raises(SystemExit, match="1"),
    ):
        cmd_session_delete(args)


# ── cmd_session_restore ──────────────────────────────────────


def test_restore_calls_spawn_for_each_agent(
    tmp_path: Path, session_dirs: tuple[Path, Path], capsys: pytest.CaptureFixture
) -> None:
    """restore should call spawn_agent once per agent in session."""
    from synapse.commands.session import cmd_session_restore
    from synapse.session import Session, SessionAgent
    from synapse.spawn import SpawnResult

    project_dir, user_dir = session_dirs
    store = _make_store(project_dir, user_dir)
    store.save(
        Session(
            session_name="team",
            agents=[
                SessionAgent(profile="claude", name="Rev", role="reviewer"),
                SessionAgent(profile="gemini", name="Gem"),
            ],
            working_dir="/p",
            created_at=time.time(),
            scope="project",
        )
    )

    mock_result = SpawnResult(
        agent_id="synapse-claude-8100",
        port=8100,
        terminal_used="tmux",
        status="submitted",
    )

    args = _make_args(session_name="team")
    with (
        patch(
            "synapse.commands.session._get_session_store",
            return_value=store,
        ),
        patch(
            "synapse.commands.session.spawn_agent", return_value=mock_result
        ) as mock_spawn,
    ):
        cmd_session_restore(args)

    assert mock_spawn.call_count == 2
    # First call: claude with name/role
    call_kwargs_0 = mock_spawn.call_args_list[0][1]
    assert call_kwargs_0["profile"] == "claude"
    assert call_kwargs_0["name"] == "Rev"
    assert call_kwargs_0["role"] == "reviewer"
    # Second call: gemini
    call_kwargs_1 = mock_spawn.call_args_list[1][1]
    assert call_kwargs_1["profile"] == "gemini"
    assert call_kwargs_1["name"] == "Gem"


def test_restore_with_worktree_flag(
    tmp_path: Path, session_dirs: tuple[Path, Path], capsys: pytest.CaptureFixture
) -> None:
    """restore --worktree should pass worktree=True to all agents."""
    from synapse.commands.session import cmd_session_restore
    from synapse.session import Session, SessionAgent
    from synapse.spawn import SpawnResult

    project_dir, user_dir = session_dirs
    store = _make_store(project_dir, user_dir)
    store.save(
        Session(
            session_name="wt-team",
            agents=[
                SessionAgent(profile="claude", worktree=False),
                SessionAgent(profile="gemini", worktree=True),
            ],
            working_dir="/p",
            created_at=time.time(),
            scope="project",
        )
    )

    mock_result = SpawnResult(
        agent_id="synapse-claude-8100",
        port=8100,
        terminal_used="tmux",
        status="submitted",
    )

    # --worktree flag applies to ALL agents
    args = _make_args(session_name="wt-team", worktree=True)
    with (
        patch(
            "synapse.commands.session._get_session_store",
            return_value=store,
        ),
        patch(
            "synapse.commands.session.spawn_agent", return_value=mock_result
        ) as mock_spawn,
    ):
        cmd_session_restore(args)

    # Both agents should have worktree=True
    for call in mock_spawn.call_args_list:
        assert call[1]["worktree"] is True


def test_restore_preserves_session_worktree(
    tmp_path: Path, session_dirs: tuple[Path, Path], capsys: pytest.CaptureFixture
) -> None:
    """restore without --worktree should use each agent's saved worktree value."""
    from synapse.commands.session import cmd_session_restore
    from synapse.session import Session, SessionAgent
    from synapse.spawn import SpawnResult

    project_dir, user_dir = session_dirs
    store = _make_store(project_dir, user_dir)
    store.save(
        Session(
            session_name="mixed",
            agents=[
                SessionAgent(profile="claude", worktree=True),
                SessionAgent(profile="gemini", worktree=False),
            ],
            working_dir="/p",
            created_at=time.time(),
            scope="project",
        )
    )

    mock_result = SpawnResult(
        agent_id="synapse-claude-8100",
        port=8100,
        terminal_used="tmux",
        status="submitted",
    )

    args = _make_args(session_name="mixed")
    with (
        patch(
            "synapse.commands.session._get_session_store",
            return_value=store,
        ),
        patch(
            "synapse.commands.session.spawn_agent", return_value=mock_result
        ) as mock_spawn,
    ):
        cmd_session_restore(args)

    # Claude has worktree=True, Gemini has worktree=False
    assert mock_spawn.call_args_list[0][1]["worktree"] is True
    assert mock_spawn.call_args_list[1][1]["worktree"] is False


def test_restore_with_tool_args(
    tmp_path: Path, session_dirs: tuple[Path, Path], capsys: pytest.CaptureFixture
) -> None:
    """restore should pass tool_args to spawn_agent."""
    from synapse.commands.session import cmd_session_restore
    from synapse.session import Session, SessionAgent
    from synapse.spawn import SpawnResult

    project_dir, user_dir = session_dirs
    store = _make_store(project_dir, user_dir)
    store.save(
        Session(
            session_name="args-team",
            agents=[SessionAgent(profile="claude")],
            working_dir="/p",
            created_at=time.time(),
            scope="project",
        )
    )

    mock_result = SpawnResult(
        agent_id="synapse-claude-8100",
        port=8100,
        terminal_used="tmux",
        status="submitted",
    )

    args = _make_args(
        session_name="args-team",
        tool_args=["--dangerously-skip-permissions"],
    )
    with (
        patch(
            "synapse.commands.session._get_session_store",
            return_value=store,
        ),
        patch(
            "synapse.commands.session.spawn_agent", return_value=mock_result
        ) as mock_spawn,
    ):
        cmd_session_restore(args)

    assert mock_spawn.call_args_list[0][1]["tool_args"] == [
        "--dangerously-skip-permissions"
    ]


def test_restore_exits_nonzero_on_spawn_failure(
    tmp_path: Path, session_dirs: tuple[Path, Path]
) -> None:
    """restore should exit non-zero when any spawn fails."""
    from synapse.commands.session import cmd_session_restore
    from synapse.session import Session, SessionAgent

    project_dir, user_dir = session_dirs
    store = _make_store(project_dir, user_dir)
    store.save(
        Session(
            session_name="fail-team",
            agents=[
                SessionAgent(profile="claude", name="Good"),
                SessionAgent(profile="gemini", name="Bad"),
            ],
            working_dir="/p",
            created_at=time.time(),
            scope="project",
        )
    )

    from synapse.spawn import SpawnResult

    mock_result = SpawnResult(
        agent_id="synapse-claude-8100",
        port=8100,
        terminal_used="tmux",
        status="submitted",
    )

    call_count = 0

    def _side_effect(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise RuntimeError("spawn failed")
        return mock_result

    args = _make_args(session_name="fail-team")
    with (
        patch(
            "synapse.commands.session._get_session_store",
            return_value=store,
        ),
        patch("synapse.commands.session.spawn_agent", side_effect=_side_effect),
        pytest.raises(SystemExit, match="1"),
    ):
        cmd_session_restore(args)


# ── helpers ──────────────────────────────────────────────────


def _make_store(project_dir: Path, user_dir: Path):
    """Create a SessionStore with custom directories."""
    from synapse.session import SessionStore

    return SessionStore(project_dir=project_dir, user_dir=user_dir)


# ── cmd_session_restore with --resume ────────────────────


def test_restore_with_resume_flag(
    tmp_path: Path, session_dirs: tuple[Path, Path], capsys: pytest.CaptureFixture
) -> None:
    """--resume should build per-agent resume tool_args from session_id."""
    from synapse.commands.session import cmd_session_restore
    from synapse.session import Session, SessionAgent
    from synapse.spawn import SpawnResult

    project_dir, user_dir = session_dirs
    store = _make_store(project_dir, user_dir)
    store.save(
        Session(
            session_name="resume-team",
            agents=[
                SessionAgent(profile="claude", name="Rev", session_id="conv-abc"),
                SessionAgent(profile="gemini", session_id="gem-xyz"),
            ],
            working_dir="/p",
            created_at=time.time(),
            scope="project",
        )
    )

    mock_result = SpawnResult(
        agent_id="synapse-claude-8100",
        port=8100,
        terminal_used="tmux",
        status="submitted",
    )

    args = _make_args(session_name="resume-team", resume=True)
    with (
        patch(
            "synapse.commands.session._get_session_store",
            return_value=store,
        ),
        patch(
            "synapse.commands.session.spawn_agent", return_value=mock_result
        ) as mock_spawn,
    ):
        cmd_session_restore(args)

    assert mock_spawn.call_count == 2
    # Claude: --resume conv-abc prepended to tool_args
    call0 = mock_spawn.call_args_list[0][1]
    assert call0["tool_args"] == ["--resume", "conv-abc"]
    # Gemini: --resume gem-xyz prepended to tool_args
    call1 = mock_spawn.call_args_list[1][1]
    assert call1["tool_args"] == ["--resume", "gem-xyz"]


def test_restore_with_resume_flag_no_session_id(
    tmp_path: Path, session_dirs: tuple[Path, Path], capsys: pytest.CaptureFixture
) -> None:
    """--resume without session_id should fallback to latest resume."""
    from synapse.commands.session import cmd_session_restore
    from synapse.session import Session, SessionAgent
    from synapse.spawn import SpawnResult

    project_dir, user_dir = session_dirs
    store = _make_store(project_dir, user_dir)
    store.save(
        Session(
            session_name="no-id-team",
            agents=[
                SessionAgent(profile="claude", name="Rev"),  # no session_id
                SessionAgent(profile="gemini"),
            ],
            working_dir="/p",
            created_at=time.time(),
            scope="project",
        )
    )

    mock_result = SpawnResult(
        agent_id="synapse-claude-8100",
        port=8100,
        terminal_used="tmux",
        status="submitted",
    )

    args = _make_args(session_name="no-id-team", resume=True)
    with (
        patch(
            "synapse.commands.session._get_session_store",
            return_value=store,
        ),
        patch(
            "synapse.commands.session.spawn_agent", return_value=mock_result
        ) as mock_spawn,
    ):
        cmd_session_restore(args)

    # Claude: --continue (latest fallback)
    call0 = mock_spawn.call_args_list[0][1]
    assert call0["tool_args"] == ["--continue"]
    # Gemini: --resume (latest)
    call1 = mock_spawn.call_args_list[1][1]
    assert call1["tool_args"] == ["--resume"]


def test_restore_with_resume_and_tool_args(
    tmp_path: Path, session_dirs: tuple[Path, Path], capsys: pytest.CaptureFixture
) -> None:
    """--resume + global tool_args should merge resume args + tool_args."""
    from synapse.commands.session import cmd_session_restore
    from synapse.session import Session, SessionAgent
    from synapse.spawn import SpawnResult

    project_dir, user_dir = session_dirs
    store = _make_store(project_dir, user_dir)
    store.save(
        Session(
            session_name="merge-team",
            agents=[
                SessionAgent(profile="claude", session_id="conv-123"),
            ],
            working_dir="/p",
            created_at=time.time(),
            scope="project",
        )
    )

    mock_result = SpawnResult(
        agent_id="synapse-claude-8100",
        port=8100,
        terminal_used="tmux",
        status="submitted",
    )

    args = _make_args(
        session_name="merge-team",
        resume=True,
        tool_args=["--dangerously-skip-permissions"],
    )
    with (
        patch(
            "synapse.commands.session._get_session_store",
            return_value=store,
        ),
        patch(
            "synapse.commands.session.spawn_agent", return_value=mock_result
        ) as mock_spawn,
    ):
        cmd_session_restore(args)

    # resume args should come first, then global tool_args
    call0 = mock_spawn.call_args_list[0][1]
    assert call0["tool_args"] == [
        "--resume",
        "conv-123",
        "--dangerously-skip-permissions",
    ]


def test_restore_resume_passes_fallback_tool_args(
    tmp_path: Path, session_dirs: tuple[Path, Path], capsys: pytest.CaptureFixture
) -> None:
    """--resume should pass fallback_tool_args to spawn_agent."""
    from synapse.commands.session import cmd_session_restore
    from synapse.session import Session, SessionAgent
    from synapse.spawn import SpawnResult

    project_dir, user_dir = session_dirs
    store = _make_store(project_dir, user_dir)
    store.save(
        Session(
            session_name="fallback-team",
            agents=[
                SessionAgent(profile="claude", session_id="conv-abc"),
            ],
            working_dir="/p",
            created_at=time.time(),
            scope="project",
        )
    )

    mock_result = SpawnResult(
        agent_id="synapse-claude-8100",
        port=8100,
        terminal_used="tmux",
        status="submitted",
    )

    args = _make_args(
        session_name="fallback-team",
        resume=True,
        tool_args=["--dangerously-skip-permissions"],
    )
    with (
        patch(
            "synapse.commands.session._get_session_store",
            return_value=store,
        ),
        patch(
            "synapse.commands.session.spawn_agent", return_value=mock_result
        ) as mock_spawn,
    ):
        cmd_session_restore(args)

    call0 = mock_spawn.call_args_list[0][1]
    # fallback_tool_args = original tool_args (without resume args)
    assert call0["fallback_tool_args"] == ["--dangerously-skip-permissions"]


def test_restore_resume_opencode_skips_resume(
    tmp_path: Path, session_dirs: tuple[Path, Path], capsys: pytest.CaptureFixture
) -> None:
    """--resume with opencode should not add resume args (no support)."""
    from synapse.commands.session import cmd_session_restore
    from synapse.session import Session, SessionAgent
    from synapse.spawn import SpawnResult

    project_dir, user_dir = session_dirs
    store = _make_store(project_dir, user_dir)
    store.save(
        Session(
            session_name="oc-team",
            agents=[SessionAgent(profile="opencode")],
            working_dir="/p",
            created_at=time.time(),
            scope="project",
        )
    )

    mock_result = SpawnResult(
        agent_id="synapse-opencode-8130",
        port=8130,
        terminal_used="tmux",
        status="submitted",
    )

    args = _make_args(session_name="oc-team", resume=True)
    with (
        patch(
            "synapse.commands.session._get_session_store",
            return_value=store,
        ),
        patch(
            "synapse.commands.session.spawn_agent", return_value=mock_result
        ) as mock_spawn,
    ):
        cmd_session_restore(args)

    call0 = mock_spawn.call_args_list[0][1]
    # No resume args for opencode
    assert call0["tool_args"] is None
    # No fallback needed
    assert call0.get("fallback_tool_args") is None


def test_save_captures_session_id(
    tmp_path: Path, session_dirs: tuple[Path, Path], capsys: pytest.CaptureFixture
) -> None:
    """save should capture session_id from registry if available."""
    from synapse.commands.session import cmd_session_save

    cwd = str(tmp_path)
    agents = {
        "synapse-claude-8100": {
            "agent_id": "synapse-claude-8100",
            "agent_type": "claude",
            "port": 8100,
            "name": "Rev",
            "role": "reviewer",
            "skill_set": None,
            "working_dir": cwd,
            "session_id": "conv-abc-123",
        },
    }

    project_dir, user_dir = session_dirs
    args = _make_args(session_name="with-sid")

    with (
        patch("synapse.commands.session.AgentRegistry") as MockReg,
        patch("synapse.commands.session.os.getcwd", return_value=cwd),
        patch(
            "synapse.commands.session._get_session_store",
            return_value=_make_store(project_dir, user_dir),
        ),
    ):
        MockReg.return_value.get_live_agents.return_value = agents
        cmd_session_save(args)

    saved = json.loads((project_dir / "with-sid.json").read_text())
    assert saved["agents"][0]["session_id"] == "conv-abc-123"


def test_show_displays_session_id(
    tmp_path: Path, session_dirs: tuple[Path, Path], capsys: pytest.CaptureFixture
) -> None:
    """show should display session_id when present."""
    from synapse.commands.session import cmd_session_show
    from synapse.session import Session, SessionAgent

    project_dir, user_dir = session_dirs
    store = _make_store(project_dir, user_dir)
    store.save(
        Session(
            session_name="sid-show",
            agents=[SessionAgent(profile="claude", name="Rev", session_id="conv-abc")],
            working_dir="/p",
            created_at=1700000000.0,
            scope="project",
        )
    )

    args = _make_args(session_name="sid-show")
    with patch(
        "synapse.commands.session._get_session_store",
        return_value=store,
    ):
        cmd_session_show(args)

    captured = capsys.readouterr()
    assert "conv-abc" in captured.out
