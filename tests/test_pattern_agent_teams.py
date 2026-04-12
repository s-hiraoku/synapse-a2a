from __future__ import annotations

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


def test_agent_teams_config_from_dict_tolerates_unknown_keys() -> None:
    from synapse.patterns.agent_teams import AgentTeamsConfig

    config = AgentTeamsConfig.from_dict(
        {
            "name": "qa-swarm",
            **_PATTERN_TEMPLATES["agent-teams"],
            "unexpected": "ignored",
        }
    )

    assert config.name == "qa-swarm"
    assert config.pattern == "agent-teams"
    assert config.team.count == 3
    assert config.team.profile == "claude"
    assert config.task_queue.source == "inline"
    assert config.task_queue.tasks == ["Task 1", "Task 2", "Task 3"]
    assert config.completion.mode == "all-done"
    assert config.completion.timeout == 3600


@pytest.mark.asyncio
async def test_agent_teams_run_completes_all_done() -> None:
    from synapse.patterns.agent_teams import AgentTeamsConfig, AgentTeamsPattern

    pattern = AgentTeamsPattern(run_id="run-team")
    workers = [_handle("Worker-1", 9301), _handle("Worker-2", 9302)]
    pattern.spawn_agent = AsyncMock(side_effect=workers)
    pattern.send = AsyncMock(
        side_effect=[
            TaskResult(status="completed", output="done task 1"),
            TaskResult(status="completed", output="done task 2"),
            TaskResult(status="completed", output="done task 3"),
        ]
    )
    config = AgentTeamsConfig.from_dict(
        {
            **_PATTERN_TEMPLATES["agent-teams"],
            "team": {"count": 2, "profile": "claude", "worktree": True},
        }
    )

    result = await pattern.run("Process queue", config)

    assert result.status == "completed"
    assert result.output.splitlines() == ["done task 1", "done task 2", "done task 3"]
    assert pattern.send.await_count == 3


@pytest.mark.asyncio
async def test_agent_teams_rejects_non_inline_queue_sources() -> None:
    from synapse.patterns.agent_teams import AgentTeamsConfig, AgentTeamsPattern

    pattern = AgentTeamsPattern(run_id="run-team")

    with pytest.raises(PatternError, match="inline"):
        await pattern.run(
            "Process queue",
            AgentTeamsConfig.from_dict(
                {
                    **_PATTERN_TEMPLATES["agent-teams"],
                    "task_queue": {"source": "file", "tasks": []},
                }
            ),
        )


@pytest.mark.asyncio
async def test_agent_teams_honors_stop_during_processing() -> None:
    from synapse.patterns.agent_teams import AgentTeamsConfig, AgentTeamsPattern

    pattern = AgentTeamsPattern(run_id="run-team")
    worker = _handle("Worker-1", 9301)
    pattern.spawn_agent = AsyncMock(return_value=worker)

    async def send_side_effect(*args, **kwargs):
        pattern.request_stop()
        return TaskResult(status="completed", output="done task 1")

    pattern.send = AsyncMock(side_effect=send_side_effect)
    config = AgentTeamsConfig.from_dict(
        {
            **_PATTERN_TEMPLATES["agent-teams"],
            "team": {"count": 1, "profile": "claude", "worktree": True},
        }
    )

    result = await pattern.run("Process queue", config)

    assert result.status == "stopped"
    assert result.output == "done task 1"
    assert pattern.send.await_count == 1


def test_agent_teams_is_registered() -> None:
    from synapse.patterns.agent_teams import AgentTeamsPattern

    assert BUILTIN_PATTERNS["agent-teams"] is AgentTeamsPattern
