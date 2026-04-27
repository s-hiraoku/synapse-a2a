"""Regression tests for millisecond history timestamps (#661)."""

import re
import sqlite3
import time
from pathlib import Path

from synapse.history import HistoryManager

MILLISECOND_TIMESTAMP = re.compile(r"\.\d{3}$")


def _history_manager(tmp_path: Path) -> HistoryManager:
    return HistoryManager(db_path=str(tmp_path / "history.db"))


def _save_observation(
    history: HistoryManager,
    task_id: str,
    input_text: str = "input",
) -> None:
    history.save_observation(
        task_id=task_id,
        agent_name="claude",
        session_id="session-661",
        input_text=input_text,
        output_text="output",
        status="completed",
    )


def _insert_legacy_observation(db_path: str, task_id: str, timestamp: str) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO observations
            (session_id, agent_name, task_id, input, output, status, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "legacy-session",
                "claude",
                task_id,
                "legacy input",
                "legacy output",
                "completed",
                timestamp,
            ),
        )


def test_save_observation_uses_millisecond_timestamp(tmp_path: Path):
    history = _history_manager(tmp_path)

    _save_observation(history, "task-661")

    observation = history.list_observations(limit=1)[0]
    assert MILLISECOND_TIMESTAMP.search(observation["timestamp"])


def test_consecutive_save_observations_have_distinct_timestamps(tmp_path: Path):
    history = _history_manager(tmp_path)

    _save_observation(history, "task-661-a")
    time.sleep(0.002)
    _save_observation(history, "task-661-b")

    observations = history.list_observations(limit=2)
    timestamps = {obs["timestamp"] for obs in observations}
    assert len(timestamps) == 2


def test_update_observation_status_uses_millisecond_timestamp(tmp_path: Path):
    history = _history_manager(tmp_path)
    _save_observation(history, "task-661-update")

    assert history.update_observation_status("task-661-update", "failed")

    observation = history.get_observation("task-661-update")
    assert observation is not None
    assert MILLISECOND_TIMESTAMP.search(observation["timestamp"])


def test_order_by_timestamp_handles_mixed_precision(tmp_path: Path):
    history = _history_manager(tmp_path)
    _insert_legacy_observation(
        history.db_path,
        task_id="task-661-legacy",
        timestamp="2026-04-27 11:37:06",
    )

    _save_observation(history, "task-661-new")

    observations = history.list_observations(limit=2)
    assert observations[0]["task_id"] == "task-661-new"
    assert observations[1]["task_id"] == "task-661-legacy"


def test_existing_legacy_rows_still_returned(tmp_path: Path):
    history = _history_manager(tmp_path)
    _insert_legacy_observation(
        history.db_path,
        task_id="task-661-legacy",
        timestamp="2026-04-27 11:37:06",
    )

    observations = history.list_observations(limit=1)
    assert observations[0]["task_id"] == "task-661-legacy"
    assert observations[0]["timestamp"] == "2026-04-27 11:37:06"
