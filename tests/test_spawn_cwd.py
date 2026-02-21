"""Tests for spawn cwd — spawned agents must inherit parent's working directory.

Verifies that all terminal backends (tmux, iTerm2, Terminal.app, zellij, Ghostty)
receive and use the cwd parameter so spawned agents start in the correct directory.
"""

from __future__ import annotations

import shlex
from unittest.mock import MagicMock, patch

# ============================================================
# tmux: -c {cwd} flag
# ============================================================


class TestTmuxCwd:
    """tmux split-window must include -c {cwd}."""

    def test_split_window_includes_cwd(self) -> None:
        from synapse.terminal_jump import create_tmux_panes

        cwd = "/home/user/project"
        commands = create_tmux_panes(["claude"], all_new=True, cwd=cwd)
        # split-window command should have -c /home/user/project
        split_cmds = [c for c in commands if "split-window" in c]
        assert len(split_cmds) >= 1
        assert f"-c {cwd}" in split_cmds[0]

    def test_send_keys_first_agent_has_cd_prefix(self) -> None:
        """When all_new=False, first agent uses send-keys. Must cd first."""
        from synapse.terminal_jump import create_tmux_panes

        cwd = "/home/user/project"
        commands = create_tmux_panes(["claude", "gemini"], all_new=False, cwd=cwd)
        # First command: send-keys should include cd
        send_cmds = [c for c in commands if "send-keys" in c]
        assert len(send_cmds) >= 1
        assert f"cd {cwd} &&" in send_cmds[0]

    def test_remaining_agents_split_with_cwd(self) -> None:
        """When all_new=False, remaining agents split-window with -c."""
        from synapse.terminal_jump import create_tmux_panes

        cwd = "/home/user/project"
        commands = create_tmux_panes(
            ["claude", "gemini", "codex"], all_new=False, cwd=cwd
        )
        split_cmds = [c for c in commands if "split-window" in c]
        assert len(split_cmds) >= 2
        for cmd in split_cmds:
            assert f"-c {cwd}" in cmd

    def test_cwd_with_spaces(self) -> None:
        """cwd with spaces must be properly quoted."""
        from synapse.terminal_jump import create_tmux_panes

        cwd = "/home/user/my project"
        commands = create_tmux_panes(["claude"], all_new=True, cwd=cwd)
        split_cmds = [c for c in commands if "split-window" in c]
        assert len(split_cmds) >= 1
        # The cwd should be shell-quoted
        assert shlex.quote(cwd) in split_cmds[0]


# ============================================================
# iTerm2: cd {cwd} && in AppleScript write text
# ============================================================


class TestITerm2Cwd:
    """iTerm2 AppleScript must prepend cd {cwd} before agent command."""

    def test_all_new_includes_cd(self) -> None:
        from synapse.terminal_jump import create_iterm2_panes

        cwd = "/home/user/project"
        script = create_iterm2_panes(["claude"], all_new=True, cwd=cwd)
        assert f"cd {cwd} && " in script

    def test_first_agent_includes_cd(self) -> None:
        from synapse.terminal_jump import create_iterm2_panes

        cwd = "/home/user/project"
        script = create_iterm2_panes(["claude", "gemini"], all_new=False, cwd=cwd)
        # Both agents' write text commands should include cd
        assert script.count(f"cd {cwd} && ") >= 2

    def test_cwd_with_special_chars_escaped(self) -> None:
        """cwd with AppleScript-sensitive chars must be escaped."""
        from synapse.terminal_jump import create_iterm2_panes

        cwd = '/home/user/my "project"'
        script = create_iterm2_panes(["claude"], all_new=True, cwd=cwd)
        # Double quotes in cwd get escaped by _escape_applescript_string
        # (once for the cd prefix, once for the outer write text string)
        assert "my" in script
        assert "project" in script
        # The raw unescaped double quote must NOT appear in the AppleScript string
        assert 'my "project"' not in script


# ============================================================
# Terminal.app: cd {cwd} && in do script
# ============================================================


class TestTerminalAppCwd:
    """Terminal.app osascript must include cd {cwd} && before agent command."""

    def test_includes_cd(self) -> None:
        from synapse.terminal_jump import create_terminal_app_tabs

        cwd = "/home/user/project"
        commands = create_terminal_app_tabs(["claude"], cwd=cwd)
        assert len(commands) >= 1
        assert f"cd {cwd} && " in commands[0]

    def test_all_tabs_include_cd(self) -> None:
        from synapse.terminal_jump import create_terminal_app_tabs

        cwd = "/home/user/project"
        commands = create_terminal_app_tabs(["claude", "gemini"], all_new=True, cwd=cwd)
        for cmd in commands:
            assert f"cd {cwd} && " in cmd


# ============================================================
# zellij: --cwd {cwd} flag
# ============================================================


class TestZellijCwd:
    """zellij run must include --cwd {cwd}."""

    def test_includes_cwd_flag(self) -> None:
        from synapse.terminal_jump import create_zellij_panes

        cwd = "/home/user/project"
        commands = create_zellij_panes(["claude"], cwd=cwd)
        assert len(commands) >= 1
        assert f"--cwd {cwd}" in commands[0]

    def test_all_panes_include_cwd(self) -> None:
        from synapse.terminal_jump import create_zellij_panes

        cwd = "/home/user/project"
        commands = create_zellij_panes(["claude", "gemini"], cwd=cwd)
        for cmd in commands:
            assert f"--cwd {cwd}" in cmd


# ============================================================
# Ghostty: cd {cwd} && in shell command
# ============================================================


class TestGhosttyCwd:
    """Ghostty window command must prepend cd {cwd} before agent command."""

    def test_includes_cd(self) -> None:
        from synapse.terminal_jump import create_ghostty_window

        cwd = "/home/user/project"
        commands = create_ghostty_window(["claude"], cwd=cwd)
        assert len(commands) >= 1
        assert f"cd {cwd} && " in commands[0]


# ============================================================
# create_panes: delegates cwd to backend
# ============================================================


class TestCreatePanesCwd:
    """create_panes must forward cwd to each backend."""

    def test_tmux_receives_cwd(self) -> None:
        from synapse.terminal_jump import create_panes

        cwd = "/home/user/project"
        commands = create_panes(["claude"], terminal_app="tmux", all_new=True, cwd=cwd)
        split_cmds = [c for c in commands if "split-window" in c]
        assert len(split_cmds) >= 1
        assert f"-c {cwd}" in split_cmds[0]

    def test_zellij_receives_cwd(self) -> None:
        from synapse.terminal_jump import create_panes

        cwd = "/home/user/project"
        commands = create_panes(
            ["claude"], terminal_app="zellij", all_new=True, cwd=cwd
        )
        assert any("--cwd" in c for c in commands)

    def test_default_cwd_is_os_getcwd(self) -> None:
        """When cwd=None, create_panes should use os.getcwd()."""
        from synapse.terminal_jump import create_panes

        with patch("synapse.terminal_jump.os.getcwd", return_value="/mock/cwd"):
            commands = create_panes(
                ["claude"], terminal_app="tmux", all_new=True, cwd=None
            )
        split_cmds = [c for c in commands if "split-window" in c]
        assert len(split_cmds) >= 1
        assert "-c /mock/cwd" in split_cmds[0]


# ============================================================
# spawn_agent: passes cwd to create_panes
# ============================================================


class TestSpawnAgentCwd:
    """spawn_agent() must pass cwd=os.getcwd() to create_panes."""

    @patch("synapse.spawn.subprocess.run")
    @patch("synapse.spawn.detect_terminal_app", return_value="tmux")
    @patch("synapse.spawn.create_panes")
    @patch("synapse.spawn.PortManager")
    @patch("synapse.spawn.AgentRegistry")
    @patch("synapse.spawn.load_profile")
    @patch("synapse.spawn.os.getcwd", return_value="/test/project")
    def test_passes_cwd(
        self,
        mock_getcwd,
        mock_load_profile,
        mock_registry_cls,
        mock_pm_cls,
        mock_create_panes,
        mock_detect_terminal,
        mock_subprocess_run,
    ) -> None:
        from synapse.spawn import spawn_agent

        mock_pm = MagicMock()
        mock_pm.get_available_port.return_value = 8100
        mock_pm_cls.return_value = mock_pm
        mock_create_panes.return_value = ["tmux split-window ..."]

        spawn_agent(profile="claude")

        mock_create_panes.assert_called_once()
        _, kwargs = mock_create_panes.call_args
        assert kwargs.get("cwd") == "/test/project"
