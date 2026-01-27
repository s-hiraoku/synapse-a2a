"""Tests for TerminalController resume mode functionality."""

import logging
from unittest.mock import Mock, patch

import pytest

from synapse.controller import TerminalController
from synapse.registry import AgentRegistry


class TestResumeMode:
    """Tests for resume mode (skipping initial instructions)."""

    @pytest.fixture
    def mock_registry(self):
        """Create a mock registry."""
        registry = Mock(spec=AgentRegistry)
        registry.list_agents.return_value = {
            "synapse-gemini-8101": {"agent_type": "gemini", "port": 8101}
        }
        return registry

    @pytest.fixture
    def controller_resume(self, mock_registry):
        """Create a controller with skip_initial_instructions=True."""
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$",
            registry=mock_registry,
            agent_id="synapse-gemini-8101",
            agent_type="gemini",
            skip_initial_instructions=True,
        )
        # Mock write to verify it's NOT called
        ctrl.write = Mock()
        return ctrl

    @pytest.fixture
    def controller_normal(self, mock_registry):
        """Create a controller with skip_initial_instructions=False."""
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$",
            registry=mock_registry,
            agent_id="synapse-gemini-8101",
            agent_type="gemini",
            skip_initial_instructions=False,
        )
        # Mock write to verify it IS called (or attempted)
        ctrl.write = Mock()
        return ctrl

    def test_resume_mode_skips_instructions(self, controller_resume, caplog):
        """Should skip sending instructions when skip_initial_instructions is True."""
        caplog.set_level(logging.INFO)

        # Execute
        controller_resume._send_identity_instruction()

        # Verify
        assert controller_resume._identity_sent is True
        controller_resume.write.assert_not_called()

        # Check log message
        assert "Skipping initial instructions (resume mode)" in caplog.text

    def test_resume_mode_flag_initialization(self):
        """Should correctly initialize _skip_initial_instructions flag."""
        ctrl = TerminalController(command="echo test", skip_initial_instructions=True)
        assert ctrl._skip_initial_instructions is True

        ctrl = TerminalController(command="echo test", skip_initial_instructions=False)
        assert ctrl._skip_initial_instructions is False

    def test_normal_mode_sends_instructions(self, controller_normal, monkeypatch):
        """Should attempt to send instructions when skip_initial_instructions is False."""
        # Setup mocks to allow sending to proceed
        controller_normal.master_fd = 1
        controller_normal.running = True

        # Mock settings to return some file paths
        mock_settings = Mock()
        mock_settings.get_instruction_file_paths.return_value = [".synapse/gemini.md"]

        with patch("synapse.controller.get_settings", return_value=mock_settings):
            # Speed up the test by reducing delays
            monkeypatch.setattr("synapse.controller.IDENTITY_WAIT_TIMEOUT", 0.1)
            monkeypatch.setattr("synapse.controller.POST_WRITE_IDLE_DELAY", 0)

            # Execute
            controller_normal._send_identity_instruction()

            # Verify
            assert controller_normal._identity_sent is True
            assert controller_normal.write.called
