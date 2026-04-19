"""Tests for agent definition storage used by `synapse agents` commands."""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.core


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
        name="Alice",
        profile="claude",
        role="@./roles/reviewer.md",
        skill_set="reviewer",
        scope="project",
    )

    resolved = store.resolve("Alice")
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
            name="Alice",
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
        name="Alice",
        profile="claude",
        role=None,
        skill_set=None,
        scope="project",
    )
    deleted = store.delete("Alice")
    assert deleted
    assert store.resolve("Alice") is None


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


# ── suggest_petname_ids exclude ──────────────────────────────


def test_suggest_petname_ids_excludes_taken_names() -> None:
    """Suggestions should skip names already in use."""
    from synapse.agent_profiles import suggest_petname_ids

    # Without exclude, "claude-agent" is the first candidate
    assert suggest_petname_ids("claude")[0] == "claude-agent"

    # With "claude-agent" excluded, it should not appear
    results = suggest_petname_ids("claude", exclude={"claude-agent"})
    assert "claude-agent" not in results
    assert len(results) > 0


def test_suggest_petname_ids_excludes_all_fallbacks() -> None:
    """When all normal candidates are excluded, generic fallbacks are used."""
    from synapse.agent_profiles import suggest_petname_ids

    # Exclude all claude-* fallbacks
    excluded = {"claude-agent", "claude-helper", "claude-worker", "claude-guide"}
    results = suggest_petname_ids("claude", exclude=excluded)
    for r in results:
        assert r not in excluded
