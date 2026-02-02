"""
Tests for LongMessageStore (long message file storage).

This module tests the long message temporary file storage system
that handles messages exceeding the TUI input limit.
"""

import os
import time
from pathlib import Path
from unittest.mock import patch


class TestLongMessageStoreInit:
    """Tests for LongMessageStore initialization."""

    def test_init_creates_directory(self, tmp_path: Path) -> None:
        """Test that LongMessageStore creates the message directory."""
        from synapse.long_message import LongMessageStore

        message_dir = tmp_path / "messages"
        assert not message_dir.exists()

        store = LongMessageStore(
            message_dir=message_dir,
            threshold=200,
            ttl=3600,
        )

        assert message_dir.exists()
        assert store.threshold == 200
        assert store.ttl == 3600

    def test_init_with_existing_directory(self, tmp_path: Path) -> None:
        """Test initialization with existing directory works."""
        from synapse.long_message import LongMessageStore

        message_dir = tmp_path / "messages"
        message_dir.mkdir(parents=True)

        store = LongMessageStore(
            message_dir=message_dir,
            threshold=300,
            ttl=7200,
        )

        assert message_dir.exists()
        assert store.threshold == 300


class TestNeedsFileStorage:
    """Tests for the needs_file_storage method."""

    def test_short_message_returns_false(self, tmp_path: Path) -> None:
        """Messages below threshold should not need file storage."""
        from synapse.long_message import LongMessageStore

        store = LongMessageStore(
            message_dir=tmp_path / "messages",
            threshold=200,
            ttl=3600,
        )

        # Exactly at threshold (should not need file storage)
        content = "x" * 200
        assert not store.needs_file_storage(content)

        # Below threshold
        content = "x" * 100
        assert not store.needs_file_storage(content)

        # Empty message
        assert not store.needs_file_storage("")

    def test_long_message_returns_true(self, tmp_path: Path) -> None:
        """Messages above threshold should need file storage."""
        from synapse.long_message import LongMessageStore

        store = LongMessageStore(
            message_dir=tmp_path / "messages",
            threshold=200,
            ttl=3600,
        )

        # Just above threshold
        content = "x" * 201
        assert store.needs_file_storage(content)

        # Well above threshold
        content = "x" * 1000
        assert store.needs_file_storage(content)

    def test_multibyte_characters_counted_correctly(self, tmp_path: Path) -> None:
        """Multibyte characters should be counted as single characters."""
        from synapse.long_message import LongMessageStore

        store = LongMessageStore(
            message_dir=tmp_path / "messages",
            threshold=200,
            ttl=3600,
        )

        # 200 Japanese characters (each is 3 bytes in UTF-8, but 1 character)
        content = "あ" * 200
        assert not store.needs_file_storage(content)

        content = "あ" * 201
        assert store.needs_file_storage(content)


class TestStoreMessage:
    """Tests for the store_message method."""

    def test_store_creates_file(self, tmp_path: Path) -> None:
        """store_message should create a file with the content."""
        from synapse.long_message import LongMessageStore

        store = LongMessageStore(
            message_dir=tmp_path / "messages",
            threshold=200,
            ttl=3600,
        )

        task_id = "test-task-123"
        content = "This is a test message" * 50

        file_path = store.store_message(task_id, content)

        assert file_path.exists()
        assert file_path.read_text(encoding="utf-8") == content
        # Filename contains first 8 chars of task_id
        assert task_id[:8] in str(file_path.name)

    def test_store_uses_atomic_write(self, tmp_path: Path) -> None:
        """store_message should use atomic write (temp file + rename)."""
        from synapse.long_message import LongMessageStore

        message_dir = tmp_path / "messages"
        store = LongMessageStore(
            message_dir=message_dir,
            threshold=200,
            ttl=3600,
        )

        task_id = "atomic-test"
        content = "Test content"

        file_path = store.store_message(task_id, content)

        # File should exist with correct content
        assert file_path.exists()
        assert file_path.read_text(encoding="utf-8") == content

        # No temp files should remain
        temp_files = list(message_dir.glob("*.tmp"))
        assert len(temp_files) == 0

    def test_store_with_special_characters(self, tmp_path: Path) -> None:
        """store_message should handle special characters in content."""
        from synapse.long_message import LongMessageStore

        store = LongMessageStore(
            message_dir=tmp_path / "messages",
            threshold=200,
            ttl=3600,
        )

        task_id = "special-chars"
        content = "Line 1\nLine 2\tTabbed\nNew line\nUnicode: 日本語 emoji: 🎉"

        file_path = store.store_message(task_id, content)

        assert file_path.exists()
        assert file_path.read_text(encoding="utf-8") == content


class TestReadMessage:
    """Tests for the read_message method."""

    def test_read_existing_file(self, tmp_path: Path) -> None:
        """read_message should return content of existing file."""
        from synapse.long_message import LongMessageStore

        store = LongMessageStore(
            message_dir=tmp_path / "messages",
            threshold=200,
            ttl=3600,
        )

        task_id = "read-test"
        content = "Content to read"
        file_path = store.store_message(task_id, content)

        result = store.read_message(file_path)

        assert result == content

    def test_read_nonexistent_file(self, tmp_path: Path) -> None:
        """read_message should return None for nonexistent file."""
        from synapse.long_message import LongMessageStore

        store = LongMessageStore(
            message_dir=tmp_path / "messages",
            threshold=200,
            ttl=3600,
        )

        fake_path = tmp_path / "messages" / "nonexistent.txt"

        result = store.read_message(fake_path)

        assert result is None

    def test_read_deleted_file(self, tmp_path: Path) -> None:
        """read_message should return None if file was deleted."""
        from synapse.long_message import LongMessageStore

        store = LongMessageStore(
            message_dir=tmp_path / "messages",
            threshold=200,
            ttl=3600,
        )

        task_id = "deleted-test"
        content = "To be deleted"
        file_path = store.store_message(task_id, content)

        # Delete the file
        file_path.unlink()

        result = store.read_message(file_path)

        assert result is None


class TestCleanupExpired:
    """Tests for the cleanup_expired method."""

    def test_cleanup_removes_old_files(self, tmp_path: Path) -> None:
        """cleanup_expired should remove files older than TTL."""
        from synapse.long_message import LongMessageStore

        message_dir = tmp_path / "messages"
        store = LongMessageStore(
            message_dir=message_dir,
            threshold=200,
            ttl=1,  # 1 second TTL for testing
        )

        # Create a file
        task_id = "old-task"
        content = "Old content"
        file_path = store.store_message(task_id, content)

        assert file_path.exists()

        # Wait for TTL to expire
        time.sleep(1.5)

        # Run cleanup
        removed = store.cleanup_expired()

        assert removed >= 1
        assert not file_path.exists()

    def test_cleanup_keeps_recent_files(self, tmp_path: Path) -> None:
        """cleanup_expired should keep files within TTL."""
        from synapse.long_message import LongMessageStore

        message_dir = tmp_path / "messages"
        store = LongMessageStore(
            message_dir=message_dir,
            threshold=200,
            ttl=3600,  # 1 hour TTL
        )

        # Create a file
        task_id = "recent-task"
        content = "Recent content"
        file_path = store.store_message(task_id, content)

        assert file_path.exists()

        # Run cleanup immediately
        removed = store.cleanup_expired()

        assert removed == 0
        assert file_path.exists()

    def test_cleanup_handles_empty_directory(self, tmp_path: Path) -> None:
        """cleanup_expired should handle empty directory gracefully."""
        from synapse.long_message import LongMessageStore

        store = LongMessageStore(
            message_dir=tmp_path / "messages",
            threshold=200,
            ttl=1,
        )

        # Run cleanup on empty directory
        removed = store.cleanup_expired()

        assert removed == 0


class TestGetLongMessageStore:
    """Tests for the get_long_message_store factory function."""

    def test_returns_store_instance(self, tmp_path: Path) -> None:
        """get_long_message_store should return a LongMessageStore."""
        from synapse.long_message import LongMessageStore, get_long_message_store

        with patch.dict(
            os.environ,
            {
                "SYNAPSE_LONG_MESSAGE_DIR": str(tmp_path / "messages"),
                "SYNAPSE_LONG_MESSAGE_THRESHOLD": "150",
                "SYNAPSE_LONG_MESSAGE_TTL": "1800",
            },
        ):
            # Reset singleton for test
            import synapse.long_message

            synapse.long_message._store_instance = None

            store = get_long_message_store()

            assert isinstance(store, LongMessageStore)
            assert store.threshold == 150
            assert store.ttl == 1800

    def test_uses_default_values(self, tmp_path: Path) -> None:
        """get_long_message_store should use defaults when env vars not set."""
        from synapse.long_message import get_long_message_store

        with patch.dict(
            os.environ,
            {
                "SYNAPSE_LONG_MESSAGE_DIR": str(tmp_path / "messages"),
            },
            clear=False,
        ):
            # Clear any existing env vars
            for key in [
                "SYNAPSE_LONG_MESSAGE_THRESHOLD",
                "SYNAPSE_LONG_MESSAGE_TTL",
            ]:
                os.environ.pop(key, None)

            # Reset singleton for test
            import synapse.long_message

            synapse.long_message._store_instance = None

            store = get_long_message_store()

            # Default values
            assert store.threshold == 200
            assert store.ttl == 3600

    def test_singleton_pattern(self, tmp_path: Path) -> None:
        """get_long_message_store should return the same instance."""
        from synapse.long_message import get_long_message_store

        with patch.dict(
            os.environ,
            {"SYNAPSE_LONG_MESSAGE_DIR": str(tmp_path / "messages")},
        ):
            # Reset singleton for test
            import synapse.long_message

            synapse.long_message._store_instance = None

            store1 = get_long_message_store()
            store2 = get_long_message_store()

            assert store1 is store2


class TestFormatFileReference:
    """Tests for the format_file_reference function."""

    def test_format_includes_file_path(self, tmp_path: Path) -> None:
        """format_file_reference should include the file path."""
        from synapse.long_message import format_file_reference

        file_path = tmp_path / "messages" / "test-task.txt"

        result = format_file_reference(file_path)

        assert str(file_path) in result
        assert "[LONG MESSAGE" in result or "LONG MESSAGE" in result.upper()

    def test_format_is_human_readable(self, tmp_path: Path) -> None:
        """format_file_reference should produce readable instructions."""
        from synapse.long_message import format_file_reference

        file_path = tmp_path / "messages" / "task-abc123.txt"

        result = format_file_reference(file_path)

        # Should contain instructions for the agent
        assert "read" in result.lower() or "file" in result.lower()

    def test_format_without_response_expected(self, tmp_path: Path) -> None:
        """format_file_reference should not include REPLY EXPECTED when False."""
        from synapse.long_message import format_file_reference

        file_path = tmp_path / "messages" / "test-task.txt"

        result = format_file_reference(file_path, response_expected=False)

        assert "[REPLY EXPECTED]" not in result
        assert "[LONG MESSAGE - FILE ATTACHED]" in result
        assert str(file_path) in result

    def test_format_with_response_expected(self, tmp_path: Path) -> None:
        """format_file_reference should include REPLY EXPECTED when True."""
        from synapse.long_message import format_file_reference

        file_path = tmp_path / "messages" / "test-task.txt"

        result = format_file_reference(file_path, response_expected=True)

        assert "[REPLY EXPECTED]" in result
        assert "[LONG MESSAGE - FILE ATTACHED]" in result
        assert str(file_path) in result
        # REPLY EXPECTED should come before LONG MESSAGE
        reply_pos = result.index("[REPLY EXPECTED]")
        long_msg_pos = result.index("[LONG MESSAGE")
        assert reply_pos < long_msg_pos


class TestConfigIntegration:
    """Tests for configuration integration with settings.json."""

    def test_uses_settings_env_values(self, tmp_path: Path) -> None:
        """LongMessageStore should use values from settings env."""
        from synapse.long_message import get_long_message_store

        # Simulate settings.json loaded env values
        with patch.dict(
            os.environ,
            {
                "SYNAPSE_LONG_MESSAGE_DIR": str(tmp_path / "custom-dir"),
                "SYNAPSE_LONG_MESSAGE_THRESHOLD": "250",
                "SYNAPSE_LONG_MESSAGE_TTL": "7200",
            },
        ):
            import synapse.long_message

            synapse.long_message._store_instance = None

            store = get_long_message_store()

            assert store.threshold == 250
            assert store.ttl == 7200
            assert "custom-dir" in str(store.message_dir)
