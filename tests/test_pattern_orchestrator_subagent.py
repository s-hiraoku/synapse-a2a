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


def test_orchestrator_subagent_config_from_dict_tolerates_unknown_keys() -> None:
    from synapse.patterns.orchestrator_subagent import OrchestratorSubagentConfig

    config = OrchestratorSubagentConfig.from_dict(
        {
            "name": "ship-it",
            **_PATTERN_TEMPLATES["orchestrator-subagent"],
            "unexpected": "ignored",
        }
    )

    assert config.name == "ship-it"
    assert config.pattern == "orchestrator-subagent"
    assert config.orchestrator.profile == "claude"
    assert [subtask.name for subtask in config.subtasks] == ["subtask-1", "subtask-2"]
    assert [subtask.message for subtask in config.subtasks] == [
        "First subtask",
        "Second subtask",
    ]
    assert config.parallel is True


@pytest.mark.asyncio
async def test_orchestrator_subagent_run_completes_in_parallel() -> None:
    from synapse.patterns.orchestrator_subagent import (
        OrchestratorSubagentConfig,
        OrchestratorSubagentPattern,
    )

    pattern = OrchestratorSubagentPattern(run_id="run-orch")
    orchestrator = _handle("Lead", 9201)
    subagent_one = _handle("subtask-1", 9202)
    subagent_two = _handle("subtask-2", 9203)
    pattern.spawn_agent = AsyncMock(
        side_effect=[orchestrator, subagent_one, subagent_two]
    )
    pattern.send_all = AsyncMock(
        return_value=[
            TaskResult(status="completed", output="result one"),
            TaskResult(status="completed", output="result two"),
        ]
    )
    pattern.send = AsyncMock(
        return_value=TaskResult(status="completed", output="synthesized answer")
    )

    result = await pattern.run(
        "Plan the rollout",
        OrchestratorSubagentConfig.from_dict(
            _PATTERN_TEMPLATES["orchestrator-subagent"]
        ),
    )

    assert result.status == "completed"
    assert result.output == "synthesized answer"
    pattern.send_all.assert_awaited_once()
    synthesis_prompt = pattern.send.await_args.args[1]
    assert "Plan the rollout" in synthesis_prompt
    assert "result one" in synthesis_prompt
    assert "result two" in synthesis_prompt


@pytest.mark.asyncio
async def test_orchestrator_subagent_run_completes_sequentially() -> None:
    from synapse.patterns.orchestrator_subagent import (
        OrchestratorSubagentConfig,
        OrchestratorSubagentPattern,
    )

    pattern = OrchestratorSubagentPattern(run_id="run-orch")
    orchestrator = _handle("Lead", 9201)
    subagent_one = _handle("subtask-1", 9202)
    subagent_two = _handle("subtask-2", 9203)
    pattern.spawn_agent = AsyncMock(
        side_effect=[orchestrator, subagent_one, subagent_two]
    )
    pattern.send = AsyncMock(
        side_effect=[
            TaskResult(status="completed", output="result one"),
            TaskResult(status="completed", output="result two"),
            TaskResult(status="completed", output="synthesized answer"),
        ]
    )

    result = await pattern.run(
        "Plan the rollout",
        OrchestratorSubagentConfig.from_dict(
            {**_PATTERN_TEMPLATES["orchestrator-subagent"], "parallel": False}
        ),
    )

    assert result.status == "completed"
    assert result.output == "synthesized answer"
    assert pattern.send.await_count == 3


@pytest.mark.asyncio
async def test_orchestrator_subagent_honors_stop_before_synthesis() -> None:
    from synapse.patterns.orchestrator_subagent import (
        OrchestratorSubagentConfig,
        OrchestratorSubagentPattern,
    )

    pattern = OrchestratorSubagentPattern(run_id="run-orch")
    orchestrator = _handle("Lead", 9201)
    subagent_one = _handle("subtask-1", 9202)
    subagent_two = _handle("subtask-2", 9203)
    pattern.spawn_agent = AsyncMock(
        side_effect=[orchestrator, subagent_one, subagent_two]
    )

    async def send_side_effect(*args, **kwargs):
        if pattern.send.await_count == 1:
            return TaskResult(status="completed", output="result one")
        pattern.request_stop()
        return TaskResult(status="completed", output="result two")

    pattern.send = AsyncMock(side_effect=send_side_effect)

    result = await pattern.run(
        "Plan the rollout",
        OrchestratorSubagentConfig.from_dict(
            {**_PATTERN_TEMPLATES["orchestrator-subagent"], "parallel": False}
        ),
    )

    assert result.status == "stopped"
    assert "result one" in result.output
    assert "result two" in result.output


def test_orchestrator_subagent_is_registered() -> None:
    from synapse.patterns.orchestrator_subagent import OrchestratorSubagentPattern

    assert BUILTIN_PATTERNS["orchestrator-subagent"] is OrchestratorSubagentPattern
