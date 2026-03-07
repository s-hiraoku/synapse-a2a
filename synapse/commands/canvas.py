"""Canvas CLI commands — serve, post, shortcuts, list, delete, clear.

All commands work for both agents and humans.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

from synapse.canvas.store import CanvasStore

logger = logging.getLogger(__name__)

DEFAULT_PORT = 3000
PID_FILE = ".synapse/canvas.pid"
LOG_FILE = os.path.expanduser("~/.synapse/logs/canvas.log")


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


def is_canvas_server_running(port: int = DEFAULT_PORT) -> bool:
    """Check if Canvas server is running by hitting health endpoint."""
    try:
        resp = httpx.get(f"http://localhost:{port}/api/health", timeout=2.0)
        return bool(resp.status_code == 200)
    except (httpx.ConnectError, httpx.TimeoutException):
        return False


def ensure_server_running(port: int = DEFAULT_PORT) -> bool:
    """Ensure Canvas server is running. Auto-start if needed.

    Returns True if server is running (or was started successfully).
    """
    if is_canvas_server_running(port):
        return True

    # Check PID file for stale process
    pid_path = PID_FILE
    pid, _ = read_pid_file(pid_path)
    if pid and is_pid_alive(pid):
        # Server process exists but health check failed — give it a moment
        for _ in range(6):
            time.sleep(0.5)
            if is_canvas_server_running(port):
                return True
        return False

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
    write_pid_file(pid_path, pid=proc.pid, port=port)

    # Wait for server to become ready
    for _ in range(6):  # 3 seconds max
        time.sleep(0.5)
        if is_canvas_server_running(port):
            print(f"Canvas server started on http://localhost:{port}")
            return True

    print(
        f"Warning: Canvas server failed to start. Check logs: {LOG_FILE}",
        file=sys.stderr,
    )
    return False


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

    # Use HTTP API if server is running (ensures SSE broadcast)
    if is_canvas_server_running(port):
        return _post_via_api(data, port)

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
            pinned=msg.pinned,
            tags=msg.tags or None,
        )
    return store.add_card(
        agent_id=msg.agent_id,
        content=content_json,
        title=msg.title,
        agent_name=msg.agent_name or None,
        pinned=msg.pinned,
        tags=msg.tags or None,
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
