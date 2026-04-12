"""Message-bus coordination pattern.

This v1 implementation is explicit fan-out driven by a router result. It is not
a persistent broker or queueing system.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, cast

from synapse.patterns import register_pattern
from synapse.patterns.base import CoordinationPattern, PatternConfig, TaskResult


@dataclass
class SubscriberConfig:
    profile: str
    name: str = ""
    role: str | None = None
    skill_set: str | None = None
    worktree: bool = False
    branch: str | None = None
    auto_approve: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SubscriberConfig:
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
class TopicConfig:
    name: str
    subscribers: list[SubscriberConfig] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TopicConfig:
        subscribers = data.get("subscribers")
        subscriber_items = subscribers if isinstance(subscribers, list) else []
        return cls(
            name=str(data.get("name", "")),
            subscribers=[
                SubscriberConfig.from_dict(item)
                for item in subscriber_items
                if isinstance(item, dict)
            ],
        )


@dataclass
class MessageBusConfig(PatternConfig):
    topics: list[TopicConfig] = field(default_factory=list)
    router: SubscriberConfig = field(
        default_factory=lambda: SubscriberConfig(profile="")
    )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MessageBusConfig:
        topics = data.get("topics")
        topic_items = topics if isinstance(topics, list) else []
        return cls(
            name=str(data.get("name", "")),
            pattern=str(data.get("pattern", "")),
            description=str(data.get("description", "")),
            topics=[
                TopicConfig.from_dict(item)
                for item in topic_items
                if isinstance(item, dict)
            ],
            router=SubscriberConfig.from_dict(
                data.get("router", {}) if isinstance(data.get("router"), dict) else {}
            ),
        )


@register_pattern
class MessageBusPattern(CoordinationPattern):
    name = "message-bus"
    description = "Route a task through a router and fan out to topic subscribers."
    config_class = MessageBusConfig

    async def run(self, task: str, config: PatternConfig) -> TaskResult:
        config = cast(MessageBusConfig, config)
        router = await self.spawn_agent(
            config.router.profile,
            name=config.router.name or None,
            role=config.router.role,
            skill_set=config.router.skill_set,
            worktree=config.router.worktree,
            branch=config.router.branch,
            auto_approve=config.router.auto_approve,
        )

        topic_handles: list[tuple[str, list[Any]]] = []
        for topic in config.topics:
            subscribers = [
                await self.spawn_agent(
                    subscriber.profile,
                    name=subscriber.name or None,
                    role=subscriber.role,
                    skill_set=subscriber.skill_set,
                    worktree=subscriber.worktree,
                    branch=subscriber.branch,
                    auto_approve=subscriber.auto_approve,
                )
                for subscriber in topic.subscribers
            ]
            topic_handles.append((topic.name, subscribers))

        routed = await self.send(router, task, response_mode="wait")
        outputs = [routed.output] if routed.output else []
        if self.should_stop:
            return TaskResult(status="stopped", output="\n".join(outputs))

        failures: list[str] = []
        for topic_name, subscribers in topic_handles:
            fanout_message = f"Original task:\n{task}\n\nRouter output:\n{routed.output}\n\nTopic:\n{topic_name}"
            results = await self.send_all(
                subscribers, fanout_message, response_mode="wait"
            )
            for result in results:
                if result.output:
                    outputs.append(result.output)
                if result.status == "failed" or result.error:
                    failures.append(
                        result.error or result.output or "subscriber failed"
                    )

        if failures:
            return TaskResult(
                status="failed",
                output="\n".join(output for output in outputs if output),
                error="\n".join(failures),
            )
        return TaskResult(
            status="completed", output="\n".join(output for output in outputs if output)
        )
