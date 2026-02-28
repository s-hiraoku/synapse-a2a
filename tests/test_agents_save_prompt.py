"""Tests for save-on-exit prompt of interactive agents."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from synapse.cli import _maybe_prompt_save_agent_profile


def test_save_prompt_skips_when_not_tty() -> None:
    """Prompt should be skipped in non-interactive environments."""
    store = MagicMock()
    _maybe_prompt_save_agent_profile(
        profile="claude",
        name="狗巻棘",
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
        name="狗巻棘",
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
        name="狗巻棘",
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
        name="狗巻棘",
        role="@./roles/reviewer.md",
        skill_set="reviewer",
        headless=False,
        is_tty=True,
        input_func=lambda _p: next(answers),
        print_func=lambda _m: None,
        store=store,
    )

    store.add.assert_not_called()
