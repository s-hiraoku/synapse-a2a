"""Shared Memory for cross-agent knowledge sharing.

Provides a project-local SQLite-based knowledge base where agents can
save, search, and share learned knowledge across sessions.

Storage: .synapse/memory.db (SQLite with WAL mode)
Pattern: follows task_board.py conventions.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from collections import Counter
from pathlib import Path
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = ".synapse/memory.db"


class SharedMemory:
    """Project-local shared memory for cross-agent knowledge sharing.

    Provides CRUD operations on a SQLite-backed knowledge base
    with UPSERT semantics on key, tag-based filtering, and
    full-text search across key/content/tags.
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

    @classmethod
    def from_env(cls, db_path: str | None = None) -> SharedMemory:
        """Create SharedMemory from environment variables.

        Environment variables:
        - SYNAPSE_SHARED_MEMORY_ENABLED: "true"/"1" to enable
        - SYNAPSE_SHARED_MEMORY_DB_PATH: Path to SQLite database file
        """
        env_db_path = os.environ.get("SYNAPSE_SHARED_MEMORY_DB_PATH", "").strip()
        resolved_db_path = env_db_path or db_path

        env_enabled = os.environ.get("SYNAPSE_SHARED_MEMORY_ENABLED", "true").lower()
        enabled = env_enabled in ("true", "1")

        return cls(db_path=resolved_db_path, enabled=enabled)

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        """Convert a SQLite Row to a memory dictionary."""
        return {
            "id": row["id"],
            "key": row["key"],
            "content": row["content"],
            "author": row["author"],
            "tags": json.loads(row["tags"] or "[]"),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _init_db(self) -> None:
        """Initialize database schema."""
        db_file = Path(self.db_path)
        db_file.parent.mkdir(parents=True, exist_ok=True)

        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS memories (
                        id         TEXT PRIMARY KEY,
                        key        TEXT NOT NULL UNIQUE,
                        content    TEXT NOT NULL,
                        author     TEXT NOT NULL,
                        tags       TEXT DEFAULT '[]',
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_memory_key ON memories(key)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_memory_author ON memories(author)"
                )
                conn.commit()
            finally:
                conn.close()

    def save(
        self,
        key: str,
        content: str,
        author: str,
        tags: list[str] | None = None,
    ) -> dict[str, Any] | None:
        """Save or update a memory entry (UPSERT on key).

        Args:
            key: Unique key for this memory (e.g. "auth-pattern").
            content: Memory content text.
            author: Agent ID of the author.
            tags: Optional list of tags.

        Returns:
            The saved memory dict, or None if disabled.
        """
        if not self.enabled:
            return None

        memory_id = str(uuid4())
        tags_json = json.dumps(tags or [])

        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute(
                    """
                    INSERT INTO memories (id, key, content, author, tags)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET
                        content = excluded.content,
                        author = excluded.author,
                        tags = excluded.tags,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (memory_id, key, content, author, tags_json),
                )
                conn.commit()

                row = conn.execute(
                    "SELECT * FROM memories WHERE key = ?", (key,)
                ).fetchone()
                return self._row_to_dict(row) if row else None
            finally:
                conn.close()

    def get(self, id_or_key: str) -> dict[str, Any] | None:
        """Get a memory by ID or key.

        Args:
            id_or_key: UUID or key string.

        Returns:
            Memory dict or None if not found.
        """
        if not self.enabled:
            return None

        with self._lock:
            conn = self._get_connection()
            try:
                row = conn.execute(
                    "SELECT * FROM memories WHERE id = ? OR key = ?",
                    (id_or_key, id_or_key),
                ).fetchone()
                return self._row_to_dict(row) if row else None
            finally:
                conn.close()

    def list_memories(
        self,
        author: str | None = None,
        tags: list[str] | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List memories with optional filters.

        Args:
            author: Filter by author agent ID.
            tags: Filter by tags (memories containing any of these tags).
            limit: Maximum number of results.

        Returns:
            List of memory dicts.
        """
        if not self.enabled:
            return []

        with self._lock:
            conn = self._get_connection()
            try:
                query = "SELECT * FROM memories WHERE 1=1"
                params: list[Any] = []

                if author:
                    query += " AND author = ?"
                    params.append(author)

                if tags:
                    condition = "EXISTS (SELECT 1 FROM json_each(tags) WHERE value = ?)"
                    tag_conditions = " OR ".join([condition] * len(tags))
                    query += f" AND ({tag_conditions})"
                    params.extend(tags)

                query += " ORDER BY updated_at DESC LIMIT ?"
                params.append(limit)

                rows = conn.execute(query, params).fetchall()
                return [self._row_to_dict(row) for row in rows]
            finally:
                conn.close()

    def search(self, query: str, limit: int = 100) -> list[dict[str, Any]]:
        """Search memories by key, content, or tags.

        Args:
            query: Search query string (LIKE matching).
            limit: Maximum number of results.

        Returns:
            List of matching memory dicts.
        """
        if not self.enabled:
            return []
        if limit <= 0:
            msg = "limit must be greater than 0"
            raise ValueError(msg)

        with self._lock:
            conn = self._get_connection()
            try:
                like_query = f"%{query}%"
                rows = conn.execute(
                    """
                    SELECT * FROM memories
                    WHERE key LIKE ? OR content LIKE ? OR tags LIKE ?
                    ORDER BY updated_at DESC LIMIT ?
                    """,
                    (like_query, like_query, like_query, limit),
                ).fetchall()
                return [self._row_to_dict(row) for row in rows]
            finally:
                conn.close()

    def delete(self, id_or_key: str) -> bool:
        """Delete a memory by ID or key.

        Args:
            id_or_key: UUID or key string.

        Returns:
            True if deleted, False if not found.
        """
        if not self.enabled:
            return False

        with self._lock:
            conn = self._get_connection()
            try:
                cursor = conn.execute(
                    "DELETE FROM memories WHERE id = ? OR key = ?",
                    (id_or_key, id_or_key),
                )
                conn.commit()
                return cursor.rowcount > 0
            finally:
                conn.close()

    def stats(self) -> dict[str, Any]:
        """Get memory statistics.

        Returns:
            Dict with total count, per-author counts, and per-tag counts.
        """
        if not self.enabled:
            return {"total": 0, "by_author": {}, "by_tag": {}}

        with self._lock:
            conn = self._get_connection()
            try:
                total = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]

                author_rows = conn.execute(
                    "SELECT author, COUNT(*) as cnt FROM memories GROUP BY author"
                ).fetchall()
                by_author = {row["author"]: row["cnt"] for row in author_rows}

                tag_rows = conn.execute("SELECT tags FROM memories").fetchall()
                tag_counter: Counter[str] = Counter()
                for row in tag_rows:
                    tag_counter.update(json.loads(row["tags"] or "[]"))
                by_tag = dict(tag_counter)

                return {
                    "total": total,
                    "by_author": by_author,
                    "by_tag": by_tag,
                }
            finally:
                conn.close()
