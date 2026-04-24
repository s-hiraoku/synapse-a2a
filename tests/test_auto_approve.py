"""Tests for auto-approve feature (Issue #469).

Tests cover:
1. Controller auto-approve callback (WAITING → write approval response)
2. Safety controls (cooldown, max consecutive, disable)
3. Spawn-time CLI flag injection
4. Profile YAML auto_approve config loading
"""

from __future__ import annotations

from unittest.mock import patch

import pytest


def _make_controller(
    auto_approve: dict | None = None,
    waiting_detection: dict | None = None,
):
    """Create a TerminalController with mocked dependencies."""
    from synapse.controller import TerminalController

    with patch("synapse.controller.AgentRegistry"):
        ctrl = TerminalController(
            command="echo",
            auto_approve=auto_approve,
            waiting_detection=waiting_detection,
        )
    return ctrl


# ============================================================
# TestControllerAutoApprove — runtime WAITING auto-response
# ============================================================


class TestControllerAutoApprove:
    """TerminalController auto-approve callback tests."""

    def test_auto_approve_enabled_registers_callback(self) -> None:
        """When auto_approve config is provided, a status callback is registered."""
        ctrl = _make_controller(
            auto_approve={"runtime_response": "y\\r", "max_consecutive": 5}
        )
        assert ctrl._auto_approve_enabled is True
        assert len(ctrl._status_callbacks) == 1

    def test_auto_approve_disabled_no_callback(self) -> None:
        """When auto_approve is None, no callback is registered."""
        ctrl = _make_controller(auto_approve=None)
        assert ctrl._auto_approve_enabled is False
        assert len(ctrl._status_callbacks) == 0

    def test_auto_approve_empty_config_no_callback(self) -> None:
        """Empty auto_approve config should not enable auto-approve."""
        ctrl = _make_controller(auto_approve={})
        assert ctrl._auto_approve_enabled is False

    def test_callback_fires_on_waiting(self) -> None:
        """Callback should call write() when status transitions to WAITING."""
        ctrl = _make_controller(
            auto_approve={
                "runtime_response": "y\\r",
                "max_consecutive": 20,
                "cooldown": 0.0,
            }
        )
        with patch.object(ctrl, "write") as mock_write:
            ctrl._handle_auto_approve("PROCESSING", "WAITING")
        mock_write.assert_called_once_with("y\r")

    def test_callback_ignores_non_waiting(self) -> None:
        """Callback should not fire for non-WAITING transitions."""
        ctrl = _make_controller(
            auto_approve={"runtime_response": "y\\r", "cooldown": 0.0}
        )
        with patch.object(ctrl, "write") as mock_write:
            ctrl._handle_auto_approve("PROCESSING", "READY")
            ctrl._handle_auto_approve("READY", "PROCESSING")
            ctrl._handle_auto_approve("PROCESSING", "DONE")
        mock_write.assert_not_called()

    def test_cooldown_enforced(self) -> None:
        """Second WAITING within cooldown period should be skipped."""
        ctrl = _make_controller(
            auto_approve={
                "runtime_response": "y\\r",
                "max_consecutive": 20,
                "cooldown": 10.0,  # 10 second cooldown
            }
        )
        with patch.object(ctrl, "write") as mock_write:
            # First call succeeds
            ctrl._handle_auto_approve("PROCESSING", "WAITING")
            assert mock_write.call_count == 1

            # Second call within cooldown should be skipped
            ctrl._handle_auto_approve("PROCESSING", "WAITING")
            assert mock_write.call_count == 1  # Still 1

    def test_max_consecutive_enforced(self) -> None:
        """After max_consecutive approvals, auto-approve should stop."""
        ctrl = _make_controller(
            auto_approve={
                "runtime_response": "y\\r",
                "max_consecutive": 3,
                "cooldown": 0.0,
            }
        )
        with patch.object(ctrl, "write") as mock_write:
            for _ in range(5):
                ctrl._handle_auto_approve("PROCESSING", "WAITING")

        # Should have written exactly 3 times (max_consecutive)
        assert mock_write.call_count == 3
        assert ctrl._auto_approve_stopped is True

    def test_counter_does_not_reset_on_processing(self) -> None:
        """Counter should NOT reset on WAITING→PROCESSING to prevent safety valve bypass."""
        ctrl = _make_controller(
            auto_approve={
                "runtime_response": "y\\r",
                "max_consecutive": 3,
                "cooldown": 0.0,
            }
        )
        with patch.object(ctrl, "write") as mock_write:
            # Use 2 of 3 approvals
            ctrl._handle_auto_approve("PROCESSING", "WAITING")
            ctrl._handle_auto_approve("PROCESSING", "WAITING")
            assert mock_write.call_count == 2

            # WAITING→PROCESSING should NOT reset the counter
            ctrl._handle_auto_approve("WAITING", "PROCESSING")
            assert ctrl._auto_approve_count == 2

            # Only 1 more approval before max (3 total)
            ctrl._handle_auto_approve("PROCESSING", "WAITING")
            assert mock_write.call_count == 3

            # 4th should be blocked
            ctrl._handle_auto_approve("PROCESSING", "WAITING")
            assert mock_write.call_count == 3
            assert ctrl._auto_approve_stopped is True

    def test_runtime_response_escape_decoding(self) -> None:
        """YAML escape sequences in runtime_response should be decoded."""
        ctrl = _make_controller(
            auto_approve={"runtime_response": "y\\r", "cooldown": 0.0}
        )
        # "y\\r" in YAML → "y\r" (actual carriage return)
        assert ctrl._auto_approve_response == "y\r"

    def test_enter_only_response(self) -> None:
        """Gemini profile uses just Enter (\\r) as runtime_response."""
        ctrl = _make_controller(
            auto_approve={"runtime_response": "\\r", "cooldown": 0.0}
        )
        assert ctrl._auto_approve_response == "\r"

    def test_numbered_response(self) -> None:
        """Copilot profile uses '1\\r' as runtime_response."""
        ctrl = _make_controller(
            auto_approve={"runtime_response": "1\\r", "cooldown": 0.0}
        )
        assert ctrl._auto_approve_response == "1\r"


# ============================================================
# TestSpawnAutoApproveInjection — launch-time flag injection
# ============================================================


class TestSpawnAutoApproveInjection:
    """prepare_spawn() should inject CLI flags from profile auto_approve config."""

    def test_claude_flag_injected(self) -> None:
        """Claude profile should inject --dangerously-skip-permissions."""
        from synapse.spawn import prepare_spawn

        with (
            patch(
                "synapse.spawn.load_profile",
                return_value={
                    "auto_approve": {
                        "cli_flag": "--dangerously-skip-permissions",
                        "runtime_response": "y\\r",
                    }
                },
            ),
            patch("synapse.spawn.is_port_available", return_value=True),
        ):
            prepared = prepare_spawn("claude", port=8100)

        assert prepared.tool_args is not None
        assert "--dangerously-skip-permissions" in prepared.tool_args

    def test_codex_flag_injected(self) -> None:
        """Codex profile should inject --full-auto."""
        from synapse.spawn import prepare_spawn

        with (
            patch(
                "synapse.spawn.load_profile",
                return_value={
                    "auto_approve": {
                        "cli_flag": "--full-auto",
                        "runtime_response": "y\\r",
                    }
                },
            ),
            patch("synapse.spawn.is_port_available", return_value=True),
        ):
            prepared = prepare_spawn("codex", port=8120)

        assert prepared.tool_args is not None
        assert "--full-auto" in prepared.tool_args

    def test_gemini_flag_injected(self) -> None:
        """Gemini profile should inject --yolo."""
        from synapse.spawn import prepare_spawn

        with (
            patch(
                "synapse.spawn.load_profile",
                return_value={
                    "auto_approve": {
                        "cli_flag": "--yolo",
                        "runtime_response": "\\r",
                    }
                },
            ),
            patch("synapse.spawn.is_port_available", return_value=True),
        ):
            prepared = prepare_spawn("gemini", port=8110)

        assert prepared.tool_args is not None
        assert "--yolo" in prepared.tool_args

    def test_copilot_flag_injected(self) -> None:
        """Copilot profile should inject --yolo."""
        from synapse.spawn import prepare_spawn

        with (
            patch(
                "synapse.spawn.load_profile",
                return_value={
                    "auto_approve": {
                        "cli_flag": "--yolo",
                        "runtime_response": "1\\r",
                    }
                },
            ),
            patch("synapse.spawn.is_port_available", return_value=True),
        ):
            prepared = prepare_spawn("copilot", port=8140)

        assert prepared.tool_args is not None
        assert "--yolo" in prepared.tool_args

    def test_opencode_env_flag_injected(self) -> None:
        """OpenCode should set OPENCODE_DANGEROUSLY_SKIP_PERMISSIONS env var."""
        from synapse.spawn import prepare_spawn

        with (
            patch(
                "synapse.spawn.load_profile",
                return_value={
                    "auto_approve": {
                        "cli_flag": None,
                        "env_flag": "OPENCODE_DANGEROUSLY_SKIP_PERMISSIONS=true",
                        "runtime_response": "a\\r",
                    }
                },
            ),
            patch("synapse.spawn.is_port_available", return_value=True),
        ):
            prepared = prepare_spawn("opencode", port=8130)

        assert prepared.extra_env is not None
        assert prepared.extra_env.get("OPENCODE_DANGEROUSLY_SKIP_PERMISSIONS") == "true"
        # No CLI flag should be injected (cli_flag is None)
        assert prepared.tool_args is None or "--dangerously" not in str(
            prepared.tool_args
        )

    def test_no_duplicate_flag(self) -> None:
        """If user already passes the flag, it should not be added again."""
        from synapse.spawn import prepare_spawn

        with (
            patch(
                "synapse.spawn.load_profile",
                return_value={
                    "auto_approve": {
                        "cli_flag": "--dangerously-skip-permissions",
                        "runtime_response": "y\\r",
                    }
                },
            ),
            patch("synapse.spawn.is_port_available", return_value=True),
        ):
            prepared = prepare_spawn(
                "claude",
                port=8100,
                tool_args=["--dangerously-skip-permissions"],
            )

        assert prepared.tool_args is not None
        assert prepared.tool_args.count("--dangerously-skip-permissions") == 1

    def test_alternative_flag_skips_injection(self) -> None:
        """If user passes an alternative approval flag, cli_flag should not be injected.

        Codex accepts both --full-auto and --dangerously-bypass-approvals-and-sandbox
        but they are mutually exclusive. When the user explicitly passes the bypass
        flag, the default --full-auto must not be auto-injected.
        """
        from synapse.spawn import prepare_spawn

        with (
            patch(
                "synapse.spawn.load_profile",
                return_value={
                    "auto_approve": {
                        "cli_flag": "--full-auto",
                        "alternative_flags": [
                            "--dangerously-bypass-approvals-and-sandbox",
                            "-a",
                            "--ask-for-approval",
                        ],
                        "runtime_response": "y\\r",
                    }
                },
            ),
            patch("synapse.spawn.is_port_available", return_value=True),
        ):
            prepared = prepare_spawn(
                "codex",
                port=8100,
                tool_args=["--dangerously-bypass-approvals-and-sandbox"],
            )

        assert prepared.tool_args is not None
        assert "--full-auto" not in prepared.tool_args
        assert "--dangerously-bypass-approvals-and-sandbox" in prepared.tool_args

    def test_gemini_short_yolo_flag_skips_injection(self) -> None:
        """Gemini: -y should skip --yolo injection (they are aliases)."""
        from synapse.spawn import prepare_spawn

        with (
            patch(
                "synapse.spawn.load_profile",
                return_value={
                    "auto_approve": {
                        "cli_flag": "--yolo",
                        "alternative_flags": ["-y", "--approval-mode=auto_edit"],
                        "runtime_response": "\\r",
                    }
                },
            ),
            patch("synapse.spawn.is_port_available", return_value=True),
        ):
            prepared = prepare_spawn("gemini", port=8110, tool_args=["-y"])

        assert prepared.tool_args is not None
        assert "--yolo" not in prepared.tool_args
        assert "-y" in prepared.tool_args

    def test_flag_equals_value_form_skips_injection(self) -> None:
        """`--approval-mode=auto_edit` should satisfy the `--approval-mode`
        alternative flag and skip --yolo injection, and the user's
        `--flag=value` token must be preserved verbatim in tool_args.
        """
        from synapse.spawn import prepare_spawn

        with (
            patch(
                "synapse.spawn.load_profile",
                return_value={
                    "auto_approve": {
                        "cli_flag": "--yolo",
                        "alternative_flags": ["-y", "--approval-mode"],
                        "runtime_response": "\\r",
                    }
                },
            ),
            patch("synapse.spawn.is_port_available", return_value=True),
        ):
            prepared = prepare_spawn(
                "gemini",
                port=8110,
                tool_args=["--approval-mode=auto_edit"],
            )

        assert prepared.tool_args is not None
        assert "--yolo" not in prepared.tool_args
        assert "--approval-mode=auto_edit" in prepared.tool_args

    def test_alternative_flags_string_shorthand_is_normalized(self) -> None:
        """A bare-string `alternative_flags: "--yolo"` YAML shorthand must be
        normalized to a single-element list, not iterated character by
        character (which would otherwise spuriously match "-" and "y" in
        tool_args).
        """
        from synapse.spawn import prepare_spawn

        with (
            patch(
                "synapse.spawn.load_profile",
                return_value={
                    "auto_approve": {
                        "cli_flag": "--allow-all",
                        "alternative_flags": "--yolo",
                        "runtime_response": "1\\r",
                    }
                },
            ),
            patch("synapse.spawn.is_port_available", return_value=True),
        ):
            prepared = prepare_spawn("copilot", port=8120, tool_args=["--yolo"])

        assert prepared.tool_args is not None
        assert "--allow-all" not in prepared.tool_args
        assert "--yolo" in prepared.tool_args

    def test_auto_approve_false_no_injection(self) -> None:
        """When auto_approve=False, no CLI flag should be injected."""
        from synapse.spawn import prepare_spawn

        with (
            patch(
                "synapse.spawn.load_profile",
                return_value={
                    "auto_approve": {
                        "cli_flag": "--dangerously-skip-permissions",
                        "runtime_response": "y\\r",
                    }
                },
            ),
            patch("synapse.spawn.is_port_available", return_value=True),
        ):
            prepared = prepare_spawn("claude", port=8100, auto_approve=False)

        # Should not contain the auto-approve flag
        if prepared.tool_args:
            assert "--dangerously-skip-permissions" not in prepared.tool_args
        # Should set SYNAPSE_AUTO_APPROVE=false
        assert prepared.extra_env is not None
        assert prepared.extra_env.get("SYNAPSE_AUTO_APPROVE") == "false"

    def test_auto_approve_true_sets_env(self) -> None:
        """When auto_approve=True, SYNAPSE_AUTO_APPROVE=true should be in env."""
        from synapse.spawn import prepare_spawn

        with (
            patch(
                "synapse.spawn.load_profile",
                return_value={
                    "auto_approve": {
                        "cli_flag": "--yolo",
                        "runtime_response": "\\r",
                    }
                },
            ),
            patch("synapse.spawn.is_port_available", return_value=True),
        ):
            prepared = prepare_spawn("gemini", port=8110, auto_approve=True)

        assert prepared.extra_env is not None
        assert prepared.extra_env.get("SYNAPSE_AUTO_APPROVE") == "true"

    def test_no_auto_approve_config_no_injection(self) -> None:
        """Profile without auto_approve config should not inject anything."""
        from synapse.spawn import prepare_spawn

        with (
            patch("synapse.spawn.load_profile", return_value={}),
            patch("synapse.spawn.is_port_available", return_value=True),
        ):
            prepared = prepare_spawn("claude", port=8100)

        assert prepared.tool_args is None


# ============================================================
# TestProfileAutoApproveConfig — YAML config structure
# ============================================================


class TestProfileAutoApproveConfig:
    """Verify auto_approve config is present in all profiles."""

    @pytest.mark.parametrize(
        "profile_name,expected_flag",
        [
            # Claude Code: switched from --dangerously-skip-permissions to
            # --permission-mode=auto (Anthropic's documented successor —
            # safety classifier instead of disabling all checks).
            ("claude", "--permission-mode=auto"),
            # Gemini CLI: switched from --yolo to --approval-mode=yolo for
            # consistency with the unified --approval-mode parameter
            # (default / auto_edit / yolo).
            ("gemini", "--approval-mode=yolo"),
            ("codex", "--full-auto"),
            ("copilot", "--allow-all"),
        ],
    )
    def test_profile_has_auto_approve_cli_flag(
        self, profile_name: str, expected_flag: str
    ) -> None:
        """Each profile with a CLI flag should have it in auto_approve.cli_flag."""
        from synapse.server import load_profile

        profile = load_profile(profile_name)
        auto_approve = profile.get("auto_approve", {})
        assert auto_approve.get("cli_flag") == expected_flag

    def test_opencode_has_env_flag(self) -> None:
        """OpenCode profile should have env_flag instead of cli_flag."""
        from synapse.server import load_profile

        profile = load_profile("opencode")
        auto_approve = profile.get("auto_approve", {})
        assert auto_approve.get("cli_flag") is None
        assert (
            auto_approve.get("env_flag") == "OPENCODE_DANGEROUSLY_SKIP_PERMISSIONS=true"
        )

    @pytest.mark.parametrize(
        "profile_name",
        ["claude", "gemini", "codex", "copilot", "opencode"],
    )
    def test_profile_has_runtime_response(self, profile_name: str) -> None:
        """All profiles should have a runtime_response for WAITING auto-approve."""
        from synapse.server import load_profile

        profile = load_profile(profile_name)
        auto_approve = profile.get("auto_approve", {})
        assert auto_approve.get("runtime_response"), (
            f"Profile {profile_name} missing runtime_response"
        )

    @pytest.mark.parametrize(
        "profile_name",
        ["claude", "gemini", "codex", "copilot", "opencode"],
    )
    def test_profile_auto_approve_uses_defaults(self, profile_name: str) -> None:
        """Profiles should rely on config.py defaults for max_consecutive/cooldown."""
        from synapse.server import load_profile

        profile = load_profile(profile_name)
        auto_approve = profile.get("auto_approve", {})
        # max_consecutive and cooldown should NOT be in profile (use defaults)
        assert "max_consecutive" not in auto_approve
        assert "cooldown" not in auto_approve


# ============================================================
# TestDefaultConfigUnlimited — verify unlimited defaults
# ============================================================


class TestDefaultConfigUnlimited:
    """Verify config.py defaults allow unlimited auto-approve."""

    def test_default_max_consecutive_is_unlimited(self) -> None:
        """AUTO_APPROVE_MAX_CONSECUTIVE should be 0 (unlimited)."""
        from synapse.config import AUTO_APPROVE_MAX_CONSECUTIVE

        assert AUTO_APPROVE_MAX_CONSECUTIVE == 0

    def test_default_cooldown_is_zero(self) -> None:
        """AUTO_APPROVE_COOLDOWN should be 0.0 (no cooldown)."""
        from synapse.config import AUTO_APPROVE_COOLDOWN

        assert AUTO_APPROVE_COOLDOWN == 0.0


# ============================================================
# TestUnlimitedApprovals — unlimited auto-approve behavior
# ============================================================


class TestUnlimitedApprovals:
    """When max_consecutive=0, auto-approve should be unlimited."""

    def test_unlimited_approvals_when_max_zero(self) -> None:
        """max_consecutive=0 should allow unlimited approvals."""
        ctrl = _make_controller(
            auto_approve={
                "runtime_response": "y\\r",
                "max_consecutive": 0,
                "cooldown": 0.0,
            }
        )
        with patch.object(ctrl, "write") as mock_write:
            for _ in range(50):
                ctrl._handle_auto_approve("PROCESSING", "WAITING")

        assert mock_write.call_count == 50
        assert ctrl._auto_approve_stopped is False

    def test_explicit_limit_still_works(self) -> None:
        """Explicit max_consecutive > 0 should still enforce the limit."""
        ctrl = _make_controller(
            auto_approve={
                "runtime_response": "y\\r",
                "max_consecutive": 5,
                "cooldown": 0.0,
            }
        )
        with patch.object(ctrl, "write") as mock_write:
            for _ in range(10):
                ctrl._handle_auto_approve("PROCESSING", "WAITING")

        assert mock_write.call_count == 5
        assert ctrl._auto_approve_stopped is True


# ============================================================
# TestWaitingDetectionPatterns — regex vs actual approval text
# ============================================================


class TestWaitingDetectionPatterns:
    """Verify waiting_detection regex matches actual approval prompt output."""

    @pytest.mark.parametrize(
        "profile_name,sample_outputs",
        [
            (
                "codex",
                [
                    "› 1. Yes, proceed (y)",
                    "Yes, and don't ask again for commands that start with `ls`",
                    "No, and tell Codex what to do differently",
                    "Press Enter to confirm or Esc to cancel",
                    "Press enter to confirm or Esc to cancel",
                    "Would you like to run the following command?",
                    "Would you like to make the following edits?",
                ],
            ),
            (
                "gemini",
                [
                    "● 1. Allow once",
                    "Allow for this session",
                    "No, suggest changes (esc)",
                    "Apply this change?",
                    "Do you want to proceed?",
                    "Allow for this file in all future sessions",
                ],
            ),
            (
                "opencode",
                [
                    "Permission Required",
                    "Allow (a)",
                    "Allow for session (s)",
                    "Deny (d)",
                ],
            ),
            (
                "copilot",
                [
                    "approve touch for the rest of the running session",
                    "No, and tell Copilot what to do differently",
                ],
            ),
            (
                "claude",
                [
                    "❯ Allow tool use",
                    "☐ Read file",
                    "[Y/n]",
                ],
            ),
        ],
    )
    def test_regex_matches_approval_prompts(
        self, profile_name: str, sample_outputs: list[str]
    ) -> None:
        """Profile regex should match known approval prompt text."""
        import re

        from synapse.server import load_profile

        profile = load_profile(profile_name)
        waiting = profile.get("waiting_detection", {})
        regex_str = waiting.get("regex")
        assert regex_str, f"Profile {profile_name} has no waiting_detection regex"

        pattern = re.compile(regex_str, re.MULTILINE)
        for sample in sample_outputs:
            assert pattern.search(sample), (
                f"Profile {profile_name} regex did not match: {sample!r}"
            )

    @pytest.mark.parametrize(
        "profile_name,normal_outputs",
        [
            (
                "codex",
                [
                    "I'll create a hello.py file for you.",
                    "Running: python hello.py",
                    "Output: Hello, world!",
                ],
            ),
            (
                "gemini",
                [
                    "I'll help you with that task.",
                    "Creating the file now...",
                    "Done! The file has been created.",
                ],
            ),
            (
                "opencode",
                [
                    "Let me analyze this code.",
                    "The function looks correct.",
                    "I've made the changes.",
                ],
            ),
        ],
    )
    def test_regex_does_not_match_normal_output(
        self, profile_name: str, normal_outputs: list[str]
    ) -> None:
        """Profile regex should NOT match normal conversation output."""
        import re

        from synapse.server import load_profile

        profile = load_profile(profile_name)
        waiting = profile.get("waiting_detection", {})
        regex_str = waiting.get("regex")
        pattern = re.compile(regex_str, re.MULTILINE)

        for text in normal_outputs:
            assert not pattern.search(text), (
                f"Profile {profile_name} regex false-positive on: {text!r}"
            )


# ============================================================
# TestWaitingStateDetection — _check_waiting_state integration
# ============================================================


class TestWaitingStateDetection:
    """Verify _check_waiting_state detects WAITING from PTY-like output."""

    def test_plain_text_detected(self) -> None:
        """Plain approval text should be detected as WAITING."""
        ctrl = _make_controller(
            waiting_detection={
                "regex": "Yes, proceed|Press [Ee]nter to confirm",
                "require_idle": False,
            }
        )
        result = ctrl._check_waiting_state(b"Yes, proceed")
        assert result is True

    def test_ansi_wrapped_text_detected(self) -> None:
        """Approval text wrapped in ANSI escape sequences should be detected."""
        ctrl = _make_controller(
            waiting_detection={
                "regex": "Yes, proceed|Allow once",
                "require_idle": False,
            }
        )
        # Simulate ratatui/Ink output with ANSI color codes
        ansi_data = b"\x1b[38;5;2m\xe2\x80\xba \x1b[0m1. \x1b[1mYes, proceed\x1b[0m (y)"
        result = ctrl._check_waiting_state(ansi_data)
        assert result is True

    def test_ansi_color_between_words_detected(self) -> None:
        """ANSI codes inserted between words should not break detection."""
        ctrl = _make_controller(
            waiting_detection={
                "regex": "Allow once|Permission Required",
                "require_idle": False,
            }
        )
        # "Allow once" with color reset between words
        ansi_data = b"\x1b[32mAllow\x1b[0m \x1b[1monce\x1b[0m"
        result = ctrl._check_waiting_state(ansi_data)
        assert result is True

    def test_no_match_returns_false(self) -> None:
        """Non-matching output should return False."""
        ctrl = _make_controller(
            waiting_detection={
                "regex": "Yes, proceed|Allow once",
                "require_idle": False,
            }
        )
        result = ctrl._check_waiting_state(b"Creating file hello.py...")
        assert result is False

    def test_empty_data_returns_false(self) -> None:
        """Empty data should return False."""
        ctrl = _make_controller(
            waiting_detection={
                "regex": "Yes, proceed",
                "require_idle": False,
            }
        )
        result = ctrl._check_waiting_state(b"")
        assert result is False
