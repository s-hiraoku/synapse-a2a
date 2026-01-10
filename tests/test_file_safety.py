import json
import os
import sqlite3
import tempfile
from pathlib import Path

import pytest

from synapse.file_safety import (
    ChangeType,
    FileLockDBError,
    FileSafetyManager,
    LockStatus,
)


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

    def test_check_lock(self, manager):
        """Should return lock info if file is locked."""
        manager.acquire_lock("test.py", "claude", task_id="task-1", intent="Test")

        lock_info = manager.check_lock("test.py")
        assert lock_info is not None
        assert lock_info["agent_name"] == "claude"
        assert lock_info["task_id"] == "task-1"
        assert lock_info["intent"] == "Test"

    def test_check_lock_not_locked(self, manager):
        """Should return None if file is not locked."""
        assert manager.check_lock("test.py") is None

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

    def test_get_recent_modifications(self, manager):
        """Should return recent modifications across all files."""
        manager.record_modification("file1.py", "claude", "t1", ChangeType.CREATE)
        manager.record_modification("file2.py", "gemini", "t2", ChangeType.MODIFY)

        recent = manager.get_recent_modifications(limit=10)
        assert len(recent) == 2
        # Should be ordered by timestamp DESC (newest first)
        assert recent[0]["file_path"].endswith("file2.py")
        assert recent[1]["file_path"].endswith("file1.py")

    def test_validate_write_allowed(self, manager):
        """Should allow write if not locked by others."""
        # Case 1: Not locked
        result = manager.validate_write("test.py", "claude")
        assert result["allowed"] is True

        # Case 2: Locked by self
        manager.acquire_lock("test.py", "claude")
        result = manager.validate_write("test.py", "claude")
        assert result["allowed"] is True

    def test_validate_write_denied(self, manager):
        """Should deny write if locked by another agent."""
        manager.acquire_lock("test.py", "gemini", intent="Refactoring")

        result = manager.validate_write("test.py", "claude")
        assert result["allowed"] is False
        assert "locked by gemini" in result["reason"]
        assert "Refactoring" in result["reason"]

    def test_get_statistics(self, manager):
        """Should calculate statistics correctly."""
        manager.acquire_lock("file1.py", "claude")
        manager.record_modification("file1.py", "claude", "task-1", ChangeType.CREATE)
        manager.record_modification("file1.py", "claude", "task-2", ChangeType.MODIFY)
        manager.record_modification("file2.py", "gemini", "task-3", ChangeType.MODIFY)

        stats = manager.get_statistics()

        assert stats["active_locks"] == 1
        assert stats["total_modifications"] == 3
        # by_change_type uses string keys (from SQLite), not ChangeType enum
        assert stats["by_change_type"]["MODIFY"] == 2
        assert stats["by_change_type"]["CREATE"] == 1
        assert stats["by_agent"]["claude"] == 2

    def test_get_file_context(self, manager):
        """Should return formatted context for a file."""
        # 1. Empty context
        assert manager.get_file_context("nonexistent.py") == ""

        # 2. Context with lock only
        manager.acquire_lock("locked.py", "gemini", intent="Testing")
        context = manager.get_file_context("locked.py")
        assert "[FILE CONTEXT - Recent Modifications]" in context
        assert "LOCKED by gemini" in context
        assert "Intent: Testing" in context

        # 3. Context with modifications
        manager.record_modification(
            "mod.py", "claude", "task-1", ChangeType.CREATE, intent="Initial"
        )
        manager.record_modification(
            "mod.py", "gemini", "task-2", ChangeType.MODIFY, intent="Update"
        )
        context = manager.get_file_context("mod.py")
        assert "[FILE CONTEXT - Recent Modifications]" in context
        assert "claude [CREATE] - Initial" in context
        assert "gemini [MODIFY] - Update" in context

    def test_get_modifications_by_task(self, manager):
        """Should filter modifications by task ID."""
        manager.record_modification("f1.py", "a1", "task-x", ChangeType.CREATE)
        manager.record_modification("f2.py", "a1", "task-y", ChangeType.CREATE)
        manager.record_modification("f3.py", "a1", "task-x", ChangeType.MODIFY)

        mods = manager.get_modifications_by_task("task-x")
        assert len(mods) == 2
        assert mods[0]["file_path"].endswith("f1.py")
        assert mods[1]["file_path"].endswith("f3.py")

    def test_record_modification_invalid_type(self, manager):
        """Should return None for invalid change type."""
        assert manager.record_modification("f.py", "a", "t", "INVALID") is None
        assert manager.record_modification("f.py", "a", "t", 123) is None

    def test_cleanup_old_modifications_invalid_days(self, manager):
        """Should handle invalid days parameter."""
        assert manager.cleanup_old_modifications(days=0) == 0
        assert manager.cleanup_old_modifications(days=-1) == 0
        assert manager.cleanup_old_modifications(days="7") == 0

    def test_is_locked_by_other(self, manager):
        """Should correctly detect if locked by someone else."""
        file = "test.py"
        assert manager.is_locked_by_other(file, "me") is False

        manager.acquire_lock(file, "other")
        assert manager.is_locked_by_other(file, "me") is True
        assert manager.is_locked_by_other(file, "other") is False

    def test_list_locks_filtered(self, manager):
        """Should filter locks by agent name."""
        manager.acquire_lock("f1.py", "agent1")
        manager.acquire_lock("f2.py", "agent2")

        locks1 = manager.list_locks(agent_name="agent1")
        assert len(locks1) == 1
        assert locks1[0]["agent_name"] == "agent1"

        locks2 = manager.list_locks(agent_name="agent2")
        assert len(locks2) == 1
        assert locks2[0]["agent_name"] == "agent2"

    def test_get_file_history(self, manager, temp_db_path):
        """Should retrieve modification history for a file."""
        file = "history_test.py"
        # Manually insert with different timestamps to ensure order
        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO file_modifications (file_path, agent_name, change_type, task_id, timestamp) VALUES (?, ?, ?, ?, ?)",
            (
                manager._normalize_path(file),
                "a1",
                "CREATE",
                "t1",
                "2026-01-01 10:00:00",
            ),
        )
        cursor.execute(
            "INSERT INTO file_modifications (file_path, agent_name, change_type, task_id, timestamp) VALUES (?, ?, ?, ?, ?)",
            (
                manager._normalize_path(file),
                "a2",
                "MODIFY",
                "t2",
                "2026-01-01 11:00:00",
            ),
        )
        conn.commit()
        conn.close()

        history = manager.get_file_history(file)
        assert len(history) == 2
        assert history[0]["change_type"] == "MODIFY"  # Newest first
        assert history[1]["change_type"] == "CREATE"

    def test_path_normalization(self, manager):
        """Should normalize paths consistently."""
        path1 = "./test.py"
        abs_path1 = os.path.abspath(os.path.expanduser(path1))

        manager.acquire_lock(path1, "agent1")
        lock = manager.check_lock(abs_path1)
        assert lock is not None
        assert lock["file_path"] == abs_path1

    def test_init_db_directory_creation(self, tmp_path):
        """Should create parent directory for DB if it doesn't exist."""
        db_path = tmp_path / "subdir" / "nested" / "file_safety.db"
        assert not db_path.parent.exists()

        FileSafetyManager(db_path=str(db_path))
        assert db_path.parent.exists()
        assert db_path.exists()

    def test_record_modification_non_serializable_metadata(self, manager):
        """Should handle non-serializable metadata gracefully."""
        # Sets are not JSON serializable by default
        metadata = {"key": {1, 2, 3}}
        res = manager.record_modification(
            "test.py", "agent", "task", ChangeType.MODIFY, metadata=metadata
        )
        assert res is not None

        history = manager.get_file_history("test.py")
        assert (
            history[0]["metadata"] == {}
        )  # Should fallback to empty if serialization failed

    def test_get_file_context_disabled(self, temp_db_path):
        """Should return empty string if manager is disabled."""
        manager = FileSafetyManager(db_path=temp_db_path, enabled=False)
        assert manager.get_file_context("test.py") == ""

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

    def test_retention_days_setting(self, temp_db_path):
        """Should use custom retention days."""
        manager = FileSafetyManager(db_path=temp_db_path, retention_days=7)
        assert manager.retention_days == 7

    def test_default_retention_days(self, temp_db_path):
        """Should use default retention days when not specified."""
        manager = FileSafetyManager(db_path=temp_db_path)
        assert manager.retention_days == 30  # DEFAULT_RETENTION_DAYS

    def test_auto_cleanup_on_init(self, temp_db_path):
        """Should auto-cleanup old records on initialization."""
        # First, create manager and add old record
        manager1 = FileSafetyManager(db_path=temp_db_path)
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

        assert manager1.get_statistics()["total_modifications"] == 1

        # Create new manager with short retention - should auto-cleanup
        manager2 = FileSafetyManager(db_path=temp_db_path, retention_days=30)
        assert manager2.get_statistics()["total_modifications"] == 0


class TestFileSafetyFromEnv:
    """Test FileSafetyManager.from_env() method."""

    @pytest.fixture(autouse=True)
    def clear_env(self, monkeypatch):
        """Clear file safety environment variables for each test."""
        for var in [
            "SYNAPSE_FILE_SAFETY_ENABLED",
            "SYNAPSE_FILE_SAFETY_DB_PATH",
            "SYNAPSE_FILE_SAFETY_RETENTION_DAYS",
        ]:
            monkeypatch.delenv(var, raising=False)

    @pytest.fixture
    def temp_db_path(self):
        """Create a temporary database path for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "file_safety.db"
            yield str(db_path)

    def test_from_env_enabled(self, temp_db_path, monkeypatch):
        """Should create enabled manager when env var is true."""
        monkeypatch.setenv("SYNAPSE_FILE_SAFETY_ENABLED", "true")
        manager = FileSafetyManager.from_env(db_path=temp_db_path)
        assert manager.enabled is True

    def test_from_env_disabled(self, temp_db_path, monkeypatch):
        """Should create disabled manager when env var is false."""
        monkeypatch.setenv("SYNAPSE_FILE_SAFETY_ENABLED", "false")
        manager = FileSafetyManager.from_env(db_path=temp_db_path)
        assert manager.enabled is False

    def test_from_env_retention_days(self, temp_db_path, monkeypatch):
        """Should use retention days from env var."""
        monkeypatch.setenv("SYNAPSE_FILE_SAFETY_ENABLED", "true")
        monkeypatch.setenv("SYNAPSE_FILE_SAFETY_RETENTION_DAYS", "14")
        manager = FileSafetyManager.from_env(db_path=temp_db_path)
        assert manager.retention_days == 14

    def test_from_env_invalid_retention_days(self, temp_db_path, monkeypatch):
        """Should use default when retention days is invalid."""
        monkeypatch.setenv("SYNAPSE_FILE_SAFETY_ENABLED", "true")
        monkeypatch.setenv("SYNAPSE_FILE_SAFETY_RETENTION_DAYS", "invalid")
        manager = FileSafetyManager.from_env(db_path=temp_db_path)
        assert manager.retention_days == 30  # DEFAULT

    def test_from_env_db_path_env_overrides_settings_and_arg(
        self, temp_db_path, tmp_path, monkeypatch
    ):
        """Env db path should override settings.json and explicit arg."""
        synapse_dir = tmp_path / ".synapse"
        synapse_dir.mkdir()
        settings_path = synapse_dir / "settings.json"
        settings_path.write_text(
            json.dumps(
                {"env": {"SYNAPSE_FILE_SAFETY_DB_PATH": str(tmp_path / "settings.db")}}
            )
        )
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("SYNAPSE_FILE_SAFETY_DB_PATH", str(tmp_path / "env.db"))

        manager = FileSafetyManager.from_env(db_path=temp_db_path)
        assert manager.db_path == str(tmp_path / "env.db")

    def test_from_env_db_path_settings_used_when_env_missing(
        self, temp_db_path, tmp_path, monkeypatch
    ):
        """Settings db path should be used when env is not set."""
        synapse_dir = tmp_path / ".synapse"
        synapse_dir.mkdir()
        settings_path = synapse_dir / "settings.json"
        settings_path.write_text(
            json.dumps(
                {"env": {"SYNAPSE_FILE_SAFETY_DB_PATH": str(tmp_path / "settings.db")}}
            )
        )
        monkeypatch.chdir(tmp_path)

        manager = FileSafetyManager.from_env(db_path=temp_db_path)
        assert manager.db_path == str(tmp_path / "settings.db")

    def test_from_env_db_path_falls_back_to_arg(
        self, temp_db_path, tmp_path, monkeypatch
    ):
        """Should fall back to explicit arg when no env/settings."""
        monkeypatch.chdir(tmp_path)
        manager = FileSafetyManager.from_env(db_path=temp_db_path)
        assert manager.db_path == temp_db_path

    def test_from_env_malformed_settings(self, temp_db_path, tmp_path, monkeypatch):
        """Should handle malformed settings.json gracefully."""
        synapse_dir = tmp_path / ".synapse"
        synapse_dir.mkdir()
        settings_path = synapse_dir / "settings.json"
        settings_path.write_text("invalid json {")
        monkeypatch.chdir(tmp_path)

        # Should not crash, just use default
        manager = FileSafetyManager.from_env(db_path=temp_db_path)
        assert manager.db_path == temp_db_path

    def test_get_setting_no_env_key(self, tmp_path, monkeypatch):
        """Should return default if env key is missing in settings.json."""
        synapse_dir = tmp_path / ".synapse"
        synapse_dir.mkdir()
        settings_path = synapse_dir / "settings.json"
        settings_path.write_text(json.dumps({"other": {}}))
        monkeypatch.chdir(tmp_path)

        assert FileSafetyManager._get_setting("KEY", "default") == "default"

    def test_auto_cleanup_disabled(self, temp_db_path):
        """Should skip auto-cleanup if retention_days is <= 0."""
        # This is hard to "assert" without mocking internal calls,
        # but we can ensure it doesn't crash.
        manager = FileSafetyManager(db_path=temp_db_path, retention_days=0)
        assert manager.retention_days == 0

    def test_timestamp_migration_legacy_to_iso8601(self, temp_db_path):
        """Should migrate legacy CURRENT_TIMESTAMP format to ISO-8601."""
        # Create a database with both tables (file_locks required for init)
        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()
        # Create file_locks table (required by FileSafetyManager)
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS file_locks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT NOT NULL UNIQUE,
                agent_name TEXT NOT NULL,
                task_id TEXT,
                locked_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                expires_at DATETIME NOT NULL,
                intent TEXT
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS file_modifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                agent_name TEXT NOT NULL,
                file_path TEXT NOT NULL,
                change_type TEXT NOT NULL,
                affected_lines TEXT,
                intent TEXT,
                timestamp TEXT NOT NULL,
                metadata TEXT
            )
            """
        )
        # Insert legacy format timestamps (SQLite CURRENT_TIMESTAMP style)
        # Use recent dates to avoid auto-cleanup (which deletes records > 30 days old)
        from datetime import datetime, timedelta

        recent_ts1 = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
        recent_ts2 = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute(
            """
            INSERT INTO file_modifications
            (task_id, agent_name, file_path, change_type, timestamp)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("task-1", "agent-1", "/path/file.py", "MODIFY", recent_ts1),
        )
        cursor.execute(
            """
            INSERT INTO file_modifications
            (task_id, agent_name, file_path, change_type, timestamp)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("task-2", "agent-2", "/path/file2.py", "CREATE", recent_ts2),
        )
        conn.commit()
        conn.close()

        # Now initialize FileSafetyManager which should trigger migration
        FileSafetyManager(db_path=temp_db_path)

        # Verify timestamps were migrated to ISO-8601
        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT timestamp FROM file_modifications ORDER BY id")
        rows = cursor.fetchall()
        conn.close()

        assert len(rows) == 2
        # Should now be in ISO-8601 format with T and timezone
        # Legacy '2024-01-15 10:30:45' becomes '2024-01-15T10:30:45+00:00'
        assert "T" in rows[0][0] and "+00:00" in rows[0][0]
        assert "T" in rows[1][0] and "+00:00" in rows[1][0]
        # Verify they don't have space separator anymore
        assert " " not in rows[0][0].split("T")[0]  # date part has no spaces
        assert " " not in rows[1][0].split("T")[0]

    def test_timestamp_migration_already_iso8601(self, temp_db_path):
        """Should not modify timestamps already in ISO-8601 format."""
        # Create a database with both tables
        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()
        # Create file_locks table (required by FileSafetyManager)
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS file_locks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT NOT NULL UNIQUE,
                agent_name TEXT NOT NULL,
                task_id TEXT,
                locked_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                expires_at DATETIME NOT NULL,
                intent TEXT
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS file_modifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                agent_name TEXT NOT NULL,
                file_path TEXT NOT NULL,
                change_type TEXT NOT NULL,
                affected_lines TEXT,
                intent TEXT,
                timestamp TEXT NOT NULL,
                metadata TEXT
            )
            """
        )
        # Use a recent ISO-8601 timestamp to avoid auto-cleanup
        from datetime import datetime, timedelta, timezone

        recent_dt = datetime.now(timezone.utc) - timedelta(days=1)
        iso_timestamp = recent_dt.isoformat()

        cursor.execute(
            """
            INSERT INTO file_modifications
            (task_id, agent_name, file_path, change_type, timestamp)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("task-1", "agent-1", "/path/file.py", "MODIFY", iso_timestamp),
        )
        conn.commit()
        conn.close()

        # Initialize FileSafetyManager
        FileSafetyManager(db_path=temp_db_path)

        # Verify timestamp remains unchanged
        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT timestamp FROM file_modifications")
        row = cursor.fetchone()
        conn.close()

        assert row[0] == iso_timestamp

    def test_acquire_lock_already_locked_by_another_agent(self, temp_db_path):
        """Should return ALREADY_LOCKED when another agent holds the lock."""
        manager = FileSafetyManager(db_path=temp_db_path)

        test_file = "/tmp/test_lock_file.py"

        # Acquire lock as agent-1
        result = manager.acquire_lock(test_file, "agent-1")
        assert result["status"] == LockStatus.ACQUIRED

        # agent-2 tries to acquire - should see ALREADY_LOCKED
        result2 = manager.acquire_lock(test_file, "agent-2")
        assert result2["status"] == LockStatus.ALREADY_LOCKED
        assert result2["lock_holder"] == "agent-1"


class TestFailClosedBehavior:
    """Test fail-closed behavior when database errors occur."""

    @pytest.fixture
    def temp_db_path(self):
        """Create a temporary database path for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "file_safety.db"
            yield str(db_path)

    def test_check_lock_raises_on_db_error(self, temp_db_path):
        """check_lock should raise FileLockDBError on database errors."""
        manager = FileSafetyManager(db_path=temp_db_path)

        # Corrupt the database by removing the table
        conn = sqlite3.connect(temp_db_path)
        conn.execute("DROP TABLE file_locks")
        conn.commit()
        conn.close()

        with pytest.raises(FileLockDBError):
            manager.check_lock("/path/to/file.py")

    def test_validate_write_denies_on_db_error(self, temp_db_path):
        """validate_write should deny write when database error occurs."""
        manager = FileSafetyManager(db_path=temp_db_path)

        # Corrupt the database by removing the table
        conn = sqlite3.connect(temp_db_path)
        conn.execute("DROP TABLE file_locks")
        conn.commit()
        conn.close()

        result = manager.validate_write("/path/to/file.py", "agent-1")
        assert result["allowed"] is False
        assert "database error" in result["reason"].lower()

    def test_is_locked_by_other_returns_true_on_db_error(self, temp_db_path):
        """is_locked_by_other should return True (fail-closed) on DB error."""
        manager = FileSafetyManager(db_path=temp_db_path)

        # Corrupt the database by removing the table
        conn = sqlite3.connect(temp_db_path)
        conn.execute("DROP TABLE file_locks")
        conn.commit()
        conn.close()

        # Should return True (locked) when DB is unavailable
        result = manager.is_locked_by_other("/path/to/file.py", "agent-1")
        assert result is True

    def test_get_file_context_returns_warning_on_db_error(self, temp_db_path):
        """get_file_context should return warning message on DB error."""
        manager = FileSafetyManager(db_path=temp_db_path)

        # Corrupt the database by removing the table
        conn = sqlite3.connect(temp_db_path)
        conn.execute("DROP TABLE file_locks")
        conn.commit()
        conn.close()

        context = manager.get_file_context("/path/to/file.py")
        assert "WARNING" in context
        assert "Database error" in context
        assert "cannot determine lock status" in context
