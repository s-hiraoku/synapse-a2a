"""Tests for prefix match task lookup (--reply-to with short IDs)."""

import pytest
from fastapi.testclient import TestClient

from synapse.a2a_compat import (
    Message,
    TaskStore,
    TextPart,
    create_a2a_router,
    task_store,
)


class TestTaskStorePrefixMatch:
    """Tests for TaskStore.get_by_prefix method."""

    @pytest.fixture
    def store(self) -> TaskStore:
        """Create a fresh TaskStore for each test."""
        return TaskStore()

    @pytest.fixture
    def message(self) -> Message:
        """Create a sample message."""
        return Message(parts=[TextPart(text="Test message")])

    def test_get_by_prefix_exact_match(
        self, store: TaskStore, message: Message
    ) -> None:
        """Full UUID should match exactly."""
        task = store.create(message)
        full_id = task.id

        result = store.get_by_prefix(full_id)
        assert result is not None
        assert result.id == full_id

    def test_get_by_prefix_8char_match(
        self, store: TaskStore, message: Message
    ) -> None:
        """8-character prefix should match."""
        task = store.create(message)
        prefix = task.id[:8]

        result = store.get_by_prefix(prefix)
        assert result is not None
        assert result.id == task.id

    def test_get_by_prefix_various_lengths(
        self, store: TaskStore, message: Message
    ) -> None:
        """Various prefix lengths should work."""
        task = store.create(message)

        # 4 chars
        result = store.get_by_prefix(task.id[:4])
        assert result is not None
        assert result.id == task.id

        # 12 chars
        result = store.get_by_prefix(task.id[:12])
        assert result is not None
        assert result.id == task.id

        # 20 chars
        result = store.get_by_prefix(task.id[:20])
        assert result is not None
        assert result.id == task.id

    def test_get_by_prefix_no_match(self, store: TaskStore, message: Message) -> None:
        """Non-matching prefix should return None."""
        store.create(message)

        result = store.get_by_prefix("xxxxxxxx")
        assert result is None

    def test_get_by_prefix_empty_store(self, store: TaskStore) -> None:
        """Empty store should return None."""
        result = store.get_by_prefix("abc12345")
        assert result is None

    def test_get_by_prefix_ambiguous_raises(
        self, store: TaskStore, message: Message
    ) -> None:
        """Ambiguous prefix (matches multiple) should raise ValueError."""
        # Create many tasks to increase chance of collision on short prefix
        tasks = [store.create(message) for _ in range(100)]

        # Find a 1-char prefix that matches multiple tasks
        prefix_counts: dict[str, list[str]] = {}
        for task in tasks:
            p = task.id[0]
            if p not in prefix_counts:
                prefix_counts[p] = []
            prefix_counts[p].append(task.id)

        # Find a prefix with multiple matches
        ambiguous_prefix = None
        for prefix, ids in prefix_counts.items():
            if len(ids) > 1:
                ambiguous_prefix = prefix
                break

        if ambiguous_prefix:
            with pytest.raises(ValueError, match="Ambiguous"):
                store.get_by_prefix(ambiguous_prefix)

    def test_get_by_prefix_case_sensitive(
        self, store: TaskStore, message: Message
    ) -> None:
        """Prefix matching should be case-insensitive (UUIDs are lowercase)."""
        task = store.create(message)
        prefix_lower = task.id[:8].lower()
        prefix_upper = task.id[:8].upper()

        # Both should match
        result_lower = store.get_by_prefix(prefix_lower)
        result_upper = store.get_by_prefix(prefix_upper)

        assert result_lower is not None
        assert result_upper is not None
        assert result_lower.id == task.id
        assert result_upper.id == task.id

    def test_get_by_prefix_with_hyphen(
        self, store: TaskStore, message: Message
    ) -> None:
        """Prefix with hyphen (UUID format) should work."""
        task = store.create(message)
        # UUID format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
        # Get prefix including first hyphen
        prefix_with_hyphen = task.id[:9]  # "xxxxxxxx-"

        result = store.get_by_prefix(prefix_with_hyphen)
        assert result is not None
        assert result.id == task.id


class TestReplyToWithPrefixMatch:
    """Integration tests for --reply-to using prefix match."""

    @pytest.fixture
    def store(self) -> TaskStore:
        """Create a fresh TaskStore."""
        return TaskStore()

    @pytest.fixture
    def message(self) -> Message:
        """Create a sample message."""
        return Message(parts=[TextPart(text="Test message")])

    def test_reply_to_flow_with_short_id(
        self, store: TaskStore, message: Message
    ) -> None:
        """Simulate --reply-to flow with 8-char ID from PTY display."""
        # 1. Sender creates task (via /tasks/create)
        sender_task = store.create(message, metadata={"response_expected": True})
        store.update_status(sender_task.id, "working")

        # 2. PTY displays short ID to receiver
        display_id = sender_task.id[:8]

        # 3. Receiver uses short ID for --reply-to
        found_task = store.get_by_prefix(display_id)

        # 4. Should find the original task
        assert found_task is not None
        assert found_task.id == sender_task.id
        assert found_task.status == "working"

    def test_reply_to_completes_task(self, store: TaskStore, message: Message) -> None:
        """Reply should complete the original task."""
        # Setup: sender's task
        sender_task = store.create(message, metadata={"response_expected": True})
        store.update_status(sender_task.id, "working")
        short_id = sender_task.id[:8]

        # Receiver finds task by prefix and completes it
        task = store.get_by_prefix(short_id)
        assert task is not None

        from synapse.a2a_compat import Artifact

        store.add_artifact(task.id, Artifact(type="text", data={"content": "Reply"}))
        store.update_status(task.id, "completed")

        # Verify completion
        completed = store.get(sender_task.id)
        assert completed is not None
        assert completed.status == "completed"
        assert len(completed.artifacts) == 1


class TestReplyToEndpoint:
    """HTTP endpoint tests for --reply-to with prefix match."""

    @pytest.fixture
    def app(self):
        """Create FastAPI app with A2A router."""
        from fastapi import FastAPI

        app = FastAPI()
        router = create_a2a_router(
            agent_type="test",
            port=9999,
            controller=None,  # No controller needed for reply-to tests
        )
        app.include_router(router)
        return app

    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return TestClient(app)

    @pytest.fixture(autouse=True)
    def clear_task_store(self):
        """Clear task store before each test."""
        task_store._tasks.clear()
        yield
        task_store._tasks.clear()

    def test_reply_to_with_short_id_via_endpoint(self, client) -> None:
        """POST /tasks/send-priority with short ID should work."""
        # 1. Create a task (simulating --response sender)
        create_response = client.post(
            "/tasks/create",
            json={
                "message": {"parts": [{"type": "text", "text": "Original message"}]},
                "metadata": {"response_expected": True},
            },
        )
        assert create_response.status_code == 200
        full_task_id = create_response.json()["task"]["id"]
        short_id = full_task_id[:8]

        # 2. Reply using short ID
        reply_response = client.post(
            "/tasks/send-priority?priority=3",
            json={
                "message": {"parts": [{"type": "text", "text": "Reply message"}]},
                "metadata": {"in_reply_to": short_id},
            },
        )
        assert reply_response.status_code == 200

        # 3. Verify task was completed
        result = reply_response.json()["task"]
        assert result["status"] == "completed"
        assert len(result["artifacts"]) == 1
        assert result["artifacts"][0]["data"]["content"] == "Reply message"

    def test_reply_to_with_full_id_via_endpoint(self, client) -> None:
        """POST /tasks/send-priority with full UUID should work."""
        # 1. Create a task
        create_response = client.post(
            "/tasks/create",
            json={
                "message": {"parts": [{"type": "text", "text": "Original message"}]},
                "metadata": {"response_expected": True},
            },
        )
        assert create_response.status_code == 200
        full_task_id = create_response.json()["task"]["id"]

        # 2. Reply using full ID
        reply_response = client.post(
            "/tasks/send-priority?priority=3",
            json={
                "message": {"parts": [{"type": "text", "text": "Reply message"}]},
                "metadata": {"in_reply_to": full_task_id},
            },
        )
        assert reply_response.status_code == 200
        assert reply_response.json()["task"]["status"] == "completed"

    def test_reply_to_not_found_via_endpoint(self, client) -> None:
        """POST /tasks/send-priority with non-existent ID should return 404."""
        reply_response = client.post(
            "/tasks/send-priority?priority=3",
            json={
                "message": {"parts": [{"type": "text", "text": "Reply message"}]},
                "metadata": {"in_reply_to": "nonexistent"},
            },
        )
        assert reply_response.status_code == 404
        assert "not found" in reply_response.json()["detail"].lower()
