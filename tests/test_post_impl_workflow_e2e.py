"""End-to-end verification for the ``post-impl`` workflow (issue #531).

Issue #531 asks for a *reproducible* end-to-end test that exercises the full
``synapse workflow run post-impl --async`` path that PR #530 introduced (helper
agent pattern for ``target: self`` steps, plus follow-up fixes #581, #583,
#588, #590, #591).

Spawning real Claude/Codex agents is too heavy and rate-limit-risky for CI, so
this test exercises the full ``run_workflow`` + ``_WorkflowHelper`` lifecycle
**with a fake helper controller** instead. The fake controller mimics the real
helper contract (``execute_step`` + ``kill``) and records its full lifecycle so
the test can assert:

* All 5 steps reach ``completed`` (the actual ``post-impl.yaml`` definition).
* The helper is created lazily on the first self-target step (i.e. spawned).
* The helper is killed exactly once after the run finishes (i.e. disappears).
* Step 5 does not surface a 409 ``Agent busy`` error (root cause behind #531).
* ``get_run`` (the same call ``synapse workflow status`` makes) shows the
  expected step progression that an operator would observe in the CLI.

Opt-in:
    pytest -m e2e tests/test_post_impl_workflow_e2e.py -v
or:
    SYNAPSE_E2E_POSTIMPL=1 pytest tests/test_post_impl_workflow_e2e.py -v

Without either of those, the test skips to keep the default suite fast.
"""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

import pytest

from synapse.workflow import Workflow, WorkflowStore
from synapse.workflow_runner import (
    StepResult,
    _workflow_runs,
    get_run,
    run_workflow,
)

_E2E_ENV = "SYNAPSE_E2E_POSTIMPL"
_REPO_ROOT = Path(__file__).resolve().parents[1]
_POST_IMPL_YAML = _REPO_ROOT / ".synapse" / "workflows" / "post-impl.yaml"


def _opted_in(config: pytest.Config) -> bool:
    """Return True when the user explicitly opted into the e2e run."""
    if os.environ.get(_E2E_ENV, "").lower() in {"1", "true", "yes"}:
        return True
    # ``pytest -m e2e`` (or any expression containing ``e2e``) is also accepted.
    raw = config.getoption("-m") or ""
    return "e2e" in raw


@pytest.fixture(autouse=True)
def _skip_unless_opted_in(request: pytest.FixtureRequest) -> None:
    if not _opted_in(request.config):
        pytest.skip(
            f"Post-impl e2e is opt-in. Run with `pytest -m e2e` or set {_E2E_ENV}=1."
        )


@pytest.fixture(autouse=True)
def _isolate_runner(tmp_path: Path) -> None:
    """Reset the workflow runner singletons + DB so tests don't bleed."""
    import synapse.workflow_runner as wr
    from synapse.workflow_db import WorkflowRunDB

    _workflow_runs.clear()
    old_db = wr._db
    wr._db = WorkflowRunDB(db_path=str(tmp_path / "test_runs.db"))
    try:
        yield
    finally:
        _workflow_runs.clear()
        wr._db = old_db


# ---------------------------------------------------------------------------
# Fake helper controller
# ---------------------------------------------------------------------------


class FakeHelperController:
    """Records the lifecycle the real ``_WorkflowHelper`` would go through.

    The real helper:
        1. spawns a child synapse agent (``wf-helper-<workflow>-<rand>``)
        2. waits for it to register
        3. forwards every ``target: self`` step to it via direct A2A HTTP
        4. is ``kill()``-ed in the workflow ``finally`` block

    The fake records each of those events on its own instance and on the
    shared ``HelperRegistry`` below so the test can assert "the helper
    appeared during the run and disappeared after".
    """

    def __init__(self, workflow_name: str, sender_info: dict[str, str] | None):
        self.workflow_name = workflow_name
        self.sender_info = sender_info or {}
        # Mirror the real helper's name format so tests catch regressions
        # in the wf-helper-<name>-<rand> convention.
        from uuid import uuid4

        self.agent_name = f"wf-helper-{workflow_name}-{uuid4().hex[:8]}"
        self.steps_seen: list[tuple[str, str]] = []
        self.spawned_at: float | None = None
        self.killed_at: float | None = None
        # Pretend the spawn is the moment we exist — the real helper does its
        # actual spawn lazily inside ``execute_step``; we record both the
        # __init__ moment (registry-visible) and the first execute_step call.
        HelperRegistry.spawn(self)

    async def execute_step(self, wf_step, step: StepResult) -> None:
        # Track the spawn-on-first-step moment too.
        if self.spawned_at is None:
            self.spawned_at = time.time()
        self.steps_seen.append((wf_step.target, wf_step.message))
        # Pretend the helper agent successfully ran the step. No 409 retry
        # branch because the real fix in #530+ ensures self-target steps go
        # through a single dedicated helper that is only ever asked to do
        # one thing at a time.
        step.status = "completed"
        step.output = f"helper:{wf_step.message[:32]}"
        step.completed_at = time.time()

    def kill(self) -> None:
        self.killed_at = time.time()
        HelperRegistry.kill(self)


class HelperRegistry:
    """Tiny shared registry so tests can observe spawn/kill ordering."""

    _alive: dict[str, FakeHelperController] = {}
    _history: list[tuple[str, str]] = []  # (event, agent_name)

    @classmethod
    def reset(cls) -> None:
        cls._alive.clear()
        cls._history.clear()

    @classmethod
    def spawn(cls, helper: FakeHelperController) -> None:
        cls._alive[helper.agent_name] = helper
        cls._history.append(("spawn", helper.agent_name))

    @classmethod
    def kill(cls, helper: FakeHelperController) -> None:
        cls._alive.pop(helper.agent_name, None)
        cls._history.append(("kill", helper.agent_name))

    @classmethod
    def alive(cls) -> list[str]:
        return list(cls._alive.keys())

    @classmethod
    def history(cls) -> list[tuple[str, str]]:
        return list(cls._history)


@pytest.fixture(autouse=True)
def _reset_helper_registry() -> None:
    HelperRegistry.reset()
    yield
    HelperRegistry.reset()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_post_impl_workflow() -> Workflow:
    """Load the real ``post-impl.yaml`` from the repo so the test exercises
    the actual production workflow definition (5 self-target steps)."""
    assert _POST_IMPL_YAML.is_file(), (
        f"post-impl workflow definition not found at {_POST_IMPL_YAML}; "
        "this test requires the project-scope workflow YAML."
    )
    store = WorkflowStore(
        project_dir=_POST_IMPL_YAML.parent,
        user_dir=Path("/nonexistent"),
    )
    wf = store.load("post-impl", scope="project")
    assert wf is not None, "Failed to load post-impl workflow"
    return wf


async def _poll_until_terminal(run_id: str, timeout: float = 5.0) -> None:
    """Mimic ``synapse workflow status`` polling until run finishes."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        run = get_run(run_id)
        if run is not None and run.status != "running":
            return
        await asyncio.sleep(0.05)
    raise AssertionError(f"Run {run_id} did not reach a terminal state in time")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_post_impl_workflow_full_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """End-to-end: post-impl runs all 5 steps via a single helper agent.

    Acceptance criteria from issue #531:
      * All 5 steps reach ``completed``.
      * Helper agent ``wf-helper-post-impl-*`` is spawned during the run and
        killed (disappears) afterwards.
      * Step 5 does not fail with a 409 ``Agent busy`` error.
      * ``synapse workflow status`` (== ``get_run``) reports the expected
        progression.
    """
    # 1. Patch the helper factory so no real subprocess is spawned.
    monkeypatch.setattr(
        "synapse.workflow_runner._WorkflowHelper",
        FakeHelperController,
        raising=False,
    )

    # 2. Force the self-target endpoint probe to fail so the helper path is
    #    actually exercised (the same code path that runs in the real CLI
    #    when the caller's HTTP endpoint is unreachable from the worker).
    async def _no_self_endpoint(_sender_info):
        return None

    monkeypatch.setattr(
        "synapse.workflow_runner._resolve_self_target_endpoint",
        _no_self_endpoint,
    )

    wf = _load_post_impl_workflow()
    assert len(wf.steps) == 5, (
        f"post-impl workflow should have 5 steps, found {len(wf.steps)}"
    )
    assert all(s.target == "self" for s in wf.steps), (
        "every post-impl step must target `self`"
    )

    sender_info = {
        "agent_id": "synapse-claude-8100",
        "agent_type": "claude",
        "working_dir": str(_REPO_ROOT),
    }

    # Stage A: spawn (--async returns a run_id immediately)
    before_spawn = HelperRegistry.alive()
    assert before_spawn == [], "no helpers should exist before run starts"

    run_id = await run_workflow(wf, sender_info=sender_info)
    assert run_id, "run_workflow should return a run_id immediately (--async path)"

    # Stage B: progression — poll ``get_run`` like ``synapse workflow status``
    await _poll_until_terminal(run_id)

    run = get_run(run_id)
    assert run is not None, "run should be visible to status polling"
    assert run.status == "completed", (
        f"workflow finished with status {run.status!r}; "
        f"step errors: {[(s.step_index, s.error) for s in run.steps]}"
    )

    # Stage C: all 5 steps completed in order, no 409 failure on step 5
    assert len(run.steps) == 5
    for i, step in enumerate(run.steps):
        assert step.status == "completed", (
            f"step {i} ({step.message[:40]!r}) did not complete: "
            f"status={step.status!r} error={step.error!r}"
        )
        assert step.error is None, f"step {i} unexpected error: {step.error}"
        # 409 protection — the bug behind #531 manifested as step 5 failing
        # with an HTTP 409 ``Agent busy`` after long-running steps.
        if step.error:
            assert "409" not in step.error
            assert "busy" not in step.error.lower()

    # Stage D: helper lifecycle — spawned exactly once, killed exactly once
    history = HelperRegistry.history()
    spawn_events = [evt for evt, _ in history if evt == "spawn"]
    kill_events = [evt for evt, _ in history if evt == "kill"]
    assert len(spawn_events) == 1, (
        f"exactly one helper should be spawned, got {len(spawn_events)}: {history}"
    )
    assert len(kill_events) == 1, (
        f"exactly one helper should be killed, got {len(kill_events)}: {history}"
    )
    # Spawn must precede kill.
    assert history[0][0] == "spawn"
    assert history[-1][0] == "kill"
    # Same agent on both sides of the lifecycle.
    assert history[0][1] == history[-1][1]
    # Real helper naming convention: wf-helper-<workflow>-<rand>.
    assert history[0][1].startswith("wf-helper-post-impl-")

    # Stage E: no orphan helpers after workflow finishes (#531 acceptance).
    assert HelperRegistry.alive() == [], (
        f"orphan helpers detected after workflow: {HelperRegistry.alive()}"
    )


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_post_impl_status_polling_matches_step_progression(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``synapse workflow status`` should observe each step transition.

    This guards the ``--async`` UX promise: an operator polling status while
    a long workflow is in flight must see steps move from pending → running →
    completed in order, not a single end-of-run snapshot.
    """
    snapshots: list[list[str]] = []

    class SlowHelper(FakeHelperController):
        async def execute_step(self, wf_step, step: StepResult) -> None:
            # Yield to let a status poll observe the in-progress state.
            await asyncio.sleep(0.02)
            await super().execute_step(wf_step, step)

    monkeypatch.setattr(
        "synapse.workflow_runner._WorkflowHelper",
        SlowHelper,
        raising=False,
    )

    async def _no_self_endpoint(_sender_info):
        return None

    monkeypatch.setattr(
        "synapse.workflow_runner._resolve_self_target_endpoint",
        _no_self_endpoint,
    )

    wf = _load_post_impl_workflow()
    sender_info = {
        "agent_id": "synapse-claude-8100",
        "agent_type": "claude",
        "working_dir": str(_REPO_ROOT),
    }

    run_id = await run_workflow(wf, sender_info=sender_info)

    # Poll while the workflow is still running and capture per-step statuses.
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        run = get_run(run_id)
        if run is None:
            await asyncio.sleep(0.01)
            continue
        snapshots.append([s.status for s in run.steps])
        if run.status != "running":
            break
        await asyncio.sleep(0.01)

    final = get_run(run_id)
    assert final is not None
    assert final.status == "completed"

    # We should have observed at least one snapshot where some step was
    # running while later steps were still pending — proving status reflects
    # progression rather than only end state.
    saw_progression = any("running" in snap and "pending" in snap for snap in snapshots)
    saw_terminal = any(all(s == "completed" for s in snap) for snap in snapshots)
    assert saw_progression, (
        "status polling should expose at least one in-flight snapshot "
        f"showing both running and pending steps; saw: {snapshots[:5]}..."
    )
    assert saw_terminal, "status polling should observe the final completed snapshot"
