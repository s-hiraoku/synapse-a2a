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

    @patch("synapse.registry.AgentRegistry")
    @patch("synapse.file_safety.FileSafetyManager")
    @patch("builtins.print")
    def test_cmd_file_safety_lock(self, mock_print, mock_fm, mock_registry, mock_args):
        """cmd_file_safety_lock should call acquire_lock."""
        mock_fm_inst = mock_fm.from_env.return_value
        mock_fm_inst.enabled = True
        mock_fm_inst.acquire_lock.return_value = {
            "status": LockStatus.ACQUIRED,
            "expires_at": "2026-01-09 11:00:00",
        }
        registry_instance = mock_registry.return_value
        registry_instance.get_agent.return_value = None

        cmd_file_safety_lock(mock_args)

        mock_fm_inst.acquire_lock.assert_called_once_with(
            file_path="test.py",
            agent_name="claude",
            task_id="task-1",
            duration_seconds=300,
            intent="Refactoring",
            pid=None,
        )
        printed_output = "\n".join(
            call.args[0] for call in mock_print.call_args_list if call.args
        )
        assert "Lock acquired on test.py" in printed_output

    @patch("synapse.registry.AgentRegistry")
    @patch("synapse.file_safety.FileSafetyManager")
    @patch("builtins.print")
    def test_cmd_file_safety_lock_uses_registry_pid(
        self, mock_print, mock_fm, mock_registry, mock_args
    ):
        """cmd_file_safety_lock should pass registry PID when available."""
        mock_fm_inst = mock_fm.from_env.return_value
        mock_fm_inst.enabled = True
        mock_fm_inst.acquire_lock.return_value = {
            "status": LockStatus.ACQUIRED,
            "expires_at": "2026-01-09 11:00:00",
        }

        registry_instance = mock_registry.return_value
        registry_instance.get_agent.return_value = {"pid": 4321}

        cmd_file_safety_lock(mock_args)

        mock_fm_inst.acquire_lock.assert_called_once_with(
            file_path="test.py",
            agent_name="claude",
            task_id="task-1",
            duration_seconds=300,
            intent="Refactoring",
            pid=4321,
        )

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


class TestCliFileSafetyErrorCases:
    """Tests for error cases in file-safety CLI commands."""

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

    # ===== Tests for disabled manager state =====

    @patch("synapse.file_safety.FileSafetyManager")
    @patch("builtins.print")
    def test_cmd_file_safety_status_disabled(self, mock_print, mock_fm, mock_args):
        """cmd_file_safety_status should print disabled message when manager is disabled."""
        mock_fm_inst = mock_fm.from_env.return_value
        mock_fm_inst.enabled = False

        cmd_file_safety_status(mock_args)

        mock_print.assert_called_with(
            "File safety is disabled. Enable with: SYNAPSE_FILE_SAFETY_ENABLED=true"
        )

    @patch("synapse.file_safety.FileSafetyManager")
    @patch("builtins.print")
    def test_cmd_file_safety_locks_disabled(self, mock_print, mock_fm, mock_args):
        """cmd_file_safety_locks should print disabled message when manager is disabled."""
        mock_fm_inst = mock_fm.from_env.return_value
        mock_fm_inst.enabled = False

        cmd_file_safety_locks(mock_args)

        mock_print.assert_called_with(
            "File safety is disabled. Enable with: SYNAPSE_FILE_SAFETY_ENABLED=true"
        )

    @patch("synapse.file_safety.FileSafetyManager")
    @patch("builtins.print")
    def test_cmd_file_safety_lock_disabled(self, mock_print, mock_fm, mock_args):
        """cmd_file_safety_lock should print disabled message when manager is disabled."""
        mock_fm_inst = mock_fm.from_env.return_value
        mock_fm_inst.enabled = False

        cmd_file_safety_lock(mock_args)

        mock_print.assert_called_with(
            "File safety is disabled. Enable with: SYNAPSE_FILE_SAFETY_ENABLED=true"
        )

    @patch("synapse.file_safety.FileSafetyManager")
    @patch("builtins.print")
    def test_cmd_file_safety_unlock_disabled(self, mock_print, mock_fm, mock_args):
        """cmd_file_safety_unlock should print disabled message when manager is disabled."""
        mock_fm_inst = mock_fm.from_env.return_value
        mock_fm_inst.enabled = False

        cmd_file_safety_unlock(mock_args)

        mock_print.assert_called_with(
            "File safety is disabled. Enable with: SYNAPSE_FILE_SAFETY_ENABLED=true"
        )

    @patch("synapse.file_safety.FileSafetyManager")
    @patch("builtins.print")
    def test_cmd_file_safety_history_disabled(self, mock_print, mock_fm, mock_args):
        """cmd_file_safety_history should print disabled message when manager is disabled."""
        mock_fm_inst = mock_fm.from_env.return_value
        mock_fm_inst.enabled = False

        cmd_file_safety_history(mock_args)

        mock_print.assert_called_with(
            "File safety is disabled. Enable with: SYNAPSE_FILE_SAFETY_ENABLED=true"
        )

    @patch("synapse.file_safety.FileSafetyManager")
    @patch("builtins.print")
    def test_cmd_file_safety_recent_disabled(self, mock_print, mock_fm, mock_args):
        """cmd_file_safety_recent should print disabled message when manager is disabled."""
        mock_fm_inst = mock_fm.from_env.return_value
        mock_fm_inst.enabled = False

        cmd_file_safety_recent(mock_args)

        mock_print.assert_called_with(
            "File safety is disabled. Enable with: SYNAPSE_FILE_SAFETY_ENABLED=true"
        )

    @patch("synapse.file_safety.FileSafetyManager")
    @patch("builtins.print")
    def test_cmd_file_safety_cleanup_disabled(self, mock_print, mock_fm, mock_args):
        """cmd_file_safety_cleanup should print disabled message when manager is disabled."""
        mock_fm_inst = mock_fm.from_env.return_value
        mock_fm_inst.enabled = False

        cmd_file_safety_cleanup(mock_args)

        mock_print.assert_called_with(
            "File safety is disabled. Enable with: SYNAPSE_FILE_SAFETY_ENABLED=true"
        )

    # ===== Tests for ALREADY_LOCKED status =====

    @patch("synapse.file_safety.FileSafetyManager")
    @patch("builtins.print")
    def test_cmd_file_safety_lock_already_locked(self, mock_print, mock_fm, mock_args):
        """cmd_file_safety_lock should exit with 1 when file is already locked."""
        mock_fm_inst = mock_fm.from_env.return_value
        mock_fm_inst.enabled = True
        mock_fm_inst.acquire_lock.return_value = {
            "status": LockStatus.ALREADY_LOCKED,
            "lock_holder": "gemini",
            "expires_at": "2026-01-09 12:00:00",
        }

        with pytest.raises(SystemExit) as exc_info:
            cmd_file_safety_lock(mock_args)

        assert exc_info.value.code == 1
        printed_output = "\n".join(
            call.args[0] for call in mock_print.call_args_list if call.args
        )
        assert "File is already locked by gemini" in printed_output

    # ===== Tests for FAILED status =====

    @patch("synapse.file_safety.FileSafetyManager")
    @patch("builtins.print")
    def test_cmd_file_safety_lock_failed(self, mock_print, mock_fm, mock_args):
        """cmd_file_safety_lock should exit with 1 when lock acquisition fails."""
        mock_fm_inst = mock_fm.from_env.return_value
        mock_fm_inst.enabled = True
        mock_fm_inst.acquire_lock.return_value = {
            "status": LockStatus.FAILED,
            "error": "database is locked",
        }

        with pytest.raises(SystemExit) as exc_info:
            cmd_file_safety_lock(mock_args)

        assert exc_info.value.code == 1
        printed_output = "\n".join(
            call.args[0] for call in mock_print.call_args_list if call.args
        )
        assert "Failed to acquire lock" in printed_output
        assert "database is locked" in printed_output

    # ===== Tests for unlock failure =====

    @patch("synapse.file_safety.FileSafetyManager")
    @patch("builtins.print")
    def test_cmd_file_safety_unlock_failure(self, mock_print, mock_fm, mock_args):
        """cmd_file_safety_unlock should exit with 1 when lock release fails."""
        mock_fm_inst = mock_fm.from_env.return_value
        mock_fm_inst.enabled = True
        mock_fm_inst.release_lock.return_value = False

        with pytest.raises(SystemExit) as exc_info:
            cmd_file_safety_unlock(mock_args)

        assert exc_info.value.code == 1
        printed_output = "\n".join(
            call.args[0] for call in mock_print.call_args_list if call.args
        )
        assert "No lock found for test.py by claude" in printed_output

    # ===== Tests for empty data =====

    @patch("synapse.file_safety.FileSafetyManager")
    @patch("builtins.print")
    def test_cmd_file_safety_status_no_data(self, mock_print, mock_fm, mock_args):
        """cmd_file_safety_status should handle empty statistics."""
        mock_fm_inst = mock_fm.from_env.return_value
        mock_fm_inst.enabled = True
        mock_fm_inst.get_statistics.return_value = {}

        cmd_file_safety_status(mock_args)

        mock_print.assert_called_with("No file safety data found.")

    @patch("synapse.file_safety.FileSafetyManager")
    @patch("builtins.print")
    def test_cmd_file_safety_locks_no_locks(self, mock_print, mock_fm, mock_args):
        """cmd_file_safety_locks should handle no active locks."""
        mock_fm_inst = mock_fm.from_env.return_value
        mock_fm_inst.enabled = True
        mock_fm_inst.list_locks.return_value = []

        cmd_file_safety_locks(mock_args)

        mock_print.assert_called_with("No active file locks.")

    @patch("synapse.file_safety.FileSafetyManager")
    @patch("builtins.print")
    def test_cmd_file_safety_history_no_history(self, mock_print, mock_fm, mock_args):
        """cmd_file_safety_history should handle no history."""
        mock_fm_inst = mock_fm.from_env.return_value
        mock_fm_inst.enabled = True
        mock_fm_inst.get_file_history.return_value = []

        cmd_file_safety_history(mock_args)

        mock_print.assert_called_with("No modification history found for test.py")

    @patch("synapse.file_safety.FileSafetyManager")
    @patch("builtins.print")
    def test_cmd_file_safety_recent_no_mods(self, mock_print, mock_fm, mock_args):
        """cmd_file_safety_recent should handle no recent modifications."""
        mock_fm_inst = mock_fm.from_env.return_value
        mock_fm_inst.enabled = True
        mock_fm_inst.get_recent_modifications.return_value = []

        cmd_file_safety_recent(mock_args)

        mock_print.assert_called_with("No recent modifications found.")
