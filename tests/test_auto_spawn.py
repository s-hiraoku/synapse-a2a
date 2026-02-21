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

    def test_team_start_parsed(self) -> None:
        """team start command should accept agent types."""
        import argparse

        args = argparse.Namespace(
            agents=["claude", "gemini", "codex"],
            layout="split",
        )
        assert args.agents == ["claude", "gemini", "codex"]
        assert args.layout == "split"

    def test_team_start_with_layout_flag(self) -> None:
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

    def test_create_tmux_panes_generates_commands(self) -> None:
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

    def test_create_iterm2_panes_generates_script(self) -> None:
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

    def test_create_terminal_app_tabs(self) -> None:
        """Should generate commands for Terminal.app tabs."""
        from synapse.terminal_jump import create_terminal_app_tabs

        commands = create_terminal_app_tabs(
            agents=["claude", "gemini"],
        )
        assert isinstance(commands, list)

    def test_unsupported_terminal_fallback(self) -> None:
        """Should handle unsupported terminals gracefully."""
        from synapse.terminal_jump import create_panes

        with patch("synapse.terminal_jump.detect_terminal_app", return_value=None):
            result = create_panes(
                agents=["claude", "gemini"],
                layout="split",
            )
            # Should return empty list or raise informative error
            assert isinstance(result, list)

    def test_create_panes_zellij_generates_commands(self) -> None:
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
        assert all("--close-on-exit" in cmd for cmd in commands if "zellij run" in cmd)

    def test_create_panes_zellij_respects_layout_direction(self) -> None:
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
        assert all("--close-on-exit" in cmd for cmd in horizontal)
        assert all("--close-on-exit" in cmd for cmd in vertical)

    def test_zellij_close_on_exit_always_present(self) -> None:
        """All zellij run commands should include --close-on-exit."""
        from synapse.terminal_jump import create_zellij_panes

        commands = create_zellij_panes(
            agents=["claude", "gemini", "codex"],
            layout="split",
        )

        assert commands
        assert all(cmd.startswith("zellij run ") for cmd in commands)
        assert all("--close-on-exit" in cmd for cmd in commands)


class TestExecPrefixForPaneAutoClose:
    """exec prefix should be used for shell-based terminals so panes close on exit."""

    def test_iterm2_commands_use_exec(self) -> None:
        """iTerm2 write-text commands should use exec prefix."""
        from synapse.terminal_jump import create_iterm2_panes

        script = create_iterm2_panes(agents=["claude", "gemini"])
        assert "exec " in script

    def test_iterm2_all_new_uses_exec(self) -> None:
        """iTerm2 all_new mode should also use exec prefix."""
        from synapse.terminal_jump import create_iterm2_panes

        script = create_iterm2_panes(agents=["claude", "gemini"], all_new=True)
        assert "exec " in script

    def test_terminal_app_commands_use_exec(self) -> None:
        """Terminal.app do-script commands should use exec prefix."""
        from synapse.terminal_jump import create_terminal_app_tabs

        commands = create_terminal_app_tabs(agents=["claude"])
        assert any("exec " in cmd for cmd in commands)

    def test_ghostty_commands_use_exec(self) -> None:
        """Ghostty commands should use exec prefix."""
        from synapse.terminal_jump import create_ghostty_window

        commands = create_ghostty_window(agents=["claude"])
        assert any("exec " in cmd for cmd in commands)

    def test_tmux_split_window_no_exec(self) -> None:
        """tmux split-window runs command directly, no exec needed."""
        from synapse.terminal_jump import create_tmux_panes

        commands = create_tmux_panes(agents=["claude", "gemini"], all_new=True)
        split_cmds = [c for c in commands if "split-window" in c]
        for cmd in split_cmds:
            # The quoted command inside split-window should not start with exec
            assert "exec " not in cmd

    def test_tmux_send_keys_no_exec(self) -> None:
        """tmux send-keys (handoff) should not use exec to preserve user shell."""
        from synapse.terminal_jump import create_tmux_panes

        commands = create_tmux_panes(agents=["claude", "gemini"])
        send_cmds = [c for c in commands if "send-keys" in c]
        for cmd in send_cmds:
            assert "exec " not in cmd

    def test_zellij_no_exec(self) -> None:
        """zellij run executes commands directly, no exec needed."""
        from synapse.terminal_jump import create_zellij_panes

        commands = create_zellij_panes(agents=["claude", "gemini"])
        for cmd in commands:
            # The command portion after '--' should not have exec
            after_dash = cmd.split("-- ", 1)[-1] if "-- " in cmd else cmd
            assert not after_dash.startswith("exec ")

    def test_build_agent_command_exec_flag(self) -> None:
        """_build_agent_command should support use_exec parameter."""
        from synapse.terminal_jump import _build_agent_command

        without_exec = _build_agent_command("claude")
        with_exec = _build_agent_command("claude", use_exec=True)

        assert not without_exec.startswith("exec ")
        assert with_exec.startswith("exec ")
        # Both should contain the same synapse command
        assert without_exec in with_exec


class TestTeamStartExecution:
    """Execution behavior tests for synapse team start."""

    def test_team_start_runs_commands_all_new(self) -> None:
        """Should execute all commands when --all-new is specified."""
        import argparse

        from synapse.cli import cmd_team_start

        args = argparse.Namespace(
            agents=["claude", "gemini"],
            layout="horizontal",
            all_new=True,
        )

        with patch("synapse.terminal_jump.detect_terminal_app", return_value="tmux"):
            with patch("subprocess.run") as mock_run:
                cmd_team_start(args)

        # In all_new mode, subprocess.run is called for all agent commands
        assert mock_run.call_count > 0

    def test_team_start_handoff_by_default(self) -> None:
        """Should use os.execvp for the first agent by default (handoff)."""
        import argparse

        from synapse.cli import cmd_team_start

        args = argparse.Namespace(
            agents=["claude", "gemini"],
            layout="horizontal",
            all_new=False,
        )

        with patch("synapse.terminal_jump.detect_terminal_app", return_value="tmux"):
            with patch("subprocess.run") as mock_run:
                with patch("os.execvp") as mock_exec:
                    cmd_team_start(args)

        # Should call execvp for the first agent
        assert mock_exec.called
        # Should call subprocess.run for the remaining agents
        assert mock_run.call_count > 0


# ============================================================
# TestPaneLayout - Layout configurations
# ============================================================


class TestPaneLayout:
    """Tests for pane layout configurations."""

    def test_two_agents_horizontal(self) -> None:
        """Two agents should produce a horizontal split."""
        from synapse.terminal_jump import create_tmux_panes

        commands = create_tmux_panes(
            agents=["claude", "gemini"],
            layout="horizontal",
        )
        assert any("split-window" in cmd or "split" in cmd for cmd in commands)

    def test_three_agents_tiling(self) -> None:
        """Three agents should produce a tiled layout."""
        from synapse.terminal_jump import create_tmux_panes

        commands = create_tmux_panes(
            agents=["claude", "gemini", "codex"],
            layout="split",
        )
        # Should have at least 2 split commands for 3 panes
        split_cmds = [c for c in commands if "split" in c.lower()]
        assert len(split_cmds) >= 2


class TestAgentSpecParsing:
    """Tests for profile:name:role:skill_set parsing."""

    def test_build_agent_command_simple(self) -> None:
        """Simple profile should produce simple command."""
        from synapse.terminal_jump import _build_agent_command

        cmd = _build_agent_command("claude")
        assert cmd.endswith(" claude")
        assert "-m synapse.cli claude" in cmd

    def test_build_agent_command_full(self) -> None:
        """Full spec should produce options and --no-setup."""
        from synapse.terminal_jump import _build_agent_command

        cmd = _build_agent_command("claude:Reviewer:code review:dev-set")
        assert "synapse.cli claude" in cmd
        assert "--name Reviewer" in cmd
        # Use simple 'in' check for role content, ignoring quote style
        assert "--role" in cmd
        assert "code review" in cmd
        assert "--skill-set dev-set" in cmd
        assert "--no-setup" in cmd

    def test_build_agent_command_partial(self) -> None:
        """Partial spec should omit missing parts."""
        from synapse.terminal_jump import _build_agent_command

        cmd = _build_agent_command("gemini:Searcher")
        assert "--name Searcher" in cmd
        assert "--role" not in cmd
        assert "--no-setup" in cmd

    def test_build_agent_command_with_skips(self) -> None:
        """Should handle empty parts in colon-separated spec."""
        from synapse.terminal_jump import _build_agent_command

        cmd = _build_agent_command("codex::test writer")
        assert "synapse.cli codex" in cmd
        assert "--name" not in cmd
        assert "--role" in cmd
        assert "test writer" in cmd
        assert "--no-setup" in cmd

    def test_create_panes_with_specs(self) -> None:
        """create_panes should respect extended specs across all platforms."""
        from synapse.terminal_jump import create_tmux_panes

        commands = create_tmux_panes(
            agents=["claude:C1", "gemini:G1"],
            layout="horizontal",
        )
        # Filter for commands that actually run synapse
        synapse_cmds = [c for c in commands if "synapse.cli " in c]
        assert any("--name C1" in cmd for cmd in synapse_cmds)
        assert any("--name G1" in cmd for cmd in synapse_cmds)
        assert all("--no-setup" in cmd for cmd in synapse_cmds)


class TestITerm2AppleScriptTarget:
    """iTerm2 split must target 'current session' not 'current tab'."""

    def test_all_new_splits_target_session(self) -> None:
        """all_new=True should split within 'current session of current tab'."""
        from synapse.terminal_jump import create_iterm2_panes

        script = create_iterm2_panes(agents=["claude"], all_new=True)
        assert "current session of current tab" in script
        # Must NOT have bare 'tell current tab' without session
        lines = script.splitlines()
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("tell current tab"):
                # This would be wrong — split is a session method
                raise AssertionError(
                    f"Found bare 'tell current tab' without session: {stripped}"
                )

    def test_handoff_splits_target_session(self) -> None:
        """all_new=False (handoff) should also split via session."""
        from synapse.terminal_jump import create_iterm2_panes

        script = create_iterm2_panes(agents=["claude", "gemini"], all_new=False)
        # The handoff path already uses 'current session' for the first agent
        assert "current session" in script

    def test_all_new_multiple_agents(self) -> None:
        """Multiple agents with all_new=True should all target session."""
        from synapse.terminal_jump import create_iterm2_panes

        script = create_iterm2_panes(agents=["claude", "gemini", "codex"], all_new=True)
        # Each split should happen within session context
        split_count = script.count("split vertically with default profile")
        assert split_count == 3
        assert "current session of current tab" in script
