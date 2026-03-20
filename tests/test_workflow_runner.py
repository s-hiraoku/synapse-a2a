"""Tests for synapse.workflow_runner module."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from synapse.workflow import Workflow, WorkflowStep
from synapse.workflow_runner import (
    MAX_RUNS,
    _workflow_runs,
    get_run,
    run_workflow,
)


@pytest.fixture(autouse=True)
def _clear_runs():
    """Clear the global run store before each test."""
    _workflow_runs.clear()
    yield
    _workflow_runs.clear()


def _make_workflow(
    steps: list[WorkflowStep] | None = None,
    name: str = "test-wf",
) -> Workflow:
    if steps is None:
        steps = [
            WorkflowStep(target="agent1", message="hello"),
            WorkflowStep(target="agent2", message="world"),
            WorkflowStep(target="agent3", message="done"),
        ]
    return Workflow(name=name, steps=steps, scope="project")


def _ok_endpoint(name: str) -> str | None:
    return "http://localhost:9999"


def _missing_endpoint(name: str) -> str | None:
    return None


# ---------------------------------------------------------------------------
# 1. All steps succeed
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_run_workflow_all_steps_succeed(monkeypatch):
    """When httpx returns 200 for every step, all steps complete and run status is completed."""

    async def _mock_post(self, url, **kwargs):
        resp = httpx.Response(
            200, json={"ok": True}, request=httpx.Request("POST", url)
        )
        return resp

    monkeypatch.setattr(httpx.AsyncClient, "post", _mock_post)

    wf = _make_workflow()
    run_id = await run_workflow(wf, _ok_endpoint, canvas_port=7777)

    # Let the background task finish
    await asyncio.sleep(0.1)

    run = get_run(run_id)
    assert run is not None
    assert run.status == "completed"
    assert all(s.status == "completed" for s in run.steps)
    assert all(s.task_id is not None for s in run.steps)
    assert run.completed_at is not None


# ---------------------------------------------------------------------------
# 2. Step fails -> run stops (default behaviour)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_run_workflow_step_fails_stops(monkeypatch):
    """When step 2 fails (index 1), the run stops and step 3 stays pending."""

    call_count = 0

    async def _mock_post(self, url, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise httpx.HTTPStatusError(
                "server error",
                request=httpx.Request("POST", url),
                response=httpx.Response(500),
            )
        return httpx.Response(200, json={}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", _mock_post)

    wf = _make_workflow()
    run_id = await run_workflow(wf, _ok_endpoint, canvas_port=7777)
    await asyncio.sleep(0.1)

    run = get_run(run_id)
    assert run is not None
    assert run.status == "failed"
    assert run.steps[0].status == "completed"
    assert run.steps[1].status == "failed"
    assert run.steps[1].error is not None
    assert run.steps[2].status == "pending"


# ---------------------------------------------------------------------------
# 3. continue_on_error=True -> all steps attempted
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_run_workflow_continue_on_error(monkeypatch):
    """With continue_on_error=True, all steps are attempted even if one fails."""

    call_count = 0

    async def _mock_post(self, url, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise httpx.HTTPStatusError(
                "server error",
                request=httpx.Request("POST", url),
                response=httpx.Response(500),
            )
        return httpx.Response(200, json={}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", _mock_post)

    wf = _make_workflow()
    run_id = await run_workflow(
        wf,
        _ok_endpoint,
        canvas_port=7777,
        continue_on_error=True,
    )
    await asyncio.sleep(0.1)

    run = get_run(run_id)
    assert run is not None
    assert run.status == "failed"  # still failed overall
    assert run.steps[0].status == "completed"
    assert run.steps[1].status == "failed"
    assert run.steps[2].status == "completed"  # step 3 was still attempted


# ---------------------------------------------------------------------------
# 4. Agent not found
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_run_workflow_agent_not_found():
    """When resolve_endpoint returns None, the step fails with 'not found' error."""

    wf = Workflow(
        name="test-missing",
        steps=[WorkflowStep(target="ghost", message="ping")],
        scope="project",
    )
    run_id = await run_workflow(wf, _missing_endpoint, canvas_port=7777)
    await asyncio.sleep(0.1)

    run = get_run(run_id)
    assert run is not None
    assert run.status == "failed"
    assert run.steps[0].status == "failed"
    assert "not found" in (run.steps[0].error or "").lower()


# ---------------------------------------------------------------------------
# 5. LRU eviction cap at MAX_RUNS
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_workflow_run_cap(monkeypatch):
    """Adding 55 runs should evict the oldest, keeping only MAX_RUNS (50)."""

    async def _mock_post(self, url, **kwargs):
        return httpx.Response(200, json={}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", _mock_post)

    wf = Workflow(
        name="cap-test",
        steps=[WorkflowStep(target="a", message="m")],
        scope="project",
    )

    run_ids = []
    for _ in range(55):
        rid = await run_workflow(wf, _ok_endpoint, canvas_port=7777)
        run_ids.append(rid)

    # Let all background tasks finish
    await asyncio.sleep(0.3)

    assert len(_workflow_runs) == MAX_RUNS
    # The first 5 runs should have been evicted
    for rid in run_ids[:5]:
        assert get_run(rid) is None
    # The last 50 should still exist
    for rid in run_ids[5:]:
        assert get_run(rid) is not None
