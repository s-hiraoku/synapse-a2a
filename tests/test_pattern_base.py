from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from synapse.a2a_client import A2ATask


def test_agent_handle_creation():
    from synapse.patterns import AgentHandle

    handle = AgentHandle(
        agent_id="synapse-codex-9999",
        profile="codex",
        port=9999,
        endpoint="http://localhost:9999",
        name="PatternBase",
        role="tester",
        worktree_path="/tmp/pattern-base",
        worktree_branch="feature/pattern-base",
    )

    assert handle.agent_id == "synapse-codex-9999"
    assert handle.profile == "codex"
    assert handle.port == 9999
    assert handle.endpoint == "http://localhost:9999"
    assert handle.name == "PatternBase"
    assert handle.role == "tester"
    assert handle.worktree_path == "/tmp/pattern-base"
    assert handle.worktree_branch == "feature/pattern-base"


def test_task_result_defaults():
    from synapse.patterns import TaskResult

    result = TaskResult(status="completed")

    assert result.status == "completed"
    assert result.output == ""
    assert result.error == ""
    assert result.task_id == ""
    assert result.artifacts == []


def test_pattern_config_defaults():
    from synapse.patterns import PatternConfig

    config = PatternConfig()

    assert config.name == ""
    assert config.pattern == ""
    assert config.description == ""


def test_pattern_error():
    from synapse.patterns import PatternError

    assert issubclass(PatternError, ValueError)


def test_coordination_pattern_cannot_instantiate():
    from synapse.patterns import CoordinationPattern

    with pytest.raises(TypeError):
        CoordinationPattern()


def test_coordination_pattern_concrete_subclass():
    from synapse.patterns import CoordinationPattern, PatternConfig, TaskResult

    class DemoPattern(CoordinationPattern):
        name = "demo"
        description = "Demo pattern"

        async def run(self, task: str, config: PatternConfig) -> TaskResult:
            return TaskResult(status="completed", output=task + config.name)

    pattern = DemoPattern()

    assert pattern.name == "demo"
    assert pattern.description == "Demo pattern"
    assert pattern.should_stop is False
    assert pattern._agents == []


def test_register_pattern():
    import synapse.patterns as patterns
    from synapse.patterns import CoordinationPattern, PatternConfig, register_pattern

    existing = dict(patterns.BUILTIN_PATTERNS)

    try:

        @register_pattern
        class DemoPattern(CoordinationPattern):
            name = "demo-register"
            description = "Registered test pattern"

            async def run(self, task: str, config: PatternConfig):
                return None

        assert patterns.BUILTIN_PATTERNS["demo-register"] is DemoPattern
    finally:
        patterns.BUILTIN_PATTERNS.clear()
        patterns.BUILTIN_PATTERNS.update(existing)


@pytest.mark.asyncio
async def test_spawn_agent_builds_handle(monkeypatch):
    from synapse.patterns import CoordinationPattern, PatternConfig, TaskResult

    class DemoPattern(CoordinationPattern):
        name = "demo"
        description = "Demo pattern"

        async def run(self, task: str, config: PatternConfig) -> TaskResult:
            return TaskResult(status="completed")

    pattern = DemoPattern()
    prepared = SimpleNamespace()
    spawn_result = SimpleNamespace(
        agent_id="synapse-codex-8126",
        port=8126,
        status="submitted",
        worktree_path="/tmp/pattern-base",
        worktree_branch="feature/pattern-base",
    )
    registry_data = {
        "endpoint": "http://localhost:8126",
        "name": "PatternBase",
        "role": "builder",
        "worktree_path": "/tmp/pattern-base",
        "worktree_branch": "feature/pattern-base",
    }

    fake_spawn = SimpleNamespace(
        prepare_spawn=MagicMock(return_value=prepared),
        execute_spawn=MagicMock(return_value=[spawn_result]),
        wait_for_agent=MagicMock(return_value=True),
    )
    fake_registry = MagicMock()
    fake_registry.resolve_agent.return_value = registry_data

    monkeypatch.setattr(
        "asyncio.to_thread", AsyncMock(side_effect=lambda fn, *a, **k: fn(*a, **k))
    )
    monkeypatch.setattr(
        "synapse.patterns.base.AgentRegistry", MagicMock(return_value=fake_registry)
    )
    monkeypatch.setattr("synapse.patterns.base._spawn_module", lambda: fake_spawn)

    handle = await pattern.spawn_agent(
        "codex",
        name="PatternBase",
        role="builder",
        skill_set="developer",
        worktree=True,
    )

    fake_spawn.prepare_spawn.assert_called_once_with(
        profile="codex",
        name="PatternBase",
        role="builder",
        skill_set="developer",
        worktree=True,
        branch=None,
        auto_approve=True,
    )
    fake_spawn.execute_spawn.assert_called_once_with([prepared])
    fake_spawn.wait_for_agent.assert_called_once_with("synapse-codex-8126")
    fake_registry.resolve_agent.assert_called_once_with("synapse-codex-8126")
    assert handle.agent_id == "synapse-codex-8126"
    assert handle.profile == "codex"
    assert handle.endpoint == "http://localhost:8126"
    assert handle.name == "PatternBase"
    assert handle.role == "builder"
    assert handle.worktree_path == "/tmp/pattern-base"
    assert handle.worktree_branch == "feature/pattern-base"
    assert pattern._agents == [handle]


@pytest.mark.asyncio
async def test_spawn_agents_calls_spawn_agent(monkeypatch):
    from synapse.patterns import (
        AgentHandle,
        CoordinationPattern,
        PatternConfig,
        TaskResult,
    )

    class DemoPattern(CoordinationPattern):
        name = "demo"
        description = "Demo pattern"

        async def run(self, task: str, config: PatternConfig) -> TaskResult:
            return TaskResult(status="completed")

    pattern = DemoPattern()
    handles = [
        AgentHandle(
            agent_id=f"synapse-codex-81{i}",
            profile="codex",
            port=8100 + i,
            endpoint=f"http://localhost:{8100 + i}",
        )
        for i in range(2)
    ]
    spawn_agent = AsyncMock(side_effect=handles)
    monkeypatch.setattr(pattern, "spawn_agent", spawn_agent)

    result = await pattern.spawn_agents(2, "codex", name="Worker")

    assert result == handles
    assert spawn_agent.await_count == 2


@pytest.mark.asyncio
async def test_stop_agent_calls_kill(monkeypatch):
    from synapse.patterns import (
        AgentHandle,
        CoordinationPattern,
        PatternConfig,
        TaskResult,
    )

    class DemoPattern(CoordinationPattern):
        name = "demo"
        description = "Demo pattern"

        async def run(self, task: str, config: PatternConfig) -> TaskResult:
            return TaskResult(status="completed")

    pattern = DemoPattern()
    handle = AgentHandle(
        agent_id="synapse-codex-8126",
        profile="codex",
        port=8126,
        endpoint="http://localhost:8126",
    )
    subprocess_run = MagicMock()

    monkeypatch.setattr(
        "asyncio.to_thread", AsyncMock(side_effect=lambda fn, *a, **k: fn(*a, **k))
    )
    monkeypatch.setattr("subprocess.run", subprocess_run)

    await pattern.stop_agent(handle)

    subprocess_run.assert_called_once_with(
        ["synapse", "kill", "synapse-codex-8126", "-f"],
        capture_output=True,
        check=False,
        text=True,
        timeout=30,
    )


@pytest.mark.asyncio
async def test_cleanup_stops_all_agents(monkeypatch):
    from synapse.patterns import (
        AgentHandle,
        CoordinationPattern,
        PatternConfig,
        TaskResult,
    )

    class DemoPattern(CoordinationPattern):
        name = "demo"
        description = "Demo pattern"

        async def run(self, task: str, config: PatternConfig) -> TaskResult:
            return TaskResult(status="completed")

    pattern = DemoPattern()
    pattern._agents = [
        AgentHandle(
            agent_id=f"synapse-codex-81{i}",
            profile="codex",
            port=8100 + i,
            endpoint=f"http://localhost:{8100 + i}",
        )
        for i in range(2)
    ]
    stop_agent = AsyncMock(side_effect=[RuntimeError("boom"), None])
    monkeypatch.setattr(pattern, "stop_agent", stop_agent)

    await pattern.cleanup()

    assert stop_agent.await_count == 2


@pytest.mark.asyncio
async def test_send_wraps_a2a_client(monkeypatch):
    from synapse.patterns import (
        AgentHandle,
        CoordinationPattern,
        PatternConfig,
        TaskResult,
    )

    class DemoPattern(CoordinationPattern):
        name = "demo"
        description = "Demo pattern"

        async def run(self, task: str, config: PatternConfig) -> TaskResult:
            return TaskResult(status="completed")

    pattern = DemoPattern()
    handle = AgentHandle(
        agent_id="synapse-codex-8126",
        profile="codex",
        port=8126,
        endpoint="http://localhost:8126",
    )
    task = A2ATask(
        id="task-123",
        status="completed",
        message={"parts": [{"text": "done"}]},
        artifacts=[{"path": "report.txt"}],
    )
    send_to_local = MagicMock(return_value=task)
    fake_client = MagicMock(send_to_local=send_to_local)

    monkeypatch.setattr(
        "asyncio.to_thread", AsyncMock(side_effect=lambda fn, *a, **k: fn(*a, **k))
    )
    monkeypatch.setattr("synapse.patterns.base._a2a_client", lambda: fake_client)

    result = await pattern.send(
        handle,
        "run test",
        response_mode="wait",
        priority=3,
        timeout=120,
    )

    send_to_local.assert_called_once_with(
        endpoint="http://localhost:8126",
        message="run test",
        response_mode="wait",
        priority=3,
        wait_for_completion=True,
        timeout=120,
    )
    assert result == TaskResult(
        status="completed",
        output="done",
        error="",
        task_id="task-123",
        artifacts=[{"path": "report.txt"}],
    )


@pytest.mark.asyncio
async def test_send_all_parallel(monkeypatch):
    from synapse.patterns import (
        AgentHandle,
        CoordinationPattern,
        PatternConfig,
        TaskResult,
    )

    class DemoPattern(CoordinationPattern):
        name = "demo"
        description = "Demo pattern"

        async def run(self, task: str, config: PatternConfig) -> TaskResult:
            return TaskResult(status="completed")

    pattern = DemoPattern()
    agents = [
        AgentHandle(
            agent_id=f"synapse-codex-81{i}",
            profile="codex",
            port=8100 + i,
            endpoint=f"http://localhost:{8100 + i}",
        )
        for i in range(2)
    ]
    send = AsyncMock(
        side_effect=[
            TaskResult(status="completed", output="first"),
            TaskResult(status="completed", output="second"),
        ]
    )
    gather_calls = []

    async def fake_gather(*coroutines):
        gather_calls.append(coroutines)
        return [await coro for coro in coroutines]

    monkeypatch.setattr(pattern, "send", send)
    monkeypatch.setattr("asyncio.gather", fake_gather)

    results = await pattern.send_all(agents, "hello", response_mode="wait")

    assert [result.output for result in results] == ["first", "second"]
    assert send.await_count == 2
    assert len(gather_calls) == 1


@pytest.mark.asyncio
async def test_broadcast_sends_to_all_agents(monkeypatch):
    from synapse.patterns import (
        AgentHandle,
        CoordinationPattern,
        PatternConfig,
        TaskResult,
    )

    class DemoPattern(CoordinationPattern):
        name = "demo"
        description = "Demo pattern"

        async def run(self, task: str, config: PatternConfig) -> TaskResult:
            return TaskResult(status="completed")

    pattern = DemoPattern()
    pattern._agents = [
        AgentHandle(
            agent_id=f"synapse-codex-81{i}",
            profile="codex",
            port=8100 + i,
            endpoint=f"http://localhost:{8100 + i}",
        )
        for i in range(2)
    ]
    send_all = AsyncMock(return_value=[])
    monkeypatch.setattr(pattern, "send_all", send_all)

    await pattern.broadcast("attention", priority=4)

    send_all.assert_awaited_once_with(
        pattern._agents, "attention", response_mode="notify", priority=4
    )


def test_request_stop_and_should_stop():
    from synapse.patterns import CoordinationPattern, PatternConfig, TaskResult

    class DemoPattern(CoordinationPattern):
        name = "demo"
        description = "Demo pattern"

        async def run(self, task: str, config: PatternConfig) -> TaskResult:
            return TaskResult(status="completed")

    pattern = DemoPattern()

    assert pattern.should_stop is False

    pattern.request_stop()

    assert pattern.should_stop is True


@pytest.mark.asyncio
async def test_cleanup_on_error():
    from synapse.patterns import CoordinationPattern, PatternConfig

    @dataclass
    class DemoConfig(PatternConfig):
        fail: bool = False

    class DemoPattern(CoordinationPattern):
        name = "demo"
        description = "Demo pattern"

        async def run(self, task: str, config: DemoConfig):
            try:
                if config.fail:
                    raise RuntimeError("boom")
                return task
            finally:
                await self.cleanup()

    pattern = DemoPattern()
    pattern.cleanup = AsyncMock()

    with pytest.raises(RuntimeError, match="boom"):
        await pattern.run("task", DemoConfig(fail=True))

    pattern.cleanup.assert_awaited_once()
