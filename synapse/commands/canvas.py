"""Canvas CLI commands — serve, post, shortcuts, list, delete, clear.

All commands work for both agents and humans.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import signal as sig
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

from synapse.canvas.store import CanvasStore
from synapse.registry import AgentRegistry

logger = logging.getLogger(__name__)

DEFAULT_PORT = 3000
CANVAS_SERVICE_ID = "synapse-canvas"
PID_FILE = os.path.expanduser("~/.synapse/canvas.pid")
LOG_FILE = os.path.expanduser("~/.synapse/logs/canvas.log")


def _resolve_agent_name(agent_id: str, agent_name: str = "") -> str:
    """Resolve agent display name from registry unless already provided."""
    if agent_name or not agent_id:
        return agent_name

    info = AgentRegistry().get_agent(agent_id)
    if not info:
        return ""
    return str(info.get("name") or "")


# ============================================================
# PID file management
# ============================================================


def write_pid_file(pid_path: str, pid: int, port: int) -> None:
    """Write PID and port to PID file."""
    os.makedirs(os.path.dirname(pid_path), exist_ok=True)
    Path(pid_path).write_text(json.dumps({"pid": pid, "port": port}))


def read_pid_file(pid_path: str) -> tuple[int | None, int | None]:
    """Read PID and port from PID file. Returns (None, None) if not found."""
    try:
        data = json.loads(Path(pid_path).read_text())
        return data.get("pid"), data.get("port")
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return None, None


def is_pid_alive(pid: int) -> bool:
    """Check if a process with given PID is still running."""
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


# ============================================================
# Server management
# ============================================================


def _poll(
    predicate: Callable[[], bool],
    timeout: float = 3.0,
    interval: float = 0.5,
) -> bool:
    """Poll until predicate returns True or timeout expires."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


def _get_health(port: int) -> dict[str, Any] | None:
    """Get /api/health response or None if unreachable."""
    try:
        resp = httpx.get(f"http://localhost:{port}/api/health", timeout=2.0)
        if resp.status_code == 200:
            data: dict[str, Any] = resp.json()
            return data
    except (httpx.ConnectError, httpx.TimeoutException, ValueError):
        pass
    return None


def is_canvas_server_running(port: int = DEFAULT_PORT) -> bool:
    """Check if Canvas server is running by hitting health endpoint."""
    return _get_health(port) is not None


def ensure_server_running(port: int = DEFAULT_PORT) -> bool:
    """Ensure Canvas server is running. Auto-start if needed.

    Returns True if server is running (or was started successfully).
    Detects and replaces stale Canvas processes automatically.
    """
    health = _get_health(port)
    if health is not None:
        # Server is responding — check for PID mismatch
        pid_file_pid, _ = read_pid_file(PID_FILE)
        health_pid = health.get("pid")
        if pid_file_pid and health_pid and health_pid != pid_file_pid:
            logger.warning(
                "Stale Canvas detected: health PID %d != PID file %d",
                health_pid,
                pid_file_pid,
            )
        return True

    # Check PID file for stale process
    pid_path = PID_FILE
    pid, _ = read_pid_file(pid_path)
    if pid and is_pid_alive(pid):
        # Server process exists but health check failed — give it a moment
        return _poll(lambda: is_canvas_server_running(port))

    # Check for stale process on port before starting
    stale = _detect_stale_canvas(port)
    if stale:
        stale_pid = stale["pid"]
        logger.info("Replacing stale Canvas process (PID: %d)", stale_pid)
        os.kill(stale_pid, sig.SIGTERM)
        _poll(lambda: not is_pid_alive(stale_pid))

    # Auto-start server in background
    logger.info("Canvas server not running. Starting on port %d...", port)
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    log_file = open(LOG_FILE, "a")  # noqa: SIM115
    proc = subprocess.Popen(
        [sys.executable, "-m", "synapse.canvas", "--port", str(port)],
        stdout=log_file,
        stderr=log_file,
        start_new_session=True,
    )
    log_file.close()  # child has its own fd copy
    write_pid_file(pid_path, pid=proc.pid, port=port)

    # Wait for server to become ready
    if _poll(lambda: is_canvas_server_running(port)):
        print(f"Canvas server started on http://localhost:{port}")
        return True

    print(
        f"Warning: Canvas server failed to start. Check logs: {LOG_FILE}",
        file=sys.stderr,
    )
    return False


def _is_synapse_canvas_process(pid: int) -> bool:
    """Check if a PID belongs to a synapse canvas serve process."""
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True,
            text=True,
        )
        cmdline = result.stdout.strip()
        return "synapse.canvas" in cmdline or "synapse canvas" in cmdline
    except (OSError, subprocess.SubprocessError):
        return False


def _detect_stale_canvas(port: int = DEFAULT_PORT) -> dict[str, Any] | None:
    """Detect a stale Canvas process on the given port.

    Returns dict with stale process info (pid, version) or None if port is free.
    """
    health = _get_health(port)
    if health is None:
        return None

    pid = health.get("pid")
    if pid and is_pid_alive(pid) and _is_synapse_canvas_process(pid):
        return {"pid": pid, "version": health.get("version")}
    return None


def canvas_status(port: int = DEFAULT_PORT) -> None:
    """Show Canvas server status with PID mismatch detection."""
    pid_file_pid, stored_port = read_pid_file(PID_FILE)
    health_data = _get_health(port)
    running = health_data is not None

    print("Canvas Server Status")
    print(f"  URL:      http://localhost:{port}")
    print(f"  Running:  {'yes' if running else 'no'}")

    health_pid: int | None = None

    if health_data:
        health_pid = health_data.get("pid")

    if pid_file_pid:
        alive = is_pid_alive(pid_file_pid)
        print(f"  PID:      {pid_file_pid} ({'alive' if alive else 'dead'})")
        if stored_port:
            print(f"  Port:     {stored_port}")
    else:
        print("  PID:      (no PID file)")

    if health_pid and pid_file_pid and health_pid != pid_file_pid:
        print(f"  Health PID: {health_pid}")
        print("  ⚠ MISMATCH: health PID does not match PID file")

    if health_data:
        version = health_data.get("version", "?")
        cards = health_data.get("cards", "?")
        print(f"  Version:  {version}")
        print(f"  Cards:    {cards}")

    print(f"  Log:      {LOG_FILE}")


def canvas_stop(port: int = DEFAULT_PORT) -> None:
    """Stop Canvas server with verification."""
    pid: int | None = None

    # 1) Try health endpoint
    health = _get_health(port)
    if health and health.get("service") == CANVAS_SERVICE_ID:
        pid = health.get("pid")

    # 2) Fall back to PID file
    if not pid:
        stored_pid, stored_port = read_pid_file(PID_FILE)
        if stored_pid and (stored_port is None or stored_port == port):
            pid = stored_pid

    if not pid or not is_pid_alive(pid):
        print("Canvas server is not running.")
        return

    # Verify it's actually a canvas process
    if not _is_synapse_canvas_process(pid):
        print(f"PID {pid} is not a Canvas process. Skipping.")
        return

    # Send SIGTERM and wait for exit
    os.kill(pid, sig.SIGTERM)
    _poll(lambda: not is_pid_alive(pid))

    # Verify port is released
    if is_canvas_server_running(port):
        print(
            f"Warning: port {port} still in use after stopping PID {pid}",
            file=sys.stderr,
        )
    else:
        print(f"Stopped Canvas server (PID: {pid})")

    # Clean up PID file
    with contextlib.suppress(OSError):
        os.remove(PID_FILE)


# ============================================================
# Card posting
# ============================================================


def post_card(
    raw_json: str, db_path: str | None = None, port: int = DEFAULT_PORT
) -> dict | None:
    """Post a raw JSON Canvas message. Returns card dict or None on error."""
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError:
        print("Error: Invalid JSON", file=sys.stderr)
        return None

    from synapse.canvas.protocol import CanvasMessage, validate_message

    msg = CanvasMessage.from_dict(data)
    errors = validate_message(msg)
    if errors:
        print(f"Validation errors: {'; '.join(errors)}", file=sys.stderr)
        return None

    # Autofill agent name from registry if missing
    msg.agent_name = _resolve_agent_name(msg.agent_id, msg.agent_name)

    # Use HTTP API if server is running (ensures SSE broadcast)
    if is_canvas_server_running(port):
        return _post_via_api(msg.to_dict(), port)

    # Fallback: direct DB write (no SSE)
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
        d = {"format": msg.content.format, "body": msg.content.body}
        if msg.content.lang:
            d["lang"] = msg.content.lang
        content_json = json.dumps(d, ensure_ascii=False)

    store = CanvasStore(db_path=db_path)
    if msg.card_id:
        return store.upsert_card(
            card_id=msg.card_id,
            agent_id=msg.agent_id,
            content=content_json,
            title=msg.title,
            agent_name=msg.agent_name or None,
            card_type=msg.type or "render",
            pinned=msg.pinned,
            tags=msg.tags or None,
            template=msg.template,
            template_data=msg.template_data or None,
        )
    return store.add_card(
        agent_id=msg.agent_id,
        content=content_json,
        title=msg.title,
        agent_name=msg.agent_name or None,
        card_type=msg.type or "render",
        pinned=msg.pinned,
        tags=msg.tags or None,
        template=msg.template,
        template_data=msg.template_data or None,
    )


def _post_via_api(payload: dict, port: int = DEFAULT_PORT) -> dict | None:
    """Post a card via the Canvas HTTP API (triggers SSE broadcast)."""
    try:
        resp = httpx.post(
            f"http://localhost:{port}/api/cards",
            json=payload,
            timeout=5.0,
        )
        if resp.status_code in (200, 201):
            result: dict = resp.json()
            return result
        print(f"API error {resp.status_code}: {resp.text}", file=sys.stderr)
        return None
    except (httpx.ConnectError, httpx.TimeoutException) as e:
        print(f"Failed to connect to Canvas server: {e}", file=sys.stderr)
        return None


def post_briefing(
    json_data: str | None = None,
    file_path: str | None = None,
    title: str = "",
    summary: str = "",
    agent_id: str = "",
    agent_name: str = "",
    card_id: str | None = None,
    pinned: bool = False,
    tags: list[str] | None = None,
    db_path: str | None = None,
    port: int = DEFAULT_PORT,
) -> dict | None:
    """Post a briefing card from JSON data or file. Returns card dict or None."""
    if file_path:
        raw = Path(file_path).read_text(encoding="utf-8")
    elif json_data:
        raw = json_data
    else:
        print("Error: No JSON data or file provided", file=sys.stderr)
        return None

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        print("Error: Invalid JSON", file=sys.stderr)
        return None

    # Extract content and sections from the input data
    content_blocks = data.get("content", [])
    sections = data.get("sections", [])
    briefing_title = title or data.get("title", "")
    briefing_summary = summary or data.get("summary", "")

    template_data: dict = {"sections": sections}
    if briefing_summary:
        template_data["summary"] = briefing_summary

    agent_name = _resolve_agent_name(agent_id, agent_name)

    # Build the full Canvas message payload
    payload: dict = {
        "type": "render",
        "content": content_blocks,
        "agent_id": agent_id,
        "title": briefing_title,
        "pinned": pinned,
        "template": "briefing",
        "template_data": template_data,
    }
    if agent_name:
        payload["agent_name"] = agent_name
    if card_id:
        payload["card_id"] = card_id
    if tags:
        payload["tags"] = tags

    # Validate before posting
    from synapse.canvas.protocol import CanvasMessage, validate_message

    msg = CanvasMessage.from_dict(payload)
    errors = validate_message(msg)
    if errors:
        print(f"Validation errors: {'; '.join(errors)}", file=sys.stderr)
        return None

    # Use HTTP API if server is running
    if is_canvas_server_running(port):
        return _post_via_api(payload, port)

    # Fallback: direct DB write
    content_json = json.dumps(content_blocks, ensure_ascii=False)
    store = CanvasStore(db_path=db_path)
    if card_id:
        return store.upsert_card(
            card_id=card_id,
            agent_id=agent_id,
            content=content_json,
            title=briefing_title,
            agent_name=agent_name or None,
            pinned=pinned,
            tags=tags,
            template="briefing",
            template_data=template_data,
        )
    return store.add_card(
        agent_id=agent_id,
        content=content_json,
        title=briefing_title,
        agent_name=agent_name or None,
        pinned=pinned,
        tags=tags,
        template="briefing",
        template_data=template_data,
    )


def post_shortcut(
    format_name: str,
    body: str,
    title: str = "",
    agent_id: str = "",
    agent_name: str = "",
    card_id: str | None = None,
    pinned: bool = False,
    tags: list[str] | None = None,
    lang: str | None = None,
    db_path: str | None = None,
    port: int = DEFAULT_PORT,
    file_path: str | None = None,
) -> dict | None:
    """Post a card via format shortcut. Returns card dict or None."""
    if file_path:
        body = Path(file_path).read_text(encoding="utf-8")
    agent_name = _resolve_agent_name(agent_id, agent_name)
    content_dict: dict = {"format": format_name, "body": body}
    if lang:
        content_dict["lang"] = lang

    payload: dict = {
        "agent_id": agent_id,
        "content": content_dict,
        "title": title,
        "pinned": pinned,
    }
    if agent_name:
        payload["agent_name"] = agent_name
    if card_id:
        payload["card_id"] = card_id
    if tags:
        payload["tags"] = tags

    # Use HTTP API if server is running (ensures SSE broadcast)
    if is_canvas_server_running(port):
        return _post_via_api(payload, port)

    # Fallback: direct DB write (no SSE)
    content_json = json.dumps(content_dict, ensure_ascii=False)
    store = CanvasStore(db_path=db_path)
    if card_id:
        return store.upsert_card(
            card_id=card_id,
            agent_id=agent_id,
            content=content_json,
            title=title,
            agent_name=agent_name or None,
            pinned=pinned,
            tags=tags,
        )
    return store.add_card(
        agent_id=agent_id,
        content=content_json,
        title=title,
        agent_name=agent_name or None,
        pinned=pinned,
        tags=tags,
    )
