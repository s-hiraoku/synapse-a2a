"""Async workflow execution engine for Canvas server.

Runs workflow steps sequentially in a background asyncio task,
delegating each step to ``synapse send`` via subprocess.
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
_OUTPUT_TRUNCATE_LEN = 500


@dataclass
class StepResult:
    """Status of a single workflow step execution."""

    step_index: int
    target: str
    message: str
    status: str = "pending"  # pending | running | completed | failed
    started_at: float | None = None
    completed_at: float | None = None
    output: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        truncated = self.output[:_OUTPUT_TRUNCATE_LEN] if self.output else None
        return {
            "step_index": self.step_index,
            "target": self.target,
            "message": self.message,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "output": truncated,
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
        # Try finished runs first, then any run except *keep_id*
        victim = next(
            (
                rid
                for rid, r in _workflow_runs.items()
                if rid != keep_id and r.status != "running"
            ),
            next(
                (rid for rid in _workflow_runs if rid != keep_id),
                None,
            ),
        )
        if victim is None:
            break
        del _workflow_runs[victim]


async def run_workflow(
    workflow: Workflow,
    on_update: Callable[[], None] | None = None,
    continue_on_error: bool = False,
    sender_info: dict[str, str] | None = None,
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
        _execute_workflow(run, workflow, on_update, continue_on_error, sender_info)
    )
    task.add_done_callback(
        lambda t: t.result() if not t.cancelled() and not t.exception() else None
    )
    return run_id


_NO_AGENT_MARKER = "No agent found matching"
_DIR_MISMATCH_MARKER = "is in a different directory"


def _resolve_target_endpoint(target: str) -> str | None:
    """Resolve a workflow target to its current HTTP endpoint."""
    from synapse.canvas.server import _resolve_agent_endpoint

    return _resolve_agent_endpoint(target)


def _build_canvas_workflow_request(
    wf_step: Any,
    sender_info: dict[str, str] | None,
) -> dict[str, Any]:
    """Build a direct A2A request payload for Canvas workflow execution."""
    metadata: dict[str, Any] = {
        "response_mode": wf_step.response_mode,
        "sender_task_id": str(uuid.uuid4()),
    }
    if sender_info:
        metadata["sender"] = sender_info
    return {
        "message": {
            "role": "user",
            "parts": [{"type": "text", "text": wf_step.message}],
        },
        "metadata": metadata,
    }


async def _send_workflow_request(
    endpoint: str,
    wf_step: Any,
    sender_info: dict[str, str] | None,
) -> tuple[int, str, str]:
    """Send a workflow step directly to a target agent over A2A HTTP."""
    payload = _build_canvas_workflow_request(wf_step, sender_info)
    url = f"{endpoint.rstrip('/')}/tasks/send-priority?priority={wf_step.priority}"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as e:
        detail = e.response.text.strip() or str(e)
        return e.response.status_code, "", detail
    except httpx.HTTPError as e:
        return 1, "", str(e)

    task_data = data.get("task", data) if isinstance(data, dict) else {}
    task_id = task_data.get("id", "")
    status = task_data.get("status", "")
    if isinstance(status, dict):
        status = status.get("state", "")
    summary = "Accepted"
    if task_id:
        summary += f" task {task_id[:8]}"
    if status:
        summary += f" ({status})"
    return 0, summary, ""


def _humanize_error(target: str, stderr: str) -> str:
    """Convert raw a2a.py stderr into a user-friendly error message."""
    if _DIR_MISMATCH_MARKER in stderr:
        return (
            f"Agent '{target}' already exists in a different directory. "
            f"Cannot send because an agent with the same name is running elsewhere. "
            f"Change the workflow target name or stop the existing agent."
        )
    if _NO_AGENT_MARKER in stderr:
        return (
            f"Agent '{target}' not found. Start the agent first or enable auto_spawn."
        )
    return stderr


async def _execute_step(
    wf_step: Any,
    step: StepResult,
    *,
    workflow_auto_spawn: bool = False,
    sender_info: dict[str, str] | None = None,
) -> None:
    """Execute a single workflow step via direct A2A HTTP send."""
    endpoint = _resolve_target_endpoint(wf_step.target)
    if not endpoint:
        returncode, stdout, stderr = 404, "", _NO_AGENT_MARKER
    else:
        returncode, stdout, stderr = await _send_workflow_request(
            endpoint, wf_step, sender_info
        )

    # Auto-spawn if agent not found (step-level or workflow-level setting)
    effective_auto_spawn = wf_step.auto_spawn or workflow_auto_spawn
    if returncode != 0 and _NO_AGENT_MARKER in stderr and effective_auto_spawn:
        logger.info("Agent '%s' not found, auto-spawning...", wf_step.target)
        spawned = await asyncio.to_thread(_try_spawn_and_wait, wf_step.target)
        if spawned:
            endpoint = _resolve_target_endpoint(wf_step.target)
            if endpoint:
                returncode, stdout, stderr = await _send_workflow_request(
                    endpoint, wf_step, sender_info
                )

    if returncode == 0:
        step.status = "completed"
        step.output = stdout
    else:
        step.status = "failed"
        step.error = (
            _humanize_error(wf_step.target, stderr) or f"Exit code {returncode}"
        )
    step.completed_at = time.time()


def _try_spawn_and_wait(target: str) -> bool:
    """Spawn an agent and wait for it to register. Runs in a thread."""
    from synapse.commands.workflow import (
        _try_spawn_agent,
        _wait_for_agent,
    )

    if _try_spawn_agent(target):
        return _wait_for_agent(target)
    return False


def _notify(on_update: Callable[[], None] | None) -> None:
    """Fire the update callback if provided."""
    if on_update:
        on_update()


async def _execute_workflow(
    run: WorkflowRun,
    workflow: Workflow,
    on_update: Callable[[], None] | None,
    continue_on_error: bool,
    sender_info: dict[str, str] | None,
) -> None:
    """Execute workflow steps sequentially."""
    has_failure = False

    for i, wf_step in enumerate(workflow.steps):
        step = run.steps[i]
        step.status = "running"
        step.started_at = time.time()
        _notify(on_update)

        await _execute_step(
            wf_step,
            step,
            workflow_auto_spawn=workflow.auto_spawn,
            sender_info=sender_info,
        )

        if step.status == "failed":
            has_failure = True
            _notify(on_update)
            if not continue_on_error:
                break
            continue

        _notify(on_update)

    run.status = "failed" if has_failure else "completed"
    run.completed_at = time.time()
    _notify(on_update)
