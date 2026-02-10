"""Tests for B1: Shared Task Board - CLI commands.

Test-first development: tests for `synapse tasks` subcommands.
"""

from __future__ import annotations

from unittest.mock import patch


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
