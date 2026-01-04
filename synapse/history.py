"""Session History Persistence using SQLite.

This module provides lightweight history tracking for Synapse A2A tasks,
enabling users to review past interactions and search historical data.
"""

import contextlib
import json
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any


class HistoryManager:
    """Manages task history persistence using SQLite.

    Features:
    - Automatically creates database and schema on first use
    - Thread-safe operations with lock protection
    - Optionally disabled via SYNAPSE_HISTORY_ENABLED environment variable
    - Stores task input/output with metadata
    """

    def __init__(self, db_path: str, enabled: bool = True) -> None:
        """Initialize HistoryManager.

        Args:
            db_path: Path to SQLite database file
            enabled: Whether history recording is enabled
        """
        self.enabled = enabled
        self.db_path = db_path
        self._lock = threading.RLock()

        if self.enabled:
            self._init_db()

    @classmethod
    def from_env(cls, db_path: str) -> "HistoryManager":
        """Create HistoryManager from environment variables.

        Respects SYNAPSE_HISTORY_ENABLED environment variable.
        - "true", "1": enabled
        - "false", "0", not set: disabled

        Args:
            db_path: Path to SQLite database file

        Returns:
            HistoryManager instance with enabled status from env var
        """
        env_val = os.environ.get("SYNAPSE_HISTORY_ENABLED", "false").lower()
        enabled = env_val in ("true", "1")
        return cls(db_path=db_path, enabled=enabled)

    def _init_db(self) -> None:
        """Initialize database and create schema if needed."""
        if not self.enabled:
            return

        # Create directory if it doesn't exist
        db_file = Path(self.db_path)
        db_file.parent.mkdir(parents=True, exist_ok=True)

        with self._lock:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()

                # Create observations table
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS observations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT NOT NULL,
                        agent_name TEXT NOT NULL,
                        task_id TEXT NOT NULL UNIQUE,
                        input TEXT NOT NULL,
                        output TEXT NOT NULL,
                        status TEXT NOT NULL,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                        metadata TEXT
                    )
                    """
                )

                # Create indexes for efficient querying
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_agent_name ON observations(agent_name)"
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_timestamp ON observations(timestamp)"
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_task_id ON observations(task_id)"
                )

                conn.commit()
                conn.close()
            except sqlite3.Error as e:
                if self.enabled:
                    # Log error but don't crash - history is non-critical
                    import sys

                    print(
                        f"Warning: Failed to initialize history DB: {e}",
                        file=sys.stderr,
                    )

    def save_observation(
        self,
        task_id: str,
        agent_name: str,
        session_id: str,
        input_text: str,
        output_text: str,
        status: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Save a task observation to history.

        Args:
            task_id: Unique task identifier
            agent_name: Name of the agent handling the task
            session_id: Session/conversation identifier
            input_text: Task input/request
            output_text: Task output/result
            status: Task status (completed, failed, canceled)
            metadata: Optional metadata as dict (will be JSON-serialized)
        """
        if not self.enabled:
            return

        metadata_json = None
        if metadata:
            with contextlib.suppress(TypeError, ValueError):
                metadata_json = json.dumps(metadata)

        with self._lock:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()

                cursor.execute(
                    """
                    INSERT INTO observations
                    (session_id, agent_name, task_id, input, output, status, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session_id,
                        agent_name,
                        task_id,
                        input_text,
                        output_text,
                        status,
                        metadata_json,
                    ),
                )

                conn.commit()
                conn.close()
            except sqlite3.Error as e:
                # Non-critical error - don't crash
                import sys

                print(f"Warning: Failed to save observation: {e}", file=sys.stderr)

    def get_observation(self, task_id: str) -> dict[str, Any] | None:
        """Retrieve a specific observation by task_id.

        Args:
            task_id: Task identifier to retrieve

        Returns:
            Observation dict or None if not found
        """
        if not self.enabled:
            return None

        with self._lock:
            try:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                cursor.execute(
                    "SELECT * FROM observations WHERE task_id = ?",
                    (task_id,),
                )

                row = cursor.fetchone()
                conn.close()

                if row:
                    return self._row_to_dict(row)
                return None
            except sqlite3.Error as e:
                import sys

                print(f"Warning: Failed to retrieve observation: {e}", file=sys.stderr)
                return None

    def list_observations(
        self,
        limit: int = 50,
        agent_name: str | None = None,
    ) -> list[dict[str, Any]]:
        """List observations with optional filtering.

        Args:
            limit: Maximum number of observations to return
            agent_name: Optional filter by agent name

        Returns:
            List of observation dicts, ordered by timestamp (newest first)
        """
        if not self.enabled:
            return []

        with self._lock:
            try:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                if agent_name:
                    cursor.execute(
                        """
                        SELECT * FROM observations
                        WHERE agent_name = ?
                        ORDER BY timestamp DESC
                        LIMIT ?
                        """,
                        (agent_name, limit),
                    )
                else:
                    cursor.execute(
                        """
                        SELECT * FROM observations
                        ORDER BY timestamp DESC
                        LIMIT ?
                        """,
                        (limit,),
                    )

                rows = cursor.fetchall()
                conn.close()

                return [self._row_to_dict(row) for row in rows]
            except sqlite3.Error as e:
                import sys

                print(f"Warning: Failed to list observations: {e}", file=sys.stderr)
                return []

    def _row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        """Convert sqlite3.Row to dict with parsed metadata.

        Args:
            row: sqlite3.Row object

        Returns:
            Dict representation with metadata parsed from JSON
        """
        data = dict(row)

        # Parse metadata JSON if present
        if data.get("metadata"):
            try:
                data["metadata"] = json.loads(data["metadata"])
            except (json.JSONDecodeError, TypeError):
                data["metadata"] = {}

        return data

    def search_observations(
        self,
        keywords: list[str],
        logic: str = "OR",
        case_sensitive: bool = False,
        limit: int = 50,
        agent_name: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search observations by keyword(s) in input/output fields.

        Args:
            keywords: List of keywords to search for
            logic: Search logic - "OR" (any keyword) or "AND" (all keywords)
            case_sensitive: Whether search is case-sensitive (default: False)
            limit: Maximum number of results to return
            agent_name: Optional filter by agent name

        Returns:
            List of observation dicts matching search criteria
        """
        if not self.enabled or not keywords:
            return []

        with self._lock:
            try:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                # Build LIKE/GLOB clauses dynamically
                like_clauses = []
                params = []

                for keyword in keywords:
                    if case_sensitive:
                        # Use GLOB for case-sensitive matching
                        like_clauses.append("(input GLOB ? OR output GLOB ?)")
                        params.extend([f"*{keyword}*", f"*{keyword}*"])
                    else:
                        # Use LOWER() + LIKE for case-insensitive matching
                        like_clauses.append("(LOWER(input) LIKE ? OR LOWER(output) LIKE ?)")
                        params.extend([f"%{keyword.lower()}%", f"%{keyword.lower()}%"])

                # Join clauses with OR or AND based on logic parameter
                if logic.upper() == "AND":
                    where_clause = " AND ".join(like_clauses)
                else:
                    where_clause = " OR ".join(like_clauses)

                # Build full query
                query = f"SELECT * FROM observations WHERE ({where_clause})"

                # Add agent filter if provided
                if agent_name:
                    query += " AND agent_name = ?"
                    params.append(agent_name)

                # Add ordering and limit
                query += " ORDER BY timestamp DESC LIMIT ?"
                params.append(limit)

                cursor.execute(query, params)
                rows = cursor.fetchall()
                conn.close()

                return [self._row_to_dict(row) for row in rows]
            except sqlite3.Error as e:
                import sys
                print(f"Warning: Failed to search observations: {e}", file=sys.stderr)
                return []

    def cleanup_old_observations(
        self,
        days: int,
        vacuum: bool = True,
    ) -> dict[str, Any]:
        """Delete observations older than specified number of days.

        Args:
            days: Number of days - delete records older than this
            vacuum: Whether to run VACUUM to reclaim disk space

        Returns:
            Dict with keys: deleted_count, vacuum_reclaimed_mb
        """
        if not self.enabled:
            return {"deleted_count": 0, "vacuum_reclaimed_mb": 0}

        with self._lock:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()

                # Delete observations older than N days
                cursor.execute(
                    f"""DELETE FROM observations
                       WHERE timestamp < datetime('now', '-{days} days')"""
                )
                deleted_count = cursor.rowcount
                conn.commit()

                # VACUUM to reclaim space
                vacuum_reclaimed_mb = 0.0
                if vacuum and deleted_count > 0:
                    try:
                        size_before = Path(self.db_path).stat().st_size
                        cursor.execute("VACUUM")
                        conn.commit()
                        size_after = Path(self.db_path).stat().st_size
                        vacuum_reclaimed_mb = (size_before - size_after) / (1024 * 1024)
                    except (OSError, sqlite3.Error):
                        # If VACUUM fails, still report the deletion
                        vacuum_reclaimed_mb = 0.0

                conn.close()

                return {
                    "deleted_count": deleted_count,
                    "vacuum_reclaimed_mb": vacuum_reclaimed_mb,
                }
            except sqlite3.Error as e:
                import sys
                print(f"Warning: Failed to cleanup observations: {e}", file=sys.stderr)
                return {"deleted_count": 0, "vacuum_reclaimed_mb": 0}

    def cleanup_by_size(
        self,
        max_size_mb: int,
        vacuum: bool = True,
    ) -> dict[str, Any]:
        """Delete oldest observations to keep database under max size.

        Args:
            max_size_mb: Target maximum database size in megabytes
            vacuum: Whether to run VACUUM to reclaim disk space

        Returns:
            Dict with keys: deleted_count, vacuum_reclaimed_mb
        """
        if not self.enabled:
            return {"deleted_count": 0, "vacuum_reclaimed_mb": 0}

        with self._lock:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()

                # Check current size
                current_size_mb = Path(self.db_path).stat().st_size / (1024 * 1024)

                if current_size_mb <= max_size_mb:
                    conn.close()
                    return {"deleted_count": 0, "vacuum_reclaimed_mb": 0}

                # Delete in batches (25% at a time) until under target size
                cursor.execute("SELECT COUNT(*) FROM observations")
                total_rows = cursor.fetchone()[0]
                deleted_count = 0
                max_iterations = 10

                for _ in range(max_iterations):
                    # Delete oldest 25% of remaining records
                    batch_size = max(1, total_rows // 4)

                    cursor.execute(
                        """DELETE FROM observations
                           WHERE id IN (
                               SELECT id FROM observations
                               ORDER BY timestamp ASC
                               LIMIT ?
                           )""",
                        (batch_size,),
                    )

                    deleted_count += cursor.rowcount
                    total_rows -= cursor.rowcount
                    conn.commit()

                    # Check size after deletion
                    current_size_mb = Path(self.db_path).stat().st_size / (1024 * 1024)

                    if current_size_mb <= max_size_mb or total_rows == 0:
                        break

                # VACUUM to reclaim space
                vacuum_reclaimed_mb = 0.0
                if vacuum and deleted_count > 0:
                    try:
                        size_before = Path(self.db_path).stat().st_size
                        cursor.execute("VACUUM")
                        conn.commit()
                        size_after = Path(self.db_path).stat().st_size
                        vacuum_reclaimed_mb = (size_before - size_after) / (1024 * 1024)
                    except (OSError, sqlite3.Error):
                        vacuum_reclaimed_mb = 0.0

                conn.close()

                return {
                    "deleted_count": deleted_count,
                    "vacuum_reclaimed_mb": vacuum_reclaimed_mb,
                }
            except sqlite3.Error as e:
                import sys
                print(f"Warning: Failed to cleanup by size: {e}", file=sys.stderr)
                return {"deleted_count": 0, "vacuum_reclaimed_mb": 0}

    def get_database_size(self) -> int:
        """Get database file size in bytes.

        Returns:
            Size of database file in bytes, or 0 if file doesn't exist
        """
        try:
            return Path(self.db_path).stat().st_size
        except OSError:
            return 0

    def get_statistics(
        self,
        agent_name: str | None = None,
    ) -> dict[str, Any]:
        """Get usage statistics for task history.

        Args:
            agent_name: Optional filter to get stats for specific agent only

        Returns:
            Dict with statistics: total_tasks, completed, failed, canceled,
            success_rate, by_agent breakdown, db_size_mb, oldest_task, newest_task
        """
        if not self.enabled:
            return {}

        with self._lock:
            try:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                # Build WHERE clause for agent filter
                where_clause = ""
                params = []
                if agent_name:
                    where_clause = "WHERE agent_name = ?"
                    params = [agent_name]

                # Total task count
                cursor.execute(
                    f"SELECT COUNT(*) FROM observations {where_clause}",
                    params,
                )
                total_tasks = cursor.fetchone()[0]

                if total_tasks == 0:
                    conn.close()
                    return {
                        "total_tasks": 0,
                        "completed": 0,
                        "failed": 0,
                        "canceled": 0,
                        "success_rate": 0.0,
                        "by_agent": {},
                        "db_size_mb": self.get_database_size() / (1024 * 1024),
                        "oldest_task": None,
                        "newest_task": None,
                        "date_range_days": 0,
                    }

                # Status breakdown
                cursor.execute(
                    f"SELECT status, COUNT(*) FROM observations {where_clause} GROUP BY status",
                    params,
                )
                status_counts = dict(cursor.fetchall())

                completed = status_counts.get("completed", 0)
                failed = status_counts.get("failed", 0)
                canceled = status_counts.get("canceled", 0)

                # Success rate (only count completed and failed, exclude canceled)
                total_finished = completed + failed
                success_rate = (
                    (completed / total_finished * 100) if total_finished > 0 else 0.0
                )

                # Per-agent breakdown (only if not filtering by agent)
                by_agent = {}
                if not agent_name:
                    cursor.execute(
                        """SELECT agent_name, status, COUNT(*)
                           FROM observations
                           GROUP BY agent_name, status"""
                    )
                    for agent, status, count in cursor.fetchall():
                        if agent not in by_agent:
                            by_agent[agent] = {
                                "total": 0,
                                "completed": 0,
                                "failed": 0,
                                "canceled": 0,
                            }
                        by_agent[agent][status] = count
                        by_agent[agent]["total"] += count

                # Time range
                cursor.execute(
                    f"SELECT MIN(timestamp), MAX(timestamp) FROM observations {where_clause}",
                    params,
                )
                oldest, newest = cursor.fetchone()

                # Calculate date range in days
                date_range_days = 0
                if oldest and newest:
                    from datetime import datetime

                    oldest_dt = datetime.fromisoformat(oldest)
                    newest_dt = datetime.fromisoformat(newest)
                    date_range_days = (newest_dt - oldest_dt).days

                # Database size
                db_size_mb = self.get_database_size() / (1024 * 1024)

                conn.close()

                return {
                    "total_tasks": total_tasks,
                    "completed": completed,
                    "failed": failed,
                    "canceled": canceled,
                    "success_rate": success_rate,
                    "by_agent": by_agent,
                    "db_size_mb": db_size_mb,
                    "oldest_task": oldest,
                    "newest_task": newest,
                    "date_range_days": date_range_days,
                }
            except sqlite3.Error as e:
                import sys
                print(f"Warning: Failed to get statistics: {e}", file=sys.stderr)
                return {}
