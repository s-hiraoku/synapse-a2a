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

# ============================================================
# TestControllerAutoApprove — runtime WAITING auto-response
# ============================================================


class TestControllerAutoApprove:
    """TerminalController auto-approve callback tests."""

    def _make_controller(self, auto_approve: dict | None = None):
        """Create a TerminalController with mocked dependencies."""
        from synapse.controller import TerminalController

        with patch("synapse.controller.AgentRegistry"):
            ctrl = TerminalController(
                command="echo",
                auto_approve=auto_approve,
            )
        return ctrl

    def test_auto_approve_enabled_registers_callback(self) -> None:
        """When auto_approve config is provided, a status callback is registered."""
        ctrl = self._make_controller(
            auto_approve={"runtime_response": "y\\r", "max_consecutive": 5}
        )
        assert ctrl._auto_approve_enabled is True
        assert len(ctrl._status_callbacks) == 1

    def test_auto_approve_disabled_no_callback(self) -> None:
        """When auto_approve is None, no callback is registered."""
        ctrl = self._make_controller(auto_approve=None)
        assert ctrl._auto_approve_enabled is False
        assert len(ctrl._status_callbacks) == 0

    def test_auto_approve_empty_config_no_callback(self) -> None:
        """Empty auto_approve config should not enable auto-approve."""
        ctrl = self._make_controller(auto_approve={})
        assert ctrl._auto_approve_enabled is False

    def test_callback_fires_on_waiting(self) -> None:
        """Callback should call write() when status transitions to WAITING."""
        ctrl = self._make_controller(
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
        ctrl = self._make_controller(
            auto_approve={"runtime_response": "y\\r", "cooldown": 0.0}
        )
        with patch.object(ctrl, "write") as mock_write:
            ctrl._handle_auto_approve("PROCESSING", "READY")
            ctrl._handle_auto_approve("READY", "PROCESSING")
            ctrl._handle_auto_approve("PROCESSING", "DONE")
        mock_write.assert_not_called()

    def test_cooldown_enforced(self) -> None:
        """Second WAITING within cooldown period should be skipped."""
        ctrl = self._make_controller(
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
        ctrl = self._make_controller(
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
        ctrl = self._make_controller(
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
        ctrl = self._make_controller(
            auto_approve={"runtime_response": "y\\r", "cooldown": 0.0}
        )
        # "y\\r" in YAML → "y\r" (actual carriage return)
        assert ctrl._auto_approve_response == "y\r"

    def test_enter_only_response(self) -> None:
        """Gemini profile uses just Enter (\\r) as runtime_response."""
        ctrl = self._make_controller(
            auto_approve={"runtime_response": "\\r", "cooldown": 0.0}
        )
        assert ctrl._auto_approve_response == "\r"

    def test_numbered_response(self) -> None:
        """Copilot profile uses '1\\r' as runtime_response."""
        ctrl = self._make_controller(
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
            ("claude", "--dangerously-skip-permissions"),
            ("gemini", "--yolo"),
            ("codex", "--full-auto"),
            ("copilot", "--yolo"),
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
