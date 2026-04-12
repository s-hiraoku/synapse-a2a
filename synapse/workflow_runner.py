"""Async workflow execution engine for Canvas server.

Runs workflow steps sequentially in a background asyncio task,
delegating each step to ``synapse send`` via subprocess.

Phase 2a: Runs are persisted to SQLite via :class:`WorkflowRunDB` so that
execution history survives server restarts. Active (running) runs are also
kept in an in-memory cache for low-latency reads.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
import subprocess
import time
import uuid
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

from synapse.config import BLOCKING_TASK_STATES
from synapse.registry import AgentRegistry
from synapse.tools.a2a_helpers import _normalize_working_dir
from synapse.workflow import Workflow, WorkflowError
from synapse.workflow_db import WorkflowRunDB

logger = logging.getLogger(__name__)

MAX_RUNS = 50
_OUTPUT_TRUNCATE_LEN = 500
_POLL_TIMEOUT = 600.0  # 10 min max wait per step
_SEND_MAX_RETRIES = 5
_SEND_RETRY_INTERVAL = 2.0
_HELPER_ENV_MARKER = "SYNAPSE_WORKFLOW_HELPER"
_HELPER_PARENT_ENV = "SYNAPSE_WORKFLOW_HELPER_PARENT"
_HELPER_DEPTH_ENV = "SYNAPSE_WORKFLOW_HELPER_DEPTH"
_MAX_HELPER_DEPTH = 1

# Lazily initialised DB singleton — set to None for tests that don't need it.
_db: WorkflowRunDB | None = None


def _get_db() -> WorkflowRunDB:
    """Return (and lazily create) the module-level DB singleton."""
    global _db
    if _db is None:
        _db = WorkflowRunDB()
    return _db


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

    def to_dict(self, *, truncate: bool = True) -> dict[str, Any]:
        output = (
            self.output[:_OUTPUT_TRUNCATE_LEN]
            if truncate and self.output
            else self.output
        )
        return {
            "step_index": self.step_index,
            "target": self.target,
            "message": self.message,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "output": output,
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

    def to_db_dict(self) -> dict[str, Any]:
        """Produce a dict for DB persistence (non-truncated output)."""
        return {
            "run_id": self.run_id,
            "workflow_name": self.workflow_name,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "steps": [s.to_dict(truncate=False) for s in self.steps],
        }


@dataclass
class _WorkflowHelper:
    """Lazy helper-agent runner for ``target: self`` workflow steps."""

    workflow_name: str
    sender_info: dict[str, str] | None
    agent_name: str = field(init=False)
    agent_id: str | None = None
    endpoint: str | None = None
    _spawn_attempted: bool = field(default=False, init=False)
    _killed: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        self.agent_name = f"wf-helper-{self.workflow_name}-{uuid.uuid4().hex[:8]}"

    async def execute_step(self, wf_step: Any, step: StepResult) -> None:
        """Run a self-target step through the helper agent."""
        ready, error = await self._ensure_started()
        if not ready:
            step.status = "failed"
            step.error = error or "Failed to start workflow helper"
            step.completed_at = time.time()
            return

        assert self.endpoint is not None
        if not await _wait_for_helper_idle(self.endpoint):
            step.status = "failed"
            step.error = "Helper agent did not become idle in time"
            step.completed_at = time.time()
            return
        returncode, stdout, stderr, task_id = await _send_workflow_request(
            self.endpoint, wf_step, self.sender_info
        )

        await _apply_task_result(
            step,
            returncode,
            stdout,
            stderr,
            task_id,
            wf_step,
            self.endpoint,
        )

    async def _ensure_started(self) -> tuple[bool, str | None]:
        if self.endpoint:
            return True, None
        if self._spawn_attempted:
            return False, "Workflow helper is unavailable"

        self._spawn_attempted = True
        sender_info = self.sender_info or {}
        agent_type = sender_info.get("agent_type")
        parent_agent_id = sender_info.get("agent_id")
        working_dir = sender_info.get("working_dir") or os.getcwd()
        if not agent_type or not parent_agent_id:
            return False, "Self-target workflow steps require sender metadata"

        extra_env = {
            _HELPER_ENV_MARKER: "1",
            _HELPER_PARENT_ENV: parent_agent_id,
            _HELPER_DEPTH_ENV: "1",
        }

        try:
            result = await asyncio.to_thread(
                self._spawn_helper_agent,
                agent_type,
                working_dir,
                extra_env,
            )
        except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
            logger.warning(
                "Failed to spawn workflow helper for %s: %s",
                self.workflow_name,
                exc,
            )
            return False, str(exc)

        if result.status != "submitted":
            return False, f"Helper spawn returned status '{result.status}'"

        self.agent_id = result.agent_id
        ready = await asyncio.to_thread(self._wait_for_registration)
        if not ready:
            return False, "Workflow helper did not register in time"

        endpoint = _resolve_target_endpoint(self.agent_name)
        if endpoint is None and self.agent_id:
            endpoint = _resolve_target_endpoint(self.agent_id)
        if endpoint is None:
            return False, "Workflow helper endpoint could not be resolved"

        self.endpoint = endpoint
        return True, None

    def _spawn_helper_agent(
        self,
        agent_type: str,
        working_dir: str,
        extra_env: dict[str, str],
    ) -> Any:
        from synapse.spawn import execute_spawn, prepare_spawn

        prepared = prepare_spawn(
            profile=agent_type,
            name=self.agent_name,
            role=f"workflow helper for {self.workflow_name}",
            extra_env=extra_env,
            worktree=False,
            auto_approve=True,
        )
        prepared.cwd = working_dir
        return execute_spawn([prepared], layout="auto")[0]

    def _wait_for_registration(self) -> bool:
        from synapse.commands.workflow import _wait_for_agent

        return _wait_for_agent(self.agent_name)

    def kill(self) -> None:
        """Terminate the helper agent if it was spawned."""
        if self._killed:
            return
        self._killed = True

        try:
            subprocess.run(
                ["synapse", "kill", self.agent_name, "-f"],
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError):
            logger.warning(
                "Failed to kill workflow helper %s", self.agent_name, exc_info=True
            )

        if self.agent_id:
            try:
                AgentRegistry().unregister(self.agent_id)
            except (OSError, KeyError):
                logger.debug(
                    "Workflow helper unregister cleanup failed for %s",
                    self.agent_id,
                    exc_info=True,
                )


# In-memory run storage with LRU eviction
_workflow_runs: OrderedDict[str, WorkflowRun] = OrderedDict()


def get_runs() -> list[WorkflowRun]:
    """Return all tracked runs, most recent first.

    Merges in-memory cache (authoritative for active runs) with
    persisted DB history. In-memory entries take precedence.
    """
    cached = list(reversed(_workflow_runs.values()))
    try:
        db = _get_db()
        db_runs = db.get_runs()
    except (OSError, sqlite3.Error, KeyError, TypeError, ValueError):
        logger.debug("Failed to read workflow runs from DB", exc_info=True)
        return cached

    cached_ids = {r.run_id for r in cached}
    merged: list[WorkflowRun] = list(cached)
    for d in db_runs:
        if d["run_id"] not in cached_ids:
            merged.append(_dict_to_run(d))
    # Sort most recent first
    merged.sort(key=lambda r: r.started_at, reverse=True)
    return merged


def get_run(run_id: str) -> WorkflowRun | None:
    """Return a specific run by ID (cache first, then DB)."""
    cached = _workflow_runs.get(run_id)
    if cached is not None:
        return cached
    try:
        db = _get_db()
        d = db.get_run(run_id)
        if d is not None:
            return _dict_to_run(d)
    except (OSError, sqlite3.Error, KeyError, TypeError, ValueError):
        logger.debug("Failed to read run %s from DB", run_id, exc_info=True)
    return None


def _dict_to_run(d: dict[str, Any]) -> WorkflowRun:
    """Reconstruct a WorkflowRun from a DB dict."""
    steps = [
        StepResult(
            step_index=s["step_index"],
            target=s["target"],
            message=s["message"],
            status=s["status"],
            started_at=s.get("started_at"),
            completed_at=s.get("completed_at"),
            output=s.get("output"),
            error=s.get("error"),
        )
        for s in d.get("steps", [])
    ]
    run = WorkflowRun(
        run_id=d["run_id"],
        workflow_name=d["workflow_name"],
        steps=steps,
        status=d["status"],
        started_at=d["started_at"],
    )
    run.completed_at = d.get("completed_at")
    return run


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
    _raise_if_helper_execution_forbidden()

    run_id = str(uuid.uuid4())
    steps = [
        StepResult(step_index=i, target=s.target, message=s.message)
        for i, s in enumerate(workflow.steps)
    ]
    run = WorkflowRun(run_id=run_id, workflow_name=workflow.name, steps=steps)
    _workflow_runs[run_id] = run
    _evict_old_runs(keep_id=run_id)

    # Persist initial run state to DB
    try:
        _get_db().save_run(run.to_db_dict())
    except (OSError, sqlite3.Error):
        logger.debug("Failed to persist new run %s to DB", run_id, exc_info=True)

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


def _is_self_target(
    target: str,
    sender_info: dict[str, str] | None,
) -> bool:
    """Whether a workflow target refers to the current agent."""
    if not sender_info or not target:
        return False

    sender_id = sender_info.get("agent_id") or sender_info.get("sender_id")
    sender_type = sender_info.get("agent_type") or sender_info.get("sender_type")
    if target == "self":
        return True
    if sender_id and target == sender_id:
        return True
    if not sender_type or target != sender_type:
        return False

    sender_dir = _normalize_working_dir(
        sender_info.get("working_dir") or sender_info.get("sender_working_dir")
    )
    agents = AgentRegistry().list_agents().values()
    same_type = [
        agent
        for agent in agents
        if agent.get("agent_type") == sender_type
        and _normalize_working_dir(agent.get("working_dir")) == sender_dir
    ]
    if len(same_type) == 1 and same_type[0].get("agent_id") == sender_id:
        logger.warning(
            "Workflow target '%s' auto-detected as self for agent %s",
            target,
            sender_id,
        )
        return True
    return False


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


def _extract_task_data(data: dict[str, Any]) -> dict[str, Any]:
    """Unwrap the ``{"task": {...}}`` envelope returned by A2A endpoints."""
    result: dict[str, Any] = data.get("task", data) if isinstance(data, dict) else {}
    return result


def _extract_task_status(task_data: dict[str, Any]) -> str:
    """Return the scalar status string from a task dict.

    Handles both ``"status": "completed"`` and ``"status": {"state": "completed"}``.
    """
    status = task_data.get("status", "")
    if isinstance(status, dict):
        return str(status.get("state", ""))
    return str(status)


def _extract_task_output(task_data: dict) -> str:
    """Extract text output from task artifacts."""
    parts: list[str] = []
    for artifact in task_data.get("artifacts", []):
        for part in artifact.get("parts", []):
            if part.get("type") == "text":
                parts.append(part.get("text", ""))
    return "\n".join(parts) if parts else ""


async def _poll_task_completion(
    endpoint: str,
    task_id: str,
) -> tuple[str, str]:
    """Poll target agent's task until terminal state. Returns (status, output)."""
    from synapse.config import COMPLETED_TASK_STATES, TASK_POLL_INTERVAL

    url = f"{endpoint.rstrip('/')}/tasks/{task_id}"
    deadline = time.time() + _POLL_TIMEOUT

    async with httpx.AsyncClient(timeout=10.0) as client:
        while time.time() < deadline:
            try:
                resp = await client.get(url)
                if resp.status_code == 404:
                    return "completed", ""  # task not tracked
                resp.raise_for_status()
                task_data = _extract_task_data(resp.json())
                status = _extract_task_status(task_data)
                if status in COMPLETED_TASK_STATES:
                    return status, _extract_task_output(task_data)
                if status == "input_required":
                    return "failed", (
                        "Agent requires permission approval"
                        " — check auto-approve configuration"
                    )
            except httpx.HTTPError:
                pass
            await asyncio.sleep(TASK_POLL_INTERVAL)

    return "completed", ""  # timeout → best-effort complete


def _has_working_tasks(tasks_data: Any) -> bool:
    """Return True when a /tasks payload contains any working tasks."""
    if isinstance(tasks_data, list):
        task_list = tasks_data
    elif isinstance(tasks_data, dict):
        task_list = tasks_data.get("tasks", [])
    else:
        task_list = []

    for task in task_list:
        if not isinstance(task, dict):
            continue
        if _extract_task_status(task) in BLOCKING_TASK_STATES:
            return True
    return False


async def _wait_for_helper_idle(endpoint: str) -> bool:
    """Wait until the helper has no working tasks.

    Fails fast if the helper becomes unreachable (3 consecutive connection
    errors), rather than waiting the full poll timeout.
    """
    deadline = time.time() + _POLL_TIMEOUT
    consecutive_errors = 0
    max_consecutive_errors = 3

    async with httpx.AsyncClient(timeout=5.0) as client:
        while time.time() < deadline:
            try:
                response = await client.get(f"{endpoint.rstrip('/')}/tasks")
                consecutive_errors = 0  # reset on any successful response
                if response.status_code == 200 and not _has_working_tasks(
                    response.json()
                ):
                    return True
            except httpx.HTTPError:
                consecutive_errors += 1
                if consecutive_errors >= max_consecutive_errors:
                    logger.warning(
                        "Helper at %s unreachable after %d attempts, giving up",
                        endpoint,
                        consecutive_errors,
                    )
                    return False
            await asyncio.sleep(3.0)

    return False


async def _send_workflow_request(
    endpoint: str,
    wf_step: Any,
    sender_info: dict[str, str] | None,
) -> tuple[int, str, str, str]:
    """Send a workflow step directly to a target agent over A2A HTTP.

    Returns (returncode, output, error, task_id).
    """
    payload = _build_canvas_workflow_request(wf_step, sender_info)
    url = f"{endpoint.rstrip('/')}/tasks/send-priority?priority={wf_step.priority}"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = None
            for _attempt in range(_SEND_MAX_RETRIES):
                response = await client.post(url, json=payload)
                if response.status_code == 409:
                    await asyncio.sleep(_SEND_RETRY_INTERVAL)
                    continue
                response.raise_for_status()
                break
            else:
                # All retries exhausted with 409
                if response is not None:
                    detail = response.text.strip() or "Agent busy (409)"
                    return 409, "", detail, ""
            assert response is not None  # guaranteed by for/else
            data = response.json()
    except httpx.HTTPStatusError as e:
        detail = e.response.text.strip() or str(e)
        return e.response.status_code, "", detail, ""
    except httpx.HTTPError as e:
        return 1, "", str(e), ""

    task_data = _extract_task_data(data)
    task_id = task_data.get("id", "")
    status = _extract_task_status(task_data)
    summary = "Accepted"
    if task_id:
        summary += f" task {task_id[:8]}"
    if status:
        summary += f" ({status})"
    return 0, summary, "", task_id


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


def _raise_if_helper_execution_forbidden() -> None:
    """Reject nested workflow execution from helper agents.

    If this process was spawned as a workflow helper (detected via the
    ``SYNAPSE_WORKFLOW_HELPER`` env marker), refuse to run any workflow.
    This prevents an infinite spawn loop where a self-target step whose
    message triggers another workflow would cause recursive helper spawning.

    The depth check is defensive: even in the (future) case where nested
    helpers become legal up to some limit, exceeding that limit is still
    hard-forbidden.
    """
    if not os.environ.get(_HELPER_ENV_MARKER):
        return

    raw_depth = os.environ.get(_HELPER_DEPTH_ENV, "1")
    try:
        depth = int(raw_depth)
    except ValueError:
        depth = _MAX_HELPER_DEPTH + 1
    if depth > _MAX_HELPER_DEPTH:
        raise WorkflowError(
            f"Nested workflow execution exceeds maximum helper depth "
            f"({depth} > {_MAX_HELPER_DEPTH})"
        )
    raise WorkflowError("Nested workflow execution is forbidden inside a helper agent")


async def _apply_task_result(
    step: StepResult,
    returncode: int,
    stdout: str,
    stderr: str,
    task_id: str,
    wf_step: Any,
    endpoint: str | None,
    *,
    humanize_target: str | None = None,
) -> None:
    """Apply send/poll results to a StepResult.

    Shared by both ``_WorkflowHelper.execute_step`` and ``_execute_step``
    to avoid duplicating the returncode/status branching logic.
    """
    if returncode == 0 and wf_step.response_mode == "wait" and task_id and endpoint:
        final_status, final_output = await _poll_task_completion(endpoint, task_id)
        if final_status == "failed":
            step.status = "failed"
            step.error = final_output or "Agent task failed"
        elif final_status == "canceled":
            step.status = "failed"
            step.error = "Agent task was canceled"
        else:
            step.status = "completed"
            step.output = final_output or stdout
    elif returncode == 0:
        step.status = "completed"
        step.output = stdout
    else:
        error = stderr or f"Exit code {returncode}"
        if humanize_target:
            error = _humanize_error(humanize_target, error)
        step.status = "failed"
        step.error = error
    step.completed_at = time.time()


async def _execute_step(
    wf_step: Any,
    step: StepResult,
    *,
    workflow_auto_spawn: bool = False,
    sender_info: dict[str, str] | None = None,
    helper: _WorkflowHelper | None = None,
) -> None:
    """Execute a single workflow step via direct A2A HTTP send."""
    if _is_self_target(wf_step.target, sender_info):
        if helper is None:
            step.status = "failed"
            step.error = "Workflow helper is unavailable"
            step.completed_at = time.time()
            return
        try:
            await helper.execute_step(wf_step, step)
        except Exception as exc:  # broad catch: step execution may fail in many ways
            step.status = "failed"
            step.error = str(exc) or "Workflow helper failed"
            step.completed_at = time.time()
            logger.warning(
                "Workflow helper step failed for %s: %s", wf_step.message, exc
            )
        return

    endpoint = _resolve_target_endpoint(wf_step.target)
    if not endpoint:
        returncode, stdout, stderr, task_id = 404, "", _NO_AGENT_MARKER, ""
    else:
        returncode, stdout, stderr, task_id = await _send_workflow_request(
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
                returncode, stdout, stderr, task_id = await _send_workflow_request(
                    endpoint, wf_step, sender_info
                )

    await _apply_task_result(
        step,
        returncode,
        stdout,
        stderr,
        task_id,
        wf_step,
        endpoint,
        humanize_target=wf_step.target,
    )


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
    helper: _WorkflowHelper | None = None

    try:
        for i, wf_step in enumerate(workflow.steps):
            step = run.steps[i]
            step.status = "running"
            step.started_at = time.time()
            _notify(on_update)

            if _is_self_target(wf_step.target, sender_info) and helper is None:
                try:
                    helper = _WorkflowHelper(workflow.name, sender_info)
                except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
                    step.status = "failed"
                    step.error = str(exc) or "Failed to initialize workflow helper"
                    step.completed_at = time.time()
                    has_failure = True
                    _notify(on_update)
                    if not continue_on_error:
                        break
                    continue

            await _execute_step(
                wf_step,
                step,
                workflow_auto_spawn=workflow.auto_spawn,
                sender_info=sender_info,
                helper=helper,
            )

            if step.status == "failed":
                has_failure = True
                _notify(on_update)
                if not continue_on_error:
                    break
                continue

            _notify(on_update)
    except Exception:  # broad catch: top-level safety net for workflow crash logging
        logger.exception("Workflow '%s' crashed unexpectedly", workflow.name)
        has_failure = True
    finally:
        if helper is not None:
            try:
                helper.kill()
            except (OSError, subprocess.SubprocessError):
                logger.warning(
                    "Workflow helper cleanup failed for %s",
                    workflow.name,
                    exc_info=True,
                )

    run.status = "failed" if has_failure else "completed"
    run.completed_at = time.time()
    _notify(on_update)

    # Persist final state to DB
    try:
        _get_db().save_run(run.to_db_dict())
    except (OSError, sqlite3.Error):
        logger.debug(
            "Failed to persist completed run %s to DB", run.run_id, exc_info=True
        )
