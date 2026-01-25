"""Tests for Compliance / Permissions Spec (Issue #159).

This module tests the compliance and permission control system for synapse-a2a,
implementing the specification from Issue #159.

Specification summary:
- 3 modes: manual, prefill, auto
- Provider-level configuration: claude, codex, gemini, opencode, copilot
- Mode → capability mapping (inject, submit, confirm, route)
- Hierarchical settings: user (~/.synapse) + project (.synapse)
- Warning banner display based on ui.warningBanner setting

Path conventions:
- load() accepts project_root (directory), not file path
- Settings file is always at <project_root>/.synapse/settings.json
"""

import json
import logging
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# =============================================================================
# Helper Functions
# =============================================================================


def create_settings_file(base_dir: Path, settings: dict) -> Path:
    """Create .synapse/settings.json in the given base directory.

    Args:
        base_dir: The project root or user home directory.
        settings: Settings dictionary to write.

    Returns:
        Path to the created settings.json file.
    """
    synapse_dir = base_dir / ".synapse"
    synapse_dir.mkdir(parents=True, exist_ok=True)
    settings_path = synapse_dir / "settings.json"
    settings_path.write_text(json.dumps(settings))
    return settings_path


# =============================================================================
# Tests for Mode Definition (Section 5)
# =============================================================================


class TestModeDefinition:
    """Test mode definitions and capability mappings."""

    def test_mode_values_are_valid(self):
        """Only 'manual', 'prefill', 'auto' are valid mode values."""
        from synapse.compliance import ComplianceMode

        assert ComplianceMode.MANUAL.value == "manual"
        assert ComplianceMode.PREFILL.value == "prefill"
        assert ComplianceMode.AUTO.value == "auto"

    def test_mode_capability_mapping_manual(self):
        """manual mode: all capabilities disabled."""
        from synapse.compliance import get_mode_capabilities

        caps = get_mode_capabilities("manual")
        assert caps["inject"] is False
        assert caps["submit"] is False
        assert caps["confirm"] is False
        assert caps["route"] is False

    def test_mode_capability_mapping_prefill(self):
        """prefill mode: only inject enabled."""
        from synapse.compliance import get_mode_capabilities

        caps = get_mode_capabilities("prefill")
        assert caps["inject"] is True
        assert caps["submit"] is False
        assert caps["confirm"] is False
        assert caps["route"] is False

    def test_mode_capability_mapping_auto(self):
        """auto mode: all capabilities enabled."""
        from synapse.compliance import get_mode_capabilities

        caps = get_mode_capabilities("auto")
        assert caps["inject"] is True
        assert caps["submit"] is True
        assert caps["confirm"] is True
        assert caps["route"] is True


# =============================================================================
# Tests for Provider Model (Section 6)
# =============================================================================


class TestProviderModel:
    """Test provider identification and handling."""

    def test_known_providers(self):
        """Known providers: claude, codex, gemini, opencode, copilot."""
        from synapse.compliance import KNOWN_PROVIDERS

        assert "claude" in KNOWN_PROVIDERS
        assert "codex" in KNOWN_PROVIDERS
        assert "gemini" in KNOWN_PROVIDERS
        assert "opencode" in KNOWN_PROVIDERS
        assert "copilot" in KNOWN_PROVIDERS
        assert len(KNOWN_PROVIDERS) == 5

    def test_unknown_provider_warning(self, caplog: pytest.LogCaptureFixture):
        """Unknown provider names should trigger a warning."""
        from synapse.compliance import ComplianceSettings

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            create_settings_file(
                project_root,
                {
                    "defaultMode": "auto",
                    "providers": {"unknown_agent": {"mode": "manual"}},
                },
            )

            with caplog.at_level(logging.WARNING):
                ComplianceSettings.load(project_root=project_root)

            assert "unknown_agent" in caplog.text

    def test_unknown_provider_still_works(self):
        """Unknown providers should still be read (for future compatibility)."""
        from synapse.compliance import ComplianceSettings

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            create_settings_file(
                project_root,
                {
                    "defaultMode": "auto",
                    "providers": {"future_agent": {"mode": "prefill"}},
                },
            )

            settings = ComplianceSettings.load(project_root=project_root)
            # Should still respect the configured mode
            assert settings.get_effective_mode("future_agent") == "prefill"


# =============================================================================
# Tests for Settings File (Section 7)
# =============================================================================


class TestSettingsFile:
    """Test settings file loading and schema."""

    def test_default_mode_fallback(self):
        """defaultMode defaults to 'auto' when not specified."""
        from synapse.compliance import ComplianceSettings

        # Empty directory (no settings file)
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            # Don't create settings file - use defaults

            settings = ComplianceSettings.load(
                user_root=project_root / "user",  # Non-existent
                project_root=project_root / "project",  # Non-existent
            )
            assert settings.default_mode == "auto"

    def test_default_mode_explicit(self):
        """Explicit defaultMode is respected."""
        from synapse.compliance import ComplianceSettings

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            create_settings_file(project_root, {"defaultMode": "manual"})

            settings = ComplianceSettings.load(project_root=project_root)
            assert settings.default_mode == "manual"

    def test_provider_override(self):
        """Provider-specific mode overrides defaultMode."""
        from synapse.compliance import ComplianceSettings

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
            assert settings.get_effective_mode("claude") == "auto"
            assert settings.get_effective_mode("codex") == "manual"

    def test_effective_mode_resolution_priority(self):
        """Effective mode: provider.mode > defaultMode > 'auto'."""
        from synapse.compliance import ComplianceSettings

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            create_settings_file(
                project_root,
                {
                    "defaultMode": "prefill",
                    "providers": {
                        "claude": {"mode": "auto"},
                        # codex not specified, should use defaultMode
                    },
                },
            )

            settings = ComplianceSettings.load(project_root=project_root)
            assert settings.get_effective_mode("claude") == "auto"  # explicit
            assert settings.get_effective_mode("codex") == "prefill"  # defaultMode
            assert settings.get_effective_mode("gemini") == "prefill"  # defaultMode

    def test_hierarchical_merge_user_and_project(self):
        """Project settings override user settings."""
        from synapse.compliance import ComplianceSettings

        with tempfile.TemporaryDirectory() as tmpdir:
            user_root = Path(tmpdir) / "user_home"
            user_root.mkdir()
            create_settings_file(
                user_root,
                {
                    "defaultMode": "manual",
                    "providers": {"claude": {"mode": "prefill"}},
                },
            )

            project_root = Path(tmpdir) / "project"
            project_root.mkdir()
            create_settings_file(
                project_root,
                {
                    "providers": {"claude": {"mode": "auto"}},
                },
            )

            settings = ComplianceSettings.load(
                user_root=user_root,
                project_root=project_root,
            )
            # Project overrides user for claude
            assert settings.get_effective_mode("claude") == "auto"
            # defaultMode comes from user (not overridden in project)
            assert settings.default_mode == "manual"

    def test_warning_banner_settings(self):
        """ui.warningBanner setting: always, autoOnly, off."""
        from synapse.compliance import ComplianceSettings

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Test 'always'
            create_settings_file(project_root, {"ui": {"warningBanner": "always"}})
            settings = ComplianceSettings.load(project_root=project_root)
            assert settings.warning_banner == "always"

            # Test 'autoOnly'
            create_settings_file(project_root, {"ui": {"warningBanner": "autoOnly"}})
            settings = ComplianceSettings.load(project_root=project_root)
            assert settings.warning_banner == "autoOnly"

            # Test 'off'
            create_settings_file(project_root, {"ui": {"warningBanner": "off"}})
            settings = ComplianceSettings.load(project_root=project_root)
            assert settings.warning_banner == "off"

    def test_warning_banner_default(self):
        """ui.warningBanner defaults to 'always'."""
        from synapse.compliance import ComplianceSettings

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            # Empty settings
            create_settings_file(project_root, {})

            settings = ComplianceSettings.load(project_root=project_root)
            assert settings.warning_banner == "always"


# =============================================================================
# Tests for Warning Banner Display (Section 8)
# =============================================================================


class TestWarningBanner:
    """Test warning banner display logic."""

    def test_should_show_banner_always(self):
        """Banner shows when warningBanner='always'."""
        from synapse.compliance import ComplianceSettings

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            create_settings_file(
                project_root,
                {
                    "defaultMode": "manual",  # No auto providers
                    "ui": {"warningBanner": "always"},
                },
            )

            settings = ComplianceSettings.load(project_root=project_root)
            assert settings.should_show_banner() is True

    def test_should_show_banner_auto_only_with_auto(self):
        """Banner shows when warningBanner='autoOnly' and has auto providers."""
        from synapse.compliance import ComplianceSettings

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            create_settings_file(
                project_root,
                {
                    "defaultMode": "auto",  # Has auto
                    "ui": {"warningBanner": "autoOnly"},
                },
            )

            settings = ComplianceSettings.load(project_root=project_root)
            assert settings.should_show_banner() is True

    def test_should_show_banner_auto_only_without_auto(self):
        """Banner hidden when warningBanner='autoOnly' and no auto providers."""
        from synapse.compliance import ComplianceSettings

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            create_settings_file(
                project_root,
                {
                    "defaultMode": "manual",  # No auto
                    "ui": {"warningBanner": "autoOnly"},
                },
            )

            settings = ComplianceSettings.load(project_root=project_root)
            assert settings.should_show_banner() is False

    def test_should_show_banner_off(self):
        """Banner hidden when warningBanner='off'."""
        from synapse.compliance import ComplianceSettings

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            create_settings_file(
                project_root,
                {
                    "defaultMode": "auto",  # Has auto
                    "ui": {"warningBanner": "off"},
                },
            )

            settings = ComplianceSettings.load(project_root=project_root)
            assert settings.should_show_banner() is False

    def test_get_banner_data_includes_required_info(self):
        """Banner data includes defaultMode, provider modes, capabilities."""
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
                    "ui": {"warningBanner": "always"},
                },
            )

            settings = ComplianceSettings.load(project_root=project_root)
            data = settings.get_banner_data()

            # Should include default mode
            assert data["default_mode"] == "auto"
            # Should include provider overrides
            assert data["provider_overrides"]["claude"] == "prefill"
            assert data["provider_overrides"]["codex"] == "manual"
            # Should include capabilities for default mode
            assert "capabilities" in data

    def test_format_banner_contains_key_info(self):
        """format_banner() output contains key information."""
        from synapse.compliance import ComplianceSettings

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            create_settings_file(
                project_root,
                {
                    "defaultMode": "auto",
                    "providers": {
                        "claude": {"mode": "prefill"},
                    },
                },
            )

            settings = ComplianceSettings.load(project_root=project_root)
            banner = settings.format_banner().lower()

            # Check key elements are present (case-insensitive)
            assert "auto" in banner
            assert "claude" in banner
            assert "prefill" in banner


# =============================================================================
# Tests for Policy Engine (Section 10)
# =============================================================================


class TestPolicyEngine:
    """Test Policy Engine action types and decisions."""

    def test_action_types_exist(self):
        """All specified action types should exist."""
        from synapse.compliance import ActionType

        assert ActionType.PROPOSE_PROMPT
        assert ActionType.INJECT_INPUT
        assert ActionType.SUBMIT_INPUT
        assert ActionType.AUTO_CONFIRM
        assert ActionType.ROUTE_OUTPUT
        assert ActionType.EXEC_TOOL

    def test_decision_types_exist(self):
        """Decision types: ALLOW, REQUIRE_HUMAN, DENY."""
        from synapse.compliance import Decision

        assert Decision.ALLOW
        assert Decision.REQUIRE_HUMAN
        assert Decision.DENY

    def test_policy_engine_manual_mode(self):
        """Manual mode denies inject, submit, confirm, route."""
        from synapse.compliance import ActionType, Decision, PolicyEngine

        engine = PolicyEngine(mode="manual")

        assert engine.check(ActionType.INJECT_INPUT) == Decision.DENY
        assert engine.check(ActionType.SUBMIT_INPUT) == Decision.DENY
        assert engine.check(ActionType.AUTO_CONFIRM) == Decision.DENY
        assert engine.check(ActionType.ROUTE_OUTPUT) == Decision.DENY
        # PROPOSE_PROMPT is always allowed (display only)
        assert engine.check(ActionType.PROPOSE_PROMPT) == Decision.ALLOW

    def test_policy_engine_prefill_mode(self):
        """Prefill mode allows inject, denies submit/confirm/route."""
        from synapse.compliance import ActionType, Decision, PolicyEngine

        engine = PolicyEngine(mode="prefill")

        assert engine.check(ActionType.INJECT_INPUT) == Decision.ALLOW
        assert engine.check(ActionType.SUBMIT_INPUT) == Decision.DENY
        assert engine.check(ActionType.AUTO_CONFIRM) == Decision.DENY
        assert engine.check(ActionType.ROUTE_OUTPUT) == Decision.DENY

    def test_policy_engine_auto_mode(self):
        """Auto mode allows all actions."""
        from synapse.compliance import ActionType, Decision, PolicyEngine

        engine = PolicyEngine(mode="auto")

        assert engine.check(ActionType.INJECT_INPUT) == Decision.ALLOW
        assert engine.check(ActionType.SUBMIT_INPUT) == Decision.ALLOW
        assert engine.check(ActionType.AUTO_CONFIRM) == Decision.ALLOW
        assert engine.check(ActionType.ROUTE_OUTPUT) == Decision.ALLOW

    def test_policy_engine_for_provider(self):
        """PolicyEngine.for_provider() uses provider-specific mode."""
        from synapse.compliance import (
            ActionType,
            ComplianceSettings,
            Decision,
            PolicyEngine,
        )

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

            # Claude uses auto (default)
            claude_engine = PolicyEngine.for_provider("claude", settings)
            assert claude_engine.check(ActionType.SUBMIT_INPUT) == Decision.ALLOW

            # Codex uses manual
            codex_engine = PolicyEngine.for_provider("codex", settings)
            assert codex_engine.check(ActionType.SUBMIT_INPUT) == Decision.DENY

    def test_policy_engine_mode_and_for_provider_both_supported(self):
        """Both PolicyEngine(mode=...) and for_provider() are valid."""
        from synapse.compliance import (
            ActionType,
            ComplianceSettings,
            Decision,
            PolicyEngine,
        )

        # Direct mode construction
        engine1 = PolicyEngine(mode="prefill")
        assert engine1.check(ActionType.INJECT_INPUT) == Decision.ALLOW

        # Via for_provider with settings
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            create_settings_file(project_root, {"defaultMode": "prefill"})
            settings = ComplianceSettings.load(project_root=project_root)

            engine2 = PolicyEngine.for_provider("claude", settings)
            assert engine2.check(ActionType.INJECT_INPUT) == Decision.ALLOW


# =============================================================================
# Tests for Prefill Mode UX (Section 9.2)
# =============================================================================


class TestPrefillMode:
    """Test prefill mode constraints."""

    def test_prefill_cannot_inject_newline(self):
        """Prefill mode must not inject newlines (prevents auto-submit)."""
        from synapse.compliance import ActionType, Decision, PolicyEngine

        engine = PolicyEngine(mode="prefill")

        # Check that newline/submit is denied
        assert engine.check(ActionType.SUBMIT_INPUT) == Decision.DENY

    def test_prefill_cannot_auto_confirm(self):
        """Prefill mode must not auto-confirm y/n prompts."""
        from synapse.compliance import ActionType, Decision, PolicyEngine

        engine = PolicyEngine(mode="prefill")
        assert engine.check(ActionType.AUTO_CONFIRM) == Decision.DENY


# =============================================================================
# Tests for Manual Mode UX (Section 9.3)
# =============================================================================


class TestManualMode:
    """Test manual mode constraints."""

    def test_manual_cannot_write_to_pty(self):
        """Manual mode must not write to PTY (stdin)."""
        from synapse.compliance import ActionType, Decision, PolicyEngine

        engine = PolicyEngine(mode="manual")

        assert engine.check(ActionType.INJECT_INPUT) == Decision.DENY
        assert engine.check(ActionType.SUBMIT_INPUT) == Decision.DENY

    def test_manual_allows_propose_prompt(self):
        """Manual mode allows displaying proposed prompts."""
        from synapse.compliance import ActionType, Decision, PolicyEngine

        engine = PolicyEngine(mode="manual")
        assert engine.check(ActionType.PROPOSE_PROMPT) == Decision.ALLOW


# =============================================================================
# Tests for Integration with Existing Settings
# =============================================================================


class TestSettingsIntegration:
    """Test integration with existing SynapseSettings."""

    def test_compliance_coexists_with_a2a_flow(self):
        """Compliance settings coexist with a2a.flow setting."""
        from synapse.compliance import ComplianceSettings

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            create_settings_file(
                project_root,
                {
                    "a2a": {"flow": "roundtrip"},
                    "defaultMode": "prefill",
                },
            )

            settings = ComplianceSettings.load(project_root=project_root)
            assert settings.default_mode == "prefill"
            # a2a.flow should be preserved (not affected)

    def test_missing_new_keys_use_defaults(self):
        """Existing settings without new keys use defaults."""
        from synapse.compliance import ComplianceSettings

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            # Old settings format without compliance keys
            create_settings_file(
                project_root,
                {
                    "env": {"SYNAPSE_HISTORY_ENABLED": "true"},
                    "a2a": {"flow": "auto"},
                },
            )

            settings = ComplianceSettings.load(project_root=project_root)
            # Should use defaults
            assert settings.default_mode == "auto"
            assert settings.warning_banner == "always"


# =============================================================================
# Tests for Template Settings
# =============================================================================


class TestTemplateSettings:
    """Test template settings.json for synapse init."""

    def test_template_has_compliance_keys(self):
        """Template settings.json should include compliance keys."""
        template_path = (
            Path(__file__).parent.parent
            / "synapse"
            / "templates"
            / ".synapse"
            / "settings.json"
        )

        if template_path.exists():
            with open(template_path) as f:
                template = json.load(f)

            # Should have compliance keys
            assert "defaultMode" in template
            assert "ui" in template
            assert "warningBanner" in template.get("ui", {})


# =============================================================================
# Tests for Clipboard Integration (Manual Mode)
# =============================================================================


class TestClipboardIntegration:
    """Test clipboard integration for manual mode."""

    def test_copy_to_clipboard_available(self):
        """Clipboard copy function should be available."""
        from synapse.compliance import copy_to_clipboard

        # Should not raise
        assert callable(copy_to_clipboard)

    def test_copy_to_clipboard_uses_pyperclip(self):
        """copy_to_clipboard should use pyperclip."""
        import synapse.compliance as compliance_module

        mock_pyperclip = type("MockPyperclip", (), {"copy": lambda self, x: None})()

        # Reset cached pyperclip and inject mock
        original = compliance_module.pyperclip
        compliance_module.pyperclip = mock_pyperclip

        try:
            with patch.object(mock_pyperclip, "copy") as mock_copy:
                from synapse.compliance import copy_to_clipboard

                copy_to_clipboard("test content")
                mock_copy.assert_called_with("test content")
        finally:
            compliance_module.pyperclip = original

    def test_copy_to_clipboard_handles_error(self):
        """copy_to_clipboard should handle pyperclip errors gracefully."""
        import synapse.compliance as compliance_module

        mock_pyperclip = type("MockPyperclip", (), {})()
        mock_pyperclip.copy = lambda x: (_ for _ in ()).throw(  # type: ignore
            Exception("Clipboard unavailable")
        )

        original = compliance_module.pyperclip
        compliance_module.pyperclip = mock_pyperclip

        try:
            from synapse.compliance import copy_to_clipboard

            # Should not raise, just return False
            result = copy_to_clipboard("test content")
            assert result is False
        finally:
            compliance_module.pyperclip = original
