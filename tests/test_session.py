"""Tests for SessionStore core (synapse/session.py)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest


@pytest.fixture()
def session_dirs(tmp_path: Path) -> tuple[Path, Path]:
    """Return (project_dir, user_dir) under tmp_path."""
    project = tmp_path / "project" / ".synapse" / "sessions"
    user = tmp_path / "home" / ".synapse" / "sessions"
    return project, user


@pytest.fixture()
def store(session_dirs: tuple[Path, Path]):
    from synapse.session import SessionStore

    project_dir, user_dir = session_dirs
    return SessionStore(project_dir=project_dir, user_dir=user_dir)


# ── save / load round-trip ──────────────────────────────────


def test_save_and_load_roundtrip(store) -> None:
    """Saving a session and loading it back should preserve all fields."""
    from synapse.session import Session, SessionAgent

    agents = [
        SessionAgent(profile="claude", name="Reviewer", role="code reviewer"),
        SessionAgent(profile="gemini", name="Gem"),
    ]
    session = Session(
        session_name="review-team",
        agents=agents,
        working_dir="/path/to/project",
        created_at=time.time(),
        scope="project",
    )
    store.save(session)
    loaded = store.load("review-team")
    assert loaded is not None
    assert loaded.session_name == "review-team"
    assert loaded.agent_count == 2
    assert len(loaded.agents) == 2
    assert loaded.agents[0].profile == "claude"
    assert loaded.agents[0].name == "Reviewer"
    assert loaded.agents[0].role == "code reviewer"
    assert loaded.agents[1].profile == "gemini"
    assert loaded.agents[1].name == "Gem"
    assert loaded.agents[1].role is None
    assert loaded.working_dir == "/path/to/project"
    assert loaded.scope == "project"


def test_save_creates_directory(store, session_dirs: tuple[Path, Path]) -> None:
    """save() should create session directory if it doesn't exist."""
    from synapse.session import Session, SessionAgent

    project_dir, _ = session_dirs
    assert not project_dir.exists()
    session = Session(
        session_name="test",
        agents=[SessionAgent(profile="claude")],
        working_dir="/tmp",
        created_at=time.time(),
        scope="project",
    )
    store.save(session)
    assert project_dir.exists()
    assert (project_dir / "test.json").exists()


def test_save_with_all_agent_fields(store) -> None:
    """All SessionAgent fields should survive serialization."""
    from synapse.session import Session, SessionAgent

    agent = SessionAgent(
        profile="claude",
        name="Worker",
        role="implementer",
        skill_set="dev-set",
        worktree=True,
    )
    session = Session(
        session_name="full",
        agents=[agent],
        working_dir="/project",
        created_at=1700000000.0,
        scope="user",
    )
    store.save(session)
    loaded = store.load("full", scope="user")
    assert loaded is not None
    a = loaded.agents[0]
    assert a.profile == "claude"
    assert a.name == "Worker"
    assert a.role == "implementer"
    assert a.skill_set == "dev-set"
    assert a.worktree is True


# ── upsert (overwrite same name) ────────────────────────────


def test_save_overwrites_existing(store) -> None:
    """Saving with the same name should overwrite (upsert)."""
    from synapse.session import Session, SessionAgent

    s1 = Session(
        session_name="team",
        agents=[SessionAgent(profile="claude")],
        working_dir="/v1",
        created_at=1000.0,
        scope="project",
    )
    store.save(s1)
    s2 = Session(
        session_name="team",
        agents=[
            SessionAgent(profile="claude"),
            SessionAgent(profile="gemini"),
        ],
        working_dir="/v2",
        created_at=2000.0,
        scope="project",
    )
    store.save(s2)
    loaded = store.load("team")
    assert loaded is not None
    assert loaded.agent_count == 2
    assert loaded.working_dir == "/v2"


# ── list (scope filtering) ──────────────────────────────────


def test_list_project_scope(store) -> None:
    """list_sessions('project') returns only project sessions."""
    from synapse.session import Session, SessionAgent

    store.save(
        Session(
            session_name="proj",
            agents=[SessionAgent(profile="claude")],
            working_dir="/p",
            created_at=time.time(),
            scope="project",
        )
    )
    store.save(
        Session(
            session_name="usr",
            agents=[SessionAgent(profile="gemini")],
            working_dir="/u",
            created_at=time.time(),
            scope="user",
        )
    )
    sessions = store.list_sessions(scope="project")
    names = [s.session_name for s in sessions]
    assert "proj" in names
    assert "usr" not in names


def test_list_user_scope(store) -> None:
    """list_sessions('user') returns only user sessions."""
    from synapse.session import Session, SessionAgent

    store.save(
        Session(
            session_name="usr",
            agents=[SessionAgent(profile="gemini")],
            working_dir="/u",
            created_at=time.time(),
            scope="user",
        )
    )
    sessions = store.list_sessions(scope="user")
    assert len(sessions) == 1
    assert sessions[0].session_name == "usr"


def test_list_both_scopes(store) -> None:
    """list_sessions(scope=None) returns merged results from both scopes."""
    from synapse.session import Session, SessionAgent

    store.save(
        Session(
            session_name="proj",
            agents=[SessionAgent(profile="claude")],
            working_dir="/p",
            created_at=time.time(),
            scope="project",
        )
    )
    store.save(
        Session(
            session_name="usr",
            agents=[SessionAgent(profile="gemini")],
            working_dir="/u",
            created_at=time.time(),
            scope="user",
        )
    )
    sessions = store.list_sessions(scope=None)
    names = [s.session_name for s in sessions]
    assert "proj" in names
    assert "usr" in names


def test_list_empty(store) -> None:
    """list_sessions on empty store returns empty list."""
    assert store.list_sessions(scope="project") == []
    assert store.list_sessions(scope="user") == []
    assert store.list_sessions(scope=None) == []


# ── delete ───────────────────────────────────────────────────


def test_delete_existing(store) -> None:
    """Deleting an existing session returns True."""
    from synapse.session import Session, SessionAgent

    store.save(
        Session(
            session_name="victim",
            agents=[SessionAgent(profile="claude")],
            working_dir="/p",
            created_at=time.time(),
            scope="project",
        )
    )
    assert store.delete("victim", scope="project") is True
    assert store.load("victim", scope="project") is None


def test_delete_nonexistent(store) -> None:
    """Deleting a non-existent session returns False."""
    assert store.delete("ghost", scope="project") is False


def test_delete_user_scope(store) -> None:
    """delete respects scope parameter."""
    from synapse.session import Session, SessionAgent

    store.save(
        Session(
            session_name="usr-session",
            agents=[SessionAgent(profile="codex")],
            working_dir="/u",
            created_at=time.time(),
            scope="user",
        )
    )
    # Should not find in project scope
    assert store.delete("usr-session", scope="project") is False
    # Should find in user scope
    assert store.delete("usr-session", scope="user") is True


# ── name validation ──────────────────────────────────────────


def test_valid_session_names(store) -> None:
    """Valid names should pass validation."""
    from synapse.session import SessionStore

    for name in ["review-team", "my.session", "test_123", "A-b.C_d"]:
        SessionStore._validate_session_name(name)  # Should not raise


def test_invalid_session_names() -> None:
    """Invalid names should raise SessionError."""
    from synapse.session import SessionError, SessionStore

    invalid_names = [
        "",  # empty
        "-start",  # starts with dash
        ".dotstart",  # starts with dot
        "has space",
        "has/slash",
        "../traversal",
    ]
    for name in invalid_names:
        with pytest.raises(SessionError, match="Invalid session name"):
            SessionStore._validate_session_name(name)


# ── path traversal prevention ────────────────────────────────


def test_load_rejects_traversal(store) -> None:
    """load() should reject path-traversal names."""
    from synapse.session import SessionError

    for bad_name in ["../escape", "../../etc", "has/slash"]:
        with pytest.raises(SessionError, match="Invalid session name"):
            store.load(bad_name)


def test_delete_rejects_traversal(store) -> None:
    """delete() should reject path-traversal names."""
    from synapse.session import SessionError

    for bad_name in ["../escape", "../../etc", "has/slash"]:
        with pytest.raises(SessionError, match="Invalid session name"):
            store.delete(bad_name)


def test_resolve_scope_filter_workdir_maps_to_project_scope() -> None:
    """--workdir should resolve to project scope with a directory override."""
    from argparse import Namespace

    from synapse.session import resolve_scope_filter

    scope, workdir = resolve_scope_filter(
        Namespace(user=False, project=False, workdir="/tmp/work")
    )
    assert scope == "project"
    assert workdir == "/tmp/work"


# ── broken JSON handling ─────────────────────────────────────


def test_list_skips_broken_json(store, session_dirs: tuple[Path, Path]) -> None:
    """Broken JSON files should be skipped with a warning, not crash."""
    from synapse.session import Session, SessionAgent

    project_dir, _ = session_dirs
    # Save a valid session
    store.save(
        Session(
            session_name="valid",
            agents=[SessionAgent(profile="claude")],
            working_dir="/p",
            created_at=time.time(),
            scope="project",
        )
    )
    # Write a broken JSON file manually
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "broken.json").write_text("{invalid json!!!", encoding="utf-8")

    sessions = store.list_sessions(scope="project")
    names = [s.session_name for s in sessions]
    assert "valid" in names
    assert len(sessions) == 1  # broken file skipped


def test_load_broken_json_returns_none(store, session_dirs: tuple[Path, Path]) -> None:
    """Loading a broken JSON file should return None."""
    project_dir, _ = session_dirs
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "broken.json").write_text("not json", encoding="utf-8")
    assert store.load("broken", scope="project") is None


# ── load with auto-scope resolution ─────────────────────────


def test_load_auto_scope_project_first(store) -> None:
    """load() without scope should find project first, then user."""
    from synapse.session import Session, SessionAgent

    # Only in user scope
    store.save(
        Session(
            session_name="shared",
            agents=[SessionAgent(profile="gemini")],
            working_dir="/u",
            created_at=time.time(),
            scope="user",
        )
    )
    loaded = store.load("shared")
    assert loaded is not None
    assert loaded.scope == "user"

    # Now save in project scope too
    store.save(
        Session(
            session_name="shared",
            agents=[SessionAgent(profile="claude")],
            working_dir="/p",
            created_at=time.time(),
            scope="project",
        )
    )
    loaded = store.load("shared")
    assert loaded is not None
    assert loaded.scope == "project"  # project takes priority


# ── agent_count auto-calculation ─────────────────────────────


def test_agent_count_auto(store) -> None:
    """agent_count should be auto-calculated from agents list length."""
    from synapse.session import Session, SessionAgent

    session = Session(
        session_name="counted",
        agents=[
            SessionAgent(profile="claude"),
            SessionAgent(profile="gemini"),
            SessionAgent(profile="codex"),
        ],
        working_dir="/p",
        created_at=time.time(),
        scope="project",
    )
    assert session.agent_count == 3
    store.save(session)
    loaded = store.load("counted")
    assert loaded is not None
    assert loaded.agent_count == 3


# ── path attribute ───────────────────────────────────────────


def test_loaded_session_has_path(store, session_dirs: tuple[Path, Path]) -> None:
    """Loaded session should have path attribute set."""
    from synapse.session import Session, SessionAgent

    project_dir, _ = session_dirs
    store.save(
        Session(
            session_name="pathed",
            agents=[SessionAgent(profile="claude")],
            working_dir="/p",
            created_at=time.time(),
            scope="project",
        )
    )
    loaded = store.load("pathed")
    assert loaded is not None
    assert loaded.path == project_dir / "pathed.json"


# ── session_id round-trip ─────────────────────────────────


def test_session_id_roundtrip(store) -> None:
    """session_id should survive save/load round-trip."""
    from synapse.session import Session, SessionAgent

    agents = [
        SessionAgent(profile="claude", name="Rev", session_id="conv-abc-123"),
        SessionAgent(profile="gemini", session_id="gem-sess-456"),
    ]
    session = Session(
        session_name="with-ids",
        agents=agents,
        working_dir="/p",
        created_at=time.time(),
        scope="project",
    )
    store.save(session)
    loaded = store.load("with-ids")
    assert loaded is not None
    assert loaded.agents[0].session_id == "conv-abc-123"
    assert loaded.agents[1].session_id == "gem-sess-456"


def test_session_id_backward_compat(store, session_dirs: tuple[Path, Path]) -> None:
    """Old JSON files without session_id should load with session_id=None."""
    import json

    project_dir, _ = session_dirs
    project_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "session_name": "legacy",
        "agents": [
            {
                "profile": "claude",
                "name": "Old",
                "role": None,
                "skill_set": None,
                "worktree": False,
            }
        ],
        "working_dir": "/p",
        "created_at": 1700000000.0,
        "scope": "project",
        "agent_count": 1,
    }
    (project_dir / "legacy.json").write_text(json.dumps(data), encoding="utf-8")
    loaded = store.load("legacy")
    assert loaded is not None
    assert loaded.agents[0].session_id is None


# ── build_resume_args ─────────────────────────────────────


def test_build_resume_args_claude_with_id() -> None:
    """Claude with session_id should return --resume <id>."""
    from synapse.session import build_resume_args

    assert build_resume_args("claude", "conv-123") == ["--resume", "conv-123"]


def test_build_resume_args_claude_latest() -> None:
    """Claude without session_id should return --continue (latest)."""
    from synapse.session import build_resume_args

    assert build_resume_args("claude") == ["--continue"]


def test_build_resume_args_gemini_with_id() -> None:
    """Gemini with session_id should return --resume <id>."""
    from synapse.session import build_resume_args

    assert build_resume_args("gemini", "gem-456") == ["--resume", "gem-456"]


def test_build_resume_args_gemini_latest() -> None:
    """Gemini without session_id should return --resume (latest)."""
    from synapse.session import build_resume_args

    assert build_resume_args("gemini") == ["--resume"]


def test_build_resume_args_codex_with_id() -> None:
    """Codex with session_id should return resume <id>."""
    from synapse.session import build_resume_args

    assert build_resume_args("codex", "cdx-789") == ["resume", "cdx-789"]


def test_build_resume_args_codex_latest() -> None:
    """Codex without session_id should return resume --last."""
    from synapse.session import build_resume_args

    assert build_resume_args("codex") == ["resume", "--last"]


def test_build_resume_args_copilot() -> None:
    """Copilot only supports --resume (latest, no id)."""
    from synapse.session import build_resume_args

    assert build_resume_args("copilot") == ["--resume"]
    # Even with session_id, copilot only does --resume
    assert build_resume_args("copilot", "some-id") == ["--resume"]


def test_build_resume_args_opencode() -> None:
    """OpenCode has no resume support — returns empty list."""
    from synapse.session import build_resume_args

    assert build_resume_args("opencode") == []
    assert build_resume_args("opencode", "some-id") == []


def test_build_resume_args_unknown() -> None:
    """Unknown profiles should return empty list."""
    from synapse.session import build_resume_args

    assert build_resume_args("unknown-agent") == []


def test_build_resume_args_trims_whitespace() -> None:
    """Whitespace in profile and session_id should be trimmed."""
    from synapse.session import build_resume_args

    assert build_resume_args("  claude  ", "  conv-123  ") == ["--resume", "conv-123"]
    assert build_resume_args("  gemini  ") == ["--resume"]


def test_build_resume_args_case_insensitive() -> None:
    """Profile matching should be case-insensitive."""
    from synapse.session import build_resume_args

    assert build_resume_args("Claude", "conv-123") == ["--resume", "conv-123"]
    assert build_resume_args("GEMINI") == ["--resume"]
    assert build_resume_args("Codex", "cdx-1") == ["resume", "cdx-1"]
    assert build_resume_args("COPILOT") == ["--resume"]


def test_build_resume_args_empty_session_id_treated_as_none() -> None:
    """Whitespace-only session_id should be treated as None (use latest)."""
    from synapse.session import build_resume_args

    assert build_resume_args("claude", "   ") == ["--continue"]
    assert build_resume_args("gemini", "") == ["--resume"]
