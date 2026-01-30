"""Extended tests for terminal jump to improve coverage."""

import os
import sys
from unittest.mock import MagicMock, patch

from synapse.terminal_jump import (
    _escape_applescript_string,
    _jump_ghostty,
    _jump_tmux,
    _jump_vscode,
    _jump_zellij,
    _run_applescript,
)


class TestEscapeAppleScript:
    """Tests for _escape_applescript_string."""

    def test_escape_quotes_and_backslashes(self):
        """Should escape double quotes and backslashes."""
        unsafe = 'path\\to\\"file"'
        # Backslash becomes \\, Quote becomes \"
        # path\\to\\\"file\" -> path\\\\to\\\\\"file\\"
        expected = 'path\\\\to\\\\\\"file\\"'
        assert _escape_applescript_string(unsafe) == expected

    def test_escape_simple_string(self):
        """Should leave simple strings unchanged."""
        assert _escape_applescript_string("hello") == "hello"


class TestRunAppleScriptExtended:
    """Extended tests for _run_applescript."""

    @patch("synapse.terminal_jump.shutil.which")
    @patch("synapse.terminal_jump.subprocess.run")
    def test_expected_token_success(self, mock_run, mock_which):
        """Should return True if expected token is in stdout."""
        mock_which.return_value = "/usr/bin/osascript"
        mock_run.return_value = MagicMock(returncode=0, stdout="found", stderr="")

        assert _run_applescript("script", expected_token="found") is True

    @patch("synapse.terminal_jump.shutil.which")
    @patch("synapse.terminal_jump.subprocess.run")
    def test_expected_token_failure(self, mock_run, mock_which):
        """Should return False if expected token is missing."""
        mock_which.return_value = "/usr/bin/osascript"
        mock_run.return_value = MagicMock(returncode=0, stdout="missing", stderr="")

        assert _run_applescript("script", expected_token="found") is False

    @patch("synapse.terminal_jump.shutil.which")
    @patch("synapse.terminal_jump.subprocess.run")
    def test_exception_handling(self, mock_run, mock_which):
        """Should catch general exceptions."""
        mock_which.return_value = "/usr/bin/osascript"
        mock_run.side_effect = Exception("Unexpected error")

        assert _run_applescript("script") is False


class TestJumpGhosttyExtended:
    """Extended tests for _jump_ghostty."""

    @patch("synapse.terminal_jump._jump_tmux")
    def test_jump_ghostty_in_tmux(self, mock_jump_tmux):
        """Should delegate to tmux if inside tmux."""
        with patch.dict(os.environ, {"TMUX": "1"}):
            # The function signature in source is _jump_ghostty(tty_device, agent_id)
            _jump_ghostty("/dev/tty1", "test")

            mock_jump_tmux.assert_called_once()
            args = mock_jump_tmux.call_args[0][0]
            assert args["tty_device"] == "/dev/tty1"
            assert args["agent_id"] == "test"


class TestJumpVSCodeExtended:
    """Extended tests for _jump_vscode."""

    @patch("synapse.terminal_jump._run_applescript")
    def test_jump_vscode_darwin(self, mock_applescript):
        """Should use AppleScript on macOS."""
        with patch.object(sys, "platform", "darwin"):
            mock_applescript.return_value = True
            assert _jump_vscode(None, "test") is True
            mock_applescript.assert_called_once()

    @patch("synapse.terminal_jump.shutil.which")
    @patch("synapse.terminal_jump.subprocess.run")
    def test_jump_vscode_linux_wmctrl_success(self, mock_run, mock_which):
        """Should use wmctrl on Linux if available."""
        with patch.object(sys, "platform", "linux"):
            mock_which.return_value = "/usr/bin/wmctrl"
            mock_run.return_value = MagicMock(returncode=0)

            assert _jump_vscode(None, "test") is True
            mock_run.assert_called_with(
                ["wmctrl", "-a", "Visual Studio Code"],
                capture_output=True,
                text=True,
                timeout=5,
            )

    @patch("synapse.terminal_jump.shutil.which")
    @patch("synapse.terminal_jump.subprocess.run")
    def test_jump_vscode_linux_wmctrl_failure(self, mock_run, mock_which):
        """Should return False if wmctrl fails."""
        with patch.object(sys, "platform", "linux"):
            mock_which.return_value = "/usr/bin/wmctrl"
            mock_run.return_value = MagicMock(returncode=1)

            assert _jump_vscode(None, "test") is False

    @patch("synapse.terminal_jump.shutil.which")
    def test_jump_vscode_linux_no_tool(self, mock_which):
        """Should return False if no tools available on Linux."""
        with patch.object(sys, "platform", "linux"):
            mock_which.return_value = None
            assert _jump_vscode(None, "test") is False


class TestJumpTmuxExtended:
    """Extended tests for _jump_tmux."""

    @patch("synapse.terminal_jump.shutil.which")
    def test_tmux_not_found(self, mock_which):
        """Should return False if tmux binary is missing."""
        mock_which.return_value = None
        assert _jump_tmux({}) is False

    @patch("synapse.terminal_jump.shutil.which")
    def test_no_tty_device(self, mock_which):
        """Should return False if no TTY device provided."""
        mock_which.return_value = "/usr/bin/tmux"
        assert _jump_tmux({"agent_id": "test"}) is False

    @patch("synapse.terminal_jump.shutil.which")
    @patch("synapse.terminal_jump.subprocess.run")
    def test_list_panes_failure(self, mock_run, mock_which):
        """Should return False if list-panes fails."""
        mock_which.return_value = "/usr/bin/tmux"
        mock_run.return_value = MagicMock(returncode=1, stderr="error")

        assert _jump_tmux({"tty_device": "/dev/tty1"}) is False

    @patch("synapse.terminal_jump.shutil.which")
    @patch("synapse.terminal_jump.subprocess.run")
    def test_pane_not_found(self, mock_run, mock_which):
        """Should return False if no pane matches TTY."""
        mock_which.return_value = "/usr/bin/tmux"
        mock_run.return_value = MagicMock(
            returncode=0, stdout="0.0 /dev/tty2\n0.1 /dev/tty3"
        )

        assert _jump_tmux({"tty_device": "/dev/tty1"}) is False

    @patch("synapse.terminal_jump.shutil.which")
    @patch("synapse.terminal_jump.subprocess.run")
    def test_select_pane_failure(self, mock_run, mock_which):
        """Should return False if select-pane fails."""
        mock_which.return_value = "/usr/bin/tmux"
        # First call lists panes (success), second calls select-pane (fail)
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="0.0 /dev/tty1"),
            MagicMock(returncode=1, stderr="fail"),
        ]

        assert _jump_tmux({"tty_device": "/dev/tty1"}) is False

    @patch("synapse.terminal_jump.shutil.which")
    @patch("synapse.terminal_jump.subprocess.run")
    def test_select_window_failure(self, mock_run, mock_which):
        """Should return False if select-window fails."""
        mock_which.return_value = "/usr/bin/tmux"
        # list-panes -> success, select-pane -> success, select-window -> fail
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="0.0 /dev/tty1"),
            MagicMock(returncode=0),
            MagicMock(returncode=1, stderr="fail"),
        ]

        assert _jump_tmux({"tty_device": "/dev/tty1"}) is False


class TestJumpZellijExtended:
    """Extended tests for _jump_zellij."""

    @patch("synapse.terminal_jump._run_applescript")
    def test_zellij_fallback_terminals(self, mock_applescript):
        """Should fallback to activating known terminal apps."""
        agent_info = {"agent_id": "test"}

        # Test fallback for Ghostty
        with patch.dict(os.environ, {"TERM_PROGRAM": "ghostty"}):
            _jump_zellij(agent_info)
            assert 'tell application "Ghostty"' in mock_applescript.call_args[0][0]

        # Test fallback for iTerm2
        with patch.dict(os.environ, {"TERM_PROGRAM": "iTerm.app"}):
            _jump_zellij(agent_info)
            assert 'tell application "iTerm2"' in mock_applescript.call_args[0][0]

        # Test fallback for Terminal
        with patch.dict(os.environ, {"TERM_PROGRAM": "Apple_Terminal"}):
            _jump_zellij(agent_info)
            assert 'tell application "Terminal"' in mock_applescript.call_args[0][0]

    def test_zellij_no_known_terminal(self):
        """Should return False if TERM_PROGRAM is unknown."""
        with patch.dict(os.environ, {"TERM_PROGRAM": "Unknown"}):
            assert _jump_zellij({}) is False
