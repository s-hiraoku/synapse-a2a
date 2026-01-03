"""
Tests for refactored utility functions.

These tests verify the behavior of extracted utility functions:
- config.py: Constants for timeouts and buffer sizes
- utils.py: Message text extraction, A2A prefix formatting, timestamp generation
- a2a_client.py: Consolidated task completion wait logic
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch


class TestConfig:
    """Tests for synapse/config.py constants."""

    def test_timeout_constants_exist(self) -> None:
        """Verify timeout constants are defined."""
        from synapse.config import (
            AGENT_WAIT_TIMEOUT,
            IDENTITY_WAIT_TIMEOUT,
            OUTPUT_IDLE_THRESHOLD,
            PORT_CHECK_TIMEOUT,
            POST_WRITE_IDLE_DELAY,
            REQUEST_TIMEOUT,
            STARTUP_DELAY,
            WRITE_PROCESSING_DELAY,
        )

        assert STARTUP_DELAY == 3
        assert OUTPUT_IDLE_THRESHOLD == 1.5
        assert IDENTITY_WAIT_TIMEOUT == 10
        assert WRITE_PROCESSING_DELAY == 0.5
        assert POST_WRITE_IDLE_DELAY == 2.0
        assert REQUEST_TIMEOUT == (3, 30)
        assert PORT_CHECK_TIMEOUT == 1.0
        assert AGENT_WAIT_TIMEOUT == 60

    def test_buffer_size_constants_exist(self) -> None:
        """Verify buffer size constants are defined."""
        from synapse.config import (
            API_RESPONSE_CONTEXT_SIZE,
            CONTEXT_RECENT_SIZE,
            IDLE_CHECK_WINDOW,
            OUTPUT_BUFFER_MAX,
        )

        assert OUTPUT_BUFFER_MAX == 10000
        assert IDLE_CHECK_WINDOW == 10000
        assert CONTEXT_RECENT_SIZE == 3000
        assert API_RESPONSE_CONTEXT_SIZE == 2000


class TestUtils:
    """Tests for synapse/utils.py utility functions."""

    def test_extract_text_from_parts_with_text_parts(self) -> None:
        """Extract text from TextPart objects."""
        from synapse.utils import extract_text_from_parts

        parts = [
            {"type": "text", "text": "Hello"},
            {"type": "text", "text": "World"},
        ]
        result = extract_text_from_parts(parts)
        assert result == "Hello\nWorld"

    def test_extract_text_from_parts_with_mixed_parts(self) -> None:
        """Extract text from mixed part types, ignoring non-text."""
        from synapse.utils import extract_text_from_parts

        parts = [
            {"type": "text", "text": "Hello"},
            {"type": "file", "file": {"uri": "test.txt"}},
            {"type": "text", "text": "World"},
        ]
        result = extract_text_from_parts(parts)
        assert result == "Hello\nWorld"

    def test_extract_text_from_parts_empty(self) -> None:
        """Return empty string for no text parts."""
        from synapse.utils import extract_text_from_parts

        parts = [{"type": "file", "file": {"uri": "test.txt"}}]
        result = extract_text_from_parts(parts)
        assert result == ""

    def test_extract_text_from_parts_with_pydantic_models(self) -> None:
        """Extract text from Pydantic model objects."""
        from synapse.utils import extract_text_from_parts

        class MockTextPart:
            type = "text"
            text = "Pydantic text"

        parts = [MockTextPart()]
        result = extract_text_from_parts(parts)
        assert result == "Pydantic text"

    def test_format_a2a_message(self) -> None:
        """Format A2A message with prefix."""
        from synapse.utils import format_a2a_message

        result = format_a2a_message("task123", "sender-id", "Hello world")
        assert result == "[A2A:task123:sender-id] Hello world"

    def test_format_a2a_message_with_short_task_id(self) -> None:
        """Format A2A message with full task ID (truncation is caller's responsibility)."""
        from synapse.utils import format_a2a_message

        result = format_a2a_message("abcd1234", "synapse-system", "Message")
        assert result == "[A2A:abcd1234:synapse-system] Message"

    def test_get_iso_timestamp(self) -> None:
        """Generate ISO timestamp with Z suffix."""
        from synapse.utils import get_iso_timestamp

        result = get_iso_timestamp()
        assert result.endswith("Z")
        assert "T" in result  # ISO format has T separator

    def test_get_iso_timestamp_is_utc(self) -> None:
        """Verify timestamp is in UTC."""
        from synapse.utils import get_iso_timestamp

        result = get_iso_timestamp()
        # Parse the timestamp (remove Z suffix)
        timestamp_str = result[:-1]
        parsed = datetime.fromisoformat(timestamp_str)
        # Should be close to current UTC time
        now = datetime.now(timezone.utc)
        diff = abs((now - parsed.replace(tzinfo=timezone.utc)).total_seconds())
        assert diff < 2  # Within 2 seconds


class TestA2AClientWaitLogic:
    """Tests for consolidated task completion wait logic."""

    def test_wait_for_task_completion_success(self) -> None:
        """Wait for task to complete successfully."""
        from synapse.a2a_client import A2AClient

        client = A2AClient()

        # Mock response sequence: working -> working -> completed
        with patch("synapse.a2a_client.requests.get") as mock_get:
            mock_responses = [
                MagicMock(
                    json=lambda: {"id": "task1", "status": "working", "artifacts": []},
                    raise_for_status=lambda: None,
                ),
                MagicMock(
                    json=lambda: {
                        "id": "task1",
                        "status": "completed",
                        "artifacts": [{"type": "text"}],
                    },
                    raise_for_status=lambda: None,
                ),
            ]
            mock_get.side_effect = mock_responses

            result = client._wait_for_task_completion(
                get_task_url=lambda: "http://localhost:8100/tasks/task1",
                task_id="task1",
                timeout=5,
            )

            assert result is not None
            assert result.status == "completed"

    def test_wait_for_task_completion_timeout(self) -> None:
        """Return None when timeout expires."""
        from synapse.a2a_client import A2AClient

        client = A2AClient()

        with patch("synapse.a2a_client.requests.get") as mock_get:
            # Always return working status
            mock_get.return_value = MagicMock(
                json=lambda: {"id": "task1", "status": "working", "artifacts": []},
                raise_for_status=lambda: None,
            )

            result = client._wait_for_task_completion(
                get_task_url=lambda: "http://localhost:8100/tasks/task1",
                task_id="task1",
                timeout=1,  # Short timeout
            )

            # Should return None on timeout
            assert result is None

    def test_wait_for_task_completion_failed_state(self) -> None:
        """Stop waiting when task reaches failed state."""
        from synapse.a2a_client import A2AClient

        client = A2AClient()

        with patch("synapse.a2a_client.requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                json=lambda: {"id": "task1", "status": "failed", "artifacts": []},
                raise_for_status=lambda: None,
            )

            result = client._wait_for_task_completion(
                get_task_url=lambda: "http://localhost:8100/tasks/task1",
                task_id="task1",
                timeout=5,
            )

            assert result is not None
            assert result.status == "failed"

    def test_wait_for_task_completion_canceled_state(self) -> None:
        """Stop waiting when task is canceled."""
        from synapse.a2a_client import A2AClient

        client = A2AClient()

        with patch("synapse.a2a_client.requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                json=lambda: {"id": "task1", "status": "canceled", "artifacts": []},
                raise_for_status=lambda: None,
            )

            result = client._wait_for_task_completion(
                get_task_url=lambda: "http://localhost:8100/tasks/task1",
                task_id="task1",
                timeout=5,
            )

            assert result is not None
            assert result.status == "canceled"
