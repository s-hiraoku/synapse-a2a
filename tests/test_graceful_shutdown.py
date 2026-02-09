"""Tests for B4: Graceful Shutdown feature.

Test-first development: these tests define the expected behavior
for graceful shutdown before implementation.
"""

from __future__ import annotations

import signal
from unittest.mock import MagicMock, patch

import pytest

# ============================================================
# TestShutdownStatus - Status system integration
# ============================================================


class TestShutdownStatus:
    """Tests for SHUTTING_DOWN status constant and its integration."""

    def test_shutting_down_in_all_statuses(self):
        """SHUTTING_DOWN should be a member of ALL_STATUSES."""
        from synapse.status import ALL_STATUSES, SHUTTING_DOWN

        assert SHUTTING_DOWN == "SHUTTING_DOWN"
        assert SHUTTING_DOWN in ALL_STATUSES

    def test_shutting_down_has_style(self):
        """SHUTTING_DOWN should have a display style entry."""
        from synapse.status import SHUTTING_DOWN, STATUS_STYLES

        assert SHUTTING_DOWN in STATUS_STYLES
        # Should be a non-empty string
        assert isinstance(STATUS_STYLES[SHUTTING_DOWN], str)
        assert len(STATUS_STYLES[SHUTTING_DOWN]) > 0

    def test_is_valid_status_accepts_shutting_down(self):
        """is_valid_status() should accept SHUTTING_DOWN."""
        from synapse.status import is_valid_status

        assert is_valid_status("SHUTTING_DOWN") is True

    def test_get_status_style_for_shutting_down(self):
        """get_status_style() should return a style for SHUTTING_DOWN."""
        from synapse.status import get_status_style

        style = get_status_style("SHUTTING_DOWN")
        assert isinstance(style, str)
        assert len(style) > 0


# ============================================================
# TestShutdownSettings - Settings integration
# ============================================================


class TestShutdownSettings:
    """Tests for shutdown settings in DEFAULT_SETTINGS."""

    def test_default_settings_has_shutdown_section(self):
        """DEFAULT_SETTINGS should contain a 'shutdown' section."""
        from synapse.settings import DEFAULT_SETTINGS

        assert "shutdown" in DEFAULT_SETTINGS
        shutdown = DEFAULT_SETTINGS["shutdown"]
        assert isinstance(shutdown, dict)

    def test_default_timeout_is_30(self):
        """Default shutdown timeout should be 30 seconds."""
        from synapse.settings import DEFAULT_SETTINGS

        assert DEFAULT_SETTINGS["shutdown"]["timeout_seconds"] == 30

    def test_default_graceful_enabled_is_true(self):
        """Graceful shutdown should be enabled by default."""
        from synapse.settings import DEFAULT_SETTINGS

        assert DEFAULT_SETTINGS["shutdown"]["graceful_enabled"] is True

    def test_settings_known_keys_includes_shutdown(self):
        """KNOWN_SETTINGS_KEYS should include 'shutdown'."""
        from synapse.settings import KNOWN_SETTINGS_KEYS

        assert "shutdown" in KNOWN_SETTINGS_KEYS

    def test_custom_timeout_from_settings(self, tmp_path):
        """Should load custom timeout from settings.json."""
        import json

        from synapse.settings import load_settings

        settings_file = tmp_path / "settings.json"
        settings_file.write_text(
            json.dumps({"shutdown": {"timeout_seconds": 60, "graceful_enabled": True}})
        )

        data = load_settings(settings_file)
        assert data["shutdown"]["timeout_seconds"] == 60

    def test_graceful_disabled_from_settings(self, tmp_path):
        """Should respect graceful_enabled=false from settings."""
        import json

        from synapse.settings import load_settings

        settings_file = tmp_path / "settings.json"
        settings_file.write_text(
            json.dumps({"shutdown": {"timeout_seconds": 30, "graceful_enabled": False}})
        )

        data = load_settings(settings_file)
        assert data["shutdown"]["graceful_enabled"] is False


# ============================================================
# TestShutdownRequestMessage - A2A message format
# ============================================================


class TestShutdownRequestMessage:
    """Tests for the shutdown_request A2A message format."""

    def test_shutdown_request_message_format(self):
        """shutdown_request message should have correct metadata format."""
        # The message format when sending shutdown request
        metadata = {"type": "shutdown_request"}
        assert metadata["type"] == "shutdown_request"

    def test_shutdown_request_via_send_message(self):
        """Should be able to create a SendMessageRequest with shutdown metadata."""
        from synapse.a2a_compat import Message, SendMessageRequest, TextPart

        request = SendMessageRequest(
            message=Message(
                role="user",
                parts=[TextPart(text="Shutdown requested. Please save your work.")],
            ),
            metadata={"type": "shutdown_request"},
        )

        assert request.metadata is not None
        assert request.metadata["type"] == "shutdown_request"


# ============================================================
# TestGracefulShutdownFlow - End-to-end shutdown behavior
# ============================================================


class TestGracefulShutdownFlow:
    """Tests for the graceful shutdown flow in cmd_kill."""

    @pytest.fixture
    def mock_registry(self):
        """Create a mock registry with a test agent."""
        registry = MagicMock()
        registry.resolve_agent.return_value = {
            "agent_id": "synapse-claude-8100",
            "name": "test-claude",
            "pid": 12345,
            "port": 8100,
            "agent_type": "claude",
        }
        return registry

    def test_force_kill_sends_sigkill(self, mock_registry):
        """With -f flag, should send SIGKILL immediately (existing behavior)."""
        import argparse

        args = argparse.Namespace(target="test-claude", force=True)

        with (
            patch("synapse.cli.AgentRegistry", return_value=mock_registry),
            patch("os.kill") as mock_kill,
        ):
            from synapse.cli import cmd_kill

            cmd_kill(args)

        mock_kill.assert_called_once_with(12345, signal.SIGKILL)

    def test_graceful_shutdown_sends_request_first(self, mock_registry):
        """Without -f, should attempt graceful shutdown via A2A message first."""
        import argparse

        args = argparse.Namespace(target="test-claude", force=False)

        with (
            patch("synapse.cli.AgentRegistry", return_value=mock_registry),
            patch("synapse.settings.get_settings") as mock_settings,
            patch("synapse.cli._send_shutdown_request") as mock_send,
            patch("builtins.input", return_value="y"),
            patch("os.kill"),
        ):
            mock_settings_inst = MagicMock()
            mock_settings_inst.get_shutdown_settings.return_value = {
                "timeout_seconds": 30,
                "graceful_enabled": True,
            }
            mock_settings.return_value = mock_settings_inst
            mock_send.return_value = True  # Agent acknowledged

            from synapse.cli import cmd_kill

            cmd_kill(args)

        mock_send.assert_called_once()

    def test_graceful_shutdown_falls_back_to_sigterm_on_timeout(self, mock_registry):
        """Should send SIGTERM after timeout if agent doesn't respond."""
        import argparse

        args = argparse.Namespace(target="test-claude", force=False)

        with (
            patch("synapse.cli.AgentRegistry", return_value=mock_registry),
            patch("synapse.settings.get_settings") as mock_settings,
            patch("synapse.cli._send_shutdown_request") as mock_send,
            patch("builtins.input", return_value="y"),
            patch("os.kill") as mock_kill,
        ):
            mock_settings_inst = MagicMock()
            mock_settings_inst.get_shutdown_settings.return_value = {
                "timeout_seconds": 1,
                "graceful_enabled": True,
            }
            mock_settings.return_value = mock_settings_inst
            mock_send.return_value = False  # Timeout/no response

            from synapse.cli import cmd_kill

            cmd_kill(args)

        # Should fall back to SIGTERM (not SIGKILL)
        mock_kill.assert_called_once_with(12345, signal.SIGTERM)

    def test_graceful_disabled_uses_old_behavior(self, mock_registry):
        """When graceful_enabled=false, should use SIGKILL directly."""
        import argparse

        args = argparse.Namespace(target="test-claude", force=False)

        with (
            patch("synapse.cli.AgentRegistry", return_value=mock_registry),
            patch("synapse.settings.get_settings") as mock_settings,
            patch("builtins.input", return_value="y"),
            patch("os.kill") as mock_kill,
        ):
            mock_settings_inst = MagicMock()
            mock_settings_inst.get_shutdown_settings.return_value = {
                "timeout_seconds": 30,
                "graceful_enabled": False,
            }
            mock_settings.return_value = mock_settings_inst

            from synapse.cli import cmd_kill

            cmd_kill(args)

        mock_kill.assert_called_once_with(12345, signal.SIGKILL)
