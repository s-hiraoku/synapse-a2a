"""File Locking & Modification Tracking for Multi-Agent Safety.

This module provides file-level coordination for multi-agent environments,
preventing race conditions, tracking modifications, and maintaining
context about file changes.

Features:
- File locking with automatic expiration
- Modification tracking with change intent
- Context injection for collaborative awareness
"""

import contextlib
import json
import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class ChangeType(str, Enum):
    """Type of file modification."""

    CREATE = "CREATE"
    MODIFY = "MODIFY"
    DELETE = "DELETE"


class LockStatus(str, Enum):
    """Status of lock acquisition attempt."""

    ACQUIRED = "ACQUIRED"
    ALREADY_LOCKED = "ALREADY_LOCKED"
    RENEWED = "RENEWED"
    FAILED = "FAILED"


class FileSafetyManager:
    """Manages file locking and modification tracking for multi-agent safety.

    This class provides:
    - File locking with automatic expiration to prevent race conditions
    - Modification tracking to maintain history of file changes
    - Context injection to provide modification history during file reads
    - Auto-cleanup of old modification records

    The database schema includes:
    - file_locks: Active locks on files with expiration
    - file_modifications: History of all file changes with intent
    """

    DEFAULT_LOCK_DURATION_SECONDS = 300  # 5 minutes
    DEFAULT_DB_PATH = "~/.synapse/file_safety.db"
    DEFAULT_RETENTION_DAYS = 30  # Default retention period for modification records

    def __init__(
        self,
        db_path: str | None = None,
        enabled: bool = True,
        retention_days: int | None = None,
    ) -> None:
        """Initialize FileSafetyManager.

        Args:
            db_path: Path to SQLite database file. Defaults to ~/.synapse/file_safety.db
            enabled: Whether file safety features are enabled
            retention_days: Number of days to keep modification records (auto-cleanup)
        """
        self.enabled = enabled
        self.db_path = os.path.expanduser(db_path or self.DEFAULT_DB_PATH)
        self.retention_days = retention_days or self.DEFAULT_RETENTION_DAYS
        self._lock = threading.RLock()

        if self.enabled:
            self._init_db()
            # Run auto-cleanup on startup
            self._auto_cleanup()

    @classmethod
    def from_env(cls, db_path: str | None = None) -> "FileSafetyManager":
        """Create FileSafetyManager from environment variables and settings.

        Environment variables (higher priority):
        - SYNAPSE_FILE_SAFETY_ENABLED: "true"/"1" to enable
        - SYNAPSE_FILE_SAFETY_RETENTION_DAYS: Number of days to keep records

        Falls back to .synapse/settings.json if env vars not set.

        Args:
            db_path: Optional path to SQLite database file

        Returns:
            FileSafetyManager instance with settings from env/config
        """
        # Check enabled status
        env_enabled = os.environ.get("SYNAPSE_FILE_SAFETY_ENABLED", "").lower()
        if not env_enabled:
            # Fall back to settings.json
            env_enabled = cls._get_setting(
                "SYNAPSE_FILE_SAFETY_ENABLED", "false"
            ).lower()
        enabled = env_enabled in ("true", "1")

        # Check retention days
        env_retention = os.environ.get("SYNAPSE_FILE_SAFETY_RETENTION_DAYS", "")
        if not env_retention:
            env_retention = cls._get_setting("SYNAPSE_FILE_SAFETY_RETENTION_DAYS", "")

        retention_days = None
        if env_retention:
            with contextlib.suppress(ValueError):
                retention_days = int(env_retention)

        return cls(db_path=db_path, enabled=enabled, retention_days=retention_days)

    @staticmethod
    def _get_setting(key: str, default: str = "") -> str:
        """Get a setting value from .synapse/settings.json."""
        from pathlib import Path

        for settings_path in [
            Path.cwd() / ".synapse" / "settings.json",
            Path.home() / ".synapse" / "settings.json",
        ]:
            if settings_path.exists():
                try:
                    with open(settings_path, encoding="utf-8") as f:
                        data = json.load(f)
                        if "env" in data and key in data["env"]:
                            return str(data["env"][key])
                except (json.JSONDecodeError, OSError):
                    continue
        return default

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

                # Create file_locks table
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS file_locks (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        file_path TEXT NOT NULL UNIQUE,
                        agent_name TEXT NOT NULL,
                        task_id TEXT,
                        locked_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        expires_at DATETIME NOT NULL,
                        intent TEXT
                    )
                    """
                )

                # Create file_modifications table
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS file_modifications (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        task_id TEXT NOT NULL,
                        agent_name TEXT NOT NULL,
                        file_path TEXT NOT NULL,
                        change_type TEXT NOT NULL,
                        affected_lines TEXT,
                        intent TEXT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                        metadata TEXT
                    )
                    """
                )

                # Create indexes for efficient querying
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_locks_file_path ON file_locks(file_path)"
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_locks_expires_at ON file_locks(expires_at)"
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_mods_file_path ON file_modifications(file_path)"
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_mods_task_id ON file_modifications(task_id)"
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_mods_timestamp ON file_modifications(timestamp)"
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_mods_agent_name ON file_modifications(agent_name)"
                )

                conn.commit()
                conn.close()
            except sqlite3.Error as e:
                import sys

                print(
                    f"Warning: Failed to initialize file safety DB: {e}",
                    file=sys.stderr,
                )

    def _auto_cleanup(self) -> None:
        """Automatically clean up old modification records on startup.

        Uses retention_days to determine how old records need to be before deletion.
        This runs silently on startup to keep the database size manageable.
        """
        if not self.enabled or self.retention_days <= 0:
            return

        try:
            deleted = self.cleanup_old_modifications(days=self.retention_days)
            if deleted > 0:
                import sys

                print(
                    f"[File Safety] Auto-cleaned {deleted} modification records "
                    f"older than {self.retention_days} days",
                    file=sys.stderr,
                )

            # Also cleanup expired locks
            self.cleanup_expired_locks()
        except Exception:
            # Silently ignore cleanup errors on startup
            pass

    # ========== File Locking Methods ==========

    def acquire_lock(
        self,
        file_path: str,
        agent_name: str,
        task_id: str | None = None,
        duration_seconds: int | None = None,
        intent: str | None = None,
    ) -> dict[str, Any]:
        """Attempt to acquire a lock on a file.

        Args:
            file_path: Absolute path to the file to lock
            agent_name: Name of the agent requesting the lock
            task_id: Optional task identifier
            duration_seconds: Lock duration in seconds (default: 300)
            intent: Optional description of intended changes

        Returns:
            Dict with keys:
                - status: LockStatus (ACQUIRED, ALREADY_LOCKED, RENEWED)
                - lock_holder: Agent name holding the lock (if ALREADY_LOCKED)
                - expires_at: Lock expiration time (if ACQUIRED or RENEWED)
        """
        if not self.enabled:
            return {"status": LockStatus.ACQUIRED, "expires_at": None}

        duration = duration_seconds or self.DEFAULT_LOCK_DURATION_SECONDS
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=duration)
        normalized_path = self._normalize_path(file_path)

        with self._lock:
            conn = None
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()

                # First, clean up expired locks
                self._cleanup_expired_locks_internal(cursor)

                # Check for existing lock
                cursor.execute(
                    "SELECT agent_name, expires_at FROM file_locks WHERE file_path = ?",
                    (normalized_path,),
                )
                existing = cursor.fetchone()

                if existing:
                    existing_agent, existing_expires = existing
                    if existing_agent == agent_name:
                        # Same agent - renew the lock
                        cursor.execute(
                            """
                            UPDATE file_locks
                            SET expires_at = ?, intent = ?, task_id = ?
                            WHERE file_path = ?
                            """,
                            (
                                expires_at.isoformat(),
                                intent,
                                task_id,
                                normalized_path,
                            ),
                        )
                        conn.commit()
                        return {
                            "status": LockStatus.RENEWED,
                            "expires_at": expires_at.isoformat(),
                        }
                    else:
                        # Different agent holds the lock
                        return {
                            "status": LockStatus.ALREADY_LOCKED,
                            "lock_holder": existing_agent,
                            "expires_at": existing_expires,
                        }

                # No existing lock - acquire it
                cursor.execute(
                    """
                    INSERT INTO file_locks (file_path, agent_name, task_id, expires_at, intent)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        normalized_path,
                        agent_name,
                        task_id,
                        expires_at.isoformat(),
                        intent,
                    ),
                )
                conn.commit()

                return {
                    "status": LockStatus.ACQUIRED,
                    "expires_at": expires_at.isoformat(),
                }

            except sqlite3.Error as e:
                import sys

                print(f"Warning: Failed to acquire lock: {e}", file=sys.stderr)
                return {"status": LockStatus.FAILED, "error": str(e)}
            finally:
                if conn:
                    conn.close()

    def release_lock(self, file_path: str, agent_name: str) -> bool:
        """Release a lock on a file.

        Args:
            file_path: Absolute path to the file
            agent_name: Name of the agent releasing the lock

        Returns:
            True if lock was released, False if not found or not owned by agent
        """
        if not self.enabled:
            return True

        normalized_path = self._normalize_path(file_path)

        with self._lock:
            conn = None
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()

                cursor.execute(
                    "DELETE FROM file_locks WHERE file_path = ? AND agent_name = ?",
                    (normalized_path, agent_name),
                )
                deleted = cursor.rowcount > 0

                conn.commit()
                return deleted

            except sqlite3.Error as e:
                import sys

                print(f"Warning: Failed to release lock: {e}", file=sys.stderr)
                return False
            finally:
                if conn:
                    conn.close()

    def check_lock(self, file_path: str) -> dict[str, Any] | None:
        """Check if a file is locked.

        Args:
            file_path: Absolute path to the file

        Returns:
            Lock info dict if locked, None if not locked.
            Dict contains: agent_name, task_id, locked_at, expires_at, intent
        """
        if not self.enabled:
            return None

        normalized_path = self._normalize_path(file_path)

        with self._lock:
            conn = None
            try:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                # Clean up expired locks first
                self._cleanup_expired_locks_internal(cursor)
                conn.commit()

                cursor.execute(
                    "SELECT * FROM file_locks WHERE file_path = ?",
                    (normalized_path,),
                )
                row = cursor.fetchone()

                if row:
                    return dict(row)
                return None

            except sqlite3.Error as e:
                import sys

                print(f"Warning: Failed to check lock: {e}", file=sys.stderr)
                return None
            finally:
                if conn:
                    conn.close()

    def is_locked_by_other(self, file_path: str, agent_name: str) -> bool:
        """Check if a file is locked by another agent.

        Args:
            file_path: Absolute path to the file
            agent_name: Current agent's name

        Returns:
            True if locked by another agent, False otherwise
        """
        lock_info = self.check_lock(file_path)
        if lock_info is None:
            return False
        return bool(lock_info["agent_name"] != agent_name)

    def list_locks(self, agent_name: str | None = None) -> list[dict[str, Any]]:
        """List all active locks.

        Args:
            agent_name: Optional filter by agent name

        Returns:
            List of lock info dicts
        """
        if not self.enabled:
            return []

        with self._lock:
            conn = None
            try:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                # Clean up expired locks first
                self._cleanup_expired_locks_internal(cursor)
                conn.commit()

                if agent_name:
                    cursor.execute(
                        "SELECT * FROM file_locks WHERE agent_name = ? ORDER BY locked_at DESC",
                        (agent_name,),
                    )
                else:
                    cursor.execute("SELECT * FROM file_locks ORDER BY locked_at DESC")

                rows = cursor.fetchall()

                return [dict(row) for row in rows]

            except sqlite3.Error as e:
                import sys

                print(f"Warning: Failed to list locks: {e}", file=sys.stderr)
                return []
            finally:
                if conn:
                    conn.close()

    def _cleanup_expired_locks_internal(self, cursor: sqlite3.Cursor) -> int:
        """Clean up expired locks (internal, requires cursor).

        Args:
            cursor: Active SQLite cursor

        Returns:
            Number of expired locks removed
        """
        now = datetime.now(timezone.utc).isoformat()
        cursor.execute(
            "DELETE FROM file_locks WHERE expires_at < ?",
            (now,),
        )
        return cursor.rowcount

    def cleanup_expired_locks(self) -> int:
        """Clean up expired locks.

        Returns:
            Number of expired locks removed
        """
        if not self.enabled:
            return 0

        with self._lock:
            conn = None
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()

                removed = self._cleanup_expired_locks_internal(cursor)

                conn.commit()
                return removed

            except sqlite3.Error as e:
                import sys

                print(f"Warning: Failed to cleanup expired locks: {e}", file=sys.stderr)
                return 0
            finally:
                if conn:
                    conn.close()

    # ========== File Modification Tracking Methods ==========

    def record_modification(
        self,
        file_path: str,
        agent_name: str,
        task_id: str,
        change_type: ChangeType | str,
        intent: str | None = None,
        affected_lines: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> int | None:
        """Record a file modification.

        Args:
            file_path: Absolute path to the modified file
            agent_name: Name of the agent making the change
            task_id: Task identifier
            change_type: Type of change (CREATE, MODIFY, DELETE)
            intent: Description of why the change was made
            affected_lines: Line range affected (e.g., "10-25" or "10,15,20")
            metadata: Additional metadata about the change

        Returns:
            ID of the created record, or None on failure
        """
        if not self.enabled:
            return None

        normalized_path = self._normalize_path(file_path)

        # Validate and normalize change_type
        if isinstance(change_type, ChangeType):
            change_type_str = change_type.value
        elif isinstance(change_type, str):
            valid_types = {ct.value for ct in ChangeType}
            if change_type not in valid_types:
                import sys

                print(
                    f"Warning: Invalid change_type: {change_type}. "
                    f"Must be one of {valid_types}",
                    file=sys.stderr,
                )
                return None
            change_type_str = change_type
        else:
            import sys

            print(
                f"Warning: change_type must be ChangeType or str, got {type(change_type)}",
                file=sys.stderr,
            )
            return None

        metadata_json = None
        if metadata:
            with contextlib.suppress(TypeError, ValueError):
                metadata_json = json.dumps(metadata)

        with self._lock:
            conn = None
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()

                cursor.execute(
                    """
                    INSERT INTO file_modifications
                    (task_id, agent_name, file_path, change_type, intent, affected_lines, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        task_id,
                        agent_name,
                        normalized_path,
                        change_type_str,
                        intent,
                        affected_lines,
                        metadata_json,
                    ),
                )

                record_id = cursor.lastrowid
                conn.commit()
                return record_id

            except sqlite3.Error as e:
                import sys

                print(f"Warning: Failed to record modification: {e}", file=sys.stderr)
                return None
            finally:
                if conn:
                    conn.close()

    def get_file_history(
        self,
        file_path: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Get modification history for a specific file.

        Args:
            file_path: Absolute path to the file
            limit: Maximum number of records to return

        Returns:
            List of modification records, newest first
        """
        if not self.enabled:
            return []

        normalized_path = self._normalize_path(file_path)

        with self._lock:
            conn = None
            try:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                cursor.execute(
                    """
                    SELECT * FROM file_modifications
                    WHERE file_path = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                    """,
                    (normalized_path, limit),
                )

                rows = cursor.fetchall()

                return [self._row_to_dict(row) for row in rows]

            except sqlite3.Error as e:
                import sys

                print(f"Warning: Failed to get file history: {e}", file=sys.stderr)
                return []
            finally:
                if conn:
                    conn.close()

    def get_recent_modifications(
        self,
        limit: int = 50,
        agent_name: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get recent file modifications across all files.

        Args:
            limit: Maximum number of records to return
            agent_name: Optional filter by agent name

        Returns:
            List of modification records, newest first
        """
        if not self.enabled:
            return []

        with self._lock:
            conn = None
            try:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                if agent_name:
                    cursor.execute(
                        """
                        SELECT * FROM file_modifications
                        WHERE agent_name = ?
                        ORDER BY timestamp DESC
                        LIMIT ?
                        """,
                        (agent_name, limit),
                    )
                else:
                    cursor.execute(
                        """
                        SELECT * FROM file_modifications
                        ORDER BY timestamp DESC
                        LIMIT ?
                        """,
                        (limit,),
                    )

                rows = cursor.fetchall()

                return [self._row_to_dict(row) for row in rows]

            except sqlite3.Error as e:
                import sys

                print(
                    f"Warning: Failed to get recent modifications: {e}", file=sys.stderr
                )
                return []
            finally:
                if conn:
                    conn.close()

    def get_modifications_by_task(self, task_id: str) -> list[dict[str, Any]]:
        """Get all file modifications for a specific task.

        Args:
            task_id: Task identifier

        Returns:
            List of modification records for the task
        """
        if not self.enabled:
            return []

        with self._lock:
            conn = None
            try:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                cursor.execute(
                    """
                    SELECT * FROM file_modifications
                    WHERE task_id = ?
                    ORDER BY timestamp ASC
                    """,
                    (task_id,),
                )

                rows = cursor.fetchall()

                return [self._row_to_dict(row) for row in rows]

            except sqlite3.Error as e:
                import sys

                print(
                    f"Warning: Failed to get modifications by task: {e}",
                    file=sys.stderr,
                )
                return []
            finally:
                if conn:
                    conn.close()

    # ========== Context Injection Methods ==========

    def get_file_context(self, file_path: str, limit: int = 5) -> str:
        """Get context string for a file to inject during reads.

        This provides agents with awareness of recent modifications
        to the file they are about to read or edit.

        Args:
            file_path: Absolute path to the file
            limit: Maximum number of recent modifications to include

        Returns:
            Formatted context string, empty if no history
        """
        if not self.enabled:
            return ""

        history = self.get_file_history(file_path, limit=limit)
        lock_info = self.check_lock(file_path)

        if not history and not lock_info:
            return ""

        lines = ["[FILE CONTEXT - Recent Modifications]"]

        if lock_info:
            lines.append(
                f"LOCKED by {lock_info['agent_name']} "
                f"(expires: {lock_info['expires_at']})"
            )
            if lock_info.get("intent"):
                lines.append(f"  Intent: {lock_info['intent']}")

        for mod in history:
            timestamp = mod.get("timestamp", "unknown")
            agent = mod.get("agent_name", "unknown")
            change_type = mod.get("change_type", "unknown")
            intent = mod.get("intent", "")

            line = f"- {timestamp}: {agent} [{change_type}]"
            if intent:
                line += f" - {intent}"
            lines.append(line)

        lines.append("[END FILE CONTEXT]")
        return "\n".join(lines)

    # ========== Pre-Write Validation ==========

    def validate_write(
        self,
        file_path: str,
        agent_name: str,
    ) -> dict[str, Any]:
        """Validate if an agent can write to a file.

        Checks:
        - File is not locked by another agent
        - Returns recent modification context for awareness

        Args:
            file_path: Absolute path to the file
            agent_name: Name of the agent attempting to write

        Returns:
            Dict with keys:
                - allowed: bool - whether write is allowed
                - reason: str - explanation if not allowed
                - context: str - recent modification context
        """
        if not self.enabled:
            return {"allowed": True, "reason": "", "context": ""}

        lock_info = self.check_lock(file_path)

        if lock_info and lock_info["agent_name"] != agent_name:
            return {
                "allowed": False,
                "reason": f"File is locked by {lock_info['agent_name']} "
                f"until {lock_info['expires_at']}. "
                f"Intent: {lock_info.get('intent', 'not specified')}",
                "context": self.get_file_context(file_path),
            }

        return {
            "allowed": True,
            "reason": "",
            "context": self.get_file_context(file_path),
        }

    # ========== Cleanup Methods ==========

    def cleanup_old_modifications(self, days: int = 30) -> int:
        """Delete modification records older than specified days.

        Args:
            days: Delete records older than this many days

        Returns:
            Number of records deleted
        """
        if not self.enabled:
            return 0

        # Validate days is a positive integer to prevent SQL injection
        if not isinstance(days, int) or days <= 0:
            import sys

            print(f"Warning: Invalid days parameter: {days}", file=sys.stderr)
            return 0

        with self._lock:
            conn = None
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()

                # Calculate cutoff timestamp to avoid SQL injection
                cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

                cursor.execute(
                    """
                    DELETE FROM file_modifications
                    WHERE timestamp < ?
                    """,
                    (cutoff,),
                )
                deleted = cursor.rowcount

                conn.commit()
                return deleted

            except sqlite3.Error as e:
                import sys

                print(
                    f"Warning: Failed to cleanup old modifications: {e}",
                    file=sys.stderr,
                )
                return 0
            finally:
                if conn:
                    conn.close()

    def get_statistics(self) -> dict[str, Any]:
        """Get statistics about file safety data.

        Returns:
            Dict with statistics about locks and modifications
        """
        if not self.enabled:
            return {}

        with self._lock:
            conn = None
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()

                # Active locks count
                cursor.execute("SELECT COUNT(*) FROM file_locks")
                active_locks = cursor.fetchone()[0]

                # Total modifications
                cursor.execute("SELECT COUNT(*) FROM file_modifications")
                total_modifications = cursor.fetchone()[0]

                # Modifications by type
                cursor.execute(
                    """
                    SELECT change_type, COUNT(*)
                    FROM file_modifications
                    GROUP BY change_type
                    """
                )
                by_type = dict(cursor.fetchall())

                # Modifications by agent
                cursor.execute(
                    """
                    SELECT agent_name, COUNT(*)
                    FROM file_modifications
                    GROUP BY agent_name
                    """
                )
                by_agent = dict(cursor.fetchall())

                # Most modified files
                cursor.execute(
                    """
                    SELECT file_path, COUNT(*) as count
                    FROM file_modifications
                    GROUP BY file_path
                    ORDER BY count DESC
                    LIMIT 10
                    """
                )
                most_modified = [
                    {"file_path": row[0], "count": row[1]} for row in cursor.fetchall()
                ]

                return {
                    "active_locks": active_locks,
                    "total_modifications": total_modifications,
                    "by_change_type": by_type,
                    "by_agent": by_agent,
                    "most_modified_files": most_modified,
                }

            except sqlite3.Error as e:
                import sys

                print(f"Warning: Failed to get statistics: {e}", file=sys.stderr)
                return {}
            finally:
                if conn:
                    conn.close()

    # ========== Utility Methods ==========

    def _normalize_path(self, file_path: str) -> str:
        """Normalize a file path for consistent storage.

        Args:
            file_path: File path to normalize

        Returns:
            Normalized absolute path
        """
        return os.path.abspath(os.path.expanduser(file_path))

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
