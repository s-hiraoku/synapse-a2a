"""Integration tests for Compliance / Permissions Spec (Issue #159).

Tests controller integration and banner display in various scenarios.
"""

import json
import logging
import tempfile
from io import StringIO
from pathlib import Path

import pytest


def create_settings_file(base_dir: Path, settings: dict) -> Path:
    """Create .synapse/settings.json in the given base directory."""
    synapse_dir = base_dir / ".synapse"
    synapse_dir.mkdir(parents=True, exist_ok=True)
    settings_path = synapse_dir / "settings.json"
    settings_path.write_text(json.dumps(settings))
    return settings_path


class TestControllerIntegration:
    """Test compliance integration with TerminalController."""

    def test_controller_respects_mode_on_inject(self):
        """Controller should check policy before injecting input."""
        from synapse.compliance import (
            ActionType,
            ComplianceSettings,
            Decision,
            PolicyEngine,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            create_settings_file(project_root, {"defaultMode": "manual"})

            settings = ComplianceSettings.load(project_root=project_root)
            engine = PolicyEngine.for_provider("claude", settings)

            # In manual mode, inject should be denied
            assert engine.check(ActionType.INJECT_INPUT) == Decision.DENY

    def test_controller_allows_inject_in_auto_mode(self):
        """Controller allows input injection in auto mode."""
        from synapse.compliance import (
            ActionType,
            ComplianceSettings,
            Decision,
            PolicyEngine,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            create_settings_file(project_root, {"defaultMode": "auto"})

            settings = ComplianceSettings.load(project_root=project_root)
            engine = PolicyEngine.for_provider("claude", settings)

            assert engine.check(ActionType.INJECT_INPUT) == Decision.ALLOW

    def test_controller_allows_inject_denies_submit_in_prefill(self):
        """Controller allows inject but denies submit in prefill mode."""
        from synapse.compliance import (
            ActionType,
            ComplianceSettings,
            Decision,
            PolicyEngine,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            create_settings_file(project_root, {"defaultMode": "prefill"})

            settings = ComplianceSettings.load(project_root=project_root)
            engine = PolicyEngine.for_provider("claude", settings)

            assert engine.check(ActionType.INJECT_INPUT) == Decision.ALLOW
            assert engine.check(ActionType.SUBMIT_INPUT) == Decision.DENY


class TestBannerDisplayIntegration:
    """Test banner display integration with synapse list and startup."""

    def test_banner_format_for_auto_mode(self):
        """Banner shows AUTO mode with capabilities."""
        from synapse.compliance import ComplianceSettings

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            create_settings_file(project_root, {"defaultMode": "auto"})

            settings = ComplianceSettings.load(project_root=project_root)
            banner = settings.format_banner().lower()

            assert "auto" in banner
            # Should show enabled capabilities
            assert "inject" in banner
            assert "submit" in banner

    def test_banner_format_for_mixed_modes(self):
        """Banner shows mixed modes clearly."""
        from synapse.compliance import ComplianceSettings

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            create_settings_file(
                project_root,
                {
                    "defaultMode": "auto",
                    "providers": {
                        "claude": {"mode": "prefill"},
                        "codex": {"mode": "manual"},
                    },
                },
            )

            settings = ComplianceSettings.load(project_root=project_root)
            data = settings.get_banner_data()

            # Verify data structure instead of string format
            assert data["default_mode"] == "auto"
            assert data["provider_overrides"]["claude"] == "prefill"
            assert data["provider_overrides"]["codex"] == "manual"

    def test_banner_rich_panel_rendering(self):
        """Banner can be rendered as Rich Panel."""
        from rich.console import Console

        from synapse.compliance import ComplianceSettings

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            create_settings_file(project_root, {"defaultMode": "auto"})

            settings = ComplianceSettings.load(project_root=project_root)
            banner_panel = settings.format_banner_panel()

            # Should be renderable by Rich
            output = StringIO()
            console = Console(file=output, force_terminal=True, width=100)
            console.print(banner_panel)

            rendered = output.getvalue()
            assert len(rendered) > 0  # Should produce output


class TestPrefillNotification:
    """Test prefill mode notification to user."""

    def test_prefill_notification_message(self):
        """Prefill notification message is properly formatted."""
        from synapse.compliance import format_prefill_notification

        msg = format_prefill_notification("Hello world")
        msg_lower = msg.lower()
        # Should mention prefill or enter
        assert "prefill" in msg_lower or "enter" in msg_lower or "press" in msg_lower

    def test_prefill_notification_includes_content_preview(self):
        """Prefill notification may include content preview."""
        from synapse.compliance import format_prefill_notification

        msg = format_prefill_notification("Test content here")
        # Notification should give user context
        assert len(msg) > 0


class TestManualModeClipboard:
    """Test manual mode clipboard functionality."""

    def test_manual_mode_format_display(self):
        """Manual mode displays prompt in readable format."""
        from synapse.compliance import format_manual_display

        content = "synapse send gemini 'Hello' --from claude"
        display = format_manual_display(content)

        # Should include the content or reference to it
        assert len(display) > 0
        # Should mention clipboard
        display_lower = display.lower()
        assert "clipboard" in display_lower or "copied" in display_lower

    def test_manual_mode_format_display_clipboard_failed(self):
        """Manual mode shows appropriate message when clipboard fails."""
        from synapse.compliance import format_manual_display

        content = "test command"
        display = format_manual_display(content, clipboard_success=False)

        # Should mention clipboard unavailable
        display_lower = display.lower()
        assert "unavailable" in display_lower or "copy" in display_lower


class TestConfigTUIIntegration:
    """Test integration with synapse config TUI."""

    def test_compliance_section_schema(self):
        """Compliance settings have proper schema for TUI."""
        from synapse.compliance import get_compliance_schema

        schema = get_compliance_schema()

        # Should have mode field
        assert "defaultMode" in schema
        assert schema["defaultMode"]["type"] == "enum"
        assert set(schema["defaultMode"]["values"]) == {"auto", "prefill", "manual"}

        # Should have provider settings
        assert "providers" in schema

        # Should have UI settings
        assert "ui" in schema
        assert "warningBanner" in schema["ui"]


class TestStartupLogging:
    """Test compliance banner in startup logs."""

    def test_startup_log_includes_banner(self, caplog: pytest.LogCaptureFixture):
        """Startup should log compliance banner."""
        from synapse.compliance import ComplianceSettings, log_compliance_banner

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            create_settings_file(project_root, {"defaultMode": "auto"})

            settings = ComplianceSettings.load(project_root=project_root)

            with caplog.at_level(logging.INFO):
                log_compliance_banner(settings)

            # Should log mode info
            assert "auto" in caplog.text.lower() or "mode" in caplog.text.lower()

    def test_startup_log_shows_provider_overrides(
        self, caplog: pytest.LogCaptureFixture
    ):
        """Startup log shows provider-specific modes."""
        from synapse.compliance import ComplianceSettings, log_compliance_banner

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            create_settings_file(
                project_root,
                {
                    "defaultMode": "auto",
                    "providers": {"codex": {"mode": "manual"}},
                },
            )

            settings = ComplianceSettings.load(project_root=project_root)

            with caplog.at_level(logging.INFO):
                log_compliance_banner(settings)

            # Should mention codex override
            assert "codex" in caplog.text.lower()


class TestRouteOutputControl:
    """Test route output (A2A routing) control."""

    def test_route_blocked_in_manual_mode(self):
        """Routing is blocked in manual mode."""
        from synapse.compliance import ActionType, Decision, PolicyEngine

        engine = PolicyEngine(mode="manual")
        assert engine.check(ActionType.ROUTE_OUTPUT) == Decision.DENY

    def test_route_blocked_in_prefill_mode(self):
        """Routing is blocked in prefill mode."""
        from synapse.compliance import ActionType, Decision, PolicyEngine

        engine = PolicyEngine(mode="prefill")
        assert engine.check(ActionType.ROUTE_OUTPUT) == Decision.DENY

    def test_route_allowed_in_auto_mode(self):
        """Routing is allowed in auto mode."""
        from synapse.compliance import ActionType, Decision, PolicyEngine

        engine = PolicyEngine(mode="auto")
        assert engine.check(ActionType.ROUTE_OUTPUT) == Decision.ALLOW


class TestExecToolControl:
    """Test EXEC_TOOL action type."""

    def test_exec_tool_follows_mode(self):
        """EXEC_TOOL follows same rules as other actions."""
        from synapse.compliance import ActionType, Decision, PolicyEngine

        # Auto mode - allowed
        auto_engine = PolicyEngine(mode="auto")
        # EXEC_TOOL behavior may vary based on tool type
        # For now, it follows submit_input rules
        assert auto_engine.check(ActionType.EXEC_TOOL) == Decision.ALLOW

        # Manual mode - denied (requires human intervention)
        manual_engine = PolicyEngine(mode="manual")
        assert manual_engine.check(ActionType.EXEC_TOOL) == Decision.DENY


class TestAutoConfirmControl:
    """Test auto-confirm (y/n prompt) control."""

    def test_auto_confirm_in_different_modes(self):
        """AUTO_CONFIRM follows mode rules."""
        from synapse.compliance import ActionType, Decision, PolicyEngine

        # Auto mode - allowed
        auto_engine = PolicyEngine(mode="auto")
        assert auto_engine.check(ActionType.AUTO_CONFIRM) == Decision.ALLOW

        # Prefill mode - denied
        prefill_engine = PolicyEngine(mode="prefill")
        assert prefill_engine.check(ActionType.AUTO_CONFIRM) == Decision.DENY

        # Manual mode - denied
        manual_engine = PolicyEngine(mode="manual")
        assert manual_engine.check(ActionType.AUTO_CONFIRM) == Decision.DENY


class TestInputRouterCompliance:
    """Test InputRouter compliance integration."""

    def test_input_router_initializes_compliance(self):
        """InputRouter should initialize compliance settings."""
        from synapse.input_router import InputRouter

        router = InputRouter(self_agent_type="claude")

        assert router._compliance_settings is not None
        assert router._policy_engine is not None

    def test_input_router_respects_manual_mode(self):
        """InputRouter should block routing in manual mode."""
        from unittest.mock import patch

        from synapse.compliance import ComplianceSettings
        from synapse.input_router import InputRouter

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            create_settings_file(project_root, {"defaultMode": "manual"})

            # Patch ComplianceSettings.load to use our test settings
            with patch.object(
                ComplianceSettings,
                "load",
                return_value=ComplianceSettings.load(project_root=project_root),
            ):
                router = InputRouter(
                    self_agent_type="claude", self_agent_id="test-claude"
                )
                # Should return False (blocked by compliance)
                result = router.route_to_agent("gemini", "test message")
                assert result is False
                # Should have set last_response indicating compliance block
                assert router.last_response is not None
                assert "compliance" in router.last_response.lower()

    def test_input_router_escapes_message_safely(self):
        """InputRouter should safely escape messages with special characters."""
        from unittest.mock import patch

        from synapse.compliance import ComplianceSettings
        from synapse.input_router import InputRouter

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            create_settings_file(project_root, {"defaultMode": "manual"})

            with patch.object(
                ComplianceSettings,
                "load",
                return_value=ComplianceSettings.load(project_root=project_root),
            ):
                router = InputRouter(
                    self_agent_type="claude", self_agent_id="test-claude"
                )
                # Message with single quotes that could break shell command
                result = router.route_to_agent("gemini", "test's message with 'quotes'")
                assert result is False
                # Message should be escaped safely in last_response
                # The shlex.quote should prevent command injection
                assert router.last_response is not None

    def test_input_router_clipboard_failure_message(self):
        """InputRouter should show correct message when clipboard fails."""
        from unittest.mock import patch

        from synapse.compliance import ComplianceSettings
        from synapse.input_router import InputRouter

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            create_settings_file(project_root, {"defaultMode": "manual"})

            with (
                patch.object(
                    ComplianceSettings,
                    "load",
                    return_value=ComplianceSettings.load(project_root=project_root),
                ),
                patch("synapse.input_router.copy_to_clipboard", return_value=False),
            ):
                router = InputRouter(
                    self_agent_type="claude", self_agent_id="test-claude"
                )
                result = router.route_to_agent("gemini", "test message")
                assert result is False
                # Should mention clipboard unavailable
                assert router.last_response is not None
                assert "unavailable" in router.last_response.lower()


class TestComplianceBlockedError:
    """Test ComplianceBlockedError exception."""

    def test_exception_attributes(self):
        """ComplianceBlockedError should have mode, action, and message."""
        from synapse.compliance import ActionType, ComplianceBlockedError

        err = ComplianceBlockedError(
            mode="manual",
            action=ActionType.INJECT_INPUT,
            message="Test message",
        )

        assert err.mode == "manual"
        assert err.action == ActionType.INJECT_INPUT
        assert err.message == "Test message"
        assert str(err) == "Test message"

    def test_exception_default_message(self):
        """ComplianceBlockedError should generate default message."""
        from synapse.compliance import ActionType, ComplianceBlockedError

        err = ComplianceBlockedError(mode="prefill", action=ActionType.SUBMIT_INPUT)

        assert "prefill" in err.message
        assert "submit_input" in err.message


class TestControllerComplianceException:
    """Test controller raises ComplianceBlockedError."""

    def test_controller_raises_on_manual_mode(self):
        """Controller.write() should raise ComplianceBlockedError in manual mode."""
        from unittest.mock import MagicMock, patch

        from synapse.compliance import (
            ActionType,
            ComplianceBlockedError,
            ComplianceSettings,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            create_settings_file(project_root, {"defaultMode": "manual"})

            with patch.object(
                ComplianceSettings,
                "load",
                return_value=ComplianceSettings.load(project_root=project_root),
            ):
                from synapse.controller import TerminalController

                ctrl = TerminalController(
                    command="echo test",
                    agent_type="claude",
                )
                # Mock master_fd and running state
                ctrl.master_fd = MagicMock()
                ctrl.running = True

                with pytest.raises(ComplianceBlockedError) as exc_info:
                    ctrl.write("test data")

                assert exc_info.value.mode == "manual"
                assert exc_info.value.action == ActionType.INJECT_INPUT
