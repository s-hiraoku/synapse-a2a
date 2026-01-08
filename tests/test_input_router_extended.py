"""Extended tests for InputRouter coverage."""

from unittest.mock import MagicMock, patch

import pytest

from synapse.a2a_client import A2ATask
from synapse.input_router import InputRouter


class TestInputRouterExtended:
    """Test cases for missing coverage in input_router.py."""

    @pytest.fixture
    def router(self):
        mock_registry = MagicMock()
        mock_client = MagicMock()
        return InputRouter(
            registry=mock_registry,
            a2a_client=mock_client,
            self_agent_id="sender-1",
            self_agent_type="claude",
            self_port=8100,
        )

    def test_process_char_escape_sequences(self, router):
        """Test multi-character escape sequences (Lines 88-90)."""
        # Start escape sequence
        router.process_char("\x1b")
        assert router.in_escape_sequence is True

        # Middle of sequence
        router.process_char("[")
        assert router.in_escape_sequence is True

        # End of sequence (alphabetic character)
        router.process_char("A")
        assert router.in_escape_sequence is False

    def test_process_char_backspace_empty_buffer(self, router):
        """Test backspace behavior when buffer is empty (Line 118)."""
        router.line_buffer = ""
        output, action = router.process_char("\b")
        assert output == "\b"  # Should still echo backspace
        assert router.line_buffer == ""

    def test_process_char_quoted_message(self, router):
        """Test stripping quotes from @Agent message (Lines 139-142)."""
        # Single quotes
        router.line_buffer = "@claude 'hello world'"
        _, action = router.process_char("\n")
        assert router.pending_agent == "claude"

        with patch.object(router, "send_to_agent") as mock_send:
            action()
            mock_send.assert_called_with("claude", "hello world", True)

        # Double quotes
        router.line_buffer = '@claude "hello world"'
        _, action = router.process_char("\n")
        with patch.object(router, "send_to_agent") as mock_send:
            action()
            mock_send.assert_called_with("claude", "hello world", True)

    def test_send_to_agent_ambiguous_matches(self, router):
        """Test error path for multiple matching agents (Lines 235-251)."""
        router.registry.list_agents.return_value = {
            "synapse-claude-8100": {"agent_type": "claude", "port": 8100},
            "synapse-claude-8101": {"agent_type": "claude", "port": 8101},
        }

        result = router.send_to_agent("claude", "msg")
        assert result is False
        assert "@claude-8100" in router.ambiguous_matches
        assert "@claude-8101" in router.ambiguous_matches

    def test_send_to_agent_process_not_running(self, router):
        """Test handling when process is dead (Lines 289-296)."""
        router.registry.list_agents.return_value = {
            "synapse-claude-8100": {
                "agent_id": "synapse-claude-8100",
                "agent_type": "claude",
                "pid": 99999,
                "endpoint": "http://localhost:8100",
            }
        }

        with patch("synapse.input_router.is_process_running", return_value=False):
            result = router.send_to_agent("claude", "msg")
            assert result is False
            router.registry.unregister.assert_called_with("synapse-claude-8100")

    def test_send_to_agent_port_not_responding(self, router):
        """Test handling when port is closed (Lines 315-319)."""
        router.registry.list_agents.return_value = {
            "synapse-claude-8100": {
                "agent_type": "claude",
                "port": 8100,
                "endpoint": "http://localhost:8100",
            }
        }

        with (
            patch("synapse.input_router.is_process_running", return_value=True),
            patch("synapse.input_router.is_port_open", return_value=False),
        ):
            result = router.send_to_agent("claude", "msg")
            assert result is False

    def test_send_to_agent_no_endpoint(self, router):
        """Test handling missing endpoint (Lines 324-330)."""
        router.registry.list_agents.return_value = {
            "synapse-claude-8100": {
                "agent_type": "claude",
                "port": 8100,
                # No endpoint field
            }
        }

        with (
            patch("synapse.input_router.is_process_running", return_value=True),
            patch("synapse.input_router.is_port_open", return_value=True),
        ):
            result = router.send_to_agent("claude", "msg")
            assert result is False

    def test_send_to_agent_sender_info(self, router):
        """Test sender_info construction (Lines 336-369)."""
        router.registry.list_agents.return_value = {
            "synapse-claude-8101": {
                "agent_type": "claude",
                "port": 8101,
                "endpoint": "http://localhost:8101",
            }
        }

        router.a2a_client.send_to_local.return_value = A2ATask(id="t1", status="done")

        with (
            patch("synapse.input_router.is_process_running", return_value=True),
            patch("synapse.input_router.is_port_open", return_value=True),
        ):
            router.send_to_agent("synapse-claude-8101", "hello")

            args, kwargs = router.a2a_client.send_to_local.call_args
            sender_info = kwargs["sender_info"]
            assert sender_info["sender_id"] == "sender-1"
            assert sender_info["sender_type"] == "claude"
            assert sender_info["sender_endpoint"] == "http://localhost:8100"
