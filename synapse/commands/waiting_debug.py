"""WAITING detection debug collection and reporting commands."""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from collections import Counter
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import IO, Any, Protocol

from synapse.registry import AgentRegistry

DEFAULT_WAITING_DEBUG_TIMEOUT = 5.0


def default_waiting_debug_path() -> Path:
    """Resolve the default JSONL path at call time so `HOME` overrides apply."""
    return Path.home() / ".synapse" / "waiting_debug.jsonl"


class AgentRegistryLike(Protocol):
    def list_agents(self) -> dict[str, dict[str, Any]]: ...


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _http_get_json(
    url: str, *, timeout: float = DEFAULT_WAITING_DEBUG_TIMEOUT
) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        payload = response.read().decode("utf-8")
    data = json.loads(payload)
    return data if isinstance(data, dict) else {}


class WaitingDebugCollector:
    """Collect `/debug/waiting` snapshots from registered agents."""

    def __init__(
        self,
        registry: AgentRegistryLike | None = None,
        fetcher: Callable[..., dict[str, Any]] | None = None,
        clock: Callable[[], str] | None = None,
        stderr: IO[str] | None = None,
        timeout: float = DEFAULT_WAITING_DEBUG_TIMEOUT,
    ) -> None:
        self._registry = registry or AgentRegistry()
        self._fetcher = fetcher or _http_get_json
        self._clock = clock or _now_iso
        self._stderr = stderr or sys.stderr
        self._timeout = timeout

    def collect(
        self,
        *,
        out_path: Path | str | None = None,
        agent_id: str | None = None,
        include_empty: bool = False,
    ) -> int:
        """Collect waiting debug snapshots and append them as JSONL records."""
        resolved = out_path if out_path is not None else default_waiting_debug_path()
        path = Path(resolved).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)

        written = 0
        with path.open("a", encoding="utf-8") as output:
            for current_agent_id, info in self._iter_agents(agent_id):
                endpoint = self._endpoint_for(info)
                if not endpoint:
                    self._warn(current_agent_id, "missing endpoint and port")
                    continue

                try:
                    snapshot = self._fetcher(
                        f"{endpoint}/debug/waiting", timeout=self._timeout
                    )
                except (
                    OSError,
                    TimeoutError,
                    urllib.error.URLError,
                    json.JSONDecodeError,
                    ValueError,
                ) as exc:
                    self._warn(current_agent_id, str(exc))
                    continue

                attempts = snapshot.get("attempts")
                if not isinstance(attempts, list):
                    attempts = []
                    snapshot["attempts"] = attempts
                if not attempts and not include_empty:
                    continue

                output.write(
                    json.dumps(
                        {
                            "agent_id": current_agent_id,
                            "agent_type": info.get("agent_type"),
                            "port": info.get("port"),
                            "collected_at": self._clock(),
                            "snapshot": snapshot,
                        },
                        sort_keys=True,
                    )
                    + "\n"
                )
                written += 1

        return written

    def _iter_agents(self, agent_id: str | None) -> list[tuple[str, dict[str, Any]]]:
        agents = self._registry.list_agents()
        if agent_id is not None:
            info = agents.get(agent_id)
            return [(agent_id, info)] if info is not None else []
        return list(agents.items())

    def _endpoint_for(self, info: dict[str, Any]) -> str | None:
        endpoint = info.get("endpoint")
        if isinstance(endpoint, str) and endpoint:
            return endpoint.rstrip("/")
        port = info.get("port")
        if isinstance(port, int):
            return f"http://localhost:{port}"
        return None

    def _warn(self, agent_id: str, reason: str) -> None:
        print(
            f"Warning: failed to collect waiting debug for {agent_id}: {reason}",
            file=self._stderr,
        )


class WaitingDebugReporter:
    """Aggregate waiting debug JSONL records."""

    def __init__(
        self,
        output: IO[str] | None = None,
        stderr: IO[str] | None = None,
    ) -> None:
        self._output = output or sys.stdout
        self._stderr = stderr or sys.stderr

    def report(
        self,
        *,
        input_path: Path | str | None = None,
        since: str | None = None,
        agent_id: str | None = None,
        json_output: bool = False,
        out_path: Path | str | None = None,
    ) -> dict[str, Any]:
        resolved_input = (
            input_path if input_path is not None else default_waiting_debug_path()
        )
        records = list(
            self._iter_records(Path(resolved_input).expanduser(), since, agent_id)
        )
        result = self._aggregate(records, since)

        if out_path is not None:
            serialized = json.dumps(result, indent=2, sort_keys=True) + "\n"
            out = Path(out_path).expanduser()
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(serialized, encoding="utf-8")
        elif json_output:
            self._output.write(json.dumps(result, indent=2, sort_keys=True) + "\n")
        else:
            self._render_text(result)

        return result

    def _iter_records(
        self, path: Path, since: str | None, agent_id: str | None
    ) -> list[dict[str, Any]]:
        since_dt = _parse_iso_datetime(since) if since else None
        records: list[dict[str, Any]] = []

        try:
            input_file = path.open(encoding="utf-8")
        except FileNotFoundError:
            return []

        with input_file:
            for line_number, line in enumerate(input_file, start=1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    print(
                        f"Warning: skipping invalid JSONL line {line_number}: {exc}",
                        file=self._stderr,
                    )
                    continue
                if not isinstance(record, dict):
                    continue
                if agent_id is not None and record.get("agent_id") != agent_id:
                    continue
                if since_dt is not None and not self._record_is_since(
                    record, since_dt, line_number
                ):
                    continue
                records.append(record)

        return records

    def _record_is_since(
        self, record: dict[str, Any], since_dt: datetime, line_number: int
    ) -> bool:
        collected_at = record.get("collected_at")
        if not isinstance(collected_at, str):
            return False
        try:
            collected_dt = _parse_iso_datetime(collected_at)
        except ValueError as exc:
            print(
                "Warning: record at line "
                f"{line_number} has unparseable collected_at: "
                f"{collected_at!r} ({exc})",
                file=self._stderr,
            )
            return False
        if collected_dt is None:
            return False
        return collected_dt >= since_dt

    def _aggregate(
        self, records: list[dict[str, Any]], since: str | None
    ) -> dict[str, Any]:
        profiles: Counter[str] = Counter()
        pattern_source: Counter[str] = Counter()
        path_used: Counter[str] = Counter()
        confidence: Counter[str] = Counter()
        idle_gate_drops = 0
        total_attempts = 0
        agents_seen: set[str] = set()
        renderer_unavailable_agents: set[str] = set()
        collected_at_values: list[str] = []

        for record in records:
            agent_key = str(record.get("agent_id") or "")
            if agent_key:
                agents_seen.add(agent_key)
            collected_at = record.get("collected_at")
            if isinstance(collected_at, str):
                collected_at_values.append(collected_at)

            snapshot = record.get("snapshot")
            if not isinstance(snapshot, dict):
                snapshot = {}
            if snapshot.get("renderer_available") is False and agent_key:
                renderer_unavailable_agents.add(agent_key)

            attempts = snapshot.get("attempts")
            if not isinstance(attempts, list):
                continue

            for attempt in attempts:
                if not isinstance(attempt, dict):
                    continue
                total_attempts += 1
                profiles[_label(attempt.get("profile"), record.get("agent_type"))] += 1
                pattern_source[_label(attempt.get("pattern_source"), "none")] += 1
                path_used[_label(attempt.get("path_used"), "none")] += 1
                confidence[_confidence_label(attempt.get("confidence"))] += 1
                if (
                    attempt.get("pattern_matched") is True
                    and attempt.get("idle_gate_passed") is not True
                ):
                    idle_gate_drops += 1

        renderer_total = len(agents_seen)
        renderer_count = len(renderer_unavailable_agents)
        return {
            "period": {
                "since": since,
                "first_collected_at": min(collected_at_values)
                if collected_at_values
                else None,
                "last_collected_at": max(collected_at_values)
                if collected_at_values
                else None,
            },
            "total_attempts": total_attempts,
            "profiles": _sorted_dict(profiles),
            "pattern_source": _sorted_dict(pattern_source),
            "path_used": _sorted_dict(path_used),
            "confidence": _sorted_dict(confidence),
            "idle_gate_drops": {
                "count": idle_gate_drops,
                "total": total_attempts,
                "ratio": _ratio(idle_gate_drops, total_attempts),
            },
            "renderer_unavailable_agents": {
                "count": renderer_count,
                "total": renderer_total,
                "ratio": _ratio(renderer_count, renderer_total),
            },
        }

    def _render_text(self, result: dict[str, Any]) -> None:
        period = result["period"]
        self._writeln("=== Waiting Debug Report ===")
        self._writeln(f"Since:           {period.get('since') or '-'}")
        self._writeln(f"First collected: {period.get('first_collected_at') or '-'}")
        self._writeln(f"Last collected:  {period.get('last_collected_at') or '-'}")
        self._writeln(f"Total attempts: {result['total_attempts']}")
        self._writeln()
        self._writeln("--- By profile ---")
        self._writeln(f"Profiles: {_format_counter(result['profiles'])}")
        self._writeln()
        self._writeln("--- Pattern source ---")
        self._writeln(f"Pattern source: {_format_counter(result['pattern_source'])}")
        self._writeln()
        self._writeln("--- Path used ---")
        self._writeln(f"Path used: {_format_counter(result['path_used'])}")
        self._writeln()
        self._writeln("--- Confidence ---")
        self._writeln(f"Confidence: {_format_counter(result['confidence'])}")
        self._writeln()
        self._writeln("--- Idle gate drops ---")
        drops = result["idle_gate_drops"]
        self._writeln(
            "Idle gate drops: "
            f"{drops['count']}/{drops['total']} ({drops['ratio'] * 100:.1f}%)"
        )
        self._writeln()
        self._writeln("--- Renderer unavailable ---")
        renderer = result["renderer_unavailable_agents"]
        self._writeln(
            "Renderer unavailable agents: "
            f"{renderer['count']}/{renderer['total']} "
            f"({renderer['ratio'] * 100:.1f}%)"
        )

    def _writeln(self, text: str = "") -> None:
        self._output.write(text + "\n")


def cmd_waiting_debug(args: Any) -> None:
    """Dispatch waiting-debug subcommands."""
    subcommand = getattr(args, "waiting_debug_command", None)
    if subcommand == "collect":
        timeout_arg = getattr(args, "timeout", None)
        timeout = DEFAULT_WAITING_DEBUG_TIMEOUT if timeout_arg is None else timeout_arg
        collector = WaitingDebugCollector(timeout=timeout)
        written = collector.collect(
            out_path=getattr(args, "out", None),
            agent_id=getattr(args, "agent", None),
            include_empty=getattr(args, "include_empty", False),
        )
        print(f"Collected {written} waiting debug snapshot(s)")
        return

    if subcommand == "report":
        reporter = WaitingDebugReporter()
        reporter.report(
            input_path=getattr(args, "input", None),
            since=getattr(args, "since", None),
            agent_id=getattr(args, "agent", None),
            json_output=getattr(args, "json_output", False),
            out_path=getattr(args, "out", None),
        )
        return

    raise SystemExit("Specify a waiting-debug subcommand.")


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _label(value: Any, fallback: Any) -> str:
    if value is None or value == "":
        return str(fallback if fallback not in (None, "") else "none")
    return str(value)


def _confidence_label(value: Any) -> str:
    if isinstance(value, int | float):
        return f"{float(value):.1f}"
    return _label(value, "none")


def _ratio(count: int, total: int) -> float:
    return count / total if total else 0.0


def _sorted_dict(counter: Counter[str]) -> dict[str, int]:
    return {key: counter[key] for key in sorted(counter)}


def _format_counter(values: dict[str, int]) -> str:
    if not values:
        return "-"
    return ", ".join(f"{key}={values[key]}" for key in sorted(values))
