"""Canvas Server — FastAPI application with SSE and HTML serving.

A dedicated server (default port 3000) that renders agent-posted cards
in the browser with real-time updates via Server-Sent Events.
"""

from __future__ import annotations

import asyncio
import contextlib
import glob
import json
import logging
import os
import re
import signal
import sqlite3
import sys
import time
from collections.abc import AsyncGenerator, Callable, Iterable, Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - 3.10 compat branch
    import tomli as tomllib

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from synapse import __version__
from synapse.canvas import CANVAS_CSS_FILES, CANVAS_JS_FILES, compute_asset_hash
from synapse.canvas.routes.admin import admin_router
from synapse.canvas.routes.cards import cards_router
from synapse.canvas.routes.db import db_router
from synapse.canvas.routes.multiagent import multiagent_router
from synapse.canvas.routes.wiki import is_wiki_enabled, wiki_router
from synapse.canvas.routes.workflow import workflow_router
from synapse.canvas.store import CanvasStore
from synapse.controller import strip_ansi
from synapse.paths import (
    get_file_safety_db_path,
    get_history_db_path,
    get_shared_memory_db_path,
)
from synapse.registry import is_process_running
from synapse.tools.a2a_helpers import _normalize_working_dir

logger = logging.getLogger(__name__)

# SSE event queue for broadcasting to connected clients
_sse_queues: list[asyncio.Queue[str]] = []


class _NoCacheStaticMiddleware(BaseHTTPMiddleware):
    """Add Cache-Control: no-cache to /static/ responses."""

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        response = await call_next(request)
        if request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-cache"
        return response


def _broadcast_event(event_type: str, data: dict[str, Any]) -> None:
    """Broadcast an SSE event to all connected clients."""
    payload = f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
    for q in _sse_queues:
        with contextlib.suppress(asyncio.QueueFull):
            q.put_nowait(payload)


def _strip_terminal_junk(text: str) -> str:
    """Remove ANSI escapes, terminal status bars, and spinner junk from text.

    Agent PTY output contains ANSI escape sequences, status bar text,
    and spinner animation fragments. This function cleans them while
    preserving actual content (including multi-byte chars like Japanese).
    """
    # Step 1: Truncate at BEL character — everything after is status bar junk
    if "\x07" in text:
        text = text[: text.index("\x07")]
        # Remove trailing digits before BEL (CSI parameter remnants like "7" in "です7\x07")
        text = text.rstrip("0123456789")

    # Step 2: Remove ANSI escape sequences (reuse controller.strip_ansi)
    text = strip_ansi(text)

    # Step 3: Remove DEC private mode sequences and orphaned CSI parameter fragments
    # DEC private mode: ?2026h, ?25l, ?7h etc. (remains after ESC[ is stripped)
    text = re.sub(r"\?\d+[hlHL]", "", text)
    # When \x1b was already stripped, bare fragments like "9m", "1C",
    # "249m", "38;2;153;153;153m" remain glued to real text.
    # Pattern: 1-3 digits optionally followed by ;digits, ending in a letter
    text = re.sub(r"\d+(?:;\d+)*[A-HJKSTfm]", "", text)

    # Step 4: Remove well-known terminal UI status bar phrases
    # Codex/Claude status bars: "Esc to cancel · Tab to amend · ctrl+e to explain"
    text = re.sub(
        r"(?:Esc|Tab|ctrl\+\w+)\s+to\s+\w+[\s·]*", "", text, flags=re.IGNORECASE
    )
    # Codex UI fragments: "switchAgentConnection" and similar camelCase UI tokens
    text = re.sub(
        r"switch\s*Agent\s*Connection[^)\n]*\)?", "", text, flags=re.IGNORECASE
    )

    # Step 5: Remove status bar lines with box-drawing characters
    # Codex draws ─────... lines for status bars and prompts
    text = re.sub(r"[─━═]{10,}[^\n]*", "", text)
    # Status bar fragments: "gpt-5.4 medium · 25% left · /path/..."
    text = re.sub(
        r"(?:gpt|claude|gemini|codex)[\w.-]*\s+\w+\s*·[^\n]*",
        "",
        text,
        flags=re.IGNORECASE,
    )
    # Percentage patterns from status bars: "25% left", "31% left"
    text = re.sub(r"\d+%\s+left[^\n]*", "", text, flags=re.IGNORECASE)

    # Step 6: Remove spinner animation fragments
    # "Working", "Workin", "Worki", "Work", "Wor", etc. and bullet-prefixed variants
    text = re.sub(r"[•\u2022]?\s*Work(?:ing|in|i|)\b", "", text)

    # Step 7: Remove control characters (except \t \n \r)
    text = re.sub(r"[\x00-\x08\x0e-\x1f\x7f]", "", text)

    # Step 8: Clean up
    text = re.sub(r"›[^\n]*", "", text)
    text = text.strip().strip("\u2022").strip()
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text


def _get_registry_dir() -> str:
    """Return the path to the agent registry directory."""
    return os.path.expanduser("~/.a2a/registry")


def _is_live_registry_entry(candidate: dict[str, Any]) -> bool:
    """Return False for stale registry entries with dead PIDs."""
    pid = candidate.get("pid")
    if not pid:
        return True
    try:
        return is_process_running(int(pid))
    except (TypeError, ValueError):
        return False


def _log_type_fallback(target: str, candidate: dict[str, Any]) -> None:
    logger.warning(
        "Agent target '%s' resolved by type fallback to %s",
        target,
        candidate.get("agent_id") or candidate.get("name") or candidate.get("endpoint"),
    )


def _resolve_agent_endpoint(
    target: str,
    *,
    caller_working_dir: str | None = None,
    bare_type_same_dir_only: bool = False,
) -> str | None:
    """Resolve an agent target to its HTTP endpoint.

    Searches registry files by agent_id, name, or agent_type.

    Args:
        target: Agent ID, name, or type to resolve.
        caller_working_dir: Optional caller directory used to prefer same-dir
            type fallback matches.
        bare_type_same_dir_only: When True, type targets must resolve within
            caller_working_dir and never fall back to a global type match.

    Returns:
        HTTP endpoint URL, or None if not found.
    """
    candidates: list[dict[str, Any]] = list(_iter_registry_entries(live_only=True))
    if not candidates:
        return None

    # Exact agent_id match
    for c in candidates:
        if c.get("agent_id") == target:
            return c.get("endpoint")

    # Name match
    for c in candidates:
        if c.get("name") == target:
            return c.get("endpoint")

    # Agent type match (only if unique)
    type_matches = [c for c in candidates if c.get("agent_type") == target]
    if caller_working_dir:
        caller_dir = _normalize_working_dir(caller_working_dir)
        same_dir_matches = [
            c
            for c in type_matches
            if _normalize_working_dir(c.get("working_dir")) == caller_dir
        ]
        if len(same_dir_matches) == 1:
            _log_type_fallback(target, same_dir_matches[0])
            return same_dir_matches[0].get("endpoint")
        if bare_type_same_dir_only:
            return None

    if len(type_matches) == 1:
        _log_type_fallback(target, type_matches[0])
        return type_matches[0].get("endpoint")

    return None


def _start_administrator() -> dict[str, Any]:
    """Start the administrator agent using settings config."""
    import subprocess
    import sys

    from synapse.settings import get_settings

    settings = get_settings()
    config = settings.get_administrator_config()

    cmd = [
        sys.executable,
        "-m",
        "synapse.server",
        "--profile",
        config["profile"],
        "--port",
        str(config["port"]),
    ]

    env = os.environ.copy()
    tool_args = config.get("tool_args", [])
    if tool_args:
        env["SYNAPSE_TOOL_ARGS"] = json.dumps(tool_args)

    log_dir = os.path.expanduser("~/.synapse/logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "admin.log")

    with open(log_file, "w") as log:
        process = subprocess.Popen(
            cmd, stdout=log, stderr=log, start_new_session=True, env=env
        )

    return {"status": "started", "pid": process.pid, "port": config["port"]}


def _stop_administrator() -> dict[str, Any]:
    """Stop the administrator agent."""
    from synapse.settings import get_settings

    settings = get_settings()
    config = settings.get_administrator_config()
    agent_id = f"synapse-{config['profile']}-{config['port']}"

    registry_dir = _get_registry_dir()
    registry_file = os.path.join(registry_dir, f"{agent_id}.json")

    if not os.path.exists(registry_file):
        return {"status": "not_running"}

    try:
        data = json.loads(Path(registry_file).read_text(encoding="utf-8"))
        pid = data.get("pid")
        if pid:
            os.kill(pid, signal.SIGTERM)
            return {"status": "stopped", "pid": pid}
    except (json.JSONDecodeError, OSError, ProcessLookupError):
        pass

    return {"status": "not_running"}


def _spawn_agent(
    profile: str, name: str | None = None, role: str | None = None
) -> dict[str, Any]:
    """Spawn a new agent with the given profile."""
    import subprocess
    import sys

    from synapse.port_manager import PortManager
    from synapse.registry import AgentRegistry

    registry = AgentRegistry()
    port_manager = PortManager(registry)
    port = port_manager.get_available_port(profile)

    if port is None:
        return {"status": "error", "detail": f"No available ports for {profile}"}

    cmd = [
        sys.executable,
        "-m",
        "synapse.server",
        "--profile",
        profile,
        "--port",
        str(port),
    ]

    env = os.environ.copy()

    log_dir = os.path.expanduser("~/.synapse/logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f"{profile}-{port}.log")

    with open(log_file, "w") as log:
        process = subprocess.Popen(
            cmd, stdout=log, stderr=log, start_new_session=True, env=env
        )

    agent_id = f"synapse-{profile}-{port}"
    return {"status": "started", "agent_id": agent_id, "pid": process.pid, "port": port}


def _stop_agent(agent_id: str) -> dict[str, Any]:
    """Stop an agent by its ID."""
    registry_dir = _get_registry_dir()
    registry_file = os.path.join(registry_dir, f"{agent_id}.json")

    if not os.path.exists(registry_file):
        return {"status": "not_found", "agent_id": agent_id}

    try:
        data = json.loads(Path(registry_file).read_text(encoding="utf-8"))
        pid = data.get("pid")
        if pid:
            os.kill(pid, signal.SIGTERM)
            return {"status": "stopped", "agent_id": agent_id, "pid": pid}
    except (json.JSONDecodeError, OSError, ProcessLookupError):
        pass

    return {"status": "not_found", "agent_id": agent_id}


CLEANUP_INTERVAL_SECONDS = 300  # 5 minutes

# TTL cache for slow-changing /api/system sections (skills, sessions, etc.)
_STATIC_CACHE_TTL = 60  # seconds

# Human-readable descriptions for SYNAPSE_* environment variables
_ENV_DESCRIPTIONS: dict[str, str] = {
    "SYNAPSE_HISTORY_ENABLED": "Enable task history persistence",
    "SYNAPSE_FILE_SAFETY_ENABLED": "Enable file lock coordination for multi-agent editing",
    "SYNAPSE_FILE_SAFETY_DB_PATH": "Path to file safety SQLite database",
    "SYNAPSE_FILE_SAFETY_RETENTION_DAYS": "Days to retain file safety records",
    "SYNAPSE_AUTH_ENABLED": "Require API key authentication for A2A endpoints",
    "SYNAPSE_API_KEYS": "Comma-separated list of valid API keys",
    "SYNAPSE_ADMIN_KEY": "Admin API key for privileged operations",
    "SYNAPSE_ALLOW_LOCALHOST": "Allow unauthenticated access from localhost",
    "SYNAPSE_USE_HTTPS": "Use HTTPS for agent endpoints",
    "SYNAPSE_WEBHOOK_SECRET": "Shared secret for webhook signature verification",
    "SYNAPSE_WEBHOOK_TIMEOUT": "Webhook request timeout in seconds",
    "SYNAPSE_WEBHOOK_MAX_RETRIES": "Maximum webhook delivery retry attempts",
    "SYNAPSE_LONG_MESSAGE_THRESHOLD": "Character limit before message is stored as file",
    "SYNAPSE_LONG_MESSAGE_TTL": "File-based message retention in seconds",
    "SYNAPSE_LONG_MESSAGE_DIR": "Directory for temporary message files",
    "SYNAPSE_SHARED_MEMORY_ENABLED": "Enable cross-agent shared memory",
    "SYNAPSE_SHARED_MEMORY_DB_PATH": "Path to shared memory SQLite database",
    "SYNAPSE_LEARNING_MODE_ENABLED": "Enable learning mode instructions for agents",
    "SYNAPSE_LEARNING_MODE_TRANSLATION": "Enable translation in learning mode",
    "SYNAPSE_PROACTIVE_MODE_ENABLED": "Enable proactive collaboration mode",
}


def _read_agent_profiles_from_dir(
    profiles_dir: Path,
    *,
    scope: str,
    seen_ids: set[str] | None = None,
) -> list[dict[str, str]]:
    """Read saved agent definitions from a directory."""
    profiles: list[dict[str, str]] = []
    if not profiles_dir.is_dir():
        return profiles

    seen = seen_ids if seen_ids is not None else set()
    for file_path in sorted(profiles_dir.glob("*.agent")):
        try:
            profile_data: dict[str, str] = {}
            for raw_line in file_path.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                profile_data[key.strip()] = value.strip()
            profile_id = profile_data.get("id", "")
            if not profile_id or profile_id in seen:
                continue
            seen.add(profile_id)
            profiles.append(
                {
                    "id": profile_id,
                    "name": profile_data.get("name", ""),
                    "profile": profile_data.get("profile", ""),
                    "role": profile_data.get("role", ""),
                    "skill_set": profile_data.get("skill_set", ""),
                    "scope": scope,
                }
            )
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning(
                "Skipping unreadable saved agent file %s: %s", file_path, exc
            )
            continue
    return profiles


def _active_project_root(agent_data: dict[str, Any]) -> Path | None:
    """Resolve the project root for a live agent, collapsing worktrees to base repo."""
    worktree_path = agent_data.get("worktree_path")
    if worktree_path:
        worktree = Path(str(worktree_path))
        parts = worktree.parts
        if len(parts) >= 3 and parts[-3:-1] == (".synapse", "worktrees"):
            return worktree.parents[2]

    working_dir = agent_data.get("working_dir")
    if working_dir:
        return Path(str(working_dir))
    return None


def _iter_registry_entries_with_errors(
    live_only: bool = False,
) -> Iterator[tuple[str, dict[str, Any] | Exception]]:
    """Yield ``(file_path, data_or_exception)`` for every registry JSON file.

    Shared to avoid reimplementing the glob+parse+skip pattern across callers.
    Use :func:`_iter_registry_entries` when parse errors can be silently dropped.
    """
    registry_dir = _get_registry_dir()
    if not os.path.isdir(registry_dir):
        return
    for file_path in sorted(glob.glob(os.path.join(registry_dir, "*.json"))):
        try:
            data = json.loads(Path(file_path).read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
            if not live_only:
                yield file_path, exc
            continue
        if live_only and not _is_live_registry_entry(data):
            continue
        yield file_path, data


def _iter_registry_entries(live_only: bool = False) -> Iterator[dict[str, Any]]:
    """Yield live registry dicts, silently dropping parse errors."""
    for _, data in _iter_registry_entries_with_errors(live_only=live_only):
        if isinstance(data, dict):
            yield data


def _active_project_roots(
    entries: Iterable[dict[str, Any]] | None = None,
) -> list[Path]:
    """Return unique project roots of live agents (worktree-aware).

    Pass ``entries`` to reuse an already-loaded list of registry dicts and
    avoid a second disk scan. Falls back to reading the registry directly.
    """
    if entries is None:
        entries = _iter_registry_entries(live_only=True)
    seen: set[Path] = set()
    roots: list[Path] = []
    for data in entries:
        root = _active_project_root(data)
        if root is None or root in seen:
            continue
        seen.add(root)
        roots.append(root)
    return roots


def _collect_skills(
    project_roots: list[Path],
    user_dir: Path | None,
    synapse_dir: Path | None,
) -> list[dict[str, Any]]:
    """Scan global (user/synapse) scopes once; project/plugin per active root.

    Project/plugin scopes are scanned per root so each project renders as its
    own UI group.
    """
    skills: list[dict[str, Any]] = []
    try:
        from synapse.skills import SkillScope, discover_skills
    except (ImportError, OSError, RuntimeError):
        logger.debug("Failed to import skills module", exc_info=True)
        return skills

    project_anchor_by_scope: dict[Any, Path | None] = {
        SkillScope.USER: user_dir,
        SkillScope.SYNAPSE: synapse_dir,
    }

    def _record(scanned: Any, project_root: Path | None) -> None:
        for sk in scanned:
            anchor_path = (
                project_root
                if sk.scope in (SkillScope.PROJECT, SkillScope.PLUGIN)
                else project_anchor_by_scope.get(sk.scope)
            )
            skills.append(
                {
                    "name": sk.name,
                    "description": sk.description,
                    "scope": sk.scope.value,
                    "agent_dirs": sk.agent_dirs,
                    "path": str(sk.path),
                    "source_file": str(sk.source_file),
                    "project_root": str(anchor_path) if anchor_path else "",
                }
            )

    try:
        _record(
            discover_skills(
                project_dir=None, user_dir=user_dir, synapse_dir=synapse_dir
            ),
            None,
        )
    except (OSError, RuntimeError):
        logger.debug("Failed to discover global skills", exc_info=True)

    for project_root in project_roots:
        try:
            scanned = discover_skills(
                project_dir=project_root, user_dir=None, synapse_dir=None
            )
        except (OSError, RuntimeError):
            logger.debug("Failed to discover skills in %s", project_root, exc_info=True)
            continue
        _record(scanned, project_root)

    return skills


def _mcp_entry(
    name: str,
    entry: dict[str, Any],
    scope: str,
    src_path: Path,
    project_root: str,
) -> dict[str, Any] | None:
    """Normalize one MCP server entry into the Canvas payload schema.

    ``env_keys`` is returned instead of values to avoid leaking secrets to the UI.
    """
    cmd = entry.get("command", "")
    args = entry.get("args", []) or []
    if isinstance(cmd, list):
        if not cmd:
            return None
        args = list(cmd[1:]) + list(args)
        cmd = cmd[0]
    env = entry.get("env") or {}
    return {
        "name": name,
        "scope": scope,
        "type": entry.get("type", "stdio"),
        "command": str(cmd) if cmd else "",
        "args": [str(a) for a in args],
        "cwd": str(entry.get("cwd", "")),
        "env_keys": sorted(env.keys()) if isinstance(env, dict) else [],
        "url": str(entry.get("url", "")),
        "source_file": str(src_path),
        "project_root": project_root,
    }


def _load_json_mcp_section(path: Path, key: str) -> dict[str, Any]:
    """Return the MCP dict under *key* in a JSON config, or empty dict."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        logger.debug("Failed to read MCP config %s", path, exc_info=True)
        return {}
    section = data.get(key) if isinstance(data, dict) else None
    return section if isinstance(section, dict) else {}


def _load_toml_mcp_section(path: Path) -> dict[str, Any]:
    """Return ``mcp_servers`` from a Codex TOML config, or empty dict."""
    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        logger.debug("Failed to read TOML MCP config %s", path, exc_info=True)
        return {}
    section = data.get("mcp_servers")
    return section if isinstance(section, dict) else {}


def _collect_mcp_servers(
    project_roots: list[Path],
    user_dir: Path | None,
) -> list[dict[str, Any]]:
    """Scan MCP configs across every active project + every supported agent.

    Each user-scope source uses a distinct scope label (``claude``, ``codex``,
    etc.) so the UI can render them as separate groups under "User Global".
    """
    servers: list[dict[str, Any]] = []

    def _append(entries: dict[str, Any], scope: str, src: Path, root: str) -> None:
        for name, entry in entries.items():
            if not isinstance(entry, dict):
                continue
            row = _mcp_entry(name, entry, scope, src, root)
            if row is not None:
                servers.append(row)

    for root in project_roots:
        src = root / ".mcp.json"
        _append(_load_json_mcp_section(src, "mcpServers"), "project", src, str(root))

    if user_dir is None:
        return servers

    user_sources: list[tuple[str, Path, Callable[[Path], dict[str, Any]]]] = [
        (
            "claude",
            user_dir / ".claude.json",
            lambda p: _load_json_mcp_section(p, "mcpServers"),
        ),
        ("codex", user_dir / ".codex" / "config.toml", _load_toml_mcp_section),
        (
            "gemini",
            user_dir / ".gemini" / "settings.json",
            lambda p: _load_json_mcp_section(p, "mcpServers"),
        ),
        (
            "opencode",
            user_dir / ".config" / "opencode" / "opencode.json",
            lambda p: _load_json_mcp_section(p, "mcp"),
        ),
        (
            "claude_desktop",
            user_dir
            / "Library"
            / "Application Support"
            / "Claude"
            / "claude_desktop_config.json",
            lambda p: _load_json_mcp_section(p, "mcpServers"),
        ),
    ]
    for scope, src, loader in user_sources:
        _append(loader(src), scope, src, scope)

    return servers


def _collect_static_sections(
    active_roots: Iterable[Path] | None = None,
) -> dict[str, Any]:
    """Collect slow-changing system data (skills, sessions, etc.).

    ``active_roots`` may be passed by callers that already scanned the
    registry to avoid a duplicate scan; falls back to ``_active_project_roots()``.
    """
    result: dict[str, Any] = {}

    # Always include the Canvas process's own cwd so the current project is
    # represented even when no agents are running.
    try:
        cwd_root: Path | None = Path.cwd()
    except (OSError, RuntimeError):
        cwd_root = None
    try:
        user_dir: Path | None = Path.home()
    except RuntimeError:
        user_dir = None
    synapse_dir = (user_dir / ".synapse") if user_dir else None

    scanned_roots = (
        list(active_roots) if active_roots is not None else _active_project_roots()
    )
    project_roots = list(
        dict.fromkeys(r for r in (cwd_root, *scanned_roots) if r is not None)
    )

    result["skills"] = _collect_skills(project_roots, user_dir, synapse_dir)
    result["mcp_servers"] = _collect_mcp_servers(project_roots, user_dir)
    # Export the scanned project roots so the UI can render empty rows for
    # projects that have no .mcp.json / skills but were still discovered.
    result["project_roots"] = [str(p) for p in project_roots]

    # Skill Sets
    skill_sets: list[dict[str, Any]] = []
    try:
        from synapse.skills import load_skill_sets

        for name, ss in load_skill_sets().items():
            skill_sets.append(
                {
                    "name": name,
                    "description": ss.description,
                    "skills": ss.skills,
                }
            )
    except OSError:
        logger.debug("Failed to collect skill sets", exc_info=True)
    result["skill_sets"] = skill_sets

    # Sessions
    sessions: list[dict[str, Any]] = []
    try:
        from synapse.session import SessionStore

        sess_store = SessionStore()
        for s in sess_store.list_sessions():
            sessions.append(
                {
                    "name": s.session_name,
                    "scope": s.scope,
                    "agent_count": s.agent_count,
                    "working_dir": s.working_dir or "",
                    "created_at": s.created_at or "",
                }
            )
    except (OSError, RuntimeError):
        logger.debug("Failed to collect sessions", exc_info=True)
    result["sessions"] = sessions

    # Workflows
    workflows: list[dict[str, Any]] = []
    try:
        from synapse.workflow import WorkflowStore

        wf_store = WorkflowStore()
        for wf in wf_store.list_workflows():
            workflows.append(
                {
                    "name": wf.name,
                    "description": wf.description,
                    "scope": wf.scope,
                    "step_count": wf.step_count,
                }
            )
    except (OSError, RuntimeError):
        logger.debug("Failed to collect workflows", exc_info=True)
    result["workflows"] = workflows

    # Environment (SYNAPSE_* env vars)
    environment: dict[str, dict[str, str]] = {}
    try:
        from synapse.settings import DEFAULT_SETTINGS

        default_env = DEFAULT_SETTINGS.get("env", {})
        for key in sorted(default_env.keys()):
            value = os.environ.get(key, "")
            default_val = default_env.get(key, "")
            environment[key] = {
                "value": value
                if value
                else f"(default: {default_val})"
                if default_val
                else "(not set)",
                "description": _ENV_DESCRIPTIONS.get(key, ""),
            }
    except (AttributeError, TypeError):
        logger.debug("Failed to collect environment", exc_info=True)
    result["environment"] = environment

    return result


def _static_cache_roots() -> tuple[Path, Path, Path]:
    """Return stable roots for /api/system cache invalidation."""
    project_dir = Path.cwd()
    try:
        user_dir = Path.home()
    except RuntimeError:
        user_dir = Path(os.environ.get("HOME", "."))
    synapse_dir = user_dir / ".synapse"
    return project_dir, user_dir, synapse_dir


def _extract_tip_text(content: Any) -> str:
    """Extract a displayable tip body from stored Canvas content."""
    parsed = content
    if isinstance(content, str):
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            return content

    if isinstance(parsed, list) and parsed:
        first = parsed[0]
        if isinstance(first, dict):
            body = first.get("body", "")
            return body if isinstance(body, str) else str(body)

    if isinstance(parsed, dict):
        body = parsed.get("body", "")
        if body:
            return body if isinstance(body, str) else str(body)

    return content if isinstance(content, str) else ""


def create_app(db_path: str | None = None) -> FastAPI:
    """Create and configure the Canvas FastAPI app."""
    store = CanvasStore(db_path=db_path)
    _canvas_port = int(os.environ.get("SYNAPSE_CANVAS_PORT", "3000"))
    admin_replies: dict[str, list[dict[str, Any]]] = {}
    _admin_pending_tasks: set[str] = set()
    # Map agent_task_id → pre_task_id for fallback reply correlation
    _admin_task_id_map: dict[str, str] = {}
    _ADMIN_REPLIES_MAX = 200  # Evict oldest entries beyond this limit

    async def _cleanup_loop() -> None:
        """Periodically remove expired cards."""
        while True:
            await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
            removed = store.cleanup_expired()
            if removed:
                logger.info("Auto-cleanup removed %d expired card(s)", removed)

    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
        task = asyncio.create_task(_cleanup_loop())
        yield
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    app = FastAPI(title="Synapse Canvas", lifespan=lifespan)

    # Store reference for access in endpoints
    app.state.store = store
    app.state.canvas_port = _canvas_port
    app.state.admin_replies = admin_replies
    app.state.admin_pending_tasks = _admin_pending_tasks
    app.state.admin_task_id_map = _admin_task_id_map
    app.state.admin_replies_max = _ADMIN_REPLIES_MAX
    app.state._static_cache = {}
    app.state._static_cache_ts = 0.0
    app.state._static_cache_key = None

    # Static files with no-cache headers
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.add_middleware(_NoCacheStaticMiddleware)
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # Compute asset hash from static files + template (detect stale processes)
    _asset_hash = compute_asset_hash()

    # Pre-render HTML with cache-busting (read once at startup, not per-request)
    _cache_version = str(int(time.time()))
    _index_html: str | None = None
    template_path = Path(__file__).parent / "templates" / "index.html"
    if template_path.exists():
        _index_html = template_path.read_text(encoding="utf-8")
        for asset in ("palette.css", *CANVAS_CSS_FILES, *CANVAS_JS_FILES):
            _index_html = _index_html.replace(
                f"/static/{asset}",
                f"/static/{asset}?v={_cache_version}",
            )

    # ----------------------------------------------------------------
    # GET / — Main HTML page
    # ----------------------------------------------------------------
    @app.get("/", response_class=HTMLResponse)
    async def index() -> HTMLResponse:
        if _index_html:
            return HTMLResponse(_index_html, headers={"Cache-Control": "no-store"})
        return HTMLResponse("<h1>Synapse Canvas</h1><p>Template not found.</p>")

    # ----------------------------------------------------------------
    # GET /api/health
    # ----------------------------------------------------------------
    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        return {
            "service": "synapse-canvas",
            "status": "ok",
            "pid": os.getpid(),
            "cards": store.count(),
            "version": __version__,
            "asset_hash": _asset_hash,
        }

    # ----------------------------------------------------------------
    # GET /api/system
    # ----------------------------------------------------------------
    @app.get("/api/system")
    def system_panel() -> dict[str, Any]:
        """Return system panel data (agents, tasks, file locks)."""
        agents: list[dict[str, Any]] = []
        registry_errors: list[dict[str, str]] = []
        worktrees: list[dict[str, str]] = []
        # Capture parsed entries once; reused below for profile discovery.
        registry_entries: list[dict[str, Any]] = []
        for file_path, data in _iter_registry_entries_with_errors():
            if isinstance(data, Exception):
                registry_errors.append(
                    {"source": os.path.basename(file_path), "message": str(data)}
                )
                continue

            registry_entries.append(data)

            working_dir = data.get("working_dir", "")
            worktree_branch = data.get("worktree_branch")
            working_dir_short = os.path.basename(working_dir) if working_dir else ""
            if worktree_branch:
                working_dir_short = f"[WT] {working_dir_short}"

            agents.append(
                {
                    "agent_id": data.get("agent_id", ""),
                    "name": data.get("name", ""),
                    "agent_type": data.get("agent_type", ""),
                    "status": data.get("status", ""),
                    "port": data.get("port"),
                    "pid": data.get("pid"),
                    "role": data.get("role", ""),
                    "skill_set": data.get("skill_set", ""),
                    "working_dir": working_dir_short,
                    "endpoint": data.get("endpoint", ""),
                    "current_task_preview": data.get("current_task_preview", ""),
                    "task_received_at": data.get("task_received_at"),
                    "summary": data.get("summary", ""),
                }
            )

            # Extract worktree info in the same pass
            wt_path = data.get("worktree_path")
            if wt_path:
                worktrees.append(
                    {
                        "agent_id": data.get("agent_id", ""),
                        "agent_name": data.get("name", ""),
                        "path": os.path.basename(wt_path),
                        "branch": data.get("worktree_branch", ""),
                        "base_branch": data.get("worktree_base_branch", ""),
                    }
                )

        file_locks: list[dict[str, str]] = []
        try:
            lock_db: str | None = get_file_safety_db_path()
        except (RuntimeError, OSError, ValueError):
            lock_db = None
        if lock_db and os.path.exists(lock_db):
            try:
                conn = sqlite3.connect(lock_db)
                conn.row_factory = sqlite3.Row
                now = datetime.now(timezone.utc).isoformat()
                rows = conn.execute(
                    "SELECT file_path, agent_id FROM file_locks "
                    "WHERE expires_at > ? ORDER BY locked_at DESC",
                    (now,),
                ).fetchall()
                conn.close()
                for row in rows:
                    file_locks.append(
                        {"path": row["file_path"], "agent_id": row["agent_id"]}
                    )
            except (sqlite3.Error, OSError):
                pass

        # Shared Memory
        memories: list[dict[str, Any]] = []
        try:
            memory_db: str | None = get_shared_memory_db_path()
        except (RuntimeError, OSError, ValueError):
            memory_db = None
        if memory_db and os.path.exists(memory_db):
            try:
                conn = sqlite3.connect(memory_db)
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT id, key, content, author, tags, updated_at "
                    "FROM memories ORDER BY updated_at DESC LIMIT 20"
                ).fetchall()
                conn.close()
                for row in rows:
                    tags_raw = row["tags"] or "[]"
                    try:
                        tags_parsed = json.loads(tags_raw)
                    except (json.JSONDecodeError, TypeError):
                        tags_parsed = []
                    memories.append(
                        {
                            "id": row["id"],
                            "key": row["key"],
                            "content": (row["content"] or "")[:120],
                            "author": row["author"],
                            "tags": tags_parsed,
                            "updated_at": row["updated_at"],
                        }
                    )
            except (sqlite3.Error, OSError):
                pass

        # Recent History
        history: list[dict[str, Any]] = []
        try:
            history_db: str | None = get_history_db_path()
        except (RuntimeError, OSError, ValueError):
            history_db = None
        if history_db and os.path.exists(history_db):
            try:
                conn = sqlite3.connect(history_db)
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT task_id, agent_name, input, status, timestamp "
                    "FROM observations ORDER BY timestamp DESC LIMIT 20"
                ).fetchall()
                conn.close()
                for row in rows:
                    input_text = row["input"] or ""
                    history.append(
                        {
                            "task_id": row["task_id"],
                            "agent_name": row["agent_name"],
                            "input": input_text[:100],
                            "status": row["status"],
                            "timestamp": row["timestamp"],
                        }
                    )
            except (sqlite3.Error, OSError):
                pass

        user_agent_profiles = _read_agent_profiles_from_dir(
            Path(os.path.expanduser("~/.synapse/agents")),
            scope="user",
        )

        active_project_agent_profiles: list[dict[str, str]] = []
        active_project_roots: set[Path] = set()
        seen_active_project_profile_ids: set[str] = set()
        for data in registry_entries:
            project_root = _active_project_root(data)
            if project_root is None or project_root in active_project_roots:
                continue
            active_project_roots.add(project_root)
            active_project_agent_profiles.extend(
                _read_agent_profiles_from_dir(
                    project_root / ".synapse" / "agents",
                    scope="active-project",
                    seen_ids=seen_active_project_profile_ids,
                )
            )

        # Slow-changing sections: use TTL cache to avoid repeated I/O
        now_mono = time.monotonic()
        project_dir, user_dir, synapse_dir = _static_cache_roots()
        cache_key = (
            str(project_dir.resolve()),
            str(user_dir.resolve()),
            str(synapse_dir.resolve()),
        )
        if (
            now_mono - app.state._static_cache_ts > _STATIC_CACHE_TTL
            or not app.state._static_cache
            or app.state._static_cache_key != cache_key
        ):
            app.state._static_cache = _collect_static_sections(
                active_roots=active_project_roots
            )
            app.state._static_cache_key = cache_key
            app.state._static_cache_ts = now_mono

        skills = app.state._static_cache.get("skills", [])
        mcp_servers = app.state._static_cache.get("mcp_servers", [])
        project_roots_payload = app.state._static_cache.get("project_roots", [])
        skill_sets = app.state._static_cache.get("skill_sets", [])
        sessions = app.state._static_cache.get("sessions", [])
        workflows = app.state._static_cache.get("workflows", [])
        environment = app.state._static_cache.get("environment", {})

        # Tips (from Canvas cards tagged "tip")
        tips: list[dict[str, str]] = []
        try:
            tip_cards = store.list_tips()
            for tc in tip_cards:
                tip_text = _extract_tip_text(tc.get("content"))
                if tip_text:
                    tips.append({"card_id": tc["card_id"], "text": tip_text})
        except sqlite3.Error:
            logger.debug("Failed to collect tips", exc_info=True)

        return {
            "agents": agents,
            "file_locks": file_locks,
            "memories": memories,
            "worktrees": worktrees,
            "history": history,
            "user_agent_profiles": user_agent_profiles,
            "active_project_agent_profiles": active_project_agent_profiles,
            "registry_errors": registry_errors,
            "skills": skills,
            "mcp_servers": mcp_servers,
            "project_roots": project_roots_payload,
            "skill_sets": skill_sets,
            "sessions": sessions,
            "workflows": workflows,
            "environment": environment,
            "tips": tips,
            "wiki_enabled": is_wiki_enabled(),
        }

    # ----------------------------------------------------------------
    # GET /api/stream — SSE endpoint
    # ----------------------------------------------------------------
    @app.get("/api/stream")
    async def stream() -> StreamingResponse:
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=100)
        _sse_queues.append(queue)

        async def event_generator() -> AsyncGenerator[str, None]:
            try:
                # Send initial keepalive
                yield ": keepalive\n\n"
                while True:
                    payload = await queue.get()
                    yield payload
            except asyncio.CancelledError:
                pass
            finally:
                _sse_queues.remove(queue)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    app.include_router(cards_router)
    app.include_router(admin_router)
    app.include_router(workflow_router)
    app.include_router(multiagent_router)
    app.include_router(db_router)
    app.include_router(wiki_router)

    return app
