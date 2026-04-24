"""Tests for WAITING debug collection and reporting CLI."""

from __future__ import annotations

import json
import sys
import urllib.error
from io import StringIO
from pathlib import Path
from typing import Any
from unittest.mock import patch

from synapse.cli import main
from synapse.commands.waiting_debug import (
    WaitingDebugCollector,
    WaitingDebugReporter,
    default_waiting_debug_path,
)


class FakeRegistry:
    def __init__(self, agents: dict[str, dict[str, Any]]) -> None:
        self._agents = agents

    def list_agents(self) -> dict[str, dict[str, Any]]:
        return self._agents


def _agent(
    agent_id: str,
    agent_type: str,
    port: int,
    endpoint: str | None = None,
) -> dict[str, Any]:
    return {
        "agent_id": agent_id,
        "agent_type": agent_type,
        "port": port,
        "status": "READY",
        "endpoint": endpoint or f"http://localhost:{port}",
    }


def _snapshot(*attempts: dict[str, Any], renderer_available: bool = True) -> dict:
    return {
        "renderer_available": renderer_available,
        "attempts": list(attempts),
    }


def _attempt(
    *,
    profile: str = "codex",
    pattern_source: str | None = "primary",
    path_used: str = "renderer",
    confidence: float = 1.0,
    pattern_matched: bool = True,
    idle_gate_passed: bool = True,
) -> dict[str, Any]:
    return {
        "timestamp": 1776814438.0,
        "profile": profile,
        "pattern_source": pattern_source,
        "path_used": path_used,
        "confidence": confidence,
        "pattern_matched": pattern_matched,
        "idle_gate_passed": idle_gate_passed,
    }


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_collect_appends_one_jsonl_record_per_agent_with_attempts(tmp_path: Path):
    out_path = tmp_path / "waiting_debug.jsonl"
    out_path.write_text('{"existing": true}\n')
    agents = {
        "synapse-codex-8123": _agent("synapse-codex-8123", "codex", 8123),
        "synapse-claude-8100": _agent("synapse-claude-8100", "claude", 8100),
    }
    payloads = {
        "http://localhost:8123/debug/waiting": _snapshot(_attempt()),
        "http://localhost:8100/debug/waiting": _snapshot(),
    }

    def fetcher(url: str, *, timeout: float) -> dict[str, Any]:
        return payloads[url]

    collector = WaitingDebugCollector(
        registry=FakeRegistry(agents),
        fetcher=fetcher,
        clock=lambda: "2026-04-23T10:00:00+09:00",
    )

    written = collector.collect(out_path=out_path)

    records = _read_jsonl(out_path)
    assert written == 1
    assert records[0] == {"existing": True}
    assert len(records) == 2
    record = records[1]
    assert record["agent_id"] == "synapse-codex-8123"
    assert record["agent_type"] == "codex"
    assert record["port"] == 8123
    assert record["collected_at"] == "2026-04-23T10:00:00+09:00"
    assert record["snapshot"]["attempts"][0]["pattern_source"] == "primary"


def test_collect_include_empty_records_agents_without_attempts(tmp_path: Path):
    out_path = tmp_path / "waiting_debug.jsonl"
    agents = {
        "synapse-claude-8100": _agent("synapse-claude-8100", "claude", 8100),
    }
    collector = WaitingDebugCollector(
        registry=FakeRegistry(agents),
        fetcher=lambda url, *, timeout: _snapshot(),
        clock=lambda: "2026-04-23T10:00:00+09:00",
    )

    written = collector.collect(out_path=out_path, include_empty=True)

    records = _read_jsonl(out_path)
    assert written == 1
    assert records[0]["agent_id"] == "synapse-claude-8100"
    assert records[0]["snapshot"]["attempts"] == []


def test_collect_continues_after_endpoint_error(tmp_path: Path):
    out_path = tmp_path / "waiting_debug.jsonl"
    warnings = StringIO()
    agents = {
        "synapse-claude-8100": _agent("synapse-claude-8100", "claude", 8100),
        "synapse-codex-8123": _agent("synapse-codex-8123", "codex", 8123),
    }

    def fetcher(url: str, *, timeout: float) -> dict[str, Any]:
        if url == "http://localhost:8100/debug/waiting":
            raise urllib.error.URLError("connection refused")
        return _snapshot(_attempt(profile="codex"))

    collector = WaitingDebugCollector(
        registry=FakeRegistry(agents),
        fetcher=fetcher,
        clock=lambda: "2026-04-23T10:00:00+09:00",
        stderr=warnings,
    )

    written = collector.collect(out_path=out_path)

    records = _read_jsonl(out_path)
    assert written == 1
    assert records[0]["agent_id"] == "synapse-codex-8123"
    assert "Warning:" in warnings.getvalue()
    assert "synapse-claude-8100" in warnings.getvalue()


def test_collect_agent_filter_limits_collection(tmp_path: Path):
    out_path = tmp_path / "waiting_debug.jsonl"
    agents = {
        "synapse-claude-8100": _agent("synapse-claude-8100", "claude", 8100),
        "synapse-codex-8123": _agent("synapse-codex-8123", "codex", 8123),
    }
    fetched_urls: list[str] = []

    def fetcher(url: str, *, timeout: float) -> dict[str, Any]:
        fetched_urls.append(url)
        return _snapshot(_attempt(profile="codex"))

    collector = WaitingDebugCollector(
        registry=FakeRegistry(agents),
        fetcher=fetcher,
        clock=lambda: "2026-04-23T10:00:00+09:00",
    )

    collector.collect(out_path=out_path, agent_id="synapse-codex-8123")

    assert fetched_urls == ["http://localhost:8123/debug/waiting"]
    assert _read_jsonl(out_path)[0]["agent_id"] == "synapse-codex-8123"


def test_report_aggregates_waiting_debug_jsonl(tmp_path: Path):
    input_path = tmp_path / "waiting_debug.jsonl"
    input_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "agent_id": "synapse-codex-8123",
                        "agent_type": "codex",
                        "port": 8123,
                        "collected_at": "2026-04-23T10:00:00+09:00",
                        "snapshot": _snapshot(
                            _attempt(
                                profile="codex",
                                pattern_source="primary",
                                path_used="renderer",
                                confidence=1.0,
                                pattern_matched=True,
                                idle_gate_passed=False,
                            ),
                            _attempt(
                                profile="codex",
                                pattern_source=None,
                                path_used="strip_ansi",
                                confidence=0.0,
                                pattern_matched=False,
                                idle_gate_passed=False,
                            ),
                            renderer_available=False,
                        ),
                    }
                ),
                json.dumps(
                    {
                        "agent_id": "synapse-claude-8100",
                        "agent_type": "claude",
                        "port": 8100,
                        "collected_at": "2026-04-23T10:05:00+09:00",
                        "snapshot": _snapshot(
                            _attempt(
                                profile="claude",
                                pattern_source="heuristic",
                                path_used="renderer",
                                confidence=0.6,
                            ),
                            renderer_available=True,
                        ),
                    }
                ),
            ]
        )
        + "\n"
    )
    output = StringIO()
    reporter = WaitingDebugReporter(output=output)

    result = reporter.report(input_path=input_path)

    assert result["total_attempts"] == 3
    assert result["profiles"] == {"claude": 1, "codex": 2}
    assert result["pattern_source"] == {"heuristic": 1, "none": 1, "primary": 1}
    assert result["path_used"] == {"renderer": 2, "strip_ansi": 1}
    assert result["confidence"] == {"0.0": 1, "0.6": 1, "1.0": 1}
    assert result["idle_gate_drops"]["count"] == 1
    assert result["idle_gate_drops"]["ratio"] == 1 / 3
    assert result["renderer_unavailable_agents"]["count"] == 1
    assert result["renderer_unavailable_agents"]["total"] == 2
    assert result["renderer_unavailable_agents"]["ratio"] == 0.5
    text = output.getvalue()
    assert "Total attempts: 3" in text
    assert "Profiles: claude=1, codex=2" in text
    assert "Pattern source: heuristic=1, none=1, primary=1" in text
    assert "Path used: renderer=2, strip_ansi=1" in text
    assert "Confidence: 0.0=1, 0.6=1, 1.0=1" in text
    assert "Idle gate drops: 1/3 (33.3%)" in text
    assert "Renderer unavailable agents: 1/2 (50.0%)" in text


def test_report_json_output_since_and_agent_filter(tmp_path: Path):
    input_path = tmp_path / "waiting_debug.jsonl"
    input_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "agent_id": "synapse-codex-8123",
                        "agent_type": "codex",
                        "port": 8123,
                        "collected_at": "2026-04-23T09:55:00+09:00",
                        "snapshot": _snapshot(_attempt(profile="codex")),
                    }
                ),
                json.dumps(
                    {
                        "agent_id": "synapse-codex-8123",
                        "agent_type": "codex",
                        "port": 8123,
                        "collected_at": "2026-04-23T10:05:00+09:00",
                        "snapshot": _snapshot(
                            _attempt(
                                profile="codex",
                                pattern_source="heuristic",
                                confidence=0.6,
                            )
                        ),
                    }
                ),
                json.dumps(
                    {
                        "agent_id": "synapse-claude-8100",
                        "agent_type": "claude",
                        "port": 8100,
                        "collected_at": "2026-04-23T10:06:00+09:00",
                        "snapshot": _snapshot(_attempt(profile="claude")),
                    }
                ),
            ]
        )
        + "\n"
    )
    output = StringIO()
    reporter = WaitingDebugReporter(output=output)

    result = reporter.report(
        input_path=input_path,
        since="2026-04-23T10:00:00+09:00",
        agent_id="synapse-codex-8123",
        json_output=True,
    )

    emitted = json.loads(output.getvalue())
    assert emitted == result
    assert emitted["period"]["since"] == "2026-04-23T10:00:00+09:00"
    assert emitted["total_attempts"] == 1
    assert emitted["profiles"] == {"codex": 1}
    assert emitted["pattern_source"] == {"heuristic": 1}


def test_report_skips_invalid_jsonl_lines_with_warning(tmp_path: Path):
    input_path = tmp_path / "waiting_debug.jsonl"
    input_path.write_text(
        "\n".join(
            [
                "{not json",
                json.dumps(
                    {
                        "agent_id": "synapse-codex-8123",
                        "agent_type": "codex",
                        "port": 8123,
                        "collected_at": "2026-04-23T10:00:00+09:00",
                        "snapshot": _snapshot(_attempt(profile="codex")),
                    }
                ),
            ]
        )
        + "\n"
    )
    warnings = StringIO()
    reporter = WaitingDebugReporter(output=StringIO(), stderr=warnings)

    result = reporter.report(input_path=input_path)

    assert result["total_attempts"] == 1
    assert "Warning:" in warnings.getvalue()
    assert "line 1" in warnings.getvalue()


def test_waiting_debug_cli_parses_collect_and_report_subcommands(tmp_path: Path):
    with patch("synapse.cli.cmd_waiting_debug") as mock_cmd:
        with patch.object(
            sys,
            "argv",
            [
                "synapse",
                "waiting-debug",
                "collect",
                "--out",
                str(tmp_path / "out.jsonl"),
                "--agent",
                "synapse-codex-8123",
                "--include-empty",
            ],
        ):
            main()

        collect_args = mock_cmd.call_args.args[0]
        assert collect_args.command == "waiting-debug"
        assert collect_args.waiting_debug_command == "collect"
        assert collect_args.out == tmp_path / "out.jsonl"
        assert collect_args.agent == "synapse-codex-8123"
        assert collect_args.include_empty is True

    with patch("synapse.cli.cmd_waiting_debug") as mock_cmd:
        with patch.object(
            sys,
            "argv",
            [
                "synapse",
                "waiting-debug",
                "report",
                "--in",
                str(tmp_path / "in.jsonl"),
                "--since",
                "2026-04-23T10:00:00+09:00",
                "--agent",
                "synapse-codex-8123",
                "--json",
            ],
        ):
            main()

        report_args = mock_cmd.call_args.args[0]
        assert report_args.command == "waiting-debug"
        assert report_args.waiting_debug_command == "report"
        assert report_args.input == tmp_path / "in.jsonl"
        assert report_args.since == "2026-04-23T10:00:00+09:00"
        assert report_args.agent == "synapse-codex-8123"
        assert report_args.json_output is True


def test_collect_passes_timeout_to_fetcher(tmp_path: Path):
    """--timeout should be propagated to the HTTP fetcher."""
    out_path = tmp_path / "waiting_debug.jsonl"
    agents = {
        "synapse-codex-8123": _agent("synapse-codex-8123", "codex", 8123),
    }
    recorded: dict[str, float] = {}

    def fetcher(url: str, *, timeout: float) -> dict[str, Any]:
        recorded["timeout"] = timeout
        return _snapshot(_attempt())

    collector = WaitingDebugCollector(
        registry=FakeRegistry(agents),
        fetcher=fetcher,
        clock=lambda: "2026-04-23T10:00:00+09:00",
        timeout=12.5,
    )

    collector.collect(out_path=out_path)

    assert recorded["timeout"] == 12.5


def test_collect_default_timeout_is_five_seconds(tmp_path: Path):
    """Default timeout should be 5.0s (raised from the legacy 3.0s)."""
    out_path = tmp_path / "waiting_debug.jsonl"
    agents = {
        "synapse-codex-8123": _agent("synapse-codex-8123", "codex", 8123),
    }
    recorded: dict[str, float] = {}

    def fetcher(url: str, *, timeout: float) -> dict[str, Any]:
        recorded["timeout"] = timeout
        return _snapshot(_attempt())

    collector = WaitingDebugCollector(
        registry=FakeRegistry(agents),
        fetcher=fetcher,
        clock=lambda: "2026-04-23T10:00:00+09:00",
    )

    collector.collect(out_path=out_path)

    assert recorded["timeout"] == 5.0


def test_default_waiting_debug_path_is_lazy(tmp_path: Path, monkeypatch):
    """default_waiting_debug_path() should re-evaluate HOME each call."""
    monkeypatch.setenv("HOME", str(tmp_path))
    first = default_waiting_debug_path()
    assert first == tmp_path / ".synapse" / "waiting_debug.jsonl"

    other = tmp_path / "other-home"
    other.mkdir()
    monkeypatch.setenv("HOME", str(other))
    second = default_waiting_debug_path()
    assert second == other / ".synapse" / "waiting_debug.jsonl"
    assert second != first


def test_collect_resolves_default_path_lazily(tmp_path: Path, monkeypatch, capsys):
    """collect() with no out_path should resolve ~/.synapse at call time."""
    monkeypatch.setenv("HOME", str(tmp_path))
    agents = {
        "synapse-codex-8123": _agent("synapse-codex-8123", "codex", 8123),
    }

    def fetcher(url: str, *, timeout: float) -> dict[str, Any]:
        return _snapshot(_attempt())

    collector = WaitingDebugCollector(
        registry=FakeRegistry(agents),
        fetcher=fetcher,
        clock=lambda: "2026-04-23T10:00:00+09:00",
    )

    collector.collect()

    expected = tmp_path / ".synapse" / "waiting_debug.jsonl"
    assert expected.exists()


def test_report_writes_json_to_out_path(tmp_path: Path):
    """--out should write the JSON report to a file."""
    input_path = tmp_path / "waiting_debug.jsonl"
    input_path.write_text(
        json.dumps(
            {
                "agent_id": "synapse-codex-8123",
                "agent_type": "codex",
                "port": 8123,
                "collected_at": "2026-04-23T10:00:00+09:00",
                "snapshot": _snapshot(_attempt(profile="codex")),
            }
        )
        + "\n"
    )
    out_path = tmp_path / "report.json"
    stdout = StringIO()
    reporter = WaitingDebugReporter(output=stdout)

    result = reporter.report(input_path=input_path, json_output=True, out_path=out_path)

    assert out_path.exists()
    written = json.loads(out_path.read_text())
    assert written == result
    assert written["total_attempts"] == 1
    assert stdout.getvalue() == ""


def test_report_warns_on_invalid_collected_at(tmp_path: Path):
    """Records with unparseable collected_at should produce a warning."""
    input_path = tmp_path / "waiting_debug.jsonl"
    input_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "agent_id": "synapse-codex-8123",
                        "agent_type": "codex",
                        "port": 8123,
                        "collected_at": "not-a-valid-timestamp",
                        "snapshot": _snapshot(_attempt(profile="codex")),
                    }
                ),
                json.dumps(
                    {
                        "agent_id": "synapse-codex-8123",
                        "agent_type": "codex",
                        "port": 8123,
                        "collected_at": "2026-04-23T10:05:00+09:00",
                        "snapshot": _snapshot(_attempt(profile="codex")),
                    }
                ),
            ]
        )
        + "\n"
    )
    warnings = StringIO()
    reporter = WaitingDebugReporter(output=StringIO(), stderr=warnings)

    result = reporter.report(input_path=input_path, since="2026-04-23T09:00:00+09:00")

    assert result["total_attempts"] == 1
    warnings_text = warnings.getvalue()
    assert "Warning:" in warnings_text
    assert "collected_at" in warnings_text
    assert "not-a-valid-timestamp" in warnings_text


def test_cmd_waiting_debug_passes_zero_timeout_literally(monkeypatch):
    """`--timeout 0` must reach the Collector as 0.0, not be replaced by default."""
    from argparse import Namespace

    from synapse.commands.waiting_debug import cmd_waiting_debug

    captured: dict[str, float] = {}

    class _Recorder:
        def __init__(self, *, timeout: float) -> None:
            captured["timeout"] = timeout

        def collect(self, **_: Any) -> int:
            return 0

    monkeypatch.setattr(
        "synapse.commands.waiting_debug.WaitingDebugCollector", _Recorder
    )

    args = Namespace(
        waiting_debug_command="collect",
        timeout=0.0,
        out=None,
        agent=None,
        include_empty=False,
    )
    cmd_waiting_debug(args)

    assert captured["timeout"] == 0.0


def test_waiting_debug_cli_parses_timeout_and_out_flags(tmp_path: Path):
    with patch("synapse.cli.cmd_waiting_debug") as mock_cmd:
        with patch.object(
            sys,
            "argv",
            [
                "synapse",
                "waiting-debug",
                "collect",
                "--timeout",
                "12.5",
            ],
        ):
            main()
        collect_args = mock_cmd.call_args.args[0]
        assert collect_args.timeout == 12.5

    with patch("synapse.cli.cmd_waiting_debug") as mock_cmd:
        with patch.object(
            sys,
            "argv",
            [
                "synapse",
                "waiting-debug",
                "report",
                "--out",
                str(tmp_path / "report.json"),
                "--json",
            ],
        ):
            main()
        report_args = mock_cmd.call_args.args[0]
        assert report_args.out == tmp_path / "report.json"
        assert report_args.json_output is True
