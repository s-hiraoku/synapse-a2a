"""
Tests for `synapse trace <task_id>` command.

Goal: make it easy to trace "what happened" for a task id:
- show A2A task history (input/output/metadata)
- show file-safety modifications recorded under the same task_id
"""

from __future__ import annotations

import argparse
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_args() -> argparse.Namespace:
    return argparse.Namespace(task_id="task-123")


class TestCmdTrace:
    def test_trace_task_not_found_exits(self, mock_args, capsys):
        """Should exit with code 1 when task id is not in history."""
        from synapse.cli import cmd_trace

        with patch("synapse.history.HistoryManager") as mock_hm_class:
            mock_hm = MagicMock()
            mock_hm.enabled = True
            mock_hm.get_observation.return_value = None
            mock_hm_class.from_env.return_value = mock_hm

            with pytest.raises(SystemExit) as exc_info:
                cmd_trace(mock_args)

            assert exc_info.value.code == 1

        captured = capsys.readouterr()
        assert "Task not found" in captured.out

    def test_trace_includes_file_modifications(self, mock_args, capsys):
        """Should print file modifications for the same task id."""
        from synapse.cli import cmd_trace

        observation = {
            "task_id": "task-123",
            "agent_name": "codex",
            "status": "sent",
            "session_id": "session-456",
            "timestamp": "2026-02-11T00:00:00",
            "input": "hello",
            "output": "world",
            "metadata": {"k": "v"},
        }

        with (
            patch("synapse.history.HistoryManager") as mock_hm_class,
            patch("synapse.file_safety.FileSafetyManager") as mock_fm_class,
        ):
            mock_hm = MagicMock()
            mock_hm.enabled = True
            mock_hm.get_observation.return_value = observation
            mock_hm_class.from_env.return_value = mock_hm

            mock_fm = MagicMock()
            mock_fm.enabled = True
            mock_fm.get_modifications_by_task.return_value = [
                {
                    "timestamp": "2026-02-11T00:01:02",
                    "agent_name": "synapse-codex-8120",
                    "file_path": "synapse/tools/a2a.py",
                    "change_type": "MODIFY",
                    "intent": "Add --attach support",
                    "task_id": "task-123",
                }
            ]
            mock_fm_class.from_env.return_value = mock_fm

            cmd_trace(mock_args)

            mock_fm.get_modifications_by_task.assert_called_once_with("task-123")

        captured = capsys.readouterr()
        assert "Task ID:" in captured.out
        assert "task-123" in captured.out
        assert "FILE MODIFICATIONS" in captured.out
        assert "synapse/tools/a2a.py" in captured.out

    def test_trace_file_safety_disabled_still_shows_history(self, mock_args, capsys):
        """When file-safety is disabled, trace should still show history details."""
        from synapse.cli import cmd_trace

        observation = {
            "task_id": "task-123",
            "agent_name": "codex",
            "status": "sent",
            "session_id": "session-456",
            "timestamp": "2026-02-11T00:00:00",
            "input": "hello",
            "output": "world",
            "metadata": None,
        }

        with (
            patch("synapse.history.HistoryManager") as mock_hm_class,
            patch("synapse.file_safety.FileSafetyManager") as mock_fm_class,
        ):
            mock_hm = MagicMock()
            mock_hm.enabled = True
            mock_hm.get_observation.return_value = observation
            mock_hm_class.from_env.return_value = mock_hm

            mock_fm = MagicMock()
            mock_fm.enabled = False
            mock_fm_class.from_env.return_value = mock_fm

            cmd_trace(mock_args)

        captured = capsys.readouterr()
        assert "Task ID:" in captured.out
        assert "hello" in captured.out
