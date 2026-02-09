"""Shared Task Board for multi-agent task coordination.

Provides a project-local SQLite-based task board where agents can
create, claim, and complete tasks with dependency tracking.

Storage: .synapse/task_board.db (SQLite with WAL mode)
Pattern: follows file_safety.py conventions.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = ".synapse/task_board.db"


class TaskBoard:
    """Project-local shared task board.

    Provides atomic task claiming via SQLite WAL mode and
    dependency tracking via blocked_by relationships.
    """

    def __init__(self, db_path: str | None = None, enabled: bool = True) -> None:
        self.enabled = enabled
        self.db_path = os.path.abspath(os.path.expanduser(db_path or DEFAULT_DB_PATH))
        self._lock = threading.RLock()

        if self.enabled:
            self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a SQLite connection with WAL mode."""
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _has_incomplete_blockers(
        conn: sqlite3.Connection, blocked_by: list[str]
    ) -> bool:
        """Check whether any of the given blocker task IDs are not yet completed.

        Args:
            conn: An open SQLite connection.
            blocked_by: List of task IDs to check.

        Returns:
            True if at least one blocker is incomplete, False if all are done.
        """
        if not blocked_by:
            return False
        placeholders = ",".join("?" * len(blocked_by))
        row = conn.execute(
            f"SELECT COUNT(*) FROM board_tasks "
            f"WHERE id IN ({placeholders}) AND status != 'completed'",
            blocked_by,
        ).fetchone()
        return bool(row[0] > 0)

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        """Convert a SQLite Row to a task dictionary."""
        return {
            "id": row["id"],
            "subject": row["subject"],
            "description": row["description"],
            "status": row["status"],
            "assignee": row["assignee"],
            "created_by": row["created_by"],
            "blocked_by": json.loads(row["blocked_by"] or "[]"),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "completed_at": row["completed_at"],
        }

    @classmethod
    def from_env(cls, db_path: str | None = None) -> TaskBoard:
        """Create TaskBoard from environment variables.

        Environment variables:
        - SYNAPSE_TASK_BOARD_ENABLED: "true"/"1" to enable
        - SYNAPSE_TASK_BOARD_DB_PATH: Path to SQLite database file
        """
        env_db_path = os.environ.get("SYNAPSE_TASK_BOARD_DB_PATH", "").strip()
        resolved_db_path = env_db_path or db_path

        env_enabled = os.environ.get("SYNAPSE_TASK_BOARD_ENABLED", "true").lower()
        enabled = env_enabled in ("true", "1")

        return cls(db_path=resolved_db_path, enabled=enabled)

    def _init_db(self) -> None:
        """Initialize database schema."""
        db_file = Path(self.db_path)
        db_file.parent.mkdir(parents=True, exist_ok=True)

        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS board_tasks (
                        id          TEXT PRIMARY KEY,
                        subject     TEXT NOT NULL,
                        description TEXT DEFAULT '',
                        status      TEXT NOT NULL DEFAULT 'pending',
                        assignee    TEXT,
                        created_by  TEXT NOT NULL,
                        blocked_by  TEXT DEFAULT '[]',
                        created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
                        completed_at DATETIME
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_board_status ON board_tasks(status)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_board_assignee "
                    "ON board_tasks(assignee)"
                )
                conn.commit()
            finally:
                conn.close()

    def create_task(
        self,
        subject: str,
        description: str,
        created_by: str,
        blocked_by: list[str] | None = None,
    ) -> str:
        """Create a new task.

        Args:
            subject: Task title.
            description: Task description.
            created_by: Agent ID of the creator.
            blocked_by: List of task IDs that block this task.

        Returns:
            The new task's UUID.
        """
        task_id = str(uuid4())
        blocked_json = json.dumps(blocked_by or [])

        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute(
                    """
                    INSERT INTO board_tasks
                        (id, subject, description, created_by, blocked_by)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (task_id, subject, description, created_by, blocked_json),
                )
                conn.commit()
            finally:
                conn.close()

        return task_id

    def claim_task(self, task_id: str, agent_id: str) -> bool:
        """Atomically claim a task.

        Only succeeds if the task is pending, unassigned, and not blocked.

        Args:
            task_id: The task to claim.
            agent_id: The claiming agent's ID.

        Returns:
            True if claim succeeded, False otherwise.
        """
        with self._lock:
            conn = self._get_connection()
            try:
                row = conn.execute(
                    "SELECT blocked_by FROM board_tasks WHERE id = ?",
                    (task_id,),
                ).fetchone()

                if not row:
                    return False

                blocked_by = json.loads(row["blocked_by"] or "[]")
                if self._has_incomplete_blockers(conn, blocked_by):
                    return False

                cursor = conn.execute(
                    """
                    UPDATE board_tasks
                    SET status = 'in_progress',
                        assignee = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND status = 'pending' AND assignee IS NULL
                    """,
                    (agent_id, task_id),
                )
                conn.commit()
                return cursor.rowcount > 0
            finally:
                conn.close()

    def complete_task(self, task_id: str, agent_id: str) -> list[str]:
        """Complete a task and return newly unblocked task IDs.

        Args:
            task_id: The task to complete.
            agent_id: The completing agent's ID.

        Returns:
            List of task IDs that were unblocked by this completion.
        """
        unblocked: list[str] = []

        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute(
                    """
                    UPDATE board_tasks
                    SET status = 'completed',
                        completed_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND assignee = ?
                    """,
                    (task_id, agent_id),
                )

                # Find tasks that had this task as a blocker
                rows = conn.execute(
                    "SELECT id, blocked_by FROM board_tasks WHERE status = 'pending'"
                ).fetchall()

                for row in rows:
                    blocked_by = json.loads(row["blocked_by"] or "[]")
                    if task_id not in blocked_by:
                        continue

                    remaining = [b for b in blocked_by if b != task_id]
                    if not self._has_incomplete_blockers(conn, remaining):
                        unblocked.append(row["id"])

                conn.commit()
            finally:
                conn.close()

        return unblocked

    def list_tasks(
        self,
        status: str | None = None,
        assignee: str | None = None,
    ) -> list[dict[str, Any]]:
        """List tasks with optional filters.

        Args:
            status: Filter by status (pending, in_progress, completed).
            assignee: Filter by assignee agent ID.

        Returns:
            List of task dicts.
        """
        with self._lock:
            conn = self._get_connection()
            try:
                query = "SELECT * FROM board_tasks WHERE 1=1"
                params: list[str] = []

                if status:
                    query += " AND status = ?"
                    params.append(status)
                if assignee:
                    query += " AND assignee = ?"
                    params.append(assignee)

                query += " ORDER BY created_at"
                rows = conn.execute(query, params).fetchall()

                return [self._row_to_dict(row) for row in rows]
            finally:
                conn.close()

    def get_available_tasks(self) -> list[dict[str, Any]]:
        """Get tasks that are unblocked, unassigned, and pending.

        Returns:
            List of available task dicts.
        """
        with self._lock:
            conn = self._get_connection()
            try:
                rows = conn.execute(
                    "SELECT * FROM board_tasks "
                    "WHERE status = 'pending' AND assignee IS NULL "
                    "ORDER BY created_at"
                ).fetchall()

                available = []
                for row in rows:
                    blocked_by = json.loads(row["blocked_by"] or "[]")
                    if not self._has_incomplete_blockers(conn, blocked_by):
                        available.append(self._row_to_dict(row))
                return available
            finally:
                conn.close()
