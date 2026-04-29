"""Watchdog command implementation for one-shot stuck-agent checks."""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from dataclasses import asdict
from typing import Any

from rich.console import Console
from rich.table import Table

from synapse.commands.renderers.rich_renderer import format_elapsed
from synapse.history import HistoryManager
from synapse.paths import get_history_db_path
from synapse.port_manager import is_process_alive
from synapse.registry import AgentRegistry
from synapse.watchdog import WatchdogReport, evaluate_agent

_PTY_DEBUG_TIMEOUT = 1.5


def _format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "-"
    return format_elapsed(max(0.0, seconds))


def _format_last_outbound(seconds: float | None) -> str:
    if seconds is None:
        return "(none)"
    return f"{format_elapsed(max(0.0, seconds))} ago"


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


def _report_to_dict(report: WatchdogReport) -> dict[str, Any]:
    data = asdict(report)
    if data.get("alarm_reason") is None:
        data.pop("alarm_reason", None)
    return data


def _outbound_history_for_agent(
    history_manager: HistoryManager,
    agent_id: str,
) -> list[dict[str, Any]]:
    observations = history_manager.list_observations(limit=10, agent_id=agent_id)
    return [
        observation
        for observation in observations
        if _metadata_sender_id(observation.get("metadata")) == agent_id
    ]


def _endpoint_for(info: dict[str, Any]) -> str | None:
    endpoint = info.get("endpoint")
    if isinstance(endpoint, str) and endpoint:
        return endpoint.rstrip("/")
    port = info.get("port")
    if isinstance(port, int):
        return f"http://localhost:{port}"
    return None


def _fetch_debug_pty_tail(info: dict[str, Any]) -> str | None:
    endpoint = _endpoint_for(info)
    if not endpoint:
        return None

    try:
        with urllib.request.urlopen(
            f"{endpoint}/debug/pty", timeout=_PTY_DEBUG_TIMEOUT
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, TimeoutError, urllib.error.URLError, json.JSONDecodeError):
        return None

    display = payload.get("display")
    if not isinstance(display, list):
        return None
    return "\n".join(str(line) for line in display)


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
        pty_tail = _fetch_debug_pty_tail(agent_info)
        reports.append(
            evaluate_agent(
                agent_info=agent_info,
                history=history,
                now=now,
                pty_tail=pty_tail,
            )
        )

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
        print(json.dumps([_report_to_dict(report) for report in reports], indent=2))
        return

    _print_table(reports)
