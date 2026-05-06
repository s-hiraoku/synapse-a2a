"""Regression tests for explicit agent lifecycle state management (#608)."""

from __future__ import annotations


def test_lifecycle_state_normalizes_existing_statuses() -> None:
    from synapse.status import (
        PROCESSING,
        READY,
        WAITING_FOR_INPUT,
        AgentLifecycleState,
        normalize_lifecycle_state,
    )

    assert normalize_lifecycle_state(READY) == AgentLifecycleState.IDLE
    assert normalize_lifecycle_state(PROCESSING) == AgentLifecycleState.RUNNING
    assert (
        normalize_lifecycle_state(WAITING_FOR_INPUT)
        == AgentLifecycleState.WAITING_INPUT
    )


def test_readiness_gate_blocks_input_required_tasks_even_if_registry_is_ready() -> None:
    from synapse.status import READY, AgentLifecycleState, evaluate_readiness

    readiness = evaluate_readiness(
        READY,
        input_required_tasks=[{"task_id": "task-1"}],
    )

    assert readiness.ready is False
    assert readiness.lifecycle == AgentLifecycleState.WAITING_INPUT
    assert "input_required" in readiness.reason


def test_readiness_gate_allows_idle_agent() -> None:
    from synapse.status import READY, AgentLifecycleState, evaluate_readiness

    readiness = evaluate_readiness(READY)

    assert readiness.ready is True
    assert readiness.lifecycle == AgentLifecycleState.IDLE
    assert readiness.reason == "ready"
