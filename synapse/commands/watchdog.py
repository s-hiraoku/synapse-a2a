"""Watchdog command implementation for one-shot stuck-agent checks."""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict
from typing import Any

from rich.console import Console
from rich.table import Table

from synapse.history import HistoryManager
from synapse.paths import get_history_db_path
from synapse.port_manager import is_process_alive
from synapse.registry import AgentRegistry
from synapse.watchdog import WatchdogReport, evaluate_agent


def _format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "-"
    total_seconds = max(0, int(seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}m {secs:02d}s"


def _format_last_outbound(seconds: float | None) -> str:
    if seconds is None:
        return "(none)"
    total_seconds = max(0, int(seconds))
    if total_seconds < 60:
        return f"{total_seconds}s ago"
    minutes, secs = divmod(total_seconds, 60)
    if minutes < 60:
        return f"{minutes}m ago" if secs == 0 else f"{minutes}m {secs}s ago"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m ago"


def _metadata_sender_id(metadata: Any) -> str | None:
    if not isinstance(metadata, dict):
        return None
    sender_id = metadata.get("sender_id")
    if isinstance(sender_id, str):
        return sender_id
    sender = metadata.get("sender")
    if isinstance(sender, dict):
        nested_sender_id = sender.get("sender_id")
        if isinstance(nested_sender_id, str):
            return nested_sender_id
    return None


def _outbound_history_for_agent(
    history_manager: HistoryManager,
    agent_id: str,
) -> list[dict[str, Any]]:
    observations = history_manager.list_observations(limit=50, agent_id=agent_id)
    return [
        observation
        for observation in observations
        if _metadata_sender_id(observation.get("metadata")) == agent_id
    ]


def _live_agents(registry: AgentRegistry) -> dict[str, dict[str, Any]]:
    live_agents: dict[str, dict[str, Any]] = {}
    for agent_id, info in registry.list_agents().items():
        pid = info.get("pid")
        if isinstance(pid, int) and not is_process_alive(pid):
            continue
        live_agents[agent_id] = info
    return live_agents


def _collect_reports(now: float) -> list[WatchdogReport]:
    registry = AgentRegistry()
    history_manager = HistoryManager.from_env(db_path=get_history_db_path())
    reports: list[WatchdogReport] = []

    for agent_id, agent_info in sorted(_live_agents(registry).items()):
        history = _outbound_history_for_agent(history_manager, agent_id)
        reports.append(evaluate_agent(agent_info=agent_info, history=history, now=now))

    return reports


def _print_table(reports: list[WatchdogReport]) -> None:
    table = Table(show_header=True, header_style="bold")
    table.add_column("ID")
    table.add_column("STATUS")
    table.add_column("UPTIME")
    table.add_column("SAME_STATUS_FOR")
    table.add_column("LAST_OUTBOUND")
    table.add_column("ALARM", no_wrap=True)

    for report in reports:
        table.add_row(
            report.agent_id,
            report.status,
            _format_duration(report.uptime_seconds),
            _format_duration(report.same_status_seconds),
            _format_last_outbound(report.last_outbound_seconds_ago),
            f"⚠ {report.alarm}" if report.alarm else "-",
        )

    Console(width=200).print(table)


def cmd_watchdog_check(args: argparse.Namespace) -> None:
    """Run a one-shot stuck-agent watchdog check."""
    reports = _collect_reports(now=time.time())
    if getattr(args, "alarm_only", False):
        reports = [report for report in reports if report.alarm]

    if getattr(args, "json", False):
        print(json.dumps([asdict(report) for report in reports], indent=2))
        return

    _print_table(reports)
