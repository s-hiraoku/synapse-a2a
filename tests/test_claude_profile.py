"""Tests for the Claude Code profile (synapse/profiles/claude.yaml).

Anthropic deprecated `--dangerously-skip-permissions` in favor of
`--permission-mode auto`, which uses a safety classifier instead of
disabling all checks. The profile must inject the safer flag by default
while still recognizing the legacy forms so users who pass them manually
do not get a duplicated injection.
"""

from pathlib import Path

import pytest
import yaml

PROFILES_DIR = Path(__file__).resolve().parent.parent / "synapse" / "profiles"


@pytest.fixture
def claude_profile() -> dict:
    """Load the Claude Code profile YAML."""
    with open(PROFILES_DIR / "claude.yaml") as f:
        return yaml.safe_load(f)


class TestClaudeAutoApprove:
    """Verify the auto-approve config matches Anthropic's current guidance."""

    def test_cli_flag_uses_permission_mode_auto(self, claude_profile: dict) -> None:
        """Default injection should be `--permission-mode=auto`, not the
        deprecated `--dangerously-skip-permissions` (a.k.a. bypassPermissions).
        Auto mode keeps a safety classifier active while still allowing
        unattended runs."""
        assert claude_profile["auto_approve"]["cli_flag"] == "--permission-mode=auto"

    def test_alternative_flags_recognize_legacy_bypass(
        self, claude_profile: dict
    ) -> None:
        """Users who explicitly pass the legacy bypass flag (or its modern
        `--permission-mode=bypassPermissions` long form) must not get the
        new `--permission-mode=auto` injected on top — that would either
        duplicate the flag or silently override the user's choice."""
        alternatives = claude_profile["auto_approve"]["alternative_flags"]
        assert isinstance(alternatives, list)
        assert "--dangerously-skip-permissions" in alternatives
        assert "--permission-mode=bypassPermissions" in alternatives

    def test_alternative_flags_recognize_bare_permission_mode(
        self, claude_profile: dict
    ) -> None:
        """`--permission-mode <value>` (space-separated) should also be
        treated as already-present so we don't append a second flag with
        a conflicting value."""
        alternatives = claude_profile["auto_approve"]["alternative_flags"]
        assert "--permission-mode" in alternatives

    def test_runtime_response_unchanged(self, claude_profile: dict) -> None:
        """Runtime auto-accept reply for permission prompts the agent hits
        mid-session is unrelated to the launch flag — keep it stable."""
        assert claude_profile["auto_approve"]["runtime_response"] == "y\r"
        assert claude_profile["auto_approve"]["deny_response"] == "n\r"
