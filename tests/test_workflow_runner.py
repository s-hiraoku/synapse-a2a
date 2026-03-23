"""Tests for synapse.workflow_runner module."""

from __future__ import annotations

import asyncio

import pytest

from synapse.workflow import Workflow, WorkflowStep
from synapse.workflow_runner import (
    MAX_RUNS,
    _extract_task_output,
    _poll_task_completion,
    _send_workflow_request,
    _workflow_runs,
    get_run,
    run_workflow,
)


@pytest.fixture(autouse=True)
def _clear_runs(tmp_path):
    """Clear the global run store and use a temp DB for each test."""
    import synapse.workflow_runner as wr
    from synapse.workflow_db import WorkflowRunDB

    _workflow_runs.clear()
    old_db = wr._db
    wr._db = WorkflowRunDB(db_path=str(tmp_path / "test_runs.db"))
    yield
    _workflow_runs.clear()
    wr._db = old_db


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


def _patch_workflow_send(
    monkeypatch, mock_send, endpoint: str = "http://localhost:8100"
):
    """Patch direct workflow send helpers."""
    monkeypatch.setattr(
        "synapse.workflow_runner._resolve_target_endpoint",
        lambda target: endpoint,
    )
    monkeypatch.setattr("synapse.workflow_runner._send_workflow_request", mock_send)


# ---------------------------------------------------------------------------
# 1. All steps succeed
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_run_workflow_all_steps_succeed(monkeypatch):
    """When subprocess returns 0 for every step, all steps complete."""

    async def _mock_send(*args, **kwargs):
        return 0, "ok", "", "task-abc123"

    _patch_workflow_send(monkeypatch, _mock_send)

    wf = _make_workflow()
    run_id = await run_workflow(wf)

    # Let the background task finish
    await asyncio.sleep(0.1)

    run = get_run(run_id)
    assert run is not None
    assert run.status == "completed"
    assert all(s.status == "completed" for s in run.steps)
    assert all(s.output == "ok" for s in run.steps)
    assert run.completed_at is not None


# ---------------------------------------------------------------------------
# 2. Step fails -> run stops (default behaviour)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_run_workflow_step_fails_stops(monkeypatch):
    """When step 2 fails (index 1), the run stops and step 3 stays pending."""

    call_count = 0

    async def _mock_send(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            return 1, "", "server error", ""
        return 0, "ok", "", "task-abc123"

    _patch_workflow_send(monkeypatch, _mock_send)

    wf = _make_workflow()
    run_id = await run_workflow(wf)
    await asyncio.sleep(0.1)

    run = get_run(run_id)
    assert run is not None
    assert run.status == "failed"
    assert run.steps[0].status == "completed"
    assert run.steps[1].status == "failed"
    assert run.steps[1].error == "server error"
    assert run.steps[2].status == "pending"


# ---------------------------------------------------------------------------
# 3. continue_on_error=True -> all steps attempted
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_run_workflow_continue_on_error(monkeypatch):
    """With continue_on_error=True, all steps are attempted even if one fails."""

    call_count = 0

    async def _mock_send(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            return 1, "", "server error", ""
        return 0, "ok", "", "task-abc123"

    _patch_workflow_send(monkeypatch, _mock_send)

    wf = _make_workflow()
    run_id = await run_workflow(wf, continue_on_error=True)
    await asyncio.sleep(0.1)

    run = get_run(run_id)
    assert run is not None
    assert run.status == "failed"  # still failed overall
    assert run.steps[0].status == "completed"
    assert run.steps[1].status == "failed"
    assert run.steps[2].status == "completed"  # step 3 was still attempted


# ---------------------------------------------------------------------------
# 4. Subprocess fails with no stderr -> shows exit code
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_run_workflow_empty_stderr_shows_exit_code(monkeypatch):
    """When subprocess fails with empty stderr, error shows exit code."""

    async def _mock_send(*args, **kwargs):
        return 1, "", "", ""

    _patch_workflow_send(monkeypatch, _mock_send)

    wf = Workflow(
        name="test-exit",
        steps=[WorkflowStep(target="agent1", message="ping")],
        scope="project",
    )
    run_id = await run_workflow(wf)
    await asyncio.sleep(0.1)

    run = get_run(run_id)
    assert run is not None
    assert run.status == "failed"
    assert run.steps[0].status == "failed"
    assert "Exit code 1" in (run.steps[0].error or "")


# ---------------------------------------------------------------------------
# 5. LRU eviction cap at MAX_RUNS
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_workflow_run_cap(monkeypatch):
    """Adding 55 runs should evict the oldest, keeping only MAX_RUNS (50)."""

    async def _mock_send(*args, **kwargs):
        return 0, "ok", "", "task-abc123"

    _patch_workflow_send(monkeypatch, _mock_send)

    wf = Workflow(
        name="cap-test",
        steps=[WorkflowStep(target="a", message="m")],
        scope="project",
    )

    run_ids = []
    for _ in range(55):
        rid = await run_workflow(wf)
        run_ids.append(rid)

    # Let all background tasks finish
    await asyncio.sleep(0.3)

    assert len(_workflow_runs) == MAX_RUNS
    # The first 5 runs should have been evicted from in-memory cache
    for rid in run_ids[:5]:
        assert rid not in _workflow_runs
    # The last 50 should still be in cache
    for rid in run_ids[5:]:
        assert rid in _workflow_runs
        assert get_run(rid) is not None
    # But all 55 runs are still available via get_run (DB fallback)
    for rid in run_ids[:5]:
        assert get_run(rid) is not None


# ---------------------------------------------------------------------------
# 6. Output truncation in to_dict
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_step_output_truncation(monkeypatch):
    """Long output is truncated to 500 chars in to_dict()."""

    long_output = "x" * 1000

    async def _mock_send(*args, **kwargs):
        return 0, long_output, "", "task-trunc"

    _patch_workflow_send(monkeypatch, _mock_send)

    wf = Workflow(
        name="truncation-test",
        steps=[WorkflowStep(target="a", message="m")],
        scope="project",
    )
    run_id = await run_workflow(wf)
    await asyncio.sleep(0.1)

    run = get_run(run_id)
    assert run is not None
    step_dict = run.steps[0].to_dict()
    assert len(step_dict["output"]) == 500
    # Raw output is preserved in full
    assert len(run.steps[0].output) == 1000


# ---------------------------------------------------------------------------
# 7. _extract_task_output
# ---------------------------------------------------------------------------
def test_extract_task_output():
    """Extract text parts from task artifacts."""
    task_data = {
        "artifacts": [
            {
                "parts": [
                    {"type": "text", "text": "Hello"},
                    {"type": "text", "text": "World"},
                ]
            },
            {"parts": [{"type": "data", "data": "ignored"}]},
        ]
    }
    assert _extract_task_output(task_data) == "Hello\nWorld"
    assert _extract_task_output({}) == ""
    assert _extract_task_output({"artifacts": []}) == ""


# ---------------------------------------------------------------------------
# 8. response_mode: wait — polls until completed
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_wait_mode_polls_until_completed(monkeypatch):
    """With response_mode=wait, step polls target and returns final output."""

    async def _mock_send(*args, **kwargs):
        return 0, "Accepted task abc12345", "", "task-wait-123"

    _patch_workflow_send(monkeypatch, _mock_send)

    # Mock _poll_task_completion to return completed with output
    async def _mock_poll(endpoint, task_id):
        assert task_id == "task-wait-123"
        return "completed", "Final result from agent"

    monkeypatch.setattr("synapse.workflow_runner._poll_task_completion", _mock_poll)

    wf = Workflow(
        name="wait-test",
        steps=[WorkflowStep(target="agent1", message="do work", response_mode="wait")],
        scope="project",
    )
    run_id = await run_workflow(wf)
    await asyncio.sleep(0.1)

    run = get_run(run_id)
    assert run is not None
    assert run.status == "completed"
    assert run.steps[0].status == "completed"
    assert run.steps[0].output == "Final result from agent"


# ---------------------------------------------------------------------------
# 9. response_mode: wait — agent task fails
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_wait_mode_agent_task_failed(monkeypatch):
    """With response_mode=wait, if polled task fails, step fails."""

    async def _mock_send(*args, **kwargs):
        return 0, "Accepted", "", "task-fail-456"

    _patch_workflow_send(monkeypatch, _mock_send)

    async def _mock_poll(endpoint, task_id):
        return "failed", "Syntax error in generated code"

    monkeypatch.setattr("synapse.workflow_runner._poll_task_completion", _mock_poll)

    wf = Workflow(
        name="wait-fail-test",
        steps=[WorkflowStep(target="agent1", message="do work", response_mode="wait")],
        scope="project",
    )
    run_id = await run_workflow(wf)
    await asyncio.sleep(0.1)

    run = get_run(run_id)
    assert run is not None
    assert run.status == "failed"
    assert run.steps[0].status == "failed"
    assert run.steps[0].error == "Syntax error in generated code"


# ---------------------------------------------------------------------------
# 10. response_mode: wait — agent task canceled
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_wait_mode_agent_task_canceled(monkeypatch):
    """With response_mode=wait, if polled task is canceled, step fails."""

    async def _mock_send(*args, **kwargs):
        return 0, "Accepted", "", "task-cancel-789"

    _patch_workflow_send(monkeypatch, _mock_send)

    async def _mock_poll(endpoint, task_id):
        return "canceled", ""

    monkeypatch.setattr("synapse.workflow_runner._poll_task_completion", _mock_poll)

    wf = Workflow(
        name="wait-cancel-test",
        steps=[WorkflowStep(target="agent1", message="do work", response_mode="wait")],
        scope="project",
    )
    run_id = await run_workflow(wf)
    await asyncio.sleep(0.1)

    run = get_run(run_id)
    assert run is not None
    assert run.status == "failed"
    assert run.steps[0].status == "failed"
    assert run.steps[0].error == "Agent task was canceled"


# ---------------------------------------------------------------------------
# 11. response_mode: notify — no polling
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_notify_mode_does_not_poll(monkeypatch):
    """With response_mode=notify (default), step completes immediately."""

    async def _mock_send(*args, **kwargs):
        return 0, "Accepted task abc", "", "task-notify-111"

    _patch_workflow_send(monkeypatch, _mock_send)

    poll_called = False

    async def _mock_poll(endpoint, task_id):
        nonlocal poll_called
        poll_called = True
        return "completed", ""

    monkeypatch.setattr("synapse.workflow_runner._poll_task_completion", _mock_poll)

    wf = Workflow(
        name="notify-test",
        steps=[WorkflowStep(target="agent1", message="ping")],
        scope="project",
    )
    run_id = await run_workflow(wf)
    await asyncio.sleep(0.1)

    run = get_run(run_id)
    assert run is not None
    assert run.steps[0].status == "completed"
    assert run.steps[0].output == "Accepted task abc"
    assert not poll_called


# ---------------------------------------------------------------------------
# 12. _poll_task_completion integration
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_poll_task_completion_returns_on_completed(monkeypatch):
    """_poll_task_completion returns when task reaches completed state."""
    import httpx

    call_count = 0

    async def _mock_get(self, url, **kwargs):
        nonlocal call_count
        call_count += 1
        data = {
            "task": {
                "id": "t1",
                "status": {"state": "working" if call_count < 3 else "completed"},
                "artifacts": [{"parts": [{"type": "text", "text": "done!"}]}],
            }
        }
        response = httpx.Response(200, json=data, request=httpx.Request("GET", url))
        return response

    monkeypatch.setattr(httpx.AsyncClient, "get", _mock_get)

    async def _noop_sleep(_):
        pass

    monkeypatch.setattr("synapse.workflow_runner.asyncio.sleep", _noop_sleep)

    status, output = await _poll_task_completion("http://localhost:8100", "t1")
    assert status == "completed"
    assert output == "done!"
    assert call_count == 3


# ---------------------------------------------------------------------------
# 13. 409 retry in _send_workflow_request
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_send_workflow_request_retries_on_409(monkeypatch):
    """_send_workflow_request retries on 409 then succeeds."""
    import httpx

    call_count = 0

    async def _mock_post(self, url, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            return httpx.Response(
                409, text="Agent busy", request=httpx.Request("POST", url)
            )
        return httpx.Response(
            200,
            json={"task": {"id": "t-retry", "status": {"state": "submitted"}}},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", _mock_post)
    monkeypatch.setattr("synapse.workflow_runner._SEND_RETRY_INTERVAL", 0.01)

    step = WorkflowStep(target="agent1", message="hello")
    rc, out, err, task_id = await _send_workflow_request(
        "http://localhost:8100", step, None
    )
    assert rc == 0
    assert task_id == "t-retry"
    assert call_count == 3


# ---------------------------------------------------------------------------
# 14. 409 retry exhausted
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_send_workflow_request_409_exhausted(monkeypatch):
    """_send_workflow_request returns 409 error when retries are exhausted."""
    import httpx

    async def _mock_post(self, url, **kwargs):
        return httpx.Response(
            409, text="Agent busy", request=httpx.Request("POST", url)
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", _mock_post)
    monkeypatch.setattr("synapse.workflow_runner._SEND_RETRY_INTERVAL", 0.01)
    monkeypatch.setattr("synapse.workflow_runner._SEND_MAX_RETRIES", 3)

    step = WorkflowStep(target="agent1", message="hello")
    rc, out, err, task_id = await _send_workflow_request(
        "http://localhost:8100", step, None
    )
    assert rc == 409
    assert "busy" in err.lower() or "409" in err
