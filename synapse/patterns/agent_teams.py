"""Agent-teams coordination pattern.

This v1 implementation only supports inline task queues. Other queue sources
raise PatternError instead of silently falling back.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, cast

from synapse.patterns import register_pattern
from synapse.patterns.base import (
    CoordinationPattern,
    PatternConfig,
    PatternError,
    TaskResult,
)


@dataclass
class TeamConfig:
    count: int
    profile: str
    name: str = "Worker"
    role: str | None = None
    skill_set: str | None = None
    worktree: bool = False
    branch: str | None = None
    auto_approve: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TeamConfig:
        return cls(
            count=int(data.get("count", 1)),
            profile=str(data.get("profile", "")),
            name=str(data.get("name", "Worker")),
            role=data.get("role"),
            skill_set=data.get("skill_set"),
            worktree=bool(data.get("worktree", False)),
            branch=data.get("branch"),
            auto_approve=bool(data.get("auto_approve", True)),
        )


@dataclass
class TaskQueueConfig:
    source: str = "inline"
    tasks: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskQueueConfig:
        tasks = data.get("tasks")
        return cls(
            source=str(data.get("source", "inline")),
            tasks=[str(item) for item in tasks] if isinstance(tasks, list) else [],
        )


@dataclass
class CompletionConfig:
    mode: str = "all-done"
    timeout: float = 3600

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CompletionConfig:
        return cls(
            mode=str(data.get("mode", "all-done")),
            timeout=float(data.get("timeout", 3600)),
        )


@dataclass
class AgentTeamsConfig(PatternConfig):
    team: TeamConfig = field(default_factory=lambda: TeamConfig(count=1, profile=""))
    task_queue: TaskQueueConfig = field(default_factory=TaskQueueConfig)
    completion: CompletionConfig = field(default_factory=CompletionConfig)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentTeamsConfig:
        return cls(
            name=str(data.get("name", "")),
            pattern=str(data.get("pattern", "")),
            description=str(data.get("description", "")),
            team=TeamConfig.from_dict(
                data.get("team", {}) if isinstance(data.get("team"), dict) else {}
            ),
            task_queue=TaskQueueConfig.from_dict(
                data.get("task_queue", {})
                if isinstance(data.get("task_queue"), dict)
                else {}
            ),
            completion=CompletionConfig.from_dict(
                data.get("completion", {})
                if isinstance(data.get("completion"), dict)
                else {}
            ),
        )


@register_pattern
class AgentTeamsPattern(CoordinationPattern):
    name = "agent-teams"
    description = "Run a queue of inline tasks across a configurable worker team."
    config_class = AgentTeamsConfig

    async def run(self, task: str, config: PatternConfig) -> TaskResult:
        config = cast(AgentTeamsConfig, config)
        if config.task_queue.source != "inline":
            raise PatternError(
                "agent-teams v1 only supports task_queue.source='inline'"
            )

        workers = [
            await self.spawn_agent(
                config.team.profile,
                name=f"{config.team.name}-{index}",
                role=config.team.role,
                skill_set=config.team.skill_set,
                worktree=config.team.worktree,
                branch=config.team.branch,
                auto_approve=config.team.auto_approve,
            )
            for index in range(1, max(config.team.count, 1) + 1)
        ]

        queue: asyncio.Queue[tuple[int, str]] = asyncio.Queue()
        for index, item in enumerate(config.task_queue.tasks):
            await queue.put((index, item))

        outputs: list[str] = [""] * len(config.task_queue.tasks)
        stop_status = "completed"

        def drain_queue() -> None:
            while True:
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    return
                else:
                    queue.task_done()

        async def worker_loop(worker: Any) -> None:
            nonlocal stop_status
            while not self.should_stop:
                try:
                    index, item = queue.get_nowait()
                except asyncio.QueueEmpty:
                    return
                try:
                    result = await self.send(
                        worker,
                        f"Primary task:\n{task}\n\nQueue item:\n{item}",
                        response_mode="wait",
                    )
                    outputs[index] = result.output
                    if self.should_stop:
                        stop_status = "stopped"
                        drain_queue()
                finally:
                    queue.task_done()

        tasks = [asyncio.create_task(worker_loop(worker)) for worker in workers]
        try:
            if config.completion.mode == "time-budget":
                try:
                    await asyncio.wait_for(
                        queue.join(), timeout=config.completion.timeout
                    )
                except asyncio.TimeoutError:
                    stop_status = "stopped"
            else:
                await queue.join()
        finally:
            for task_handle in tasks:
                task_handle.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

        if self.should_stop:
            stop_status = "stopped"

        completed_outputs = [output for output in outputs if output]
        return TaskResult(status=stop_status, output="\n".join(completed_outputs))
