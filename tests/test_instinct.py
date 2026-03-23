"""Tests for instinct storage and pattern analysis."""

from __future__ import annotations

from synapse.observation import ObservationStore


def test_instinct_store_crud(tmp_path):
    """InstinctStore should support save/get/list/delete/count."""
    from synapse.instinct import InstinctStore

    store = InstinctStore(db_path=str(tmp_path / "instincts.db"))

    saved = store.save(
        trigger="pytest fails with import error",
        action="check __init__.py exports",
        confidence=0.3,
        scope="project",
        domain="testing",
        source_observations=["obs-1", "obs-2"],
        project_hash="proj-1",
        agent_id="synapse-claude-8100",
    )

    assert saved["trigger"] == "pytest fails with import error"
    fetched = store.get(saved["id"])
    assert fetched is not None
    assert fetched["action"] == "check __init__.py exports"

    listed = store.list(scope="project", domain="testing", project_hash="proj-1")
    assert len(listed) == 1
    assert listed[0]["id"] == saved["id"]
    assert store.count(scope="project", domain="testing", project_hash="proj-1") == 1

    assert store.delete(saved["id"]) is True
    assert store.get(saved["id"]) is None
    assert store.count() == 0


def test_instinct_store_update_confidence_and_promote(tmp_path):
    """InstinctStore should update confidence and promote scope."""
    from synapse.instinct import InstinctStore

    store = InstinctStore(db_path=str(tmp_path / "instincts.db"))
    saved = store.save(
        trigger="repeated timeout errors",
        action="retry with backoff",
        confidence=0.3,
        scope="project",
        domain="debugging",
        source_observations=["obs-1"],
        project_hash="proj-1",
        agent_id="synapse-codex-8110",
    )

    assert store.update_confidence(saved["id"], 0.7) is True
    updated = store.get(saved["id"])
    assert updated is not None
    assert updated["confidence"] == 0.7

    assert store.promote(saved["id"]) is True
    promoted = store.get(saved["id"])
    assert promoted is not None
    assert promoted["scope"] == "global"


def test_pattern_analyzer_detects_repeated_errors(tmp_path):
    """Repeated error types should produce an instinct candidate."""
    from synapse.instinct import InstinctStore
    from synapse.pattern_analyzer import PatternAnalyzer

    obs_store = ObservationStore(db_path=str(tmp_path / "observations.db"))
    instinct_store = InstinctStore(db_path=str(tmp_path / "instincts.db"))
    analyzer = PatternAnalyzer(obs_store, instinct_store)

    obs_store.save(
        event_type="error",
        agent_id="synapse-claude-8100",
        agent_type="claude",
        data={
            "error_type": "import_error",
            "error_message": "cannot import name X",
            "recovery_action": "check exports",
        },
        project_hash="proj-1",
    )
    obs_store.save(
        event_type="error",
        agent_id="synapse-codex-8110",
        agent_type="codex",
        data={
            "error_type": "import_error",
            "error_message": "cannot import name Y",
            "recovery_action": "check exports",
        },
        project_hash="proj-1",
    )

    results = analyzer.analyze(project_hash="proj-1")

    assert len(results) == 1
    assert results[0]["domain"] == "debugging"
    assert results[0]["confidence"] == 0.3
    assert len(results[0]["source_observations"]) == 2


def test_pattern_analyzer_confidence_rises_for_duplicate_instincts(tmp_path):
    """analyze_and_save should raise confidence when the same pattern repeats."""
    from synapse.instinct import InstinctStore
    from synapse.pattern_analyzer import PatternAnalyzer

    obs_store = ObservationStore(db_path=str(tmp_path / "observations.db"))
    instinct_store = InstinctStore(db_path=str(tmp_path / "instincts.db"))
    analyzer = PatternAnalyzer(obs_store, instinct_store)

    for idx in range(3):
        obs_store.save(
            event_type="status_change",
            agent_id=f"synapse-claude-81{idx}0",
            agent_type="claude",
            data={
                "from_status": "PROCESSING",
                "to_status": "READY",
                "trigger": "idle_detected",
            },
            project_hash="proj-1",
        )

    first_saved = analyzer.analyze_and_save(project_hash="proj-1")
    assert len(first_saved) == 1
    first = instinct_store.list(project_hash="proj-1")[0]
    assert first["confidence"] == 0.5

    for idx in range(2):
        obs_store.save(
            event_type="status_change",
            agent_id=f"synapse-codex-81{idx}0",
            agent_type="codex",
            data={
                "from_status": "PROCESSING",
                "to_status": "READY",
                "trigger": "idle_detected",
            },
            project_hash="proj-1",
        )

    second_saved = analyzer.analyze_and_save(project_hash="proj-1")
    assert len(second_saved) == 1
    second = instinct_store.list(project_hash="proj-1")[0]
    assert second["confidence"] == 0.7


def test_pattern_analyzer_detects_success_pattern_by_sender(tmp_path):
    """Repeated successful tasks from the same sender should produce a candidate."""
    from synapse.instinct import InstinctStore
    from synapse.pattern_analyzer import PatternAnalyzer

    obs_store = ObservationStore(db_path=str(tmp_path / "observations.db"))
    instinct_store = InstinctStore(db_path=str(tmp_path / "instincts.db"))
    analyzer = PatternAnalyzer(obs_store, instinct_store)

    obs_ids: list[str] = []
    for idx in range(2):
        received = obs_store.save(
            event_type="task_received",
            agent_id=f"synapse-claude-81{idx}0",
            agent_type="claude",
            data={
                "message": "Review PR",
                "sender": "synapse-codex-8110",
                "priority": 3,
            },
            project_hash="proj-1",
        )
        completed = obs_store.save(
            event_type="task_completed",
            agent_id=f"synapse-claude-81{idx}0",
            agent_type="claude",
            data={
                "task_id": f"task-{idx}",
                "duration": 1.2,
                "status": "completed",
                "output_summary": "done",
            },
            project_hash="proj-1",
        )
        obs_ids.extend([received["id"], completed["id"]])

    results = analyzer.analyze(project_hash="proj-1")
    triggers = {item["trigger"] for item in results}
    assert any("synapse-codex-8110" in trigger for trigger in triggers)
