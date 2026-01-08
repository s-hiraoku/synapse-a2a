import argparse
from unittest.mock import MagicMock, patch

import pytest

from synapse.cli import (
    cmd_file_safety_cleanup,
    cmd_file_safety_history,
    cmd_file_safety_lock,
    cmd_file_safety_locks,
    cmd_file_safety_recent,
    cmd_file_safety_status,
    cmd_file_safety_unlock,
)
from synapse.file_safety import LockStatus


class TestCliFileSafetyCommands:
    """Tests for file-safety CLI commands."""

    @pytest.fixture
    def mock_args(self):
        """Create a mock args object."""
        args = MagicMock(spec=argparse.Namespace)
        args.file = "test.py"
        args.agent = "claude"
        args.limit = 50
        args.task_id = "task-1"
        args.duration = 300
        args.intent = "Refactoring"
        args.force = False
        args.days = 30
        return args

    @patch("synapse.file_safety.FileSafetyManager")
    @patch("builtins.print")
    def test_cmd_file_safety_status(self, mock_print, mock_fm, mock_args):
        """cmd_file_safety_status should call get_statistics and print results."""
        mock_fm_inst = mock_fm.from_env.return_value
        mock_fm_inst.enabled = True
        mock_fm_inst.get_statistics.return_value = {
            "active_locks": 1,
            "total_modifications": 5,
            "by_change_type": {"MODIFY": 3},
            "by_agent": {"claude": 5},
            "most_modified_files": [{"file_path": "test.py", "count": 5}],
        }

        cmd_file_safety_status(mock_args)

        mock_fm_inst.get_statistics.assert_called_once()
        printed_output = "\n".join(
            call.args[0] for call in mock_print.call_args_list if call.args
        )
        assert "FILE SAFETY STATISTICS" in printed_output
        assert "Active Locks:        1" in printed_output

    @patch("synapse.file_safety.FileSafetyManager")
    @patch("builtins.print")
    def test_cmd_file_safety_locks(self, mock_print, mock_fm, mock_args):
        """cmd_history_locks should call list_locks."""
        mock_fm_inst = mock_fm.from_env.return_value
        mock_fm_inst.enabled = True
        mock_fm_inst.list_locks.return_value = [
            {
                "file_path": "test.py",
                "agent_name": "claude",
                "expires_at": "2026-01-09 11:00:00",
            }
        ]

        cmd_file_safety_locks(mock_args)

        mock_fm_inst.list_locks.assert_called_once()
        printed_output = "\n".join(
            call.args[0] for call in mock_print.call_args_list if call.args
        )
        assert "test.py" in printed_output
        assert "claude" in printed_output

    @patch("synapse.file_safety.FileSafetyManager")
    @patch("builtins.print")
    def test_cmd_file_safety_lock(self, mock_print, mock_fm, mock_args):
        """cmd_file_safety_lock should call acquire_lock."""
        mock_fm_inst = mock_fm.from_env.return_value
        mock_fm_inst.enabled = True
        mock_fm_inst.acquire_lock.return_value = {
            "status": LockStatus.ACQUIRED,
            "expires_at": "2026-01-09 11:00:00",
        }

        cmd_file_safety_lock(mock_args)

        mock_fm_inst.acquire_lock.assert_called_once_with(
            file_path="test.py",
            agent_name="claude",
            task_id="task-1",
            duration_seconds=300,
            intent="Refactoring",
        )
        printed_output = "\n".join(
            call.args[0] for call in mock_print.call_args_list if call.args
        )
        assert "Lock acquired on test.py" in printed_output

    @patch("synapse.file_safety.FileSafetyManager")
    @patch("builtins.print")
    def test_cmd_file_safety_unlock(self, mock_print, mock_fm, mock_args):
        """cmd_file_safety_unlock should call release_lock."""
        mock_fm_inst = mock_fm.from_env.return_value
        mock_fm_inst.enabled = True
        mock_fm_inst.release_lock.return_value = True

        cmd_file_safety_unlock(mock_args)

        mock_fm_inst.release_lock.assert_called_once_with("test.py", "claude")
        printed_output = "\n".join(
            call.args[0] for call in mock_print.call_args_list if call.args
        )
        assert "Lock released on test.py" in printed_output

    @patch("synapse.file_safety.FileSafetyManager")
    @patch("builtins.print")
    def test_cmd_file_safety_history(self, mock_print, mock_fm, mock_args):
        """cmd_file_safety_history should call get_file_history."""
        mock_fm_inst = mock_fm.from_env.return_value
        mock_fm_inst.enabled = True
        mock_fm_inst.get_file_history.return_value = [
            {
                "timestamp": "2026-01-09 10:00:00",
                "agent_name": "claude",
                "change_type": "MODIFY",
                "task_id": "t1",
            }
        ]

        cmd_file_safety_history(mock_args)

        mock_fm_inst.get_file_history.assert_called_once_with("test.py", limit=50)
        printed_output = "\n".join(
            call.args[0] for call in mock_print.call_args_list if call.args
        )
        assert "Modification history for: test.py" in printed_output

    @patch("synapse.file_safety.FileSafetyManager")
    @patch("builtins.print")
    def test_cmd_file_safety_recent(self, mock_print, mock_fm, mock_args):
        """cmd_file_safety_recent should call get_recent_modifications."""
        mock_fm_inst = mock_fm.from_env.return_value
        mock_fm_inst.enabled = True
        mock_fm_inst.get_recent_modifications.return_value = [
            {
                "timestamp": "2026-01-09 10:00:00",
                "agent_name": "claude",
                "change_type": "MODIFY",
                "file_path": "test.py",
            }
        ]

        cmd_file_safety_recent(mock_args)

        mock_fm_inst.get_recent_modifications.assert_called_once_with(
            limit=50, agent_name="claude"
        )
        printed_output = "\n".join(
            call.args[0] for call in mock_print.call_args_list if call.args
        )
        assert "test.py" in printed_output

    @patch("synapse.file_safety.FileSafetyManager")
    @patch("builtins.print")
    def test_cmd_file_safety_cleanup(self, mock_print, mock_fm, mock_args):
        """cmd_file_safety_cleanup should call cleanup_old_modifications."""
        mock_args.force = True
        mock_fm_inst = mock_fm.from_env.return_value
        mock_fm_inst.enabled = True
        mock_fm_inst.cleanup_old_modifications.return_value = 10
        mock_fm_inst.cleanup_expired_locks.return_value = 5

        cmd_file_safety_cleanup(mock_args)

        mock_fm_inst.cleanup_old_modifications.assert_called_once_with(days=30)
        mock_fm_inst.cleanup_expired_locks.assert_called_once()
        printed_output = "\n".join(
            call.args[0] for call in mock_print.call_args_list if call.args
        )
        assert "Deleted 10 modification records older than 30 days" in printed_output
        assert "Cleaned up 5 expired locks" in printed_output
