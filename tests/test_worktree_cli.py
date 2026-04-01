"""CLI integration tests for worktree support in spawn/team-start."""

from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import MagicMock, patch


class TestSpawnParserWorktree:
    """Test that the spawn subcommand parser accepts --worktree."""

    def _get_spawn_parser(self) -> argparse.ArgumentParser:
        """Build a minimal spawn parser mirroring cli.py's p_spawn."""
        parser = argparse.ArgumentParser()
        parser.add_argument("profile")
        parser.add_argument("--port", type=int)
        parser.add_argument("--name", "-n")
        parser.add_argument("--role", "-r")
        parser.add_argument("--skill-set", "-S", dest="skill_set")
        parser.add_argument("--terminal")
        parser.add_argument(
            "--worktree",
            "-w",
            nargs="?",
            const=True,
            default=None,
            metavar="NAME",
        )
        return parser

    def test_spawn_parser_accepts_worktree(self) -> None:
        parser = self._get_spawn_parser()
        args = parser.parse_args(["claude", "--worktree"])
        assert args.worktree is True
        assert args.profile == "claude"

    def test_spawn_parser_worktree_with_name(self) -> None:
        parser = self._get_spawn_parser()
        args = parser.parse_args(["claude", "--worktree", "feature-auth"])
        assert args.worktree == "feature-auth"

    def test_spawn_parser_worktree_short_flag(self) -> None:
        parser = self._get_spawn_parser()
        args = parser.parse_args(["claude", "-w"])
        assert args.worktree is True

    def test_spawn_parser_worktree_default_none(self) -> None:
        parser = self._get_spawn_parser()
        args = parser.parse_args(["claude"])
        assert args.worktree is None


class TestTeamStartParserWorktree:
    """Test that team start parser accepts --worktree."""

    def _get_team_start_parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser()
        parser.add_argument("agents", nargs="+")
        parser.add_argument("--layout", default="split")
        parser.add_argument("--all-new", action="store_true")
        parser.add_argument(
            "--worktree",
            "-w",
            nargs="?",
            const=True,
            default=None,
            metavar="NAME",
        )
        return parser

    def test_team_start_parser_accepts_worktree(self) -> None:
        parser = self._get_team_start_parser()
        args = parser.parse_args(["claude", "gemini", "--worktree"])
        assert args.worktree is True
        assert args.agents == ["claude", "gemini"]

    def test_team_start_parser_worktree_with_name(self) -> None:
        parser = self._get_team_start_parser()
        args = parser.parse_args(["claude", "gemini", "--worktree", "team-task"])
        assert args.worktree == "team-task"


class TestCmdSpawnWithWorktree:
    """Test that cmd_spawn integrates with worktree creation."""

    @patch("synapse.spawn.create_panes", return_value=["echo test"])
    @patch("subprocess.run")
    def test_cmd_spawn_with_worktree_calls_create_worktree(
        self,
        mock_subprocess_run: MagicMock,
        mock_create_panes: MagicMock,
        tmp_path: Path,
    ) -> None:
        from synapse.spawn import spawn_agent
        from synapse.worktree import WorktreeInfo

        mock_subprocess_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        wt_dir = tmp_path / ".synapse" / "worktrees" / "test-wt"

        mock_wt_info = WorktreeInfo(
            name="test-wt",
            path=wt_dir,
            branch="worktree-test-wt",
            base_branch="origin/main",
            created_at=1000.0,
        )

        with (
            patch("synapse.spawn.load_profile"),
            patch("synapse.spawn.is_port_available", return_value=True),
            patch("synapse.spawn.detect_terminal_app", return_value="tmux"),
            patch(
                "synapse.worktree.create_worktree", return_value=mock_wt_info
            ) as mock_create_wt,
        ):
            result = spawn_agent(
                profile="claude",
                port=8100,
                worktree=True,
            )

            mock_create_wt.assert_called_once_with(name=None, base_branch=None)
            assert result.worktree_path == str(wt_dir)
            assert result.worktree_branch == "worktree-test-wt"

            # Verify cwd and env propagation to create_panes
            panes_call = mock_create_panes.call_args
            assert panes_call.kwargs["cwd"] == str(wt_dir)
            env = panes_call.kwargs["extra_env"]
            assert env["SYNAPSE_WORKTREE_PATH"] == str(wt_dir)
            assert env["SYNAPSE_WORKTREE_BRANCH"] == "worktree-test-wt"

    @patch("synapse.spawn.create_panes", return_value=["echo test"])
    @patch("subprocess.run")
    def test_cmd_spawn_with_worktree_name(
        self,
        mock_subprocess_run: MagicMock,
        mock_create_panes: MagicMock,
        tmp_path: Path,
    ) -> None:
        from synapse.spawn import spawn_agent
        from synapse.worktree import WorktreeInfo

        wt_dir = tmp_path / ".synapse" / "worktrees" / "my-feature"
        mock_wt_info = WorktreeInfo(
            name="my-feature",
            path=wt_dir,
            branch="worktree-my-feature",
            base_branch="origin/main",
            created_at=1000.0,
        )

        mock_subprocess_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        with (
            patch("synapse.spawn.load_profile"),
            patch("synapse.spawn.is_port_available", return_value=True),
            patch("synapse.spawn.detect_terminal_app", return_value="tmux"),
            patch(
                "synapse.worktree.create_worktree", return_value=mock_wt_info
            ) as mock_create_wt,
        ):
            result = spawn_agent(
                profile="claude",
                port=8100,
                worktree="my-feature",
            )

            mock_create_wt.assert_called_once_with(name="my-feature", base_branch=None)
            assert result.worktree_path == str(wt_dir)

            # Verify cwd and env propagation to create_panes
            panes_call = mock_create_panes.call_args
            assert panes_call.kwargs["cwd"] == str(wt_dir)
            env = panes_call.kwargs["extra_env"]
            assert env["SYNAPSE_WORKTREE_PATH"] == str(wt_dir)
            assert env["SYNAPSE_WORKTREE_BRANCH"] == "worktree-my-feature"

    @patch("synapse.spawn.create_panes", return_value=["echo test"])
    @patch("subprocess.run")
    def test_cmd_spawn_without_worktree(
        self,
        mock_subprocess_run: MagicMock,
        mock_create_panes: MagicMock,
    ) -> None:
        from synapse.spawn import spawn_agent

        mock_subprocess_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        with (
            patch("synapse.spawn.load_profile"),
            patch("synapse.spawn.is_port_available", return_value=True),
            patch("synapse.spawn.detect_terminal_app", return_value="tmux"),
        ):
            result = spawn_agent(
                profile="claude",
                port=8100,
            )

            assert result.worktree_path is None
            assert result.worktree_branch is None


class TestSpawnResultWorktreeFields:
    """Test that SpawnResult has worktree fields."""

    def test_spawn_result_has_worktree_fields(self) -> None:
        from synapse.spawn import SpawnResult

        result = SpawnResult(
            agent_id="synapse-claude-8100",
            port=8100,
            terminal_used="tmux",
            status="submitted",
            worktree_path="/repo/.synapse/worktrees/test",
            worktree_branch="worktree-test",
        )
        assert result.worktree_path == "/repo/.synapse/worktrees/test"
        assert result.worktree_branch == "worktree-test"

    def test_spawn_result_worktree_defaults_none(self) -> None:
        from synapse.spawn import SpawnResult

        result = SpawnResult(
            agent_id="synapse-claude-8100",
            port=8100,
            terminal_used="tmux",
            status="submitted",
        )
        assert result.worktree_path is None
        assert result.worktree_branch is None
