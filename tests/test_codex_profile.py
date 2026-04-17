"""Regression tests for the codex profile's waiting_detection regex.

Codex keeps introducing new TUI prompts (approval overlays, model-switch
modals, rate-limit modals). Each miss in ``waiting_detection`` causes the
agent to stall silently in PROCESSING while the PTY is really blocked on
user input — there is no auto-escalation until the regex catches the new
shape. These tests pin down the patterns we rely on today so that a
regression (or a well-meaning regex cleanup) does not silently reopen a
whole class of stall bugs.

See the issue tracking the deeper waiting_detection + alternate-screen-
buffer fix for the longer-term plan.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml


@pytest.fixture
def codex_profile() -> dict:
    path = Path(__file__).parent.parent / "synapse" / "profiles" / "codex.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


class TestCodexWaitingDetection:
    def test_regex_compiles(self, codex_profile: dict) -> None:
        regex = codex_profile["waiting_detection"]["regex"]
        assert re.compile(regex) is not None

    def test_matches_approval_overlay(self, codex_profile: dict) -> None:
        regex = re.compile(codex_profile["waiting_detection"]["regex"])
        overlay = (
            "› 1. Yes, proceed (y)\n"
            "  2. Yes, and don't ask again for commands that start with `cp ...` (p)\n"
            "  3. No, and tell Codex what to do differently (esc)\n"
        )
        assert regex.search(overlay)

    def test_matches_model_switch_modal(self, codex_profile: dict) -> None:
        """Rate-limit model-switch modal. Newer codex builds pop this up
        when the session is about to blow the API rate limit. Previously
        the regex missed it and the agent stalled with no notification."""
        regex = re.compile(codex_profile["waiting_detection"]["regex"])
        modal = (
            "Approaching rate limits\n"
            "Switch to gpt-5.1-codex-mini for lower credit usage?\n"
            "\n"
            "› 1. Switch to gpt-5.1-codex-mini\n"
            "  2. Keep current model\n"
            "  3. Keep current model (never show again)\n"
        )
        assert regex.search(modal)

    def test_matches_usage_limit_banner(self, codex_profile: dict) -> None:
        """Step D diagnostic (2026-04-15) captured this exact screen
        while codex was blocked on an OpenAI usage limit. The pre-fix
        regex missed it, so the workflow runner escalated to the parent
        as input_required every few seconds. Until the Approval Gate
        loop bug is fixed in its own PR, detecting this as WAITING at
        least stops the spam and surfaces a consistent signal."""
        regex = re.compile(codex_profile["waiting_detection"]["regex"])
        banner = (
            "\u25a0 You've hit your usage limit. Upgrade to Pro "
            "(https://chatgpt.com/explore/pro), visit "
            "https://chatgpt.com/codex/settings/usage to purchase "
            "more credits or try again at Apr 17th, 2026 6:28 AM. "
            "\u203a Find and fix a bug in @filename   gpt-5.4 medium"
        )
        assert regex.search(banner)

    def test_matches_bare_numbered_selector(self, codex_profile: dict) -> None:
        """Even without any of the named phrases, the `› 1.` shape should
        be enough on its own to trigger WAITING detection. This keeps us
        covered for future prompt copy changes."""
        regex = re.compile(codex_profile["waiting_detection"]["regex"])
        assert regex.search("› 1. Some brand new prompt text")

    def test_waiting_expiry_long_enough_for_parent_intervention(
        self, codex_profile: dict
    ) -> None:
        """``waiting_expiry`` controls how long WAITING state sticks before
        auto-clearing. Too short and the parent has no time to intervene
        before the state flips back to PROCESSING and the notification is
        silently lost."""
        expiry = codex_profile["waiting_detection"]["waiting_expiry"]
        assert expiry >= 30

    def test_auto_approve_alternative_flags_include_bypass(
        self, codex_profile: dict
    ) -> None:
        """Workflow auto-spawn picks the first alternative flag so that
        long-running batch workflows don't get derailed by runtime
        permission prompts. The dangerous bypass flag must stay first so
        workflow runs keep their deterministic behavior."""
        alternatives = codex_profile["auto_approve"]["alternative_flags"]
        assert isinstance(alternatives, list)
        assert alternatives[0] == "--dangerously-bypass-approvals-and-sandbox"
