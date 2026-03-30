from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request

from synapse.canvas import server as server_module
from synapse.utils import extract_text_from_parts

admin_router = APIRouter()


@admin_router.post("/tasks/send")
@admin_router.post("/tasks/send-priority")
async def admin_receive_reply(request: Request) -> dict[str, Any]:
    """Receive agent replies via the standard A2A callback path."""
    body = await request.json()
    message = body.get("message", {}) or {}
    metadata = body.get("metadata", {}) or {}
    task_id = metadata.get("in_reply_to") or metadata.get("sender_task_id")

    admin_task_id_map = request.app.state.admin_task_id_map
    admin_pending_tasks = request.app.state.admin_pending_tasks
    admin_replies = request.app.state.admin_replies

    if task_id and task_id in admin_task_id_map:
        task_id = admin_task_id_map.pop(task_id)

    if not task_id and len(admin_pending_tasks) == 1:
        task_id = next(iter(admin_pending_tasks))
    elif not task_id and len(admin_pending_tasks) > 1:
        server_module.logger.warning(
            "Reply without correlation and %d pending tasks; cannot determine target",
            len(admin_pending_tasks),
        )

    if not isinstance(task_id, str) or not task_id:
        task_id = str(uuid.uuid4())
        server_module.logger.warning(
            "Reply received without task correlation, using synthetic ID %s",
            task_id[:8],
        )

    parts = message.get("parts", []) if isinstance(message, dict) else []
    raw_output = extract_text_from_parts(parts).strip()
    output = server_module._strip_terminal_junk(raw_output) if raw_output else ""

    sender = metadata.get("sender", {})
    sender_id = sender.get("sender_id", "") if isinstance(sender, dict) else ""
    reply = {
        "task_id": task_id,
        "status": "completed",
        "output": output,
        "sender_id": sender_id,
    }
    admin_replies.setdefault(task_id, []).append(reply)
    server_module._broadcast_event("admin_reply", reply)
    admin_pending_tasks.discard(task_id)

    while len(admin_replies) > request.app.state.admin_replies_max:
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


@admin_router.get("/api/admin/agents")
async def admin_agents() -> dict[str, Any]:
    """Return list of live agents for Admin view."""
    registry_dir = server_module._get_registry_dir()
    agents: list[dict[str, Any]] = []
    if os.path.isdir(registry_dir):
        for file_path in sorted(Path(registry_dir).glob("*.json")):
            try:
                data = json.loads(file_path.read_text(encoding="utf-8"))
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
                    "summary": data.get("summary", ""),
                }
            )
    return {"agents": agents}


@admin_router.post("/api/admin/send")
async def admin_send(request: Request) -> Any:
    """Forward a message to a target agent via A2A protocol."""
    body = await request.json()
    target = body.get("target", "")
    message = body.get("message", "")

    if not target or not message:
        raise HTTPException(status_code=400, detail="target and message are required")

    endpoint = server_module._resolve_agent_endpoint(target)
    if not endpoint:
        raise HTTPException(status_code=404, detail=f"Agent '{target}' not found")

    pre_task_id = str(uuid.uuid4())

    # Register pending task before the HTTP call so that replies arriving
    # before this coroutine resumes can still be correlated.
    request.app.state.admin_pending_tasks.add(pre_task_id)

    a2a_request = {
        "message": {"role": "user", "parts": [{"type": "text", "text": message}]},
        "metadata": {
            "response_mode": "notify",
            "sender": {
                "sender_id": "canvas-admin",
                "sender_name": "Admin",
                "sender_endpoint": (
                    f"http://localhost:{request.app.state.canvas_port}"
                ),
            },
            "sender_task_id": pre_task_id,
        },
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(f"{endpoint}/tasks/send", json=a2a_request)
            resp_data = resp.json()
    except httpx.HTTPError as exc:
        request.app.state.admin_pending_tasks.discard(pre_task_id)
        raise HTTPException(
            status_code=502,
            detail=f"Failed to reach agent: {exc}",
        ) from exc

    task_data = resp_data.get("task", resp_data)
    agent_task_id = task_data.get("id", "")
    status = task_data.get("status", "unknown")
    if isinstance(status, dict):
        status = status.get("state", "unknown")

    if agent_task_id:
        request.app.state.admin_task_id_map[agent_task_id] = pre_task_id

    return {"task_id": pre_task_id, "status": status}


@admin_router.get("/api/admin/replies/{task_id}")
async def admin_replies_poll(task_id: str, request: Request) -> dict[str, Any]:
    """Return stored replies for a task."""
    replies = request.app.state.admin_replies.get(task_id, [])
    if not replies:
        return {"task_id": task_id, "status": "waiting", "output": ""}

    output = "\n\n".join(
        reply.get("output", "") for reply in replies if reply.get("output")
    ).strip()
    return {"task_id": task_id, "status": "completed", "output": output}


@admin_router.get("/api/admin/tasks/{task_id}")
async def admin_task_proxy(task_id: str, target: str | None = None) -> Any:
    """Proxy a task status request to the target agent."""
    if not target:
        raise HTTPException(
            status_code=400, detail="target query parameter is required"
        )

    endpoint = server_module._resolve_agent_endpoint(target)
    if not endpoint:
        raise HTTPException(status_code=404, detail=f"Agent '{target}' not found")

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{endpoint}/tasks/{task_id}")
            resp_data = resp.json()
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to reach agent: {exc}",
        ) from exc

    state = resp_data.get("status", "unknown")
    if isinstance(state, dict):
        state = state.get("state", "unknown")

    output_parts: list[str] = []
    for artifact in resp_data.get("artifacts", []):
        for part in artifact.get("parts", []):
            if part.get("type") == "text" and part.get("text"):
                output_parts.append(part["text"])
        data = artifact.get("data")
        if isinstance(data, dict):
            content = data.get("content", "")
            if content:
                output_parts.append(content)
        elif isinstance(data, str) and data:
            output_parts.append(data)
    output = "\n".join(output_parts)

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
        "output": server_module._strip_terminal_junk(output) if output else "",
        "error": error,
    }


@admin_router.post("/api/admin/start")
async def admin_start() -> dict[str, Any]:
    """Start the administrator agent."""
    return server_module._start_administrator()


@admin_router.post("/api/admin/stop")
async def admin_stop() -> dict[str, Any]:
    """Stop the administrator agent."""
    return server_module._stop_administrator()


@admin_router.post("/api/admin/agents/spawn")
async def admin_spawn_agent(request: Request) -> Any:
    """Spawn a new agent from a profile."""
    body = await request.json()
    profile = body.get("profile", "")
    if not profile:
        raise HTTPException(status_code=400, detail="profile is required")

    name = body.get("name")
    role = body.get("role")
    result = server_module._spawn_agent(profile, name=name, role=role)
    if result.get("status") == "error":
        raise HTTPException(
            status_code=500,
            detail=result.get("detail", "Failed to spawn"),
        )
    return result


@admin_router.delete("/api/admin/agents/{agent_id}")
async def admin_stop_agent(agent_id: str) -> dict[str, Any]:
    """Stop an agent by ID."""
    return server_module._stop_agent(agent_id)


@admin_router.post("/api/admin/jump/{agent_id}")
async def admin_jump_to_agent(agent_id: str) -> dict[str, Any]:
    """Jump to the terminal running the specified agent."""
    from synapse.terminal_jump import jump_to_terminal

    registry_dir = server_module._get_registry_dir()
    agent_file = (Path(registry_dir) / f"{agent_id}.json").resolve()
    if agent_file.parent != Path(registry_dir).resolve():
        return {"ok": False, "error": "Invalid agent_id"}
    if not agent_file.is_file():
        return {"ok": False, "error": f"Agent {agent_id} not found"}
    try:
        agent_info = json.loads(agent_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"ok": False, "error": "Failed to read agent info"}

    success = jump_to_terminal(agent_info)
    if not success:
        tty = agent_info.get("tty_device", "")
        pid = agent_info.get("pid", "")
        return {
            "ok": False,
            "error": f"tty={tty or 'none'}, pid={pid or 'none'}",
        }
    return {"ok": True}
