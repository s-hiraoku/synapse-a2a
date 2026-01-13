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
import logging
import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


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


class FileLockDBError(Exception):
    """Raised when a database error occurs during file lock operations.

    This exception is used to implement fail-closed behavior: when the
    database is unavailable or returns an error, operations that depend
    on lock state should deny access rather than assume no lock exists.
    """

    pass


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
    DEFAULT_DB_PATH = ".synapse/file_safety.db"  # Project-local database
    DEFAULT_RETENTION_DAYS = 30  # Default retention period for modification records

    def __init__(
        self,
        db_path: str | None = None,
        enabled: bool = True,
        retention_days: int | None = None,
    ) -> None:
        """Initialize FileSafetyManager.

        Args:
            db_path: Path to SQLite database file. Defaults to .synapse/file_safety.db
            enabled: Whether file safety features are enabled
            retention_days: Number of days to keep modification records (auto-cleanup)
        """
        self.enabled = enabled
        self.db_path = os.path.abspath(
            os.path.expanduser(db_path or self.DEFAULT_DB_PATH)
        )
        self.retention_days = (
            retention_days
            if retention_days is not None
            else self.DEFAULT_RETENTION_DAYS
        )
        self._lock = threading.RLock()

        if self.enabled:
            self._init_db()
            # Run auto-cleanup on startup
            self._auto_cleanup()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a SQLite connection with WAL mode and timeout for better concurrency.

        Returns:
            sqlite3.Connection configured for multi-agent access
        """
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    @classmethod
    def from_env(cls, db_path: str | None = None) -> "FileSafetyManager":
        """Create FileSafetyManager from environment variables and settings.

        Environment variables (higher priority):
        - SYNAPSE_FILE_SAFETY_ENABLED: "true"/"1" to enable
        - SYNAPSE_FILE_SAFETY_DB_PATH: Path to SQLite database file
        - SYNAPSE_FILE_SAFETY_RETENTION_DAYS: Number of days to keep records

        Falls back to .synapse/settings.json if env vars not set.

        Args:
            db_path: Optional path to SQLite database file

        Returns:
            FileSafetyManager instance with settings from env/config
        """
        # Resolve DB path (env > settings > arg > default)
        env_db_path = os.environ.get("SYNAPSE_FILE_SAFETY_DB_PATH", "").strip()
        if not env_db_path:
            env_db_path = cls._get_setting("SYNAPSE_FILE_SAFETY_DB_PATH", "").strip()
        resolved_db_path = env_db_path or db_path

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

        return cls(
            db_path=resolved_db_path, enabled=enabled, retention_days=retention_days
        )

    @staticmethod
    def _get_setting(key: str, default: str = "") -> str:
        """Get a setting value from .synapse/settings.json."""
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
            conn = None
            try:
                conn = self._get_connection()
                cursor = conn.cursor()

                # Create file_locks table with PID-based session tracking
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS file_locks (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        file_path TEXT NOT NULL UNIQUE,
                        agent_name TEXT NOT NULL,
                        agent_id TEXT,
                        agent_type TEXT,
                        pid INTEGER,
                        task_id TEXT,
                        locked_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        expires_at DATETIME NOT NULL,
                        intent TEXT
                    )
                    """
                )

                # Create file_modifications table
                # Note: timestamp column uses TEXT for ISO-8601 UTC strings
                # (no DEFAULT - must be provided explicitly for consistency)
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
                        timestamp TEXT NOT NULL,
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

                # Migrate schema: add new columns if they don't exist
                # (must be done before creating indexes on new columns)
                self._migrate_locks_schema(cursor, conn)

                # Add indexes for new columns (after migration)
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_locks_agent_type ON file_locks(agent_type)"
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_locks_pid ON file_locks(pid)"
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_locks_agent_id ON file_locks(agent_id)"
                )
                conn.commit()

                # Migrate legacy timestamps to ISO-8601 format
                self._migrate_timestamps_to_iso8601(cursor, conn)

                logger.debug(f"File safety database initialized: {self.db_path}")
            except sqlite3.Error as e:
                logger.error(f"Failed to initialize file safety DB: {e}")
            finally:
                if conn is not None:
                    conn.close()

    def _migrate_locks_schema(
        self, cursor: sqlite3.Cursor, conn: sqlite3.Connection
    ) -> None:
        """Migrate file_locks schema to add new columns for PID-based tracking.

        Adds columns if they don't exist:
        - agent_id: Full agent identifier (e.g., "synapse-claude-8100")
        - agent_type: Short agent type (e.g., "claude")
        - pid: Process ID for session tracking
        """
        try:
            # Check existing columns
            cursor.execute("PRAGMA table_info(file_locks)")
            existing_columns = {row[1] for row in cursor.fetchall()}

            # Add missing columns
            if "agent_id" not in existing_columns:
                cursor.execute("ALTER TABLE file_locks ADD COLUMN agent_id TEXT")
                # Migrate existing data: copy agent_name to agent_id
                cursor.execute(
                    "UPDATE file_locks SET agent_id = agent_name WHERE agent_id IS NULL"
                )
                logger.info("Migrated file_locks: added agent_id column")

            if "agent_type" not in existing_columns:
                cursor.execute("ALTER TABLE file_locks ADD COLUMN agent_type TEXT")
                logger.info("Migrated file_locks: added agent_type column")

            if "pid" not in existing_columns:
                cursor.execute("ALTER TABLE file_locks ADD COLUMN pid INTEGER")
                logger.info("Migrated file_locks: added pid column")

            conn.commit()
        except sqlite3.Error as e:
            logger.warning(f"Schema migration failed (non-fatal): {e}")

    def _migrate_timestamps_to_iso8601(
        self, cursor: sqlite3.Cursor, conn: sqlite3.Connection
    ) -> None:
        """Migrate legacy CURRENT_TIMESTAMP format to ISO-8601 UTC strings.

        Legacy format: 'YYYY-MM-DD HH:MM:SS' (SQLite CURRENT_TIMESTAMP)
        Target format: 'YYYY-MM-DDTHH:MM:SS+00:00' (ISO-8601 with timezone)

        This migration runs on every init but only updates rows that need it.
        """
        try:
            # Find rows with legacy timestamp format (contains space, no 'T')
            # Legacy: '2024-01-15 10:30:00'
            # ISO-8601: '2024-01-15T10:30:00+00:00'
            cursor.execute(
                """
                SELECT id, timestamp FROM file_modifications
                WHERE timestamp LIKE '____-__-__ __:__:%'
                  AND timestamp NOT LIKE '%T%'
                """
            )
            legacy_rows = cursor.fetchall()

            if not legacy_rows:
                return

            logger.info(
                f"Migrating {len(legacy_rows)} legacy timestamps to ISO-8601 format"
            )

            for row_id, legacy_ts in legacy_rows:
                # Convert 'YYYY-MM-DD HH:MM:SS' to 'YYYY-MM-DDTHH:MM:SS+00:00'
                # Assume legacy timestamps are UTC
                iso_ts = legacy_ts.replace(" ", "T") + "+00:00"
                cursor.execute(
                    "UPDATE file_modifications SET timestamp = ? WHERE id = ?",
                    (iso_ts, row_id),
                )

            conn.commit()
            logger.info(f"Successfully migrated {len(legacy_rows)} timestamps")
        except sqlite3.Error as e:
            logger.warning(f"Timestamp migration failed (non-fatal): {e}")

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
                logger.info(
                    f"Auto-cleaned {deleted} modification records "
                    f"older than {self.retention_days} days"
                )

            # Also cleanup expired locks
            expired = self.cleanup_expired_locks()
            if expired > 0:
                logger.debug(f"Cleaned up {expired} expired locks")
        except Exception as e:
            logger.debug(f"Auto-cleanup error (ignored): {e}")

    # ========== File Locking Methods ==========

    def acquire_lock(
        self,
        file_path: str,
        agent_name: str | None = None,
        task_id: str | None = None,
        duration_seconds: int | None = None,
        intent: str | None = None,
        *,
        agent_id: str | None = None,
        agent_type: str | None = None,
        pid: int | None = None,
    ) -> dict[str, Any]:
        """Attempt to acquire a lock on a file.

        Args:
            file_path: Absolute path to the file to lock
            agent_name: Name of the agent requesting the lock (deprecated, use agent_id)
            task_id: Optional task identifier
            duration_seconds: Lock duration in seconds (default: 300)
            intent: Optional description of intended changes
            agent_id: Full agent identifier (e.g., "synapse-claude-8100")
            agent_type: Short agent type (e.g., "claude") for filtering
            pid: Process ID for session tracking (default: current process)

        Returns:
            Dict with keys:
                - status: LockStatus (ACQUIRED, ALREADY_LOCKED, RENEWED)
                - lock_holder: Agent name holding the lock (if ALREADY_LOCKED)
                - expires_at: Lock expiration time (if ACQUIRED or RENEWED)
        """
        if not self.enabled:
            return {"status": LockStatus.ACQUIRED, "expires_at": None}

        # Handle backward compatibility: agent_name -> agent_id
        effective_agent_id = agent_id or agent_name
        if not effective_agent_id:
            raise ValueError("Either agent_id or agent_name must be provided")

        # Use current process PID if not specified
        effective_pid = pid if pid is not None else os.getpid()

        duration = duration_seconds or self.DEFAULT_LOCK_DURATION_SECONDS
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=duration)
        normalized_path = self._normalize_path(file_path)

        with self._lock:
            conn = None
            try:
                conn = self._get_connection()
                cursor = conn.cursor()

                # First, clean up expired locks and stale locks (dead processes)
                self._cleanup_expired_locks_internal(cursor)
                self._cleanup_stale_locks_internal(cursor)

                # Check for existing lock
                cursor.execute(
                    "SELECT agent_id, agent_name, expires_at, pid FROM file_locks WHERE file_path = ?",
                    (normalized_path,),
                )
                existing = cursor.fetchone()

                if existing:
                    (
                        existing_agent_id,
                        existing_agent_name,
                        existing_expires,
                        existing_pid,
                    ) = existing
                    # Use agent_id if available, fall back to agent_name for old records
                    existing_identifier = existing_agent_id or existing_agent_name

                    if existing_identifier == effective_agent_id:
                        # Same agent - renew the lock
                        cursor.execute(
                            """
                            UPDATE file_locks
                            SET expires_at = ?, intent = ?, task_id = ?, pid = ?,
                                agent_id = ?, agent_type = ?
                            WHERE file_path = ?
                            """,
                            (
                                expires_at.isoformat(),
                                intent,
                                task_id,
                                effective_pid,
                                effective_agent_id,
                                agent_type,
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
                            "lock_holder": existing_identifier,
                            "expires_at": existing_expires,
                        }

                # No existing lock - acquire it
                cursor.execute(
                    """
                    INSERT INTO file_locks
                    (file_path, agent_name, agent_id, agent_type, pid, task_id, expires_at, intent)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        normalized_path,
                        effective_agent_id,  # Keep agent_name for backward compatibility
                        effective_agent_id,
                        agent_type,
                        effective_pid,
                        task_id,
                        expires_at.isoformat(),
                        intent,
                    ),
                )
                conn.commit()

                logger.debug(
                    f"Lock acquired: {normalized_path} by {effective_agent_id} "
                    f"(pid={effective_pid}, expires: {expires_at.isoformat()})"
                )
                return {
                    "status": LockStatus.ACQUIRED,
                    "expires_at": expires_at.isoformat(),
                }

            except sqlite3.IntegrityError:
                # Concurrent INSERT due to UNIQUE constraint on file_path
                # Another agent acquired the lock between our SELECT and INSERT
                if conn:
                    conn.rollback()
                try:
                    cursor.execute(
                        "SELECT agent_name, expires_at FROM file_locks WHERE file_path = ?",
                        (normalized_path,),
                    )
                    row = cursor.fetchone()
                    if row:
                        return {
                            "status": LockStatus.ALREADY_LOCKED,
                            "lock_holder": row[0],
                            "expires_at": row[1],
                        }
                    # Lock was released between our INSERT attempt and this SELECT
                    # Return generic ALREADY_LOCKED since we can't safely retry
                    return {
                        "status": LockStatus.ALREADY_LOCKED,
                        "lock_holder": "unknown",
                        "expires_at": None,
                    }
                except sqlite3.Error:
                    # Fall back to generic ALREADY_LOCKED if SELECT fails
                    return {
                        "status": LockStatus.ALREADY_LOCKED,
                        "lock_holder": "unknown",
                        "expires_at": None,
                    }
            except sqlite3.Error as e:
                logger.error(f"Failed to acquire lock on {normalized_path}: {e}")
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
                conn = self._get_connection()
                cursor = conn.cursor()

                cursor.execute(
                    "DELETE FROM file_locks WHERE file_path = ? AND agent_name = ?",
                    (normalized_path, agent_name),
                )
                deleted = cursor.rowcount > 0

                conn.commit()
                if deleted:
                    logger.debug(f"Lock released: {normalized_path} by {agent_name}")
                return deleted

            except sqlite3.Error as e:
                logger.error(f"Failed to release lock on {normalized_path}: {e}")
                return False
            finally:
                if conn:
                    conn.close()

    def check_lock(
        self, file_path: str, *, cleanup_stale: bool = True
    ) -> dict[str, Any] | None:
        """Check if a file is locked.

        Args:
            file_path: Absolute path to the file
            cleanup_stale: If True, automatically clean up locks from dead processes

        Returns:
            Lock info dict if locked, None if not locked.
            Dict contains: agent_name, agent_id, agent_type, pid, task_id, locked_at, expires_at, intent

        Raises:
            FileLockDBError: If database error occurs (fail-closed behavior)
        """
        if not self.enabled:
            return None

        normalized_path = self._normalize_path(file_path)

        with self._lock:
            conn = None
            try:
                conn = self._get_connection()
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
                    row_dict = dict(row)
                    pid = row_dict.get("pid")

                    # Check if the lock holder is still alive
                    if cleanup_stale and pid and not self._is_process_running(pid):
                        # Lock holder is dead, clean up
                        cursor.execute(
                            "DELETE FROM file_locks WHERE file_path = ?",
                            (normalized_path,),
                        )
                        conn.commit()
                        logger.debug(
                            f"Auto-cleaned stale lock on {normalized_path} "
                            f"(pid {pid} no longer running)"
                        )
                        return None

                    return row_dict
                return None

            except sqlite3.Error as e:
                # Fail-closed: raise exception so callers can deny access
                logger.error(f"Database error checking lock for {normalized_path}: {e}")
                raise FileLockDBError(f"Failed to check lock: {e}") from e
            finally:
                if conn:
                    conn.close()

    def is_locked_by_other(self, file_path: str, agent_name: str) -> bool:
        """Check if a file is locked by another agent.

        Uses fail-closed behavior: returns True (locked) if database
        error occurs, to prevent potential conflicts.

        Args:
            file_path: Absolute path to the file
            agent_name: Current agent's name

        Returns:
            True if locked by another agent or if database error occurs,
            False only if confirmed not locked by another agent
        """
        try:
            lock_info = self.check_lock(file_path)
        except FileLockDBError:
            # Fail-closed: assume locked if we can't check
            logger.warning(f"Assuming file locked due to database error: {file_path}")
            return True

        if lock_info is None:
            return False
        return bool(lock_info["agent_name"] != agent_name)

    def list_locks(
        self,
        agent_name: str | None = None,
        *,
        pid: int | None = None,
        agent_type: str | None = None,
        include_stale: bool = True,
    ) -> list[dict[str, Any]]:
        """List all active locks.

        Args:
            agent_name: Optional filter by agent name/agent_id (exact match)
            pid: Optional filter by process ID (exact match)
            agent_type: Optional filter by agent type (e.g., "claude", "gemini")
            include_stale: If True, include locks from dead processes (default: True)

        Returns:
            List of lock info dicts
        """
        if not self.enabled:
            return []

        with self._lock:
            conn = None
            try:
                conn = self._get_connection()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                # Clean up expired locks first
                self._cleanup_expired_locks_internal(cursor)
                conn.commit()

                # Build query based on filters
                if pid is not None:
                    cursor.execute(
                        "SELECT * FROM file_locks WHERE pid = ? ORDER BY locked_at DESC",
                        (pid,),
                    )
                elif agent_type:
                    cursor.execute(
                        "SELECT * FROM file_locks WHERE agent_type = ? ORDER BY locked_at DESC",
                        (agent_type,),
                    )
                elif agent_name:
                    # Support both agent_name and agent_id for backward compatibility
                    cursor.execute(
                        """SELECT * FROM file_locks
                           WHERE agent_name = ? OR agent_id = ?
                           ORDER BY locked_at DESC""",
                        (agent_name, agent_name),
                    )
                else:
                    cursor.execute("SELECT * FROM file_locks ORDER BY locked_at DESC")

                rows = cursor.fetchall()

                # Filter out stale locks if requested
                result = []
                for row in rows:
                    row_dict = dict(row)
                    pid = row_dict.get("pid")
                    if pid and not include_stale and not self._is_process_running(pid):
                        continue
                    result.append(row_dict)

                return result

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

    def _is_process_running(self, pid: int) -> bool:
        """Check if a process is still running.

        Args:
            pid: Process ID to check

        Returns:
            True if process is running, False otherwise
        """
        try:
            os.kill(pid, 0)  # Signal 0 only checks existence
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            # Process exists but we don't have permission
            return True
        except (OSError, TypeError):
            return False

    def _cleanup_stale_locks_internal(self, cursor: sqlite3.Cursor) -> int:
        """Clean up locks from dead processes (internal, requires cursor).

        Args:
            cursor: Active SQLite cursor

        Returns:
            Number of stale locks removed
        """
        # Get all locks with PIDs
        cursor.execute("SELECT id, pid FROM file_locks WHERE pid IS NOT NULL")
        rows = cursor.fetchall()

        stale_ids = []
        for lock_id, pid in rows:
            if not self._is_process_running(pid):
                stale_ids.append(lock_id)

        if stale_ids:
            placeholders = ",".join("?" * len(stale_ids))
            cursor.execute(
                f"DELETE FROM file_locks WHERE id IN ({placeholders})",
                stale_ids,
            )
            logger.debug(f"Cleaned up {len(stale_ids)} stale locks from dead processes")

        return len(stale_ids)

    def cleanup_stale_locks(self) -> int:
        """Clean up all locks from dead processes.

        Returns:
            Number of stale locks removed
        """
        if not self.enabled:
            return 0

        with self._lock:
            conn = None
            try:
                conn = self._get_connection()
                cursor = conn.cursor()

                removed = self._cleanup_stale_locks_internal(cursor)

                conn.commit()
                return removed

            except sqlite3.Error as e:
                logger.error(f"Failed to cleanup stale locks: {e}")
                return 0
            finally:
                if conn:
                    conn.close()

    def get_stale_locks(self) -> list[dict[str, Any]]:
        """Get list of locks from dead processes.

        Returns:
            List of lock info dicts for stale locks
        """
        if not self.enabled:
            return []

        with self._lock:
            conn = None
            try:
                conn = self._get_connection()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                cursor.execute("SELECT * FROM file_locks WHERE pid IS NOT NULL")
                rows = cursor.fetchall()

                stale_locks = []
                for row in rows:
                    row_dict = dict(row)
                    pid = row_dict.get("pid")
                    if pid and not self._is_process_running(pid):
                        stale_locks.append(row_dict)

                return stale_locks

            except sqlite3.Error as e:
                logger.error(f"Failed to get stale locks: {e}")
                return []
            finally:
                if conn:
                    conn.close()

    def force_unlock(self, file_path: str) -> bool:
        """Force release a lock on a file regardless of owner.

        Args:
            file_path: Absolute path to the file

        Returns:
            True if lock was released, False if not found
        """
        if not self.enabled:
            return True

        normalized_path = self._normalize_path(file_path)

        with self._lock:
            conn = None
            try:
                conn = self._get_connection()
                cursor = conn.cursor()

                cursor.execute(
                    "DELETE FROM file_locks WHERE file_path = ?",
                    (normalized_path,),
                )
                deleted = cursor.rowcount > 0

                conn.commit()
                if deleted:
                    logger.info(f"Force unlocked: {normalized_path}")
                return deleted

            except sqlite3.Error as e:
                logger.error(f"Failed to force unlock {normalized_path}: {e}")
                return False
            finally:
                if conn:
                    conn.close()

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
                conn = self._get_connection()
                cursor = conn.cursor()

                removed = self._cleanup_expired_locks_internal(cursor)

                conn.commit()
                return removed

            except sqlite3.Error as e:
                logger.error(f"Failed to cleanup expired locks: {e}")
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
                logger.warning(
                    f"Invalid change_type: {change_type}. Must be one of {valid_types}"
                )
                return None
            change_type_str = change_type
        else:
            logger.warning(
                f"change_type must be ChangeType or str, got {type(change_type)}"
            )
            return None

        metadata_json = None
        if metadata:
            with contextlib.suppress(TypeError, ValueError):
                metadata_json = json.dumps(metadata)

        # Use ISO-8601 UTC timestamp for consistent sorting and comparison
        timestamp = datetime.now(timezone.utc).isoformat()

        with self._lock:
            conn = None
            try:
                conn = self._get_connection()
                cursor = conn.cursor()

                cursor.execute(
                    """
                    INSERT INTO file_modifications
                    (task_id, agent_name, file_path, change_type, intent, affected_lines, metadata, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        task_id,
                        agent_name,
                        normalized_path,
                        change_type_str,
                        intent,
                        affected_lines,
                        metadata_json,
                        timestamp,
                    ),
                )

                record_id = cursor.lastrowid
                conn.commit()
                logger.debug(
                    f"Recorded modification: {normalized_path} by {agent_name} "
                    f"({change_type_str})"
                )
                return record_id

            except sqlite3.Error as e:
                logger.error(f"Failed to record modification: {e}")
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
                conn = self._get_connection()
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
                conn = self._get_connection()
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
                conn = self._get_connection()
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
            Formatted context string, empty if no history.
            Returns warning message if database error occurs.
        """
        if not self.enabled:
            return ""

        history = self.get_file_history(file_path, limit=limit)

        try:
            lock_info = self.check_lock(file_path)
        except FileLockDBError:
            # Include warning in context so agents are aware of DB issues
            return (
                "[FILE CONTEXT - WARNING]\n"
                "Database error: cannot determine lock status.\n"
                "Proceed with caution - file may be locked by another agent.\n"
                "[END FILE CONTEXT]"
            )

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

        Uses fail-closed behavior: if the database is unavailable,
        write access is denied to prevent potential conflicts.

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

        try:
            lock_info = self.check_lock(file_path)
        except FileLockDBError as e:
            # Fail-closed: deny write when database is unavailable
            logger.warning(f"Denying write due to database error: {e}")
            return {
                "allowed": False,
                "reason": "Cannot verify lock status due to database error. "
                "Write denied for safety.",
                "context": "",
            }

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
            days: Delete records older than this many days.
                  Use 0 to skip cleanup (no records deleted).
                  Negative values are invalid and will be rejected.

        Returns:
            Number of records deleted
        """
        if not self.enabled:
            return 0

        # Validate days is a non-negative integer
        if not isinstance(days, int) or days < 0:
            import sys

            print(f"Warning: Invalid days parameter: {days}", file=sys.stderr)
            return 0

        # days=0 means skip cleanup (consistent with _auto_cleanup behavior)
        if days == 0:
            return 0

        with self._lock:
            conn = None
            try:
                conn = self._get_connection()
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
                conn = self._get_connection()
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
        else:
            data["metadata"] = {}

        return data
