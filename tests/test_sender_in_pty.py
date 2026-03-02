"""Tests for sender identification in PTY-injected A2A messages.

When an agent receives a message from another agent, the PTY-injected text
should include sender identification so the receiving agent can correctly
identify who sent the message.

Format: A2A: [From: <display_name> (<sender_id>)] <message>
"""

from synapse.utils import format_a2a_message


class TestFormatA2AMessageWithSender:
    """format_a2a_message should include sender info when provided."""

    def test_no_sender_preserves_original_format(self):
        """Without sender info, format stays as before: 'A2A: <message>'."""
        result = format_a2a_message("Hello world")
        assert result == "A2A: Hello world"

    def test_no_sender_with_reply_expected(self):
        """Without sender, reply expected format unchanged."""
        result = format_a2a_message("Hello", response_mode="wait")
        assert result == "A2A: [REPLY EXPECTED] Hello"

    def test_sender_id_only(self):
        """With sender_id but no name, show sender_id."""
        result = format_a2a_message("Hello", sender_id="synapse-claude-8100")
        assert result == "A2A: [From: synapse-claude-8100] Hello"

    def test_sender_id_and_name(self):
        """With both sender_id and name, show name (sender_id)."""
        result = format_a2a_message(
            "Hello",
            sender_id="synapse-claude-8100",
            sender_name="Alice",
        )
        assert result == "A2A: [From: Alice (synapse-claude-8100)] Hello"

    def test_sender_with_reply_expected(self):
        """Sender info should appear before REPLY EXPECTED marker."""
        result = format_a2a_message(
            "What do you think?",
            response_mode="wait",
            sender_id="synapse-gemini-8110",
            sender_name="Bob",
        )
        assert result == (
            "A2A: [From: Bob (synapse-gemini-8110)] [REPLY EXPECTED] What do you think?"
        )

    def test_sender_id_with_reply_expected_no_name(self):
        """Sender ID without name + reply expected."""
        result = format_a2a_message(
            "Status?",
            response_mode="wait",
            sender_id="synapse-codex-8120",
        )
        assert result == ("A2A: [From: synapse-codex-8120] [REPLY EXPECTED] Status?")

    def test_sender_name_without_id_ignored(self):
        """If sender_name is given but no sender_id, ignore it."""
        result = format_a2a_message("Hello", sender_name="SomeName")
        assert result == "A2A: Hello"

    def test_dedup_reply_expected_with_sender(self):
        """Existing [REPLY EXPECTED] in content should be deduped."""
        result = format_a2a_message(
            "[REPLY EXPECTED] Hello",
            response_mode="wait",
            sender_id="synapse-claude-8100",
        )
        assert result == ("A2A: [From: synapse-claude-8100] [REPLY EXPECTED] Hello")


class TestSenderInfoInMetadata:
    """sender_name should be included in A2A metadata."""

    def test_sender_name_included_in_sender_info(self):
        """_extract_sender_info_from_agent should include name when available."""
        from synapse.tools.a2a import _extract_sender_info_from_agent

        info = {
            "agent_type": "claude",
            "endpoint": "http://localhost:8100",
            "name": "Alice",
        }
        result = _extract_sender_info_from_agent("synapse-claude-8100", info)

        assert result["sender_id"] == "synapse-claude-8100"
        assert result["sender_name"] == "Alice"

    def test_sender_name_absent_when_no_name(self):
        """_extract_sender_info_from_agent should omit name when not set."""
        from synapse.tools.a2a import _extract_sender_info_from_agent

        info = {
            "agent_type": "claude",
            "endpoint": "http://localhost:8100",
        }
        result = _extract_sender_info_from_agent("synapse-claude-8100", info)

        assert result["sender_id"] == "synapse-claude-8100"
        assert "sender_name" not in result


class TestSenderInfoExtraction:
    """SenderInfo dataclass should handle sender_name."""

    def test_extract_sender_name_from_metadata(self):
        """_extract_sender_info should extract sender_name."""
        from synapse.a2a_compat import _extract_sender_info

        metadata = {
            "sender": {
                "sender_id": "synapse-claude-8100",
                "sender_name": "Alice",
                "sender_endpoint": "http://localhost:8100",
            }
        }
        info = _extract_sender_info(metadata)

        assert info.sender_id == "synapse-claude-8100"
        assert info.sender_name == "Alice"

    def test_extract_sender_name_absent(self):
        """_extract_sender_info should default sender_name to None."""
        from synapse.a2a_compat import _extract_sender_info

        metadata = {
            "sender": {
                "sender_id": "synapse-claude-8100",
                "sender_endpoint": "http://localhost:8100",
            }
        }
        info = _extract_sender_info(metadata)

        assert info.sender_id == "synapse-claude-8100"
        assert info.sender_name is None


class TestLongMessageFileReference:
    """Long message file references should include sender info."""

    def test_file_reference_with_sender(self):
        """format_file_reference should include sender when provided."""
        from pathlib import Path

        from synapse.long_message import format_file_reference

        result = format_file_reference(
            Path("/tmp/test.txt"),
            sender_id="synapse-claude-8100",
            sender_name="Alice",
        )
        assert "[From: Alice (synapse-claude-8100)]" in result
        assert "[LONG MESSAGE - FILE ATTACHED]" in result

    def test_file_reference_without_sender(self):
        """format_file_reference without sender stays unchanged."""
        from pathlib import Path

        from synapse.long_message import format_file_reference

        result = format_file_reference(Path("/tmp/test.txt"))
        assert "[From:" not in result
        assert "[LONG MESSAGE - FILE ATTACHED]" in result

    def test_file_reference_with_reply_expected_and_sender(self):
        """Both reply expected and sender info should be present."""
        from pathlib import Path

        from synapse.long_message import format_file_reference

        result = format_file_reference(
            Path("/tmp/test.txt"),
            response_mode="wait",
            sender_id="synapse-gemini-8110",
        )
        assert "[From: synapse-gemini-8110]" in result
        assert "[REPLY EXPECTED]" in result


class TestPTYInjectionIncludesSender:
    """End-to-end: _send_task_message should pass sender to format_a2a_message."""

    def test_send_task_message_includes_sender_in_pty(self):
        """When a message arrives with sender metadata, PTY text includes sender."""

        # This is a structural test: verify format_a2a_message is called
        # with sender_id and sender_name extracted from metadata.
        # Full integration test would require running the FastAPI app.

        # We verify the data flow by checking SenderInfo extraction
        from synapse.a2a_compat import _extract_sender_info

        metadata = {
            "sender": {
                "sender_id": "synapse-claude-8100",
                "sender_name": "Alice",
                "sender_endpoint": "http://localhost:8100",
            },
            "response_mode": "wait",
        }
        info = _extract_sender_info(metadata)
        assert info.sender_id == "synapse-claude-8100"
        assert info.sender_name == "Alice"

        # Verify format_a2a_message produces correct output with this info
        result = format_a2a_message(
            "test message",
            response_mode="wait",
            sender_id=info.sender_id,
            sender_name=info.sender_name,
        )
        assert "[From: Alice (synapse-claude-8100)]" in result
        assert "[REPLY EXPECTED]" in result
        assert "test message" in result
