"""Tests for synapse.workflow_runner module."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from synapse.workflow import Workflow, WorkflowStep
from synapse.workflow_runner import (
    MAX_RUNS,
    StepResult,
    _apply_task_result,
    _extract_task_output,
    _has_working_tasks,
    _is_self_target,
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
    monkeypatch.setattr(
        "synapse.workflow_runner._wait_for_helper_idle",
        lambda endpoint: asyncio.sleep(0, result=True),
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
    async def _mock_poll(endpoint, task_id, *, target_is_self=False):
        assert task_id == "task-wait-123"
        assert target_is_self is False
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

    async def _mock_poll(endpoint, task_id, *, target_is_self=False):
        assert target_is_self is False
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

    async def _mock_poll(endpoint, task_id, *, target_is_self=False):
        assert target_is_self is False
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

    async def _mock_poll(endpoint, task_id, *, target_is_self=False):
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


def test_is_self_target_literal_self():
    """Literal ``self`` should always be treated as the current agent."""
    sender_info = {"agent_id": "synapse-claude-8103", "agent_type": "claude"}

    assert _is_self_target("self", sender_info)


def test_is_self_target_matches_sender_agent_id():
    """Explicit agent-id self references should be recognized."""
    sender_info = {"agent_id": "synapse-claude-8103", "agent_type": "claude"}

    assert _is_self_target("synapse-claude-8103", sender_info)


def test_is_self_target_type_match_sole_agent_of_type(monkeypatch):
    """Legacy type target should map to self when it is the only local match."""
    sender_info = {
        "agent_id": "synapse-claude-8103",
        "agent_type": "claude",
        "working_dir": "/repo",
    }
    agents = {
        "synapse-claude-8103": {
            "agent_id": "synapse-claude-8103",
            "agent_type": "claude",
            "working_dir": "/repo",
        },
        "synapse-codex-8124": {
            "agent_id": "synapse-codex-8124",
            "agent_type": "codex",
            "working_dir": "/repo",
        },
    }

    monkeypatch.setattr(
        "synapse.workflow_runner.AgentRegistry",
        lambda: type("Registry", (), {"list_agents": lambda self: agents})(),
    )

    assert _is_self_target("claude", sender_info)


def test_is_self_target_type_match_multiple_agents_returns_false(monkeypatch):
    """Type target should not auto-map to self when peers of that type exist."""
    sender_info = {
        "agent_id": "synapse-claude-8103",
        "agent_type": "claude",
        "working_dir": "/repo",
    }
    agents = {
        "synapse-claude-8103": {
            "agent_id": "synapse-claude-8103",
            "agent_type": "claude",
            "working_dir": "/repo",
        },
        "synapse-claude-8104": {
            "agent_id": "synapse-claude-8104",
            "agent_type": "claude",
            "working_dir": "/repo",
        },
    }

    monkeypatch.setattr(
        "synapse.workflow_runner.AgentRegistry",
        lambda: type("Registry", (), {"list_agents": lambda self: agents})(),
    )

    assert not _is_self_target("claude", sender_info)


def _make_sender_info(
    agent_id: str = "synapse-codex-8124",
    *,
    agent_type: str = "codex",
    working_dir: str = "/tmp/worktree-codex-525",
) -> dict[str, str]:
    return {
        "agent_id": agent_id,
        "agent_type": agent_type,
        "working_dir": working_dir,
    }


class _FakeHelper:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.killed = 0
        self.raise_on_messages: set[str] = set()

    async def execute_step(self, wf_step, step: StepResult) -> None:
        self.calls.append((wf_step.target, wf_step.message))
        if wf_step.message in self.raise_on_messages:
            raise RuntimeError(f"boom: {wf_step.message}")
        step.status = "completed"
        step.output = f"helper:{wf_step.message}"
        step.completed_at = 123.0

    def kill(self) -> None:
        self.killed += 1


def _patch_helper_factory(monkeypatch, helpers: list[_FakeHelper]) -> None:
    def _factory(*args, **kwargs):
        helper = _FakeHelper()
        helpers.append(helper)
        return helper

    monkeypatch.setattr(
        "synapse.workflow_runner._WorkflowHelper",
        _factory,
        raising=False,
    )


@pytest.mark.asyncio
async def test_execute_step_self_target_uses_helper_not_orchestrator(monkeypatch):
    """Self-target steps should go through the helper instead of the orchestrator."""
    helpers: list[_FakeHelper] = []
    _patch_helper_factory(monkeypatch, helpers)

    resolve_calls: list[str] = []

    def _resolve(target: str) -> str:
        resolve_calls.append(target)
        return "http://localhost:9999"

    monkeypatch.setattr("synapse.workflow_runner._resolve_target_endpoint", _resolve)

    wf = Workflow(
        name="self-helper-path",
        steps=[WorkflowStep(target="self", message="/release", response_mode="wait")],
        scope="project",
    )
    run_id = await run_workflow(wf, sender_info=_make_sender_info())
    await asyncio.sleep(0.1)

    run = get_run(run_id)
    assert run is not None
    assert run.status == "completed"
    assert helpers
    assert helpers[0].calls == [("self", "/release")]
    assert resolve_calls == []


@pytest.mark.asyncio
async def test_workflow_helper_spawned_lazily_on_first_self_step(monkeypatch):
    """No helper should be created until the first self-target step is executed."""
    helpers: list[_FakeHelper] = []
    _patch_helper_factory(monkeypatch, helpers)

    async def _mock_send(*args, **kwargs):
        return 0, "ok", "", "task-abc123"

    _patch_workflow_send(monkeypatch, _mock_send)

    wf = Workflow(
        name="lazy-helper",
        steps=[
            WorkflowStep(target="agent1", message="hello"),
            WorkflowStep(target="self", message="/release"),
        ],
        scope="project",
    )
    run_id = await run_workflow(wf, sender_info=_make_sender_info())

    assert helpers == []

    await asyncio.sleep(0.1)
    run = get_run(run_id)
    assert run is not None
    assert run.status == "completed"
    assert len(helpers) == 1
    assert helpers[0].calls == [("self", "/release")]


@pytest.mark.asyncio
async def test_workflow_helper_reused_across_steps(monkeypatch):
    """All self-target steps in a run should reuse a single helper instance."""
    helpers: list[_FakeHelper] = []
    _patch_helper_factory(monkeypatch, helpers)

    wf = Workflow(
        name="reuse-helper",
        steps=[
            WorkflowStep(target="self", message="/parallel-docs-simplify-sync"),
            WorkflowStep(target="self", message="/release"),
            WorkflowStep(target="self", message="/pr-guardian"),
        ],
        scope="project",
    )
    run_id = await run_workflow(wf, sender_info=_make_sender_info())
    await asyncio.sleep(0.1)

    run = get_run(run_id)
    assert run is not None
    assert run.status == "completed"
    assert len(helpers) == 1
    assert helpers[0].calls == [
        ("self", "/parallel-docs-simplify-sync"),
        ("self", "/release"),
        ("self", "/pr-guardian"),
    ]


@pytest.mark.asyncio
async def test_workflow_helper_killed_on_success(monkeypatch):
    """Helper should be killed after a successful workflow run."""
    helpers: list[_FakeHelper] = []
    _patch_helper_factory(monkeypatch, helpers)

    wf = Workflow(
        name="helper-success",
        steps=[WorkflowStep(target="self", message="/release")],
        scope="project",
    )
    run_id = await run_workflow(wf, sender_info=_make_sender_info())
    await asyncio.sleep(0.1)

    run = get_run(run_id)
    assert run is not None
    assert run.status == "completed"
    assert len(helpers) == 1
    assert helpers[0].killed == 1


@pytest.mark.asyncio
async def test_workflow_helper_killed_on_failure(monkeypatch):
    """Helper should be killed when a self-target step fails."""
    helpers: list[_FakeHelper] = []

    def _factory(*args, **kwargs):
        helper = _FakeHelper()

        async def _fail_execute_step(wf_step, step: StepResult) -> None:
            step.status = "failed"
            step.error = "helper failed"
            step.completed_at = 123.0

        helper.execute_step = _fail_execute_step  # type: ignore[method-assign]
        helpers.append(helper)
        return helper

    monkeypatch.setattr(
        "synapse.workflow_runner._WorkflowHelper",
        _factory,
        raising=False,
    )

    wf = Workflow(
        name="helper-failure",
        steps=[WorkflowStep(target="self", message="/release")],
        scope="project",
    )
    run_id = await run_workflow(wf, sender_info=_make_sender_info())
    await asyncio.sleep(0.1)

    run = get_run(run_id)
    assert run is not None
    assert run.status == "failed"
    assert len(helpers) == 1
    assert helpers[0].killed == 1


@pytest.mark.asyncio
async def test_workflow_helper_killed_on_exception(monkeypatch):
    """Helper should be killed if helper execution raises unexpectedly."""
    helpers: list[_FakeHelper] = []
    _patch_helper_factory(monkeypatch, helpers)
    helpers_raise = helpers

    def _factory(*args, **kwargs):
        helper = _FakeHelper()
        helper.raise_on_messages.add("/release")
        helpers_raise.append(helper)
        return helper

    monkeypatch.setattr(
        "synapse.workflow_runner._WorkflowHelper",
        _factory,
        raising=False,
    )

    wf = Workflow(
        name="helper-exception",
        steps=[WorkflowStep(target="self", message="/release")],
        scope="project",
    )
    run_id = await run_workflow(wf, sender_info=_make_sender_info())
    await asyncio.sleep(0.1)

    run = get_run(run_id)
    assert run is not None
    assert run.status == "failed"
    assert len(helpers) == 1
    assert helpers[0].killed == 1


@pytest.mark.asyncio
async def test_workflow_no_self_steps_does_not_spawn_helper(monkeypatch):
    """Ordinary workflows should not pay helper startup cost."""
    helpers: list[_FakeHelper] = []
    _patch_helper_factory(monkeypatch, helpers)

    async def _mock_send(*args, **kwargs):
        return 0, "ok", "", "task-abc123"

    _patch_workflow_send(monkeypatch, _mock_send)

    wf = _make_workflow()
    run_id = await run_workflow(wf, sender_info=_make_sender_info())
    await asyncio.sleep(0.1)

    run = get_run(run_id)
    assert run is not None
    assert run.status == "completed"
    assert helpers == []


@pytest.mark.asyncio
async def test_run_workflow_in_helper_env_raises_error(monkeypatch):
    """Nested workflow execution must be blocked inside helper agents."""
    monkeypatch.setenv("SYNAPSE_WORKFLOW_HELPER", "1")
    monkeypatch.setenv("SYNAPSE_WORKFLOW_HELPER_DEPTH", "1")

    wf = Workflow(
        name="nested-helper",
        steps=[WorkflowStep(target="self", message="/release")],
        scope="project",
    )

    with pytest.raises(Exception, match="Nested workflow execution is forbidden"):
        await run_workflow(wf, sender_info=_make_sender_info())


@pytest.mark.asyncio
async def test_workflow_helper_spawn_failure_marks_step_failed_no_crash(monkeypatch):
    """Helper spawn failures should fail only the self-target step."""
    monkeypatch.setattr(
        "synapse.workflow_runner._WorkflowHelper",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("spawn failed")),
        raising=False,
    )

    async def _mock_send(*args, **kwargs):
        return 0, "ok", "", "task-abc123"

    _patch_workflow_send(monkeypatch, _mock_send)

    wf = Workflow(
        name="spawn-failure",
        steps=[
            WorkflowStep(target="self", message="/release"),
            WorkflowStep(target="agent1", message="after failure"),
        ],
        scope="project",
    )
    run_id = await run_workflow(
        wf,
        sender_info=_make_sender_info(),
        continue_on_error=True,
    )
    await asyncio.sleep(0.1)

    run = get_run(run_id)
    assert run is not None
    assert run.status == "failed"
    assert run.steps[0].status == "failed"
    assert "spawn failed" in (run.steps[0].error or "")
    assert run.steps[1].status == "completed"


# ---------------------------------------------------------------------------
# 15. Helper idle wait before send
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_wait_for_helper_idle_polls_until_no_working_tasks(monkeypatch):
    """_wait_for_helper_idle returns True once all tasks finish."""
    import httpx

    from synapse.workflow_runner import _wait_for_helper_idle

    task_states = [
        [{"status": {"state": "working"}}],
        [{"status": {"state": "working"}}],
        [],  # no working tasks
    ]
    sleep_calls: list[float] = []

    async def _mock_get(self, url, **kwargs):
        state = task_states.pop(0) if task_states else []
        return httpx.Response(200, json=state, request=httpx.Request("GET", url))

    async def _mock_sleep(delay):
        sleep_calls.append(delay)

    monkeypatch.setattr(httpx.AsyncClient, "get", _mock_get)
    monkeypatch.setattr("synapse.workflow_runner.asyncio.sleep", _mock_sleep)

    result = await _wait_for_helper_idle("http://localhost:8100")

    assert result is True
    assert len(sleep_calls) == 2  # slept twice before becoming idle


@pytest.mark.asyncio
async def test_wait_for_helper_idle_timeout_returns_false(monkeypatch):
    """_wait_for_helper_idle returns False on timeout."""
    import httpx

    from synapse.workflow_runner import _wait_for_helper_idle

    current_time = 0.0

    async def _mock_get(self, url, **kwargs):
        return httpx.Response(
            200,
            json=[{"status": {"state": "working"}}],
            request=httpx.Request("GET", url),
        )

    async def _mock_sleep(delay):
        nonlocal current_time
        current_time += delay

    monkeypatch.setattr(httpx.AsyncClient, "get", _mock_get)
    monkeypatch.setattr("synapse.workflow_runner.asyncio.sleep", _mock_sleep)
    monkeypatch.setattr("synapse.workflow_runner.time.time", lambda: current_time)
    monkeypatch.setattr("synapse.workflow_runner._POLL_TIMEOUT", 6.0)

    result = await _wait_for_helper_idle("http://localhost:8100")

    assert result is False


# ---------------------------------------------------------------------------
# 16. _poll_task_completion handles input_required as failure (#533)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_poll_task_completion_input_required_returns_failed(monkeypatch):
    """input_required should be treated as failure in workflow context."""
    import httpx

    async def _mock_get(self, url, **kwargs):
        data = {
            "task": {
                "id": "t1",
                "status": {"state": "input_required"},
            }
        }
        return httpx.Response(200, json=data, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.AsyncClient, "get", _mock_get)

    async def _noop_sleep(_):
        pass

    monkeypatch.setattr("synapse.workflow_runner.asyncio.sleep", _noop_sleep)

    status, output = await _poll_task_completion("http://localhost:8100", "t1")
    assert status == "failed"
    assert "permission" in output.lower()


@pytest.mark.asyncio
async def test_poll_task_completion_input_required_self_target_retries(monkeypatch):
    """target_is_self=True: input_required is transient, polling continues."""
    import httpx

    call_count = 0

    async def _mock_get(self, url, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            data = {"task": {"id": "t1", "status": {"state": "input_required"}}}
        else:
            data = {
                "task": {
                    "id": "t1",
                    "status": {"state": "completed"},
                    "artifacts": [{"parts": [{"type": "text", "text": "done"}]}],
                }
            }
        return httpx.Response(200, json=data, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.AsyncClient, "get", _mock_get)

    async def _noop_sleep(_):
        pass

    monkeypatch.setattr("synapse.workflow_runner.asyncio.sleep", _noop_sleep)

    status, output = await _poll_task_completion(
        "http://localhost:8100",
        "t1",
        target_is_self=True,
    )

    assert status == "completed"
    assert output == "done"
    assert call_count >= 2


@pytest.mark.asyncio
async def test_poll_task_completion_input_required_self_target_timeout(monkeypatch):
    """target_is_self=True: persistent input_required times out to completed/empty."""
    import httpx

    current_time = 100.0

    async def _mock_get(self, url, **kwargs):
        data = {"task": {"id": "t1", "status": {"state": "input_required"}}}
        return httpx.Response(200, json=data, request=httpx.Request("GET", url))

    async def _mock_sleep(delay):
        nonlocal current_time
        current_time += delay

    monkeypatch.setattr(httpx.AsyncClient, "get", _mock_get)
    monkeypatch.setattr("synapse.workflow_runner.asyncio.sleep", _mock_sleep)
    monkeypatch.setattr("synapse.workflow_runner.time.time", lambda: current_time)
    monkeypatch.setattr("synapse.workflow_runner._POLL_TIMEOUT", 0.05)
    monkeypatch.setattr("synapse.config.TASK_POLL_INTERVAL", 0.01)

    status, output = await _poll_task_completion(
        "http://localhost:8100",
        "t1",
        target_is_self=True,
    )

    assert status == "completed"
    assert output == ""


@pytest.mark.asyncio
async def test_apply_task_result_passes_target_is_self_for_self_target(monkeypatch):
    """_apply_task_result forwards target_is_self=True into polling."""

    mock_poll = AsyncMock(return_value=("completed", "x"))
    monkeypatch.setattr("synapse.workflow_runner._poll_task_completion", mock_poll)

    step = StepResult(step_index=0, target="self", message="hi", status="running")
    wf_step = SimpleNamespace(
        target="self",
        response_mode="wait",
        message="hi",
        priority=0,
    )

    await _apply_task_result(
        step,
        0,
        "",
        "",
        "t1",
        wf_step,
        "http://localhost:9999",
        target_is_self=True,
    )

    mock_poll.assert_awaited_once_with(
        "http://localhost:9999",
        "t1",
        target_is_self=True,
    )


@pytest.mark.asyncio
async def test_apply_task_result_passes_target_is_self_false_for_other(monkeypatch):
    """_apply_task_result forwards target_is_self=False into polling."""

    mock_poll = AsyncMock(return_value=("completed", "x"))
    monkeypatch.setattr("synapse.workflow_runner._poll_task_completion", mock_poll)

    step = StepResult(step_index=0, target="agent1", message="hi", status="running")
    wf_step = SimpleNamespace(
        target="agent1",
        response_mode="wait",
        message="hi",
        priority=0,
    )

    await _apply_task_result(
        step,
        0,
        "",
        "",
        "t1",
        wf_step,
        "http://localhost:9999",
        target_is_self=False,
    )

    mock_poll.assert_awaited_once_with(
        "http://localhost:9999",
        "t1",
        target_is_self=False,
    )


# ---------------------------------------------------------------------------
# 17. _has_working_tasks treats input_required as blocking (#533)
# ---------------------------------------------------------------------------
def test_has_working_tasks_includes_input_required():
    """input_required tasks should count as blocking (not idle)."""
    tasks = [{"status": {"state": "input_required"}}]
    assert _has_working_tasks(tasks) is True


def test_has_working_tasks_working_still_detected():
    """working tasks should still be detected as blocking."""
    tasks = [{"status": {"state": "working"}}]
    assert _has_working_tasks(tasks) is True


def test_has_working_tasks_completed_not_blocking():
    """completed tasks should not be blocking."""
    tasks = [{"status": {"state": "completed"}}]
    assert _has_working_tasks(tasks) is False


def test_has_working_tasks_empty_not_blocking():
    """Empty task list should not be blocking."""
    assert _has_working_tasks([]) is False


# ---------------------------------------------------------------------------
# 18. wait mode with input_required — step fails (#533)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_wait_mode_input_required_fails_step(monkeypatch):
    """With response_mode=wait, input_required from poll should fail the step."""

    async def _mock_send(*args, **kwargs):
        return 0, "Accepted", "", "task-perm-001"

    _patch_workflow_send(monkeypatch, _mock_send)

    async def _mock_poll(endpoint, task_id, *, target_is_self=False):
        assert target_is_self is False
        return (
            "failed",
            "Agent requires permission approval — check auto-approve configuration",
        )

    monkeypatch.setattr("synapse.workflow_runner._poll_task_completion", _mock_poll)

    wf = Workflow(
        name="input-required-test",
        steps=[WorkflowStep(target="agent1", message="do work", response_mode="wait")],
        scope="project",
    )
    run_id = await run_workflow(wf)
    await asyncio.sleep(0.1)

    run = get_run(run_id)
    assert run is not None
    assert run.status == "failed"
    assert run.steps[0].status == "failed"
    assert "permission" in (run.steps[0].error or "").lower()
