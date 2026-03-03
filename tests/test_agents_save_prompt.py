"""Tests for save-on-exit prompt of interactive agents."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from synapse.agent_profiles import AgentProfile, AgentProfileStore
from synapse.cli import _maybe_prompt_save_agent_profile


def test_save_prompt_skips_when_not_tty() -> None:
    """Prompt should be skipped in non-interactive environments."""
    store = MagicMock()
    _maybe_prompt_save_agent_profile(
        profile="claude",
        name="Alice",
        role="@./roles/reviewer.md",
        skill_set="reviewer",
        headless=False,
        is_tty=False,
        input_func=lambda _p: "y",
        print_func=lambda _m: None,
        store=store,
    )
    store.add.assert_not_called()


def test_save_prompt_persists_when_confirmed() -> None:
    """Prompt should persist when user confirms and provides id."""
    store = MagicMock()
    answers = iter(["y", "silent-snake", "project"])

    _maybe_prompt_save_agent_profile(
        profile="claude",
        name="Alice",
        role="@./roles/reviewer.md",
        skill_set="reviewer",
        headless=False,
        is_tty=True,
        input_func=lambda _p: next(answers),
        print_func=lambda _m: None,
        store=store,
    )

    store.add.assert_called_once_with(
        profile_id="silent-snake",
        name="Alice",
        profile="claude",
        role="@./roles/reviewer.md",
        skill_set="reviewer",
        scope="project",
    )


def test_save_prompt_skips_when_env_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prompt should be skipped when feature flag is disabled."""
    monkeypatch.setenv("SYNAPSE_AGENT_SAVE_PROMPT_ENABLED", "false")
    store = MagicMock()
    answers = iter(["y", "silent-snake", "project"])

    _maybe_prompt_save_agent_profile(
        profile="claude",
        name="Alice",
        role="@./roles/reviewer.md",
        skill_set="reviewer",
        headless=False,
        is_tty=True,
        input_func=lambda _p: next(answers),
        print_func=lambda _m: None,
        store=store,
    )

    store.add.assert_not_called()


# ── Skip when already saved ──────────────────────────────────


def test_save_prompt_skips_when_already_saved() -> None:
    """Prompt should be skipped when an identical profile already exists."""
    store = MagicMock(spec=AgentProfileStore)
    store.list_all.return_value = [
        AgentProfile(
            profile_id="calm-lead",
            name="Alice",
            profile="claude",
            role="reviewer",
            skill_set="review-set",
            scope="project",
        )
    ]
    called = False

    def _input(prompt: str) -> str:
        nonlocal called
        called = True
        return "y"

    _maybe_prompt_save_agent_profile(
        profile="claude",
        name="Alice",
        role="reviewer",
        skill_set="review-set",
        headless=False,
        is_tty=True,
        input_func=_input,
        print_func=lambda _m: None,
        store=store,
    )

    assert not called, "input_func should never be called when already saved"
    store.add.assert_not_called()


def test_save_prompt_skips_when_already_saved_none_fields() -> None:
    """Prompt should be skipped even when role and skill_set are None."""
    store = MagicMock(spec=AgentProfileStore)
    store.list_all.return_value = [
        AgentProfile(
            profile_id="quick-fox",
            name="Bob",
            profile="gemini",
            role=None,
            skill_set=None,
            scope="user",
        )
    ]

    _maybe_prompt_save_agent_profile(
        profile="gemini",
        name="Bob",
        role=None,
        skill_set=None,
        headless=False,
        is_tty=True,
        input_func=lambda _p: "y",
        print_func=lambda _m: None,
        store=store,
    )

    store.add.assert_not_called()


def test_save_prompt_asks_when_different_from_saved() -> None:
    """Prompt should appear when current config differs from all saved profiles."""
    store = MagicMock(spec=AgentProfileStore)
    store.list_all.return_value = [
        AgentProfile(
            profile_id="calm-lead",
            name="Alice",
            profile="claude",
            role="reviewer",
            skill_set="review-set",
            scope="project",
        )
    ]
    answers = iter(["y", "brave-lion", "project"])

    _maybe_prompt_save_agent_profile(
        profile="claude",
        name="Alice",
        role="implementer",  # different role
        skill_set="dev-set",
        headless=False,
        is_tty=True,
        input_func=lambda _p: next(answers),
        print_func=lambda _m: None,
        store=store,
    )

    store.add.assert_called_once()


def test_save_prompt_asks_when_no_saved_profiles() -> None:
    """Prompt should appear when store has no saved profiles at all."""
    store = MagicMock(spec=AgentProfileStore)
    store.list_all.return_value = []
    answers = iter(["n"])

    _maybe_prompt_save_agent_profile(
        profile="claude",
        name="Alice",
        role="reviewer",
        skill_set=None,
        headless=False,
        is_tty=True,
        input_func=lambda _p: next(answers),
        print_func=lambda _m: None,
        store=store,
    )

    store.add.assert_not_called()  # user declined, but prompt was shown
