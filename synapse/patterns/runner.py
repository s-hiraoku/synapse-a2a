"""Pattern execution engine.

Manages pattern lifecycle: instantiation, execution, tracking, cleanup.
"""

from __future__ import annotations

import asyncio
import importlib
import importlib.util
import logging
import time
import uuid
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


@dataclass
class PatternRun:
    """Tracks a single pattern execution."""

    run_id: str
    pattern_name: str
    pattern_type: str
    task: str
    status: str = "running"
    started_at: float = field(default_factory=time.time)
    completed_at: float | None = None
    output: str = ""
    error: str = ""
    agents: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "pattern_name": self.pattern_name,
            "pattern_type": self.pattern_type,
            "task": self.task,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "output": self.output,
            "error": self.error,
            "agents": list(self.agents),
        }


class PatternRunner:
    """Manages pattern execution and in-memory run tracking."""

    _MAX_RUNS = 50

    def __init__(self) -> None:
        self._runs: OrderedDict[str, PatternRun] = OrderedDict()
        self._live_patterns: dict[str, Any] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}

    def describe_plan(
        self,
        pattern_type: str,
        task: str,
        config: dict | None = None,
    ) -> list[str]:
        """Return a side-effect-free execution preview for ``pattern_type``.

        Instantiates the pattern class, parses the config, and calls the
        pattern's ``describe_plan`` hook. No agents are spawned and no A2A
        traffic is generated.
        """
        pattern_cls = self._resolve_pattern_class(pattern_type)
        pattern = pattern_cls(run_id="")
        parsed_config = self._build_config(pattern, config)
        return list(pattern.describe_plan(task, parsed_config))

    async def run_pattern(
        self,
        pattern_type: str,
        task: str,
        config: dict | None = None,
        on_update: Callable[[], None] | None = None,
    ) -> str:
        """Start pattern execution and return a run ID immediately."""
        pattern_cls = self._resolve_pattern_class(pattern_type)
        run_id = uuid.uuid4().hex[:12]
        run = PatternRun(
            run_id=run_id,
            pattern_name=self._pattern_name(pattern_type, config),
            pattern_type=pattern_type,
            task=task,
        )
        self._runs[run_id] = run
        self._evict_old_runs(keep_id=run_id)

        pattern = pattern_cls(run_id=run_id)
        self._live_patterns[run_id] = pattern
        parsed_config = self._build_config(pattern, config)
        task_handle = asyncio.create_task(
            self._execute_pattern(run, pattern, task, parsed_config, on_update)
        )
        task_handle.add_done_callback(self._consume_task_exception)
        self._tasks[run_id] = task_handle
        return run_id

    async def _execute_pattern(
        self,
        run: PatternRun,
        pattern: Any,
        task: str,
        config: Any,
        on_update: Callable[[], None] | None,
    ) -> None:
        """Execute a pattern and guarantee cleanup and state updates."""
        try:
            result = await pattern.run(task, config)
            run.status = getattr(result, "status", "completed")
            run.output = getattr(result, "output", "")
            run.error = getattr(result, "error", "")
        except Exception as exc:
            run.status = "failed"
            run.error = str(exc)
        finally:
            agents = [self._agent_to_dict(agent) for agent in pattern._agents]
            try:
                await pattern.cleanup()
            finally:
                run.completed_at = time.time()
                run.agents = agents
                self._live_patterns.pop(run.run_id, None)
                self._tasks.pop(run.run_id, None)
                self._evict_old_runs()
                if on_update is not None:
                    on_update()

    def get_run(self, run_id: str) -> PatternRun | None:
        """Return a tracked run by ID."""
        return self._runs.get(run_id)

    def get_runs(self) -> list[PatternRun]:
        """Return runs ordered from newest to oldest."""
        return sorted(self._runs.values(), key=lambda run: run.started_at, reverse=True)

    async def stop_run(self, run_id: str) -> bool:
        """Request stop for an active run."""
        run = self._runs.get(run_id)
        pattern = self._live_patterns.get(run_id)
        if run is None or pattern is None or run.status != "running":
            return False
        pattern.request_stop()
        run.status = "stopped"
        return True

    def _evict_old_runs(self, keep_id: str | None = None) -> None:
        """Evict the oldest completed runs when over the cache cap."""
        while len(self._runs) > self._MAX_RUNS:
            victim = next(
                (
                    run_id
                    for run_id, run in self._runs.items()
                    if run_id != keep_id and run.status != "running"
                ),
                None,
            )
            if victim is None:
                logger.warning(
                    "Run cache at limit (%d) with all runs active", self._MAX_RUNS
                )
                break
            self._runs.pop(victim, None)
            self._live_patterns.pop(victim, None)
            self._tasks.pop(victim, None)

    @staticmethod
    def _consume_task_exception(task: asyncio.Task[None]) -> None:
        if task.cancelled():
            return
        try:
            task.result()
        except Exception:
            logger.exception("Pattern execution task failed")

    @staticmethod
    def _pattern_name(pattern_type: str, config: dict | None) -> str:
        if isinstance(config, dict):
            name = config.get("name")
            if isinstance(name, str) and name:
                return name
        return pattern_type

    @staticmethod
    def _build_config(pattern: Any, config: dict | None) -> Any:
        config_data = dict(config or {})
        config_class = getattr(pattern, "config_class", None)
        if config_class is None:
            config_class = PatternRunner._base_attr("PatternConfig")
        if hasattr(config_class, "from_dict"):
            return config_class.from_dict(config_data)
        if is_dataclass(config_class):
            field_names = {f.name for f in fields(config_class)}
            config_data = {k: v for k, v in config_data.items() if k in field_names}
        return config_class(**config_data)

    def _resolve_pattern_class(self, pattern_type: str) -> type[Any]:
        builtins = self._builtin_patterns()
        if pattern_type in builtins:
            return builtins[pattern_type]

        custom_class = self._load_custom_pattern_class(pattern_type)
        if custom_class is not None:
            return custom_class

        raise ValueError(f"Unknown pattern type: {pattern_type}")

    @staticmethod
    def _builtin_patterns() -> dict[str, type[Any]]:
        try:
            package = importlib.import_module("synapse.patterns")
        except ModuleNotFoundError:
            return {}
        return getattr(package, "BUILTIN_PATTERNS", {})

    @classmethod
    def _load_custom_pattern_class(cls, pattern_type: str) -> type[Any] | None:
        pattern_file = Path.cwd() / ".synapse" / "patterns" / f"{pattern_type}.py"
        if not pattern_file.is_file():
            return None

        spec = importlib.util.spec_from_file_location(
            f"synapse.patterns.custom_{pattern_type}", pattern_file
        )
        if spec is None or spec.loader is None:
            raise ValueError(f"Failed to load custom pattern: {pattern_type}")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        base_class = cls._base_attr("CoordinationPattern")
        explicit = getattr(module, "PATTERN_CLASS", None)
        if isinstance(explicit, type) and issubclass(explicit, base_class):
            return explicit

        for value in vars(module).values():
            if (
                isinstance(value, type)
                and issubclass(value, base_class)
                and value is not base_class
            ):
                return value
        raise ValueError(f"No CoordinationPattern subclass found in {pattern_file}")

    @staticmethod
    def _base_attr(name: str) -> Any:
        module = importlib.import_module("synapse.patterns.base")
        return getattr(module, name)

    @staticmethod
    def _agent_to_dict(agent: Any) -> dict:
        if isinstance(agent, dict):
            return dict(agent)
        if is_dataclass(agent) and not isinstance(agent, type):
            return asdict(agent)
        if hasattr(agent, "__dict__"):
            return dict(vars(agent))
        return {"value": repr(agent)}


# Module-level singleton so CLI commands and Canvas routes share state.
_runner: PatternRunner | None = None


def get_runner() -> PatternRunner:
    """Return the shared PatternRunner singleton."""
    global _runner  # noqa: PLW0603
    if _runner is None:
        _runner = PatternRunner()
    return _runner
