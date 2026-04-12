from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from synapse.commands.multiagent import _PATTERN_TEMPLATES
from synapse.patterns import BUILTIN_PATTERNS, AgentHandle, TaskResult


def _handle(name: str, port: int) -> AgentHandle:
    return AgentHandle(
        agent_id=f"synapse-codex-{port}",
        profile="codex",
        port=port,
        endpoint=f"http://localhost:{port}",
        name=name,
    )


def test_generator_verifier_config_from_dict_tolerates_unknown_keys() -> None:
    from synapse.patterns.generator_verifier import GeneratorVerifierConfig

    config = GeneratorVerifierConfig.from_dict(
        {
            "name": "quality-loop",
            **_PATTERN_TEMPLATES["generator-verifier"],
            "unexpected": "ignored",
        }
    )

    assert config.name == "quality-loop"
    assert config.pattern == "generator-verifier"
    assert config.generator.profile == "claude"
    assert config.generator.worktree is True
    assert config.verifier.name == "Verifier"
    assert config.verifier.criteria == [{"command": "pytest", "expect": "exit-0"}]
    assert config.max_iterations == 3
    assert config.on_failure == "escalate"


@pytest.mark.asyncio
async def test_generator_verifier_run_completes_after_pass() -> None:
    from synapse.patterns.generator_verifier import (
        GeneratorVerifierConfig,
        GeneratorVerifierPattern,
    )

    pattern = GeneratorVerifierPattern(run_id="run-gv")
    generator = _handle("Generator", 9101)
    verifier = _handle("Verifier", 9102)
    pattern.spawn_agent = AsyncMock(side_effect=[generator, verifier])
    pattern.send = AsyncMock(
        side_effect=[
            TaskResult(status="completed", output="draft v1"),
            TaskResult(status="completed", output="PASS: matches criteria"),
        ]
    )

    result = await pattern.run(
        "Write a release summary",
        GeneratorVerifierConfig.from_dict(_PATTERN_TEMPLATES["generator-verifier"]),
    )

    assert result.status == "completed"
    assert result.output == "draft v1"
    assert result.error == ""
    assert pattern.send.await_count == 2
    generator_prompt = pattern.send.await_args_list[0].args[1]
    verifier_prompt = pattern.send.await_args_list[1].args[1]
    assert "Write a release summary" in generator_prompt
    assert "draft v1" in verifier_prompt
    assert "pytest" in verifier_prompt


@pytest.mark.asyncio
async def test_generator_verifier_run_fails_after_iteration_exhaustion() -> None:
    from synapse.patterns.generator_verifier import (
        GeneratorVerifierConfig,
        GeneratorVerifierPattern,
    )

    pattern = GeneratorVerifierPattern(run_id="run-gv")
    generator = _handle("Generator", 9101)
    verifier = _handle("Verifier", 9102)
    pattern.spawn_agent = AsyncMock(side_effect=[generator, verifier])
    pattern.send = AsyncMock(
        side_effect=[
            TaskResult(status="completed", output="draft v1"),
            TaskResult(status="completed", output="Needs more detail"),
            TaskResult(status="completed", output="draft v2"),
            TaskResult(status="completed", output="Still missing PASS"),
            TaskResult(status="completed", output="draft v3"),
            TaskResult(status="completed", output="No PASS marker yet"),
        ]
    )
    config = GeneratorVerifierConfig.from_dict(
        {
            **_PATTERN_TEMPLATES["generator-verifier"],
            "max_iterations": 3,
            "on_failure": "escalate",
        }
    )

    result = await pattern.run("Produce an answer", config)

    assert result.status == "failed"
    assert result.output == "draft v3"
    assert "No PASS marker yet" in result.error


@pytest.mark.asyncio
async def test_generator_verifier_honors_stop_between_iterations() -> None:
    from synapse.patterns.generator_verifier import (
        GeneratorVerifierConfig,
        GeneratorVerifierPattern,
    )

    pattern = GeneratorVerifierPattern(run_id="run-gv")
    generator = _handle("Generator", 9101)
    verifier = _handle("Verifier", 9102)
    pattern.spawn_agent = AsyncMock(side_effect=[generator, verifier])

    async def send_side_effect(*args, **kwargs):
        call_index = pattern.send.await_count
        if call_index == 1:
            return TaskResult(status="completed", output="draft v1")
        pattern.request_stop()
        return TaskResult(status="completed", output="Needs another pass")

    pattern.send = AsyncMock(side_effect=send_side_effect)

    result = await pattern.run(
        "Write a release summary",
        GeneratorVerifierConfig.from_dict(_PATTERN_TEMPLATES["generator-verifier"]),
    )

    assert result.status == "stopped"
    assert result.output == "draft v1"


def test_generator_verifier_is_registered() -> None:
    from synapse.patterns.generator_verifier import GeneratorVerifierPattern

    assert BUILTIN_PATTERNS["generator-verifier"] is GeneratorVerifierPattern


def test_builtin_patterns_smoke() -> None:
    import synapse.patterns as patterns

    assert sorted(patterns.BUILTIN_PATTERNS.keys()) == [
        "agent-teams",
        "generator-verifier",
        "message-bus",
        "orchestrator-subagent",
        "shared-state",
    ]
