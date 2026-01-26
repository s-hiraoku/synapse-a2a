"""Tests for ReplyStack class."""

from synapse.reply_stack import ReplyStack


class TestReplyStack:
    """Test cases for ReplyStack."""

    def test_push_and_pop(self) -> None:
        """Test basic push and pop operations."""
        stack = ReplyStack()
        sender_info = {
            "sender_endpoint": "http://localhost:8100",
            "sender_task_id": "abc12345",
        }
        stack.push(sender_info)
        result = stack.pop()
        assert result == sender_info

    def test_pop_empty_returns_none(self) -> None:
        """Test pop on empty stack returns None."""
        stack = ReplyStack()
        assert stack.pop() is None

    def test_lifo_order(self) -> None:
        """Test that stack follows LIFO order."""
        stack = ReplyStack()
        info1 = {"sender_endpoint": "http://localhost:8100", "sender_task_id": "id1"}
        info2 = {"sender_endpoint": "http://localhost:8110", "sender_task_id": "id2"}
        info3 = {"sender_endpoint": "http://localhost:8120", "sender_task_id": "id3"}

        stack.push(info1)
        stack.push(info2)
        stack.push(info3)

        assert stack.pop() == info3
        assert stack.pop() == info2
        assert stack.pop() == info1
        assert stack.pop() is None

    def test_peek_returns_top_without_removing(self) -> None:
        """Test that peek returns top element without removing it."""
        stack = ReplyStack()
        info = {"sender_endpoint": "http://localhost:8100", "sender_task_id": "abc"}
        stack.push(info)

        # Peek should return the same element multiple times
        assert stack.peek() == info
        assert stack.peek() == info
        # Pop should still return it
        assert stack.pop() == info
        assert stack.peek() is None

    def test_is_empty(self) -> None:
        """Test is_empty method."""
        stack = ReplyStack()
        assert stack.is_empty() is True

        stack.push({"sender_endpoint": "http://localhost:8100"})
        assert stack.is_empty() is False

        stack.pop()
        assert stack.is_empty() is True

    def test_clear(self) -> None:
        """Test clear method removes all items."""
        stack = ReplyStack()
        stack.push({"sender_endpoint": "http://localhost:8100"})
        stack.push({"sender_endpoint": "http://localhost:8110"})

        stack.clear()
        assert stack.is_empty() is True
        assert stack.pop() is None

    def test_partial_sender_info(self) -> None:
        """Test handling of partial sender info (missing some fields)."""
        stack = ReplyStack()
        # Only endpoint, no task_id
        info = {"sender_endpoint": "http://localhost:8100"}
        stack.push(info)
        assert stack.pop() == info

    def test_thread_safety(self) -> None:
        """Test thread-safe operations."""
        import threading

        stack = ReplyStack()
        errors = []

        def push_items() -> None:
            try:
                for i in range(100):
                    stack.push({"sender_endpoint": f"http://localhost:{8100 + i}"})
            except Exception as e:
                errors.append(e)

        def pop_items() -> None:
            try:
                for _ in range(100):
                    stack.pop()  # May return None, that's ok
            except Exception as e:
                errors.append(e)

        threads = []
        for _ in range(5):
            threads.append(threading.Thread(target=push_items))
            threads.append(threading.Thread(target=pop_items))

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

        info = {"sender_endpoint": "http://localhost:8100", "sender_task_id": "test123"}
        stack.push(info)
        assert stack.pop() == info
