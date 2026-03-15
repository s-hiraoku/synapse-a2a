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


_registry_cache: Any = None


def _get_registry() -> Any:
    """Return a cached AgentRegistry instance (avoids N+1 instantiation)."""
    global _registry_cache
    if _registry_cache is None:
        from synapse.registry import AgentRegistry

        _registry_cache = AgentRegistry()
    return _registry_cache


def resolve_display_name(agent_id: str | None) -> str:
    """Resolve an agent_id to a human-readable display name.

    Returns ``"Name (agent_id)"`` when the registry has a name,
    otherwise returns the raw *agent_id*.  Empty/None → ``""``.
    """
    if not agent_id:
        return ""
    try:
        info = _get_registry().get_agent(agent_id)
        if info:
            name = str(info.get("name") or "")
            if name:
                return f"{name} ({agent_id})"
    except Exception:
        logger.debug("Failed to resolve agent name for %s", agent_id, exc_info=True)
    return agent_id


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
        d: dict[str, Any] = {
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
            "priority": row["priority"],
            "fail_reason": row["fail_reason"],
            "a2a_task_id": row["a2a_task_id"],
            "assignee_hint": row["assignee_hint"],
        }
        # Phase 2 grouping columns (graceful for old schemas)
        keys = row.keys()
        for col in (
            "group_id",
            "group_title",
            "plan_id",
            "component",
            "milestone",
            "external_ref",
        ):
            d[col] = row[col] if col in keys else None
        return d

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
                        completed_at DATETIME,
                        priority    INTEGER DEFAULT 3,
                        fail_reason TEXT DEFAULT '',
                        a2a_task_id TEXT,
                        assignee_hint TEXT
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
                # --- Schema migration for existing databases ---
                columns = [
                    row[1] for row in conn.execute("PRAGMA table_info(board_tasks)")
                ]
                if "priority" not in columns:
                    conn.execute(
                        "ALTER TABLE board_tasks ADD COLUMN priority INTEGER DEFAULT 3"
                    )
                if "fail_reason" not in columns:
                    conn.execute(
                        "ALTER TABLE board_tasks ADD COLUMN fail_reason TEXT DEFAULT ''"
                    )
                if "a2a_task_id" not in columns:
                    conn.execute("ALTER TABLE board_tasks ADD COLUMN a2a_task_id TEXT")
                if "assignee_hint" not in columns:
                    conn.execute(
                        "ALTER TABLE board_tasks ADD COLUMN assignee_hint TEXT"
                    )
                # Phase 2: grouping columns
                for col in (
                    "group_id",
                    "group_title",
                    "plan_id",
                    "component",
                    "milestone",
                    "external_ref",
                ):
                    if col not in columns:
                        conn.execute(f"ALTER TABLE board_tasks ADD COLUMN {col} TEXT")
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_board_group ON board_tasks(group_id)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_board_priority ON board_tasks(priority)"
                )
                conn.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_board_a2a_task_unique "
                    "ON board_tasks(a2a_task_id) "
                    "WHERE a2a_task_id IS NOT NULL"
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
        priority: int = 3,
        *,
        group_id: str | None = None,
        group_title: str | None = None,
        plan_id: str | None = None,
        component: str | None = None,
        milestone: str | None = None,
    ) -> str:
        """Create a new task.

        Args:
            subject: Task title.
            description: Task description.
            created_by: Agent ID of the creator.
            blocked_by: List of task IDs that block this task.
            priority: Task priority 1-5 (higher is more urgent).
            group_id: Optional group identifier for task grouping.
            group_title: Optional human-readable group title.
            plan_id: Optional plan card ID this task was created from.
            component: Optional component tag (e.g. "backend", "frontend").
            milestone: Optional milestone tag (e.g. "v1.0").

        Returns:
            The new task's UUID.

        Raises:
            ValueError: If priority is not an integer between 1 and 5.
        """
        if not isinstance(priority, int) or not (1 <= priority <= 5):
            raise ValueError(
                f"priority must be an integer between 1 and 5, got {priority!r}"
            )
        task_id = str(uuid4())
        blocked_json = json.dumps(blocked_by or [])

        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute(
                    """
                    INSERT INTO board_tasks
                        (id, subject, description, created_by, blocked_by, priority,
                         group_id, group_title, plan_id, component, milestone)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        task_id,
                        subject,
                        description,
                        created_by,
                        blocked_json,
                        priority,
                        group_id,
                        group_title,
                        plan_id,
                        component,
                        milestone,
                    ),
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
                cursor = conn.execute(
                    """
                    UPDATE board_tasks
                    SET status = 'completed',
                        completed_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND assignee = ? AND status = 'in_progress'
                    """,
                    (task_id, agent_id),
                )

                if cursor.rowcount == 0:
                    conn.rollback()
                    return unblocked

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

    def fail_task(self, task_id: str, agent_id: str, reason: str = "") -> bool:
        """Mark a task as failed.

        Only succeeds if the task is in_progress and assigned to the given agent.
        Unlike complete_task, failed tasks do NOT unblock dependents.

        Args:
            task_id: The task to fail.
            agent_id: The agent reporting the failure.
            reason: Optional failure reason.

        Returns:
            True if the task was updated, False if no matching task was found.
        """
        with self._lock:
            conn = self._get_connection()
            try:
                cursor = conn.execute(
                    """
                    UPDATE board_tasks
                    SET status = 'failed',
                        fail_reason = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND assignee = ? AND status = 'in_progress'
                    """,
                    (reason, task_id, agent_id),
                )
                conn.commit()
                return cursor.rowcount > 0
            finally:
                conn.close()

    def reopen_task(self, task_id: str, agent_id: str) -> bool:
        """Reopen a completed or failed task back to pending.

        Clears assignee, completed_at, and fail_reason.
        Only works on completed or failed tasks.

        Args:
            task_id: The task to reopen.
            agent_id: The agent performing the reopen (for audit).

        Returns:
            True if the task was reopened, False otherwise.
        """
        del agent_id  # Reserved for audit parity with other task actions.

        with self._lock:
            conn = self._get_connection()
            try:
                cursor = conn.execute(
                    """
                    UPDATE board_tasks
                    SET status = 'pending',
                        assignee = NULL,
                        completed_at = NULL,
                        fail_reason = '',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND status IN ('completed', 'failed')
                    """,
                    (task_id,),
                )
                conn.commit()
                return cursor.rowcount > 0
            finally:
                conn.close()

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        """Get a single task by ID.

        Args:
            task_id: The task ID.

        Returns:
            Task dict or None if not found.
        """
        with self._lock:
            conn = self._get_connection()
            try:
                row = conn.execute(
                    "SELECT * FROM board_tasks WHERE id = ?", (task_id,)
                ).fetchone()
                return self._row_to_dict(row) if row else None
            finally:
                conn.close()

    def list_tasks(
        self,
        status: str | None = None,
        assignee: str | None = None,
        *,
        group_id: str | None = None,
        component: str | None = None,
        milestone: str | None = None,
    ) -> list[dict[str, Any]]:
        """List tasks with optional filters.

        Args:
            status: Filter by status (pending, in_progress, completed).
            assignee: Filter by assignee agent ID.
            group_id: Filter by group_id.
            component: Filter by component.
            milestone: Filter by milestone.

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
                if group_id:
                    query += " AND group_id = ?"
                    params.append(group_id)
                if component:
                    query += " AND component = ?"
                    params.append(component)
                if milestone:
                    query += " AND milestone = ?"
                    params.append(milestone)

                query += " ORDER BY created_at"
                rows = conn.execute(query, params).fetchall()

                return [self._row_to_dict(row) for row in rows]
            finally:
                conn.close()

    def find_tasks_by_prefix(self, prefix: str, limit: int = 4) -> list[dict[str, Any]]:
        """Find tasks whose IDs start with the given prefix.

        Args:
            prefix: Task ID prefix to match.
            limit: Maximum number of matches to return.

        Returns:
            Matching task dicts ordered by creation time.
        """
        escaped = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        param = f"{escaped}%"
        with self._lock:
            conn = self._get_connection()
            try:
                rows = conn.execute(
                    """
                    SELECT * FROM board_tasks
                    WHERE id LIKE ? ESCAPE '\\'
                    ORDER BY created_at
                    LIMIT ?
                    """,
                    (param, limit),
                ).fetchall()
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
                    "ORDER BY priority DESC, created_at"
                ).fetchall()

                available = []
                for row in rows:
                    blocked_by = json.loads(row["blocked_by"] or "[]")
                    if not self._has_incomplete_blockers(conn, blocked_by):
                        available.append(self._row_to_dict(row))
                return available
            finally:
                conn.close()

    _VALID_STATUSES = frozenset({"pending", "in_progress", "completed", "failed"})

    def purge(self, status: str | None = None) -> int:
        """Delete tasks from the board.

        Args:
            status: If given, only delete tasks with this status.
                    If None, delete all tasks.

        Returns:
            Number of deleted tasks.

        Raises:
            ValueError: If status is not a valid task status.
        """
        if status is not None and status not in self._VALID_STATUSES:
            raise ValueError(
                f"Invalid status '{status}'. "
                f"Must be one of: {', '.join(sorted(self._VALID_STATUSES))}"
            )
        with self._lock:
            conn = self._get_connection()
            try:
                if status:
                    cursor = conn.execute(
                        "DELETE FROM board_tasks WHERE status = ?", (status,)
                    )
                else:
                    cursor = conn.execute("DELETE FROM board_tasks")
                conn.commit()
                return cursor.rowcount
            finally:
                conn.close()

    def _find_stale(
        self,
        conn: sqlite3.Connection,
        older_than_seconds: int,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """Find tasks whose updated_at is older than the threshold."""
        query = "SELECT * FROM board_tasks WHERE updated_at < datetime('now', ?)"
        params: list[str | int] = [f"-{older_than_seconds} seconds"]
        if status:
            query += " AND status = ?"
            params.append(status)
        rows = conn.execute(query, params).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def purge_stale(
        self,
        older_than_seconds: int,
        status: str | None = None,
        *,
        dry_run: bool = False,
    ) -> list[dict[str, Any]]:
        """Delete tasks whose updated_at is older than the threshold.

        Args:
            older_than_seconds: Age threshold in seconds.
            status: If given, only purge stale tasks with this status.
            dry_run: If True, return matching tasks without deleting.

        Returns:
            List of deleted (or would-be-deleted) task dicts.
        """
        with self._lock:
            conn = self._get_connection()
            try:
                stale = self._find_stale(conn, older_than_seconds, status)

                if stale and not dry_run:
                    ids = [t["id"] for t in stale]
                    placeholders = ",".join("?" for _ in ids)
                    conn.execute(
                        f"DELETE FROM board_tasks WHERE id IN ({placeholders})",
                        ids,
                    )
                    conn.commit()

                return stale
            finally:
                conn.close()

    def purge_by_ids(self, ids: list[str]) -> int:
        """Delete specific tasks by their IDs.

        Args:
            ids: List of task IDs to delete.

        Returns:
            Number of deleted tasks.
        """
        if not ids:
            return 0
        with self._lock:
            conn = self._get_connection()
            try:
                placeholders = ",".join("?" for _ in ids)
                cursor = conn.execute(
                    f"DELETE FROM board_tasks WHERE id IN ({placeholders})",
                    ids,
                )
                conn.commit()
                return cursor.rowcount
            finally:
                conn.close()

    def update_group(
        self,
        task_id: str,
        group_id: str | None = None,
        group_title: str | None = None,
    ) -> bool:
        """Update the group_id and/or group_title of a task.

        Args:
            task_id: The task to update.
            group_id: New group identifier (set if provided).
            group_title: New group title (set if provided).

        Returns:
            True if the task was updated, False if not found.
        """
        sets: list[str] = []
        params: list[str] = []
        if group_id is not None:
            sets.append("group_id = ?")
            params.append(group_id)
        if group_title is not None:
            sets.append("group_title = ?")
            params.append(group_title)
        if not sets:
            return False
        sets.append("updated_at = CURRENT_TIMESTAMP")
        params.append(task_id)

        with self._lock:
            conn = self._get_connection()
            try:
                cursor = conn.execute(
                    f"UPDATE board_tasks SET {', '.join(sets)} WHERE id = ?",
                    params,
                )
                conn.commit()
                return cursor.rowcount > 0
            finally:
                conn.close()

    def set_assignee_hint(self, task_id: str, hint: str) -> bool:
        """Set the assignee hint for a task.

        Args:
            task_id: The board task ID.
            hint: The target agent name or ID (pre-claim suggestion).

        Returns:
            True if the hint was set, False if no matching task found.
        """
        with self._lock:
            conn = self._get_connection()
            try:
                cursor = conn.execute(
                    """
                    UPDATE board_tasks
                    SET assignee_hint = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (hint, task_id),
                )
                conn.commit()
                return cursor.rowcount > 0
            finally:
                conn.close()

    def set_blocked_by(self, task_id: str, blocked_by: list[str]) -> bool:
        """Set the blocked_by list for a task.

        Sanitizes the list: removes self-references, deduplicates,
        and drops IDs that do not exist in the board.

        Args:
            task_id: The board task ID.
            blocked_by: List of task IDs that block this task.

        Returns:
            True if the task was updated, False if no matching task found.
        """
        with self._lock:
            conn = self._get_connection()
            try:
                # Sanitize: remove self-cycle and deduplicate
                candidates = list(
                    dict.fromkeys(bid for bid in blocked_by if bid != task_id)
                )
                # Keep only IDs that exist in the board
                if candidates:
                    placeholders = ",".join("?" for _ in candidates)
                    existing = {
                        row["id"]
                        for row in conn.execute(
                            f"SELECT id FROM board_tasks WHERE id IN ({placeholders})",
                            candidates,
                        ).fetchall()
                    }
                    candidates = [bid for bid in candidates if bid in existing]

                cursor = conn.execute(
                    """
                    UPDATE board_tasks
                    SET blocked_by = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (json.dumps(candidates), task_id),
                )
                conn.commit()
                return cursor.rowcount > 0
            finally:
                conn.close()

    def link_a2a_task(self, board_task_id: str, a2a_task_id: str) -> bool:
        """Link a board task to an A2A transport task.

        Args:
            board_task_id: The board task ID.
            a2a_task_id: The A2A transport task ID.

        Returns:
            True if the link was set, False if no matching board task found
            or if the a2a_task_id is already linked to another board task.
        """
        import sqlite3

        with self._lock:
            conn = self._get_connection()
            try:
                try:
                    cursor = conn.execute(
                        """
                        UPDATE board_tasks
                        SET a2a_task_id = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                        """,
                        (a2a_task_id, board_task_id),
                    )
                    conn.commit()
                    return cursor.rowcount > 0
                except sqlite3.IntegrityError:
                    conn.rollback()
                    return False
            finally:
                conn.close()

    def find_by_a2a_task_id(self, a2a_task_id: str) -> dict[str, Any] | None:
        """Find a board task linked to an A2A transport task ID.

        Args:
            a2a_task_id: The A2A transport task ID.

        Returns:
            Task dict or None if not found.
        """
        with self._lock:
            conn = self._get_connection()
            try:
                row = conn.execute(
                    "SELECT * FROM board_tasks WHERE a2a_task_id = ?",
                    (a2a_task_id,),
                ).fetchone()
                return self._row_to_dict(row) if row else None
            finally:
                conn.close()
