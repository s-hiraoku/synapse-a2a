"""synapse send-keys: write raw input bytes into a running agent's PTY.

Minimal escape hatch for unsticking agents that are blocked on a TUI dialog
the parent cannot otherwise answer (codex CLI edit-confirmation, model
picker, etc). See issue #695 for context. The command is intentionally
low-level — higher-level wrappers (synapse dialog-respond) can build on
this primitive.
"""

from __future__ import annotations

import argparse
import codecs
import json
import sys
import urllib.error
import urllib.request
from typing import Any

from synapse.registry import AgentRegistry

_TIMEOUT = 5.0


def _resolve_endpoint(target: str) -> str:
    registry = AgentRegistry()
    info = registry.get_agent(target)
    if not info:
        for agent_data in registry.list_agents().values():
            if agent_data.get("name") == target:
                info = agent_data
                break
    if not info:
        print(f"Error: agent '{target}' not found in registry", file=sys.stderr)
        sys.exit(1)
    endpoint = info.get("endpoint")
    if isinstance(endpoint, str) and endpoint:
        return endpoint.rstrip("/")
    port = info.get("port")
    if isinstance(port, int):
        return f"http://localhost:{port}"
    print(f"Error: agent '{target}' has no resolvable endpoint", file=sys.stderr)
    sys.exit(1)


def _decode_data(raw: str, *, escape: bool) -> str:
    if not escape:
        return raw
    try:
        return codecs.decode(raw, "unicode_escape")
    except UnicodeDecodeError as exc:
        print(f"Error: failed to decode escape sequences: {exc}", file=sys.stderr)
        sys.exit(1)


def cmd_send_keys(args: argparse.Namespace) -> None:
    target: str = args.target
    raw: str | None = args.data
    if raw is None and args.enter:
        raw = ""
    if raw is None:
        print(
            "Error: provide DATA positionally or pass --enter",
            file=sys.stderr,
        )
        sys.exit(2)

    text = _decode_data(raw, escape=args.escape)
    submit_seq = "\r" if args.enter else None

    endpoint = _resolve_endpoint(target)
    payload: dict[str, Any] = {"data": text}
    if submit_seq is not None:
        payload["submit_seq"] = submit_seq

    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{endpoint}/pty/write",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            response = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        print(f"Error: HTTP {exc.code} — {detail}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as exc:
        print(f"Error: failed to reach {endpoint}: {exc}", file=sys.stderr)
        sys.exit(1)

    if not response.get("ok"):
        print(f"Error: PTY write reported failure: {response}", file=sys.stderr)
        sys.exit(1)
    if args.json:
        print(json.dumps(response))
    else:
        bytes_written = response.get("bytes_written", len(text))
        print(f"ok: wrote {bytes_written} bytes to {target}")
