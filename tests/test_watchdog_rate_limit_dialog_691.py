"""Tests for watchdog rate-limit dialog detection (#691)."""

from __future__ import annotations

import argparse
import json
from unittest.mock import patch

from synapse.status import PROCESSING, READY, WAITING

OBSERVED_PTY_TAIL = (
    "1. <some-mini-model>           Small, fast, and cost-efficient model for simpler coding tasks.\n"
    "2. Keep current model\n"
    "3. Keep current model (never show again)  Hide future rate limit reminders about switching models.\n"
    "Press enter to confirm or esc to go back"
)


def test_detect_rate_limit_dialog_matches_observed_pty_tail() -> None:
    from synapse.watchdog import _detect_rate_limit_dialog

    assert _detect_rate_limit_dialog(OBSERVED_PTY_TAIL) is True


def test_detect_rate_limit_dialog_ignores_normal_codex_prompt() -> None:
    from synapse.watchdog import _detect_rate_limit_dialog

    normal_tail = "> Run /review on my current changes\n  gpt-5.4-mini medium · /..."
    assert _detect_rate_limit_dialog(normal_tail) is False


def test_detect_rate_limit_dialog_handles_none_or_empty() -> None:
    from synapse.watchdog import _detect_rate_limit_dialog

    assert _detect_rate_limit_dialog(None) is False
    assert _detect_rate_limit_dialog("") is False


def test_evaluate_agent_returns_rate_limit_dialog_alarm() -> None:
    from synapse.watchdog import evaluate_agent

    report = evaluate_agent(
        agent_info={
            "agent_id": "synapse-codex-8124",
            "status": WAITING,
            "registered_at": 1_776_800_000.0,
            "last_status_change_at": 1_776_800_000.0,
        },
        history=[],
        now=1_776_800_000.0,
        pty_tail=OBSERVED_PTY_TAIL,
    )

    assert report.alarm == "rate_limit_dialog"
    assert (
        report.alarm_reason == "PTY tail contains codex CLI rate-limit reminder dialog"
    )


def test_evaluate_agent_skips_rate_limit_dialog_alarm_when_not_waiting() -> None:
    from synapse.watchdog import evaluate_agent

    for non_waiting_status in (READY, PROCESSING):
        report = evaluate_agent(
            agent_info={
                "agent_id": "synapse-codex-8124",
                "status": non_waiting_status,
                "registered_at": 1_776_800_000.0,
                "last_status_change_at": 1_776_800_000.0,
            },
            history=[],
            now=1_776_800_000.0,
            pty_tail=OBSERVED_PTY_TAIL,
        )

        assert report.alarm is None
        assert report.alarm_reason is None


def test_collect_reports_skips_pty_fetch_for_non_waiting_agents() -> None:
    from synapse.commands.watchdog import _collect_reports

    with (
        patch("synapse.commands.watchdog.AgentRegistry") as registry_cls,
        patch("synapse.commands.watchdog.HistoryManager") as history_cls,
        patch("synapse.commands.watchdog.is_process_alive", return_value=True),
        patch("synapse.commands.watchdog._fetch_debug_pty_tail") as fetch_pty,
        patch("synapse.commands.watchdog.evaluate_agent") as evaluate,
    ):
        registry_cls.return_value.list_agents.return_value = {
            "synapse-codex-8124": {
                "agent_id": "synapse-codex-8124",
                "status": PROCESSING,
                "registered_at": 1_776_800_000.0,
                "last_status_change_at": 1_776_800_000.0,
            }
        }
        history_cls.from_env.return_value.list_observations.return_value = []
        evaluate.return_value = object()

        _collect_reports(now=1_776_800_000.0)

    fetch_pty.assert_not_called()
    assert evaluate.call_args.kwargs["pty_tail"] is None


def test_alarm_only_filter_includes_rate_limit_dialog(capsys) -> None:
    from synapse.commands.watchdog import cmd_watchdog_check
    from synapse.watchdog import WatchdogReport

    with (
        patch("synapse.commands.watchdog.AgentRegistry") as registry_cls,
        patch("synapse.commands.watchdog.HistoryManager") as history_cls,
        patch("synapse.commands.watchdog.is_process_alive", return_value=True),
        patch("synapse.commands.watchdog.evaluate_agent") as evaluate,
    ):
        registry_cls.return_value.list_agents.return_value = {
            "synapse-codex-8124": {
                "agent_id": "synapse-codex-8124",
                "status": WAITING,
                "registered_at": 1_776_800_000.0,
                "last_status_change_at": 1_776_800_000.0,
            }
        }
        history_cls.from_env.return_value.list_observations.return_value = []
        evaluate.return_value = WatchdogReport(
            "synapse-codex-8124",
            WAITING,
            100.0,
            100.0,
            None,
            "rate_limit_dialog",
            "PTY tail contains codex CLI rate-limit reminder dialog",
        )

        cmd_watchdog_check(argparse.Namespace(alarm_only=True, json=True))

    rows = json.loads(capsys.readouterr().out)
    assert rows == [
        {
            "agent_id": "synapse-codex-8124",
            "status": WAITING,
            "uptime_seconds": 100.0,
            "same_status_seconds": 100.0,
            "last_outbound_seconds_ago": None,
            "alarm": "rate_limit_dialog",
            "alarm_reason": "PTY tail contains codex CLI rate-limit reminder dialog",
        }
    ]
