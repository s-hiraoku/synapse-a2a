"""Tests for synapse spawn --task / --task-file support."""

from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import patch

import pytest


def _make_spawn_parser() -> argparse.ArgumentParser:
    """Build the spawn parser with the expected task-related flags."""
    from synapse.cli import _add_response_mode_flags

    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command")
    p = sub.add_parser("spawn")
    p.add_argument("profile")
    p.add_argument("--port", type=int)
    p.add_argument("--name", "-n")
    p.add_argument("--role", "-r")
    p.add_argument("--skill-set", "-S", dest="skill_set")
    p.add_argument("--terminal")
    task_group = p.add_mutually_exclusive_group()
    task_group.add_argument("--task", dest="task", default=None)
    task_group.add_argument("--task-file", dest="task_file", default=None)
    p.add_argument("--task-timeout", dest="task_timeout", type=int, default=30)
    _add_response_mode_flags(p)
    return parser


def _make_args(**overrides: object) -> argparse.Namespace:
    data: dict[str, object] = {
        "profile": "claude",
        "port": None,
        "name": None,
        "role": None,
        "skill_set": None,
        "terminal": None,
        "tool_args": [],
        "worktree": None,
        "no_auto_approve": False,
        "branch": None,
        "task": None,
        "task_file": None,
        "task_timeout": 30,
        "response_mode": None,
    }
    data.update(overrides)
    return argparse.Namespace(**data)


class TestSpawnTaskCLIParsing:
    """argparse coverage for spawn task options."""

    def test_spawn_accepts_task_option(self) -> None:
        args = _make_spawn_parser().parse_args(
            ["spawn", "claude", "--task", "Write tests"]
        )

        assert args.task == "Write tests"
        assert args.task_file is None

    def test_spawn_accepts_task_file_option(self) -> None:
        args = _make_spawn_parser().parse_args(
            ["spawn", "claude", "--task-file", "./task.md"]
        )

        assert args.task is None
        assert args.task_file == "./task.md"

    def test_spawn_task_and_task_file_mutually_exclusive(self) -> None:
        with pytest.raises(SystemExit):
            _make_spawn_parser().parse_args(
                [
                    "spawn",
                    "claude",
                    "--task",
                    "Write tests",
                    "--task-file",
                    "./task.md",
                ]
            )

    def test_spawn_task_with_wait_notify_silent(self) -> None:
        parser = _make_spawn_parser()

        wait_args = parser.parse_args(["spawn", "claude", "--task", "Write", "--wait"])
        notify_args = parser.parse_args(
            ["spawn", "claude", "--task", "Write", "--notify"]
        )
        silent_args = parser.parse_args(
            ["spawn", "claude", "--task", "Write", "--silent"]
        )

        assert wait_args.response_mode == "wait"
        assert notify_args.response_mode == "notify"
        assert silent_args.response_mode == "silent"

    def test_spawn_task_timeout_option(self) -> None:
        args = _make_spawn_parser().parse_args(
            ["spawn", "claude", "--task", "Write tests", "--task-timeout", "60"]
        )

        assert args.task_timeout == 60


class TestSpawnTaskExecution:
    """cmd_spawn behavior when a task should be sent after readiness."""

    def test_cmd_spawn_with_task_sends_after_ready(self, capsys) -> None:
        from synapse.cli import cmd_spawn
        from synapse.spawn import SpawnResult

        args = _make_args(task="Write tests", response_mode="wait")
        result = SpawnResult(
            agent_id="synapse-claude-8100",
            port=8100,
            terminal_used="tmux",
            status="submitted",
        )
        agent_info = {"agent_id": result.agent_id, "pid": 12345}

        with (
            patch("synapse.spawn.spawn_agent", return_value=result),
            patch("synapse.spawn.wait_for_agent", return_value=agent_info) as mock_wait,
            patch("synapse.cli._run_a2a_command") as mock_run,
            patch(
                "synapse.cli._build_a2a_cmd",
                return_value=["python", "-m", "synapse.tools.a2a", "send"],
            ) as mock_build,
        ):
            cmd_spawn(args)

        mock_wait.assert_called_once_with(
            result.agent_id, timeout=30, poll_interval=0.5
        )
        mock_build.assert_called_once_with(
            "send",
            "Write tests",
            target=result.agent_id,
            response_mode="wait",
            force=False,
        )
        mock_run.assert_called_once_with(
            ["python", "-m", "synapse.tools.a2a", "send"], exit_on_error=True
        )
        captured = capsys.readouterr()
        assert f"{result.agent_id} {result.port}" in captured.out

    def test_cmd_spawn_with_task_file_reads_file(self, tmp_path: Path) -> None:
        from synapse.cli import cmd_spawn
        from synapse.spawn import SpawnResult

        task_file = tmp_path / "task.md"
        task_file.write_text("Write tests from file", encoding="utf-8")
        args = _make_args(task_file=str(task_file))
        result = SpawnResult(
            agent_id="synapse-claude-8100",
            port=8100,
            terminal_used="tmux",
            status="submitted",
        )
        agent_info = {"agent_id": result.agent_id, "pid": 12345}

        with (
            patch("synapse.spawn.spawn_agent", return_value=result),
            patch("synapse.spawn.wait_for_agent", return_value=agent_info),
            patch("synapse.cli._run_a2a_command"),
            patch("synapse.cli._build_a2a_cmd") as mock_build,
        ):
            cmd_spawn(args)

        assert mock_build.call_args.args[1] == "Write tests from file"

    def test_cmd_spawn_task_timeout_prints_warning(self, capsys) -> None:
        from synapse.cli import cmd_spawn
        from synapse.spawn import SpawnResult

        args = _make_args(task="Write tests")
        result = SpawnResult(
            agent_id="synapse-claude-8100",
            port=8100,
            terminal_used="tmux",
            status="submitted",
        )

        with (
            patch("synapse.spawn.spawn_agent", return_value=result),
            patch("synapse.spawn.wait_for_agent", return_value=None),
            patch("synapse.cli._run_a2a_command") as mock_run,
            patch("synapse.cli._build_a2a_cmd") as mock_build,
        ):
            cmd_spawn(args)

        mock_build.assert_not_called()
        mock_run.assert_not_called()
        captured = capsys.readouterr()
        assert "not yet registered after spawn" in captured.err
        assert f"synapse send {result.agent_id}" in captured.err

    def test_cmd_spawn_task_uses_extended_timeout(self) -> None:
        from synapse.cli import cmd_spawn
        from synapse.spawn import SpawnResult

        args = _make_args(task="Write tests", task_timeout=60)
        result = SpawnResult(
            agent_id="synapse-claude-8100",
            port=8100,
            terminal_used="tmux",
            status="submitted",
        )
        agent_info = {"agent_id": result.agent_id, "pid": 12345}

        with (
            patch("synapse.spawn.spawn_agent", return_value=result),
            patch("synapse.spawn.wait_for_agent", return_value=agent_info) as mock_wait,
            patch("synapse.cli._run_a2a_command"),
            patch("synapse.cli._build_a2a_cmd"),
        ):
            cmd_spawn(args)

        mock_wait.assert_called_once_with(
            result.agent_id, timeout=60, poll_interval=0.5
        )

    def test_cmd_spawn_task_respects_response_mode(self) -> None:
        from synapse.cli import cmd_spawn
        from synapse.spawn import SpawnResult

        args = _make_args(task="Write tests", response_mode="silent")
        result = SpawnResult(
            agent_id="synapse-claude-8100",
            port=8100,
            terminal_used="tmux",
            status="submitted",
        )
        agent_info = {"agent_id": result.agent_id, "pid": 12345}

        with (
            patch("synapse.spawn.spawn_agent", return_value=result),
            patch("synapse.spawn.wait_for_agent", return_value=agent_info),
            patch("synapse.cli._run_a2a_command"),
            patch("synapse.cli._build_a2a_cmd") as mock_build,
        ):
            cmd_spawn(args)

        assert mock_build.call_args.kwargs["response_mode"] == "silent"

    def test_cmd_spawn_without_task_unchanged(self, capsys) -> None:
        from synapse.cli import cmd_spawn
        from synapse.spawn import SpawnResult

        args = _make_args()
        result = SpawnResult(
            agent_id="synapse-claude-8100",
            port=8100,
            terminal_used="tmux",
            status="submitted",
        )
        agent_info = {"agent_id": result.agent_id, "pid": 12345}

        with (
            patch("synapse.spawn.spawn_agent", return_value=result),
            patch("synapse.spawn.wait_for_agent", return_value=agent_info) as mock_wait,
            patch("synapse.cli._run_a2a_command") as mock_run,
            patch("synapse.cli._build_a2a_cmd") as mock_build,
        ):
            cmd_spawn(args)

        mock_wait.assert_called_once_with(
            result.agent_id, timeout=3.0, poll_interval=0.5
        )
        mock_build.assert_not_called()
        mock_run.assert_not_called()
        captured = capsys.readouterr()
        assert "Warning:" not in captured.err
