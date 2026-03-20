"""Async workflow execution engine for Canvas server.

Runs workflow steps sequentially in a background asyncio task,
sending each step to the target agent via A2A protocol.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

from synapse.workflow import Workflow

logger = logging.getLogger(__name__)

MAX_RUNS = 50


@dataclass
class StepResult:
    """Status of a single workflow step execution."""

    step_index: int
    target: str
    message: str
    status: str = "pending"  # pending | running | completed | failed
    started_at: float | None = None
    completed_at: float | None = None
    task_id: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_index": self.step_index,
            "target": self.target,
            "message": self.message,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "task_id": self.task_id,
            "error": self.error,
        }


@dataclass
class WorkflowRun:
    """Tracks a single workflow execution."""

    run_id: str
    workflow_name: str
    steps: list[StepResult]
    status: str = "running"  # running | completed | failed
    started_at: float = field(default_factory=time.time)
    completed_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "workflow_name": self.workflow_name,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "steps": [s.to_dict() for s in self.steps],
        }


# In-memory run storage with LRU eviction
_workflow_runs: OrderedDict[str, WorkflowRun] = OrderedDict()


def get_runs() -> list[WorkflowRun]:
    """Return all tracked runs, most recent first."""
    return list(reversed(_workflow_runs.values()))


def get_run(run_id: str) -> WorkflowRun | None:
    """Return a specific run by ID."""
    return _workflow_runs.get(run_id)


def _evict_old_runs(keep_id: str | None = None) -> None:
    """Remove oldest finished runs when over MAX_RUNS.

    Prefers evicting completed/failed runs. Falls back to oldest run
    if all are still running, but never evicts *keep_id*.
    """
    while len(_workflow_runs) > MAX_RUNS:
        # Prefer evicting non-running runs first
        evicted = False
        for rid, run in _workflow_runs.items():
            if rid != keep_id and run.status != "running":
                del _workflow_runs[rid]
                evicted = True
                break
        if not evicted:
            # Fall back: evict oldest run that isn't the one we just created
            for rid in _workflow_runs:
                if rid != keep_id:
                    del _workflow_runs[rid]
                    evicted = True
                    break
        if not evicted:
            break


async def run_workflow(
    workflow: Workflow,
    resolve_endpoint: Callable[[str], str | None],
    canvas_port: int,
    on_update: Callable[[], None] | None = None,
    continue_on_error: bool = False,
) -> str:
    """Start a workflow execution in the background.

    Returns the run_id immediately. The workflow runs asynchronously.
    """
    run_id = str(uuid.uuid4())
    steps = [
        StepResult(step_index=i, target=s.target, message=s.message)
        for i, s in enumerate(workflow.steps)
    ]
    run = WorkflowRun(run_id=run_id, workflow_name=workflow.name, steps=steps)
    _workflow_runs[run_id] = run
    _evict_old_runs(keep_id=run_id)

    task = asyncio.create_task(
        _execute_workflow(
            run,
            workflow,
            resolve_endpoint,
            canvas_port,
            on_update,
            continue_on_error,
        )
    )
    task.add_done_callback(
        lambda t: t.result() if not t.cancelled() and not t.exception() else None
    )
    return run_id


async def _execute_workflow(
    run: WorkflowRun,
    workflow: Workflow,
    resolve_endpoint: Callable[[str], str | None],
    canvas_port: int,
    on_update: Callable[[], None] | None,
    continue_on_error: bool,
) -> None:
    """Execute workflow steps sequentially."""
    has_failure = False

    async with httpx.AsyncClient(timeout=30.0) as client:
        for i, wf_step in enumerate(workflow.steps):
            step = run.steps[i]
            endpoint = resolve_endpoint(wf_step.target)
            if not endpoint:
                step.status = "failed"
                step.error = f"Agent '{wf_step.target}' not found"
                step.started_at = time.time()
                step.completed_at = step.started_at
                has_failure = True
                if on_update:
                    on_update()
                if not continue_on_error:
                    break
                continue

            step.status = "running"
            step.started_at = time.time()
            if on_update:
                on_update()

            try:
                task_id = str(uuid.uuid4())
                a2a_request = {
                    "message": {
                        "role": "user",
                        "parts": [{"type": "text", "text": wf_step.message}],
                    },
                    "metadata": {
                        "response_mode": wf_step.response_mode,
                        "sender": {
                            "sender_id": "canvas-workflow",
                            "sender_name": "Workflow",
                            "sender_endpoint": f"http://localhost:{canvas_port}",
                        },
                        "sender_task_id": task_id,
                    },
                }
                resp = await client.post(
                    f"{endpoint}/tasks/send",
                    json=a2a_request,
                )
                resp.raise_for_status()

                step.task_id = task_id
                step.status = "completed"
                step.completed_at = time.time()
            except Exception as e:
                step.status = "failed"
                step.error = str(e)
                step.completed_at = time.time()
                has_failure = True
                if not continue_on_error:
                    if on_update:
                        on_update()
                    break

            if on_update:
                on_update()

    run.status = "failed" if has_failure else "completed"
    run.completed_at = time.time()
    if on_update:
        on_update()
