"""Tests for ReplyStack class."""

from synapse.reply_stack import ReplyStack, SenderInfo


class TestReplyStack:
    """Test cases for ReplyStack with Map-based storage."""

    def test_set_and_get_by_sender_id(self) -> None:
        """Test basic set and get operations by sender_id."""
        stack = ReplyStack()
        sender_info: SenderInfo = {
            "sender_endpoint": "http://localhost:8100",
            "sender_task_id": "abc12345",
        }
        stack.set("synapse-claude-8100", sender_info)
        result = stack.get("synapse-claude-8100")
        assert result == sender_info

    def test_get_nonexistent_returns_none(self) -> None:
        """Test get on nonexistent sender returns None."""
        stack = ReplyStack()
        assert stack.get("nonexistent") is None

    def test_multiple_senders_coexist(self) -> None:
        """Test that multiple senders can coexist in the map."""
        stack = ReplyStack()
        info_claude: SenderInfo = {
            "sender_endpoint": "http://localhost:8100",
            "sender_task_id": "id1",
        }
        info_gemini: SenderInfo = {
            "sender_endpoint": "http://localhost:8110",
            "sender_task_id": "id2",
        }
        info_codex: SenderInfo = {
            "sender_endpoint": "http://localhost:8120",
            "sender_task_id": "id3",
        }

        stack.set("synapse-claude-8100", info_claude)
        stack.set("synapse-gemini-8110", info_gemini)
        stack.set("synapse-codex-8120", info_codex)

        # All three should be retrievable
        assert stack.get("synapse-claude-8100") == info_claude
        assert stack.get("synapse-gemini-8110") == info_gemini
        assert stack.get("synapse-codex-8120") == info_codex

    def test_same_sender_overwrites(self) -> None:
        """Test that same sender_id overwrites previous entry."""
        stack = ReplyStack()
        info1: SenderInfo = {
            "sender_endpoint": "http://localhost:8100",
            "sender_task_id": "first",
        }
        info2: SenderInfo = {
            "sender_endpoint": "http://localhost:8100",
            "sender_task_id": "second",
        }

        stack.set("synapse-claude-8100", info1)
        stack.set("synapse-claude-8100", info2)

        # Should have the second value
        result = stack.get("synapse-claude-8100")
        assert result == info2
        assert result is not None
        assert result["sender_task_id"] == "second"

    def test_pop_removes_entry(self) -> None:
        """Test that pop returns and removes the entry."""
        stack = ReplyStack()
        info: SenderInfo = {
            "sender_endpoint": "http://localhost:8100",
            "sender_task_id": "abc",
        }
        stack.set("synapse-claude-8100", info)

        # Pop should return and remove
        result = stack.pop("synapse-claude-8100")
        assert result == info

        # Second pop should return None
        assert stack.pop("synapse-claude-8100") is None
        assert stack.get("synapse-claude-8100") is None

    def test_pop_any_returns_last_entry_lifo(self) -> None:
        """Test that pop() without sender_id returns the last added entry (LIFO)."""
        stack = ReplyStack()
        info1: SenderInfo = {
            "sender_endpoint": "http://localhost:8100",
            "sender_task_id": "abc",
        }
        info2: SenderInfo = {
            "sender_endpoint": "http://localhost:8110",
            "sender_task_id": "def",
        }
        stack.set("synapse-claude-8100", info1)
        stack.set("synapse-gemini-8110", info2)

        # pop() should return the last added entry (LIFO - gemini)
        result = stack.pop()
        assert result == info2

        # pop() again should return the first entry (claude)
        result = stack.pop()
        assert result == info1

        # Stack should now be empty
        assert stack.is_empty()

        # Should be empty now
        assert stack.is_empty() is True

    def test_pop_empty_returns_none(self) -> None:
        """Test that pop on empty map returns None."""
        stack = ReplyStack()
        assert stack.pop() is None
        assert stack.pop("nonexistent") is None

    def test_is_empty(self) -> None:
        """Test is_empty method."""
        stack = ReplyStack()
        assert stack.is_empty() is True

        stack.set("synapse-claude-8100", {"sender_endpoint": "http://localhost:8100"})
        assert stack.is_empty() is False

        stack.pop("synapse-claude-8100")
        assert stack.is_empty() is True

    def test_clear(self) -> None:
        """Test clear method removes all items."""
        stack = ReplyStack()
        stack.set("synapse-claude-8100", {"sender_endpoint": "http://localhost:8100"})
        stack.set("synapse-gemini-8110", {"sender_endpoint": "http://localhost:8110"})

        stack.clear()
        assert stack.is_empty() is True
        assert stack.get("synapse-claude-8100") is None
        assert stack.get("synapse-gemini-8110") is None

    def test_partial_sender_info(self) -> None:
        """Test handling of partial sender info (missing some fields)."""
        stack = ReplyStack()
        # Only endpoint, no task_id
        info: SenderInfo = {"sender_endpoint": "http://localhost:8100"}
        stack.set("synapse-claude-8100", info)
        assert stack.get("synapse-claude-8100") == info

    def test_list_senders(self) -> None:
        """Test listing all sender IDs."""
        stack = ReplyStack()
        stack.set("synapse-claude-8100", {"sender_endpoint": "http://localhost:8100"})
        stack.set("synapse-gemini-8110", {"sender_endpoint": "http://localhost:8110"})

        senders = stack.list_senders()
        assert set(senders) == {"synapse-claude-8100", "synapse-gemini-8110"}

    def test_peek_last(self) -> None:
        """Test peek_last returns last (most recently added) entry without removing."""
        stack = ReplyStack()
        stack.set("synapse-claude-8100", {"sender_endpoint": "http://localhost:8100"})
        stack.set("synapse-gemini-8110", {"sender_endpoint": "http://localhost:8110"})

        # Peek should return the last added entry (gemini - LIFO)
        info = stack.peek_last()
        assert info is not None
        assert info["sender_endpoint"] == "http://localhost:8110"

        # Entry should still exist after peek
        assert not stack.is_empty()
        senders = stack.list_senders()
        assert len(senders) == 2

    def test_peek_last_empty(self) -> None:
        """Test peek_last returns None when empty."""
        stack = ReplyStack()
        assert stack.peek_last() is None

    def test_thread_safety(self) -> None:
        """Test thread-safe operations."""
        import threading

        stack = ReplyStack()
        errors: list[Exception] = []

        def set_items() -> None:
            try:
                for i in range(100):
                    stack.set(
                        f"agent-{i % 10}",
                        {"sender_endpoint": f"http://localhost:{8100 + i}"},
                    )
            except Exception as e:
                errors.append(e)

        def get_items() -> None:
            try:
                for i in range(100):
                    stack.get(f"agent-{i % 10}")  # May return None, that's ok
            except Exception as e:
                errors.append(e)

        threads = []
        for _ in range(5):
            threads.append(threading.Thread(target=set_items))
            threads.append(threading.Thread(target=get_items))

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Thread safety errors: {errors}"


class TestReplyStackGlobal:
    """Test the global reply stack instance."""

    def test_get_reply_stack_returns_singleton(self) -> None:
        """Test that get_reply_stack returns the same instance."""
        from synapse.reply_stack import get_reply_stack

        stack1 = get_reply_stack()
        stack2 = get_reply_stack()
        assert stack1 is stack2

    def test_global_stack_operations(self) -> None:
        """Test operations on global stack."""
        from synapse.reply_stack import get_reply_stack

        stack = get_reply_stack()
        # Clear first to ensure clean state
        stack.clear()

        info: SenderInfo = {
            "sender_endpoint": "http://localhost:8100",
            "sender_task_id": "test123",
        }
        stack.set("synapse-claude-8100", info)
        assert stack.get("synapse-claude-8100") == info

        # Cleanup
        stack.clear()
