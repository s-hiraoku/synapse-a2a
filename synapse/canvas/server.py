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
import sqlite3
import time
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from synapse.canvas.protocol import (
    FORMAT_REGISTRY,
    CanvasMessage,
    validate_message,
)
from synapse.canvas.store import CanvasStore

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
    "SYNAPSE_TASK_BOARD_ENABLED": "Enable shared task board for team coordination",
    "SYNAPSE_TASK_BOARD_DB_PATH": "Path to task board SQLite database",
    "SYNAPSE_SHARED_MEMORY_ENABLED": "Enable cross-agent shared memory",
    "SYNAPSE_SHARED_MEMORY_DB_PATH": "Path to shared memory SQLite database",
    "SYNAPSE_LEARNING_MODE_ENABLED": "Enable learning mode instructions for agents",
    "SYNAPSE_LEARNING_MODE_TRANSLATION": "Enable translation in learning mode",
    "SYNAPSE_PROACTIVE_MODE_ENABLED": "Enable proactive collaboration mode",
}


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
        return {"status": "ok", "cards": store.count()}

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

        tasks: dict[str, list[dict[str, Any]]] = {
            "pending": [],
            "in_progress": [],
            "completed": [],
            "failed": [],
        }
        try:
            from synapse.task_board import TaskBoard

            board = TaskBoard.from_env()
            rows = sorted(
                board.list_tasks(),
                key=lambda item: item.get("created_at", ""),
                reverse=True,
            )[:50]
            for row in rows:
                status = row.get("status", "")
                if status not in tasks:
                    continue
                tasks[status].append(
                    {
                        "id": row.get("id", ""),
                        "subject": row.get("subject", ""),
                        "assignee": row.get("assignee") or "",
                        "description": row.get("description", ""),
                        "priority": row.get("priority", 3),
                        "created_by": row.get("created_by", ""),
                        "created_at": row.get("created_at", ""),
                    }
                )
        except Exception:
            logger.debug("Failed to collect tasks", exc_info=True)

        file_locks: list[dict[str, str]] = []
        lock_db = ".synapse/file_safety.db"
        if os.path.exists(lock_db):
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
        memory_db = ".synapse/memory.db"
        if os.path.exists(memory_db):
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
        history_db = ".synapse/history.db"
        if os.path.exists(history_db):
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

        # Saved Agent Profiles
        agent_profiles: list[dict[str, str]] = []
        for scope, profiles_dir in [
            ("user", os.path.expanduser("~/.synapse/agents")),
            ("project", ".synapse/agents"),
        ]:
            if not os.path.isdir(profiles_dir):
                continue
            for file_path in sorted(glob.glob(os.path.join(profiles_dir, "*.agent"))):
                try:
                    profile_data: dict[str, str] = {}
                    for raw_line in (
                        Path(file_path).read_text(encoding="utf-8").splitlines()
                    ):
                        line = raw_line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        key, value = line.split("=", 1)
                        profile_data[key.strip()] = value.strip()
                    agent_profiles.append(
                        {
                            "id": profile_data.get("id", ""),
                            "name": profile_data.get("name", ""),
                            "profile": profile_data.get("profile", ""),
                            "role": profile_data.get("role", ""),
                            "skill_set": profile_data.get("skill_set", ""),
                            "scope": scope,
                        }
                    )
                except OSError:
                    continue

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
            "tasks": tasks,
            "file_locks": file_locks,
            "memories": memories,
            "worktrees": worktrees,
            "history": history,
            "agent_profiles": agent_profiles,
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
    # POST /api/cards — Create or update card
    # ----------------------------------------------------------------
    @app.post("/api/cards", status_code=201, response_model=None)
    async def create_card(request: Request) -> Any:
        body = await request.json()
        msg = CanvasMessage.from_dict(body)

        errors = validate_message(msg)
        if errors:
            raise HTTPException(status_code=422, detail=errors)

        # Serialize content to JSON string for storage
        if isinstance(msg.content, list):
            content_json = json.dumps(
                [
                    {
                        "format": b.format,
                        "body": b.body,
                        **({"lang": b.lang} if b.lang else {}),
                    }
                    for b in msg.content
                ],
                ensure_ascii=False,
            )
        else:
            d: dict[str, Any] = {"format": msg.content.format, "body": msg.content.body}
            if msg.content.lang:
                d["lang"] = msg.content.lang
            content_json = json.dumps(d, ensure_ascii=False)

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

    return app
