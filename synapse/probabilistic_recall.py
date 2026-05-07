"""Probabilistic recall over saved task history.

This module implements the small, deterministic core behind issue #227:
given candidate observations from history, score each one using frequency,
recency, and random noise, then roll the dice to decide whether it surfaces
as an advisory memory.
"""

from __future__ import annotations

import math
import random
import re
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from typing import Any

_SECONDS_PER_DAY = 24 * 60 * 60
_KEYWORD_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.:-]*")
_STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "how",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}


def _parse_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        raw = value.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(raw)
        except ValueError:
            dt = datetime.now(timezone.utc)
    else:
        dt = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _encounter_count(observation: dict[str, Any]) -> int:
    metadata = observation.get("metadata")
    if isinstance(metadata, dict):
        value = metadata.get("encounter_count", 1)
        if isinstance(value, int | float):
            return max(1, int(value))
    return 1


def score_recall_candidate(
    observation: dict[str, Any],
    *,
    now: datetime | None = None,
    noise: float = 0.0,
    alpha: float = 1.0,
    beta: float = 1.0,
    gamma: float = 0.35,
    half_life_days: float = 30.0,
) -> float:
    """Return recall probability for a single observation.

    The score follows the #227 intent without deleting data: frequently
    encountered and recent memories are more likely to surface, while noise
    makes recall non-deterministic unless tests inject stable values.
    """
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    timestamp = _parse_timestamp(observation.get("timestamp"))
    age_days = max(0.0, (now - timestamp).total_seconds() / _SECONDS_PER_DAY)
    recency = math.exp(-age_days / max(half_life_days, 0.001))
    frequency = math.log1p(_encounter_count(observation))
    raw = (alpha * frequency) + (beta * recency) + (gamma * noise) - 2.0
    return 1.0 / (1.0 + math.exp(-raw))


def select_recalled_observations(
    observations: Iterable[dict[str, Any]],
    *,
    now: datetime | None = None,
    limit: int = 3,
    random_fn: Callable[[], float] | None = None,
    noise_fn: Callable[[], float] | None = None,
) -> list[dict[str, Any]]:
    """Select observations that pass their recall probability roll."""
    now = now or datetime.now(timezone.utc)
    roll = random_fn or random.random
    noise = noise_fn or (lambda: random.gauss(0.0, 1.0))

    scored: list[tuple[float, dict[str, Any]]] = []
    for observation in observations:
        probability = score_recall_candidate(
            observation,
            now=now,
            noise=noise(),
        )
        if roll() <= probability:
            scored.append((probability, observation))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [observation for _, observation in scored[:limit]]


def extract_recall_keywords(text: str, *, max_keywords: int = 8) -> list[str]:
    """Extract stable search keywords from a task description."""
    seen: set[str] = set()
    keywords: list[str] = []
    for match in _KEYWORD_RE.finditer(text):
        keyword = match.group(0).strip("_.:-")
        normalized = keyword.lower()
        if len(normalized) < 3 or normalized in _STOP_WORDS or normalized in seen:
            continue
        seen.add(normalized)
        keywords.append(keyword)
        if len(keywords) >= max_keywords:
            break
    return keywords


def _one_line(value: Any, max_len: int = 120) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "..."


def build_memory_block(observations: Iterable[dict[str, Any]]) -> str:
    """Format recalled observations as a compact prompt block."""
    items = list(observations)
    if not items:
        return ""

    lines = ["[MEMORY] Related past experiences:"]
    for observation in items:
        input_text = _one_line(observation.get("input"))
        output_text = _one_line(observation.get("output"))
        if output_text:
            lines.append(f"- {input_text} -> {output_text}")
        else:
            lines.append(f"- {input_text}")
    return "\n".join(lines)
