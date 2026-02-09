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
