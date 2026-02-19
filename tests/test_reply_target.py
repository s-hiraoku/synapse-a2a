"""Tests for file-based reply target persistence (synapse/reply_target.py).

This module addresses Issue #237: synapse reply fails for spawned agents because
the in-memory reply_stack may be empty when synapse reply queries it.
File-based persistence provides a durable fallback.
"""

import json
import threading
import time
from pathlib import Path

import pytest

from synapse.reply_target import FileReplyTargetStore


@pytest.fixture
def tmp_store(tmp_path: Path) -> FileReplyTargetStore:
    """Create a FileReplyTargetStore backed by a temp directory."""
    return FileReplyTargetStore(base_dir=tmp_path)


class TestFileReplyTargetStore:
    """Unit tests for file-based reply target storage."""

    def test_save_and_load(self, tmp_store: FileReplyTargetStore) -> None:
        """Save sender info and load it back by agent_id."""
        tmp_store.save(
            agent_id="synapse-claude-8100",
            sender_id="synapse-gemini-8110",
            sender_info={
                "sender_endpoint": "http://localhost:8110",
                "sender_uds_path": "/tmp/synapse-gemini-8110.sock",
                "sender_task_id": "task-abc123",
            },
        )
        result = tmp_store.load("synapse-claude-8100")
        assert result is not None
        assert result["sender_endpoint"] == "http://localhost:8110"
        assert result["sender_task_id"] == "task-abc123"

    def test_load_nonexistent_returns_none(
        self, tmp_store: FileReplyTargetStore
    ) -> None:
        """Load from non-existent agent returns None."""
        assert tmp_store.load("synapse-nonexistent-9999") is None

    def test_save_overwrites_same_sender(
        self, tmp_store: FileReplyTargetStore
    ) -> None:
        """Same sender_id overwrites previous entry (most recent wins)."""
        tmp_store.save(
            agent_id="synapse-claude-8100",
            sender_id="synapse-gemini-8110",
            sender_info={"sender_endpoint": "http://localhost:8110", "sender_task_id": "first"},
        )
        tmp_store.save(
            agent_id="synapse-claude-8100",
            sender_id="synapse-gemini-8110",
            sender_info={"sender_endpoint": "http://localhost:8110", "sender_task_id": "second"},
        )
        result = tmp_store.load("synapse-claude-8100")
        assert result is not None
        assert result["sender_task_id"] == "second"

    def test_multiple_senders_coexist(self, tmp_store: FileReplyTargetStore) -> None:
        """Multiple senders can coexist for the same agent."""
        tmp_store.save(
            agent_id="synapse-claude-8100",
            sender_id="synapse-gemini-8110",
            sender_info={"sender_endpoint": "http://localhost:8110"},
        )
        tmp_store.save(
            agent_id="synapse-claude-8100",
            sender_id="synapse-codex-8120",
            sender_info={"sender_endpoint": "http://localhost:8120"},
        )

        targets = tmp_store.list_targets("synapse-claude-8100")
        assert set(targets) == {"synapse-gemini-8110", "synapse-codex-8120"}

    def test_pop_removes_entry(self, tmp_store: FileReplyTargetStore) -> None:
        """Pop returns and removes the entry."""
        tmp_store.save(
            agent_id="synapse-claude-8100",
            sender_id="synapse-gemini-8110",
            sender_info={"sender_endpoint": "http://localhost:8110"},
        )

        result = tmp_store.pop("synapse-claude-8100", sender_id="synapse-gemini-8110")
        assert result is not None
        assert result["sender_endpoint"] == "http://localhost:8110"

        # Second pop returns None
        assert tmp_store.pop("synapse-claude-8100", sender_id="synapse-gemini-8110") is None

    def test_pop_without_sender_id_returns_latest(
        self, tmp_store: FileReplyTargetStore
    ) -> None:
        """Pop without sender_id returns the most recently saved entry."""
        tmp_store.save(
            agent_id="synapse-claude-8100",
            sender_id="synapse-gemini-8110",
            sender_info={"sender_endpoint": "http://localhost:8110"},
        )
        tmp_store.save(
            agent_id="synapse-claude-8100",
            sender_id="synapse-codex-8120",
            sender_info={"sender_endpoint": "http://localhost:8120"},
        )

        result = tmp_store.pop("synapse-claude-8100")
        assert result is not None
        # Should return the last added entry (codex)
        assert result["sender_endpoint"] == "http://localhost:8120"

    def test_load_with_sender_id(self, tmp_store: FileReplyTargetStore) -> None:
        """Load with specific sender_id returns that sender's info."""
        tmp_store.save(
            agent_id="synapse-claude-8100",
            sender_id="synapse-gemini-8110",
            sender_info={"sender_endpoint": "http://localhost:8110"},
        )
        tmp_store.save(
            agent_id="synapse-claude-8100",
            sender_id="synapse-codex-8120",
            sender_info={"sender_endpoint": "http://localhost:8120"},
        )

        result = tmp_store.load("synapse-claude-8100", sender_id="synapse-gemini-8110")
        assert result is not None
        assert result["sender_endpoint"] == "http://localhost:8110"

    def test_list_targets_empty(self, tmp_store: FileReplyTargetStore) -> None:
        """List targets for non-existent agent returns empty list."""
        assert tmp_store.list_targets("synapse-nonexistent-9999") == []

    def test_atomic_write_safety(self, tmp_store: FileReplyTargetStore) -> None:
        """File is written atomically (no partial JSON on disk)."""
        tmp_store.save(
            agent_id="synapse-claude-8100",
            sender_id="synapse-gemini-8110",
            sender_info={"sender_endpoint": "http://localhost:8110"},
        )

        # The file should be valid JSON (not a .tmp file)
        reply_file = tmp_store.base_dir / "synapse-claude-8100.reply.json"
        assert reply_file.exists()
        data = json.loads(reply_file.read_text())
        assert "synapse-gemini-8110" in data

        # No .tmp files should remain
        tmp_files = list(tmp_store.base_dir.glob("*.tmp"))
        assert len(tmp_files) == 0

    def test_corrupted_file_returns_none(self, tmp_store: FileReplyTargetStore) -> None:
        """Corrupted JSON file returns None gracefully (no crash)."""
        reply_file = tmp_store.base_dir / "synapse-claude-8100.reply.json"
        reply_file.write_text("{broken json")

        result = tmp_store.load("synapse-claude-8100")
        assert result is None

    def test_thread_safety(self, tmp_store: FileReplyTargetStore) -> None:
        """Concurrent save/load operations don't crash."""
        errors: list[Exception] = []

        def writer(thread_id: int) -> None:
            try:
                for i in range(20):
                    tmp_store.save(
                        agent_id="synapse-claude-8100",
                        sender_id=f"agent-{thread_id}",
                        sender_info={"sender_endpoint": f"http://localhost:{8200 + i}"},
                    )
            except Exception as e:
                errors.append(e)

        def reader() -> None:
            try:
                for _ in range(20):
                    tmp_store.load("synapse-claude-8100")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(3)]
        threads += [threading.Thread(target=reader) for _ in range(3)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Thread safety errors: {errors}"

    def test_save_includes_timestamp(self, tmp_store: FileReplyTargetStore) -> None:
        """Saved entry includes a timestamp for staleness detection."""
        tmp_store.save(
            agent_id="synapse-claude-8100",
            sender_id="synapse-gemini-8110",
            sender_info={"sender_endpoint": "http://localhost:8110"},
        )

        reply_file = tmp_store.base_dir / "synapse-claude-8100.reply.json"
        data = json.loads(reply_file.read_text())
        entry = data["synapse-gemini-8110"]
        assert "timestamp" in entry

    def test_cleanup_stale_entries(self, tmp_store: FileReplyTargetStore) -> None:
        """Stale entries (older than max_age) are cleaned up."""
        # Save an entry with a backdated timestamp
        tmp_store.save(
            agent_id="synapse-claude-8100",
            sender_id="synapse-gemini-8110",
            sender_info={"sender_endpoint": "http://localhost:8110"},
        )

        # Manually backdate the timestamp
        reply_file = tmp_store.base_dir / "synapse-claude-8100.reply.json"
        data = json.loads(reply_file.read_text())
        data["synapse-gemini-8110"]["timestamp"] = time.time() - 7200  # 2 hours ago
        reply_file.write_text(json.dumps(data))

        # Cleanup with 1-hour max age
        removed = tmp_store.cleanup("synapse-claude-8100", max_age_seconds=3600)
        assert removed == 1
        assert tmp_store.load("synapse-claude-8100") is None
