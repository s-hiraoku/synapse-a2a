"""Minimal MCP server for Synapse bootstrap resources."""

from __future__ import annotations

import json
import logging
import os
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass
from importlib.metadata import version
from pathlib import Path
from typing import TextIO, cast

from synapse.registry import AgentRegistry
from synapse.settings import SynapseSettings, get_settings

logger = logging.getLogger(__name__)


class UnknownMCPResourceError(ValueError):
    """Raised when an unknown MCP resource URI is requested."""


@dataclass(frozen=True)
class MCPResource:
    """Static description of an MCP resource."""

    uri: str
    name: str
    description: str
    mimeType: str = "text/markdown"


@dataclass(frozen=True)
class MCPTool:
    """Static description of an MCP tool."""

    name: str
    description: str
    inputSchema: dict[str, object]


class SynapseMCPServer:
    """Expose Synapse bootstrap documents as MCP resources."""

    _AGENT_JSON_FIELDS = (
        "agent_id",
        "agent_type",
        "name",
        "role",
        "skill_set",
        "port",
        "status",
        "pid",
        "working_dir",
        "endpoint",
        "transport",
        "current_task_preview",
        "task_received_at",
    )

    def __init__(
        self,
        settings_factory: Callable[[], SynapseSettings] | None = None,
        *,
        agent_type: str = "default",
        agent_id: str = "synapse-mcp",
        port: int = 0,
        user_dir: Path | None = None,
        registry_factory: Callable[[], AgentRegistry] | None = None,
    ) -> None:
        self._settings_factory = settings_factory or get_settings
        self._registry_factory = registry_factory or AgentRegistry
        self.agent_type = agent_type
        self.agent_id = agent_id
        self.port = port
        self.user_dir = user_dir
        self._cached_settings: SynapseSettings | None = None

    def _settings(self) -> SynapseSettings:
        if self._cached_settings is None:
            self._cached_settings = self._settings_factory()
        return self._cached_settings

    def list_resources(self) -> list[MCPResource]:
        """List available instruction resources for the current agent context."""
        settings = self._settings()
        resources = [
            MCPResource(
                uri="synapse://instructions/default",
                name="Default Instructions",
                description="Base Synapse bootstrap instructions for the current agent.",
            )
        ]

        optional_map = {
            "file-safety.md": MCPResource(
                uri="synapse://instructions/file-safety",
                name="File Safety Instructions",
                description="Multi-agent file locking and modification safety rules.",
            ),
            "shared-memory.md": MCPResource(
                uri="synapse://instructions/shared-memory",
                name="Shared Memory Instructions",
                description="Shared memory conventions and usage guidance.",
            ),
            "learning.md": MCPResource(
                uri="synapse://instructions/learning",
                name="Learning Instructions",
                description="Learning mode guidance and capture rules.",
            ),
            "proactive.md": MCPResource(
                uri="synapse://instructions/proactive",
                name="Proactive Mode Instructions",
                description="Proactive mode operating instructions.",
            ),
        }

        file_paths = settings.get_instruction_file_paths(
            self.agent_type, user_dir=self.user_dir
        )
        basenames = {Path(path).name for path in file_paths}
        for filename, resource in optional_map.items():
            if filename in basenames:
                resources.append(resource)

        return resources

    def list_tools(self) -> list[MCPTool]:
        """List available MCP tools."""
        return [
            MCPTool(
                name="bootstrap_agent",
                description="Return runtime context and instruction resource URIs for the current agent.",
                inputSchema={"type": "object", "properties": {}},
            ),
            MCPTool(
                name="list_agents",
                description="List all running Synapse agents with status and connection info.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "status": {
                            "type": "string",
                            "description": "Filter by status (READY, PROCESSING, etc.)",
                        },
                    },
                },
            ),
        ]

    def read_resource(self, uri: str) -> str:
        """Read a specific Synapse instruction resource."""
        settings = self._settings()

        if uri == "synapse://instructions/default":
            text = settings.get_static_instruction_resource(
                self.agent_type,
                agent_id=self.agent_id,
                port=self.port,
                name=self.agent_id,
            )
            if text:
                return text
            raise UnknownMCPResourceError(uri)

        filename_map = {
            "synapse://instructions/file-safety": "file-safety.md",
            "synapse://instructions/shared-memory": "shared-memory.md",
            "synapse://instructions/learning": "learning.md",
            "synapse://instructions/proactive": "proactive.md",
        }
        filename = filename_map.get(uri)
        if filename is None:
            raise UnknownMCPResourceError(uri)

        text = settings.get_instruction_file_content(
            filename,
            user_dir=self.user_dir,
            agent_id=self.agent_id,
            port=self.port,
        )
        if text:
            return text
        raise UnknownMCPResourceError(uri)

    def call_tool(self, name: str, arguments: dict[str, object]) -> dict[str, object]:
        """Call a supported MCP tool."""
        if name == "bootstrap_agent":
            return self._tool_bootstrap_agent()
        if name == "list_agents":
            return self._tool_list_agents(arguments)
        raise ValueError(f"Unsupported MCP tool: {name}")

    def _tool_bootstrap_agent(self) -> dict[str, object]:
        """Return runtime context and instruction resource URIs."""
        resources = [resource.uri for resource in self.list_resources()]
        return {
            "agent_id": self.agent_id,
            "agent_type": self.agent_type,
            "port": self.port,
            "working_dir": os.fspath(Path.cwd()),
            "instruction_resources": resources,
            "available_features": [
                "instructions",
                "tasks",
                "memory",
                "canvas",
                "file_safety",
            ],
        }

    def _tool_list_agents(self, arguments: dict[str, object]) -> dict[str, object]:
        """List all running agents from the registry."""
        registry = self._registry_factory()
        agents = registry.list_agents()

        result = []
        for agent_id, info in agents.items():
            entry: dict[str, object] = {k: info.get(k) for k in self._AGENT_JSON_FIELDS}
            entry["agent_id"] = agent_id
            transport = registry.get_transport_display(agent_id)
            entry["transport"] = transport or "-"
            result.append(entry)

        status_filter = arguments.get("status")
        if isinstance(status_filter, str) and status_filter:
            result = [a for a in result if a.get("status") == status_filter]

        return {"agents": result}

    def handle_request(self, request: dict[str, object]) -> dict[str, object] | None:
        """Handle a single JSON-RPC MCP request."""
        method = request.get("method")
        request_id = request.get("id")
        params = request.get("params", {})

        try:
            if method == "initialize":
                result: dict[str, object] = {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"resources": {}, "tools": {}},
                    "serverInfo": {
                        "name": "synapse-a2a",
                        "version": version("synapse-a2a"),
                    },
                }
            elif method == "notifications/initialized":
                return None
            elif method == "ping":
                result = {}
            elif method == "resources/list":
                result = {
                    "resources": [
                        asdict(resource) for resource in self.list_resources()
                    ]
                }
            elif method == "resources/read":
                if not isinstance(params, dict):
                    raise ValueError("resources/read params must be an object")
                uri = params.get("uri")
                if not isinstance(uri, str):
                    raise ValueError("resources/read requires string uri")
                text = self.read_resource(uri)
                result = {
                    "contents": [
                        {
                            "uri": uri,
                            "mimeType": "text/markdown",
                            "text": text,
                        }
                    ]
                }
            elif method == "tools/list":
                result = {"tools": [asdict(tool) for tool in self.list_tools()]}
            elif method == "tools/call":
                if not isinstance(params, dict):
                    raise ValueError("tools/call params must be an object")
                name = params.get("name")
                arguments = params.get("arguments", {})
                if not isinstance(name, str):
                    raise ValueError("tools/call requires string name")
                if not isinstance(arguments, dict):
                    raise ValueError("tools/call requires object arguments")
                payload = self.call_tool(name, arguments)
                result = {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(payload),
                        }
                    ]
                }
            else:
                raise ValueError(f"Unsupported MCP method: {method}")
        except UnknownMCPResourceError as exc:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32002, "message": f"Unknown resource: {exc}"},
            }
        except Exception as exc:  # pragma: no cover - defensive server path
            logger.exception("MCP request failed")
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32603, "message": str(exc)},
            }

        return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _read_message(stream: TextIO) -> dict[str, object] | None:
    line = stream.readline()
    if not line:
        return None
    return cast(dict[str, object], json.loads(line))


def _write_message(stream: TextIO, payload: dict[str, object]) -> None:
    stream.write(json.dumps(payload))
    stream.write("\n")
    stream.flush()


def serve_stdio(server: SynapseMCPServer) -> None:
    """Serve MCP requests over stdio using header-framed JSON-RPC."""
    input_stream = sys.stdin
    output_stream = sys.stdout

    while True:
        request = _read_message(input_stream)
        if request is None:
            return
        response = server.handle_request(request)
        if request.get("id") is not None and response is not None:
            _write_message(output_stream, response)
