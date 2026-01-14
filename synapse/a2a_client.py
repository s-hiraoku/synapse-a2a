"""
Google A2A Protocol Client

This module provides a client for communicating with external
Google A2A compatible agents.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin

import httpx
import requests

from synapse.config import (
    COMPLETED_TASK_STATES,
    REQUEST_TIMEOUT,
    TASK_POLL_INTERVAL,
)
from synapse.utils import get_iso_timestamp

if TYPE_CHECKING:
    from synapse.registry import AgentRegistry

# ============================================================
# Data Classes
# ============================================================


@dataclass
class ExternalAgent:
    """Represents an external A2A agent"""

    name: str
    url: str
    description: str = ""
    capabilities: dict[str, Any] = field(default_factory=dict)
    skills: list[dict[str, Any]] = field(default_factory=list)
    added_at: str = ""
    last_seen: str = ""
    alias: str = ""  # Short name for @alias syntax

    def __post_init__(self) -> None:
        if not self.added_at:
            self.added_at = get_iso_timestamp()
        if not self.alias:
            # Generate alias from name (lowercase, no spaces)
            self.alias = self.name.lower().replace(" ", "-").replace("_", "-")


@dataclass
class A2AMessage:
    """A2A Message structure"""

    role: str = "user"
    parts: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_text(cls, text: str) -> A2AMessage:
        """Create a message from plain text"""
        return cls(role="user", parts=[{"type": "text", "text": text}])


@dataclass
class A2ATask:
    """A2A Task response"""

    id: str
    status: str
    message: dict[str, Any] | None = None
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any], fallback_id: str = "") -> A2ATask:
        """Create an A2ATask from a dictionary response."""
        return cls(
            id=data.get("id", fallback_id),
            status=data.get("status", "unknown"),
            message=data.get("message"),
            artifacts=data.get("artifacts", []),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )


# ============================================================
# External Agent Registry
# ============================================================


class ExternalAgentRegistry:
    """
    Manages external A2A agents.

    Stores agent information in ~/.a2a/external/
    """

    def __init__(self) -> None:
        self.registry_dir = Path.home() / ".a2a" / "external"
        self.registry_dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, ExternalAgent] = {}
        self._lock = threading.Lock()
        self._load_all()

    def _load_all(self) -> None:
        """Load all agents from disk"""
        with self._lock:
            for file in self.registry_dir.glob("*.json"):
                try:
                    with open(file) as f:
                        data = json.load(f)
                        agent = ExternalAgent(**data)
                        self._cache[agent.alias] = agent
                except Exception as e:
                    print(f"Warning: Failed to load {file}: {e}")

    def _save(self, agent: ExternalAgent) -> None:
        """Save agent to disk"""
        file_path = self.registry_dir / f"{agent.alias}.json"
        with open(file_path, "w") as f:
            json.dump(asdict(agent), f, indent=2)

    def add(self, agent: ExternalAgent) -> bool:
        """Add an external agent"""
        with self._lock:
            self._cache[agent.alias] = agent
            self._save(agent)
            return True

    def remove(self, alias: str) -> bool:
        """Remove an external agent"""
        with self._lock:
            if alias in self._cache:
                del self._cache[alias]
                file_path = self.registry_dir / f"{alias}.json"
                if file_path.exists():
                    file_path.unlink()
                return True
            return False

    def get(self, alias: str) -> ExternalAgent | None:
        """Get an agent by alias"""
        with self._lock:
            return self._cache.get(alias)

    def list_agents(self) -> list[ExternalAgent]:
        """List all registered external agents"""
        with self._lock:
            return list(self._cache.values())

    def update_last_seen(self, alias: str) -> None:
        """Update last seen timestamp"""
        with self._lock:
            if alias in self._cache:
                self._cache[alias].last_seen = get_iso_timestamp()
                self._save(self._cache[alias])


# ============================================================
# A2A Client
# ============================================================


class A2AClient:
    """
    Client for communicating with external Google A2A agents.
    """

    def __init__(self, registry: ExternalAgentRegistry | None = None):
        self.registry = registry or ExternalAgentRegistry()
        self.timeout = REQUEST_TIMEOUT

    @property
    def _timeout_seconds(self) -> float:
        """Extract read timeout in seconds from timeout config."""
        return self.timeout[1] if isinstance(self.timeout, tuple) else self.timeout

    def discover(self, url: str, alias: str | None = None) -> ExternalAgent | None:
        """
        Discover an agent by fetching its Agent Card.

        Args:
            url: Base URL of the agent (e.g., https://agent.example.com)
            alias: Optional alias for the agent

        Returns:
            ExternalAgent if successful, None otherwise
        """
        try:
            # Fetch Agent Card
            agent_card_url = urljoin(url.rstrip("/") + "/", ".well-known/agent.json")
            response = requests.get(agent_card_url, timeout=self.timeout)
            response.raise_for_status()

            card = response.json()

            agent = ExternalAgent(
                name=card.get("name", "Unknown"),
                url=card.get("url", url),
                description=card.get("description", ""),
                capabilities=card.get("capabilities", {}),
                skills=card.get("skills", []),
                alias=alias or card.get("name", "agent").lower().replace(" ", "-"),
            )

            # Register the agent
            self.registry.add(agent)

            return agent

        except requests.exceptions.RequestException as e:
            print(f"Failed to discover agent at {url}: {e}")
            return None

    def send_to_local(
        self,
        endpoint: str,
        message: str,
        priority: int = 1,
        wait_for_completion: bool = False,
        timeout: int = 60,
        sender_info: dict[str, str] | None = None,
        response_expected: bool = True,
        in_reply_to: str | None = None,
        uds_path: str | None = None,
        local_only: bool = False,
        registry: AgentRegistry | None = None,
        sender_agent_id: str | None = None,
        target_agent_id: str | None = None,
    ) -> A2ATask | None:
        """
        Send a message to a local Synapse agent using A2A protocol.

        This is the unified method for local agent communication.
        Uses /tasks/send-priority for priority support (Synapse extension).

        Args:
            endpoint: Agent endpoint URL (e.g., http://localhost:8001)
            message: Message text to send
            priority: Priority level (1-5, 5=interrupt)
            wait_for_completion: Whether to wait for task completion
            timeout: Timeout in seconds for waiting
            sender_info: Optional dict with sender_id, sender_type, sender_endpoint
            response_expected: Whether the sender expects a response from the target agent
            in_reply_to: Optional task ID to attach a reply to
            uds_path: Optional UDS socket path for local communication
            local_only: If True, only use UDS (no HTTP fallback)
            registry: Optional AgentRegistry for transport status updates
            sender_agent_id: Optional sender agent ID for transport display
            target_agent_id: Optional target agent ID for transport display

        Returns:
            A2ATask if successful, None otherwise
        """
        if local_only and not uds_path:
            return None

        # Helper to update transport status in registry
        def _update_transport(transport_type: str | None) -> None:
            if not registry:
                return
            if sender_agent_id:
                value = f"{transport_type}→" if transport_type else None
                registry.update_transport(sender_agent_id, value)
            if target_agent_id:
                value = f"→{transport_type}" if transport_type else None
                registry.update_transport(target_agent_id, value)

        try:
            # Create A2A message
            a2a_message = A2AMessage.from_text(message)

            # Build request payload
            payload: dict[str, Any] = {"message": asdict(a2a_message)}

            # Add metadata with sender info and response_expected flag
            metadata: dict[str, Any] = {"response_expected": response_expected}
            if sender_info:
                metadata["sender"] = sender_info
            if in_reply_to:
                metadata["in_reply_to"] = in_reply_to
            payload["metadata"] = metadata

            task_data = None
            used_uds = False

            if uds_path:
                uds_file = Path(uds_path)
                if uds_file.exists():
                    # Update transport to UDS before attempting
                    _update_transport("UDS")
                    retries = [0.05, 0.1, 0.2]
                    for idx, delay in enumerate(retries, start=1):
                        try:
                            uds_url = (
                                f"http://localhost/tasks/send-priority?priority="
                                f"{priority}"
                            )
                            transport = httpx.HTTPTransport(uds=uds_path)
                            timeout_cfg = httpx.Timeout(
                                self._timeout_seconds, connect=0.2
                            )
                            with httpx.Client(
                                transport=transport, timeout=timeout_cfg
                            ) as client:
                                uds_response = client.post(uds_url, json=payload)
                                uds_response.raise_for_status()
                                result = uds_response.json()
                                task_data = result.get("task", result)
                                used_uds = True
                                break
                        except httpx.TransportError:
                            if idx == len(retries):
                                # UDS failed, clear transport before TCP fallback
                                _update_transport(None)
                                if local_only:
                                    return None
                                break
                            time.sleep(delay)
                        except httpx.HTTPStatusError:
                            _update_transport(None)
                            return None
                else:
                    if local_only:
                        return None

            if task_data is None:
                # Update transport to TCP
                _update_transport("TCP")
                # Use /tasks/send-priority for priority support
                url = f"{endpoint.rstrip('/')}/tasks/send-priority?priority={priority}"
                http_response = requests.post(url, json=payload, timeout=self.timeout)
                http_response.raise_for_status()

                result = http_response.json()
                task_data = result.get("task", result)

            task = A2ATask.from_dict(task_data)

            if wait_for_completion:
                completed_task = self._wait_for_local_completion(
                    endpoint, task.id, timeout, uds_path=uds_path if used_uds else None
                )
                if completed_task is not None:
                    task = completed_task

            # Clear transport status after communication completes
            _update_transport(None)

            return task

        except requests.exceptions.RequestException as e:
            # Clear transport status on error
            _update_transport(None)
            print(f"Failed to send message to local agent: {e}")
            return None

    def _wait_for_task_completion(
        self,
        get_task_url: Callable[[], str],
        task_id: str,
        timeout: int,
        uds_path: str | None = None,
    ) -> A2ATask | None:
        """
        Wait for a task to complete (unified wait logic).

        Args:
            get_task_url: Callable that returns the task status URL
            task_id: Task ID to wait for
            timeout: Maximum wait time in seconds

        Returns:
            A2ATask if completed, None on timeout
        """
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                url = get_task_url()
                if uds_path:
                    transport = httpx.HTTPTransport(uds=uds_path)
                    timeout_cfg = httpx.Timeout(self._timeout_seconds, connect=0.2)
                    with httpx.Client(
                        transport=transport, timeout=timeout_cfg
                    ) as client:
                        uds_response = client.get(url)
                        uds_response.raise_for_status()
                        data = uds_response.json()
                else:
                    http_response = requests.get(url, timeout=self.timeout)
                    http_response.raise_for_status()
                    data = http_response.json()
                task = A2ATask.from_dict(data, fallback_id=task_id)

                if task.status in COMPLETED_TASK_STATES:
                    return task

            except (requests.exceptions.RequestException, httpx.HTTPError):
                pass

            time.sleep(TASK_POLL_INTERVAL)

        return None

    def _wait_for_local_completion(
        self, endpoint: str, task_id: str, timeout: int, uds_path: str | None = None
    ) -> A2ATask | None:
        """Wait for a local task to complete."""
        return self._wait_for_task_completion(
            get_task_url=lambda: f"{endpoint.rstrip('/')}/tasks/{task_id}",
            task_id=task_id,
            timeout=timeout,
            uds_path=uds_path,
        )

    def send_message(
        self,
        alias: str,
        message: str,
        wait_for_completion: bool = False,
        timeout: int = 60,
    ) -> A2ATask | None:
        """
        Send a message to an external agent.

        Args:
            alias: Agent alias
            message: Message text to send
            wait_for_completion: Whether to wait for task completion
            timeout: Timeout in seconds for waiting

        Returns:
            A2ATask if successful, None otherwise
        """
        agent = self.registry.get(alias)
        if not agent:
            print(f"Agent '{alias}' not found")
            return None

        try:
            # Create A2A message
            a2a_message = A2AMessage.from_text(message)

            # Send to /tasks/send
            url = urljoin(agent.url.rstrip("/") + "/", "tasks/send")
            response = requests.post(
                url, json={"message": asdict(a2a_message)}, timeout=self.timeout
            )
            response.raise_for_status()

            result = response.json()
            task_data = result.get("task", result)

            task = A2ATask.from_dict(task_data)

            self.registry.update_last_seen(alias)

            if wait_for_completion:
                completed_task = self._wait_for_completion(agent, task.id, timeout)
                if completed_task is not None:
                    task = completed_task

            return task

        except requests.exceptions.RequestException as e:
            print(f"Failed to send message to {alias}: {e}")
            return None

    def get_task(self, alias: str, task_id: str) -> A2ATask | None:
        """Get task status from an external agent"""
        agent = self.registry.get(alias)
        if not agent:
            return None

        try:
            url = urljoin(agent.url.rstrip("/") + "/", f"tasks/{task_id}")
            response = requests.get(url, timeout=self.timeout)
            response.raise_for_status()

            data = response.json()
            return A2ATask.from_dict(data, fallback_id=task_id)

        except requests.exceptions.RequestException as e:
            print(f"Failed to get task from {alias}: {e}")
            return None

    def cancel_task(self, alias: str, task_id: str) -> bool:
        """Cancel a task on an external agent"""
        agent = self.registry.get(alias)
        if not agent:
            return False

        try:
            url = urljoin(agent.url.rstrip("/") + "/", f"tasks/{task_id}/cancel")
            response = requests.post(url, timeout=self.timeout)
            response.raise_for_status()
            return True

        except requests.exceptions.RequestException:
            return False

    def _wait_for_completion(
        self, agent: ExternalAgent, task_id: str, timeout: int
    ) -> A2ATask | None:
        """Wait for a task to complete on external agent."""
        base_url = agent.url.rstrip("/") + "/"
        return self._wait_for_task_completion(
            get_task_url=lambda: urljoin(base_url, f"tasks/{task_id}"),
            task_id=task_id,
            timeout=timeout,
        )

    def list_agents(self) -> list[ExternalAgent]:
        """List all registered external agents"""
        return self.registry.list_agents()

    def remove_agent(self, alias: str) -> bool:
        """Remove an external agent"""
        return self.registry.remove(alias)


# ============================================================
# Global client instance
# ============================================================

_client: A2AClient | None = None


def get_client() -> A2AClient:
    """Get the global A2A client instance"""
    global _client
    if _client is None:
        _client = A2AClient()
    return _client
