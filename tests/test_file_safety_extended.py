import sqlite3
from unittest.mock import patch

import pytest

from synapse.file_safety import (
    ChangeType,
    FileLockDBError,
    FileSafetyManager,
    LockStatus,
)


class TestFileSafetyExtended:
    """Extended tests for FileSafetyManager covering edge cases and error handling."""

    @pytest.fixture
    def manager(self, tmp_path):
        """Create a FileSafetyManager instance."""
        db_path = tmp_path / "safety.db"
        return FileSafetyManager(db_path=str(db_path))

    def test_get_modifications_by_task(self, manager):
        """Should retrieve modifications filtered by task_id."""
        manager.record_modification("file1.py", "claude", "task-A", ChangeType.CREATE)
        manager.record_modification("file2.py", "claude", "task-A", ChangeType.MODIFY)
        manager.record_modification("file3.py", "claude", "task-B", ChangeType.CREATE)

        mods = manager.get_modifications_by_task("task-A")

        assert len(mods) == 2
        from pathlib import Path

        filenames = {Path(m["file_path"]).name for m in mods}
        assert filenames == {"file1.py", "file2.py"}
        assert all(m["task_id"] == "task-A" for m in mods)

    def test_record_modification_invalid_change_type(self, manager, capsys, caplog):
        """Should fail gracefully when invalid change_type is provided."""
        result = manager.record_modification(
            "file.py", "claude", "task-1", "INVALID_TYPE"
        )

        assert result is None
        # Check both for backward compatibility (some might still use print)
        captured = capsys.readouterr()
        log_output = caplog.text
        assert (
            "Invalid change_type" in captured.err or "Invalid change_type" in log_output
        )

    def test_record_modification_invalid_type_object(self, manager, capsys, caplog):
        """Should fail gracefully when change_type is wrong type."""
        result = manager.record_modification(
            "file.py",
            "claude",
            "task-1",
            123,  # type: ignore
        )

        assert result is None
        captured = capsys.readouterr()
        log_output = caplog.text
        assert (
            "change_type must be ChangeType or str" in captured.err
            or "change_type must be ChangeType or str" in log_output
        )

    def test_corrupted_metadata_json(self, manager):
        """Should handle corrupted JSON in metadata column."""
        # Insert record with invalid JSON manually
        manager.record_modification("file.py", "claude", "task-1", ChangeType.CREATE)

        with sqlite3.connect(manager.db_path) as conn:
            conn.execute(
                "UPDATE file_modifications SET metadata = '{invalid-json' WHERE task_id = 'task-1'"
            )

        # Should not crash when reading
        history = manager.get_file_history("file.py")
        assert len(history) == 1
        assert history[0]["metadata"] == {}  # Fallback to empty dict

    def test_cleanup_expired_locks_public(self, manager):
        """Should expose cleanup_expired_locks public method."""
        # Create expired lock manually
        with sqlite3.connect(manager.db_path) as conn:
            conn.execute(
                """
                INSERT INTO file_locks (file_path, agent_name, expires_at)
                VALUES (?, ?, datetime('now', '-1 minute'))
                """,
                ("/tmp/expired", "claude"),
            )

        count = manager.cleanup_expired_locks()
        assert count == 1
        assert len(manager.list_locks()) == 0

    @patch("sqlite3.connect")
    def test_db_error_handling(self, mock_connect, manager, capsys, caplog):
        """Should handle database errors in various methods."""
        mock_connect.side_effect = sqlite3.Error("Simulated DB Error")

        # Test acquire_lock error
        res = manager.acquire_lock("f", "a")
        assert res["status"] == LockStatus.FAILED
        assert "Simulated DB Error" in res["error"]

        # Test release_lock error
        assert manager.release_lock("f", "a") is False

        # Test check_lock error - now raises FileLockDBError (fail-closed behavior)
        with pytest.raises(FileLockDBError):
            manager.check_lock("f")

        # Test list_locks error
        assert manager.list_locks() == []

        # Test record_modification error
        assert manager.record_modification("f", "a", "t", ChangeType.CREATE) is None

        # Test get_file_history error
        assert manager.get_file_history("f") == []

        # Test get_recent_modifications error
        assert manager.get_recent_modifications() == []

        # Test get_modifications_by_task error
        assert manager.get_modifications_by_task("t") == []

        # Test cleanup_expired_locks error
        assert manager.cleanup_expired_locks() == 0

        # Test cleanup_old_modifications error
        assert manager.cleanup_old_modifications(30) == 0

        # Test get_statistics error
        assert manager.get_statistics() == {}

        # Check stderr and logs
        captured = capsys.readouterr()
        log_output = caplog.text
        # Some are logged, some are printed
        assert (
            "Failed to acquire lock" in captured.err
            or "Failed to acquire lock" in log_output
        )
        assert (
            "Failed to release lock" in captured.err
            or "Failed to release lock" in log_output
        )
        # check_lock now logs "Database error checking lock" instead of "Failed to check lock"
        assert (
            "Database error checking lock" in captured.err
            or "Database error checking lock" in log_output
        )

    def test_cleanup_old_modifications_invalid_input(self, manager, capsys):
        """Should validate input for cleanup_old_modifications."""
        assert manager.cleanup_old_modifications(-5) == 0
        captured = capsys.readouterr()
        assert "Warning: Invalid days parameter" in captured.err

    def test_init_db_error(self, tmp_path, capsys, caplog):
        """Should handle error during DB initialization."""
        # Create a directory where the file should be to cause IsADirectoryError or similar
        # But easier to just mock sqlite3.connect

        db_path = tmp_path / "bad_db"

        with patch("sqlite3.connect", side_effect=sqlite3.Error("Init Error")):
            _ = FileSafetyManager(db_path=str(db_path))
            # Should have logged or printed error
            captured = capsys.readouterr()
            log_output = caplog.text
            assert (
                "Failed to initialize file safety DB" in captured.err
                or "Failed to initialize file safety DB" in log_output
            )
