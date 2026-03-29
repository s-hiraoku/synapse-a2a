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
import time
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from synapse import __version__
from synapse.canvas import compute_asset_hash
from synapse.canvas.export import MAX_EXPORT_SIZE, export_card
from synapse.canvas.protocol import (
    FORMAT_REGISTRY,
    CanvasMessage,
    validate_message,
)
from synapse.canvas.store import CanvasStore
from synapse.controller import strip_ansi
from synapse.paths import (
    get_file_safety_db_path,
    get_history_db_path,
    get_shared_memory_db_path,
)
from synapse.utils import extract_text_from_parts

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


def _resolve_agent_endpoint(target: str) -> str | None:
    """Resolve an agent target to its HTTP endpoint.

    Searches registry files by agent_id, name, or agent_type.

    Args:
        target: Agent ID, name, or type to resolve.

    Returns:
        HTTP endpoint URL, or None if not found.
    """
    registry_dir = _get_registry_dir()
    if not os.path.isdir(registry_dir):
        return None

    candidates: list[dict[str, Any]] = []
    for file_path in glob.glob(os.path.join(registry_dir, "*.json")):
        try:
            data = json.loads(Path(file_path).read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            continue
        candidates.append(data)

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
    if len(type_matches) == 1:
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


def _collect_static_sections() -> dict[str, Any]:
    """Collect slow-changing system data (skills, sessions, etc.)."""
    result: dict[str, Any] = {}

    # Skills
    skills: list[dict[str, Any]] = []
    try:
        from synapse.skills import discover_skills

        project_dir = Path.cwd()
        user_dir = Path.home()
        synapse_dir = user_dir / ".synapse"

        for sk in discover_skills(
            project_dir=project_dir,
            user_dir=user_dir,
            synapse_dir=synapse_dir,
        ):
            skills.append(
                {
                    "name": sk.name,
                    "description": sk.description,
                    "scope": sk.scope.value
                    if hasattr(sk.scope, "value")
                    else str(sk.scope),
                    "agent_dirs": sk.agent_dirs,
                }
            )
    except Exception:
        logger.debug("Failed to collect skills", exc_info=True)
    result["skills"] = skills

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
    except Exception:
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
    except Exception:
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
    except Exception:
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
    except Exception:
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
        _index_html = _index_html.replace(
            "/static/palette.css", f"/static/palette.css?v={_cache_version}"
        )
        _index_html = _index_html.replace(
            "/static/canvas.css", f"/static/canvas.css?v={_cache_version}"
        )
        _index_html = _index_html.replace(
            "/static/canvas.js", f"/static/canvas.js?v={_cache_version}"
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
        registry_dir = os.path.expanduser("~/.a2a/registry")
        if os.path.isdir(registry_dir):
            for file_path in sorted(glob.glob(os.path.join(registry_dir, "*.json"))):
                try:
                    data = json.loads(Path(file_path).read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
                    registry_errors.append(
                        {"source": os.path.basename(file_path), "message": str(e)}
                    )
                    continue

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
        for file_path in sorted(glob.glob(os.path.join(registry_dir, "*.json"))):
            try:
                data = json.loads(Path(file_path).read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError, UnicodeDecodeError):
                continue
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
            app.state._static_cache = _collect_static_sections()
            app.state._static_cache_key = cache_key
            app.state._static_cache_ts = now_mono

        skills = app.state._static_cache.get("skills", [])
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
        except Exception:
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
            "skill_sets": skill_sets,
            "sessions": sessions,
            "workflows": workflows,
            "environment": environment,
            "tips": tips,
        }

    # ----------------------------------------------------------------
    # POST /api/tips/consume — Consume (delete) a displayed tip
    # ----------------------------------------------------------------
    @app.post("/api/tips/consume")
    async def consume_tip(request: Request) -> dict[str, Any]:
        """Delete a tip card after it has been displayed."""
        body = await request.json()
        card_id = body.get("card_id", "")
        if not card_id:
            raise HTTPException(status_code=400, detail="card_id is required")
        deleted = store.consume_tip(card_id)
        return {"consumed": deleted, "card_id": card_id}

    # ----------------------------------------------------------------
    # Link-preview OGP enrichment
    # ----------------------------------------------------------------
    async def _enrich_link_previews(msg: CanvasMessage) -> None:
        """Enrich link-preview content blocks with OGP metadata."""
        from synapse.canvas.ogp import fetch_ogp

        blocks = msg.content if isinstance(msg.content, list) else [msg.content]
        targets: list[tuple[Any, dict, str]] = []
        for block in blocks:
            if block.format != "link-preview":
                continue
            body = block.body
            if not isinstance(body, dict):
                continue
            url = body.get("url")
            if not url or not isinstance(url, str):
                continue
            if body.get("fetched"):
                continue
            targets.append((block, body, url))

        if not targets:
            return

        results = await asyncio.gather(
            *(fetch_ogp(url) for _, _, url in targets),
            return_exceptions=True,
        )
        for (block, body, _), result in zip(targets, results, strict=True):
            if isinstance(result, BaseException) or not isinstance(result, dict):
                continue
            body.update(result)
            block.body = body

    # ----------------------------------------------------------------
    # POST /api/cards — Create or update card
    # ----------------------------------------------------------------
    @app.post("/api/cards", status_code=201, response_model=None)
    async def create_card(request: Request) -> Any:
        body = await request.json()
        msg = CanvasMessage.from_dict(body)

        errors = validate_message(msg)
        if errors:
            raise HTTPException(status_code=422, detail=errors)

        # Enrich link-preview blocks with OGP metadata
        await _enrich_link_previews(msg)

        # Serialize content to JSON string for storage
        if isinstance(msg.content, list):
            content_json = json.dumps(
                [b.to_dict() for b in msg.content],
                ensure_ascii=False,
            )
        else:
            content_json = json.dumps(msg.content.to_dict(), ensure_ascii=False)

        if msg.card_id:
            # Check if card already exists (for status code decision)
            existing = store.get_card(msg.card_id)

            result = store.upsert_card(
                card_id=msg.card_id,
                agent_id=msg.agent_id,
                content=content_json,
                title=msg.title,
                agent_name=msg.agent_name or None,
                pinned=msg.pinned,
                tags=msg.tags or None,
                template=msg.template,
                template_data=msg.template_data or None,
            )
            if result is None:
                raise HTTPException(
                    status_code=403,
                    detail=f"Card '{msg.card_id}' is owned by a different agent",
                )
            if existing is not None:
                _broadcast_event("card_updated", result)
                return JSONResponse(content=result, status_code=200)
            else:
                _broadcast_event("card_created", result)
                return result
        else:
            # Create new
            result = store.add_card(
                agent_id=msg.agent_id,
                content=content_json,
                title=msg.title,
                agent_name=msg.agent_name or None,
                pinned=msg.pinned,
                tags=msg.tags or None,
                template=msg.template,
                template_data=msg.template_data or None,
            )
            _broadcast_event("card_created", result)
            return result

    # ----------------------------------------------------------------
    # GET /api/cards — List cards
    # ----------------------------------------------------------------
    @app.get("/api/cards")
    async def list_cards(
        agent_id: str | None = None,
        search: str | None = None,
        type: str | None = None,
    ) -> list[dict[str, Any]]:
        return store.list_cards(
            agent_id=agent_id,
            search=search,
            content_type=type,
        )

    # ----------------------------------------------------------------
    # GET /api/cards/{card_id} — Get single card
    # ----------------------------------------------------------------
    @app.get("/api/cards/{card_id}")
    async def get_card(card_id: str) -> dict[str, Any]:
        card = store.get_card(card_id)
        if card is None:
            raise HTTPException(status_code=404, detail="Card not found")
        return card

    # ----------------------------------------------------------------
    # GET /api/cards/{card_id}/download — Download card as file
    # ----------------------------------------------------------------
    @app.get("/api/cards/{card_id}/download")
    async def download_card(card_id: str, format: str | None = None) -> Response:
        card = store.get_card(card_id)
        if card is None:
            raise HTTPException(status_code=404, detail="Card not found")
        content_bytes, filename, content_type = export_card(card, target_format=format)
        if len(content_bytes) > MAX_EXPORT_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"Export too large ({len(content_bytes)} bytes). Maximum is {MAX_EXPORT_SIZE} bytes.",
            )
        return Response(
            content=content_bytes,
            media_type=content_type,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )

    # ----------------------------------------------------------------
    # DELETE /api/cards/{card_id} — Delete card
    # ----------------------------------------------------------------
    @app.delete("/api/cards/{card_id}")
    async def delete_card(card_id: str, request: Request) -> dict[str, str]:
        agent_id = request.headers.get("X-Agent-Id", "")
        card = store.get_card(card_id)
        if card is None:
            raise HTTPException(status_code=404, detail="Card not found")
        if card["agent_id"] != agent_id:
            raise HTTPException(
                status_code=403, detail="Cannot delete another agent's card"
            )
        store.delete_card(card_id, agent_id=agent_id)
        _broadcast_event("card_deleted", {"card_id": card_id})
        return {"deleted": card_id}

    # ----------------------------------------------------------------
    # DELETE /api/cards — Clear cards
    # ----------------------------------------------------------------
    @app.delete("/api/cards")
    async def clear_cards(agent_id: str | None = None) -> dict[str, int]:
        count = store.clear_all(agent_id=agent_id)
        return {"cleared": count}

    # ----------------------------------------------------------------
    # GET /api/formats — List supported formats
    # ----------------------------------------------------------------
    @app.get("/api/formats")
    async def list_formats() -> dict[str, dict[str, Any]]:
        return {
            name: {"body_type": spec.body_type, "sandboxed": spec.sandboxed}
            for name, spec in FORMAT_REGISTRY.items()
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

    @app.post("/tasks/send")
    @app.post("/tasks/send-priority")
    async def admin_receive_reply(request: Request) -> dict[str, Any]:
        """Receive agent replies via the standard A2A callback path.

        Also handles /tasks/send-priority (Synapse extension) since
        a2a_client uses that endpoint by default for priority support.
        """
        body = await request.json()
        message = body.get("message", {}) or {}
        metadata = body.get("metadata", {}) or {}
        task_id = metadata.get("in_reply_to") or metadata.get("sender_task_id")

        # Resolve agent_task_id → pre_task_id via mapping
        if task_id and task_id in _admin_task_id_map:
            task_id = _admin_task_id_map.pop(task_id)

        # Fallback: if still no correlation, pick any pending task
        if not task_id and _admin_pending_tasks:
            task_id = next(iter(_admin_pending_tasks))

        if not isinstance(task_id, str) or not task_id:
            task_id = str(uuid.uuid4())
            logger.warning(
                "Reply received without task correlation, using synthetic ID %s",
                task_id[:8],
            )

        parts = message.get("parts", []) if isinstance(message, dict) else []
        raw_output = extract_text_from_parts(parts).strip()
        # Clean terminal junk that may leak through auto-notify responses
        # (artifact-based replies contain PTY output with ANSI escapes,
        # status bars, and spinner fragments).
        output = _strip_terminal_junk(raw_output) if raw_output else ""

        sender = metadata.get("sender", {})
        sender_id = sender.get("sender_id", "") if isinstance(sender, dict) else ""
        reply = {
            "task_id": task_id,
            "status": "completed",
            "output": output,
            "sender_id": sender_id,
        }
        admin_replies.setdefault(task_id, []).append(reply)
        _broadcast_event("admin_reply", reply)
        _admin_pending_tasks.discard(task_id)

        # Evict oldest entries to prevent unbounded growth
        while len(admin_replies) > _ADMIN_REPLIES_MAX:
            oldest_key = next(iter(admin_replies))
            del admin_replies[oldest_key]

        now = datetime.now(timezone.utc).isoformat()
        return {
            "task": {
                "id": task_id,
                "status": "completed",
                "message": message,
                "artifacts": [],
                "error": None,
                "created_at": now,
                "updated_at": now,
                "context_id": None,
                "metadata": metadata,
            }
        }

    # ----------------------------------------------------------------
    # Admin API — Command Center endpoints
    # ----------------------------------------------------------------

    @app.get("/api/admin/agents")
    async def admin_agents() -> dict[str, Any]:
        """Return list of live agents for Admin view."""
        registry_dir = _get_registry_dir()
        agents: list[dict[str, Any]] = []
        if os.path.isdir(registry_dir):
            for file_path in sorted(glob.glob(os.path.join(registry_dir, "*.json"))):
                try:
                    data = json.loads(Path(file_path).read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError, UnicodeDecodeError):
                    continue
                agents.append(
                    {
                        "agent_id": data.get("agent_id", ""),
                        "name": data.get("name", ""),
                        "agent_type": data.get("agent_type", ""),
                        "status": data.get("status", ""),
                        "port": data.get("port"),
                        "endpoint": data.get("endpoint", ""),
                        "role": data.get("role", ""),
                        "skill_set": data.get("skill_set", ""),
                        "working_dir": data.get("working_dir", ""),
                        "tty_device": data.get("tty_device", ""),
                    }
                )
        return {"agents": agents}

    @app.post("/api/admin/send")
    async def admin_send(request: Request) -> Any:
        """Forward a message to a target agent via A2A protocol."""
        body = await request.json()
        target = body.get("target", "")
        message = body.get("message", "")

        if not target or not message:
            raise HTTPException(
                status_code=400, detail="target and message are required"
            )

        endpoint = _resolve_agent_endpoint(target)
        if not endpoint:
            raise HTTPException(status_code=404, detail=f"Agent '{target}' not found")

        # Build A2A SendMessageRequest with sender info so the agent
        # knows this comes from the Admin Command Center (human operator)
        # Pre-generate a task ID so we can include it as sender_task_id.
        # This lets the agent's reply include in_reply_to for correlation.
        pre_task_id = str(uuid.uuid4())

        a2a_request = {
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": message}],
            },
            "metadata": {
                "response_mode": "notify",
                "sender": {
                    "sender_id": "canvas-admin",
                    "sender_name": "Admin",
                    "sender_endpoint": f"http://localhost:{_canvas_port}",
                },
                "sender_task_id": pre_task_id,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{endpoint}/tasks/send",
                    json=a2a_request,
                )
                resp_data = resp.json()
        except httpx.HTTPError as e:
            raise HTTPException(
                status_code=502, detail=f"Failed to reach agent: {e}"
            ) from e

        # SendMessageResponse wraps task in {"task": {...}}
        task_data = resp_data.get("task", resp_data)
        agent_task_id = task_data.get("id", "")
        status = task_data.get("status", "unknown")
        if isinstance(status, dict):
            status = status.get("state", "unknown")

        # Use pre_task_id as the canonical admin task_id.
        # The agent's reply will include in_reply_to=pre_task_id
        # (from sender_task_id in metadata), so the frontend polls
        # for replies using this same ID.
        _admin_pending_tasks.add(pre_task_id)
        # Map agent_task_id → pre_task_id for fallback correlation
        if agent_task_id:
            _admin_task_id_map[agent_task_id] = pre_task_id

        return {"task_id": pre_task_id, "status": status}

    @app.get("/api/admin/replies/{task_id}")
    async def admin_replies_poll(task_id: str) -> dict[str, Any]:
        """Return stored replies for a task."""
        replies = admin_replies.get(task_id, [])
        if not replies:
            return {"task_id": task_id, "status": "waiting", "output": ""}

        output = "\n\n".join(
            reply.get("output", "") for reply in replies if reply.get("output")
        ).strip()
        return {"task_id": task_id, "status": "completed", "output": output}

    @app.get("/api/admin/tasks/{task_id}")
    async def admin_task_proxy(task_id: str, target: str | None = None) -> Any:
        """Proxy a task status request to the target agent."""
        if not target:
            raise HTTPException(
                status_code=400, detail="target query parameter is required"
            )

        endpoint = _resolve_agent_endpoint(target)
        if not endpoint:
            raise HTTPException(status_code=404, detail=f"Agent '{target}' not found")

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(f"{endpoint}/tasks/{task_id}")
                resp_data = resp.json()
        except httpx.HTTPError as e:
            raise HTTPException(
                status_code=502, detail=f"Failed to reach agent: {e}"
            ) from e

        # Extract status — A2A Task.status is a plain string, not an object
        state = resp_data.get("status", "unknown")
        if isinstance(state, dict):
            state = state.get("state", "unknown")

        # Extract text from all artifacts
        # Format varies: [{parts: [{type, text}]}] or [{type, data: {content}}]
        output_parts: list[str] = []
        for artifact in resp_data.get("artifacts", []):
            # Format 1: {parts: [{type: "text", text: "..."}]}
            for part in artifact.get("parts", []):
                if part.get("type") == "text" and part.get("text"):
                    output_parts.append(part["text"])
            # Format 2: {type: "text", data: {content: "..."}} or data as string
            data = artifact.get("data")
            if isinstance(data, dict):
                content = data.get("content", "")
                if content:
                    output_parts.append(content)
            elif isinstance(data, str) and data:
                output_parts.append(data)
        output = "\n".join(output_parts)

        # Also check message for output (fallback when no artifacts)
        msg = resp_data.get("message")
        if msg and not output:
            for part in msg.get("parts", []):
                if part.get("type") == "text":
                    output += part.get("text", "")

        error = None
        if resp_data.get("error"):
            err = resp_data["error"]
            error = err.get("message", str(err)) if isinstance(err, dict) else str(err)

        return {
            "task_id": task_id,
            "status": state,
            "output": _strip_terminal_junk(output) if output else "",
            "error": error,
        }

    @app.post("/api/admin/start")
    async def admin_start() -> dict[str, Any]:
        """Start the administrator agent."""
        return _start_administrator()

    @app.post("/api/admin/stop")
    async def admin_stop() -> dict[str, Any]:
        """Stop the administrator agent."""
        return _stop_administrator()

    @app.post("/api/admin/agents/spawn")
    async def admin_spawn_agent(request: Request) -> Any:
        """Spawn a new agent from a profile."""
        body = await request.json()
        profile = body.get("profile", "")
        if not profile:
            raise HTTPException(status_code=400, detail="profile is required")

        name = body.get("name")
        role = body.get("role")
        result = _spawn_agent(profile, name=name, role=role)
        if result.get("status") == "error":
            raise HTTPException(
                status_code=500, detail=result.get("detail", "Failed to spawn")
            )
        return result

    @app.delete("/api/admin/agents/{agent_id}")
    async def admin_stop_agent(agent_id: str) -> dict[str, Any]:
        """Stop an agent by ID."""
        return _stop_agent(agent_id)

    @app.post("/api/admin/jump/{agent_id}")
    async def admin_jump_to_agent(agent_id: str) -> dict[str, Any]:
        """Jump to the terminal running the specified agent."""
        from synapse.terminal_jump import jump_to_terminal

        registry_dir = _get_registry_dir()
        agent_file = os.path.join(registry_dir, f"{agent_id}.json")
        if not os.path.isfile(agent_file):
            return {"ok": False, "error": f"Agent {agent_id} not found"}
        try:
            agent_info = json.loads(Path(agent_file).read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"ok": False, "error": "Failed to read agent info"}

        # jump_to_terminal enriches agent_info with resolved tty_device
        success = jump_to_terminal(agent_info)
        if not success:
            # Report agent-level info (tty may have been resolved by jump_to_terminal)
            tty = agent_info.get("tty_device", "")
            pid = agent_info.get("pid", "")
            return {
                "ok": False,
                "error": f"tty={tty or 'none'}, pid={pid or 'none'}",
            }
        return {"ok": True}

    # ── Workflow endpoints ────────────────────────────────────
    def _workflow_to_dict(wf: Any) -> dict[str, Any]:
        """Serialize a Workflow to a JSON-friendly dict."""
        return {
            "name": wf.name,
            "description": wf.description,
            "scope": wf.scope,
            "step_count": wf.step_count,
            "steps": [
                {
                    "target": s.target,
                    "message": s.message,
                    "priority": s.priority,
                    "response_mode": s.response_mode,
                }
                for s in wf.steps
            ],
        }

    @app.get("/api/workflow")
    async def workflow_list() -> dict[str, Any]:
        """List all workflows with full step details."""
        from synapse.workflow import WorkflowStore

        workflows: list[dict[str, Any]] = []
        try:
            store = WorkflowStore()
            for wf in store.list_workflows():
                workflows.append(_workflow_to_dict(wf))
        except Exception:
            logger.debug("Failed to list workflows", exc_info=True)
        project_dir = str(Path.cwd())
        return {"workflows": workflows, "project_dir": project_dir}

    @app.post("/api/workflow/run/{name}")
    async def workflow_run(name: str, request: Request) -> dict[str, Any]:
        """Start a workflow execution."""
        from synapse.workflow import WorkflowStore
        from synapse.workflow_runner import run_workflow

        store = WorkflowStore()
        wf = store.load(name)
        if wf is None:
            raise HTTPException(status_code=404, detail=f"Workflow '{name}' not found")

        body: dict[str, Any] = {}
        with contextlib.suppress(Exception):
            body = await request.json()
        continue_on_error = body.get("continue_on_error", False)
        sender_info = {
            "sender_id": "canvas-workflow",
            "sender_name": "Workflow",
            "sender_endpoint": f"http://localhost:{_canvas_port}",
        }

        run_id = await run_workflow(
            wf,
            on_update=lambda: _broadcast_event("workflow_update", {}),
            continue_on_error=continue_on_error,
            sender_info=sender_info,
        )
        return {"run_id": run_id, "status": "running"}

    @app.get("/api/workflow/runs")
    async def workflow_runs_list() -> dict[str, Any]:
        """List active and recent workflow runs."""
        from synapse.workflow_runner import get_runs

        return {"runs": [r.to_dict() for r in get_runs()]}

    @app.get("/api/workflow/runs/{run_id}")
    async def workflow_run_status(run_id: str) -> dict[str, Any]:
        """Get the status of a specific workflow run."""
        from synapse.workflow_runner import get_run

        run = get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
        return run.to_dict()

    @app.get("/api/workflow/{name}")
    async def workflow_get(name: str) -> dict[str, Any]:
        """Get a single workflow by name."""
        from synapse.workflow import WorkflowStore

        store = WorkflowStore()
        wf = store.load(name)
        if wf is None:
            raise HTTPException(status_code=404, detail=f"Workflow '{name}' not found")
        return _workflow_to_dict(wf)

    # ── DB Browser endpoints ────────────────────────────────

    def _get_synapse_dir() -> str:
        return os.environ.get("SYNAPSE_DIR", os.path.join(os.getcwd(), ".synapse"))

    def _list_databases() -> list[dict[str, Any]]:
        synapse_dir = _get_synapse_dir()
        dbs: list[dict[str, Any]] = []
        if not os.path.isdir(synapse_dir):
            return dbs
        _hidden_dbs = {"task_board.db"}
        for f in sorted(os.listdir(synapse_dir)):
            if f.endswith(".db") and f not in _hidden_dbs:
                path = os.path.join(synapse_dir, f)
                try:
                    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as conn:
                        tables = [
                            r[0]
                            for r in conn.execute(
                                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                            )
                        ]
                    size = os.path.getsize(path)
                    dbs.append(
                        {"name": f, "path": path, "tables": tables, "size": size}
                    )
                except Exception:
                    continue
        return dbs

    @app.get("/api/db/list")
    async def db_list() -> list[dict[str, Any]]:
        """List all SQLite databases in .synapse/."""
        return _list_databases()

    @app.get("/api/db/{db_name}/{table_name}")
    async def db_query(
        db_name: str,
        table_name: str,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Query rows from a table in a Synapse database (read-only)."""
        if not db_name.endswith(".db"):
            raise HTTPException(status_code=400, detail="Invalid database name")
        # Sanitize table name to prevent injection
        if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", table_name):
            raise HTTPException(status_code=400, detail="Invalid table name")
        synapse_dir = _get_synapse_dir()
        db_path = os.path.join(synapse_dir, db_name)
        if not os.path.isfile(db_path):
            raise HTTPException(
                status_code=404, detail=f"Database '{db_name}' not found"
            )
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            with conn:
                # Get column info
                cols = [
                    r[1]
                    for r in conn.execute(f"PRAGMA table_info({table_name})")  # noqa: S608
                ]
                if not cols:
                    raise HTTPException(
                        status_code=404, detail=f"Table '{table_name}' not found"
                    )
                # Count total rows
                total = conn.execute(
                    f"SELECT COUNT(*) FROM {table_name}"  # noqa: S608
                ).fetchone()[0]
                # Fetch rows
                rows = [
                    dict(r)
                    for r in conn.execute(
                        f"SELECT * FROM {table_name} LIMIT ? OFFSET ?",  # noqa: S608
                        (min(limit, 500), offset),
                    )
                ]
            return {
                "db": db_name,
                "table": table_name,
                "columns": cols,
                "rows": rows,
                "total": total,
                "limit": min(limit, 500),
                "offset": offset,
            }
        except sqlite3.OperationalError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    return app
