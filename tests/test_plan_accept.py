"""Tests for Plan accept → Task Board integration and progress sync."""

from __future__ import annotations

import json

from synapse.canvas.store import CanvasStore
from synapse.task_board import TaskBoard


def _create_plan_card(store: CanvasStore, plan_id: str = "plan-test") -> dict:
    """Create a plan card in the Canvas store for testing."""
    template_data = {
        "plan_id": plan_id,
        "status": "proposed",
        "mermaid": "graph TD\n  A[Design] --> B[Implement]\n  B --> C[Test]",
        "steps": [
            {
                "id": "step-1",
                "subject": "Design auth",
                "agent": "claude",
                "status": "pending",
                "blocked_by": [],
            },
            {
                "id": "step-2",
                "subject": "Implement auth",
                "agent": "codex",
                "status": "pending",
                "blocked_by": ["step-1"],
            },
            {
                "id": "step-3",
                "subject": "Test auth",
                "agent": "gemini",
                "status": "pending",
                "blocked_by": ["step-2"],
            },
        ],
    }

    return store.upsert_card(
        card_id=plan_id,
        agent_id="synapse-claude-8100",
        content=json.dumps({"format": "plan", "body": {}}, ensure_ascii=False),
        title="Plan: Auth Migration",
        pinned=True,
        template="plan",
        template_data=template_data,
    )


class TestAcceptPlan:
    """Tests for accept_plan: Plan Card → Task Board registration."""

    def test_accept_plan_creates_tasks(self, tmp_path):
        """Accepting a plan should create tasks in the Task Board."""
        from synapse.commands.canvas import accept_plan

        canvas_db = str(tmp_path / "canvas.db")
        board_db = str(tmp_path / "board.db")

        store = CanvasStore(db_path=canvas_db)
        board = TaskBoard(db_path=board_db)
        _create_plan_card(store, "plan-auth")

        result = accept_plan("plan-auth", canvas_db=canvas_db, board_db=board_db)

        assert result is not None
        assert result["plan_id"] == "plan-auth"
        assert len(result["task_ids"]) == 3

        # Verify tasks exist in board
        tasks = board.list_tasks()
        assert len(tasks) == 3
        subjects = [t["subject"] for t in tasks]
        assert "Design auth" in subjects
        assert "Implement auth" in subjects
        assert "Test auth" in subjects

    def test_accept_plan_sets_dependencies(self, tmp_path):
        """Tasks created from plan should have correct blocked_by relationships."""
        from synapse.commands.canvas import accept_plan

        canvas_db = str(tmp_path / "canvas.db")
        board_db = str(tmp_path / "board.db")

        store = CanvasStore(db_path=canvas_db)
        board = TaskBoard(db_path=board_db)
        _create_plan_card(store, "plan-dep")

        result = accept_plan("plan-dep", canvas_db=canvas_db, board_db=board_db)

        # step-1 should have no blockers
        step1_id = result["step_to_task"]["step-1"]
        step2_id = result["step_to_task"]["step-2"]
        step3_id = result["step_to_task"]["step-3"]

        tasks_by_id = {t["id"]: t for t in board.list_tasks()}

        blocked_1 = tasks_by_id[step1_id]["blocked_by"]
        blocked_2 = tasks_by_id[step2_id]["blocked_by"]
        blocked_3 = tasks_by_id[step3_id]["blocked_by"]

        assert blocked_1 == []
        assert step1_id in blocked_2
        assert step2_id in blocked_3

    def test_accept_plan_sets_assignee_hint(self, tmp_path):
        """Tasks should have assignee_hint from suggested agent."""
        from synapse.commands.canvas import accept_plan

        canvas_db = str(tmp_path / "canvas.db")
        board_db = str(tmp_path / "board.db")

        store = CanvasStore(db_path=canvas_db)
        board = TaskBoard(db_path=board_db)
        _create_plan_card(store, "plan-hint")

        result = accept_plan("plan-hint", canvas_db=canvas_db, board_db=board_db)

        tasks_by_id = {t["id"]: t for t in board.list_tasks()}
        step1_id = result["step_to_task"]["step-1"]

        assert tasks_by_id[step1_id].get("assignee_hint") == "claude"

    def test_accept_plan_updates_card_status(self, tmp_path):
        """Accepting plan should update Canvas card status to 'active'."""
        from synapse.commands.canvas import accept_plan

        canvas_db = str(tmp_path / "canvas.db")
        board_db = str(tmp_path / "board.db")

        store = CanvasStore(db_path=canvas_db)
        TaskBoard(db_path=board_db)
        _create_plan_card(store, "plan-status")

        accept_plan("plan-status", canvas_db=canvas_db, board_db=board_db)

        card = store.get_card("plan-status")
        assert card is not None
        td = (
            json.loads(card["template_data"])
            if isinstance(card["template_data"], str)
            else card["template_data"]
        )
        assert td["status"] == "active"

    def test_accept_plan_not_found(self, tmp_path):
        """Accepting a non-existent plan should return None."""
        from synapse.commands.canvas import accept_plan

        canvas_db = str(tmp_path / "canvas.db")
        board_db = str(tmp_path / "board.db")

        CanvasStore(db_path=canvas_db)
        TaskBoard(db_path=board_db)

        result = accept_plan("nonexistent", canvas_db=canvas_db, board_db=board_db)
        assert result is None

    def test_accept_plan_sets_priority(self, tmp_path):
        """Tasks should inherit priority from plan steps if present."""
        from synapse.commands.canvas import accept_plan

        canvas_db = str(tmp_path / "canvas.db")
        board_db = str(tmp_path / "board.db")

        store = CanvasStore(db_path=canvas_db)
        board = TaskBoard(db_path=board_db)
        _create_plan_card(store, "plan-prio")

        accept_plan("plan-prio", canvas_db=canvas_db, board_db=board_db)

        # Default priority should be 3
        tasks = board.list_tasks()
        for t in tasks:
            assert t["priority"] == 3


class TestPlanProgressSync:
    """Tests for Task Board → Canvas Plan Card progress sync."""

    def test_sync_updates_step_statuses(self, tmp_path):
        """Completing a task should update the corresponding step status in the Plan Card."""
        from synapse.commands.canvas import accept_plan, sync_plan_progress

        canvas_db = str(tmp_path / "canvas.db")
        board_db = str(tmp_path / "board.db")

        store = CanvasStore(db_path=canvas_db)
        board = TaskBoard(db_path=board_db)
        _create_plan_card(store, "plan-sync")

        result = accept_plan("plan-sync", canvas_db=canvas_db, board_db=board_db)
        step1_id = result["step_to_task"]["step-1"]

        # Claim and complete step-1
        board.claim_task(step1_id, "synapse-claude-8100")
        board.complete_task(step1_id, "synapse-claude-8100")

        # Sync progress
        sync_plan_progress("plan-sync", canvas_db=canvas_db, board_db=board_db)

        card = store.get_card("plan-sync")
        td = (
            json.loads(card["template_data"])
            if isinstance(card["template_data"], str)
            else card["template_data"]
        )

        step_statuses = {s["id"]: s["status"] for s in td["steps"]}
        assert step_statuses["step-1"] == "completed"

    def test_sync_marks_plan_completed_when_all_done(self, tmp_path):
        """Plan status should change to 'completed' when all steps are done."""
        from synapse.commands.canvas import accept_plan, sync_plan_progress

        canvas_db = str(tmp_path / "canvas.db")
        board_db = str(tmp_path / "board.db")

        store = CanvasStore(db_path=canvas_db)
        board = TaskBoard(db_path=board_db)
        _create_plan_card(store, "plan-done")

        result = accept_plan("plan-done", canvas_db=canvas_db, board_db=board_db)

        # Complete all tasks
        for step_id in ["step-1", "step-2", "step-3"]:
            task_id = result["step_to_task"][step_id]
            board.claim_task(task_id, "agent")
            board.complete_task(task_id, "agent")

        sync_plan_progress("plan-done", canvas_db=canvas_db, board_db=board_db)

        card = store.get_card("plan-done")
        td = (
            json.loads(card["template_data"])
            if isinstance(card["template_data"], str)
            else card["template_data"]
        )
        assert td["status"] == "completed"
