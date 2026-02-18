"""Tests for synapse spawn command — single-agent pane spawning.

Test-first development: these tests define the expected behavior for
the `synapse spawn` CLI command and `spawn_agent()` core function.
"""

from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest

# ============================================================
# TestSpawnCLIParsing - CLI argument parsing
# ============================================================


def _make_spawn_parser():
    """Build the spawn subparser matching cli.py's definition.

    Note: tool_args are NOT in the parser — they are pre-extracted
    from sys.argv by _extract_tool_args() in main() before parsing.
    """
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command")
    p = sub.add_parser("spawn")
    p.add_argument("profile")
    p.add_argument("--port", type=int)
    p.add_argument("--name", "-n")
    p.add_argument("--role", "-r")
    p.add_argument("--skill-set", "-S", dest="skill_set")
    p.add_argument("--terminal")
    return parser


class TestSpawnCLIParsing:
    """Tests for synapse spawn CLI argument parsing using real argparse."""

    def test_spawn_accepts_profile(self) -> None:
        """synapse spawn claude should parse profile as positional arg."""
        args = _make_spawn_parser().parse_args(["spawn", "claude"])
        assert args.profile == "claude"
        assert args.port is None
        assert args.name is None

    def test_spawn_accepts_port(self) -> None:
        """--port should accept an integer and convert to int type."""
        args = _make_spawn_parser().parse_args(["spawn", "gemini", "--port", "8115"])
        assert args.port == 8115
        assert isinstance(args.port, int)

    def test_spawn_accepts_name_and_role(self) -> None:
        """--name and --role should be parsed correctly."""
        args = _make_spawn_parser().parse_args(
            ["spawn", "claude", "--name", "Tester", "--role", "test writer"]
        )
        assert args.name == "Tester"
        assert args.role == "test writer"

    def test_spawn_accepts_skill_set(self) -> None:
        """--skill-set (and short -S) should be parsed into skill_set."""
        args = _make_spawn_parser().parse_args(
            ["spawn", "claude", "--skill-set", "dev-set"]
        )
        assert args.skill_set == "dev-set"

        args_short = _make_spawn_parser().parse_args(
            ["spawn", "claude", "-S", "dev-set"]
        )
        assert args_short.skill_set == "dev-set"

    def test_spawn_accepts_terminal(self) -> None:
        """--terminal should accept an explicit terminal choice."""
        args = _make_spawn_parser().parse_args(
            ["spawn", "claude", "--terminal", "tmux"]
        )
        assert args.terminal == "tmux"

    def test_spawn_name_role_not_eaten_by_tool_args(self) -> None:
        """--name and --role must NOT be swallowed by tool_args.

        Bug: argparse.REMAINDER consumed everything after 'profile',
        making --name/--role always None. Fix: tool_args are now
        pre-extracted from sys.argv via _extract_tool_args() before
        argparse sees them.
        """
        args = _make_spawn_parser().parse_args(
            ["spawn", "claude", "--name", "Reviewer", "--role", "code review"]
        )
        assert args.name == "Reviewer"
        assert args.role == "code review"

    def test_spawn_tool_args_after_separator(self) -> None:
        """Arguments after '--' are pre-extracted by _extract_tool_args().

        The '--' separator and everything after it are stripped from
        sys.argv before argparse runs, then attached as args.tool_args.
        """
        from synapse.cli import _extract_tool_args

        argv = ["spawn", "claude", "--name", "X", "--", "--skip-perms"]
        clean_argv, tool_args = _extract_tool_args(argv)

        args = _make_spawn_parser().parse_args(clean_argv)
        assert args.name == "X"
        assert tool_args == ["--skip-perms"]


# ============================================================
# TestSpawnAgent - Core spawn_agent() function
# ============================================================


class TestSpawnAgent:
    """Tests for spawn_agent() function."""

    def test_spawn_returns_result(self) -> None:
        """spawn_agent() should return a SpawnResult with agent_id and port."""
        from synapse.spawn import SpawnResult, spawn_agent

        with (
            patch("synapse.spawn.load_profile", return_value={"name": "claude"}),
            patch("synapse.spawn.PortManager") as mock_pm_cls,
            patch("synapse.spawn.detect_terminal_app", return_value="tmux"),
            patch("synapse.spawn.create_panes", return_value=["tmux cmd"]),
            patch("subprocess.run"),
        ):
            mock_pm = MagicMock()
            mock_pm.get_available_port.return_value = 8100
            mock_pm_cls.return_value = mock_pm

            result = spawn_agent("claude")

        assert isinstance(result, SpawnResult)
        assert result.agent_id == "synapse-claude-8100"
        assert result.port == 8100
        assert result.status == "submitted"

    def test_spawn_with_explicit_port(self) -> None:
        """Explicit port should be used if available."""
        from synapse.spawn import spawn_agent

        with (
            patch("synapse.spawn.load_profile", return_value={"name": "gemini"}),
            patch("synapse.spawn.is_port_available", return_value=True),
            patch("synapse.spawn.detect_terminal_app", return_value="tmux"),
            patch("synapse.spawn.create_panes", return_value=["tmux cmd"]),
            patch("subprocess.run"),
        ):
            result = spawn_agent("gemini", port=8115)

        assert result.port == 8115
        assert result.agent_id == "synapse-gemini-8115"

    def test_spawn_port_in_use_raises(self) -> None:
        """Explicit port that is in use should raise RuntimeError."""
        from synapse.spawn import spawn_agent

        with (
            patch("synapse.spawn.load_profile", return_value={"name": "claude"}),
            patch("synapse.spawn.is_port_available", return_value=False),
            pytest.raises(RuntimeError, match="Port 8100 is already in use"),
        ):
            spawn_agent("claude", port=8100)

    def test_spawn_port_exhaustion_raises(self) -> None:
        """If no ports available, should raise RuntimeError."""
        from synapse.spawn import spawn_agent

        with (
            patch("synapse.spawn.load_profile", return_value={"name": "claude"}),
            patch("synapse.spawn.PortManager") as mock_pm_cls,
            pytest.raises(RuntimeError, match="No available ports"),
        ):
            mock_pm = MagicMock()
            mock_pm.get_available_port.return_value = None
            mock_pm.format_exhaustion_error.return_value = (
                "No available ports for claude"
            )
            mock_pm_cls.return_value = mock_pm

            spawn_agent("claude")

    def test_spawn_invalid_profile_raises(self) -> None:
        """Invalid profile should raise FileNotFoundError."""
        from synapse.spawn import spawn_agent

        with (
            patch(
                "synapse.spawn.load_profile",
                side_effect=FileNotFoundError("Profile nonexistent not found"),
            ),
            pytest.raises(FileNotFoundError),
        ):
            spawn_agent("nonexistent")

    def test_spawn_no_terminal_raises(self) -> None:
        """If no terminal detected and none specified, should raise RuntimeError."""
        from synapse.spawn import spawn_agent

        with (
            patch("synapse.spawn.load_profile", return_value={"name": "claude"}),
            patch("synapse.spawn.PortManager") as mock_pm_cls,
            patch("synapse.spawn.detect_terminal_app", return_value=None),
            pytest.raises(RuntimeError, match="No supported terminal detected"),
        ):
            mock_pm = MagicMock()
            mock_pm.get_available_port.return_value = 8100
            mock_pm_cls.return_value = mock_pm

            spawn_agent("claude")

    def test_spawn_passes_name_and_role(self) -> None:
        """name and role should be passed through to the agent spec."""
        from synapse.spawn import spawn_agent

        with (
            patch("synapse.spawn.load_profile", return_value={"name": "claude"}),
            patch("synapse.spawn.PortManager") as mock_pm_cls,
            patch("synapse.spawn.detect_terminal_app", return_value="tmux"),
            patch("synapse.spawn.create_panes", return_value=["tmux cmd"]) as mock_cp,
            patch("subprocess.run"),
        ):
            mock_pm = MagicMock()
            mock_pm.get_available_port.return_value = 8100
            mock_pm_cls.return_value = mock_pm

            spawn_agent("claude", name="Reviewer", role="code review")

        # The agent spec should include name and role
        call_args = mock_cp.call_args
        agent_specs = call_args[0][0]  # First positional arg (agents list)
        spec = agent_specs[0]
        assert "Reviewer" in spec
        assert "code review" in spec

    def test_spawn_explicit_terminal(self) -> None:
        """Explicit terminal should override auto-detection."""
        from synapse.spawn import spawn_agent

        with (
            patch("synapse.spawn.load_profile", return_value={"name": "claude"}),
            patch("synapse.spawn.PortManager") as mock_pm_cls,
            patch("synapse.spawn.create_panes", return_value=["iterm cmd"]) as mock_cp,
            patch("subprocess.run"),
        ):
            mock_pm = MagicMock()
            mock_pm.get_available_port.return_value = 8100
            mock_pm_cls.return_value = mock_pm

            result = spawn_agent("claude", terminal="iTerm2")

        assert result.terminal_used == "iTerm2"
        # create_panes should receive the explicit terminal
        call_kwargs = mock_cp.call_args
        assert call_kwargs[1].get("terminal_app") == "iTerm2"

    def test_spawn_command_failure_raises(self) -> None:
        """If pane creation command fails, spawn_agent should raise RuntimeError."""
        from synapse.spawn import spawn_agent

        with (
            patch("synapse.spawn.load_profile", return_value={"name": "claude"}),
            patch("synapse.spawn.PortManager") as mock_pm_cls,
            patch("synapse.spawn.detect_terminal_app", return_value="tmux"),
            patch("synapse.spawn.create_panes", return_value=["tmux bad-cmd"]),
            patch(
                "subprocess.run",
                side_effect=subprocess.CalledProcessError(1, ["tmux", "bad-cmd"]),
            ),
            pytest.raises(RuntimeError, match="Failed to spawn agent"),
        ):
            mock_pm = MagicMock()
            mock_pm.get_available_port.return_value = 8100
            mock_pm_cls.return_value = mock_pm

            spawn_agent("claude")


# ============================================================
# TestSpawnCLIExecution - cmd_spawn() output
# ============================================================


class TestSpawnCLIExecution:
    """Tests for cmd_spawn() CLI command execution."""

    def test_cmd_spawn_prints_agent_id_and_port(self, capsys) -> None:
        """cmd_spawn should print '{agent_id} {port}' on success."""
        from synapse.cli import cmd_spawn
        from synapse.spawn import SpawnResult

        mock_result = SpawnResult(
            agent_id="synapse-claude-8100",
            port=8100,
            terminal_used="tmux",
            status="submitted",
        )

        args = argparse.Namespace(
            profile="claude",
            port=None,
            name=None,
            role=None,
            skill_set=None,
            terminal=None,
        )

        with patch("synapse.spawn.spawn_agent", return_value=mock_result):
            cmd_spawn(args)

        captured = capsys.readouterr()
        assert "synapse-claude-8100 8100" in captured.out

    def test_cmd_spawn_error_exits_1(self) -> None:
        """cmd_spawn should exit(1) on error."""
        from synapse.cli import cmd_spawn

        args = argparse.Namespace(
            profile="nonexistent",
            port=None,
            name=None,
            role=None,
            skill_set=None,
            terminal=None,
        )

        with (
            patch(
                "synapse.spawn.spawn_agent",
                side_effect=FileNotFoundError("Profile not found"),
            ),
            pytest.raises(SystemExit) as exc_info,
        ):
            cmd_spawn(args)

        assert exc_info.value.code == 1


# ============================================================
# TestGhosttyPaneCreation - Ghostty window creation
# ============================================================


class TestGhosttyPaneCreation:
    """Tests for create_ghostty_window() function."""

    def test_create_ghostty_window_generates_open_command(self) -> None:
        """Should generate macOS 'open' command for Ghostty."""
        from synapse.terminal_jump import create_ghostty_window

        commands = create_ghostty_window(
            agents=["claude"],
        )
        assert isinstance(commands, list)
        assert len(commands) > 0
        # Should use 'open -na Ghostty' pattern
        assert any("open" in cmd and "Ghostty" in cmd for cmd in commands)

    def test_create_ghostty_window_includes_agent_command(self) -> None:
        """The generated command should include synapse agent command."""
        from synapse.terminal_jump import create_ghostty_window

        commands = create_ghostty_window(
            agents=["claude:Reviewer:code-review"],
        )
        # Should contain synapse command for the agent
        full = " ".join(commands)
        assert "synapse" in full
        assert "claude" in full

    def test_create_ghostty_window_multiple_agents(self) -> None:
        """Multiple agents should each get their own Ghostty window."""
        from synapse.terminal_jump import create_ghostty_window

        commands = create_ghostty_window(
            agents=["claude", "gemini"],
        )
        # Each agent should produce a command
        assert len(commands) == 2


# ============================================================
# TestBuildAgentCommandPort - Port field in agent spec
# ============================================================


class TestBuildAgentCommandPort:
    """Tests for _build_agent_command() port field support."""

    def test_port_field_generates_port_flag(self) -> None:
        """5th colon field should generate --port flag."""
        from synapse.terminal_jump import _build_agent_command

        cmd = _build_agent_command("claude:Reviewer:review::8105")
        assert "--port 8105" in cmd

    def test_port_field_backward_compat(self) -> None:
        """4-field spec should still work without port."""
        from synapse.terminal_jump import _build_agent_command

        cmd = _build_agent_command("claude:Reviewer:review:dev-set")
        assert "--port" not in cmd
        assert "--name" in cmd
        assert "--role" in cmd
        assert "--skill-set" in cmd

    def test_port_only_field(self) -> None:
        """Spec with empty name/role/skill-set but port should work."""
        from synapse.terminal_jump import _build_agent_command

        cmd = _build_agent_command("claude::::8100")
        assert "--port 8100" in cmd
        assert "--name" not in cmd

    def test_no_setup_added_when_extra_fields(self) -> None:
        """--no-setup should be added when any colon field is present."""
        from synapse.terminal_jump import _build_agent_command

        cmd = _build_agent_command("claude::::8100")
        assert "--no-setup" in cmd

    def test_invalid_port_field_raises_value_error(self) -> None:
        """Non-numeric port in agent spec should be rejected."""
        from synapse.terminal_jump import _build_agent_command

        with pytest.raises(ValueError):
            _build_agent_command("claude::::not-a-port")

    def test_uses_python_module_launcher_instead_of_bare_synapse(self) -> None:
        """Child command should use current Python launcher for consistency."""
        from synapse.terminal_jump import _build_agent_command

        cmd = _build_agent_command("codex::::8121:headless")
        expected_fragment = f"{shlex.quote(sys.executable)} -m synapse.cli codex"

        assert expected_fragment in cmd
        assert not cmd.startswith("synapse codex")


# ============================================================
# TestHeadlessMode - spawn always uses --headless
# ============================================================


class TestHeadlessMode:
    """Tests for headless mode in spawn-generated commands."""

    def test_spawn_generates_headless_flag(self) -> None:
        """spawn_agent should generate commands with --headless flag."""
        from synapse.spawn import spawn_agent

        with (
            patch("synapse.spawn.load_profile", return_value={"name": "claude"}),
            patch("synapse.spawn.PortManager") as mock_pm_cls,
            patch("synapse.spawn.detect_terminal_app", return_value="tmux"),
            patch("synapse.spawn.create_panes", return_value=["tmux cmd"]) as mock_cp,
            patch("subprocess.run"),
        ):
            mock_pm = MagicMock()
            mock_pm.get_available_port.return_value = 8100
            mock_pm_cls.return_value = mock_pm

            spawn_agent("claude")

        # The agent spec should produce a command with --headless
        call_args = mock_cp.call_args
        agent_specs = call_args[0][0]
        spec = agent_specs[0]
        # Verify _build_agent_command produces --headless for this spec
        from synapse.terminal_jump import _build_agent_command

        cmd = _build_agent_command(spec)
        assert "--headless" in cmd

    def test_build_agent_command_headless_flag(self) -> None:
        """6th colon field 'headless' should generate --headless flag."""
        from synapse.terminal_jump import _build_agent_command

        cmd = _build_agent_command("claude::::8100:headless")
        assert "--headless" in cmd
        assert "--no-setup" in cmd
        assert "--port 8100" in cmd

    def test_build_agent_command_no_headless_backward_compat(self) -> None:
        """5-field spec without headless should not add --headless."""
        from synapse.terminal_jump import _build_agent_command

        cmd = _build_agent_command("claude::::8100")
        assert "--headless" not in cmd


# ============================================================
# TestWaitForAgent - Registry polling
# ============================================================


class TestWaitForAgent:
    """Tests for wait_for_agent() registry polling."""

    def test_wait_finds_registered_agent(self) -> None:
        """Should return agent info when agent appears in registry."""
        from synapse.spawn import wait_for_agent

        agent_info = {"agent_id": "synapse-claude-8100", "pid": 12345, "port": 8100}

        with (
            patch("synapse.spawn.AgentRegistry") as mock_reg_cls,
            patch("synapse.port_manager.is_process_alive", return_value=True),
        ):
            mock_reg = MagicMock()
            mock_reg.list_agents.return_value = {"synapse-claude-8100": agent_info}
            mock_reg_cls.return_value = mock_reg

            result = wait_for_agent("synapse-claude-8100", timeout=1.0)

        assert result == agent_info

    def test_wait_returns_none_on_timeout(self) -> None:
        """Should return None when agent never appears."""
        from synapse.spawn import wait_for_agent

        with patch("synapse.spawn.AgentRegistry") as mock_reg_cls:
            mock_reg = MagicMock()
            mock_reg.list_agents.return_value = {}
            mock_reg_cls.return_value = mock_reg

            result = wait_for_agent(
                "synapse-claude-8100", timeout=0.3, poll_interval=0.1
            )

        assert result is None

    def test_wait_skips_dead_process(self) -> None:
        """Should not return info for a dead process."""
        from synapse.spawn import wait_for_agent

        agent_info = {"agent_id": "synapse-claude-8100", "pid": 99999, "port": 8100}

        with (
            patch("synapse.spawn.AgentRegistry") as mock_reg_cls,
            patch("synapse.port_manager.is_process_alive", return_value=False),
        ):
            mock_reg = MagicMock()
            mock_reg.list_agents.return_value = {"synapse-claude-8100": agent_info}
            mock_reg_cls.return_value = mock_reg

            result = wait_for_agent(
                "synapse-claude-8100", timeout=0.3, poll_interval=0.1
            )

        assert result is None


# ============================================================
# TestClaudeCodeEnvUnset - Prevent nested session detection
# ============================================================


class TestClaudeCodeEnvUnset:
    """Tests for CLAUDECODE env var unset in spawned agent commands.

    When synapse spawn is run from within a Claude Code session, the
    CLAUDECODE environment variable is inherited by child processes.
    Claude Code detects this and refuses to start, thinking it's a
    nested session. The fix is to unset CLAUDECODE via `env -u` in
    the generated command.
    """

    def test_env_unset_without_exec(self) -> None:
        """Without exec, command should start with 'env -u CLAUDECODE'."""
        from synapse.terminal_jump import _build_agent_command

        cmd = _build_agent_command("claude")
        assert cmd.startswith("env -u CLAUDECODE")

    def test_env_unset_with_exec(self) -> None:
        """With use_exec=True, 'exec' should precede 'env -u CLAUDECODE'."""
        from synapse.terminal_jump import _build_agent_command

        cmd = _build_agent_command("claude", use_exec=True)
        assert cmd.startswith("exec env -u CLAUDECODE")

    @pytest.mark.parametrize(
        "profile", ["claude", "gemini", "codex", "opencode", "copilot"]
    )
    def test_env_unset_all_profiles(self, profile: str) -> None:
        """All agent profiles should unset CLAUDECODE, not just claude."""
        from synapse.terminal_jump import _build_agent_command

        cmd = _build_agent_command(profile)
        assert cmd.startswith("env -u CLAUDECODE")

    def test_zellij_panes_include_env_unset(self) -> None:
        """Zellij pane commands should include env -u CLAUDECODE."""
        from synapse.terminal_jump import create_zellij_panes

        commands = create_zellij_panes(agents=["claude"], layout="split")
        assert any("env -u CLAUDECODE" in cmd for cmd in commands)

    def test_tmux_panes_include_env_unset(self) -> None:
        """tmux pane commands should include env -u CLAUDECODE."""
        from synapse.terminal_jump import create_tmux_panes

        commands = create_tmux_panes(agents=["claude", "gemini"], all_new=True)
        split_cmds = [c for c in commands if "split-window" in c]
        assert split_cmds, "Expected at least one split-window command"
        assert all("env -u CLAUDECODE" in cmd for cmd in split_cmds)
