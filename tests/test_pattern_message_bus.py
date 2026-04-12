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


def test_message_bus_config_from_dict_tolerates_unknown_keys() -> None:
    from synapse.patterns.message_bus import MessageBusConfig

    config = MessageBusConfig.from_dict(
        {
            "name": "events-pipeline",
            **_PATTERN_TEMPLATES["message-bus"],
            "unexpected": "ignored",
        }
    )

    assert config.name == "events-pipeline"
    assert config.pattern == "message-bus"
    assert config.router.name == "Router"
    assert [topic.name for topic in config.topics] == ["events"]
    assert [subscriber.name for subscriber in config.topics[0].subscribers] == [
        "Handler-1",
        "Handler-2",
    ]


@pytest.mark.asyncio
async def test_message_bus_run_fans_out_by_topic() -> None:
    from synapse.patterns.message_bus import MessageBusConfig, MessageBusPattern

    pattern = MessageBusPattern(run_id="run-bus")
    router = _handle("Router", 9401)
    subscriber_one = _handle("Handler-1", 9402)
    subscriber_two = _handle("Handler-2", 9403)
    pattern.spawn_agent = AsyncMock(
        side_effect=[router, subscriber_one, subscriber_two]
    )
    pattern.send = AsyncMock(
        return_value=TaskResult(status="completed", output="events")
    )
    pattern.send_all = AsyncMock(
        return_value=[
            TaskResult(status="completed", output="handled one"),
            TaskResult(status="completed", output="handled two"),
        ]
    )

    result = await pattern.run(
        "Broadcast deployment event",
        MessageBusConfig.from_dict(_PATTERN_TEMPLATES["message-bus"]),
    )

    assert result.status == "completed"
    assert result.output.splitlines() == ["events", "handled one", "handled two"]
    router_prompt = pattern.send.await_args.args[1]
    fanout_prompt = pattern.send_all.await_args.args[1]
    assert "Broadcast deployment event" in router_prompt
    assert "events" in fanout_prompt


@pytest.mark.asyncio
async def test_message_bus_propagates_subscriber_failure() -> None:
    from synapse.patterns.message_bus import MessageBusConfig, MessageBusPattern

    pattern = MessageBusPattern(run_id="run-bus")
    router = _handle("Router", 9401)
    subscriber_one = _handle("Handler-1", 9402)
    subscriber_two = _handle("Handler-2", 9403)
    pattern.spawn_agent = AsyncMock(
        side_effect=[router, subscriber_one, subscriber_two]
    )
    pattern.send = AsyncMock(
        return_value=TaskResult(status="completed", output="events")
    )
    pattern.send_all = AsyncMock(
        return_value=[
            TaskResult(status="completed", output="handled one"),
            TaskResult(status="failed", error="subscriber failed"),
        ]
    )

    result = await pattern.run(
        "Broadcast deployment event",
        MessageBusConfig.from_dict(_PATTERN_TEMPLATES["message-bus"]),
    )

    assert result.status == "failed"
    assert "subscriber failed" in result.error


@pytest.mark.asyncio
async def test_message_bus_honors_stop_before_fanout() -> None:
    from synapse.patterns.message_bus import MessageBusConfig, MessageBusPattern

    pattern = MessageBusPattern(run_id="run-bus")
    router = _handle("Router", 9401)
    subscriber_one = _handle("Handler-1", 9402)
    subscriber_two = _handle("Handler-2", 9403)
    pattern.spawn_agent = AsyncMock(
        side_effect=[router, subscriber_one, subscriber_two]
    )

    async def send_side_effect(*args, **kwargs):
        pattern.request_stop()
        return TaskResult(status="completed", output="events")

    pattern.send = AsyncMock(side_effect=send_side_effect)
    pattern.send_all = AsyncMock()

    result = await pattern.run(
        "Broadcast deployment event",
        MessageBusConfig.from_dict(_PATTERN_TEMPLATES["message-bus"]),
    )

    assert result.status == "stopped"
    assert result.output == "events"
    pattern.send_all.assert_not_awaited()


def test_message_bus_is_registered() -> None:
    from synapse.patterns.message_bus import MessageBusPattern

    assert BUILTIN_PATTERNS["message-bus"] is MessageBusPattern
