"""Tests for AgentProfileStore scope consistency across session lifecycle."""

from __future__ import annotations

from pathlib import Path

import pytest


def test_maybe_prompt_save_uses_provided_store(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """_maybe_prompt_save_agent_profile should use the provided store, not Path.cwd()."""
    from synapse.agent_profiles import AgentProfileStore

    # Create two separate "project" directories
    dir_a = tmp_path / "project_a"
    dir_b = tmp_path / "project_b"
    dir_a.mkdir()
    dir_b.mkdir()

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    # Create store rooted at dir_a (simulating startup-time)
    store = AgentProfileStore(project_root=dir_a, home_dir=home)

    # Change cwd to dir_b (simulating cwd drift during session)
    monkeypatch.chdir(dir_b)

    from synapse.cli import _maybe_prompt_save_agent_profile

    responses = iter(["y", "wise-strategist", "project"])
    _maybe_prompt_save_agent_profile(
        profile="claude",
        name="Frank",
        role="task manager",
        skill_set="manager",
        headless=False,
        is_tty=True,
        input_func=lambda _prompt: next(responses),
        print_func=lambda _msg: None,
        store=store,
    )

    # The .agent file should be saved under dir_a, not dir_b
    assert (dir_a / ".synapse" / "agents" / "wise-strategist.agent").exists()
    assert not (dir_b / ".synapse" / "agents" / "wise-strategist.agent").exists()


def test_maybe_prompt_save_without_store_uses_cwd(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Without an explicit store, fallback to Path.cwd() (existing behavior)."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(tmp_path)

    from synapse.cli import _maybe_prompt_save_agent_profile

    responses = iter(["y", "wise-strategist", "project"])
    _maybe_prompt_save_agent_profile(
        profile="claude",
        name="Frank",
        role="task manager",
        skill_set=None,
        headless=False,
        is_tty=True,
        input_func=lambda _prompt: next(responses),
        print_func=lambda _msg: None,
    )

    assert (tmp_path / ".synapse" / "agents" / "wise-strategist.agent").exists()


def test_prompt_default_scope_is_user_in_worktree(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Accepting the scope default in a worktree saves to user scope."""
    from synapse.agent_profiles import AgentProfileStore

    main_root = tmp_path / "repo"
    worktree_root = main_root / ".synapse" / "worktrees" / "test-wt"
    home = tmp_path / "home"
    worktree_root.mkdir(parents=True)
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr("synapse.worktree.is_path_in_worktree", lambda _path: True)

    store = AgentProfileStore(project_root=worktree_root, home_dir=home)

    from synapse.cli import _maybe_prompt_save_agent_profile

    prompts: list[str] = []
    responses = iter(["y", "wise-strategist", ""])

    def input_func(prompt: str) -> str:
        prompts.append(prompt)
        return next(responses)

    _maybe_prompt_save_agent_profile(
        profile="claude",
        name="Frank",
        role="task manager",
        skill_set="manager",
        headless=False,
        is_tty=True,
        input_func=input_func,
        print_func=lambda _msg: None,
        store=store,
    )

    assert "default: user" in prompts[-1]
    assert "worktree is deleted on cleanup" in prompts[-1]
    assert (home / ".synapse" / "agents" / "wise-strategist.agent").exists()
    assert not (
        worktree_root / ".synapse" / "agents" / "wise-strategist.agent"
    ).exists()


def test_prompt_default_scope_is_project_outside_worktree(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Outside a worktree, accepting the scope default still saves to project scope."""
    from synapse.agent_profiles import AgentProfileStore

    project_root = tmp_path / "repo"
    home = tmp_path / "home"
    project_root.mkdir()
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr("synapse.worktree.is_path_in_worktree", lambda _path: False)

    store = AgentProfileStore(project_root=project_root, home_dir=home)

    from synapse.cli import _maybe_prompt_save_agent_profile

    prompts: list[str] = []
    responses = iter(["y", "wise-strategist", ""])

    def input_func(prompt: str) -> str:
        prompts.append(prompt)
        return next(responses)

    _maybe_prompt_save_agent_profile(
        profile="claude",
        name="Frank",
        role="task manager",
        skill_set="manager",
        headless=False,
        is_tty=True,
        input_func=input_func,
        print_func=lambda _msg: None,
        store=store,
    )

    assert "default: project" in prompts[-1]
    assert (project_root / ".synapse" / "agents" / "wise-strategist.agent").exists()
    assert not (home / ".synapse" / "agents" / "wise-strategist.agent").exists()
