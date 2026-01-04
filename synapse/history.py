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
