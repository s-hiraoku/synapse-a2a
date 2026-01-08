import sqlite3
import tempfile
from pathlib import Path

import pytest

from synapse.file_safety import ChangeType, FileSafetyManager, LockStatus


class TestFileSafetyManager:
    """Test FileSafetyManager for file locking and modification tracking."""

    @pytest.fixture
    def temp_db_path(self):
        """Create a temporary database path for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "file_safety.db"
            yield str(db_path)

    @pytest.fixture
    def manager(self, temp_db_path):
        """Create a FileSafetyManager instance for testing."""
        return FileSafetyManager(db_path=temp_db_path)

    def test_init_creates_database(self, temp_db_path):
        """Should create database file on initialization."""
        assert not Path(temp_db_path).exists()
        FileSafetyManager(db_path=temp_db_path)
        assert Path(temp_db_path).exists()

    def test_init_creates_tables(self, temp_db_path):
        """Should create required tables with correct schema."""
        FileSafetyManager(db_path=temp_db_path)

        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()

        # Check file_locks table
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='file_locks'"
        )
        assert cursor.fetchone() is not None

        # Check file_modifications table
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='file_modifications'"
        )
        assert cursor.fetchone() is not None

        conn.close()

    def test_acquire_lock_success(self, manager):
        """Should successfully acquire a lock on a file."""
        result = manager.acquire_lock(
            file_path="test.py",
            agent_name="claude",
            task_id="task-1",
            intent="Refactoring",
        )

        assert result["status"] == LockStatus.ACQUIRED
        assert "expires_at" in result

        # Verify in DB
        locks = manager.list_locks()
        assert len(locks) == 1
        assert locks[0]["file_path"].endswith("test.py")
        assert locks[0]["agent_name"] == "claude"

    def test_acquire_lock_already_locked(self, manager):
        """Should fail to acquire lock if already locked by another agent."""
        manager.acquire_lock("test.py", "claude")

        result = manager.acquire_lock("test.py", "gemini")

        assert result["status"] == LockStatus.ALREADY_LOCKED
        assert result["lock_holder"] == "claude"

    def test_acquire_lock_renew(self, manager):
        """Should renew lock if requested by the same agent."""
        manager.acquire_lock("test.py", "claude")

        result = manager.acquire_lock("test.py", "claude")

        assert result["status"] == LockStatus.RENEWED

    def test_release_lock_success(self, manager):
        """Should successfully release a lock."""
        manager.acquire_lock("test.py", "claude")
        assert len(manager.list_locks()) == 1

        success = manager.release_lock("test.py", "claude")

        assert success is True
        assert len(manager.list_locks()) == 0

    def test_release_lock_not_held(self, manager):
        """Should fail to release lock if not held by the agent."""
        manager.acquire_lock("test.py", "claude")

        success = manager.release_lock("test.py", "gemini")

        assert success is False
        assert len(manager.list_locks()) == 1

    def test_record_modification(self, manager):
        """Should record file modification."""
        manager.record_modification(
            file_path="test.py",
            agent_name="claude",
            task_id="task-1",
            change_type=ChangeType.MODIFY,
            intent="Fix bug",
            affected_lines="10-15",
        )

        history = manager.get_file_history("test.py")
        assert len(history) == 1
        assert history[0]["file_path"].endswith("test.py")
        assert history[0]["agent_name"] == "claude"
        assert history[0]["change_type"] == "MODIFY"
        assert history[0]["intent"] == "Fix bug"

    def test_get_statistics(self, manager):
        """Should calculate statistics correctly."""
        manager.acquire_lock("file1.py", "claude")
        manager.record_modification("file1.py", "claude", "task-1", ChangeType.CREATE)
        manager.record_modification("file1.py", "claude", "task-2", ChangeType.MODIFY)
        manager.record_modification("file2.py", "gemini", "task-3", ChangeType.MODIFY)

        stats = manager.get_statistics()

        assert stats["active_locks"] == 1
        assert stats["total_modifications"] == 3
        assert stats["by_agent"]["claude"] == 2
        assert stats["by_agent"]["gemini"] == 1
        assert stats["by_change_type"]["MODIFY"] == 2
        assert stats["by_change_type"]["CREATE"] == 1

    def test_cleanup_old_modifications(self, manager, temp_db_path):
        """Should delete records older than N days."""
        # Manually insert an old record
        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO file_modifications 
               (file_path, agent_name, change_type, task_id, timestamp) 
               VALUES (?, ?, ?, ?, datetime('now', '-40 days'))""",
            ("old.py", "claude", "MODIFY", "old-task"),
        )
        conn.commit()
        conn.close()

        assert manager.get_statistics()["total_modifications"] == 1

        deleted = manager.cleanup_old_modifications(days=30)
        assert deleted == 1
        assert manager.get_statistics()["total_modifications"] == 0

    def test_disabled_manager(self, temp_db_path):
        """Should return ACQUIRED with no expiration if disabled."""
        manager = FileSafetyManager(db_path=temp_db_path, enabled=False)

        result = manager.acquire_lock("test.py", "claude")
        assert result["status"] == LockStatus.ACQUIRED
        assert result["expires_at"] is None

        # Should not create database file
        assert not Path(temp_db_path).exists()
