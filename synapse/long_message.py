"""
Long Message Storage Module.

This module handles temporary file storage for messages that exceed
the TUI input area limit (approximately 200-300 characters).

When a message is too long to be pasted directly into an agent's TUI,
it is stored in a temporary file and a reference message is sent instead.
The agent can then read the full content from the file.
"""

import logging
import os
import tempfile
import time
from pathlib import Path

from synapse._pty_sanitize import strip_control_bytes
from synapse.utils import build_sender_prefix

logger = logging.getLogger(__name__)

# Default configuration values
DEFAULT_THRESHOLD = 200  # Characters (measured limit is 200-300)
DEFAULT_TTL = 3600  # 1 hour
DEFAULT_CLEANUP_INTERVAL = 300.0  # 5 minutes between lazy cleanup sweeps
DEFAULT_MESSAGE_DIR = Path(tempfile.gettempdir()) / "synapse-a2a" / "messages"


class LongMessageStore:
    """
    Temporary file storage for long messages.

    Messages exceeding the threshold are stored in files and a reference
    message is sent to the agent instead. Files are automatically cleaned
    up after the TTL expires.

    Attributes:
        message_dir: Directory for storing message files.
        threshold: Character count threshold for file storage.
        ttl: Time-to-live in seconds for stored files.
        _last_cleanup_ts: Unix timestamp of the most recent
            cleanup_expired() invocation; used by maybe_cleanup_expired()
            to throttle to at most one cleanup per DEFAULT_CLEANUP_INTERVAL
            seconds.
    """

    def __init__(
        self,
        message_dir: Path,
        threshold: int = DEFAULT_THRESHOLD,
        ttl: int = DEFAULT_TTL,
    ) -> None:
        """
        Initialize the long message store.

        Args:
            message_dir: Directory for storing message files.
            threshold: Character count threshold for file storage.
            ttl: Time-to-live in seconds for stored files.
        """
        self.message_dir = message_dir
        self.threshold = threshold
        self.ttl = ttl
        self._last_cleanup_ts: float = 0.0

        # Create directory if it doesn't exist
        self.message_dir.mkdir(parents=True, exist_ok=True)

    def needs_file_storage(self, content: str) -> bool:
        """
        Check if content exceeds the threshold and needs file storage.

        Character count is used (not byte count) to handle multibyte
        characters correctly.

        Args:
            content: The message content to check.

        Returns:
            True if content exceeds threshold, False otherwise.
        """
        return len(content) > self.threshold

    def store_message(self, task_id: str, content: str) -> Path:
        """
        Store message content in a temporary file.

        Uses atomic write (temp file + rename) to ensure file integrity.
        The file is named with the task_id for easy identification.

        Content is passed through ``strip_control_bytes`` before persisting
        so PTY scrape residue (ANSI escapes, status-bar fragments,
        partial-render bytes) cannot leak into the long-message file path
        — symmetric to PR #663/#668 (Bug C routes A/B). See issue #677.

        Args:
            task_id: The task ID associated with this message.
            content: The message content to store.

        Returns:
            Path to the created file.
        """
        content = strip_control_bytes(content)

        # Generate unique filename using task_id and timestamp
        timestamp = int(time.time() * 1000)
        filename = f"{task_id[:8]}-{timestamp}.txt"
        file_path = self.message_dir / filename

        # Atomic write: write to temp file, then rename
        temp_path = file_path.with_suffix(".tmp")
        try:
            temp_path.write_text(content, encoding="utf-8")
            temp_path.rename(file_path)
            logger.debug(f"Stored long message to {file_path}")
        except OSError:
            # Clean up temp file on error
            if temp_path.exists():
                temp_path.unlink()
            raise

        self.maybe_cleanup_expired()
        return file_path

    def read_message(self, file_path: Path) -> str | None:
        """
        Read message content from a stored file.

        Args:
            file_path: Path to the message file.

        Returns:
            File content if file exists, None otherwise.
        """
        if not file_path.exists():
            return None

        try:
            return file_path.read_text(encoding="utf-8")
        except OSError as e:
            logger.warning(f"Failed to read message file {file_path}: {e}")
            return None

    def cleanup_expired(self) -> int:
        """
        Remove files that have exceeded their TTL.

        Scans the message directory and removes files older than the TTL.
        Only removes files with .txt extension to avoid accidental deletion.

        Returns:
            Number of files removed.
        """
        if not self.message_dir.exists():
            return 0

        now = time.time()
        removed = 0

        for file_path in self.message_dir.glob("*.txt"):
            try:
                mtime = file_path.stat().st_mtime
                if now - mtime > self.ttl:
                    file_path.unlink()
                    removed += 1
                    logger.debug(f"Cleaned up expired message file: {file_path}")
            except OSError as e:
                logger.warning(f"Failed to cleanup file {file_path}: {e}")

        return removed

    def maybe_cleanup_expired(self, interval: float = DEFAULT_CLEANUP_INTERVAL) -> int:
        """
        Run cleanup_expired at most once per interval seconds.

        Throttled lazy cleanup intended to be called from write paths
        (e.g. store_message) so temp files do not accumulate between
        explicit cleanup calls. The first invocation always runs because
        the initial _last_cleanup_ts is 0.

        Args:
            interval: Minimum seconds between cleanup sweeps.

        Returns:
            Number of files removed in this call (0 when throttled).
        """
        now = time.time()
        if now - self._last_cleanup_ts < interval:
            return 0
        self._last_cleanup_ts = now
        return self.cleanup_expired()


# Singleton instance
_store_instance: LongMessageStore | None = None


def _get_env_int(name: str, default: int) -> int:
    """Get an integer from environment variable, returning default if not set."""
    value = os.environ.get(name)
    return int(value) if value else default


def get_long_message_store() -> LongMessageStore:
    """
    Get or create the singleton LongMessageStore instance.

    Configuration is read from environment variables:
    - SYNAPSE_LONG_MESSAGE_DIR: Directory for message files
    - SYNAPSE_LONG_MESSAGE_THRESHOLD: Character count threshold
    - SYNAPSE_LONG_MESSAGE_TTL: Time-to-live in seconds

    Returns:
        The singleton LongMessageStore instance.
    """
    global _store_instance

    if _store_instance is None:
        message_dir_env = os.environ.get("SYNAPSE_LONG_MESSAGE_DIR")
        message_dir = Path(message_dir_env) if message_dir_env else DEFAULT_MESSAGE_DIR

        _store_instance = LongMessageStore(
            message_dir=message_dir,
            threshold=_get_env_int("SYNAPSE_LONG_MESSAGE_THRESHOLD", DEFAULT_THRESHOLD),
            ttl=_get_env_int("SYNAPSE_LONG_MESSAGE_TTL", DEFAULT_TTL),
        )
        # Reclaim any stale files left behind by a previous process.
        _store_instance.cleanup_expired()
        _store_instance._last_cleanup_ts = time.time()

    return _store_instance


def format_file_reference(
    file_path: Path,
    response_mode: str = "silent",
    sender_id: str | None = None,
    sender_name: str | None = None,
) -> str:
    """
    Format a file reference message for the agent.

    Creates a human-readable message that instructs the agent to read
    the full message content from the specified file.

    Args:
        file_path: Path to the message file.
        response_mode: Response mode ("wait", "notify", or "silent").
        sender_id: Sender agent ID (e.g., synapse-claude-8100).
        sender_name: Sender display name (e.g., Alice).

    Returns:
        Formatted reference message string with optional sender and reply marker.
    """
    sender_prefix = build_sender_prefix(sender_id, sender_name)
    reply_marker = "[REPLY EXPECTED] " if response_mode in ("wait", "notify") else ""
    return (
        f"{sender_prefix}{reply_marker}[LONG MESSAGE - FILE ATTACHED] "
        f"Path: {file_path} — Please read this file to get the complete message."
    )
