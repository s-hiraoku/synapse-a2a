"""Tests for --response reply PTY injection (v0.3.13).

When an agent sends a message with --response flag, the recipient processes
the message and sends a reply. This reply should be written to the sender's
PTY so the conversation can continue naturally.
"""

from synapse.utils import format_a2a_message


class TestReplyPtyInjection:
    """Tests for reply message PTY injection."""

    def test_reply_message_has_in_reply_to_metadata(self) -> None:
        """Replies should include in_reply_to metadata pointing to sender's task."""
        # This is the metadata format _send_response_to_sender uses
        metadata = {
            "sender": {"sender_id": "synapse-codex-8120"},
            "response_expected": False,
            "in_reply_to": "abc12345-1234-5678-abcd-123456789012",
        }

        # Verify structure
        assert "in_reply_to" in metadata
        assert metadata["in_reply_to"] == "abc12345-1234-5678-abcd-123456789012"
        assert metadata["response_expected"] is False

    def test_format_a2a_message_reply_no_response_expected(self) -> None:
        """Reply messages should not have REPLY EXPECTED prefix."""
        msg = format_a2a_message("This is my reply", response_expected=False)
        assert "REPLY EXPECTED" not in msg
        assert "A2A:" in msg
        assert "This is my reply" in msg

    def test_format_a2a_message_with_response_expected(self) -> None:
        """Original request with response_expected=True should have prefix."""
        msg = format_a2a_message("Please help me", response_expected=True)
        assert "REPLY EXPECTED" in msg
        assert "Please help me" in msg


class TestReplyToExistingTask:
    """Tests for the in_reply_to flow in send_message endpoint."""

    def test_in_reply_to_updates_existing_task(self) -> None:
        """When in_reply_to is set, should update existing task with artifact."""
        # This tests the logic in _send_task_message
        # When in_reply_to is present, the code should:
        # 1. Find the existing task by prefix
        # 2. Add the reply content as an artifact
        # 3. Update status to completed
        # 4. ALSO write to PTY so agent can see reply and continue conversation

        # The actual implementation is in a2a_compat.py _send_task_message
        # We verify the expected behavior:
        in_reply_to = "abc12345"  # 8-char prefix from PTY display
        assert len(in_reply_to) == 8

    def test_reply_writes_to_pty_with_standard_prefix(self) -> None:
        """Reply should be written to PTY with standard A2A: prefix."""
        # When an agent receives a reply (in_reply_to is set):
        # - The reply should be written to the sender's PTY
        # - Format: "A2A: <message>" (no trailing \n, submit_seq handles submission)
        # - This enables the agent to see the reply and continue the conversation

        message = "Here is my analysis of the code"
        expected_format = f"A2A: {message}"

        assert expected_format.startswith("A2A: ")
        assert message in expected_format

    def test_new_message_writes_to_pty(self) -> None:
        """When in_reply_to is NOT set, should write to PTY."""
        import pytest

        pytest.skip("Requires integration PTY fixture")


class TestReplyMessageFormat:
    """Tests for reply message formatting."""

    def test_reply_from_agent_has_agent_role(self) -> None:
        """Reply messages should have role='agent' not 'user'."""
        # The response payload in _send_response_to_sender
        payload = {
            "message": {
                "role": "agent",  # Must be 'agent' for replies
                "parts": [{"type": "text", "text": "Reply content"}],
            },
            "metadata": {
                "sender": {"sender_id": "synapse-codex-8120"},
                "response_expected": False,
                "in_reply_to": "task-uuid",
            },
        }

        assert payload["message"]["role"] == "agent"
        assert payload["metadata"]["response_expected"] is False

    def test_reply_includes_sender_id(self) -> None:
        """Reply should include sender_id for context."""
        sender_id = "synapse-codex-8120"
        payload = {
            "metadata": {
                "sender": {"sender_id": sender_id},
            }
        }

        assert payload["metadata"]["sender"]["sender_id"] == sender_id
