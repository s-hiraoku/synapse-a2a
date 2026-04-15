from __future__ import annotations

import asyncio
import logging
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

import yaml

from synapse.registry import AgentRegistry

if TYPE_CHECKING:
    from types import ModuleType

    from synapse.a2a_client import A2AClient as _A2AClientType

logger = logging.getLogger(__name__)


def _spawn_module() -> ModuleType:
    from synapse import spawn

    return spawn


def _a2a_client() -> _A2AClientType:
    from synapse.a2a_client import A2AClient

    return A2AClient()


def _extract_message_text(message: dict | None) -> str:
    if not isinstance(message, dict):
        return ""
    parts = message.get("parts")
    if not isinstance(parts, list):
        return ""
    texts: list[str] = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        text = part.get("text")
        if isinstance(text, str):
            texts.append(text)
    return "\n".join(texts)


@dataclass
class AgentHandle:
    """Reference to a spawned agent."""

    agent_id: str
    profile: str
    port: int
    endpoint: str
    name: str | None = None
    role: str | None = None
    worktree_path: str | None = None
    worktree_branch: str | None = None


@dataclass
class TaskResult:
    """Result from agent communication or pattern execution."""

    status: str
    output: str = ""
    error: str = ""
    task_id: str = ""
    artifacts: list[dict] = field(default_factory=list)


@dataclass
class PatternConfig:
    """Base configuration for coordination patterns."""

    name: str = ""
    pattern: str = ""
    description: str = ""


class PatternError(ValueError):
    """Raised for invalid pattern operations."""


class CoordinationPattern(ABC):
    """Abstract base class for all coordination patterns."""

    name: str = ""
    description: str = ""

    def __init__(self, run_id: str = "") -> None:
        self.run_id = run_id
        self._agents: list[AgentHandle] = []
        self._stopped = False

    async def spawn_agent(
        self,
        profile: str,
        name: str | None = None,
        role: str | None = None,
        skill_set: str | None = None,
        worktree: bool = False,
        branch: str | None = None,
        auto_approve: bool = True,
    ) -> AgentHandle:
        spawn = _spawn_module()
        prepared = await asyncio.to_thread(
            spawn.prepare_spawn,
            profile=profile,
            name=name,
            role=role,
            skill_set=skill_set,
            worktree=worktree,
            branch=branch,
            auto_approve=auto_approve,
        )
        results = await asyncio.to_thread(spawn.execute_spawn, [prepared])
        if not results:
            raise PatternError("Spawn returned no results")

        result = results[0]
        if getattr(result, "status", "") != "submitted":
            raise PatternError(f"Spawn failed with status: {result.status}")

        alive = await asyncio.to_thread(spawn.wait_for_agent, result.agent_id)
        if not alive:
            raise PatternError(f"Spawned agent did not become ready: {result.agent_id}")

        info = AgentRegistry().resolve_agent(result.agent_id)
        if info is None:
            raise PatternError(
                f"Spawned agent missing from registry: {result.agent_id}"
            )

        endpoint = info.get("endpoint")
        if not isinstance(endpoint, str) or not endpoint:
            raise PatternError(f"Spawned agent missing endpoint: {result.agent_id}")

        handle = AgentHandle(
            agent_id=result.agent_id,
            profile=profile,
            port=result.port,
            endpoint=endpoint,
            name=info.get("name"),
            role=info.get("role"),
            worktree_path=info.get("worktree_path") or result.worktree_path,
            worktree_branch=info.get("worktree_branch") or result.worktree_branch,
        )
        self._agents.append(handle)
        return handle

    async def spawn_agents(
        self,
        count: int,
        profile: str,
        **kwargs: Any,
    ) -> list[AgentHandle]:
        return list(
            await asyncio.gather(
                *[self.spawn_agent(profile, **kwargs) for _ in range(count)]
            )
        )

    async def stop_agent(self, agent: AgentHandle) -> None:
        await asyncio.to_thread(
            subprocess.run,
            ["synapse", "kill", agent.agent_id, "-f"],
            capture_output=True,
            check=False,
            text=True,
            timeout=30,
        )

    async def cleanup(self) -> None:
        agents = list(self._agents)
        self._agents = []
        for agent in agents:
            try:
                await self.stop_agent(agent)
            except Exception:
                logger.warning("Failed to stop agent %s", agent.agent_id, exc_info=True)

    async def send(
        self,
        target: AgentHandle,
        message: str,
        response_mode: str = "wait",
        priority: int = 3,
        timeout: int = 600,
    ) -> TaskResult:
        client = _a2a_client()
        task = await asyncio.to_thread(
            client.send_to_local,
            endpoint=target.endpoint,
            message=message,
            response_mode=response_mode,
            priority=priority,
            wait_for_completion=response_mode == "wait",
            timeout=timeout,
        )
        if task is None:
            raise PatternError(f"No task result received from {target.agent_id}")

        return TaskResult(
            status=task.status,
            output=_extract_message_text(task.message),
            error="",
            task_id=task.id,
            artifacts=list(task.artifacts),
        )

    async def send_all(
        self,
        targets: list[AgentHandle],
        message: str,
        response_mode: str = "wait",
        priority: int = 3,
        timeout: int = 600,
    ) -> list[TaskResult]:
        return await asyncio.gather(
            *[
                self.send(
                    target,
                    message,
                    response_mode=response_mode,
                    priority=priority,
                    timeout=timeout,
                )
                for target in targets
            ]
        )

    async def broadcast(self, message: str, priority: int = 1) -> None:
        await self.send_all(
            self._agents,
            message,
            response_mode="notify",
            priority=priority,
        )

    async def wiki_write(self, key: str, content: str) -> None:
        from synapse.wiki import ensure_wiki_dir

        def _write() -> None:
            wiki_dir = ensure_wiki_dir("project")
            page_path = wiki_dir / "pages" / f"{key}.md"
            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
            frontmatter = {
                "type": "learning",
                "title": key.replace("-", " ").title(),
                "created": timestamp,
                "updated": timestamp,
                "sources": [],
                "links": [],
                "confidence": "medium",
                "author": "pattern",
            }
            document = f"---\n{yaml.dump(frontmatter, default_flow_style=False)}---\n{content}\n"
            page_path.write_text(document, encoding="utf-8")

        await asyncio.to_thread(_write)

    async def wiki_query(self, question: str) -> str:
        completed = await asyncio.to_thread(
            subprocess.run,
            ["synapse", "wiki", "query", question],
            capture_output=True,
            check=False,
            text=True,
            timeout=30,
        )
        return completed.stdout.strip()

    async def merge_worktree(self, agent: AgentHandle) -> None:
        await asyncio.to_thread(
            subprocess.run,
            ["synapse", "merge", agent.agent_id],
            capture_output=True,
            check=False,
            text=True,
            timeout=60,
        )

    async def canvas_post(self, content_format: str, body: str, **kwargs: Any) -> None:
        command = ["synapse", "canvas", "post", content_format, body]
        if title := kwargs.get("title"):
            command.extend(["--title", str(title)])
        if tags := kwargs.get("tags"):
            command.extend(["--tags", str(tags)])
        await asyncio.to_thread(
            subprocess.run,
            command,
            capture_output=True,
            check=False,
            text=True,
            timeout=30,
        )

    def log(self, message: str) -> None:
        logger.info("%s: %s", self.name or self.__class__.__name__, message)

    def request_stop(self) -> None:
        self._stopped = True

    @property
    def should_stop(self) -> bool:
        return self._stopped

    @abstractmethod
    async def run(self, task: str, config: PatternConfig) -> TaskResult:
        """Execute the coordination pattern."""

    def describe_plan(self, task: str, config: PatternConfig) -> list[str]:
        """Return a human-readable preview of what ``run`` would do.

        Subclasses should override this to list the agents that would be
        spawned, the messages that would be sent, and any verification or
        termination rules that would be enforced. Implementations MUST NOT
        perform spawns, A2A calls, or other side effects — the result is
        consumed by ``synapse map run ... --dry-run``.
        """
        return [f"{self.__class__.__name__}: no plan preview available"]
