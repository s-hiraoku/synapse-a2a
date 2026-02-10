"""Tests for B1: Shared Task Board - API endpoints.

Test-first development: these tests define the expected A2A API behavior.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app_client(tmp_path):
    """Create a FastAPI test client with task board enabled."""
    import os

    os.environ["SYNAPSE_TASK_BOARD_DB_PATH"] = str(tmp_path / "task_board.db")
    os.environ["SYNAPSE_TASK_BOARD_ENABLED"] = "true"

    from fastapi import FastAPI

    from synapse.a2a_compat import create_a2a_router

    app = FastAPI()
    router = create_a2a_router(
        controller=None,
        agent_type="claude",
        port=8100,
        agent_id="synapse-claude-8100",
    )
    app.include_router(router)
    yield TestClient(app)

    # Cleanup
    os.environ.pop("SYNAPSE_TASK_BOARD_DB_PATH", None)
    os.environ.pop("SYNAPSE_TASK_BOARD_ENABLED", None)


class TestTaskBoardEndpoints:
    """Tests for task board API endpoints."""

    def test_get_task_board_empty(self, app_client):
        """GET /tasks/board should return empty list initially."""
        response = app_client.get("/tasks/board")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        assert "tasks" in data
        assert len(data["tasks"]) == 0

    def test_create_task_via_api(self, app_client):
        """POST /tasks/board should create a task."""
        response = app_client.post(
            "/tasks/board",
            json={
                "subject": "Write tests",
                "description": "Unit tests for auth",
                "created_by": "synapse-claude-8100",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["status"] == "pending"

    def test_claim_task_via_api(self, app_client):
        """POST /tasks/board/{id}/claim should claim a task."""
        # Create task first
        create_resp = app_client.post(
            "/tasks/board",
            json={
                "subject": "Test",
                "description": "",
                "created_by": "claude",
            },
        )
        task_id = create_resp.json()["id"]

        # Claim it
        response = app_client.post(
            f"/tasks/board/{task_id}/claim",
            json={"agent_id": "synapse-claude-8100"},
        )
        assert response.status_code == 200
        assert response.json()["claimed"] is True

    def test_complete_task_via_api(self, app_client):
        """POST /tasks/board/{id}/complete should complete a task."""
        # Create and claim
        create_resp = app_client.post(
            "/tasks/board",
            json={
                "subject": "Test",
                "description": "",
                "created_by": "claude",
            },
        )
        task_id = create_resp.json()["id"]
        app_client.post(
            f"/tasks/board/{task_id}/claim",
            json={"agent_id": "synapse-claude-8100"},
        )

        # Complete
        response = app_client.post(
            f"/tasks/board/{task_id}/complete",
            json={"agent_id": "synapse-claude-8100"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "unblocked" in data
