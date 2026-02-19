"""Tests for tool_args passthrough in spawn/team-start commands.

Validates that --dangerously-skip-permissions and other CLI tool arguments
are correctly propagated through the entire chain:
  CLI → spawn_agent/create_panes → _build_agent_command → terminal command
"""

from __future__ import annotations

import argparse
from unittest.mock import MagicMock, patch

# ============================================================
# TestBuildAgentCommandToolArgs
# ============================================================


class TestBuildAgentCommandToolArgs:
    """Tests for _build_agent_command() tool_args parameter."""

    def test_no_tool_args_unchanged(self) -> None:
        """Without tool_args, command should be unchanged."""
        from synapse.terminal_jump import _build_agent_command

        cmd_without = _build_agent_command("claude")
        cmd_with_none = _build_agent_command("claude", tool_args=None)
        assert cmd_without == cmd_with_none
        assert "-- " not in cmd_without

    def test_tool_args_appended(self) -> None:
        """tool_args should be appended after ' -- '."""
        from synapse.terminal_jump import _build_agent_command

        cmd = _build_agent_command(
            "claude", tool_args=["--dangerously-skip-permissions"]
        )
        assert "-- --dangerously-skip-permissions" in cmd

    def test_multiple_tool_args(self) -> None:
        """Multiple tool_args should all appear after ' -- '."""
        from synapse.terminal_jump import _build_agent_command

        cmd = _build_agent_command("claude", tool_args=["--flag1", "--flag2", "value"])
        assert "-- --flag1 --flag2 value" in cmd

    def test_tool_args_special_chars_quoted(self) -> None:
        """Special characters in tool_args should be shell-quoted."""
        from synapse.terminal_jump import _build_agent_command

        cmd = _build_agent_command("claude", tool_args=["--msg=hello world"])
        # shlex.quote should wrap the value
        assert "-- " in cmd
        # The value should be quoted to protect the space
        parts = cmd.split("-- ", 1)[1]
        assert "hello world" in parts or "hello\\ world" in parts

    def test_tool_args_empty_list(self) -> None:
        """Empty tool_args list should not add ' -- '."""
        from synapse.terminal_jump import _build_agent_command

        cmd = _build_agent_command("claude", tool_args=[])
        assert "-- " not in cmd

    def test_exec_and_tool_args_coexist(self) -> None:
        """use_exec=True and tool_args should both work together."""
        from synapse.terminal_jump import _build_agent_command

        cmd = _build_agent_command("claude", use_exec=True, tool_args=["--skip"])
        assert cmd.startswith("exec ")
        assert "-- --skip" in cmd

    def test_tool_args_with_agent_spec(self) -> None:
        """tool_args should work with full agent spec (name:role:etc)."""
        from synapse.terminal_jump import _build_agent_command

        cmd = _build_agent_command(
            "claude:Reviewer:review::8105",
            tool_args=["--dangerously-skip-permissions"],
        )
        assert "--port 8105" in cmd
        assert "--name" in cmd
        assert "-- --dangerously-skip-permissions" in cmd


# ============================================================
# TestCreatePanesToolArgs
# ============================================================


class TestCreatePanesToolArgs:
    """Tests for tool_args propagation through create_panes() and friends."""

    def test_create_panes_passes_tool_args_to_tmux(self) -> None:
        """create_panes with tmux should pass tool_args to _build_agent_command."""
        from synapse.terminal_jump import create_panes

        commands = create_panes(
            ["claude"],
            terminal_app="tmux",
            all_new=True,
            tool_args=["--dangerously-skip-permissions"],
        )
        full = " ".join(commands)
        assert "-- --dangerously-skip-permissions" in full

    def test_create_tmux_panes_tool_args(self) -> None:
        """create_tmux_panes should include tool_args in generated commands."""
        from synapse.terminal_jump import create_tmux_panes

        commands = create_tmux_panes(
            ["claude", "gemini"],
            all_new=True,
            tool_args=["--flag"],
        )
        # All agent commands should include tool_args
        agent_commands = [c for c in commands if "split-window" in c]
        for cmd in agent_commands:
            assert "-- --flag" in cmd

    def test_create_iterm2_panes_tool_args(self) -> None:
        """create_iterm2_panes should include tool_args in AppleScript."""
        from synapse.terminal_jump import create_iterm2_panes

        script = create_iterm2_panes(
            ["claude"],
            all_new=True,
            tool_args=["--dangerously-skip-permissions"],
        )
        assert "-- --dangerously-skip-permissions" in script

    def test_create_terminal_app_tabs_tool_args(self) -> None:
        """create_terminal_app_tabs should include tool_args."""
        from synapse.terminal_jump import create_terminal_app_tabs

        commands = create_terminal_app_tabs(
            ["claude"],
            all_new=True,
            tool_args=["--flag"],
        )
        full = " ".join(commands)
        assert "-- --flag" in full

    def test_create_zellij_panes_tool_args(self) -> None:
        """create_zellij_panes should include tool_args."""
        from synapse.terminal_jump import create_zellij_panes

        commands = create_zellij_panes(
            ["claude"],
            tool_args=["--skip"],
        )
        full = " ".join(commands)
        assert "-- --skip" in full

    def test_create_ghostty_window_tool_args(self) -> None:
        """create_ghostty_window should include tool_args."""
        from synapse.terminal_jump import create_ghostty_window

        commands = create_ghostty_window(
            ["claude"],
            tool_args=["--dangerously-skip-permissions"],
        )
        full = " ".join(commands)
        assert "-- --dangerously-skip-permissions" in full

    def test_create_panes_no_tool_args_backward_compat(self) -> None:
        """create_panes without tool_args should work as before."""
        from synapse.terminal_jump import create_panes

        commands = create_panes(
            ["claude"],
            terminal_app="tmux",
            all_new=True,
        )
        full = " ".join(commands)
        # Extract only the synapse command portion — stop at the next tmux
        # delimiter or end of string to avoid matching tmux's own '--'.
        synapse_idx = full.find("synapse")
        assert synapse_idx != -1, "synapse command not found in output"
        after_synapse = full[synapse_idx:]
        next_tmux = after_synapse.find(" tmux ")
        synapse_part = after_synapse[:next_tmux] if next_tmux != -1 else after_synapse
        assert "-- " not in synapse_part


# ============================================================
# TestSpawnToolArgs
# ============================================================


class TestSpawnToolArgs:
    """Tests for spawn_agent() tool_args parameter."""

    def test_spawn_passes_tool_args_to_create_panes(self) -> None:
        """spawn_agent(tool_args=...) should forward to create_panes."""
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

            spawn_agent("claude", tool_args=["--dangerously-skip-permissions"])

        call_kwargs = mock_cp.call_args[1]
        assert call_kwargs.get("tool_args") == ["--dangerously-skip-permissions"]

    def test_spawn_no_tool_args_passes_none(self) -> None:
        """spawn_agent() without tool_args should pass None."""
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

        call_kwargs = mock_cp.call_args[1]
        assert call_kwargs.get("tool_args") is None


# ============================================================
# TestSpawnCLIToolArgs
# ============================================================


class TestSpawnCLIToolArgs:
    """Tests for CLI parsing of tool_args in spawn command.

    tool_args are pre-extracted from sys.argv via _extract_tool_args()
    before argparse runs, so 'synapse spawn claude -- --flag' works
    by splitting at '--' first.
    """

    def _make_parser(self):
        """Build spawn subparser matching cli.py (no tool_args arg)."""
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

    def test_parse_spawn_with_tool_args(self) -> None:
        """'synapse spawn claude -- --flag' should capture tool_args."""
        from synapse.cli import _extract_tool_args

        argv = ["spawn", "claude", "--", "--dangerously-skip-permissions"]
        clean_argv, tool_args = _extract_tool_args(argv)

        args = self._make_parser().parse_args(clean_argv)
        assert args.profile == "claude"
        assert "--dangerously-skip-permissions" in tool_args

    def test_parse_spawn_without_tool_args(self) -> None:
        """'synapse spawn claude' should have empty tool_args."""
        from synapse.cli import _extract_tool_args

        argv = ["spawn", "claude"]
        clean_argv, tool_args = _extract_tool_args(argv)

        self._make_parser().parse_args(clean_argv)  # should not raise
        assert tool_args == []

    def test_cmd_spawn_forwards_tool_args(self) -> None:
        """cmd_spawn should pass tool_args to spawn_agent."""
        from synapse.cli import cmd_spawn
        from synapse.spawn import SpawnResult

        mock_result = SpawnResult(
            agent_id="synapse-claude-8100",
            port=8100,
            terminal_used="tmux",
            status="submitted",
        )

        agent_info = {"agent_id": "synapse-claude-8100", "pid": 123, "port": 8100}

        # tool_args are pre-extracted by main() — no leading '--'
        args = argparse.Namespace(
            profile="claude",
            port=None,
            name=None,
            role=None,
            skill_set=None,
            terminal=None,
            tool_args=["--dangerously-skip-permissions"],
        )

        with (
            patch("synapse.spawn.spawn_agent", return_value=mock_result) as mock_sa,
            patch("synapse.spawn.wait_for_agent", return_value=agent_info),
        ):
            cmd_spawn(args)

        call_kwargs = mock_sa.call_args[1]
        assert call_kwargs["tool_args"] == ["--dangerously-skip-permissions"]


# ============================================================
# TestTeamStartToolArgs
# ============================================================


class TestTeamStartToolArgs:
    """Tests for tool_args extraction in team start command.

    Note: argparse REMAINDER with nargs='+' agents is tricky because
    the greedy '+' consumes '--'. The CLI implementation strips '--'
    from the agents list at runtime via _extract_tool_args().
    """

    def test_extract_tool_args_from_agents(self) -> None:
        """_extract_tool_args should split agents at '--' separator."""
        from synapse.cli import _extract_tool_args

        agents = ["claude", "gemini", "--", "--flag1", "--flag2"]
        cleaned_agents, tool_args = _extract_tool_args(agents)
        assert cleaned_agents == ["claude", "gemini"]
        assert tool_args == ["--flag1", "--flag2"]

    def test_extract_tool_args_no_separator(self) -> None:
        """When no '--' in agents, tool_args should be empty."""
        from synapse.cli import _extract_tool_args

        agents = ["claude", "gemini"]
        cleaned_agents, tool_args = _extract_tool_args(agents)
        assert cleaned_agents == ["claude", "gemini"]
        assert tool_args == []

    def test_extract_tool_args_separator_only(self) -> None:
        """'--' with no args after should give empty tool_args."""
        from synapse.cli import _extract_tool_args

        agents = ["claude", "--"]
        cleaned_agents, tool_args = _extract_tool_args(agents)
        assert cleaned_agents == ["claude"]
        assert tool_args == []


# ============================================================
# TestSpawnAPIToolArgs
# ============================================================


class TestSpawnAPIToolArgs:
    """Tests for API model tool_args field."""

    def test_spawn_request_accepts_tool_args(self) -> None:
        """SpawnRequest should accept tool_args field."""
        from synapse.a2a_compat import SpawnRequest

        req = SpawnRequest(
            profile="claude",
            tool_args=["--dangerously-skip-permissions"],
        )
        assert req.tool_args == ["--dangerously-skip-permissions"]

    def test_spawn_request_tool_args_optional(self) -> None:
        """tool_args should default to None."""
        from synapse.a2a_compat import SpawnRequest

        req = SpawnRequest(profile="claude")
        assert req.tool_args is None

    def test_team_start_request_accepts_tool_args(self) -> None:
        """TeamStartRequest should accept tool_args field."""
        from synapse.a2a_compat import TeamStartRequest

        req = TeamStartRequest(
            agents=["claude", "gemini"],
            tool_args=["--flag"],
        )
        assert req.tool_args == ["--flag"]
