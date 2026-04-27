"""Tests for one-shot agent watchdog stuck detection (#646)."""

from __future__ import annotations

import argparse
import json
from typing import Any
from unittest.mock import patch

from synapse.status import PROCESSING, RATE_LIMITED, READY, SENDING_REPLY, WAITING

NOW = 1_776_800_000.0


def _agent_info(
    *,
    agent_id: str = "synapse-codex-8122",
    status: str = READY,
    registered_delta: float = 120.0,
    last_status_delta: float | None = 0.0,
) -> dict[str, Any]:
    info: dict[str, Any] = {
        "agent_id": agent_id,
        "status": status,
        "registered_at": NOW - registered_delta,
        "pid": 12345,
        "port": 8122,
    }
    if last_status_delta is not None:
        info["last_status_change_at"] = NOW - last_status_delta
    return info


def _history_row(*, timestamp_delta: float) -> dict[str, Any]:
    return {
        "task_id": "task-outbound",
        "agent_name": "codex",
        "timestamp": NOW - timestamp_delta,
        "metadata": {"sender": {"sender_id": "synapse-codex-8122"}},
    }


def test_evaluate_processing_stuck_with_no_outbound() -> None:
    from synapse.watchdog import evaluate_agent

    report = evaluate_agent(
        agent_info=_agent_info(status=PROCESSING, last_status_delta=31 * 60),
        history=[],
        now=NOW,
    )

    assert report.alarm == "Stuck-on-reply suspected"
    assert report.same_status_seconds == 31 * 60
    assert report.last_outbound_seconds_ago is None


def test_evaluate_processing_stuck_but_recent_outbound() -> None:
    from synapse.watchdog import evaluate_agent

    report = evaluate_agent(
        agent_info=_agent_info(status=PROCESSING, last_status_delta=31 * 60),
        history=[_history_row(timestamp_delta=5 * 60)],
        now=NOW,
    )

    assert report.alarm is None
    assert report.last_outbound_seconds_ago == 5 * 60


def test_evaluate_sending_reply_too_long() -> None:
    from synapse.watchdog import evaluate_agent

    report = evaluate_agent(
        agent_info=_agent_info(status=SENDING_REPLY, last_status_delta=90),
        history=[],
        now=NOW,
    )

    assert report.alarm == "Send stuck > 60s"


def test_evaluate_rate_limited_too_long() -> None:
    from synapse.watchdog import evaluate_agent

    report = evaluate_agent(
        agent_info=_agent_info(status=RATE_LIMITED, last_status_delta=31 * 60),
        history=[],
        now=NOW,
    )

    assert report.alarm == "Rate-limited > 30m"


def test_evaluate_spawn_never_ready() -> None:
    from synapse.watchdog import evaluate_agent

    report = evaluate_agent(
        agent_info=_agent_info(
            status=WAITING,
            registered_delta=70,
            last_status_delta=None,
        ),
        history=[],
        now=NOW,
    )

    assert report.alarm == "Spawn never ready"
    assert report.same_status_seconds is None


def test_evaluate_healthy_processing() -> None:
    from synapse.watchdog import evaluate_agent

    report = evaluate_agent(
        agent_info=_agent_info(status=PROCESSING, last_status_delta=5 * 60),
        history=[_history_row(timestamp_delta=60)],
        now=NOW,
    )

    assert report.alarm is None


def test_evaluate_missing_last_status_change_at_skips_judgement() -> None:
    from synapse.watchdog import evaluate_agent

    report = evaluate_agent(
        agent_info=_agent_info(
            status=PROCESSING,
            registered_delta=2 * 60 * 60,
            last_status_delta=None,
        ),
        history=[],
        now=NOW,
    )

    assert report.alarm is None
    assert report.same_status_seconds is None


def test_watchdog_check_alarm_only_filters_clean_agents(capsys) -> None:
    from synapse.commands.watchdog import cmd_watchdog_check
    from synapse.watchdog import WatchdogReport

    agents = {
        "clean": _agent_info(agent_id="clean", status=READY),
        "stuck": _agent_info(agent_id="stuck", status=PROCESSING),
    }

    with (
        patch("synapse.commands.watchdog.AgentRegistry") as registry_cls,
        patch("synapse.commands.watchdog.HistoryManager") as history_cls,
        patch("synapse.commands.watchdog.is_process_alive", return_value=True),
        patch("synapse.commands.watchdog.evaluate_agent") as evaluate,
    ):
        registry_cls.return_value.list_agents.return_value = agents
        history_cls.from_env.return_value.list_observations.return_value = []
        evaluate.side_effect = [
            WatchdogReport("clean", READY, 30.0, 30.0, None, None),
            WatchdogReport(
                "stuck",
                PROCESSING,
                3_600.0,
                1_900.0,
                None,
                "Stuck-on-reply suspected",
            ),
        ]

        cmd_watchdog_check(argparse.Namespace(alarm_only=True, json=False))

    output = capsys.readouterr().out
    assert "stuck" in output
    assert "Stuck-on-reply suspected" in output
    assert "clean" not in output


def test_watchdog_check_json_output(capsys) -> None:
    from synapse.commands.watchdog import cmd_watchdog_check
    from synapse.watchdog import WatchdogReport

    agents = {"stuck": _agent_info(agent_id="stuck", status=PROCESSING)}

    with (
        patch("synapse.commands.watchdog.AgentRegistry") as registry_cls,
        patch("synapse.commands.watchdog.HistoryManager") as history_cls,
        patch("synapse.commands.watchdog.is_process_alive", return_value=True),
        patch("synapse.commands.watchdog.evaluate_agent") as evaluate,
    ):
        registry_cls.return_value.list_agents.return_value = agents
        history_cls.from_env.return_value.list_observations.return_value = []
        evaluate.return_value = WatchdogReport(
            "stuck",
            PROCESSING,
            3_600.0,
            1_900.0,
            None,
            "Stuck-on-reply suspected",
        )

        cmd_watchdog_check(argparse.Namespace(alarm_only=False, json=True))

    rows = json.loads(capsys.readouterr().out)
    assert rows == [
        {
            "agent_id": "stuck",
            "status": PROCESSING,
            "uptime_seconds": 3_600.0,
            "same_status_seconds": 1_900.0,
            "last_outbound_seconds_ago": None,
            "alarm": "Stuck-on-reply suspected",
        }
    ]
