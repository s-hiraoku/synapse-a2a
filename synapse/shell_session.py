"""SQLite-backed persistence for interactive shell sessions."""

from __future__ import annotations

import os
import sqlite3
import threading
from pathlib import Path
from typing import Any
from uuid import uuid4

DEFAULT_DB_PATH = "~/.synapse/shell_sessions.db"


class ShellSessionStore:
    """SQLite-backed shell session persistence."""

    def __init__(self, db_path: str | None = None) -> None:
        env_db_path = os.environ.get("SYNAPSE_SHELL_SESSION_DB_PATH", "").strip()
        resolved = env_db_path or db_path or DEFAULT_DB_PATH
        self.db_path = os.path.abspath(os.path.expanduser(resolved))
        self._lock = threading.RLock()
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
                    CREATE TABLE IF NOT EXISTS sessions (
                        id TEXT PRIMARY KEY,
                        name TEXT,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS session_entries (
                        id TEXT PRIMARY KEY,
                        session_id TEXT NOT NULL REFERENCES sessions(id),
                        role TEXT NOT NULL,
                        content TEXT NOT NULL,
                        agent_target TEXT,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_entry_session "
                    "ON session_entries(session_id)"
                )
                conn.commit()
            finally:
                conn.close()

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        return dict(row)

    def create_session(self, name: str | None = None) -> dict[str, Any]:
        """Create and return a new shell session."""
        session_id = str(uuid4())
        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute(
                    "INSERT INTO sessions (id, name) VALUES (?, ?)",
                    (session_id, name),
                )
                conn.commit()
                row = conn.execute(
                    "SELECT * FROM sessions WHERE id = ?",
                    (session_id,),
                ).fetchone()
                return self._row_to_dict(row) if row else {}
            finally:
                conn.close()

    def add_entry(
        self,
        session_id: str,
        role: str,
        content: str,
        agent_target: str | None = None,
    ) -> dict[str, Any]:
        """Add a user or agent entry to an existing session."""
        entry_id = str(uuid4())
        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute(
                    """
                    INSERT INTO session_entries
                    (id, session_id, role, content, agent_target)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (entry_id, session_id, role, content, agent_target),
                )
                conn.execute(
                    """
                    UPDATE sessions
                    SET updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (session_id,),
                )
                conn.commit()
                row = conn.execute(
                    "SELECT * FROM session_entries WHERE id = ?",
                    (entry_id,),
                ).fetchone()
                return self._row_to_dict(row) if row else {}
            finally:
                conn.close()

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        """Return a session row by ID."""
        with self._lock:
            conn = self._get_connection()
            try:
                row = conn.execute(
                    "SELECT * FROM sessions WHERE id = ?",
                    (session_id,),
                ).fetchone()
                return self._row_to_dict(row) if row else None
            finally:
                conn.close()

    def get_entries(self, session_id: str, limit: int = 100) -> list[dict[str, Any]]:
        """Return chronological entries for a session."""
        with self._lock:
            conn = self._get_connection()
            try:
                rows = conn.execute(
                    """
                    SELECT * FROM session_entries
                    WHERE session_id = ?
                    ORDER BY created_at ASC, rowid ASC
                    LIMIT ?
                    """,
                    (session_id, limit),
                ).fetchall()
                return [self._row_to_dict(row) for row in rows]
            finally:
                conn.close()

    def list_sessions(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return sessions ordered by latest activity."""
        with self._lock:
            conn = self._get_connection()
            try:
                rows = conn.execute(
                    """
                    SELECT * FROM sessions
                    ORDER BY updated_at DESC, created_at DESC, rowid DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
                return [self._row_to_dict(row) for row in rows]
            finally:
                conn.close()

    def save_session_name(self, session_id: str, name: str) -> bool:
        """Update the display name for a session."""
        with self._lock:
            conn = self._get_connection()
            try:
                cursor = conn.execute(
                    """
                    UPDATE sessions
                    SET name = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (name, session_id),
                )
                conn.commit()
                return cursor.rowcount > 0
            finally:
                conn.close()
