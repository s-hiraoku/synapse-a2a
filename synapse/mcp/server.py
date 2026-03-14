"""Minimal MCP server for Synapse bootstrap resources."""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass
from importlib.metadata import version
from pathlib import Path
from typing import TextIO, cast

import yaml

from synapse.registry import AgentRegistry
from synapse.settings import SynapseSettings, get_settings

logger = logging.getLogger(__name__)

_SMART_SUGGEST_INSTRUCTIONS = """
## Smart Suggest

When you receive a new task, call `analyze_task` with the user's prompt first.
If it returns a suggestion, share it with the user and ask for approval.
If it returns no suggestion, continue normally.
""".strip()

_DEFAULT_SUGGEST_CONFIG: dict[str, object] = {
    "enabled": True,
    "triggers": {
        "min_files": 10,
        "multi_directory": True,
        "missing_tests": True,
        "min_prompt_length": 200,
        "keywords": [
            "リファクタ",
            "移行",
            "レビュー",
            "設計",
            "大規模",
            "refactor",
            "migrate",
            "review",
            "redesign",
        ],
    },
}


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
            MCPTool(
                name="analyze_task",
                description="Analyze a user prompt and suggest team/task splits when the work looks large enough.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "prompt": {
                            "type": "string",
                            "description": "User instruction to analyze for team/task split suggestions.",
                        }
                    },
                    "required": ["prompt"],
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
                if "analyze_task" not in text:
                    text = text.rstrip() + "\n\n" + _SMART_SUGGEST_INSTRUCTIONS
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
        if name == "analyze_task":
            prompt = arguments.get("prompt")
            if not isinstance(prompt, str):
                raise ValueError("analyze_task requires string prompt")
            return self._tool_analyze_task(prompt)
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

    def _tool_analyze_task(self, prompt: str) -> dict[str, object]:
        """Analyze a prompt and suggest a team/task split when triggers match."""
        config = self._load_suggest_config()
        if not bool(config.get("enabled", True)):
            return {"suggestion": None, "reason": "disabled"}

        triggers = config.get("triggers", {})
        if not isinstance(triggers, dict):
            triggers = {}

        changed_paths = self._get_git_status_paths()
        triggered_by: list[str] = []

        min_files = triggers.get("min_files", 10)
        if isinstance(min_files, int) and len(changed_paths) >= min_files:
            triggered_by.append("changed_files")

        if triggers.get("multi_directory", True):
            directories = {self._group_directory(path) for path in changed_paths}
            if len(directories) >= 2:
                triggered_by.append("multi_directory")

        if triggers.get("missing_tests", True) and self._has_missing_tests(
            changed_paths
        ):
            triggered_by.append("missing_tests")

        min_prompt_length = triggers.get("min_prompt_length", 200)
        if isinstance(min_prompt_length, int) and len(prompt) >= min_prompt_length:
            triggered_by.append("prompt_length")

        keywords = triggers.get("keywords", [])
        if isinstance(keywords, list):
            prompt_lower = prompt.lower()
            for keyword in keywords:
                if isinstance(keyword, str) and keyword.lower() in prompt_lower:
                    triggered_by.append(f"keyword:{keyword}")

        if not triggered_by:
            return {"suggestion": None, "reason": "no_trigger_matched"}

        return {
            "suggestion": self._build_suggestion(prompt, changed_paths, triggered_by),
            "triggered_by": triggered_by,
        }

    def _load_suggest_config(self) -> dict[str, object]:
        """Load suggest configuration from project scope, falling back to defaults."""
        config: dict[str, object] = {
            "enabled": _DEFAULT_SUGGEST_CONFIG["enabled"],
            "triggers": dict(
                cast(dict[str, object], _DEFAULT_SUGGEST_CONFIG["triggers"])
            ),
        }
        config_path = Path.cwd() / ".synapse" / "suggest.yaml"
        if not config_path.is_file():
            return config

        try:
            raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            logger.warning("Failed to load suggest config from %s", config_path)
            return config

        if not isinstance(raw, dict):
            return config
        suggest = raw.get("suggest", {})
        if not isinstance(suggest, dict):
            return config

        enabled = suggest.get("enabled")
        if isinstance(enabled, bool):
            config["enabled"] = enabled

        raw_triggers = suggest.get("triggers", {})
        if isinstance(raw_triggers, dict):
            merged_triggers = cast(dict[str, object], config["triggers"])
            merged_triggers.update(raw_triggers)

        return config

    def _get_git_status_paths(self) -> list[str]:
        """Return changed paths from git status, ignoring failures."""
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True,
                text=True,
                check=False,
                cwd=Path.cwd(),
            )
        except OSError:
            return []

        if result.returncode != 0:
            return []

        return self._parse_git_status_paths(result.stdout)

    def _parse_git_status_paths(self, output: str) -> list[str]:
        """Extract changed paths from git status --porcelain output."""
        paths: list[str] = []
        for line in output.splitlines():
            if len(line) < 4:
                continue
            path_text = line[3:].strip()
            if " -> " in path_text:
                path_text = path_text.split(" -> ", 1)[1].strip()
            if path_text:
                paths.append(path_text)
        return paths

    def _group_directory(self, path_text: str) -> str:
        path = Path(path_text)
        if len(path.parts) <= 1:
            return "."
        return path.parts[0]

    def _has_missing_tests(self, changed_paths: list[str]) -> bool:
        project_root = Path.cwd()
        tests_root = project_root / "tests"
        if not tests_root.exists():
            # No tests directory at all — any source file counts as missing
            return any(
                Path(p).suffix == ".py"
                and not (Path(p).parts and Path(p).parts[0] == "tests")
                and not Path(p).name.startswith("test_")
                for p in changed_paths
            )
        # Build set of existing test filenames once (avoid per-file rglob)
        existing_tests = {f.name for f in tests_root.rglob("test_*.py")}
        for path_text in changed_paths:
            path = Path(path_text)
            if path.suffix != ".py":
                continue
            if path.parts and path.parts[0] == "tests":
                continue
            if path.name.startswith("test_"):
                continue
            if f"test_{path.stem}.py" not in existing_tests:
                return True
        return False

    def _build_suggestion(
        self, prompt: str, changed_paths: list[str], triggered_by: list[str]
    ) -> dict[str, object]:
        subject = self._derive_subject(prompt, changed_paths)
        tasks = [
            {
                "subject": f"{subject} design",
                "description": "Clarify scope, interfaces, and rollout risks before implementation.",
                "suggested_agent": "claude",
                "priority": 4,
                "blocked_by": [],
            },
            {
                "subject": f"{subject} implementation",
                "description": "Make the code changes across the affected files and directories.",
                "suggested_agent": "codex",
                "priority": 3,
                "blocked_by": [f"{subject} design"],
            },
            {
                "subject": f"{subject} verification",
                "description": "Add or update tests and review the final behavior.",
                "suggested_agent": "gemini",
                "priority": 3,
                "blocked_by": [f"{subject} implementation"],
            },
        ]

        summary = (
            "This work looks broad enough to benefit from splitting design, "
            "implementation, and verification."
        )
        if any(
            trigger.startswith("keyword:review") or trigger == "keyword:レビュー"
            for trigger in triggered_by
        ):
            summary = "This request looks review-heavy; splitting analysis, implementation, and verification will reduce context switching."

        return {
            "type": "team_split",
            "summary": summary,
            "tasks": tasks,
            "approve_command": "Share the proposed split with the user and ask for approval before execution.",
            "team_command": "synapse team start claude codex gemini -- <approved task>",
        }

    def _derive_subject(self, prompt: str, changed_paths: list[str]) -> str:
        cleaned = re.sub(r"\s+", " ", prompt).strip()
        if cleaned:
            return cleaned[:40].rstrip(" .")
        if changed_paths:
            return Path(changed_paths[0]).stem.replace("_", " ")
        return "Task"

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
