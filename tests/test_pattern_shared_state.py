from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from synapse.commands.multiagent import _PATTERN_TEMPLATES
from synapse.patterns import BUILTIN_PATTERNS, AgentHandle, PatternError, TaskResult


def _handle(name: str, port: int) -> AgentHandle:
    return AgentHandle(
        agent_id=f"synapse-codex-{port}",
        profile="codex",
        port=port,
        endpoint=f"http://localhost:{port}",
        name=name,
    )


def test_shared_state_config_from_dict_tolerates_unknown_keys() -> None:
    from synapse.patterns.shared_state import SharedStateConfig

    config = SharedStateConfig.from_dict(
        {
            "name": "research-grid",
            **_PATTERN_TEMPLATES["shared-state"],
            "unexpected": "ignored",
        }
    )

    assert config.name == "research-grid"
    assert config.pattern == "shared-state"
    assert [agent.name for agent in config.agents] == ["Researcher-1", "Researcher-2"]
    assert config.shared_store == "wiki"
    assert config.termination.mode == "time-budget"
    assert config.termination.budget == 600


@pytest.mark.asyncio
async def test_shared_state_run_queries_wiki_after_agents_finish() -> None:
    from synapse.patterns.shared_state import SharedStateConfig, SharedStatePattern

    pattern = SharedStatePattern(run_id="run-state")
    agent_one = _handle("Researcher-1", 9501)
    agent_two = _handle("Researcher-2", 9502)
    pattern.spawn_agent = AsyncMock(side_effect=[agent_one, agent_two])
    pattern.send = AsyncMock(
        side_effect=[
            TaskResult(status="completed", output="finding one"),
            TaskResult(status="completed", output="finding two"),
        ]
    )
    pattern.wiki_query = AsyncMock(return_value="combined finding")

    result = await pattern.run(
        "Investigate issue 541",
        SharedStateConfig.from_dict(_PATTERN_TEMPLATES["shared-state"]),
    )

    assert result.status == "completed"
    assert result.output == "combined finding"
    assert pattern.send.await_count == 2
    first_prompt = pattern.send.await_args_list[0].args[1]
    assert "write findings to wiki key run-state-Researcher-1" in first_prompt
    pattern.wiki_query.assert_awaited_once_with("Investigate issue 541")


@pytest.mark.asyncio
async def test_shared_state_rejects_non_wiki_shared_store() -> None:
    from synapse.patterns.shared_state import SharedStateConfig, SharedStatePattern

    pattern = SharedStatePattern(run_id="run-state")

    with pytest.raises(PatternError, match="wiki"):
        await pattern.run(
            "Investigate issue 541",
            SharedStateConfig.from_dict(
                {**_PATTERN_TEMPLATES["shared-state"], "shared_store": "memory"}
            ),
        )


@pytest.mark.asyncio
async def test_shared_state_honors_time_budget() -> None:
    from synapse.patterns.shared_state import SharedStateConfig, SharedStatePattern

    pattern = SharedStatePattern(run_id="run-state")
    agent_one = _handle("Researcher-1", 9501)
    agent_two = _handle("Researcher-2", 9502)
    pattern.spawn_agent = AsyncMock(side_effect=[agent_one, agent_two])

    async def slow_send(*args, **kwargs):
        await asyncio.sleep(0.01)
        return TaskResult(status="completed", output="late finding")

    pattern.send = AsyncMock(side_effect=slow_send)
    pattern.wiki_query = AsyncMock(return_value="partial aggregate")

    result = await pattern.run(
        "Investigate issue 541",
        SharedStateConfig.from_dict(
            {
                **_PATTERN_TEMPLATES["shared-state"],
                "termination": {"mode": "time-budget", "budget": 0.001},
            }
        ),
    )

    assert result.status == "stopped"
    assert result.output == "partial aggregate"


def test_shared_state_is_registered() -> None:
    from synapse.patterns.shared_state import SharedStatePattern

    assert BUILTIN_PATTERNS["shared-state"] is SharedStatePattern
