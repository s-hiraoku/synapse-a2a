from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from synapse.canvas import server as server_module

workflow_router = APIRouter()


def _workflow_to_dict(wf: Any) -> dict[str, Any]:
    """Serialize a Workflow to a JSON-friendly dict."""
    return {
        "name": wf.name,
        "description": wf.description,
        "scope": wf.scope,
        "step_count": wf.step_count,
        "steps": [
            {
                "target": step.target,
                "message": step.message,
                "priority": step.priority,
                "response_mode": step.response_mode,
            }
            for step in wf.steps
        ],
    }


@workflow_router.get("/api/workflow")
async def workflow_list() -> dict[str, Any]:
    """List all workflows with full step details."""
    from synapse.workflow import WorkflowStore

    workflows: list[dict[str, Any]] = []
    try:
        store = WorkflowStore()
        for workflow in store.list_workflows():
            workflows.append(_workflow_to_dict(workflow))
    except (OSError, RuntimeError):
        server_module.logger.debug("Failed to list workflows", exc_info=True)
    return {"workflows": workflows, "project_dir": str(Path.cwd())}


@workflow_router.post("/api/workflow/run/{name}")
async def workflow_run(name: str, request: Request) -> dict[str, Any]:
    """Start a workflow execution."""
    from synapse.workflow import WorkflowStore
    from synapse.workflow_runner import run_workflow

    store = WorkflowStore()
    workflow = store.load(name)
    if workflow is None:
        raise HTTPException(status_code=404, detail=f"Workflow '{name}' not found")

    body: dict[str, Any] = {}
    with contextlib.suppress(Exception):
        body = await request.json()
    continue_on_error = body.get("continue_on_error", False)
    sender_info = {
        "sender_id": "canvas-workflow",
        "sender_name": "Workflow",
        "sender_endpoint": f"http://localhost:{request.app.state.canvas_port}",
    }

    run_id = await run_workflow(
        workflow,
        on_update=lambda: server_module._broadcast_event("workflow_update", {}),
        continue_on_error=continue_on_error,
        sender_info=sender_info,
    )
    return {"run_id": run_id, "status": "running"}


@workflow_router.get("/api/workflow/runs")
async def workflow_runs_list() -> dict[str, Any]:
    """List active and recent workflow runs."""
    from synapse.workflow_runner import get_runs

    return {"runs": [run.to_dict() for run in get_runs()]}


@workflow_router.get("/api/workflow/runs/{run_id}")
async def workflow_run_status(run_id: str) -> dict[str, Any]:
    """Get the status of a specific workflow run."""
    from synapse.workflow_runner import get_run

    run = get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    return run.to_dict()


@workflow_router.get("/api/workflow/{name}")
async def workflow_get(name: str) -> dict[str, Any]:
    """Get a single workflow by name."""
    from synapse.workflow import WorkflowStore

    store = WorkflowStore()
    workflow = store.load(name)
    if workflow is None:
        raise HTTPException(status_code=404, detail=f"Workflow '{name}' not found")
    return _workflow_to_dict(workflow)
