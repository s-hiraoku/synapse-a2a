"""
Integration tests for long message handling in A2A compat layer.

These tests verify that long messages are stored in files and
short messages are sent directly to PTY.
"""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from synapse.a2a_compat import (
    create_a2a_router,
)


@pytest.fixture
def mock_controller() -> MagicMock:
    """Create a mock TerminalController."""
    controller = MagicMock()
    controller.status = "IDLE"
    controller.get_context.return_value = ""
    return controller


@pytest.fixture
def mock_registry() -> MagicMock:
    """Create a mock AgentRegistry."""
    registry = MagicMock()
    return registry


@pytest.fixture
def test_client(
    mock_controller: MagicMock, mock_registry: MagicMock, tmp_path: Path
) -> TestClient:
    """Create a test client with mock dependencies."""
    # Reset the singleton for each test
    import synapse.long_message

    synapse.long_message._store_instance = None

    # Set environment variables for long message storage
    with patch.dict(
        os.environ,
        {
            "SYNAPSE_LONG_MESSAGE_DIR": str(tmp_path / "messages"),
            "SYNAPSE_LONG_MESSAGE_THRESHOLD": "100",
            "SYNAPSE_LONG_MESSAGE_TTL": "3600",
        },
    ):
        app = FastAPI()
        router = create_a2a_router(
            controller=mock_controller,
            agent_type="test",
            port=8199,
            submit_seq="\n",
            agent_id="synapse-test-8199",
            registry=mock_registry,
        )
        app.include_router(router)
        yield TestClient(app)


class TestShortMessageBypass:
    """Tests for short message direct PTY send."""

    def test_short_message_sent_directly(
        self, test_client: TestClient, mock_controller: MagicMock, tmp_path: Path
    ) -> None:
        """Short messages should be sent directly to PTY without file storage."""
        short_message = "Hello, agent!"  # Under 100 chars threshold

        response = test_client.post(
            "/tasks/send",
            json={
                "message": {
                    "role": "user",
                    "parts": [{"type": "text", "text": short_message}],
                }
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["task"]["status"] == "working"

        # Check that controller.write was called with the message
        mock_controller.write.assert_called_once()
        written_content = mock_controller.write.call_args[0][0]

        # Should contain the original message, not a file reference
        assert "A2A:" in written_content
        assert short_message in written_content
        assert "[LONG MESSAGE" not in written_content

        # No files should be created
        message_dir = tmp_path / "messages"
        if message_dir.exists():
            assert len(list(message_dir.glob("*.txt"))) == 0

    def test_message_at_threshold_not_stored(
        self, test_client: TestClient, mock_controller: MagicMock, tmp_path: Path
    ) -> None:
        """Message exactly at threshold should not need file storage."""
        # Threshold is 100 chars
        exact_message = "x" * 100

        response = test_client.post(
            "/tasks/send",
            json={
                "message": {
                    "role": "user",
                    "parts": [{"type": "text", "text": exact_message}],
                }
            },
        )

        assert response.status_code == 200

        written_content = mock_controller.write.call_args[0][0]
        assert exact_message in written_content
        assert "[LONG MESSAGE" not in written_content


class TestLongMessageFileStorage:
    """Tests for long message file storage."""

    def test_long_message_stored_in_file(
        self, test_client: TestClient, mock_controller: MagicMock, tmp_path: Path
    ) -> None:
        """Long messages should be stored in file and reference sent to PTY."""
        # Create message longer than 100 char threshold
        long_message = "This is a very long message. " * 10  # ~300 chars

        response = test_client.post(
            "/tasks/send",
            json={
                "message": {
                    "role": "user",
                    "parts": [{"type": "text", "text": long_message}],
                }
            },
        )

        assert response.status_code == 200

        # Check that controller.write was called
        mock_controller.write.assert_called_once()
        written_content = mock_controller.write.call_args[0][0]

        # Should contain file reference, not original message
        assert "[LONG MESSAGE" in written_content
        assert "stored at:" in written_content.lower()

        # Original message should NOT be in PTY write
        assert long_message not in written_content

        # File should be created
        message_dir = tmp_path / "messages"
        assert message_dir.exists()
        files = list(message_dir.glob("*.txt"))
        assert len(files) == 1

        # File should contain the full message
        file_content = files[0].read_text(encoding="utf-8")
        assert file_content == long_message

    def test_file_reference_contains_path(
        self, test_client: TestClient, mock_controller: MagicMock, tmp_path: Path
    ) -> None:
        """File reference message should contain the actual file path."""
        long_message = "y" * 200

        response = test_client.post(
            "/tasks/send",
            json={
                "message": {
                    "role": "user",
                    "parts": [{"type": "text", "text": long_message}],
                }
            },
        )

        assert response.status_code == 200

        written_content = mock_controller.write.call_args[0][0]

        # Find the file path in the reference
        message_dir = tmp_path / "messages"
        files = list(message_dir.glob("*.txt"))
        assert len(files) == 1

        # The file path should be in the written content
        assert str(files[0]) in written_content


class TestLongMessageWithMetadata:
    """Tests for long message handling with request metadata."""

    def test_long_message_with_response_expected(
        self, test_client: TestClient, mock_controller: MagicMock, tmp_path: Path
    ) -> None:
        """Long message with response_expected should still work correctly."""
        long_message = "z" * 150

        response = test_client.post(
            "/tasks/send",
            json={
                "message": {
                    "role": "user",
                    "parts": [{"type": "text", "text": long_message}],
                },
                "metadata": {
                    "response_expected": True,
                    "sender": {
                        "sender_id": "other-agent",
                        "sender_endpoint": "http://localhost:8100",
                    },
                },
            },
        )

        assert response.status_code == 200

        written_content = mock_controller.write.call_args[0][0]

        # Should have file reference with REPLY EXPECTED prefix
        assert "[LONG MESSAGE" in written_content
        assert "[REPLY EXPECTED]" in written_content

    def test_task_id_in_filename(
        self, test_client: TestClient, mock_controller: MagicMock, tmp_path: Path
    ) -> None:
        """Stored file should contain task ID for traceability."""
        long_message = "a" * 150

        response = test_client.post(
            "/tasks/send",
            json={
                "message": {
                    "role": "user",
                    "parts": [{"type": "text", "text": long_message}],
                }
            },
        )

        assert response.status_code == 200
        task_id = response.json()["task"]["id"]
        task_id_prefix = task_id[:8]

        # Check file name contains task ID prefix
        message_dir = tmp_path / "messages"
        files = list(message_dir.glob("*.txt"))
        assert len(files) == 1
        assert task_id_prefix in files[0].name


class TestLongMessageInReplyTo:
    """Tests for long message handling when replying to existing tasks."""

    def test_long_reply_stored_in_file(
        self, test_client: TestClient, mock_controller: MagicMock, tmp_path: Path
    ) -> None:
        """Long reply messages should also be stored in files."""
        # First, create a task to reply to
        initial_response = test_client.post(
            "/tasks/send",
            json={
                "message": {
                    "role": "user",
                    "parts": [{"type": "text", "text": "Hello"}],
                }
            },
        )
        assert initial_response.status_code == 200
        task_id = initial_response.json()["task"]["id"]

        # Reset mock to clear the initial call
        mock_controller.write.reset_mock()

        # Now send a long reply
        long_reply = "This is a long reply message. " * 10  # ~310 chars

        reply_response = test_client.post(
            "/tasks/send",
            json={
                "message": {
                    "role": "agent",
                    "parts": [{"type": "text", "text": long_reply}],
                },
                "metadata": {"in_reply_to": task_id},
            },
        )

        assert reply_response.status_code == 200

        # Check that controller.write was called with file reference
        mock_controller.write.assert_called_once()
        written_content = mock_controller.write.call_args[0][0]

        # Should contain file reference, not original message
        assert "[LONG MESSAGE" in written_content
        assert "stored at:" in written_content.lower()
        assert long_reply not in written_content

    def test_short_reply_sent_directly(
        self, test_client: TestClient, mock_controller: MagicMock, tmp_path: Path
    ) -> None:
        """Short reply messages should be sent directly without file storage."""
        # First, create a task to reply to
        initial_response = test_client.post(
            "/tasks/send",
            json={
                "message": {
                    "role": "user",
                    "parts": [{"type": "text", "text": "Hello"}],
                }
            },
        )
        assert initial_response.status_code == 200
        task_id = initial_response.json()["task"]["id"]

        # Reset mock
        mock_controller.write.reset_mock()

        # Send a short reply
        short_reply = "Got it, thanks!"

        reply_response = test_client.post(
            "/tasks/send",
            json={
                "message": {
                    "role": "agent",
                    "parts": [{"type": "text", "text": short_reply}],
                },
                "metadata": {"in_reply_to": task_id},
            },
        )

        assert reply_response.status_code == 200

        # Check that controller.write was called with the message directly
        mock_controller.write.assert_called_once()
        written_content = mock_controller.write.call_args[0][0]

        assert short_reply in written_content
        assert "[LONG MESSAGE" not in written_content
