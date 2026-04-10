"""Minimal MCP server for Synapse bootstrap resources."""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import TextIO, cast

import yaml

from synapse import __version__
from synapse.canvas.protocol import FORMAT_REGISTRY, CanvasMessage, validate_message
from synapse.canvas.store import CanvasStore
from synapse.file_safety import FileSafetyManager
from synapse.registry import AgentRegistry
from synapse.settings import SynapseSettings, get_settings

logger = logging.getLogger(__name__)

# Canonical URI for the default instruction resource.
# Shared with controller.py (_build_mcp_bootstrap_message).
MCP_INSTRUCTIONS_DEFAULT_URI = "synapse://instructions/default"

_SMART_SUGGEST_INSTRUCTIONS = """
## Smart Suggest

When you receive a new task, call `analyze_task` with the user's prompt first.
It returns a `delegation_strategy` field:
- "self": Handle the task yourself (small scope, no delegation needed)
- "subagent": Use your built-in subagent capability (Claude: Agent tool, Codex: subprocess)
- "spawn": Use `synapse spawn` or `synapse team start` for multi-agent execution

If delegation_strategy is "spawn" and a suggestion is returned, share it with the user and ask for approval.
For "self" or "subagent", continue normally with the recommended approach.
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

_DEFAULT_DELEGATION_THRESHOLDS: dict[str, int] = {
    "self_max_files": 3,
    "self_max_lines": 100,
    "subagent_max_files": 8,
    "subagent_max_dirs": 2,
}

_DEFAULT_SUBAGENT_CAPABLE_AGENTS: list[str] = ["claude", "codex"]

# Keywords that indicate a different model's perspective is needed → spawn
_CROSS_MODEL_KEYWORDS: list[str] = [
    "review",
    "レビュー",
    "verify",
    "検証",
    "second opinion",
    "別視点",
]

_LARGE_FILE_THRESHOLD = 100  # lines changed to count as "large"


@dataclass(frozen=True)
class GitDiffStats:
    """Metrics from git diff --numstat for delegation decisions."""

    files_changed: int
    insertions: int
    deletions: int
    directory_spread: int
    file_paths: list[str]
    large_files: list[str]


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
        "summary",
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
        file_safety_factory: Callable[[], FileSafetyManager] | None = None,
    ) -> None:
        self._settings_factory = settings_factory or get_settings
        self._registry_factory = registry_factory or AgentRegistry
        self._file_safety_factory = (
            file_safety_factory or self._default_file_safety_factory
        )
        self.agent_type = agent_type
        self.agent_id = agent_id
        self.port = port
        self.user_dir = user_dir
        self._cached_settings: SynapseSettings | None = None

    @staticmethod
    def _default_file_safety_factory() -> FileSafetyManager | None:
        """Create a FileSafetyManager when available."""
        try:
            return FileSafetyManager()
        except Exception as exc:
            logger.debug("FileSafetyManager unavailable: %s", exc)
            return None

    def _settings(self) -> SynapseSettings:
        if self._cached_settings is None:
            try:
                self._cached_settings = self._settings_factory()
            except Exception as exc:
                logger.error("Failed to load SynapseSettings: %s", exc)
                raise RuntimeError(f"Failed to load settings: {exc}") from exc
        return self._cached_settings

    def list_resources(self) -> list[MCPResource]:
        """List available instruction resources for the current agent context."""
        settings = self._settings()
        resources = [
            MCPResource(
                uri=MCP_INSTRUCTIONS_DEFAULT_URI,
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
            "wiki.md": MCPResource(
                uri="synapse://instructions/wiki",
                name="Wiki Instructions",
                description="LLM Wiki knowledge accumulation rules and conventions.",
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
                description="Analyze a user prompt and suggest delegation strategy (self/subagent/spawn) with team/task splits when appropriate.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "prompt": {
                            "type": "string",
                            "description": "User instruction to analyze for team/task split suggestions.",
                        },
                        "files": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional list of file paths the task is expected to touch.",
                        },
                        "agent_type": {
                            "type": "string",
                            "description": "Calling agent's type (e.g. claude, codex, gemini). Used for subagent capability check.",
                        },
                    },
                    "required": ["prompt"],
                },
            ),
            MCPTool(
                name="canvas_post",
                description="Post content to Canvas without shell escaping. Body may be a string or JSON string for structured formats.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "format": {
                            "type": "string",
                            "description": "Canvas content format",
                        },
                        "body": {
                            "type": "string",
                            "description": "Content body (JSON string for structured formats).",
                        },
                        "title": {
                            "type": "string",
                            "description": "Optional card title.",
                        },
                        "tags": {
                            "type": "string",
                            "description": "Optional comma-separated tags.",
                        },
                    },
                    "required": ["format", "body"],
                },
            ),
        ]

    def read_resource(self, uri: str) -> str:
        """Read a specific Synapse instruction resource."""
        settings = self._settings()

        if uri == MCP_INSTRUCTIONS_DEFAULT_URI:
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
            "synapse://instructions/wiki": "wiki.md",
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
            files = arguments.get("files")
            if files is not None and not isinstance(files, list):
                files = None
            agent_type = arguments.get("agent_type")
            if not isinstance(agent_type, str):
                agent_type = self.agent_type
            return self._tool_analyze_task(prompt, files=files, agent_type=agent_type)
        if name == "canvas_post":
            return self._tool_canvas_post(arguments)
        raise ValueError(f"Unsupported MCP tool: {name}")

    def _tool_canvas_post(self, arguments: dict[str, object]) -> dict[str, object]:
        """Post a Canvas card directly through the local store."""
        format_name = arguments.get("format")
        body = arguments.get("body")
        title = arguments.get("title", "")
        tags_value = arguments.get("tags", "")

        if not isinstance(format_name, str) or not format_name:
            raise ValueError("canvas_post requires string format")
        if format_name not in FORMAT_REGISTRY:
            raise ValueError(
                f"Unknown Canvas format '{format_name}'. "
                f"Valid formats: {', '.join(sorted(FORMAT_REGISTRY))}"
            )
        if not isinstance(title, str):
            raise ValueError("canvas_post title must be a string")
        if not isinstance(tags_value, (str, list)):
            raise ValueError("canvas_post tags must be a string or list")

        body_value = self._coerce_canvas_body(format_name, body)
        tags = self._parse_canvas_tags(tags_value)

        payload: dict[str, object] = {
            "type": "render",
            "content": {"format": format_name, "body": body_value},
            "agent_id": self.agent_id,
            "title": title,
        }
        if tags:
            payload["tags"] = tags

        msg = CanvasMessage.from_dict(payload)
        errors = validate_message(msg)
        if errors:
            raise ValueError("; ".join(errors))

        if isinstance(msg.content, list):
            content_json = json.dumps(
                [block.to_dict() for block in msg.content],
                ensure_ascii=False,
            )
        else:
            content_json = json.dumps(msg.content.to_dict(), ensure_ascii=False)

        store = CanvasStore()
        result = store.add_card(
            agent_id=msg.agent_id or self.agent_id,
            content=content_json,
            title=msg.title,
            agent_name=msg.agent_name or None,
            card_type=msg.type or "render",
            pinned=msg.pinned,
            tags=msg.tags or None,
            template=msg.template,
            template_data=msg.template_data or None,
        )

        try:
            from synapse.canvas import server as canvas_server

            canvas_server._broadcast_event("card_created", result)
        except Exception as exc:  # pragma: no cover - best effort broadcast
            logger.debug("Failed to broadcast Canvas SSE event: %s", exc)

        return result

    def _coerce_canvas_body(
        self, format_name: str, body: object
    ) -> str | dict[str, object] | list[object]:
        """Coerce a Canvas body value from MCP arguments."""
        spec = FORMAT_REGISTRY[format_name]
        if spec.body_type == "string":
            if not isinstance(body, str):
                raise ValueError(f"{format_name} body must be a string")
            return body

        if isinstance(body, (dict, list)):
            parsed = body
        elif isinstance(body, str):
            try:
                parsed = json.loads(body)
            except json.JSONDecodeError as err:
                if spec.body_type == "object":
                    raise ValueError(
                        f"{format_name} body must be valid JSON for structured formats"
                    ) from err
                return body
        else:
            raise ValueError(f"{format_name} body must be a string, object, or array")

        if spec.body_type == "object" and not isinstance(parsed, dict):
            raise ValueError(f"{format_name} body must be a JSON object")
        return cast(str | dict[str, object] | list[object], parsed)

    def _parse_canvas_tags(self, tags_value: object) -> list[str]:
        """Parse tag arguments into a compact list."""
        if isinstance(tags_value, list):
            return [str(tag).strip() for tag in tags_value if str(tag).strip()]
        if isinstance(tags_value, str):
            return [tag.strip() for tag in tags_value.split(",") if tag.strip()]
        return []

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
        try:
            registry = self._registry_factory()
            agents = registry.list_agents()
        except Exception as exc:
            logger.warning("Failed to list agents from registry: %s", exc)
            return {"agents": [], "error": str(exc)}

        result = []
        for agent_id, info in agents.items():
            try:
                entry: dict[str, object] = {
                    k: info.get(k) for k in self._AGENT_JSON_FIELDS
                }
                entry["agent_id"] = agent_id
                transport = registry.get_transport_display(agent_id)
                entry["transport"] = transport or "-"
                result.append(entry)
            except Exception as exc:
                logger.warning("Failed to process agent %s: %s", agent_id, exc)
                continue

        status_filter = arguments.get("status")
        if isinstance(status_filter, str) and status_filter:
            result = [a for a in result if a.get("status") == status_filter]

        return {"agents": result}

    def _tool_analyze_task(
        self,
        prompt: str,
        *,
        files: list[str] | None = None,
        agent_type: str | None = None,
    ) -> dict[str, object]:
        """Analyze a prompt and suggest delegation strategy + team/task split."""
        config = self._load_suggest_config()
        if not bool(config.get("enabled", True)):
            return {"suggestion": None, "reason": "disabled"}

        effective_agent_type = agent_type or self.agent_type
        triggers = config.get("triggers", {})
        if not isinstance(triggers, dict):
            triggers = {}

        changed_paths = self._get_git_status_paths()
        diff_stats = self._get_git_diff_stats()
        extracted_paths = self._extract_file_paths_from_prompt(prompt)
        analysis_paths = list(
            dict.fromkeys(diff_stats.file_paths + changed_paths + extracted_paths)
        )
        if files:
            analysis_paths = list(dict.fromkeys(analysis_paths + files))
        if analysis_paths:
            diff_stats = replace(
                diff_stats,
                files_changed=max(diff_stats.files_changed, len(analysis_paths)),
                directory_spread=len(
                    {self._group_directory(p) for p in analysis_paths}
                ),
                file_paths=analysis_paths,
            )

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

        # Diff-size trigger
        diff_size_cfg = triggers.get("diff_size", {})
        if isinstance(diff_size_cfg, dict):
            min_lines = diff_size_cfg.get("min_lines", 200)
            if (
                isinstance(min_lines, int)
                and (diff_stats.insertions + diff_stats.deletions) >= min_lines
            ):
                triggered_by.append("diff_size")

        # Determine delegation strategy regardless of trigger match
        strategy, strategy_reason = self._determine_delegation_strategy(
            diff_stats, prompt, effective_agent_type, config
        )
        file_conflicts = self._detect_file_conflicts(analysis_paths)
        dependencies = self._detect_dependencies(analysis_paths)
        parallelizable = not dependencies
        warnings: list[str] = []

        if file_conflicts["risk"] == "high":
            strategy = "spawn"
            strategy_reason = "High file-lock conflict risk across task files"
            warnings.append("High file conflict risk detected; prefer spawn.")
        elif (
            not parallelizable
            and len(analysis_paths)
            <= self._load_delegation_thresholds(config)["self_max_files"]
        ):
            strategy = "self"
            strategy_reason = (
                "Strong sequential dependencies across a small file set favor self"
            )

        context: dict[str, object] = {
            "diff_stats": {
                "files": diff_stats.files_changed,
                "insertions": diff_stats.insertions,
                "deletions": diff_stats.deletions,
                "spread": diff_stats.directory_spread,
            },
            "file_conflicts": file_conflicts,
            "dependencies": dependencies,
            "parallelizable": parallelizable,
        }

        suggestion = (
            self._build_suggestion(prompt, analysis_paths, triggered_by, dependencies)
            if triggered_by and strategy == "spawn"
            else None
        )

        # Recommend worktree when spawn strategy or high file conflict risk
        recommended_worktree = strategy == "spawn" or file_conflicts["risk"] == "high"

        result: dict[str, object] = {
            "delegation_strategy": strategy,
            "strategy_reason": strategy_reason,
            "recommended_worktree": recommended_worktree,
            "suggestion": suggestion,
            "context": context,
            "triggered_by": triggered_by,
            "warnings": warnings,
        }
        if not triggered_by:
            result["reason"] = "no_trigger_matched"
        return result

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

        raw_thresholds = suggest.get("delegation_thresholds", {})
        if isinstance(raw_thresholds, dict):
            config["delegation_thresholds"] = raw_thresholds

        raw_capable = suggest.get("subagent_capable_agents")
        if isinstance(raw_capable, list):
            config["subagent_capable_agents"] = raw_capable

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
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.debug("git status failed: %s", exc)
            return []

        if result.returncode != 0:
            logger.debug("git status exited with code %d", result.returncode)
            return []

        return self._parse_git_status_paths(result.stdout)

    def _get_git_diff_stats(self) -> GitDiffStats:
        """Return diff metrics from git diff --numstat, ignoring failures."""
        try:
            result = subprocess.run(
                ["git", "diff", "--numstat", "HEAD"],
                capture_output=True,
                text=True,
                check=False,
                cwd=Path.cwd(),
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.debug("git diff --numstat failed: %s", exc)
            return GitDiffStats(0, 0, 0, 0, [], [])

        if result.returncode != 0:
            return GitDiffStats(0, 0, 0, 0, [], [])

        return self._parse_git_numstat(result.stdout)

    def _parse_git_numstat(self, output: str) -> GitDiffStats:
        """Parse git diff --numstat output into GitDiffStats."""
        if not output or not output.strip():
            return GitDiffStats(0, 0, 0, 0, [], [])

        file_paths: list[str] = []
        large_files: list[str] = []
        total_ins = 0
        total_del = 0

        for line in output.strip().splitlines():
            parts = line.split("\t", 2)
            if len(parts) < 3:
                continue

            ins_str, del_str, filepath = parts
            file_paths.append(filepath)

            if ins_str == "-" or del_str == "-":  # binary file
                continue

            try:
                ins = int(ins_str)
                dels = int(del_str)
            except ValueError:
                continue

            total_ins += ins
            total_del += dels
            if ins + dels >= _LARGE_FILE_THRESHOLD:
                large_files.append(filepath)

        directory_spread = len({self._group_directory(p) for p in file_paths})

        return GitDiffStats(
            files_changed=len(file_paths),
            insertions=total_ins,
            deletions=total_del,
            directory_spread=directory_spread,
            file_paths=file_paths,
            large_files=large_files,
        )

    def _extract_file_paths_from_prompt(self, prompt: str) -> list[str]:
        """Extract likely repository file paths mentioned in the prompt."""
        matches = re.findall(
            r"(?<![\w/.-])([A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+)",
            prompt,
        )
        paths: list[str] = []
        for match in matches:
            candidate = match.rstrip(".,:;)]}\"'")
            if "." not in Path(candidate).name:
                continue
            if candidate.startswith(("http://", "https://")):
                continue
            if candidate not in paths:
                paths.append(candidate)
        return paths

    def _detect_file_conflicts(self, task_files: list[str]) -> dict[str, object]:
        """Detect active locks on task files held by other agents."""
        if not task_files:
            return {"locked_by_others": {}, "risk": "none"}

        try:
            manager = self._file_safety_factory()
            if manager is None:
                return {"locked_by_others": {}, "risk": "none"}
            locks = manager.list_locks()
        except Exception as exc:
            logger.debug("File conflict detection unavailable: %s", exc)
            return {"locked_by_others": {}, "risk": "none"}

        locked_by_others: dict[str, str] = {}
        task_file_set = set(task_files)
        for lock in locks:
            file_path = str(lock.get("file_path", ""))
            if file_path not in task_file_set:
                continue
            holder = str(lock.get("agent_id") or lock.get("agent_name") or "")
            if holder == self.agent_id:
                continue
            locked_by_others[file_path] = holder

        overlap_count = len(locked_by_others)
        risk = "none"
        if overlap_count >= 3:
            risk = "high"
        elif overlap_count >= 1:
            risk = "low"
        return {"locked_by_others": locked_by_others, "risk": risk}

    def _detect_dependencies(self, changed_paths: list[str]) -> list[dict[str, str]]:
        """Infer dependency edges where 'from' must complete before 'to'."""
        dependencies: list[dict[str, str]] = []
        seen: set[tuple[str, str, str]] = set()
        project_root = Path.cwd()
        module_map = self._build_module_map(changed_paths)

        for path_text in changed_paths:
            if Path(path_text).suffix != ".py":
                continue
            try:
                content = (project_root / path_text).read_text(encoding="utf-8")
            except OSError:
                continue

            imports = re.findall(
                r"^\s*from\s+([A-Za-z_][\w.]*)\s+import\s+",
                content,
                flags=re.MULTILINE,
            )
            for import_clause in re.findall(
                r"^\s*import\s+([A-Za-z_][\w., ]*)",
                content,
                flags=re.MULTILINE,
            ):
                imports.extend(
                    part.strip() for part in import_clause.split(",") if part.strip()
                )

            for module_name in imports:
                dependency_path = self._resolve_module_dependency(
                    module_name, module_map
                )
                if dependency_path is None or dependency_path == path_text:
                    continue
                key = (dependency_path, path_text, "import")
                if key in seen:
                    continue
                dependencies.append(
                    {
                        "from": dependency_path,
                        "to": path_text,
                        "reason": "import",
                    }
                )
                seen.add(key)

        ordered_paths = sorted(
            changed_paths,
            key=lambda item: (self._dependency_tier(item), changed_paths.index(item)),
        )
        for previous, current in zip(ordered_paths, ordered_paths[1:], strict=False):
            previous_tier = self._dependency_tier(previous)
            current_tier = self._dependency_tier(current)
            if previous_tier >= current_tier:
                continue
            key = (previous, current, "naming_convention")
            if key in seen:
                continue
            dependencies.append(
                {
                    "from": previous,
                    "to": current,
                    "reason": "naming_convention",
                }
            )
            seen.add(key)

        return dependencies

    def _build_module_map(self, changed_paths: list[str]) -> dict[str, str]:
        module_map: dict[str, str] = {}
        for path_text in changed_paths:
            path = Path(path_text)
            if path.suffix != ".py":
                continue
            module_name = ".".join(path.with_suffix("").parts)
            module_map[module_name] = path_text
            if path.name == "__init__.py":
                module_map[".".join(path.parent.parts)] = path_text
        return module_map

    def _resolve_module_dependency(
        self, module_name: str, module_map: dict[str, str]
    ) -> str | None:
        for candidate in sorted(module_map, key=len, reverse=True):
            if module_name == candidate or module_name.startswith(candidate + "."):
                return module_map[candidate]
        return None

    def _dependency_tier(self, path_text: str) -> int:
        lowered = path_text.lower()
        if lowered.startswith("tests/") or Path(path_text).name.startswith("test_"):
            return 2
        if any(token in lowered for token in ("migration", "schema", "model")):
            return 0
        if any(token in lowered for token in ("service", "handler")):
            return 1
        return 1

    @staticmethod
    def _load_delegation_thresholds(config: dict[str, object] | None) -> dict[str, int]:
        """Load delegation thresholds from config, falling back to defaults."""
        thresholds = dict(_DEFAULT_DELEGATION_THRESHOLDS)
        if config:
            cfg_thresholds = config.get("delegation_thresholds")
            if isinstance(cfg_thresholds, dict):
                for k, v in cfg_thresholds.items():
                    if isinstance(v, int):
                        thresholds[k] = v
        return thresholds

    def _determine_delegation_strategy(
        self,
        diff_stats: GitDiffStats,
        prompt: str,
        agent_type: str,
        config: dict[str, object] | None = None,
    ) -> tuple[str, str]:
        """Determine whether to handle task self, via subagent, or via spawn.

        Returns (strategy, reason) tuple.
        """
        thresholds = self._load_delegation_thresholds(config)
        subagent_capable = list(_DEFAULT_SUBAGENT_CAPABLE_AGENTS)

        if config:
            cfg_capable = config.get("subagent_capable_agents")
            if isinstance(cfg_capable, list):
                subagent_capable = [a for a in cfg_capable if isinstance(a, str)]

        total_lines = diff_stats.insertions + diff_stats.deletions

        # Check for cross-model keywords → always spawn
        prompt_lower = prompt.lower()
        for kw in _CROSS_MODEL_KEYWORDS:
            if kw.lower() in prompt_lower:
                return (
                    "spawn",
                    f"Different model perspective needed (keyword: {kw})",
                )

        # Small change → self
        if (
            diff_stats.files_changed <= thresholds["self_max_files"]
            and total_lines <= thresholds["self_max_lines"]
            and diff_stats.directory_spread <= 1
        ):
            return (
                "self",
                f"Small change ({diff_stats.files_changed} files, "
                f"{total_lines} lines, {diff_stats.directory_spread} directory)",
            )

        # Medium change + subagent-capable agent → subagent
        if (
            diff_stats.files_changed <= thresholds["subagent_max_files"]
            and diff_stats.directory_spread <= thresholds["subagent_max_dirs"]
            and agent_type in subagent_capable
        ):
            return (
                "subagent",
                f"Medium change ({diff_stats.files_changed} files, "
                f"{total_lines} lines, {diff_stats.directory_spread} dirs) — "
                f"{agent_type} has built-in subagent capability",
            )

        # Large change or non-subagent-capable → spawn
        return (
            "spawn",
            f"Large change ({diff_stats.files_changed} files, "
            f"{total_lines} lines, {diff_stats.directory_spread} dirs) — "
            f"recommend Synapse spawn for parallel execution",
        )

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
        self,
        prompt: str,
        changed_paths: list[str],
        triggered_by: list[str],
        dependencies: list[dict[str, str]],
    ) -> dict[str, object]:
        subject = self._derive_subject(prompt, changed_paths)
        agent_cycle = ["claude", "codex", "gemini"]
        tasks: list[dict[str, object]] = []
        prior_subjects: list[str] = []
        for index, tier_files in enumerate(
            self._build_dependency_tiers(changed_paths, dependencies), start=1
        ):
            task_subject = f"{subject} tier {index}"
            tasks.append(
                {
                    "subject": task_subject,
                    "description": (
                        f"Update dependency tier {index}: {', '.join(tier_files)}."
                    ),
                    "suggested_agent": agent_cycle[(index - 1) % len(agent_cycle)],
                    "priority": 4 if index == 1 else 3,
                    "blocked_by": list(prior_subjects),
                }
            )
            prior_subjects.append(task_subject)

        summary = (
            "This work looks broad enough to benefit from splitting execution by "
            "dependency tier."
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

    def _build_dependency_tiers(
        self, changed_paths: list[str], dependencies: list[dict[str, str]]
    ) -> list[list[str]]:
        if not changed_paths:
            return []
        if not dependencies:
            return [changed_paths]

        incoming: dict[str, set[str]] = {path: set() for path in changed_paths}
        outgoing: dict[str, set[str]] = {path: set() for path in changed_paths}
        for dependency in dependencies:
            source = dependency["from"]
            target = dependency["to"]
            if source not in incoming or target not in incoming:
                continue
            incoming[target].add(source)
            outgoing[source].add(target)

        remaining = list(changed_paths)
        tiers: list[list[str]] = []
        while remaining:
            tier = [path for path in remaining if not incoming[path]]
            if not tier:
                tiers.append(remaining[:])
                break
            tiers.append(tier)
            remaining = [path for path in remaining if path not in tier]
            for path in tier:
                for child in outgoing[path]:
                    incoming[child].discard(path)
        return tiers

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
                        "version": __version__,
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
