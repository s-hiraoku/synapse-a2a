"""Tests for probabilistic recall memory (#227)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def _observation(
    task_id: str,
    *,
    input_text: str,
    output_text: str,
    timestamp: datetime,
    encounter_count: int = 1,
) -> dict[str, object]:
    return {
        "task_id": task_id,
        "input": input_text,
        "output": output_text,
        "timestamp": timestamp.isoformat(),
        "metadata": {"encounter_count": encounter_count},
    }


def test_recall_scores_frequency_and_recency() -> None:
    """Frequent recent memories should score above rare old memories."""
    from synapse.probabilistic_recall import score_recall_candidate

    now = datetime(2026, 5, 7, tzinfo=timezone.utc)
    recent_frequent = _observation(
        "recent",
        input_text="Fix JWT refresh token test",
        output_text="Use frozen clock for token expiry",
        timestamp=now - timedelta(days=1),
        encounter_count=6,
    )
    old_rare = _observation(
        "old",
        input_text="Fix JWT refresh token test",
        output_text="Use frozen clock for token expiry",
        timestamp=now - timedelta(days=120),
        encounter_count=1,
    )

    assert score_recall_candidate(recent_frequent, now=now, noise=0.0) > (
        score_recall_candidate(old_rare, now=now, noise=0.0)
    )


def test_select_recalled_observations_uses_probability_rolls() -> None:
    """Recall selection should be deterministic when RNG is injected."""
    from synapse.probabilistic_recall import select_recalled_observations

    now = datetime(2026, 5, 7, tzinfo=timezone.utc)
    observations = [
        _observation(
            "keep",
            input_text="Docker build cache",
            output_text="Use uv sync before tests",
            timestamp=now,
            encounter_count=10,
        ),
        _observation(
            "drop",
            input_text="Old unrelated task",
            output_text="Noisy detail",
            timestamp=now - timedelta(days=365),
            encounter_count=1,
        ),
    ]
    rolls = iter([0.01, 0.99])

    selected = select_recalled_observations(
        observations,
        now=now,
        random_fn=lambda: next(rolls),
        noise_fn=lambda: 0.0,
    )

    assert [item["task_id"] for item in selected] == ["keep"]


def test_build_memory_block_formats_recalled_observations() -> None:
    """Selected memories should be formatted as a compact advisory block."""
    from synapse.probabilistic_recall import build_memory_block

    block = build_memory_block(
        [
            {
                "task_id": "t1",
                "input": "Implement auth refresh tokens",
                "output": "Remember to freeze time in expiry tests",
            }
        ]
    )

    assert block.startswith("[MEMORY] Related past experiences:")
    assert "Implement auth refresh tokens" in block
    assert "freeze time" in block


def test_history_manager_recall_searches_existing_history(tmp_path) -> None:
    """HistoryManager should expose a recall helper backed by saved history."""
    from synapse.history import HistoryManager

    manager = HistoryManager(db_path=str(tmp_path / "history.db"))
    manager.save_observation(
        task_id="jwt-1",
        agent_name="claude",
        session_id="s1",
        input_text="Implement JWT refresh token endpoint",
        output_text="Freeze time when testing token expiry",
        status="completed",
        metadata={"encounter_count": 8},
    )

    recalled = manager.recall_observations(
        "JWT token expiry bug",
        random_fn=lambda: 0.0,
        noise_fn=lambda: 0.0,
    )

    assert len(recalled) == 1
    assert recalled[0]["task_id"] == "jwt-1"
