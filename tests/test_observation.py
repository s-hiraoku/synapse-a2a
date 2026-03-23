"""Tests for observation storage and collection."""

from __future__ import annotations

import threading
import time

import pytest

from synapse.controller import TerminalController


def test_observation_store_crud_and_search(tmp_path):
    """ObservationStore should support save/list/search/count/clear."""
    from synapse.observation import ObservationStore

    store = ObservationStore(db_path=str(tmp_path / "observations.db"))

    first = store.save(
        event_type="task_received",
        agent_id="synapse-claude-8100",
        agent_type="claude",
        data={
            "message": "Review this patch",
            "sender": "synapse-codex-8110",
            "priority": 3,
        },
        project_hash="proj-1",
    )
    second = store.save(
        event_type="error",
        agent_id="synapse-claude-8100",
        agent_type="claude",
        data={
            "error_type": "quota",
            "error_message": "limit exceeded",
            "recovery_action": "retry",
        },
        project_hash="proj-1",
    )

    assert first is not None
    assert second is not None
    assert first["event_type"] == "task_received"
    assert second["event_type"] == "error"

    rows = store.list(agent_id="synapse-claude-8100")
    assert len(rows) == 2
    assert {row["event_type"] for row in rows} == {"task_received", "error"}

    matches = store.search("limit exceeded")
    assert len(matches) == 1
    assert matches[0]["id"] == second["id"]

    assert store.count() == 2
    assert store.count(event_type="error") == 1
    assert store.clear() == 2
    assert store.count() == 0


def test_observation_collector_record_methods(tmp_path):
    """ObservationCollector should persist typed events."""
    from synapse.observation import ObservationCollector, ObservationStore

    store = ObservationStore(db_path=str(tmp_path / "observations.db"))
    collector = ObservationCollector(store=store)

    collector.record_task_received(
        agent_id="synapse-claude-8100",
        agent_type="claude",
        message="Investigate failure",
        sender="synapse-codex-8110",
        priority=4,
    )
    collector.record_task_completed(
        agent_id="synapse-claude-8100",
        agent_type="claude",
        task_id="task-123",
        duration=2.5,
        status="completed",
        output_summary="Done",
    )
    collector.record_error(
        agent_id="synapse-claude-8100",
        agent_type="claude",
        error_type="timeout",
        error_message="request timed out",
        recovery_action="retry later",
    )
    collector.record_status_change(
        agent_id="synapse-claude-8100",
        agent_type="claude",
        from_status="PROCESSING",
        to_status="READY",
        trigger="idle_detected",
    )
    collector.record_file_operation(
        agent_id="synapse-claude-8100",
        agent_type="claude",
        file_path="synapse/controller.py",
        operation_type="write",
    )

    rows = store.list(limit=10)
    assert len(rows) == 5
    latest_by_type = {row["event_type"]: row for row in rows}
    assert latest_by_type["task_received"]["data"]["message"] == "Investigate failure"
    assert latest_by_type["task_completed"]["data"]["task_id"] == "task-123"
    assert latest_by_type["error"]["data"]["error_type"] == "timeout"
    assert latest_by_type["status_change"]["data"]["to_status"] == "READY"
    assert (
        latest_by_type["file_operation"]["data"]["file_path"] == "synapse/controller.py"
    )


def test_observation_collector_from_env_respects_enable_flag(tmp_path, monkeypatch):
    """Observation collection should be disabled via environment variable."""
    from synapse.observation import ObservationCollector

    monkeypatch.setenv("SYNAPSE_OBSERVATION_ENABLED", "false")
    monkeypatch.setenv("SYNAPSE_OBSERVATION_DB_PATH", str(tmp_path / "observations.db"))

    collector = ObservationCollector.from_env()
    result = collector.record_task_received(
        agent_id="synapse-claude-8100",
        agent_type="claude",
        message="Should not persist",
        sender="synapse-codex-8110",
        priority=1,
    )

    assert collector.enabled is False
    assert result is None
    assert collector.store.count() == 0


def test_observation_store_is_thread_safe(tmp_path):
    """Concurrent writes should not lose observations."""
    from synapse.observation import ObservationStore

    store = ObservationStore(db_path=str(tmp_path / "observations.db"))

    def _writer(idx: int) -> None:
        store.save(
            event_type="status_change",
            agent_id=f"agent-{idx % 3}",
            agent_type="codex",
            data={"from_status": "PROCESSING", "to_status": "READY", "idx": idx},
        )

    threads = [threading.Thread(target=_writer, args=(i,)) for i in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert store.count() == 20


def test_terminal_controller_records_status_changes(tmp_path):
    """TerminalController should record status transitions through ObservationCollector."""
    from synapse.observation import ObservationCollector

    collector = ObservationCollector.from_env(db_path=str(tmp_path / "observations.db"))
    controller = TerminalController(
        command="echo test",
        idle_regex=r"\$",
        agent_id="synapse-claude-8100",
        agent_type="claude",
    )
    controller.attach_observation_collector(collector)

    controller.running = True
    controller.master_fd = 1
    controller._identity_sent = True
    controller.output_buffer = b"prompt $"
    controller._last_output_time = time.time() - 2

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("synapse.controller.threading.Thread", _ImmediateThread)
        controller._check_idle_state(b"$")

    rows = collector.store.list(limit=5)
    assert any(
        row["event_type"] == "status_change"
        and row["data"]["from_status"] == "PROCESSING"
        and row["data"]["to_status"] == "READY"
        for row in rows
    )


class _ImmediateThread:
    """Run callback bodies immediately for deterministic controller tests."""

    def __init__(self, target=None, args=(), kwargs=None, daemon=None):  # noqa: ANN001
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}

    def start(self) -> None:
        if self._target:
            self._target(*self._args, **self._kwargs)
