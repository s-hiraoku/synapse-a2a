"""Tests for task ownership design.

The new design:
- Task is owned by the SENDER, not the receiver
- When sending with --response, sender creates and holds a task
- When sending with --reply-to, the reply is attached to sender's task
- Receiver does NOT create a task, just processes the message

Flow:
1. Claude sends to Codex with --response
   - Claude creates task (abc123, status=waiting)
   - Codex receives [A2A:abc123:claude] message (no task created on Codex)

2. Codex replies with --reply-to abc123
   - Claude finds task abc123, updates to completed
   - Claude's wait is released
"""

import pytest

from synapse.a2a_compat import (
    Artifact,
    Message,
    TaskStore,
    TextPart,
)
from synapse.utils import format_a2a_message

# ============================================================
# Test: Sender's task ID is included in metadata
# ============================================================


class TestSenderTaskIdInMetadata:
    """Test that sender's task ID is passed to receiver."""

    def test_request_payload_includes_sender_task_id_when_sender_endpoint_available(
        self,
    ):
        """Request payload should include sender_task_id when sender's server is available."""
        # The new design creates task on sender's SERVER (not CLI process).
        # sender_task_id is only included when sender_endpoint is in sender_info.

        from unittest.mock import MagicMock, patch

        from synapse.a2a_client import A2AClient

        # Track calls to different endpoints
        calls = {}

        def mock_post(url, json=None, **kwargs):
            calls[url] = json
            mock_response = MagicMock()
            if "/tasks/create" in url:
                mock_response.json.return_value = {
                    "task": {"id": "sender-task-123", "status": "working"}
                }
            else:
                mock_response.json.return_value = {
                    "task": {"id": "receiver-task", "status": "working"}
                }
            mock_response.raise_for_status = MagicMock()
            return mock_response

        with patch("synapse.a2a_client.requests") as mock_requests:
            mock_requests.post = mock_post

            client = A2AClient()

            # With sender_endpoint, task should be created on sender's server
            client.send_to_local(
                endpoint="http://localhost:8120",
                message="Test message",
                priority=1,
                response_expected=True,
                wait_for_completion=False,
                sender_info={
                    "sender_id": "synapse-claude-8100",
                    "sender_endpoint": "http://localhost:8100",
                },
            )

            # Verify /tasks/create was called on sender's server
            create_url = "http://localhost:8100/tasks/create"
            assert create_url in calls, (
                "/tasks/create should be called on sender's server"
            )

            # Verify sender_task_id is in the send request
            send_url = [k for k in calls if "/tasks/send-priority" in k][0]
            send_payload = calls[send_url]
            assert "sender_task_id" in send_payload["metadata"], (
                "sender_task_id should be included when sender_endpoint is available"
            )

    def test_sender_task_id_not_included_when_no_sender_endpoint(self):
        """When sender_endpoint is not available, sender_task_id is not included."""
        # Without sender_endpoint, we can't create task on sender's server

        from unittest.mock import MagicMock, patch

        from synapse.a2a_client import A2AClient

        with patch("synapse.a2a_client.requests") as mock_requests:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "task": {"id": "receiver-task", "status": "working"}
            }
            mock_response.raise_for_status = MagicMock()
            mock_requests.post.return_value = mock_response

            client = A2AClient()

            # Without sender_endpoint - task creation is skipped
            client.send_to_local(
                endpoint="http://localhost:8100",
                message="Test message",
                priority=1,
                response_expected=True,
                wait_for_completion=False,
                sender_info={"sender_id": "external-agent"},  # No sender_endpoint
            )

            # Verify the request was made
            assert mock_requests.post.called

            # Check that sender_task_id is NOT in metadata
            call_args = mock_requests.post.call_args
            payload = call_args.kwargs.get("json") or call_args[1].get("json")

            assert "metadata" in payload
            assert "sender_task_id" not in payload["metadata"], (
                "sender_task_id should NOT be included when sender_endpoint is unavailable"
            )

    def test_sender_task_not_created_when_no_response_expected(self):
        """When response_expected=False, no sender task should be created."""
        from unittest.mock import MagicMock, patch

        from synapse.a2a_client import A2AClient
        from synapse.a2a_compat import task_store

        # Count tasks before
        initial_count = len(task_store._tasks)

        with patch("synapse.a2a_client.requests") as mock_requests:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "task": {"id": "receiver-task", "status": "working"}
            }
            mock_response.raise_for_status = MagicMock()
            mock_requests.post.return_value = mock_response

            client = A2AClient()

            client.send_to_local(
                endpoint="http://localhost:8100",
                message="Test message",
                priority=1,
                response_expected=False,  # No response expected
                wait_for_completion=False,
            )

            # Verify no sender_task_id in metadata
            call_args = mock_requests.post.call_args
            payload = call_args.kwargs.get("json") or call_args[1].get("json")
            assert "sender_task_id" not in payload["metadata"], (
                "sender_task_id should NOT be included when response_expected=False"
            )

            # Count tasks after - should be same as before
            assert len(task_store._tasks) == initial_count, (
                "No new task should be created when response_expected=False"
            )


# ============================================================
# Test: Receiver displays sender's task ID in PTY
# ============================================================


class TestReceiverDisplaysSenderTaskId:
    """Test that receiver shows sender's task ID in PTY output."""

    def test_pty_output_format(self):
        """PTY output should use the correct format."""
        message = "Hello from Claude"

        formatted = format_a2a_message(message)

        # Should have A2A prefix and message content
        assert formatted == "A2A: Hello from Claude"

    def test_server_endpoint_uses_sender_task_id(self):
        """Server endpoint should use sender_task_id from metadata for PTY output."""
        from unittest.mock import MagicMock

        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from synapse.a2a_compat import create_a2a_router, task_store

        # Create a mock controller
        mock_controller = MagicMock()
        mock_controller.status = "IDLE"

        # Create router with mock controller
        router = create_a2a_router(
            controller=mock_controller,
            agent_type="test",
            port=8199,
        )

        # Clear the task store for test isolation
        task_store._tasks.clear()

        sender_task_id = "sender123"
        sender_id = "synapse-claude-8100"

        # Create FastAPI app with the router
        app = FastAPI()
        app.include_router(router)

        client = TestClient(app)

        response = client.post(
            "/tasks/send-priority?priority=1",
            json={
                "message": {
                    "role": "user",
                    "parts": [{"type": "text", "text": "Test message"}],
                },
                "metadata": {
                    "sender_task_id": sender_task_id,
                    "sender": {"sender_id": sender_id},
                    "response_expected": True,
                },
            },
        )

        assert response.status_code == 200

        # Verify controller.write was called with A2A prefixed message
        mock_controller.write.assert_called_once()
        call_args = mock_controller.write.call_args
        written_content = call_args[0][0]

        # PTY output includes A2A prefix and [REPLY EXPECTED] marker
        # when response_expected is True
        assert written_content == "A2A: [REPLY EXPECTED] Test message"


# ============================================================
# Test: TaskStore operations for sender-side tasks
# ============================================================


class TestTaskStoreForSenderTasks:
    """Test TaskStore operations for the new sender-side task model."""

    def test_create_task_for_outgoing_message(self):
        """Sender should be able to create a task for outgoing messages."""
        task_store = TaskStore()

        # Create a task for an outgoing message (sender-side)
        message = Message(role="user", parts=[TextPart(text="Please analyze this")])
        task = task_store.create(
            message,
            metadata={
                "response_expected": True,
                "direction": "outgoing",  # NEW: mark as outgoing
                "target_agent": "synapse-codex-8120",
            },
        )

        assert task.id is not None
        assert task.status == "submitted"
        assert task.metadata.get("response_expected") is True
        assert task.metadata.get("direction") == "outgoing"

    def test_update_task_status_to_waiting(self):
        """Task status can be updated to 'waiting' for response."""
        task_store = TaskStore()

        message = Message(role="user", parts=[TextPart(text="Test")])
        task = task_store.create(message, metadata={"response_expected": True})

        # Update to waiting (after message sent, waiting for reply)
        task_store.update_status(task.id, "working")

        updated = task_store.get(task.id)
        assert updated.status == "working"

    def test_complete_task_with_reply(self):
        """Task should be completable when reply arrives."""
        task_store = TaskStore()

        message = Message(role="user", parts=[TextPart(text="Analyze this")])
        task = task_store.create(message, metadata={"response_expected": True})
        task_id = task.id

        # Simulate reply arriving
        reply_content = "Here is my analysis: ..."
        task_store.add_artifact(
            task_id, Artifact(type="text", data={"content": reply_content})
        )
        task_store.update_status(task_id, "completed")

        completed = task_store.get(task_id)
        assert completed.status == "completed"
        assert len(completed.artifacts) == 1
        assert completed.artifacts[0].data["content"] == reply_content


# ============================================================
# Test: --reply-to handling
# ============================================================


class TestReplyToHandling:
    """Test that --reply-to correctly updates sender's task."""

    def test_reply_to_updates_existing_task(self):
        """--reply-to should update the original sender's task."""
        task_store = TaskStore()

        # 1. Sender creates task
        message = Message(role="user", parts=[TextPart(text="Original request")])
        sender_task = task_store.create(message, metadata={"response_expected": True})
        sender_task_id = sender_task.id
        task_store.update_status(sender_task_id, "working")

        # 2. Reply arrives with --reply-to sender_task_id
        reply_text = "Here is the response"
        task_store.add_artifact(
            sender_task_id, Artifact(type="text", data={"content": reply_text})
        )
        task_store.update_status(sender_task_id, "completed")

        # 3. Verify task is completed with artifact
        completed = task_store.get(sender_task_id)
        assert completed.status == "completed"
        assert len(completed.artifacts) == 1

    def test_reply_to_nonexistent_task_returns_none(self):
        """--reply-to with invalid task ID should return None."""
        task_store = TaskStore()

        result = task_store.get("nonexistent-task-id")
        assert result is None


# ============================================================
# Test: Full roundtrip flow
# ============================================================


class TestRoundtripFlow:
    """Test the complete roundtrip communication flow."""

    def test_complete_roundtrip_lifecycle(self):
        """Test complete lifecycle: send with --response, reply with --reply-to."""
        # Simulate sender's task store (e.g., Claude)
        sender_task_store = TaskStore()

        # 1. Sender creates task when sending with --response
        request_message = Message(
            role="user", parts=[TextPart(text="Please analyze this")]
        )
        sender_task = sender_task_store.create(
            request_message,
            metadata={
                "response_expected": True,
                "target_agent": "synapse-codex-8120",
            },
        )
        sender_task_id = sender_task.id
        sender_task_store.update_status(sender_task_id, "working")

        # Verify sender's task exists and is working
        assert sender_task_store.get(sender_task_id).status == "working"

        # 2. Message is sent to receiver with sender_task_id in metadata
        # (In real implementation, this would be in the HTTP request)
        # Metadata would contain: sender_task_id, sender info, response_expected

        # 3. Receiver processes message (NO task created on receiver side)
        # Receiver just sees the message in PTY

        # 4. Receiver sends reply with --reply-to sender_task_id
        # This updates sender's task
        reply_content = "Analysis complete: everything looks good!"
        sender_task_store.add_artifact(
            sender_task_id, Artifact(type="text", data={"content": reply_content})
        )
        sender_task_store.update_status(sender_task_id, "completed")

        # 5. Verify sender's task is completed with reply
        completed_task = sender_task_store.get(sender_task_id)
        assert completed_task.status == "completed"
        assert len(completed_task.artifacts) == 1
        assert "Analysis complete" in completed_task.artifacts[0].data["content"]

    def test_oneway_flow_no_task_retained(self):
        """Test oneway flow: send without --response, no task waiting."""
        sender_task_store = TaskStore()

        # Send without response_expected - task may be created but not retained
        # Or implementation may skip task creation entirely for oneway

        request_message = Message(
            role="user", parts=[TextPart(text="FYI: task completed")]
        )

        # For oneway, we might not create a task at all
        # Or create and immediately complete it
        task = sender_task_store.create(
            request_message,
            metadata={
                "response_expected": False,
                "direction": "outgoing",
            },
        )

        # For oneway, task could be immediately completed or skipped
        sender_task_store.update_status(task.id, "completed")

        completed = sender_task_store.get(task.id)
        assert completed.status == "completed"

    def test_end_to_end_reply_to_via_endpoint(self):
        """Test that --reply-to works via the actual API endpoint."""
        from unittest.mock import MagicMock

        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from synapse.a2a_compat import create_a2a_router, task_store

        # Clear task store
        task_store._tasks.clear()

        # Create a mock controller for the sender (Claude)
        sender_controller = MagicMock()
        sender_controller.status = "IDLE"

        # Create sender's router (Claude)
        sender_router = create_a2a_router(
            controller=sender_controller,
            agent_type="claude",
            port=8100,
        )

        # Create sender's app
        sender_app = FastAPI()
        sender_app.include_router(sender_router)
        sender_client = TestClient(sender_app)

        # Step 1: Create a sender task (simulating --response flag)
        # This is what A2AClient.send_to_local does when response_expected=True
        from synapse.a2a_compat import Message as A2AMessage
        from synapse.a2a_compat import TextPart as A2ATextPart

        sender_message = A2AMessage(
            role="user", parts=[A2ATextPart(text="Please analyze this code")]
        )
        sender_task = task_store.create(
            sender_message,
            metadata={"response_expected": True, "direction": "outgoing"},
        )
        sender_task_id = sender_task.id
        task_store.update_status(sender_task_id, "working")

        # Verify sender task is waiting
        assert task_store.get(sender_task_id).status == "working"

        # Step 2: Receiver (Codex) sends reply with --reply-to
        # This hits the sender's (Claude's) endpoint
        reply_response = sender_client.post(
            "/tasks/send-priority?priority=1",
            json={
                "message": {
                    "role": "user",
                    "parts": [{"type": "text", "text": "Analysis: Code looks good!"}],
                },
                "metadata": {
                    "in_reply_to": sender_task_id,  # Key: this is the --reply-to value
                    "sender": {"sender_id": "synapse-codex-8120"},
                },
            },
        )

        # Should succeed
        assert reply_response.status_code == 200

        # Step 3: Verify the sender's task is now completed
        completed_task = task_store.get(sender_task_id)
        assert completed_task is not None
        assert completed_task.status == "completed"
        assert len(completed_task.artifacts) == 1
        assert "Code looks good" in completed_task.artifacts[0].data["content"]


# ============================================================
# Test: Error scenarios
# ============================================================


class TestErrorScenarios:
    """Test error handling for task ownership."""

    def test_reply_to_expired_task(self):
        """Reply to an expired/cleaned task should handle gracefully."""
        task_store = TaskStore()

        # Task doesn't exist (expired or never existed)
        result = task_store.get("expired-task-id")
        assert result is None

        # Attempting to add artifact to non-existent task
        result = task_store.add_artifact(
            "expired-task-id", Artifact(type="text", data={"content": "Reply"})
        )
        assert result is None

    def test_duplicate_reply_handling(self):
        """Multiple replies to the same task should be handled."""
        task_store = TaskStore()

        message = Message(role="user", parts=[TextPart(text="Request")])
        task = task_store.create(message, metadata={"response_expected": True})
        task_id = task.id

        # First reply
        task_store.add_artifact(
            task_id, Artifact(type="text", data={"content": "First reply"})
        )

        # Second reply (duplicate or follow-up)
        task_store.add_artifact(
            task_id, Artifact(type="text", data={"content": "Second reply"})
        )

        task = task_store.get(task_id)
        # Both artifacts should be stored
        assert len(task.artifacts) == 2


# ============================================================
# Integration test placeholder
# ============================================================


class TestIntegration:
    """Integration tests for the full system (placeholder)."""

    @pytest.mark.skip(reason="Requires running agents")
    def test_real_roundtrip_between_agents(self):
        """Test real roundtrip between two running agents."""
        # This would test:
        # 1. Start Claude and Codex agents
        # 2. Claude sends to Codex with --response
        # 3. Codex receives message with sender_task_id
        # 4. Codex replies with --reply-to sender_task_id
        # 5. Claude's wait is released with the reply
        pass
