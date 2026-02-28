"""Tests for agent definition storage used by `synapse agents` commands."""

from __future__ import annotations

from pathlib import Path

import pytest


def test_add_and_resolve_by_name(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Definitions should be resolvable by display name."""
    home = tmp_path / "home"
    home.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(tmp_path)

    from synapse.agent_profiles import AgentProfileStore

    store = AgentProfileStore()
    store.add(
        profile_id="silent-snake",
        name="狗巻棘",
        profile="claude",
        role="@./roles/reviewer.md",
        skill_set="reviewer",
        scope="project",
    )

    resolved = store.resolve("狗巻棘")
    assert resolved is not None
    assert resolved.profile_id == "silent-snake"
    assert resolved.profile == "claude"


def test_add_rejects_non_petname_id(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """IDs must follow petname format (word-word, lowercase)."""
    home = tmp_path / "home"
    home.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(tmp_path)

    from synapse.agent_profiles import AgentProfileError, AgentProfileStore

    store = AgentProfileStore()
    with pytest.raises(AgentProfileError, match="petname"):
        store.add(
            profile_id="dog",
            name="狗巻棘",
            profile="claude",
            role=None,
            skill_set=None,
            scope="project",
        )


def test_delete_by_name(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Delete should accept a display name."""
    home = tmp_path / "home"
    home.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(tmp_path)

    from synapse.agent_profiles import AgentProfileStore

    store = AgentProfileStore()
    store.add(
        profile_id="silent-snake",
        name="狗巻棘",
        profile="claude",
        role=None,
        skill_set=None,
        scope="project",
    )
    deleted = store.delete("狗巻棘")
    assert deleted
    assert store.resolve("狗巻棘") is None


def test_list_all_skips_corrupted_agent_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Corrupted .agent files should be skipped instead of failing list_all()."""
    home = tmp_path / "home"
    home.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(tmp_path)

    from synapse.agent_profiles import AgentProfileStore

    store = AgentProfileStore()
    store.add(
        profile_id="silent-snake",
        name="Reviewer",
        profile="codex",
        role=None,
        skill_set=None,
        scope="project",
    )
    # Invalid id format to force parse-time validation error.
    (store.project_dir / "bad.agent").write_text(
        "id=invalid\nname=Broken\nprofile=claude\n",
        encoding="utf-8",
    )

    profiles = store.list_all()
    assert [p.profile_id for p in profiles] == ["silent-snake"]


def test_add_rejects_whitespace_only_required_fields(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Whitespace-only name/profile should be treated as missing."""
    home = tmp_path / "home"
    home.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(tmp_path)

    from synapse.agent_profiles import AgentProfileError, AgentProfileStore

    store = AgentProfileStore()
    with pytest.raises(AgentProfileError, match="name is required"):
        store.add(
            profile_id="silent-snake",
            name="   ",
            profile="claude",
            role=None,
            skill_set=None,
            scope="project",
        )

    with pytest.raises(AgentProfileError, match="profile is required"):
        store.add(
            profile_id="silent-snake",
            name="Reviewer",
            profile="   ",
            role=None,
            skill_set=None,
            scope="project",
        )
