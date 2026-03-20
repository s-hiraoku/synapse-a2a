"""Tests for synapse.workflow_runner module."""

from __future__ import annotations

import asyncio

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


class _FakeProcess:
    """Fake asyncio.subprocess.Process for testing."""

    def __init__(self, returncode: int = 0, stdout: bytes = b"", stderr: bytes = b""):
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr

    async def communicate(self) -> tuple[bytes, bytes]:
        return self._stdout, self._stderr


def _patch_subprocess(monkeypatch, mock_fn):
    """Patch asyncio.create_subprocess_exec used by _run_a2a_subprocess."""
    monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_fn)


# ---------------------------------------------------------------------------
# 1. All steps succeed
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_run_workflow_all_steps_succeed(monkeypatch):
    """When subprocess returns 0 for every step, all steps complete."""

    async def _mock_exec(*args, **kwargs):
        return _FakeProcess(returncode=0, stdout=b"ok")

    _patch_subprocess(monkeypatch, _mock_exec)

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

    async def _mock_exec(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            return _FakeProcess(returncode=1, stderr=b"server error")
        return _FakeProcess(returncode=0, stdout=b"ok")

    _patch_subprocess(monkeypatch, _mock_exec)

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

    async def _mock_exec(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            return _FakeProcess(returncode=1, stderr=b"server error")
        return _FakeProcess(returncode=0, stdout=b"ok")

    _patch_subprocess(monkeypatch, _mock_exec)

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

    async def _mock_exec(*args, **kwargs):
        return _FakeProcess(returncode=1, stderr=b"")

    _patch_subprocess(monkeypatch, _mock_exec)

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

    async def _mock_exec(*args, **kwargs):
        return _FakeProcess(returncode=0, stdout=b"ok")

    _patch_subprocess(monkeypatch, _mock_exec)

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
    # The first 5 runs should have been evicted
    for rid in run_ids[:5]:
        assert get_run(rid) is None
    # The last 50 should still exist
    for rid in run_ids[5:]:
        assert get_run(rid) is not None


# ---------------------------------------------------------------------------
# 6. Output truncation in to_dict
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_step_output_truncation(monkeypatch):
    """Long output is truncated to 500 chars in to_dict()."""

    long_output = "x" * 1000

    async def _mock_exec(*args, **kwargs):
        return _FakeProcess(returncode=0, stdout=long_output.encode())

    _patch_subprocess(monkeypatch, _mock_exec)

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
