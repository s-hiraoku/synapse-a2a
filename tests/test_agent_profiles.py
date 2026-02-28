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
