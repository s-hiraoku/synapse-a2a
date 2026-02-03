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

logger = logging.getLogger(__name__)

# Default configuration values
DEFAULT_THRESHOLD = 200  # Characters (measured limit is 200-300)
DEFAULT_TTL = 3600  # 1 hour
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

        Args:
            task_id: The task ID associated with this message.
            content: The message content to store.

        Returns:
            Path to the created file.
        """
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
        except Exception:
            # Clean up temp file on error
            if temp_path.exists():
                temp_path.unlink()
            raise

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

    return _store_instance


def format_file_reference(file_path: Path, response_expected: bool = False) -> str:
    """
    Format a file reference message for the agent.

    Creates a human-readable message that instructs the agent to read
    the full message content from the specified file.

    Args:
        file_path: Path to the message file.
        response_expected: Whether the sender expects a response.

    Returns:
        Formatted reference message string with optional reply marker.
    """
    reply_marker = "[REPLY EXPECTED] " if response_expected else ""
    return (
        f"{reply_marker}[LONG MESSAGE - FILE ATTACHED]\n"
        f"The full message content is stored at: {file_path}\n"
        f"Please read this file to get the complete message."
    )
