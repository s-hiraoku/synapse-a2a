"""Observation storage for PTY and A2A learning signals."""

from __future__ import annotations

import builtins
import hashlib
import json
import os
import sqlite3
import subprocess
import threading
from pathlib import Path
from typing import Any
from uuid import uuid4

from synapse.paths import get_observation_db_path


def _resolve_project_hash() -> str:
    """Return a stable per-project hash."""
    try:
        remote = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            check=False,
            capture_output=True,
            text=True,
            timeout=1.0,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        remote = ""

    source = remote or str(Path.cwd().resolve())
    return hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]


class ObservationStore:
    """SQLite-backed store for observation events."""

    def __init__(self, db_path: str | None = None, enabled: bool = True) -> None:
        self.enabled = enabled
        self.db_path = os.path.abspath(db_path or get_observation_db_path())
        self._lock = threading.RLock()

        if self.enabled:
            self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        db_file = Path(self.db_path)
        db_file.parent.mkdir(parents=True, exist_ok=True)

        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS observations (
                        id TEXT PRIMARY KEY,
                        event_type TEXT NOT NULL,
                        agent_id TEXT NOT NULL,
                        agent_type TEXT,
                        data TEXT NOT NULL,
                        project_hash TEXT,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_obs_agent ON observations(agent_id)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_obs_event ON observations(event_type)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_obs_project ON observations(project_hash)"
                )
                conn.commit()
            finally:
                conn.close()

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "event_type": row["event_type"],
            "agent_id": row["agent_id"],
            "agent_type": row["agent_type"],
            "data": json.loads(row["data"]),
            "project_hash": row["project_hash"],
            "created_at": row["created_at"],
        }

    def save(
        self,
        *,
        event_type: str,
        agent_id: str,
        agent_type: str | None = None,
        data: dict[str, Any],
        project_hash: str | None = None,
    ) -> dict[str, Any] | None:
        """Persist a single observation row."""
        if not self.enabled:
            return None

        obs_id = str(uuid4())
        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute(
                    """
                    INSERT INTO observations (
                        id, event_type, agent_id, agent_type, data, project_hash
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        obs_id,
                        event_type,
                        agent_id,
                        agent_type,
                        json.dumps(data),
                        project_hash,
                    ),
                )
                conn.commit()
                row = conn.execute(
                    "SELECT * FROM observations WHERE id = ?", (obs_id,)
                ).fetchone()
                return self._row_to_dict(row) if row else None
            finally:
                conn.close()

    def list(
        self,
        *,
        agent_id: str | None = None,
        event_type: str | None = None,
        project_hash: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List observations with optional filters."""
        if not self.enabled:
            return []

        with self._lock:
            conn = self._get_connection()
            try:
                query = "SELECT * FROM observations WHERE 1=1"
                params: list[Any] = []
                if agent_id:
                    query += " AND agent_id = ?"
                    params.append(agent_id)
                if event_type:
                    query += " AND event_type = ?"
                    params.append(event_type)
                if project_hash:
                    query += " AND project_hash = ?"
                    params.append(project_hash)
                query += " ORDER BY created_at DESC, id DESC LIMIT ?"
                params.append(limit)
                rows = conn.execute(query, params).fetchall()
                return [self._row_to_dict(row) for row in rows]
            finally:
                conn.close()

    def search(self, query: str, limit: int = 50) -> builtins.list[dict[str, Any]]:
        """Search observations by event metadata."""
        if not self.enabled:
            return []

        like_query = f"%{query}%"
        with self._lock:
            conn = self._get_connection()
            try:
                rows = conn.execute(
                    """
                    SELECT * FROM observations
                    WHERE event_type LIKE ?
                       OR agent_id LIKE ?
                       OR COALESCE(agent_type, '') LIKE ?
                       OR data LIKE ?
                       OR COALESCE(project_hash, '') LIKE ?
                    ORDER BY created_at DESC, id DESC
                    LIMIT ?
                    """,
                    (
                        like_query,
                        like_query,
                        like_query,
                        like_query,
                        like_query,
                        limit,
                    ),
                ).fetchall()
                return [self._row_to_dict(row) for row in rows]
            finally:
                conn.close()

    def count(
        self,
        *,
        agent_id: str | None = None,
        event_type: str | None = None,
        project_hash: str | None = None,
    ) -> int:
        """Count observations with optional filters."""
        if not self.enabled:
            return 0

        with self._lock:
            conn = self._get_connection()
            try:
                query = "SELECT COUNT(*) FROM observations WHERE 1=1"
                params: list[Any] = []
                if agent_id:
                    query += " AND agent_id = ?"
                    params.append(agent_id)
                if event_type:
                    query += " AND event_type = ?"
                    params.append(event_type)
                if project_hash:
                    query += " AND project_hash = ?"
                    params.append(project_hash)
                value = conn.execute(query, params).fetchone()
                return int(value[0]) if value else 0
            finally:
                conn.close()

    def clear(
        self,
        *,
        agent_id: str | None = None,
        event_type: str | None = None,
        project_hash: str | None = None,
    ) -> int:
        """Delete observations and return number of removed rows."""
        if not self.enabled:
            return 0

        with self._lock:
            conn = self._get_connection()
            try:
                query = "DELETE FROM observations WHERE 1=1"
                params: list[Any] = []
                if agent_id:
                    query += " AND agent_id = ?"
                    params.append(agent_id)
                if event_type:
                    query += " AND event_type = ?"
                    params.append(event_type)
                if project_hash:
                    query += " AND project_hash = ?"
                    params.append(project_hash)
                cursor = conn.execute(query, params)
                conn.commit()
                return int(cursor.rowcount)
            finally:
                conn.close()


class ObservationCollector:
    """Typed interface for writing observation events."""

    def __init__(
        self,
        store: ObservationStore | None = None,
        *,
        db_path: str | None = None,
        enabled: bool = True,
        project_hash: str | None = None,
    ) -> None:
        self.enabled = enabled
        self.store = store or ObservationStore(db_path=db_path, enabled=enabled)
        self.project_hash = project_hash or _resolve_project_hash()

    @classmethod
    def from_env(cls, db_path: str | None = None) -> ObservationCollector:
        """Create a collector from environment variables."""
        env_enabled = os.environ.get("SYNAPSE_OBSERVATION_ENABLED", "true").lower()
        enabled = env_enabled in ("true", "1")
        return cls(db_path=db_path, enabled=enabled)

    def _record(
        self,
        event_type: str,
        agent_id: str,
        agent_type: str | None,
        data: dict[str, Any],
    ) -> dict[str, Any] | None:
        if not self.enabled:
            return None

        return self.store.save(
            event_type=event_type,
            agent_id=agent_id,
            agent_type=agent_type,
            data=data,
            project_hash=self.project_hash,
        )

    def record_task_received(
        self,
        agent_id: str,
        agent_type: str | None,
        message: str,
        sender: str | None,
        priority: int,
    ) -> dict[str, Any] | None:
        return self._record(
            "task_received",
            agent_id,
            agent_type,
            {
                "message": message,
                "sender": sender,
                "priority": priority,
            },
        )

    def record_task_completed(
        self,
        agent_id: str,
        agent_type: str | None,
        task_id: str,
        duration: float | None,
        status: str,
        output_summary: str,
    ) -> dict[str, Any] | None:
        return self._record(
            "task_completed",
            agent_id,
            agent_type,
            {
                "task_id": task_id,
                "duration": duration,
                "status": status,
                "output_summary": output_summary,
            },
        )

    def record_error(
        self,
        agent_id: str,
        agent_type: str | None,
        error_type: str,
        error_message: str,
        recovery_action: str | None,
    ) -> dict[str, Any] | None:
        return self._record(
            "error",
            agent_id,
            agent_type,
            {
                "error_type": error_type,
                "error_message": error_message,
                "recovery_action": recovery_action,
            },
        )

    def record_status_change(
        self,
        agent_id: str,
        agent_type: str | None,
        from_status: str,
        to_status: str,
        trigger: str,
    ) -> dict[str, Any] | None:
        return self._record(
            "status_change",
            agent_id,
            agent_type,
            {
                "from_status": from_status,
                "to_status": to_status,
                "trigger": trigger,
            },
        )

    def record_file_operation(
        self,
        agent_id: str,
        agent_type: str | None,
        file_path: str,
        operation_type: str,
    ) -> dict[str, Any] | None:
        return self._record(
            "file_operation",
            agent_id,
            agent_type,
            {
                "file_path": file_path,
                "operation_type": operation_type,
            },
        )
