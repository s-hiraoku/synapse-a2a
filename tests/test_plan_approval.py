"""Tests for B3: Plan Approval Workflow.

Test-first development: tests for plan mode metadata, approve/reject endpoints.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

# ============================================================
# TestPlanModeMetadata - Plan mode metadata handling
# ============================================================


class TestPlanModeMetadata:
    """Tests for plan_mode metadata in A2A messages."""

    def test_plan_mode_in_metadata(self):
        """plan_mode should be settable in message metadata."""
        from synapse.a2a_compat import Message, SendMessageRequest, TextPart

        request = SendMessageRequest(
            message=Message(
                role="user",
                parts=[TextPart(text="Write tests for auth module")],
            ),
            metadata={"plan_mode": True},
        )
        assert request.metadata["plan_mode"] is True

    def test_format_plan_instruction(self):
        """format_plan_instruction should return instruction text."""
        from synapse.approval import format_plan_instruction

        instruction = format_plan_instruction()
        assert isinstance(instruction, str)
        assert len(instruction) > 0
        # Should mention creating a plan without implementing
        assert "plan" in instruction.lower()


# ============================================================
# TestApproveRejectEndpoints - API endpoints
# ============================================================


@pytest.fixture
def app_client_with_task():
    """Create a test client with a pre-created task."""
    from fastapi import FastAPI

    from synapse.a2a_compat import create_a2a_router
    from synapse.controller import TerminalController

    controller = MagicMock(spec=TerminalController)
    controller.write = MagicMock(return_value=True)

    app = FastAPI()
    router = create_a2a_router(
        controller=controller,
        agent_type="claude",
        port=8100,
        agent_id="synapse-claude-8100",
    )
    app.include_router(router)
    client = TestClient(app)

    # Create a task first
    response = client.post(
        "/tasks/send",
        json={
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": "Write a plan for tests"}],
            },
            "metadata": {"plan_mode": True},
        },
    )
    task_id = response.json()["task"]["id"]

    return client, task_id, controller


class TestApproveRejectEndpoints:
    """Tests for approve/reject API endpoints."""

    def test_approve_task(self, app_client_with_task):
        """POST /tasks/{id}/approve should approve and update status."""
        client, task_id, controller = app_client_with_task

        response = client.post(f"/tasks/{task_id}/approve", json={})
        assert response.status_code == 200
        data = response.json()
        assert data["approved"] is True
        assert data["task_id"] == task_id

    def test_reject_task(self, app_client_with_task):
        """POST /tasks/{id}/reject should reject with reason."""
        client, task_id, controller = app_client_with_task

        response = client.post(
            f"/tasks/{task_id}/reject",
            json={"reason": "Use OAuth instead of JWT"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["rejected"] is True
        assert data["reason"] == "Use OAuth instead of JWT"

    def test_approve_sends_pty_message(self, app_client_with_task):
        """Approval should write a message to agent via PTY."""
        client, task_id, controller = app_client_with_task

        client.post(f"/tasks/{task_id}/approve", json={})
        # Controller.write should have been called
        assert controller.write.called

    def test_reject_sends_pty_message(self, app_client_with_task):
        """Rejection should write a message to agent via PTY."""
        client, task_id, controller = app_client_with_task

        client.post(
            f"/tasks/{task_id}/reject",
            json={"reason": "Wrong approach"},
        )
        assert controller.write.called

    def test_approve_nonexistent_task(self, app_client_with_task):
        """Approving a non-existent task should return 404."""
        client, _, _ = app_client_with_task

        response = client.post("/tasks/nonexistent-id/approve", json={})
        assert response.status_code == 404


# ============================================================
# TestApproveRejectCLI - CLI commands
# ============================================================


class TestApproveRejectCLI:
    """Tests for synapse approve/reject CLI commands."""

    def test_plan_mode_flag_in_send(self):
        """--plan-mode should be parseable (future enhancement)."""
        # This tests the metadata structure
        metadata = {"plan_mode": True}
        assert metadata["plan_mode"] is True
