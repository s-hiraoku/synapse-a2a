"""Tests for the pattern execution runner."""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

import pytest


@dataclass
class _DummyTaskResult:
    status: str = "completed"
    output: str = ""
    error: str = ""


class _DummyPatternConfig:
    def __init__(self, **kwargs) -> None:
        self.values = dict(kwargs)


class _DummyPattern:
    config_class = _DummyPatternConfig

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self._agents = []
        self.stop_requested = False

    async def run(self, task: str, config: _DummyPatternConfig) -> _DummyTaskResult:
        return _DummyTaskResult(output=f"{task}:{config.values.get('suffix', '')}")

    async def cleanup(self) -> None:
        return None

    def request_stop(self) -> None:
        self.stop_requested = True


@pytest.fixture()
def runner_module(monkeypatch: pytest.MonkeyPatch):
    """Import the runner with stubbed base and registry modules."""
    base_module = ModuleType("synapse.patterns.base")
    base_module.CoordinationPattern = _DummyPattern
    base_module.PatternConfig = _DummyPatternConfig
    base_module.TaskResult = _DummyTaskResult

    package_module = ModuleType("synapse.patterns")
    package_module.BUILTIN_PATTERNS = {"dummy": _DummyPattern}
    package_module.__path__ = [
        str(Path(__file__).resolve().parents[1] / "synapse" / "patterns")
    ]

    monkeypatch.setitem(sys.modules, "synapse.patterns", package_module)
    monkeypatch.setitem(sys.modules, "synapse.patterns.base", base_module)
    sys.modules.pop("synapse.patterns.runner", None)

    import importlib

    module = importlib.import_module("synapse.patterns.runner")
    yield module
    sys.modules.pop("synapse.patterns.runner", None)


@pytest.mark.asyncio
async def test_run_pattern_returns_run_id(runner_module) -> None:
    """run_pattern() should return a run ID immediately."""
    runner = runner_module.PatternRunner()

    run_id = await runner.run_pattern("dummy", "test task")

    assert isinstance(run_id, str)
    assert len(run_id) == 12


@pytest.mark.asyncio
async def test_run_pattern_creates_run(runner_module, monkeypatch) -> None:
    """run_pattern() should add a running PatternRun to the cache."""
    runner = runner_module.PatternRunner()
    gate = asyncio.Event()

    async def blocked_execute(*args, **kwargs):
        await gate.wait()

    monkeypatch.setattr(runner, "_execute_pattern", blocked_execute)

    run_id = await runner.run_pattern("dummy", "queued task")

    run = runner.get_run(run_id)
    assert run is not None
    assert run.status == "running"
    assert run.task == "queued task"
    gate.set()


@pytest.mark.asyncio
async def test_run_pattern_unknown_type(runner_module) -> None:
    """Unknown pattern types should raise ValueError."""
    runner = runner_module.PatternRunner()

    with pytest.raises(ValueError, match="Unknown pattern type"):
        await runner.run_pattern("missing", "test task")


@pytest.mark.asyncio
async def test_execute_pattern_success(runner_module) -> None:
    """Successful runs should capture status and output."""
    runner = runner_module.PatternRunner()
    run = runner_module.PatternRun(
        run_id="run123",
        pattern_name="named pattern",
        pattern_type="dummy",
        task="demo",
    )
    pattern = _DummyPattern(run.run_id)
    config = _DummyPatternConfig(suffix="ok")
    updates: list[str] = []

    await runner._execute_pattern(
        run, pattern, "demo", config, lambda: updates.append("u")
    )

    assert run.status == "completed"
    assert run.output == "demo:ok"
    assert run.error == ""
    assert run.completed_at is not None
    assert updates == ["u"]


@pytest.mark.asyncio
async def test_execute_pattern_failure(runner_module) -> None:
    """Exceptions from pattern.run() should mark the run as failed."""
    runner = runner_module.PatternRunner()
    run = runner_module.PatternRun(
        run_id="run123",
        pattern_name="named pattern",
        pattern_type="dummy",
        task="demo",
    )

    class BrokenPattern(_DummyPattern):
        async def run(self, task: str, config: _DummyPatternConfig) -> _DummyTaskResult:
            raise RuntimeError("boom")

    pattern = BrokenPattern(run.run_id)

    await runner._execute_pattern(run, pattern, "demo", _DummyPatternConfig(), None)

    assert run.status == "failed"
    assert run.error == "boom"
    assert run.completed_at is not None


@pytest.mark.asyncio
async def test_execute_pattern_cleanup_always_called(runner_module) -> None:
    """cleanup() should run even when execution fails."""
    runner = runner_module.PatternRunner()
    run = runner_module.PatternRun(
        run_id="run123",
        pattern_name="named pattern",
        pattern_type="dummy",
        task="demo",
    )
    calls: list[str] = []

    class CleanupPattern(_DummyPattern):
        async def run(self, task: str, config: _DummyPatternConfig) -> _DummyTaskResult:
            raise RuntimeError("boom")

        async def cleanup(self) -> None:
            calls.append("cleanup")

    await runner._execute_pattern(
        run, CleanupPattern(run.run_id), "demo", _DummyPatternConfig(), None
    )

    assert calls == ["cleanup"]


@pytest.mark.asyncio
async def test_get_run(runner_module) -> None:
    """get_run() should return a previously created run."""
    runner = runner_module.PatternRunner()

    run_id = await runner.run_pattern("dummy", "lookup")
    await asyncio.sleep(0)

    run = runner.get_run(run_id)

    assert run is not None
    assert run.run_id == run_id


def test_get_runs_most_recent_first(runner_module) -> None:
    """get_runs() should return the newest runs first."""
    runner = runner_module.PatternRunner()
    older = runner_module.PatternRun(
        run_id="older",
        pattern_name="p1",
        pattern_type="dummy",
        task="one",
        started_at=1.0,
    )
    newer = runner_module.PatternRun(
        run_id="newer",
        pattern_name="p2",
        pattern_type="dummy",
        task="two",
        started_at=2.0,
    )
    runner._runs["older"] = older
    runner._runs["newer"] = newer

    runs = runner.get_runs()

    assert [run.run_id for run in runs] == ["newer", "older"]


@pytest.mark.asyncio
async def test_stop_run(runner_module) -> None:
    """stop_run() should request stop on the active pattern instance."""
    runner = runner_module.PatternRunner()
    run = runner_module.PatternRun(
        run_id="run123",
        pattern_name="named pattern",
        pattern_type="dummy",
        task="demo",
    )
    pattern = _DummyPattern(run.run_id)
    runner._runs[run.run_id] = run
    runner._live_patterns[run.run_id] = pattern

    stopped = await runner.stop_run(run.run_id)

    assert stopped is True
    assert pattern.stop_requested is True
    assert run.status == "stopped"


def test_evict_old_runs(runner_module) -> None:
    """Old completed runs should be evicted when the cache exceeds the cap."""
    runner = runner_module.PatternRunner()
    runner._MAX_RUNS = 3
    statuses = ["completed", "running", "failed", "completed"]

    for index, status in enumerate(statuses):
        run = runner_module.PatternRun(
            run_id=f"run-{index}",
            pattern_name="p",
            pattern_type="dummy",
            task="demo",
            status=status,
            started_at=float(index),
        )
        runner._runs[run.run_id] = run

    runner._evict_old_runs()

    assert list(runner._runs) == ["run-1", "run-2", "run-3"]
