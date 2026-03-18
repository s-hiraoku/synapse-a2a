"""Opt-in live E2E tests against real agent CLIs.

These tests are intentionally skipped unless explicitly enabled because they
require locally installed/authenticated agent binaries and network access.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import time
from contextlib import closing
from pathlib import Path

import pytest
import requests

LIVE_E2E_ENV = "SYNAPSE_LIVE_E2E"
LIVE_E2E_PROFILES_ENV = "SYNAPSE_LIVE_E2E_PROFILES"
PROFILES = ("claude", "codex", "gemini", "opencode", "copilot")
SEND_TIMEOUT_SECONDS = 180
STARTUP_TIMEOUT_SECONDS = 90
POLL_INTERVAL_SECONDS = 1.0


def _live_e2e_enabled() -> bool:
    return os.environ.get(LIVE_E2E_ENV, "").lower() in {"1", "true", "yes"}


def _selected_profiles() -> set[str]:
    raw = os.environ.get(LIVE_E2E_PROFILES_ENV, "")
    if not raw.strip():
        return set(PROFILES)
    return {part.strip() for part in raw.split(",") if part.strip()}


def _require_live_profile(profile: str) -> None:
    if not _live_e2e_enabled():
        pytest.skip(f"set {LIVE_E2E_ENV}=1 to run live agent E2E tests")
    if profile not in _selected_profiles():
        pytest.skip(
            f"{profile} not selected in {LIVE_E2E_PROFILES_ENV} "
            f"(enabled: {sorted(_selected_profiles())})"
        )
    if shutil.which(profile) is None:
        # In CI (SYNAPSE_LIVE_E2E=1), a missing CLI is a real failure —
        # the workflow must install it.  Locally, skip gracefully.
        if os.environ.get("CI", "").lower() in {"true", "1"}:
            pytest.fail(
                f"CLI '{profile}' not found on PATH — the workflow must "
                f"install it before running tests"
            )
        pytest.skip(f"required CLI '{profile}' is not installed on PATH")


def _pick_free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return int(sock.getsockname()[1])


def _wait_for_server(port: int, timeout: float) -> None:
    deadline = time.time() + timeout
    url = f"http://127.0.0.1:{port}/.well-known/agent.json"
    last_error: str | None = None
    while time.time() < deadline:
        try:
            response = requests.get(url, timeout=2)
            if response.status_code == 200:
                return
            last_error = f"unexpected status {response.status_code}"
        except requests.RequestException as exc:
            last_error = str(exc)
        time.sleep(POLL_INTERVAL_SECONDS)
    raise AssertionError(f"agent server on port {port} did not start: {last_error}")


def _send_task(port: int, token: str) -> str:
    payload = {
        "message": {
            "role": "user",
            "parts": [
                {
                    "type": "text",
                    "text": (f"Reply with the exact token {token} and nothing else."),
                }
            ],
        },
        "metadata": {"response_mode": "silent"},
    }
    url = f"http://127.0.0.1:{port}/tasks/send"
    deadline = time.time() + SEND_TIMEOUT_SECONDS
    last_error: str | None = None
    while time.time() < deadline:
        try:
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                body = response.json()
                return str(body["task"]["id"])
            if response.status_code == 503:
                last_error = response.text
                time.sleep(POLL_INTERVAL_SECONDS)
                continue
            raise AssertionError(
                f"unexpected send status {response.status_code}: {response.text}"
            )
        except requests.RequestException as exc:
            last_error = str(exc)
            time.sleep(POLL_INTERVAL_SECONDS)
    raise AssertionError(f"send did not succeed before timeout: {last_error}")


def _wait_for_task_completion(port: int, task_id: str, token: str) -> dict:
    url = f"http://127.0.0.1:{port}/tasks/{task_id}"
    deadline = time.time() + SEND_TIMEOUT_SECONDS
    last_payload: dict | None = None
    while time.time() < deadline:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        payload = response.json()
        last_payload = payload
        if payload.get("status") in {"completed", "failed", "canceled", "rejected"}:
            serialized = json.dumps(payload, ensure_ascii=False)
            assert payload["status"] == "completed", serialized
            assert token in serialized, serialized
            return payload
        time.sleep(POLL_INTERVAL_SECONDS)
    raise AssertionError(
        "task did not complete before timeout: "
        f"{json.dumps(last_payload, ensure_ascii=False) if last_payload else 'no data'}"
    )


def _terminate_process(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return

    try:
        proc.send_signal(signal.SIGINT)
        proc.wait(timeout=10)
        return
    except subprocess.TimeoutExpired:
        pass

    proc.terminate()
    try:
        proc.wait(timeout=5)
        return
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


@pytest.mark.live_e2e
@pytest.mark.parametrize("profile", PROFILES)
def test_live_agent_round_trip(profile: str, tmp_path: Path) -> None:
    """A live agent should accept a task and return the requested token."""
    _require_live_profile(profile)

    port = _pick_free_port()
    token = f"SYNAPSE_E2E_OK_{profile.upper()}_{int(time.time())}"
    proc = subprocess.Popen(
        [
            "synapse",
            profile,
            "--port",
            str(port),
            "--headless",
            "--no-setup",
        ],
        cwd=tmp_path,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        _wait_for_server(port, STARTUP_TIMEOUT_SECONDS)
        task_id = _send_task(port, token)
        task = _wait_for_task_completion(port, task_id, token)
        assert task["id"] == task_id
    finally:
        _terminate_process(proc)
