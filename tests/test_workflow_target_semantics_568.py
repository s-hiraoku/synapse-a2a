"""Regression tests for workflow target resolution semantics from issue #568."""

from __future__ import annotations

from typing import Any

import pytest

from synapse.workflow import WorkflowStep
from synapse.workflow_runner import StepResult, _execute_step, _resolve_target_endpoint


def _agent(
    agent_id: str,
    agent_type: str,
    endpoint: str,
    *,
    name: str | None = None,
    working_dir: str = "/repo/current",
) -> dict[str, Any]:
    return {
        "agent_id": agent_id,
        "agent_type": agent_type,
        "name": name,
        "endpoint": endpoint,
        "working_dir": working_dir,
        "pid": 1234,
    }


def _patch_registry(
    monkeypatch: pytest.MonkeyPatch, entries: list[dict[str, Any]]
) -> None:
    from synapse.canvas import server as canvas_server

    monkeypatch.setattr(
        canvas_server,
        "_iter_registry_entries",
        lambda live_only=True: iter(entries),
    )


def _patch_workflow_cwd(monkeypatch: pytest.MonkeyPatch, cwd: str) -> None:
    import synapse.workflow_runner as workflow_runner

    monkeypatch.setattr(workflow_runner.os, "getcwd", lambda: cwd)


def test_bare_type_with_same_dir_match_resolves(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_workflow_cwd(monkeypatch, "/repo/current")
    _patch_registry(
        monkeypatch,
        [
            _agent(
                "synapse-claude-8100",
                "claude",
                "http://localhost:8100",
                working_dir="/repo/other",
            ),
            _agent(
                "synapse-claude-8101",
                "claude",
                "http://localhost:8101",
                working_dir="/repo/current",
            ),
        ],
    )

    assert _resolve_target_endpoint("claude") == "http://localhost:8101"


def test_bare_type_with_only_other_dir_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_workflow_cwd(monkeypatch, "/repo/current")
    _patch_registry(
        monkeypatch,
        [
            _agent(
                "synapse-claude-8100",
                "claude",
                "http://localhost:8100",
                working_dir="/repo/other",
            ),
        ],
    )

    assert _resolve_target_endpoint("claude") is None


def test_bare_type_with_no_matches_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_workflow_cwd(monkeypatch, "/repo/current")
    _patch_registry(
        monkeypatch,
        [
            _agent(
                "synapse-codex-8124",
                "codex",
                "http://localhost:8124",
                working_dir="/repo/current",
            ),
        ],
    )

    assert _resolve_target_endpoint("claude") is None


def test_specific_name_resolves_globally(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_workflow_cwd(monkeypatch, "/repo/current")
    _patch_registry(
        monkeypatch,
        [
            _agent(
                "synapse-claude-8100",
                "claude",
                "http://localhost:8100",
                name="my-agent",
                working_dir="/repo/other",
            ),
        ],
    )

    assert _resolve_target_endpoint("my-agent") == "http://localhost:8100"


@pytest.mark.asyncio
async def test_self_target_unaffected(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _resolve_self(sender_info):
        return "http://localhost:8122"

    async def _send(endpoint, wf_step, sender_info):
        return 0, "ok", "", "task-1"

    def _resolve_target(target: str) -> str | None:
        raise AssertionError("self target should not use bare target resolution")

    monkeypatch.setattr(
        "synapse.workflow_runner._resolve_self_target_endpoint",
        _resolve_self,
    )
    monkeypatch.setattr("synapse.workflow_runner._send_workflow_request", _send)
    monkeypatch.setattr(
        "synapse.workflow_runner._resolve_target_endpoint",
        _resolve_target,
    )

    step = StepResult(step_index=0, target="self", message="status")
    await _execute_step(
        WorkflowStep(target="self", message="status"),
        step,
        sender_info={"agent_id": "synapse-codex-8122", "agent_type": "codex"},
    )

    assert step.status == "completed"
    assert step.output == "ok"


def test_canvas_caller_uses_legacy_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    from synapse.canvas import server as canvas_server

    _patch_registry(
        monkeypatch,
        [
            _agent(
                "synapse-claude-8100",
                "claude",
                "http://localhost:8100",
                working_dir="/repo/other",
            ),
        ],
    )

    assert (
        canvas_server._resolve_agent_endpoint(
            "claude",
            caller_working_dir="/repo/current",
        )
        == "http://localhost:8100"
    )


@pytest.mark.asyncio
async def test_auto_spawn_triggered_when_strict_resolution_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_workflow_cwd(monkeypatch, "/repo/current")
    entries = [
        _agent(
            "synapse-claude-8100",
            "claude",
            "http://localhost:8100",
            working_dir="/repo/other",
        ),
    ]
    _patch_registry(monkeypatch, entries)

    spawned_targets: list[str] = []
    send_endpoints: list[str] = []

    def _spawn(target: str) -> bool:
        spawned_targets.append(target)
        entries.append(
            _agent(
                "synapse-claude-8101",
                "claude",
                "http://localhost:8101",
                working_dir="/repo/current",
            )
        )
        return True

    async def _send(endpoint, wf_step, sender_info):
        send_endpoints.append(endpoint)
        return 0, "spawned ok", "", "task-1"

    monkeypatch.setattr("synapse.workflow_runner._try_spawn_and_wait", _spawn)
    monkeypatch.setattr("synapse.workflow_runner._send_workflow_request", _send)

    step = StepResult(step_index=0, target="claude", message="do work")
    await _execute_step(
        WorkflowStep(target="claude", message="do work"),
        step,
        workflow_auto_spawn=True,
    )

    assert spawned_targets == ["claude"]
    assert send_endpoints == ["http://localhost:8101"]
    assert step.status == "completed"
    assert step.output == "spawned ok"
