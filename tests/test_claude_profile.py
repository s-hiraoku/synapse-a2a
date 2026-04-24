"""Tests for the Claude Code profile (synapse/profiles/claude.yaml).

Anthropic deprecated `--dangerously-skip-permissions` in favor of
`--permission-mode auto`, which uses a safety classifier instead of
disabling all checks. The profile must inject the safer flag by default
while still recognizing the legacy forms so users who pass them manually
do not get a duplicated injection.
"""

from pathlib import Path
from unittest.mock import patch

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


class TestClaudeAutoApproveSpawnIntegration:
    """End-to-end checks that prepare_spawn() respects the alternative_flags
    list when the user passes a permission-mode flag manually.

    The YAML-only assertions above guarantee the alternatives list contents
    but not that the spawn pipeline actually consults it. A regression here
    would mean the user passes ``--permission-mode bypassPermissions`` and
    Synapse silently appends ``--permission-mode=auto`` on top, producing a
    conflicting CLI invocation that Claude Code rejects.
    """

    def test_space_separated_permission_mode_skips_injection(self) -> None:
        """``["--permission-mode", "auto"]`` (space-separated form) must be
        recognised as already-present so the canonical ``--permission-mode=auto``
        is not appended on top.
        """
        from synapse.spawn import prepare_spawn

        with (
            patch("synapse.spawn.is_port_available", return_value=True),
        ):
            prepared = prepare_spawn(
                "claude",
                port=8100,
                tool_args=["--permission-mode", "bypassPermissions"],
            )

        assert prepared.tool_args is not None
        # Canonical flag must not be appended when the user already specified
        # the bare alternative form.
        assert "--permission-mode=auto" not in prepared.tool_args
        # User's tokens must be preserved verbatim.
        assert prepared.tool_args[-2:] == ["--permission-mode", "bypassPermissions"]

    def test_legacy_dangerously_skip_permissions_skips_injection(self) -> None:
        """The historical ``--dangerously-skip-permissions`` flag is still
        accepted as a synonym; injection must be skipped so users who
        haven't yet migrated their scripts don't get a conflicting flag."""
        from synapse.spawn import prepare_spawn

        with (
            patch("synapse.spawn.is_port_available", return_value=True),
        ):
            prepared = prepare_spawn(
                "claude",
                port=8100,
                tool_args=["--dangerously-skip-permissions"],
            )

        assert prepared.tool_args is not None
        assert "--permission-mode=auto" not in prepared.tool_args
        assert "--dangerously-skip-permissions" in prepared.tool_args

    def test_permission_mode_equals_form_skips_injection(self) -> None:
        """``--permission-mode=bypassPermissions`` (= form) must also satisfy
        the alternative_flags check via exact-match against the explicit
        long form listed in claude.yaml."""
        from synapse.spawn import prepare_spawn

        with (
            patch("synapse.spawn.is_port_available", return_value=True),
        ):
            prepared = prepare_spawn(
                "claude",
                port=8100,
                tool_args=["--permission-mode=bypassPermissions"],
            )

        assert prepared.tool_args is not None
        assert "--permission-mode=auto" not in prepared.tool_args
        assert "--permission-mode=bypassPermissions" in prepared.tool_args

    def test_no_user_flag_injects_canonical_default(self) -> None:
        """When the user passes no permission flag, prepare_spawn must inject
        the canonical ``--permission-mode=auto`` so headless agents start
        without prompting."""
        from synapse.spawn import prepare_spawn

        with (
            patch("synapse.spawn.is_port_available", return_value=True),
        ):
            prepared = prepare_spawn("claude", port=8100, tool_args=[])

        assert prepared.tool_args is not None
        assert "--permission-mode=auto" in prepared.tool_args
