"""Shared agent view helpers for list/status commands."""

from __future__ import annotations

import re
from typing import Any

CANONICAL_JSON_FIELDS = (
    "agent_id",
    "status",
    "current_task_preview",
    "task_received_at",
    "uptime_seconds",
    "input_required_tasks",
)


def strip_status_annotations(status: Any) -> Any:
    """Return the machine-readable status without human list annotations."""
    if not isinstance(status, str):
        return status
    return status.replace(" [ORPHAN]", "")


def build_agent_json_view(
    agent: dict[str, Any],
    *,
    now: float,
    include_fields: tuple[str, ...],
) -> dict[str, Any]:
    """Build the programmatic JSON view for an agent."""
    entry = {field: agent.get(field) for field in include_fields}

    if "status" in entry:
        entry["status"] = strip_status_annotations(entry["status"])

    if "uptime_seconds" in include_fields:
        uptime = agent.get("uptime_seconds")
        if uptime is None:
            registered_at = agent.get("registered_at")
            if isinstance(now, (int, float)) and isinstance(
                registered_at, (int, float)
            ):
                uptime = now - registered_at
        entry["uptime_seconds"] = uptime

    if "current_task_preview" in include_fields:
        entry["current_task_preview"] = agent.get("current_task_preview")
    if "task_received_at" in include_fields:
        entry["task_received_at"] = agent.get("task_received_at")
    if "input_required_tasks" in include_fields:
        entry["input_required_tasks"] = agent.get("input_required_tasks") or []

    return entry


def resolve_agent_from_snapshot(
    agents: list[dict[str, Any]],
    target: str,
) -> dict[str, Any] | None:
    """Resolve a target from a preloaded agent list using registry priority rules."""
    for info in agents:
        if info.get("name") == target:
            return info

    for info in agents:
        if info.get("agent_id") == target:
            return info

    if match := re.match(r"^([\w-]+)-(\d+)$", target):
        agent_type, port_str = match.groups()
        port = int(port_str)
        for info in agents:
            if info.get("agent_type") == agent_type and info.get("port") == port:
                return info

    type_matches = [info for info in agents if info.get("agent_type") == target]
    return type_matches[0] if len(type_matches) == 1 else None
