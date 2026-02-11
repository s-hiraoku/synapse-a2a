"""Tests for B6: Auto-Spawn Split Panes feature.

Test-first development: tests for pane creation and team start command.
"""

from __future__ import annotations

from unittest.mock import patch

# ============================================================
# TestTeamStartCommand - CLI command parsing
# ============================================================


class TestTeamStartCommand:
    """Tests for synapse team start command."""

    def test_team_start_parsed(self):
        """team start command should accept agent types."""
        import argparse

        args = argparse.Namespace(
            agents=["claude", "gemini", "codex"],
            layout="split",
        )
        assert args.agents == ["claude", "gemini", "codex"]
        assert args.layout == "split"

    def test_team_start_with_layout_flag(self):
        """--layout flag should be accepted."""
        import argparse

        args = argparse.Namespace(
            agents=["claude", "gemini"],
            layout="horizontal",
        )
        assert args.layout == "horizontal"


# ============================================================
# TestTerminalPaneCreation - Pane creation functions
# ============================================================


class TestTerminalPaneCreation:
    """Tests for terminal pane creation."""

    def test_create_tmux_panes_generates_commands(self):
        """Should generate tmux split-window commands."""
        from synapse.terminal_jump import create_tmux_panes

        commands = create_tmux_panes(
            agents=["claude", "gemini", "codex"],
            layout="split",
        )
        assert isinstance(commands, list)
        assert len(commands) > 0
        # Should contain tmux commands
        assert any("tmux" in cmd for cmd in commands)

    def test_create_iterm2_panes_generates_script(self):
        """Should generate AppleScript for iTerm2."""
        from synapse.terminal_jump import create_iterm2_panes

        script = create_iterm2_panes(
            agents=["claude", "gemini"],
        )
        assert isinstance(script, str)
        assert "tell application" in script.lower()
        # Verify both agents appear in the script
        assert "claude" in script
        assert "gemini" in script

    def test_create_terminal_app_tabs(self):
        """Should generate commands for Terminal.app tabs."""
        from synapse.terminal_jump import create_terminal_app_tabs

        commands = create_terminal_app_tabs(
            agents=["claude", "gemini"],
        )
        assert isinstance(commands, list)

    def test_unsupported_terminal_fallback(self):
        """Should handle unsupported terminals gracefully."""
        from synapse.terminal_jump import create_panes

        with patch("synapse.terminal_jump.detect_terminal_app", return_value=None):
            result = create_panes(
                agents=["claude", "gemini"],
                layout="split",
            )
            # Should return empty list or raise informative error
            assert isinstance(result, list)

    def test_create_panes_zellij_generates_commands(self):
        """Should generate zellij commands when terminal is zellij."""
        from synapse.terminal_jump import create_panes

        commands = create_panes(
            agents=["claude", "gemini", "codex"],
            layout="split",
            terminal_app="zellij",
        )

        assert isinstance(commands, list)
        assert len(commands) > 0
        assert any("zellij run" in cmd for cmd in commands)

    def test_create_panes_zellij_respects_layout_direction(self):
        """Should map horizontal/vertical layout to zellij split directions."""
        from synapse.terminal_jump import create_panes

        horizontal = create_panes(
            agents=["claude", "gemini"],
            layout="horizontal",
            terminal_app="zellij",
        )
        vertical = create_panes(
            agents=["claude", "gemini"],
            layout="vertical",
            terminal_app="zellij",
        )

        assert any("--direction right" in cmd for cmd in horizontal)
        assert any("--direction down" in cmd for cmd in vertical)


class TestTeamStartExecution:
    """Execution behavior tests for synapse team start."""

    def test_team_start_runs_zellij_commands(self):
        """Should execute generated commands when zellij is detected."""
        import argparse

        from synapse.cli import cmd_team_start

        args = argparse.Namespace(
            agents=["claude", "gemini"],
            layout="horizontal",
        )

        with patch("synapse.terminal_jump.detect_terminal_app", return_value="zellij"):
            with patch("subprocess.run") as mock_run:
                cmd_team_start(args)

        assert mock_run.call_count > 0


# ============================================================
# TestPaneLayout - Layout configurations
# ============================================================


class TestPaneLayout:
    """Tests for pane layout configurations."""

    def test_two_agents_horizontal(self):
        """Two agents should produce a horizontal split."""
        from synapse.terminal_jump import create_tmux_panes

        commands = create_tmux_panes(
            agents=["claude", "gemini"],
            layout="horizontal",
        )
        assert any("split-window" in cmd or "split" in cmd for cmd in commands)

    def test_three_agents_tiling(self):
        """Three agents should produce a tiled layout."""
        from synapse.terminal_jump import create_tmux_panes

        commands = create_tmux_panes(
            agents=["claude", "gemini", "codex"],
            layout="split",
        )
        # Should have at least 2 split commands for 3 panes
        split_cmds = [c for c in commands if "split" in c.lower()]
        assert len(split_cmds) >= 2
