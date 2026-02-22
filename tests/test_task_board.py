"""Tests for B1: Shared Task Board - Core logic.

Test-first development: these tests define the expected behavior
for the TaskBoard before implementation.
"""

from __future__ import annotations

import sqlite3

import pytest

# ============================================================
# TestTaskBoardInit - Database initialization
# ============================================================


class TestTaskBoardInit:
    """Tests for TaskBoard database initialization."""

    @pytest.fixture
    def board(self, tmp_path):
        """Create a TaskBoard instance."""
        from synapse.task_board import TaskBoard

        db_path = str(tmp_path / "task_board.db")
        return TaskBoard(db_path=db_path)

    def test_db_created(self, board):
        """Database file should be created on init."""
        import os

        assert os.path.exists(board.db_path)

    def test_board_tasks_table_exists(self, board):
        """board_tasks table should exist."""
        conn = sqlite3.connect(board.db_path)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='board_tasks'"
        )
        assert cursor.fetchone() is not None
        conn.close()

    def test_indexes_exist(self, board):
        """Status and assignee indexes should exist."""
        conn = sqlite3.connect(board.db_path)
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
        index_names = {row[0] for row in cursor.fetchall()}
        assert "idx_board_status" in index_names
        assert "idx_board_assignee" in index_names
        conn.close()

    def test_wal_mode(self, board):
        """Database should use WAL journal mode."""
        conn = sqlite3.connect(board.db_path)
        result = conn.execute("PRAGMA journal_mode").fetchone()
        assert result[0] == "wal"
        conn.close()


# ============================================================
# TestTaskBoardCreateTask - Task creation
# ============================================================


class TestTaskBoardCreateTask:
    """Tests for creating tasks."""

    @pytest.fixture
    def board(self, tmp_path):
        from synapse.task_board import TaskBoard

        return TaskBoard(db_path=str(tmp_path / "task_board.db"))

    def test_create_returns_uuid(self, board):
        """create_task should return a UUID string."""
        task_id = board.create_task(
            subject="Write tests",
            description="Write unit tests for auth module",
            created_by="synapse-claude-8100",
        )
        assert isinstance(task_id, str)
        assert len(task_id) > 0

    def test_created_task_has_pending_status(self, board):
        """New tasks should have status=pending."""
        task_id = board.create_task(
            subject="Write tests",
            description="",
            created_by="synapse-claude-8100",
        )
        tasks = board.list_tasks()
        task = next(t for t in tasks if t["id"] == task_id)
        assert task["status"] == "pending"

    def test_created_task_stores_blocked_by(self, board):
        """blocked_by should be stored correctly."""
        t1 = board.create_task(subject="Task 1", description="", created_by="claude")
        t2 = board.create_task(
            subject="Task 2",
            description="",
            created_by="claude",
            blocked_by=[t1],
        )
        tasks = board.list_tasks()
        task2 = next(t for t in tasks if t["id"] == t2)
        assert t1 in task2["blocked_by"]

    def test_created_task_stores_created_by(self, board):
        """created_by should be stored."""
        task_id = board.create_task(
            subject="Test",
            description="",
            created_by="synapse-gemini-8110",
        )
        tasks = board.list_tasks()
        task = next(t for t in tasks if t["id"] == task_id)
        assert task["created_by"] == "synapse-gemini-8110"


# ============================================================
# TestTaskBoardClaimTask - Atomic task claiming
# ============================================================


class TestTaskBoardClaimTask:
    """Tests for atomic task claiming."""

    @pytest.fixture
    def board(self, tmp_path):
        from synapse.task_board import TaskBoard

        return TaskBoard(db_path=str(tmp_path / "task_board.db"))

    def test_claim_success(self, board):
        """Should successfully claim an unclaimed task."""
        task_id = board.create_task(subject="Test", description="", created_by="claude")
        result = board.claim_task(task_id, "synapse-claude-8100")
        assert result is True

    def test_claim_sets_in_progress(self, board):
        """Claimed task should transition to in_progress."""
        task_id = board.create_task(subject="Test", description="", created_by="claude")
        board.claim_task(task_id, "synapse-claude-8100")
        tasks = board.list_tasks()
        task = next(t for t in tasks if t["id"] == task_id)
        assert task["status"] == "in_progress"
        assert task["assignee"] == "synapse-claude-8100"

    def test_double_claim_rejected(self, board):
        """Cannot claim an already claimed task."""
        task_id = board.create_task(subject="Test", description="", created_by="claude")
        board.claim_task(task_id, "synapse-claude-8100")
        result = board.claim_task(task_id, "synapse-gemini-8110")
        assert result is False

    def test_blocked_task_claim_rejected(self, board):
        """Cannot claim a task that is blocked."""
        t1 = board.create_task(subject="Task 1", description="", created_by="claude")
        t2 = board.create_task(
            subject="Task 2",
            description="",
            created_by="claude",
            blocked_by=[t1],
        )
        result = board.claim_task(t2, "synapse-claude-8100")
        assert result is False


# ============================================================
# TestTaskBoardCompleteTask - Task completion
# ============================================================


class TestTaskBoardCompleteTask:
    """Tests for task completion."""

    @pytest.fixture
    def board(self, tmp_path):
        from synapse.task_board import TaskBoard

        return TaskBoard(db_path=str(tmp_path / "task_board.db"))

    def test_complete_sets_status(self, board):
        """complete_task should set status to completed."""
        task_id = board.create_task(subject="Test", description="", created_by="claude")
        board.claim_task(task_id, "synapse-claude-8100")
        board.complete_task(task_id, "synapse-claude-8100")
        tasks = board.list_tasks()
        task = next(t for t in tasks if t["id"] == task_id)
        assert task["status"] == "completed"

    def test_complete_unblocks_dependents(self, board):
        """Completing a task should unblock dependent tasks."""
        t1 = board.create_task(subject="Task 1", description="", created_by="claude")
        t2 = board.create_task(
            subject="Task 2",
            description="",
            created_by="claude",
            blocked_by=[t1],
        )
        board.claim_task(t1, "synapse-claude-8100")
        unblocked = board.complete_task(t1, "synapse-claude-8100")
        assert t2 in unblocked

    def test_partial_unblock(self, board):
        """Task with multiple blockers: only unblocked when all complete."""
        t1 = board.create_task(subject="Task 1", description="", created_by="claude")
        t2 = board.create_task(subject="Task 2", description="", created_by="claude")
        t3 = board.create_task(
            subject="Task 3",
            description="",
            created_by="claude",
            blocked_by=[t1, t2],
        )

        board.claim_task(t1, "synapse-claude-8100")
        unblocked = board.complete_task(t1, "synapse-claude-8100")
        # t3 still blocked by t2
        assert t3 not in unblocked

        board.claim_task(t2, "synapse-gemini-8110")
        unblocked = board.complete_task(t2, "synapse-gemini-8110")
        # Now t3 should be unblocked
        assert t3 in unblocked


# ============================================================
# TestTaskBoardListTasks - Task listing and filtering
# ============================================================


class TestTaskBoardListTasks:
    """Tests for task listing."""

    @pytest.fixture
    def board(self, tmp_path):
        from synapse.task_board import TaskBoard

        return TaskBoard(db_path=str(tmp_path / "task_board.db"))

    def test_list_all_tasks(self, board):
        """Should return all tasks."""
        board.create_task(subject="T1", description="", created_by="claude")
        board.create_task(subject="T2", description="", created_by="gemini")
        tasks = board.list_tasks()
        assert len(tasks) == 2

    def test_filter_by_status(self, board):
        """Should filter by status."""
        t1 = board.create_task(subject="T1", description="", created_by="claude")
        board.create_task(subject="T2", description="", created_by="gemini")
        board.claim_task(t1, "synapse-claude-8100")

        pending = board.list_tasks(status="pending")
        assert len(pending) == 1
        assert pending[0]["subject"] == "T2"

    def test_filter_by_assignee(self, board):
        """Should filter by assignee."""
        t1 = board.create_task(subject="T1", description="", created_by="claude")
        board.create_task(subject="T2", description="", created_by="gemini")
        board.claim_task(t1, "synapse-claude-8100")

        assigned = board.list_tasks(assignee="synapse-claude-8100")
        assert len(assigned) == 1
        assert assigned[0]["subject"] == "T1"

    def test_get_available_tasks(self, board):
        """Should return unblocked, unassigned, pending tasks."""
        t1 = board.create_task(subject="T1", description="", created_by="claude")
        board.create_task(
            subject="T2",
            description="",
            created_by="claude",
            blocked_by=[t1],
        )
        board.create_task(subject="T3", description="", created_by="gemini")

        available = board.get_available_tasks()
        subjects = [t["subject"] for t in available]
        assert "T1" in subjects
        assert "T3" in subjects
        assert "T2" not in subjects


# ============================================================
# TestTaskBoardFromEnv - Environment-based initialization
# ============================================================


class TestTaskBoardFromEnv:
    """Tests for from_env initialization."""

    def test_from_env_default(self, tmp_path, monkeypatch):
        """Should create with default path when env not set."""
        from synapse.task_board import TaskBoard

        monkeypatch.chdir(tmp_path)
        board = TaskBoard.from_env()
        assert board is not None

    def test_from_env_custom_path(self, tmp_path, monkeypatch):
        """Should use SYNAPSE_TASK_BOARD_DB_PATH if set."""
        from synapse.task_board import TaskBoard

        db_path = str(tmp_path / "custom.db")
        monkeypatch.setenv("SYNAPSE_TASK_BOARD_DB_PATH", db_path)
        board = TaskBoard.from_env()
        assert board.db_path == db_path


# ============================================================
# TestTaskBoardPriority - Priority column
# ============================================================


class TestTaskBoardPriority:
    """Tests for task priority support."""

    @pytest.fixture
    def board(self, tmp_path):
        from synapse.task_board import TaskBoard

        return TaskBoard(db_path=str(tmp_path / "task_board.db"))

    def test_default_priority(self, board):
        """Tasks should have default priority 3."""
        task_id = board.create_task(subject="Test", description="", created_by="claude")
        tasks = board.list_tasks()
        task = next(t for t in tasks if t["id"] == task_id)
        assert task["priority"] == 3

    def test_create_with_priority(self, board):
        """create_task should accept priority parameter."""
        task_id = board.create_task(
            subject="Urgent", description="", created_by="claude", priority=5
        )
        tasks = board.list_tasks()
        task = next(t for t in tasks if t["id"] == task_id)
        assert task["priority"] == 5

    def test_available_tasks_ordered_by_priority(self, board):
        """get_available_tasks should return higher priority first."""
        board.create_task(
            subject="Low", description="", created_by="claude", priority=1
        )
        board.create_task(
            subject="High", description="", created_by="claude", priority=5
        )
        board.create_task(
            subject="Normal", description="", created_by="claude", priority=3
        )

        available = board.get_available_tasks()
        subjects = [t["subject"] for t in available]
        assert subjects == ["High", "Normal", "Low"]

    def test_priority_with_blocked_tasks(self, board):
        """Blocked tasks should not appear even with high priority."""
        t1 = board.create_task(
            subject="Blocker", description="", created_by="claude", priority=1
        )
        board.create_task(
            subject="Blocked High",
            description="",
            created_by="claude",
            priority=5,
            blocked_by=[t1],
        )
        board.create_task(
            subject="Available Low",
            description="",
            created_by="claude",
            priority=2,
        )

        available = board.get_available_tasks()
        subjects = [t["subject"] for t in available]
        assert "Blocked High" not in subjects
        assert "Available Low" in subjects


# ============================================================
# TestTaskBoardFailTask - Task failure
# ============================================================


class TestTaskBoardFailTask:
    """Tests for fail_task functionality."""

    @pytest.fixture
    def board(self, tmp_path):
        from synapse.task_board import TaskBoard

        return TaskBoard(db_path=str(tmp_path / "task_board.db"))

    def test_fail_sets_status(self, board):
        """fail_task should set status to failed."""
        task_id = board.create_task(subject="Test", description="", created_by="claude")
        board.claim_task(task_id, "synapse-claude-8100")
        board.fail_task(task_id, "synapse-claude-8100", reason="Tests failed")

        tasks = board.list_tasks()
        task = next(t for t in tasks if t["id"] == task_id)
        assert task["status"] == "failed"

    def test_fail_stores_reason(self, board):
        """fail_task should store the failure reason."""
        task_id = board.create_task(subject="Test", description="", created_by="claude")
        board.claim_task(task_id, "synapse-claude-8100")
        board.fail_task(task_id, "synapse-claude-8100", reason="Dependency missing")

        tasks = board.list_tasks()
        task = next(t for t in tasks if t["id"] == task_id)
        assert task["fail_reason"] == "Dependency missing"

    def test_fail_preserves_assignee(self, board):
        """fail_task should keep assignee for audit trail."""
        task_id = board.create_task(subject="Test", description="", created_by="claude")
        board.claim_task(task_id, "synapse-claude-8100")
        board.fail_task(task_id, "synapse-claude-8100")

        tasks = board.list_tasks()
        task = next(t for t in tasks if t["id"] == task_id)
        assert task["assignee"] == "synapse-claude-8100"

    def test_fail_wrong_agent(self, board):
        """fail_task should fail silently if agent doesn't match."""
        task_id = board.create_task(subject="Test", description="", created_by="claude")
        board.claim_task(task_id, "synapse-claude-8100")
        board.fail_task(task_id, "synapse-gemini-8110")

        tasks = board.list_tasks()
        task = next(t for t in tasks if t["id"] == task_id)
        assert task["status"] == "in_progress"  # unchanged

    def test_fail_pending_task_noop(self, board):
        """fail_task on pending task should have no effect."""
        task_id = board.create_task(subject="Test", description="", created_by="claude")
        board.fail_task(task_id, "synapse-claude-8100")

        tasks = board.list_tasks()
        task = next(t for t in tasks if t["id"] == task_id)
        assert task["status"] == "pending"

    def test_fail_does_not_unblock_dependents(self, board):
        """Failed task should NOT unblock dependent tasks."""
        t1 = board.create_task(subject="Task 1", description="", created_by="claude")
        t2 = board.create_task(
            subject="Task 2",
            description="",
            created_by="claude",
            blocked_by=[t1],
        )
        board.claim_task(t1, "synapse-claude-8100")
        board.fail_task(t1, "synapse-claude-8100")

        available = board.get_available_tasks()
        available_ids = [t["id"] for t in available]
        assert t2 not in available_ids

    def test_fail_empty_reason(self, board):
        """fail_task with no reason should default to empty string."""
        task_id = board.create_task(subject="Test", description="", created_by="claude")
        board.claim_task(task_id, "synapse-claude-8100")
        board.fail_task(task_id, "synapse-claude-8100")

        tasks = board.list_tasks()
        task = next(t for t in tasks if t["id"] == task_id)
        assert task["fail_reason"] == ""

    def test_filter_by_failed_status(self, board):
        """list_tasks should support filtering by failed status."""
        t1 = board.create_task(subject="Good", description="", created_by="claude")
        t2 = board.create_task(subject="Bad", description="", created_by="claude")
        board.claim_task(t1, "synapse-claude-8100")
        board.complete_task(t1, "synapse-claude-8100")
        board.claim_task(t2, "synapse-claude-8100")
        board.fail_task(t2, "synapse-claude-8100", reason="Error")

        failed = board.list_tasks(status="failed")
        assert len(failed) == 1
        assert failed[0]["subject"] == "Bad"


# ============================================================
# TestTaskBoardReopenTask - Task reopening
# ============================================================


class TestTaskBoardReopenTask:
    """Tests for reopen_task functionality."""

    @pytest.fixture
    def board(self, tmp_path):
        from synapse.task_board import TaskBoard

        return TaskBoard(db_path=str(tmp_path / "task_board.db"))

    def test_reopen_completed_task(self, board):
        """reopen_task should move completed task back to pending."""
        task_id = board.create_task(subject="Test", description="", created_by="claude")
        board.claim_task(task_id, "synapse-claude-8100")
        board.complete_task(task_id, "synapse-claude-8100")

        result = board.reopen_task(task_id, "synapse-claude-8100")
        assert result is True

        tasks = board.list_tasks()
        task = next(t for t in tasks if t["id"] == task_id)
        assert task["status"] == "pending"
        assert task["assignee"] is None
        assert task["completed_at"] is None

    def test_reopen_failed_task(self, board):
        """reopen_task should move failed task back to pending."""
        task_id = board.create_task(subject="Test", description="", created_by="claude")
        board.claim_task(task_id, "synapse-claude-8100")
        board.fail_task(task_id, "synapse-claude-8100", reason="Error")

        result = board.reopen_task(task_id, "synapse-claude-8100")
        assert result is True

        tasks = board.list_tasks()
        task = next(t for t in tasks if t["id"] == task_id)
        assert task["status"] == "pending"
        assert task["assignee"] is None
        assert task["fail_reason"] == ""

    def test_reopen_clears_assignee(self, board):
        """reopen_task should clear assignee."""
        task_id = board.create_task(subject="Test", description="", created_by="claude")
        board.claim_task(task_id, "synapse-claude-8100")
        board.complete_task(task_id, "synapse-claude-8100")
        board.reopen_task(task_id, "synapse-claude-8100")

        tasks = board.list_tasks()
        task = next(t for t in tasks if t["id"] == task_id)
        assert task["assignee"] is None

    def test_reopen_pending_returns_false(self, board):
        """reopen_task on pending task should return False (no-op)."""
        task_id = board.create_task(subject="Test", description="", created_by="claude")
        result = board.reopen_task(task_id, "synapse-claude-8100")
        assert result is False

    def test_reopen_in_progress_returns_false(self, board):
        """reopen_task on in_progress task should return False (no-op)."""
        task_id = board.create_task(subject="Test", description="", created_by="claude")
        board.claim_task(task_id, "synapse-claude-8100")
        result = board.reopen_task(task_id, "synapse-claude-8100")
        assert result is False

    def test_reopen_nonexistent_returns_false(self, board):
        """reopen_task on nonexistent task should return False."""
        result = board.reopen_task("nonexistent-id", "synapse-claude-8100")
        assert result is False

    def test_reopened_task_becomes_available(self, board):
        """Reopened task should appear in get_available_tasks."""
        task_id = board.create_task(subject="Test", description="", created_by="claude")
        board.claim_task(task_id, "synapse-claude-8100")
        board.complete_task(task_id, "synapse-claude-8100")
        board.reopen_task(task_id, "synapse-claude-8100")

        available = board.get_available_tasks()
        available_ids = [t["id"] for t in available]
        assert task_id in available_ids

    def test_reopened_task_can_be_reclaimed(self, board):
        """Reopened task should be claimable by any agent."""
        task_id = board.create_task(subject="Test", description="", created_by="claude")
        board.claim_task(task_id, "synapse-claude-8100")
        board.fail_task(task_id, "synapse-claude-8100", reason="Error")
        board.reopen_task(task_id, "synapse-claude-8100")

        # Different agent can now claim
        result = board.claim_task(task_id, "synapse-gemini-8110")
        assert result is True

    def test_reopen_preserves_priority(self, board):
        """reopen_task should not change the task's priority."""
        task_id = board.create_task(
            subject="Urgent", description="", created_by="claude", priority=5
        )
        board.claim_task(task_id, "synapse-claude-8100")
        board.complete_task(task_id, "synapse-claude-8100")
        board.reopen_task(task_id, "synapse-claude-8100")

        tasks = board.list_tasks()
        task = next(t for t in tasks if t["id"] == task_id)
        assert task["priority"] == 5

    def test_reopen_does_not_affect_downstream_completed(self, board):
        """Reopening a task should NOT revert already completed downstream tasks."""
        t1 = board.create_task(subject="Task 1", description="", created_by="claude")
        t2 = board.create_task(
            subject="Task 2",
            description="",
            created_by="claude",
            blocked_by=[t1],
        )
        # Complete both
        board.claim_task(t1, "synapse-claude-8100")
        board.complete_task(t1, "synapse-claude-8100")
        board.claim_task(t2, "synapse-claude-8100")
        board.complete_task(t2, "synapse-claude-8100")

        # Reopen t1 — t2 should stay completed
        board.reopen_task(t1, "synapse-claude-8100")

        tasks = board.list_tasks()
        task2 = next(t for t in tasks if t["id"] == t2)
        assert task2["status"] == "completed"


# ============================================================
# TestTaskBoardMigration - Schema migration for existing DBs
# ============================================================


class TestTaskBoardMigration:
    """Tests for schema migration when opening an existing DB."""

    def test_migration_adds_priority_column(self, tmp_path):
        """Opening an old DB should add priority column."""
        db_path = str(tmp_path / "old.db")

        # Create DB with old schema (no priority/fail_reason columns)
        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            CREATE TABLE board_tasks (
                id TEXT PRIMARY KEY,
                subject TEXT NOT NULL,
                description TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending',
                assignee TEXT,
                created_by TEXT NOT NULL,
                blocked_by TEXT DEFAULT '[]',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                completed_at DATETIME
            )
            """
        )
        conn.execute(
            "INSERT INTO board_tasks (id, subject, created_by) VALUES ('t1', 'Old task', 'claude')"
        )
        conn.commit()
        conn.close()

        # Open with new TaskBoard — should migrate
        from synapse.task_board import TaskBoard

        board = TaskBoard(db_path=db_path)

        # Old task should have default priority
        tasks = board.list_tasks()
        assert len(tasks) == 1
        assert tasks[0]["priority"] == 3
        assert tasks[0]["fail_reason"] == ""

    def test_migration_adds_fail_reason_column(self, tmp_path):
        """Opening an old DB should add fail_reason column."""
        db_path = str(tmp_path / "old.db")

        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            CREATE TABLE board_tasks (
                id TEXT PRIMARY KEY,
                subject TEXT NOT NULL,
                description TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending',
                assignee TEXT,
                created_by TEXT NOT NULL,
                blocked_by TEXT DEFAULT '[]',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                completed_at DATETIME
            )
            """
        )
        conn.commit()
        conn.close()

        from synapse.task_board import TaskBoard

        board = TaskBoard(db_path=db_path)

        # Should be able to fail a task (fail_reason column exists)
        task_id = board.create_task(
            subject="New task", description="", created_by="claude"
        )
        board.claim_task(task_id, "synapse-claude-8100")
        board.fail_task(task_id, "synapse-claude-8100", reason="Test failure")

        tasks = board.list_tasks()
        task = next(t for t in tasks if t["id"] == task_id)
        assert task["fail_reason"] == "Test failure"
