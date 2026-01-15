"""Tests for PID-based lock management in FileSafetyManager."""

import os
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from synapse.file_safety import FileSafetyManager, LockStatus


def future_iso_timestamp(hours: int = 1) -> str:
    """Generate ISO-8601 timestamp in the future."""
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


class TestPIDBasedLockManagement:
    """Test PID-based lock management features."""

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

    def test_acquire_lock_stores_pid(self, manager, temp_db_path):
        """Should store PID when acquiring a lock."""
        current_pid = os.getpid()

        result = manager.acquire_lock(
            file_path="test.py",
            agent_id="synapse-claude-8100",
            agent_type="claude",
            intent="Testing",
        )

        assert result["status"] == LockStatus.ACQUIRED

        # Verify PID is stored in DB
        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT pid, agent_id, agent_type FROM file_locks")
        row = cursor.fetchone()
        conn.close()

        assert row[0] == current_pid
        assert row[1] == "synapse-claude-8100"
        assert row[2] == "claude"

    def test_acquire_lock_with_explicit_pid(self, manager, temp_db_path):
        """Should use explicit PID when provided."""
        explicit_pid = 99999

        result = manager.acquire_lock(
            file_path="test.py",
            agent_id="synapse-claude-8100",
            agent_type="claude",
            pid=explicit_pid,
        )

        assert result["status"] == LockStatus.ACQUIRED

        # Verify explicit PID is stored
        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT pid FROM file_locks")
        row = cursor.fetchone()
        conn.close()

        assert row[0] == explicit_pid

    def test_list_locks_includes_pid_info(self, manager):
        """Should include PID and process status in lock listing."""
        manager.acquire_lock(
            file_path="test.py",
            agent_id="synapse-claude-8100",
            agent_type="claude",
        )

        locks = manager.list_locks()

        assert len(locks) == 1
        assert "pid" in locks[0]
        assert "agent_id" in locks[0]
        assert "agent_type" in locks[0]
        assert locks[0]["pid"] == os.getpid()

    def test_list_locks_filter_by_agent_type(self, manager):
        """Should filter locks by agent_type."""
        manager.acquire_lock(
            "file1.py", agent_id="synapse-claude-8100", agent_type="claude"
        )
        manager.acquire_lock(
            "file2.py", agent_id="synapse-gemini-8110", agent_type="gemini"
        )

        claude_locks = manager.list_locks(agent_type="claude")
        assert len(claude_locks) == 1
        assert claude_locks[0]["agent_type"] == "claude"

        gemini_locks = manager.list_locks(agent_type="gemini")
        assert len(gemini_locks) == 1
        assert gemini_locks[0]["agent_type"] == "gemini"

    def test_list_locks_filter_by_pid(self, manager, temp_db_path):
        """Should filter locks by pid."""
        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO file_locks
            (file_path, agent_name, agent_id, agent_type, pid, expires_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "/tmp/file1.py",
                "synapse-claude-8100",
                "synapse-claude-8100",
                "claude",
                1111,
                future_iso_timestamp(),
            ),
        )
        cursor.execute(
            """
            INSERT INTO file_locks
            (file_path, agent_name, agent_id, agent_type, pid, expires_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "/tmp/file2.py",
                "synapse-gemini-8110",
                "synapse-gemini-8110",
                "gemini",
                2222,
                future_iso_timestamp(),
            ),
        )
        conn.commit()
        conn.close()

        locks = manager.list_locks(pid=1111, include_stale=True)
        assert len(locks) == 1
        assert locks[0]["file_path"].endswith("file1.py")
        assert locks[0]["pid"] == 1111

    def test_check_lock_detects_dead_process(self, manager, temp_db_path):
        """Should detect and clean up locks from dead processes."""
        # Insert a lock with a non-existent PID
        dead_pid = 999999999  # Very unlikely to exist
        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO file_locks
            (file_path, agent_name, agent_id, agent_type, pid, expires_at, intent)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "/tmp/test.py",
                "synapse-dead-8100",
                "synapse-dead-8100",
                "dead",
                dead_pid,
                future_iso_timestamp(),
                "Testing",
            ),
        )
        conn.commit()
        conn.close()

        # check_lock should detect dead process and return None
        lock_info = manager.check_lock("/tmp/test.py")

        # Lock should be auto-cleaned
        assert lock_info is None
        assert len(manager.list_locks()) == 0

    def test_is_locked_by_other_ignores_dead_process_locks(self, manager, temp_db_path):
        """Should not consider locks from dead processes as valid."""
        dead_pid = 999999999
        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO file_locks
            (file_path, agent_name, agent_id, agent_type, pid, expires_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "/tmp/test.py",
                "synapse-dead-8100",
                "synapse-dead-8100",
                "dead",
                dead_pid,
                future_iso_timestamp(),
            ),
        )
        conn.commit()
        conn.close()

        # Should return False because the lock holder is dead
        result = manager.is_locked_by_other("/tmp/test.py", "synapse-claude-8100")
        assert result is False

    def test_cleanup_stale_locks(self, manager, temp_db_path):
        """Should clean up all locks from dead processes."""
        # First add a live lock (this triggers stale cleanup internally)
        manager.acquire_lock(
            "live.py", agent_id="synapse-claude-8100", agent_type="claude"
        )

        # Now insert stale locks directly into DB
        dead_pid = 999999999
        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()
        expires = future_iso_timestamp()
        for i in range(3):
            cursor.execute(
                """
                INSERT INTO file_locks
                (file_path, agent_name, agent_id, agent_type, pid, expires_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    f"/tmp/test{i}.py",
                    f"synapse-dead-{i}",
                    f"synapse-dead-{i}",
                    "dead",
                    dead_pid,
                    expires,
                ),
            )
        conn.commit()
        conn.close()

        # Verify we have 4 locks total (1 live + 3 stale)
        all_locks = manager.list_locks(include_stale=True)
        assert len(all_locks) == 4

        # Clean up stale locks
        cleaned = manager.cleanup_stale_locks()

        assert cleaned == 3
        locks = manager.list_locks()
        assert len(locks) == 1
        assert locks[0]["agent_id"] == "synapse-claude-8100"

    def test_get_stale_locks(self, manager, temp_db_path):
        """Should return list of locks from dead processes."""
        # Add a live lock first (this triggers internal cleanup)
        manager.acquire_lock(
            "live.py", agent_id="synapse-claude-8100", agent_type="claude"
        )

        # Now insert a stale lock directly
        dead_pid = 999999999
        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO file_locks
            (file_path, agent_name, agent_id, agent_type, pid, expires_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "/tmp/stale.py",
                "synapse-dead-8100",
                "synapse-dead-8100",
                "dead",
                dead_pid,
                future_iso_timestamp(),
            ),
        )
        conn.commit()
        conn.close()

        stale = manager.get_stale_locks()

        assert len(stale) == 1
        assert stale[0]["agent_id"] == "synapse-dead-8100"
        assert stale[0]["pid"] == dead_pid

    def test_get_stale_locks_empty_table(self, manager):
        """Should return empty list when file_locks table is empty (issue #97)."""
        # Ensure no locks exist
        all_locks = manager.list_locks(include_stale=True)
        assert len(all_locks) == 0

        # get_stale_locks should return empty list, not cause false positives
        stale = manager.get_stale_locks()
        assert len(stale) == 0

    def test_get_stale_locks_after_unlock(self, manager):
        """Should return empty list after proper lock/unlock cycle (issue #97)."""
        import os

        # Acquire a lock
        manager.acquire_lock(
            "issue97_test.py",
            agent_id="synapse-claude-8100",
            agent_type="claude",
            pid=os.getpid(),
        )

        # Verify lock exists
        locks = manager.list_locks()
        assert len(locks) == 1

        # Properly release the lock
        manager.release_lock("issue97_test.py", "synapse-claude-8100")

        # After unlock, no stale locks should be reported
        stale = manager.get_stale_locks()
        assert len(stale) == 0

        # Also verify no active locks
        locks = manager.list_locks()
        assert len(locks) == 0

    def test_force_unlock(self, manager):
        """Should force unlock a file regardless of owner."""
        manager.acquire_lock(
            "test.py", agent_id="synapse-gemini-8110", agent_type="gemini"
        )

        # Normal unlock should fail for different agent
        assert manager.release_lock("test.py", "synapse-claude-8100") is False

        # Force unlock should succeed
        assert manager.force_unlock("test.py") is True
        assert len(manager.list_locks()) == 0

    def test_backward_compatibility_agent_name(self, manager):
        """Should maintain backward compatibility with agent_name parameter."""
        # Old API: agent_name (should still work, maps to agent_id)
        result = manager.acquire_lock(
            file_path="test.py",
            agent_name="synapse-claude-8100",
        )

        assert result["status"] == LockStatus.ACQUIRED

        locks = manager.list_locks()
        assert len(locks) == 1
        # agent_name should be stored as agent_id for backward compatibility
        assert locks[0]["agent_id"] == "synapse-claude-8100"


class TestDBSchemaMigration:
    """Test database schema migration for new columns."""

    @pytest.fixture
    def temp_db_path(self):
        """Create a temporary database path for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "file_safety.db"
            yield str(db_path)

    def test_migration_adds_new_columns(self, temp_db_path):
        """Should add pid and agent_type columns to existing database."""
        # Create old schema database
        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE file_locks (
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
            CREATE TABLE file_modifications (
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
        # Insert old-style lock with ISO-8601 format for expires_at
        cursor.execute(
            """
            INSERT INTO file_locks (file_path, agent_name, expires_at)
            VALUES (?, ?, ?)
            """,
            ("/tmp/old.py", "old-agent", future_iso_timestamp()),
        )
        conn.commit()
        conn.close()

        # Initialize manager (should trigger migration)
        manager = FileSafetyManager(db_path=temp_db_path)

        # Verify new columns exist
        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(file_locks)")
        columns = {row[1] for row in cursor.fetchall()}
        conn.close()

        assert "pid" in columns
        assert "agent_id" in columns
        assert "agent_type" in columns

        # Old data should be migrated (agent_name -> agent_id)
        # Note: Old locks without PID are preserved (not treated as stale)
        locks = manager.list_locks()
        assert len(locks) == 1
        assert locks[0]["agent_id"] == "old-agent"


class TestListCommandIntegration:
    """Test integration with synapse list command."""

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

    def test_list_locks_for_agent_type_matches(self, manager):
        """list_locks should correctly filter by agent_type for synapse list."""
        # This is the key fix: synapse list uses agent_type to filter
        manager.acquire_lock(
            "file1.py",
            agent_id="synapse-claude-8100",
            agent_type="claude",
        )
        manager.acquire_lock(
            "file2.py",
            agent_id="synapse-gemini-8110",
            agent_type="gemini",
        )

        # synapse list --watch queries by agent_type
        claude_locks = manager.list_locks(agent_type="claude")
        assert len(claude_locks) == 1
        assert claude_locks[0]["file_path"].endswith("file1.py")

        gemini_locks = manager.list_locks(agent_type="gemini")
        assert len(gemini_locks) == 1
        assert gemini_locks[0]["file_path"].endswith("file2.py")
