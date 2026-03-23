"""Instinct storage for learned project and global patterns."""

from __future__ import annotations

import builtins
import json
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any
from uuid import uuid4

DEFAULT_DB_PATH = ".synapse/instincts.db"


class InstinctStore:
    """SQLite-backed store for learned instincts."""

    def __init__(self, db_path: str | None = None, enabled: bool = True) -> None:
        self.enabled = enabled
        self.db_path = os.path.abspath(os.path.expanduser(db_path or DEFAULT_DB_PATH))
        self._lock = threading.RLock()

        if self.enabled:
            self._init_db()

    @classmethod
    def from_env(cls, db_path: str | None = None) -> InstinctStore:
        """Create an instinct store from environment variables."""
        env_db_path = os.environ.get("SYNAPSE_INSTINCT_DB_PATH", "").strip()
        resolved_db_path = env_db_path or db_path
        return cls(db_path=resolved_db_path, enabled=True)

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
                    CREATE TABLE IF NOT EXISTS instincts (
                        id TEXT PRIMARY KEY,
                        trigger TEXT NOT NULL,
                        action TEXT NOT NULL,
                        confidence REAL DEFAULT 0.3,
                        scope TEXT DEFAULT 'project',
                        domain TEXT,
                        source_observations TEXT,
                        project_hash TEXT,
                        agent_id TEXT,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_inst_scope ON instincts(scope)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_inst_domain ON instincts(domain)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_inst_confidence ON instincts(confidence)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_inst_project ON instincts(project_hash)"
                )
                conn.commit()
            finally:
                conn.close()

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "trigger": row["trigger"],
            "action": row["action"],
            "confidence": row["confidence"],
            "scope": row["scope"],
            "domain": row["domain"],
            "source_observations": json.loads(row["source_observations"] or "[]"),
            "project_hash": row["project_hash"],
            "agent_id": row["agent_id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def save(
        self,
        trigger: str,
        action: str,
        confidence: float = 0.3,
        scope: str = "project",
        domain: str | None = None,
        source_observations: list[str] | None = None,
        project_hash: str | None = None,
        agent_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Insert a new instinct row."""
        if not self.enabled:
            return None

        instinct_id = str(uuid4())
        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute(
                    """
                    INSERT INTO instincts (
                        id, trigger, action, confidence, scope, domain,
                        source_observations, project_hash, agent_id
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        instinct_id,
                        trigger,
                        action,
                        confidence,
                        scope,
                        domain,
                        json.dumps(source_observations or []),
                        project_hash,
                        agent_id,
                    ),
                )
                conn.commit()
                row = conn.execute(
                    "SELECT * FROM instincts WHERE id = ?", (instinct_id,)
                ).fetchone()
                return self._row_to_dict(row) if row else None
            finally:
                conn.close()

    def get(self, instinct_id: str) -> dict[str, Any] | None:
        """Get an instinct by ID."""
        if not self.enabled:
            return None

        with self._lock:
            conn = self._get_connection()
            try:
                row = conn.execute(
                    "SELECT * FROM instincts WHERE id = ?", (instinct_id,)
                ).fetchone()
                return self._row_to_dict(row) if row else None
            finally:
                conn.close()

    def list(
        self,
        scope: str | None = None,
        domain: str | None = None,
        min_confidence: float | None = None,
        project_hash: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List instincts with optional filters."""
        if not self.enabled:
            return []

        with self._lock:
            conn = self._get_connection()
            try:
                query = "SELECT * FROM instincts WHERE 1=1"
                params: list[Any] = []
                if scope:
                    query += " AND scope = ?"
                    params.append(scope)
                if domain:
                    query += " AND domain = ?"
                    params.append(domain)
                if min_confidence is not None:
                    query += " AND confidence >= ?"
                    params.append(min_confidence)
                if project_hash:
                    query += " AND project_hash = ?"
                    params.append(project_hash)
                query += " ORDER BY confidence DESC, updated_at DESC LIMIT ?"
                params.append(limit)
                rows = conn.execute(query, params).fetchall()
                return [self._row_to_dict(row) for row in rows]
            finally:
                conn.close()

    def find_by_trigger_action(
        self, trigger: str, action: str, project_hash: str | None = None
    ) -> dict[str, Any] | None:
        """Find an instinct by its semantic key."""
        if not self.enabled:
            return None

        with self._lock:
            conn = self._get_connection()
            try:
                query = "SELECT * FROM instincts WHERE trigger = ? AND action = ?"
                params: list[Any] = [trigger, action]
                if project_hash:
                    query += " AND project_hash = ?"
                    params.append(project_hash)
                query += " ORDER BY updated_at DESC LIMIT 1"
                row = conn.execute(query, params).fetchone()
                return self._row_to_dict(row) if row else None
            finally:
                conn.close()

    def update_confidence(self, instinct_id: str, new_confidence: float) -> bool:
        """Update confidence for an instinct."""
        if not self.enabled:
            return False

        with self._lock:
            conn = self._get_connection()
            try:
                cursor = conn.execute(
                    """
                    UPDATE instincts
                    SET confidence = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (new_confidence, instinct_id),
                )
                conn.commit()
                return cursor.rowcount > 0
            finally:
                conn.close()

    def update_sources(
        self, instinct_id: str, source_observations: builtins.list[str]
    ) -> bool:
        """Update source observations for an instinct."""
        if not self.enabled:
            return False

        with self._lock:
            conn = self._get_connection()
            try:
                cursor = conn.execute(
                    """
                    UPDATE instincts
                    SET source_observations = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (json.dumps(source_observations), instinct_id),
                )
                conn.commit()
                return cursor.rowcount > 0
            finally:
                conn.close()

    def promote(self, instinct_id: str) -> bool:
        """Promote a project instinct to global scope."""
        if not self.enabled:
            return False

        with self._lock:
            conn = self._get_connection()
            try:
                cursor = conn.execute(
                    """
                    UPDATE instincts
                    SET scope = 'global', updated_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND scope = 'project'
                    """,
                    (instinct_id,),
                )
                conn.commit()
                return cursor.rowcount > 0
            finally:
                conn.close()

    def delete(self, instinct_id: str) -> bool:
        """Delete an instinct by ID."""
        if not self.enabled:
            return False

        with self._lock:
            conn = self._get_connection()
            try:
                cursor = conn.execute(
                    "DELETE FROM instincts WHERE id = ?",
                    (instinct_id,),
                )
                conn.commit()
                return cursor.rowcount > 0
            finally:
                conn.close()

    def count(
        self,
        scope: str | None = None,
        domain: str | None = None,
        project_hash: str | None = None,
    ) -> int:
        """Count instincts with optional filters."""
        if not self.enabled:
            return 0

        with self._lock:
            conn = self._get_connection()
            try:
                query = "SELECT COUNT(*) FROM instincts WHERE 1=1"
                params: list[Any] = []
                if scope:
                    query += " AND scope = ?"
                    params.append(scope)
                if domain:
                    query += " AND domain = ?"
                    params.append(domain)
                if project_hash:
                    query += " AND project_hash = ?"
                    params.append(project_hash)
                row = conn.execute(query, params).fetchone()
                return int(row[0]) if row else 0
            finally:
                conn.close()
