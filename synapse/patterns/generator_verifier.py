"""Generator-verifier coordination pattern.

This v1 implementation treats verifier criteria strictly as text included in the
verification prompt. It does not execute shell commands or external checks.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, cast

from synapse.patterns import register_pattern
from synapse.patterns.base import CoordinationPattern, PatternConfig, TaskResult


@dataclass
class GeneratorConfig:
    profile: str
    name: str = ""
    role: str | None = None
    skill_set: str | None = None
    worktree: bool = False
    branch: str | None = None
    auto_approve: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GeneratorConfig:
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
class VerifierConfig(GeneratorConfig):
    criteria: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VerifierConfig:
        base = GeneratorConfig.from_dict(data)
        criteria = data.get("criteria")
        return cls(
            profile=base.profile,
            name=base.name,
            role=base.role,
            skill_set=base.skill_set,
            worktree=base.worktree,
            branch=base.branch,
            auto_approve=base.auto_approve,
            criteria=list(criteria) if isinstance(criteria, list) else [],
        )


@dataclass
class GeneratorVerifierConfig(PatternConfig):
    generator: GeneratorConfig = field(
        default_factory=lambda: GeneratorConfig(profile="")
    )
    verifier: VerifierConfig = field(default_factory=lambda: VerifierConfig(profile=""))
    max_iterations: int = 1
    on_failure: str = "escalate"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GeneratorVerifierConfig:
        return cls(
            name=str(data.get("name", "")),
            pattern=str(data.get("pattern", "")),
            description=str(data.get("description", "")),
            generator=GeneratorConfig.from_dict(
                data.get("generator", {})
                if isinstance(data.get("generator"), dict)
                else {}
            ),
            verifier=VerifierConfig.from_dict(
                data.get("verifier", {})
                if isinstance(data.get("verifier"), dict)
                else {}
            ),
            max_iterations=int(data.get("max_iterations", 1)),
            on_failure=str(data.get("on_failure", "escalate")),
        )


@register_pattern
class GeneratorVerifierPattern(CoordinationPattern):
    name = "generator-verifier"
    description = "Generate output, verify it against textual criteria, and iterate."
    config_class = GeneratorVerifierConfig

    async def run(self, task: str, config: PatternConfig) -> TaskResult:
        config = cast(GeneratorVerifierConfig, config)
        generator = await self.spawn_agent(
            config.generator.profile,
            name=config.generator.name or None,
            role=config.generator.role,
            skill_set=config.generator.skill_set,
            worktree=config.generator.worktree,
            branch=config.generator.branch,
            auto_approve=config.generator.auto_approve,
        )
        verifier = await self.spawn_agent(
            config.verifier.profile,
            name=config.verifier.name or None,
            role=config.verifier.role,
            skill_set=config.verifier.skill_set,
            worktree=config.verifier.worktree,
            branch=config.verifier.branch,
            auto_approve=config.verifier.auto_approve,
        )

        latest_output = ""
        latest_feedback = ""

        for iteration in range(1, max(config.max_iterations, 1) + 1):
            if self.should_stop:
                return TaskResult(
                    status="stopped", output=latest_output, error=latest_feedback
                )

            generator_prompt = self._generator_prompt(task, iteration, latest_feedback)
            generated = await self.send(
                generator, generator_prompt, response_mode="wait"
            )
            latest_output = generated.output

            verifier_prompt = self._verifier_prompt(
                task, latest_output, config.verifier.criteria
            )
            verified = await self.send(verifier, verifier_prompt, response_mode="wait")
            latest_feedback = verified.output or verified.error

            if re.search(r"(?m)^\s*PASS\b", verified.output):
                return TaskResult(status="completed", output=latest_output)

            if self.should_stop:
                return TaskResult(
                    status="stopped", output=latest_output, error=latest_feedback
                )

        if config.on_failure == "accept":
            return TaskResult(
                status="completed", output=latest_output, error=latest_feedback
            )
        return TaskResult(status="failed", output=latest_output, error=latest_feedback)

    @staticmethod
    def _generator_prompt(task: str, iteration: int, feedback: str) -> str:
        prompt = f"Task:\n{task}\n\nIteration: {iteration}"
        if feedback:
            prompt += f"\n\nVerifier feedback to address:\n{feedback}"
        return prompt

    @staticmethod
    def _verifier_prompt(task: str, output: str, criteria: list[dict[str, Any]]) -> str:
        return (
            f"Task:\n{task}\n\nGenerated output:\n{output}\n\n"
            f"Criteria (text only; do not execute):\n{criteria}\n\n"
            "Reply with PASS if the output satisfies the criteria. Otherwise explain what to fix."
        )
