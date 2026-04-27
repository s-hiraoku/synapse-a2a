"""Pure watchdog evaluation logic for stuck-agent detection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from synapse.status import PROCESSING, RATE_LIMITED, READY, SENDING_REPLY

RATE_LIMITED_SECONDS = 30 * 60
SENDING_REPLY_SECONDS = 60
PROCESSING_SECONDS = 30 * 60
OUTBOUND_IDLE_SECONDS = 10 * 60
SPAWN_READY_SECONDS = 60
SPAWN_READY_MAX_SECONDS = 5 * 60


@dataclass(frozen=True)
class WatchdogReport:
    agent_id: str
    status: str
    uptime_seconds: float | None
    same_status_seconds: float | None
    last_outbound_seconds_ago: float | None
    alarm: str | None


def _seconds_since(value: Any, now: float) -> float | None:
    timestamp = _timestamp_to_epoch(value)
    if timestamp is None:
        return None
    return max(0.0, now - timestamp)


def _timestamp_to_epoch(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            pass

        normalized = value.strip()
        if not normalized:
            return None
        if normalized.endswith("Z"):
            normalized = f"{normalized[:-1]}+00:00"
        for candidate in (normalized, normalized.replace(" ", "T", 1)):
            try:
                return datetime.fromisoformat(candidate).timestamp()
            except ValueError:
                continue
    return None


def _last_outbound_seconds_ago(
    history: list[dict[str, Any]], now: float
) -> float | None:
    for row in history:
        seconds_ago = _seconds_since(row.get("timestamp"), now)
        if seconds_ago is not None:
            return seconds_ago
    return None


def evaluate_agent(
    *,
    agent_info: dict[str, Any],
    history: list[dict[str, Any]],
    now: float,
) -> WatchdogReport:
    """Evaluate one agent against the Stage 1 watchdog heuristics."""
    agent_id = str(agent_info.get("agent_id") or "")
    status = str(agent_info.get("status") or "-")
    uptime_seconds = _seconds_since(agent_info.get("registered_at"), now)
    same_status_seconds = _seconds_since(agent_info.get("last_status_change_at"), now)
    last_outbound_seconds_ago = _last_outbound_seconds_ago(history, now)

    alarm: str | None = None
    if (
        status == RATE_LIMITED
        and same_status_seconds is not None
        and same_status_seconds > RATE_LIMITED_SECONDS
    ):
        alarm = "Rate-limited > 30m"
    elif (
        status == SENDING_REPLY
        and same_status_seconds is not None
        and same_status_seconds > SENDING_REPLY_SECONDS
    ):
        alarm = "Send stuck > 60s"
    elif (
        status == PROCESSING
        and same_status_seconds is not None
        and same_status_seconds > PROCESSING_SECONDS
        and (
            last_outbound_seconds_ago is None
            or last_outbound_seconds_ago > OUTBOUND_IDLE_SECONDS
        )
    ):
        alarm = "Stuck-on-reply suspected"
    elif (
        status != READY
        and same_status_seconds is None
        and uptime_seconds is not None
        and uptime_seconds > SPAWN_READY_SECONDS
        and uptime_seconds <= SPAWN_READY_MAX_SECONDS
    ):
        alarm = "Spawn never ready"

    return WatchdogReport(
        agent_id=agent_id,
        status=status,
        uptime_seconds=uptime_seconds,
        same_status_seconds=same_status_seconds,
        last_outbound_seconds_ago=last_outbound_seconds_ago,
        alarm=alarm,
    )
