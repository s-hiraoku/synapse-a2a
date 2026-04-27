"""Pure watchdog evaluation logic for stuck-agent detection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from synapse.status import PROCESSING, RATE_LIMITED, READY, SENDING_REPLY

_THIRTY_MINUTES = 30 * 60

RATE_LIMITED_ALARM_SECONDS = _THIRTY_MINUTES
SENDING_REPLY_ALARM_SECONDS = 60
PROCESSING_STALL_SECONDS = _THIRTY_MINUTES
OUTBOUND_IDLE_SECONDS = 10 * 60
SPAWN_READY_GRACE_SECONDS = 60
SPAWN_READY_WINDOW_SECONDS = 5 * 60


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


_DURATION_RULES: tuple[tuple[str, float, str], ...] = (
    (RATE_LIMITED, RATE_LIMITED_ALARM_SECONDS, "Rate-limited > 30m"),
    (SENDING_REPLY, SENDING_REPLY_ALARM_SECONDS, "Send stuck > 60s"),
)


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

    alarm = _evaluate_alarm(
        status=status,
        same_status_seconds=same_status_seconds,
        uptime_seconds=uptime_seconds,
        last_outbound_seconds_ago=last_outbound_seconds_ago,
    )

    return WatchdogReport(
        agent_id=agent_id,
        status=status,
        uptime_seconds=uptime_seconds,
        same_status_seconds=same_status_seconds,
        last_outbound_seconds_ago=last_outbound_seconds_ago,
        alarm=alarm,
    )


def _evaluate_alarm(
    *,
    status: str,
    same_status_seconds: float | None,
    uptime_seconds: float | None,
    last_outbound_seconds_ago: float | None,
) -> str | None:
    for rule_status, threshold, message in _DURATION_RULES:
        if (
            status == rule_status
            and same_status_seconds is not None
            and same_status_seconds > threshold
        ):
            return message

    if (
        status == PROCESSING
        and same_status_seconds is not None
        and same_status_seconds > PROCESSING_STALL_SECONDS
        and (
            last_outbound_seconds_ago is None
            or last_outbound_seconds_ago > OUTBOUND_IDLE_SECONDS
        )
    ):
        return "Stuck-on-reply suspected"

    if (
        status != READY
        and same_status_seconds is None
        and uptime_seconds is not None
        and SPAWN_READY_GRACE_SECONDS < uptime_seconds <= SPAWN_READY_WINDOW_SECONDS
    ):
        return "Spawn never ready"

    return None
