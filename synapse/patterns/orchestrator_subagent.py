"""Orchestrator-subagent coordination pattern.

This pattern decomposes work across named subagents and lets an orchestrator
produce the final synthesis from their combined outputs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, cast

from synapse.patterns import register_pattern
from synapse.patterns.base import CoordinationPattern, PatternConfig, TaskResult


@dataclass
class OrchestratorConfig:
    profile: str
    name: str = ""
    role: str | None = None
    skill_set: str | None = None
    worktree: bool = False
    branch: str | None = None
    auto_approve: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OrchestratorConfig:
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
class SubtaskConfig:
    name: str
    message: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SubtaskConfig:
        return cls(
            name=str(data.get("name", "")),
            message=str(data.get("message", "")),
        )


@dataclass
class OrchestratorSubagentConfig(PatternConfig):
    orchestrator: OrchestratorConfig = field(
        default_factory=lambda: OrchestratorConfig(profile="")
    )
    subtasks: list[SubtaskConfig] = field(default_factory=list)
    parallel: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OrchestratorSubagentConfig:
        subtasks = data.get("subtasks")
        subtask_items = subtasks if isinstance(subtasks, list) else []
        return cls(
            name=str(data.get("name", "")),
            pattern=str(data.get("pattern", "")),
            description=str(data.get("description", "")),
            orchestrator=OrchestratorConfig.from_dict(
                data.get("orchestrator", {})
                if isinstance(data.get("orchestrator"), dict)
                else {}
            ),
            subtasks=[
                SubtaskConfig.from_dict(item)
                for item in subtask_items
                if isinstance(item, dict)
            ],
            parallel=bool(data.get("parallel", True)),
        )


@register_pattern
class OrchestratorSubagentPattern(CoordinationPattern):
    name = "orchestrator-subagent"
    description = "Delegate named subtasks to subagents and synthesize the results."
    config_class = OrchestratorSubagentConfig

    async def run(self, task: str, config: PatternConfig) -> TaskResult:
        config = cast(OrchestratorSubagentConfig, config)
        orchestrator = await self.spawn_agent(
            config.orchestrator.profile,
            name=config.orchestrator.name or None,
            role=config.orchestrator.role,
            skill_set=config.orchestrator.skill_set,
            worktree=config.orchestrator.worktree,
            branch=config.orchestrator.branch,
            auto_approve=config.orchestrator.auto_approve,
        )
        subagents = [
            await self.spawn_agent(
                config.orchestrator.profile,
                name=subtask.name or None,
                worktree=config.orchestrator.worktree,
                auto_approve=config.orchestrator.auto_approve,
            )
            for subtask in config.subtasks
        ]

        if config.parallel:
            parallel_prompt = self._parallel_prompt(task, config.subtasks)
            results = await self.send_all(
                subagents, parallel_prompt, response_mode="wait"
            )
        else:
            results = []
            for agent, subtask in zip(subagents, config.subtasks, strict=True):
                result = await self.send(
                    agent,
                    f"Task:\n{task}\n\nSubtask:\n{subtask.message}",
                    response_mode="wait",
                )
                results.append(result)

        combined_output = "\n".join(
            result.output for result in results if result.output
        )
        if self.should_stop:
            return TaskResult(status="stopped", output=combined_output)

        synthesis = await self.send(
            orchestrator,
            self._synthesis_prompt(task, results),
            response_mode="wait",
        )
        return TaskResult(
            status=synthesis.status,
            output=synthesis.output,
            error=synthesis.error,
            task_id=synthesis.task_id,
            artifacts=synthesis.artifacts,
        )

    def describe_plan(self, task: str, config: PatternConfig) -> list[str]:
        config = cast(OrchestratorSubagentConfig, config)
        lead = config.orchestrator
        mode = "parallel" if config.parallel else "sequential"
        lines = [
            f"Task: {task}",
            f"Spawn Orchestrator ({lead.name or 'unnamed'}) "
            f"profile={lead.profile or '?'}",
            f"Spawn {len(config.subtasks)} subagent(s) ({mode}):",
        ]
        for subtask in config.subtasks:
            lines.append(f"  - {subtask.name}: {subtask.message}")
        lines.append("Dispatch subtasks in " + mode + " and collect outputs")
        lines.append("Ask Orchestrator to synthesize a final response")
        return lines

    @staticmethod
    def _parallel_prompt(task: str, subtasks: list[SubtaskConfig]) -> str:
        subtask_lines = "\n".join(
            f"- {subtask.name}: {subtask.message}" for subtask in subtasks
        )
        return (
            f"Primary task:\n{task}\n\n"
            "You are one member of a subagent team. Complete the subtask matching your assigned name:\n"
            f"{subtask_lines}"
        )

    @staticmethod
    def _synthesis_prompt(task: str, results: list[TaskResult]) -> str:
        outputs = "\n".join(result.output for result in results if result.output)
        return f"Primary task:\n{task}\n\nSubagent outputs:\n{outputs}\n\nSynthesize a final response."
