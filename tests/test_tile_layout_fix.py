"""Tests for tmux post-spawn tiling and pane command execution behavior."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, call, patch

import pytest


def _prepared_agent(
    profile: str,
    port: int,
    *,
    tool_args: list[str] | None = None,
    extra_env: dict[str, str] | None = None,
    worktree_path: str | None = None,
):
    from synapse.spawn import PreparedAgent

    return PreparedAgent(
        profile=profile,
        port=port,
        agent_spec=f"{profile}::::{port}",
        cwd="/tmp/worktree" if worktree_path else "/tmp/project",
        tool_args=tool_args,
        extra_env=extra_env,
        fallback_tool_args=None,
        worktree_path=worktree_path,
        worktree_branch="test-branch" if worktree_path else None,
    )


class TestPostSpawnTilingTmux:
    """Caller-level tmux tiling should only happen for individual spawn paths."""

    @patch("synapse.spawn._post_spawn_tile")
    @patch("synapse.spawn._run_pane_commands")
    @patch("synapse.spawn.create_panes")
    def test_worktree_spawn_runs_tiled_layout(
        self,
        mock_create_panes: MagicMock,
        mock_run_pane_commands: MagicMock,
        mock_post_spawn_tile: MagicMock,
    ) -> None:
        """Worktree spawns should tile after 2+ submitted panes."""
        from synapse.spawn import execute_spawn

        agents = [
            _prepared_agent("claude", 8111, worktree_path="/tmp/wt-1"),
            _prepared_agent("gemini", 8112, worktree_path="/tmp/wt-2"),
        ]
        mock_create_panes.side_effect = [
            ["tmux split-window one"],
            ["tmux split-window two"],
        ]

        execute_spawn(agents, terminal="tmux")

        assert mock_run_pane_commands.call_count == 2
        mock_post_spawn_tile.assert_called_once_with("tmux", 2)

    @patch("synapse.spawn.subprocess.run")
    def test_single_agent_no_tiling(self, mock_run: MagicMock) -> None:
        """Single-pane cases should not invoke tmux select-layout."""
        from synapse.spawn import _post_spawn_tile

        _post_spawn_tile("tmux", 1)

        mock_run.assert_not_called()

    @patch("synapse.spawn._post_spawn_tile")
    @patch("synapse.spawn._run_pane_commands")
    @patch("synapse.spawn.create_panes", return_value=["tmux split-window batch"])
    def test_batch_spawn_no_extra_tiling(
        self,
        _mock_create_panes: MagicMock,
        _mock_run_pane_commands: MagicMock,
        mock_post_spawn_tile: MagicMock,
    ) -> None:
        """Batch tiling stays inside create_panes; caller should not tile again."""
        from synapse.spawn import execute_spawn

        agents = [
            _prepared_agent(
                "claude", 8111, tool_args=["--dangerously-skip-permissions"]
            ),
            _prepared_agent(
                "gemini", 8112, tool_args=["--dangerously-skip-permissions"]
            ),
        ]

        execute_spawn(agents, terminal="tmux")

        mock_post_spawn_tile.assert_not_called()


class TestRunPaneCommandsDelay:
    """Pane command execution should support delay and strict failure mode."""

    @patch("synapse.spawn.time.sleep")
    @patch("synapse.spawn.subprocess.run")
    def test_delay_applied_between_commands(
        self,
        mock_run: MagicMock,
        mock_sleep: MagicMock,
    ) -> None:
        """Delay should apply between commands, not before the first one."""
        from synapse.spawn import _run_pane_commands

        _run_pane_commands(
            [
                "tmux split-window -h",
                "tmux select-pane -T pane",
                "tmux split-window -v",
            ],
            delay=0.1,
        )

        assert mock_run.call_count == 3
        mock_sleep.assert_has_calls([call(0.1), call(0.1)])

    @patch("synapse.spawn.time.sleep")
    @patch("synapse.spawn.subprocess.run")
    def test_no_delay_by_default(
        self,
        mock_run: MagicMock,
        mock_sleep: MagicMock,
    ) -> None:
        """Delay defaults to disabled."""
        from synapse.spawn import _run_pane_commands

        _run_pane_commands(["tmux split-window -h", "tmux split-window -v"])

        assert mock_run.call_count == 2
        mock_sleep.assert_not_called()

    def test_check_true_raises(self) -> None:
        """check=True should surface subprocess failures."""
        from synapse.spawn import _run_pane_commands

        error = subprocess.CalledProcessError(1, ["tmux", "split-window"])
        with patch("synapse.spawn.subprocess.run", side_effect=error):
            with pytest.raises(subprocess.CalledProcessError):
                _run_pane_commands(["tmux split-window -h"], check=True)


class TestZellijPaneCount:
    """Zellij pane count uses an env-backed monotonic counter."""

    def test_env_var_counter(self) -> None:
        """Existing counter should be returned, then incremented."""
        from synapse.terminal_jump import _get_zellij_pane_count

        with patch.dict("os.environ", {"SYNAPSE_ZELLIJ_PANE_COUNT": "2"}, clear=False):
            count = _get_zellij_pane_count()
            assert count == 2
            assert __import__("os").environ["SYNAPSE_ZELLIJ_PANE_COUNT"] == "3"

    def test_default_returns_1(self) -> None:
        """Missing or invalid counter should start from 1."""
        from synapse.terminal_jump import _get_zellij_pane_count

        with patch.dict("os.environ", {}, clear=True):
            count = _get_zellij_pane_count()
            assert count == 1
            assert __import__("os").environ["SYNAPSE_ZELLIJ_PANE_COUNT"] == "2"
