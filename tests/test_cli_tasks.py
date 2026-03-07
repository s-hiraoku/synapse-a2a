"""Tests for B1: Shared Task Board - CLI commands.

Test-first development: tests for `synapse tasks` subcommands.
"""

from __future__ import annotations

import argparse
from unittest.mock import patch

import pytest


class TestTasksCLI:
    """Tests for synapse tasks subcommands."""

    def test_tasks_list_command(self, tmp_path):
        """synapse tasks list should list tasks."""
        from synapse.task_board import TaskBoard

        board = TaskBoard(db_path=str(tmp_path / "board.db"))
        board.create_task(
            subject="Test task",
            description="Test",
            created_by="claude",
        )

        with patch("synapse.task_board.TaskBoard.from_env", return_value=board):
            import argparse

            from synapse.cli import cmd_tasks_list

            args = argparse.Namespace(status=None, agent=None)
            cmd_tasks_list(args)

    def test_tasks_create_command(self, tmp_path):
        """synapse tasks create should create a task."""
        from synapse.task_board import TaskBoard

        board = TaskBoard(db_path=str(tmp_path / "board.db"))

        with patch("synapse.task_board.TaskBoard.from_env", return_value=board):
            import argparse

            from synapse.cli import cmd_tasks_create

            args = argparse.Namespace(
                subject="New task",
                description="Test description",
                blocked_by=None,
            )
            cmd_tasks_create(args)

        tasks = board.list_tasks()
        assert len(tasks) == 1
        assert tasks[0]["subject"] == "New task"

    def test_tasks_assign_accepts_unique_short_id(self, tmp_path, capsys):
        """synapse tasks assign should accept a unique task ID prefix."""
        from synapse.task_board import TaskBoard

        board = TaskBoard(db_path=str(tmp_path / "board.db"))
        task_id = board.create_task(
            subject="Short id task",
            description="Test",
            created_by="claude",
        )

        with patch("synapse.task_board.TaskBoard.from_env", return_value=board):
            from synapse.cli import cmd_tasks_assign

            args = argparse.Namespace(task_id=task_id[:8], agent="gemini")
            cmd_tasks_assign(args)

        out = capsys.readouterr().out
        assert f"Assigned {task_id[:8]} to gemini" in out

    def test_tasks_assign_rejects_unknown_short_id(self, tmp_path, capsys):
        """synapse tasks assign should fail for an unknown task ID prefix."""
        from synapse.task_board import TaskBoard

        board = TaskBoard(db_path=str(tmp_path / "board.db"))
        board.create_task(
            subject="Known task",
            description="Test",
            created_by="claude",
        )

        with patch("synapse.task_board.TaskBoard.from_env", return_value=board):
            from synapse.cli import cmd_tasks_assign

            args = argparse.Namespace(task_id="deadbeef", agent="gemini")
            with pytest.raises(SystemExit) as exc:
                cmd_tasks_assign(args)

        err = capsys.readouterr().err
        assert exc.value.code == 1
        assert "No task found starting with 'deadbeef'" in err

    def test_tasks_assign_rejects_ambiguous_short_id(self, tmp_path, capsys):
        """synapse tasks assign should fail for an ambiguous task ID prefix."""
        with patch("synapse.task_board.TaskBoard.from_env") as from_env:
            board = from_env.return_value
            board.find_tasks_by_prefix.return_value = [
                {"id": "abc12345-0000-0000-0000-000000000001"},
                {"id": "abc12345-0000-0000-0000-000000000002"},
            ]

            from synapse.cli import cmd_tasks_assign

            args = argparse.Namespace(task_id="abc12345", agent="gemini")
            with pytest.raises(SystemExit) as exc:
                cmd_tasks_assign(args)

        err = capsys.readouterr().err
        assert exc.value.code == 1
        assert "Multiple tasks found starting with 'abc12345'" in err
