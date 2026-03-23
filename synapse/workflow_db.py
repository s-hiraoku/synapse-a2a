"""SQLite-backed persistent storage for workflow execution history.

Follows the same patterns as task_board.py:
- SQLite with WAL mode for concurrent reads
- threading.RLock for write serialization
- Row factory for dict-like access

Storage: .synapse/workflow_runs.db
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = ".synapse/workflow_runs.db"


class WorkflowRunDB:
    """Persistent storage for workflow run history."""

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = str(Path(db_path or DEFAULT_DB_PATH).expanduser().resolve())
        self._lock = threading.RLock()
        self._init_db()

    # ------------------------------------------------------------------
    # Connection helpers
    # ------------------------------------------------------------------

    def _get_connection(self) -> sqlite3.Connection:
        """Get a SQLite connection with WAL mode."""
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        return conn

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _init_db(self) -> None:
        """Create tables and indexes if they don't exist."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS runs (
                        run_id          TEXT PRIMARY KEY,
                        workflow_name   TEXT NOT NULL,
                        status          TEXT NOT NULL DEFAULT 'running',
                        started_at      REAL NOT NULL,
                        completed_at    REAL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS run_steps (
                        run_id          TEXT NOT NULL,
                        step_index      INTEGER NOT NULL,
                        target          TEXT NOT NULL,
                        message         TEXT NOT NULL,
                        status          TEXT NOT NULL DEFAULT 'pending',
                        started_at      REAL,
                        completed_at    REAL,
                        output          TEXT,
                        error           TEXT,
                        PRIMARY KEY (run_id, step_index),
                        FOREIGN KEY (run_id) REFERENCES runs(run_id)
                            ON DELETE CASCADE
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_runs_started ON runs(started_at)"
                )
                # Mark any leftover "running" rows as failed (ghost runs
                # from a previous process that crashed before completing).
                conn.execute(
                    "UPDATE runs SET status = 'failed' WHERE status = 'running'"
                )
                conn.commit()
            finally:
                conn.close()

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def save_run(self, run_dict: dict[str, Any]) -> None:
        """Insert a new workflow run with its steps.

        *run_dict* uses the same shape as ``WorkflowRun.to_dict()``
        but with full (non-truncated) step output.
        """
        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO runs "
                    "(run_id, workflow_name, status, started_at, completed_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        run_dict["run_id"],
                        run_dict["workflow_name"],
                        run_dict["status"],
                        run_dict["started_at"],
                        run_dict.get("completed_at"),
                    ),
                )
                for step in run_dict.get("steps", []):
                    conn.execute(
                        "INSERT OR REPLACE INTO run_steps "
                        "(run_id, step_index, target, message, "
                        " status, started_at, completed_at, output, error) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            run_dict["run_id"],
                            step["step_index"],
                            step["target"],
                            step["message"],
                            step["status"],
                            step.get("started_at"),
                            step.get("completed_at"),
                            step.get("output"),
                            step.get("error"),
                        ),
                    )
                conn.commit()
            finally:
                conn.close()

    def update_run_status(
        self,
        run_id: str,
        status: str,
        completed_at: float | None = None,
    ) -> None:
        """Update the status (and optional completed_at) of a run."""
        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute(
                    "UPDATE runs SET status = ?, completed_at = ? WHERE run_id = ?",
                    (status, completed_at, run_id),
                )
                conn.commit()
            finally:
                conn.close()

    def update_step(self, run_id: str, step: dict[str, Any]) -> None:
        """Update a single step's status, timestamps, output, and error."""
        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute(
                    "UPDATE run_steps SET "
                    "status = ?, started_at = ?, completed_at = ?, "
                    "output = ?, error = ? "
                    "WHERE run_id = ? AND step_index = ?",
                    (
                        step["status"],
                        step.get("started_at"),
                        step.get("completed_at"),
                        step.get("output"),
                        step.get("error"),
                        run_id,
                        step["step_index"],
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        """Load a single run with its steps. Returns None if not found."""
        with self._lock:
            conn = self._get_connection()
            try:
                row = conn.execute(
                    "SELECT * FROM runs WHERE run_id = ?", (run_id,)
                ).fetchone()
                if row is None:
                    return None
                step_rows = conn.execute(
                    "SELECT * FROM run_steps WHERE run_id = ? ORDER BY step_index",
                    (run_id,),
                ).fetchall()
                return self._build_run_dict(
                    row, [self._step_row_to_dict(s) for s in step_rows]
                )
            finally:
                conn.close()

    def get_runs(self, limit: int = 200) -> list[dict[str, Any]]:
        """Return runs ordered by most recent first."""
        with self._lock:
            conn = self._get_connection()
            try:
                rows = conn.execute(
                    "SELECT * FROM runs ORDER BY started_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
                if not rows:
                    return []
                # Batch-fetch all steps for the selected runs (avoids N+1)
                run_ids = [r["run_id"] for r in rows]
                placeholders = ",".join("?" * len(run_ids))
                all_steps = conn.execute(
                    f"SELECT * FROM run_steps WHERE run_id IN ({placeholders}) "
                    "ORDER BY step_index",
                    run_ids,
                ).fetchall()
                steps_by_run: dict[str, list[dict[str, Any]]] = {}
                for s in all_steps:
                    steps_by_run.setdefault(s["run_id"], []).append(
                        self._step_row_to_dict(s)
                    )
                return [
                    self._build_run_dict(r, steps_by_run.get(r["run_id"], []))
                    for r in rows
                ]
            finally:
                conn.close()

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def delete_runs_older_than(self, cutoff_timestamp: float) -> int:
        """Delete runs started before *cutoff_timestamp*.

        Returns the number of deleted *runs* (not steps).
        Steps are removed via ON DELETE CASCADE.
        """
        with self._lock:
            conn = self._get_connection()
            try:
                cursor = conn.execute(
                    "DELETE FROM runs WHERE started_at < ?",
                    (cutoff_timestamp,),
                )
                count = cursor.rowcount
                conn.commit()
                return count
            finally:
                conn.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _step_row_to_dict(s: sqlite3.Row) -> dict[str, Any]:
        """Convert a run_steps row to a plain dict."""
        return {
            "step_index": s["step_index"],
            "target": s["target"],
            "message": s["message"],
            "status": s["status"],
            "started_at": s["started_at"],
            "completed_at": s["completed_at"],
            "output": s["output"],
            "error": s["error"],
        }

    @staticmethod
    def _build_run_dict(
        row: sqlite3.Row, steps: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Assemble a full run dict from a runs row and pre-fetched steps."""
        return {
            "run_id": row["run_id"],
            "workflow_name": row["workflow_name"],
            "status": row["status"],
            "started_at": row["started_at"],
            "completed_at": row["completed_at"],
            "steps": steps,
        }
