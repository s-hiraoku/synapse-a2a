"""Shared-state coordination pattern.

This v1 implementation only supports the project wiki as the shared store.
Other backends raise PatternError instead of silently falling back.
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
class SharedAgentConfig:
    profile: str
    name: str = ""
    role: str | None = None
    skill_set: str | None = None
    worktree: bool = False
    branch: str | None = None
    auto_approve: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SharedAgentConfig:
        return cls(
            profile=str(data.get("profile", "")),
            name=str(data.get("name", "")),
            role=data.get("role"),
            skill_set=data.get("skill_set"),
            worktree=bool(data.get("worktree", False)),
            branch=data.get("branch"),
            auto_approve=bool(data.get("auto_approve", True)),
        )


@dataclass
class TerminationConfig:
    mode: str = "time-budget"
    budget: float = 600

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TerminationConfig:
        return cls(
            mode=str(data.get("mode", "time-budget")),
            budget=float(data.get("budget", 600)),
        )


@dataclass
class SharedStateConfig(PatternConfig):
    agents: list[SharedAgentConfig] = field(default_factory=list)
    shared_store: str = "wiki"
    termination: TerminationConfig = field(default_factory=TerminationConfig)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SharedStateConfig:
        agents = data.get("agents")
        agent_items = agents if isinstance(agents, list) else []
        return cls(
            name=str(data.get("name", "")),
            pattern=str(data.get("pattern", "")),
            description=str(data.get("description", "")),
            agents=[
                SharedAgentConfig.from_dict(item)
                for item in agent_items
                if isinstance(item, dict)
            ],
            shared_store=str(data.get("shared_store", "wiki")),
            termination=TerminationConfig.from_dict(
                data.get("termination", {})
                if isinstance(data.get("termination"), dict)
                else {}
            ),
        )


@register_pattern
class SharedStatePattern(CoordinationPattern):
    name = "shared-state"
    description = (
        "Coordinate agents through shared wiki state and aggregate the result."
    )
    config_class = SharedStateConfig

    async def run(self, task: str, config: PatternConfig) -> TaskResult:
        config = cast(SharedStateConfig, config)
        if config.shared_store != "wiki":
            raise PatternError("shared-state v1 only supports shared_store='wiki'")

        agents = [
            await self.spawn_agent(
                agent.profile,
                name=agent.name or None,
                role=agent.role,
                skill_set=agent.skill_set,
                worktree=agent.worktree,
                branch=agent.branch,
                auto_approve=agent.auto_approve,
            )
            for agent in config.agents
        ]

        async def delegate(target: Any) -> TaskResult:
            key_name = target.name or target.agent_id
            message = (
                f"Task:\n{task}\n\nwrite findings to wiki key {self.run_id}-{key_name}"
            )
            return await self.send(target, message, response_mode="wait")

        sends = asyncio.gather(*(delegate(agent) for agent in agents))
        status = "completed"
        if config.termination.mode == "time-budget":
            try:
                await asyncio.wait_for(sends, timeout=config.termination.budget)
            except asyncio.TimeoutError:
                status = "stopped"
        else:
            await sends

        if self.should_stop:
            status = "stopped"

        aggregate = await self.wiki_query(task)
        return TaskResult(status=status, output=aggregate)
