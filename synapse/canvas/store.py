"""CanvasStore — SQLite-backed card storage for Synapse Canvas.

Storage: .synapse/canvas.db (project-local, WAL mode)
Cards are ephemeral: cleared on server restart, expire after TTL.
Follows shared_memory.py / task_board.py conventions.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from uuid import uuid4

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = ".synapse/canvas.db"
DEFAULT_CARD_TTL = 3600  # 1 hour


class CanvasStore:
    """SQLite-backed card storage with TTL, upsert, and ownership."""

    def __init__(
        self,
        db_path: str | None = None,
        card_ttl: int = DEFAULT_CARD_TTL,
    ) -> None:
        self.db_path = os.path.abspath(os.path.expanduser(db_path or DEFAULT_DB_PATH))
        self.card_ttl = card_ttl
        self._lock = threading.RLock()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with self._lock:
            conn = self._get_connection()
            try:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS cards (
                        id          TEXT PRIMARY KEY,
                        card_id     TEXT UNIQUE,
                        agent_id    TEXT NOT NULL,
                        agent_name  TEXT,
                        type        TEXT NOT NULL DEFAULT 'render',
                        content     TEXT NOT NULL,
                        title       TEXT,
                        pinned      INTEGER DEFAULT 0,
                        tags        TEXT,
                        template    TEXT DEFAULT '',
                        template_data TEXT DEFAULT '',
                        expires_at  DATETIME,
                        created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP
                    );
                    CREATE INDEX IF NOT EXISTS idx_cards_card_id ON cards(card_id);
                    CREATE INDEX IF NOT EXISTS idx_cards_agent ON cards(agent_id);
                    CREATE INDEX IF NOT EXISTS idx_cards_expires ON cards(expires_at);
                    """
                )
                conn.commit()

                # Migration: add template columns to existing DBs
                try:
                    conn.execute(
                        "ALTER TABLE cards ADD COLUMN template TEXT DEFAULT ''"
                    )
                    conn.execute(
                        "ALTER TABLE cards ADD COLUMN template_data TEXT DEFAULT ''"
                    )
                    conn.commit()
                except sqlite3.OperationalError:
                    pass  # Columns already exist
            finally:
                conn.close()

    def _now_utc(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")

    def _expires_at(self, pinned: bool) -> str | None:
        if pinned:
            return None
        dt = datetime.now(timezone.utc) + timedelta(seconds=self.card_ttl)
        return dt.strftime("%Y-%m-%d %H:%M:%S.%f")

    def _row_to_dict(self, row: sqlite3.Row) -> dict:
        d = dict(row)
        if d.get("tags"):
            d["tags"] = json.loads(d["tags"])
        else:
            d["tags"] = []
        # Template fields
        d["template"] = d.get("template") or ""
        td_raw = d.get("template_data") or ""
        if td_raw:
            try:
                d["template_data"] = json.loads(td_raw)
            except (json.JSONDecodeError, TypeError):
                d["template_data"] = {}
        else:
            d["template_data"] = {}
        return d

    def add_card(
        self,
        agent_id: str,
        content: str,
        title: str = "",
        agent_name: str | None = None,
        card_id: str | None = None,
        card_type: str = "render",
        pinned: bool = False,
        tags: list[str] | None = None,
        template: str = "",
        template_data: dict | None = None,
    ) -> dict:
        """Add a new card. Returns the created card as dict."""
        internal_id = str(uuid4())[:8]
        if card_id is None:
            card_id = str(uuid4())[:8]

        now = self._now_utc()
        expires = self._expires_at(pinned)
        tags_json = json.dumps(tags, ensure_ascii=False) if tags else None
        td_json = json.dumps(template_data, ensure_ascii=False) if template_data else ""

        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute(
                    """
                    INSERT INTO cards (id, card_id, agent_id, agent_name, type,
                                       content, title, pinned, tags,
                                       template, template_data,
                                       expires_at, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        internal_id,
                        card_id,
                        agent_id,
                        agent_name,
                        card_type,
                        content,
                        title,
                        1 if pinned else 0,
                        tags_json,
                        template,
                        td_json,
                        expires,
                        now,
                        now,
                    ),
                )
                conn.commit()

                row = conn.execute(
                    "SELECT * FROM cards WHERE id = ?", (internal_id,)
                ).fetchone()
                return self._row_to_dict(row)
            finally:
                conn.close()

    def upsert_card(
        self,
        card_id: str,
        agent_id: str,
        content: str,
        title: str = "",
        agent_name: str | None = None,
        card_type: str = "render",
        pinned: bool = False,
        tags: list[str] | None = None,
        template: str = "",
        template_data: dict | None = None,
    ) -> dict | None:
        """Create or update a card by card_id. Returns None if ownership check fails."""
        with self._lock:
            conn = self._get_connection()
            try:
                existing = conn.execute(
                    "SELECT * FROM cards WHERE card_id = ?", (card_id,)
                ).fetchone()

                if existing is not None:
                    # Ownership check
                    if existing["agent_id"] != agent_id:
                        return None

                    now = self._now_utc()
                    expires = self._expires_at(pinned)
                    tags_json = (
                        json.dumps(tags, ensure_ascii=False)
                        if tags
                        else existing["tags"]
                    )
                    td_json = (
                        json.dumps(template_data, ensure_ascii=False)
                        if template_data is not None
                        else existing["template_data"]
                    )

                    conn.execute(
                        """
                        UPDATE cards SET content = ?, title = ?, pinned = ?,
                               tags = ?, template = ?, template_data = ?,
                               expires_at = ?, updated_at = ?,
                               agent_name = COALESCE(?, agent_name)
                        WHERE card_id = ?
                        """,
                        (
                            content,
                            title,
                            1 if pinned else 0,
                            tags_json,
                            template or existing["template"],
                            td_json,
                            expires,
                            now,
                            agent_name,
                            card_id,
                        ),
                    )
                    conn.commit()

                    row = conn.execute(
                        "SELECT * FROM cards WHERE card_id = ?", (card_id,)
                    ).fetchone()
                    return self._row_to_dict(row)
                else:
                    # Create new
                    return self.add_card(
                        agent_id=agent_id,
                        content=content,
                        title=title,
                        agent_name=agent_name,
                        card_id=card_id,
                        card_type=card_type,
                        pinned=pinned,
                        tags=tags,
                        template=template,
                        template_data=template_data,
                    )
            finally:
                conn.close()

    def get_card(self, card_id: str) -> dict | None:
        """Retrieve a card by card_id."""
        with self._lock:
            conn = self._get_connection()
            try:
                row = conn.execute(
                    "SELECT * FROM cards WHERE card_id = ?", (card_id,)
                ).fetchone()
                if row is None:
                    return None
                return self._row_to_dict(row)
            finally:
                conn.close()

    def list_cards(
        self,
        agent_id: str | None = None,
        search: str | None = None,
        content_type: str | None = None,
    ) -> list[dict]:
        """List cards with optional filters. Excludes expired cards."""
        now = self._now_utc()
        conditions = ["(expires_at IS NULL OR expires_at > ?)"]
        params: list[str] = [now]

        if agent_id:
            conditions.append("agent_id = ?")
            params.append(agent_id)

        if search:
            conditions.append("title LIKE ?")
            params.append(f"%{search}%")

        if content_type:
            # Search for format in JSON content (handles both with/without spaces)
            conditions.append("(content LIKE ? OR content LIKE ?)")
            params.append(f'%"format": "{content_type}"%')
            params.append(f'%"format":"{content_type}"%')

        where = " AND ".join(conditions)
        query = f"SELECT * FROM cards WHERE {where} ORDER BY updated_at DESC"

        with self._lock:
            conn = self._get_connection()
            try:
                rows = conn.execute(query, params).fetchall()
                return [self._row_to_dict(row) for row in rows]
            finally:
                conn.close()

    def delete_card(self, card_id: str, agent_id: str) -> bool:
        """Delete a card. Returns False if not found or ownership check fails."""
        with self._lock:
            conn = self._get_connection()
            try:
                existing = conn.execute(
                    "SELECT agent_id FROM cards WHERE card_id = ?", (card_id,)
                ).fetchone()

                if existing is None:
                    return False

                if existing["agent_id"] != agent_id:
                    return False

                conn.execute("DELETE FROM cards WHERE card_id = ?", (card_id,))
                conn.commit()
                return True
            finally:
                conn.close()

    def clear_all(self, agent_id: str | None = None) -> int:
        """Clear all cards or cards for a specific agent. Returns count deleted."""
        with self._lock:
            conn = self._get_connection()
            try:
                if agent_id:
                    cursor = conn.execute(
                        "DELETE FROM cards WHERE agent_id = ?", (agent_id,)
                    )
                else:
                    cursor = conn.execute("DELETE FROM cards")
                conn.commit()
                return cursor.rowcount
            finally:
                conn.close()

    def list_tips(self) -> list[dict]:
        """List cards tagged with 'tip'. Returns list of card dicts."""
        now = self._now_utc()
        with self._lock:
            conn = self._get_connection()
            try:
                rows = conn.execute(
                    "SELECT * FROM cards "
                    "WHERE tags LIKE '%\"tip\"%' "
                    "AND (expires_at IS NULL OR expires_at > ?) "
                    "ORDER BY updated_at DESC",
                    (now,),
                ).fetchall()
                return [self._row_to_dict(row) for row in rows]
            finally:
                conn.close()

    def consume_tip(self, card_id: str) -> bool:
        """Delete a tip card by ID (no ownership check). Returns True if deleted."""
        with self._lock:
            conn = self._get_connection()
            try:
                cursor = conn.execute(
                    "DELETE FROM cards WHERE card_id = ? AND tags LIKE '%\"tip\"%'",
                    (card_id,),
                )
                conn.commit()
                return cursor.rowcount > 0
            finally:
                conn.close()

    def cleanup_expired(self) -> int:
        """Remove expired cards from the database. Returns count removed."""
        now = self._now_utc()
        with self._lock:
            conn = self._get_connection()
            try:
                cursor = conn.execute(
                    "DELETE FROM cards WHERE expires_at IS NOT NULL AND expires_at <= ?",
                    (now,),
                )
                conn.commit()
                return cursor.rowcount
            finally:
                conn.close()

    def count(self) -> int:
        """Return total number of non-expired cards."""
        now = self._now_utc()
        with self._lock:
            conn = self._get_connection()
            try:
                row = conn.execute(
                    "SELECT COUNT(*) FROM cards WHERE expires_at IS NULL OR expires_at > ?",
                    (now,),
                ).fetchone()
                return int(row[0])
            finally:
                conn.close()
