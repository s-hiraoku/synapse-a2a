"""Tests for terminal jump functionality."""

from __future__ import annotations

import os
import subprocess
from unittest.mock import MagicMock, patch

from synapse.terminal_jump import (
    can_jump,
    detect_terminal_app,
    get_supported_terminals,
    jump_to_terminal,
)


class TestDetectTerminalApp:
    """Tests for detect_terminal_app function."""

    def test_detect_tmux(self) -> None:
        """Should detect tmux when TMUX env var is set."""
        with patch.dict(os.environ, {"TMUX": "/tmp/tmux-1000/default,12345,0"}):
            assert detect_terminal_app() == "tmux"

    def test_detect_zellij(self) -> None:
        """Should detect Zellij when ZELLIJ env var is set."""
        with patch.dict(os.environ, {"ZELLIJ": "0"}, clear=True):
            assert detect_terminal_app() == "zellij"

    def test_detect_iterm2(self) -> None:
        """Should detect iTerm2 from TERM_PROGRAM."""
        with patch.dict(os.environ, {"TERM_PROGRAM": "iTerm.app"}, clear=True):
            assert detect_terminal_app() == "iTerm2"

    def test_detect_terminal_app(self) -> None:
        """Should detect Terminal.app from TERM_PROGRAM."""
        with patch.dict(os.environ, {"TERM_PROGRAM": "Apple_Terminal"}, clear=True):
            assert detect_terminal_app() == "Terminal"

    def test_detect_ghostty(self) -> None:
        """Should detect Ghostty from TERM_PROGRAM."""
        with patch.dict(os.environ, {"TERM_PROGRAM": "ghostty"}, clear=True):
            assert detect_terminal_app() == "Ghostty"

    def test_detect_vscode(self) -> None:
        """Should detect VS Code from TERM_PROGRAM."""
        with patch.dict(os.environ, {"TERM_PROGRAM": "vscode"}, clear=True):
            assert detect_terminal_app() == "VSCode"

    def test_detect_unknown(self) -> None:
        """Should return None for unknown terminal."""
        with patch.dict(os.environ, {"TERM_PROGRAM": "unknown"}, clear=True):
            assert detect_terminal_app() is None

    def test_detect_no_env(self) -> None:
        """Should return None when no terminal env vars set."""
        with patch.dict(os.environ, {}, clear=True):
            assert detect_terminal_app() is None


class TestGetSupportedTerminals:
    """Tests for get_supported_terminals function."""

    def test_returns_list(self) -> None:
        """Should return a list of supported terminals."""
        terminals = get_supported_terminals()
        assert isinstance(terminals, list)
        assert len(terminals) > 0

    def test_includes_expected_terminals(self) -> None:
        """Should include known terminal emulators."""
        terminals = get_supported_terminals()
        assert "iTerm2" in terminals
        assert "Terminal" in terminals
        assert "Ghostty" in terminals
        assert "VSCode" in terminals
        assert "tmux" in terminals
        assert "zellij" in terminals


class TestCanJump:
    """Tests for can_jump function."""

    def test_can_jump_with_tmux(self) -> None:
        """Should return True when tmux is detected."""
        with patch.dict(os.environ, {"TMUX": "/tmp/tmux"}):
            assert can_jump() is True

    def test_can_jump_with_iterm2(self) -> None:
        """Should return True when iTerm2 is detected."""
        with patch.dict(os.environ, {"TERM_PROGRAM": "iTerm.app"}, clear=True):
            assert can_jump() is True

    def test_cannot_jump_unknown(self) -> None:
        """Should return False for unknown terminal."""
        with patch.dict(os.environ, {}, clear=True):
            assert can_jump() is False


class TestJumpToTerminal:
    """Tests for jump_to_terminal function."""

    def test_jump_no_terminal_detected(self) -> None:
        """Should return False when no terminal detected."""
        with patch.dict(os.environ, {}, clear=True):
            result = jump_to_terminal({"agent_id": "test", "tty_device": "/dev/tty0"})
            assert result is False

    def test_jump_unsupported_terminal(self) -> None:
        """Should return False for unsupported terminal."""
        agent_info = {"agent_id": "test", "tty_device": "/dev/tty0"}
        result = jump_to_terminal(agent_info, terminal_app="UnsupportedTerminal")
        assert result is False

    @patch("synapse.terminal_jump._run_applescript")
    def test_jump_iterm2(self, mock_applescript: MagicMock) -> None:
        """Should call AppleScript for iTerm2 jump."""
        mock_applescript.return_value = True
        agent_info = {"agent_id": "test-agent", "tty_device": "/dev/ttys001"}

        result = jump_to_terminal(agent_info, terminal_app="iTerm2")

        assert result is True
        mock_applescript.assert_called_once()
        script = mock_applescript.call_args[0][0]
        assert "iTerm2" in script
        assert "/dev/ttys001" in script

    @patch("synapse.terminal_jump._run_applescript")
    def test_jump_terminal_app(self, mock_applescript: MagicMock) -> None:
        """Should call AppleScript for Terminal.app jump."""
        mock_applescript.return_value = True
        agent_info = {"agent_id": "test-agent", "tty_device": "/dev/ttys002"}

        result = jump_to_terminal(agent_info, terminal_app="Terminal")

        assert result is True
        mock_applescript.assert_called_once()
        script = mock_applescript.call_args[0][0]
        assert "Terminal" in script

    @patch("synapse.terminal_jump._run_applescript")
    def test_jump_ghostty(self, mock_applescript: MagicMock) -> None:
        """Should call AppleScript for Ghostty jump (activate only)."""
        mock_applescript.return_value = True
        agent_info = {"agent_id": "synapse-claude-8100", "tty_device": "/dev/ttys003"}

        result = jump_to_terminal(agent_info, terminal_app="Ghostty")

        assert result is True
        mock_applescript.assert_called_once()
        script = mock_applescript.call_args[0][0]
        assert "Ghostty" in script
        assert "activate" in script

    @patch("synapse.terminal_jump.shutil.which")
    @patch("synapse.terminal_jump.subprocess.run")
    def test_jump_tmux(self, mock_run: MagicMock, mock_which: MagicMock) -> None:
        """Should use tmux commands for tmux jump."""
        mock_which.return_value = "/usr/bin/tmux"
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="main:0.0 /dev/ttys004\nmain:0.1 /dev/ttys005\n",
        )
        agent_info = {"agent_id": "test-agent", "tty_device": "/dev/ttys004"}

        result = jump_to_terminal(agent_info, terminal_app="tmux")

        assert result is True
        # Should call list-panes first, then select-pane and select-window
        assert mock_run.call_count >= 1

    @patch("synapse.terminal_jump.shutil.which")
    @patch("synapse.terminal_jump.subprocess.run")
    def test_jump_zellij(self, mock_run: MagicMock, mock_which: MagicMock) -> None:
        """Should activate terminal app for zellij (direct pane focus not supported)."""
        mock_which.return_value = "/usr/bin/osascript"
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        agent_info = {"agent_id": "test-agent", "zellij_pane_id": "42"}

        with patch.dict(os.environ, {"TERM_PROGRAM": "ghostty"}):
            result = jump_to_terminal(agent_info, terminal_app="zellij")

        # Zellij falls back to activating terminal app since direct pane focus
        # is not supported via CLI
        assert result is True
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert "osascript" in call_args

    def test_jump_no_tty_device(self) -> None:
        """Should return False when no tty_device in agent_info."""
        agent_info = {"agent_id": "test-agent"}

        with patch("synapse.terminal_jump._run_applescript") as mock_as:
            result = jump_to_terminal(agent_info, terminal_app="iTerm2")

        assert result is False
        mock_as.assert_not_called()


class TestRunApplescript:
    """Tests for _run_applescript helper."""

    @patch("synapse.terminal_jump.shutil.which")
    def test_applescript_not_available(self, mock_which: MagicMock) -> None:
        """Should return False when osascript not found."""
        mock_which.return_value = None

        from synapse.terminal_jump import _run_applescript

        result = _run_applescript('tell application "Finder" to activate')
        assert result is False

    @patch("synapse.terminal_jump.shutil.which")
    @patch("synapse.terminal_jump.subprocess.run")
    def test_applescript_success(
        self, mock_run: MagicMock, mock_which: MagicMock
    ) -> None:
        """Should return True on successful execution."""
        mock_which.return_value = "/usr/bin/osascript"
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        from synapse.terminal_jump import _run_applescript

        result = _run_applescript('tell application "Finder" to activate')
        assert result is True

    @patch("synapse.terminal_jump.shutil.which")
    @patch("synapse.terminal_jump.subprocess.run")
    def test_applescript_failure(
        self, mock_run: MagicMock, mock_which: MagicMock
    ) -> None:
        """Should return False on execution failure."""
        mock_which.return_value = "/usr/bin/osascript"
        mock_run.return_value = MagicMock(returncode=1, stderr="error")

        from synapse.terminal_jump import _run_applescript

        result = _run_applescript('tell application "Finder" to activate')
        assert result is False

    @patch("synapse.terminal_jump.shutil.which")
    @patch("synapse.terminal_jump.subprocess.run")
    def test_applescript_timeout(
        self, mock_run: MagicMock, mock_which: MagicMock
    ) -> None:
        """Should return False on timeout."""
        mock_which.return_value = "/usr/bin/osascript"
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="osascript", timeout=5)

        from synapse.terminal_jump import _run_applescript

        result = _run_applescript('tell application "Finder" to activate')
        assert result is False
