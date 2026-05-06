"""Explicit adapter interface for CLI-backed agents."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from synapse.port_manager import PORT_RANGES
from synapse.registry import AgentRegistry


class UnknownAdapterError(ValueError):
    """Raised when no adapter is registered for a profile."""


@runtime_checkable
class AgentAdapter(Protocol):
    """Common interface for interacting with a CLI-backed agent."""

    profile: str
    target: str

    def send(self, input: str) -> str:
        """Send input to the agent and return the task id or response id."""

    def status(self) -> str:
        """Return the agent's current status."""


@dataclass
class HttpAgentAdapter:
    """HTTP-backed adapter for Synapse-wrapped CLI agents."""

    profile: str
    target: str
    timeout: float = 5.0

    def _endpoint(self) -> str:
        registry = AgentRegistry()
        info = registry.resolve_agent(self.target) or registry.get_agent(self.target)
        if not info:
            raise UnknownAdapterError(f"agent not found: {self.target}")
        endpoint = info.get("endpoint")
        if isinstance(endpoint, str) and endpoint:
            return endpoint.rstrip("/")
        port = info.get("port")
        if isinstance(port, int):
            return f"http://localhost:{port}"
        raise UnknownAdapterError(f"agent has no endpoint: {self.target}")

    def status(self) -> str:
        with urllib.request.urlopen(
            f"{self._endpoint()}/status", timeout=self.timeout
        ) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return str(data.get("status", "UNKNOWN"))

    def send(self, input: str) -> str:
        payload = {
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": input}],
            },
            "metadata": {"response_mode": "notify"},
        }
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self._endpoint()}/tasks/send",
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise RuntimeError(f"failed to send to {self.target}: {exc}") from exc
        task = data.get("task") if isinstance(data, dict) else None
        if isinstance(task, dict):
            return str(task.get("id", ""))
        return ""


_CLI_ADAPTER_PROFILES = frozenset(PORT_RANGES)


def get_adapter(profile: str, *, target: str) -> AgentAdapter:
    """Return an adapter for a known CLI profile."""
    if profile not in _CLI_ADAPTER_PROFILES:
        raise UnknownAdapterError(f"unknown adapter profile: {profile}")
    return HttpAgentAdapter(profile=profile, target=target)
