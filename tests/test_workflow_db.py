"""Tests for synapse.workflow_db — SQLite persistent workflow run storage."""

from __future__ import annotations

import time

import pytest

from synapse.workflow_db import WorkflowRunDB


@pytest.fixture
def db(tmp_path):
    """Create a WorkflowRunDB backed by a temporary directory."""
    return WorkflowRunDB(db_path=str(tmp_path / "workflow_runs.db"))


def _make_run_dict(
    run_id: str = "run-1",
    workflow_name: str = "test-wf",
    status: str = "running",
    num_steps: int = 2,
) -> dict:
    started = time.time()
    steps = [
        {
            "step_index": i,
            "target": f"agent{i}",
            "message": f"step {i}",
            "status": "pending",
            "started_at": None,
            "completed_at": None,
            "output": None,
            "error": None,
        }
        for i in range(num_steps)
    ]
    return {
        "run_id": run_id,
        "workflow_name": workflow_name,
        "status": status,
        "started_at": started,
        "completed_at": None,
        "steps": steps,
    }


# ------------------------------------------------------------------
# 1. Schema creation
# ------------------------------------------------------------------
def test_db_creates_tables(db):
    """DB initialisation creates runs and run_steps tables."""
    import sqlite3

    conn = sqlite3.connect(db.db_path)
    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    conn.close()
    assert "runs" in tables
    assert "run_steps" in tables


# ------------------------------------------------------------------
# 2. Save and load round-trip
# ------------------------------------------------------------------
def test_save_and_get_run(db):
    """A saved run can be loaded back with all fields intact."""
    d = _make_run_dict()
    db.save_run(d)

    loaded = db.get_run("run-1")
    assert loaded is not None
    assert loaded["run_id"] == "run-1"
    assert loaded["workflow_name"] == "test-wf"
    assert loaded["status"] == "running"
    assert len(loaded["steps"]) == 2
    assert loaded["steps"][0]["target"] == "agent0"
    assert loaded["steps"][1]["target"] == "agent1"


# ------------------------------------------------------------------
# 3. get_run returns None for missing run
# ------------------------------------------------------------------
def test_get_run_not_found(db):
    """get_run returns None when run_id doesn't exist."""
    assert db.get_run("nonexistent") is None


# ------------------------------------------------------------------
# 4. update_run_status
# ------------------------------------------------------------------
def test_update_run_status(db):
    """update_run_status changes status and completed_at."""
    d = _make_run_dict()
    db.save_run(d)

    now = time.time()
    db.update_run_status("run-1", "completed", completed_at=now)

    loaded = db.get_run("run-1")
    assert loaded is not None
    assert loaded["status"] == "completed"
    assert loaded["completed_at"] == pytest.approx(now, abs=0.01)


# ------------------------------------------------------------------
# 5. update_step
# ------------------------------------------------------------------
def test_update_step(db):
    """update_step persists step status changes."""
    d = _make_run_dict()
    db.save_run(d)

    now = time.time()
    db.update_step(
        "run-1",
        {
            "step_index": 0,
            "status": "completed",
            "started_at": now - 1.0,
            "completed_at": now,
            "output": "result text",
            "error": None,
        },
    )

    loaded = db.get_run("run-1")
    assert loaded is not None
    step0 = loaded["steps"][0]
    assert step0["status"] == "completed"
    assert step0["output"] == "result text"
    assert step0["completed_at"] == pytest.approx(now, abs=0.01)


# ------------------------------------------------------------------
# 6. get_runs ordering (most recent first)
# ------------------------------------------------------------------
def test_get_runs_ordering(db):
    """get_runs returns runs ordered by started_at descending."""
    base_time = time.time()
    for i in range(5):
        d = _make_run_dict(run_id=f"run-{i}", num_steps=1)
        d["started_at"] = base_time + i
        db.save_run(d)

    runs = db.get_runs()
    assert len(runs) == 5
    assert runs[0]["run_id"] == "run-4"  # most recent
    assert runs[4]["run_id"] == "run-0"  # oldest


# ------------------------------------------------------------------
# 7. Survives "restart" (new DB instance reads old data)
# ------------------------------------------------------------------
def test_persistence_across_instances(tmp_path):
    """Data written by one DB instance is readable by a new instance."""
    db_path = str(tmp_path / "workflow_runs.db")

    db1 = WorkflowRunDB(db_path=db_path)
    d = _make_run_dict(run_id="persistent-run")
    db1.save_run(d)
    db1.update_run_status("persistent-run", "completed", completed_at=time.time())

    # Simulate restart: create a brand new instance
    db2 = WorkflowRunDB(db_path=db_path)
    loaded = db2.get_run("persistent-run")
    assert loaded is not None
    assert loaded["status"] == "completed"
    assert len(loaded["steps"]) == 2


# ------------------------------------------------------------------
# 8. save_run with INSERT OR REPLACE updates existing run
# ------------------------------------------------------------------
def test_save_run_upsert(db):
    """Calling save_run twice with the same run_id updates the row."""
    d = _make_run_dict()
    db.save_run(d)

    d["status"] = "completed"
    d["completed_at"] = time.time()
    d["steps"][0]["status"] = "completed"
    d["steps"][0]["output"] = "done"
    db.save_run(d)

    loaded = db.get_run("run-1")
    assert loaded is not None
    assert loaded["status"] == "completed"
    assert loaded["steps"][0]["status"] == "completed"
    assert loaded["steps"][0]["output"] == "done"


# ------------------------------------------------------------------
# 9. delete_runs_older_than
# ------------------------------------------------------------------
def test_delete_old_runs(db):
    """delete_runs_older_than removes old runs and their steps."""
    base_time = time.time()
    for i in range(5):
        d = _make_run_dict(run_id=f"run-{i}", num_steps=1)
        d["started_at"] = base_time + i
        db.save_run(d)

    # Delete runs older than run-3's started_at
    cutoff = base_time + 3
    db.delete_runs_older_than(cutoff)

    runs = db.get_runs()
    ids = {r["run_id"] for r in runs}
    assert "run-0" not in ids
    assert "run-1" not in ids
    assert "run-2" not in ids
    assert "run-3" in ids
    assert "run-4" in ids


# ------------------------------------------------------------------
# 10. get_runs limit
# ------------------------------------------------------------------
def test_get_runs_respects_limit(db):
    """get_runs respects the limit parameter."""
    base_time = time.time()
    for i in range(10):
        d = _make_run_dict(run_id=f"run-{i}", num_steps=1)
        d["started_at"] = base_time + i
        db.save_run(d)

    runs = db.get_runs(limit=3)
    assert len(runs) == 3
    assert runs[0]["run_id"] == "run-9"
