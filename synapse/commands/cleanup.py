"""`synapse cleanup` — kill orphaned spawned agents.

An orphan is a child agent (registered with ``spawned_by``) whose parent
has either been removed from the registry or whose parent PID is no
longer alive. See :meth:`synapse.registry.AgentRegistry.get_orphans`.

This command never touches root agents (no ``spawned_by``) and never
touches children whose parent is still live, so it is safe to run
alongside the existing ``synapse kill`` command without changing its
semantics.
"""

from __future__ import annotations

import argparse
import contextlib
import logging
import os
import signal
import time
from typing import Any

from synapse.registry import AgentRegistry, is_process_running
from synapse.status import READY

logger = logging.getLogger(__name__)

# Env var that opts into opportunistic cleanup of long-READY orphans.
# Value is the idle timeout in seconds; 0 / unset / non-positive = off.
IDLE_TIMEOUT_ENV = "SYNAPSE_ORPHAN_IDLE_TIMEOUT"


def _terminate(pid: int) -> bool:
    """Send SIGTERM to ``pid``. Returns True if the signal was delivered.

    Missing or already-exited processes are treated as success — the
    caller still wants the registry entry cleaned up either way.
    """
    try:
        os.kill(pid, signal.SIGTERM)
        return True
    except ProcessLookupError:
        return True
    except PermissionError:
        logger.warning("event=cleanup_no_permission pid=%s", pid)
        return False
    except OSError as exc:
        logger.warning("event=cleanup_kill_failed pid=%s err=%s", pid, exc)
        return False


def _kill_orphan(registry: AgentRegistry, agent_id: str, info: dict[str, Any]) -> bool:
    """Kill one orphan and unregister it. Returns True on success."""
    pid = info.get("pid")
    if isinstance(pid, int) and pid > 0:
        _terminate(pid)
    # Always unregister so a stale entry can't poison future runs.
    with contextlib.suppress(Exception):
        registry.unregister(agent_id)
    return True


def cmd_cleanup(args: argparse.Namespace) -> None:
    """Entry point for ``synapse cleanup [--dry-run] [<agent>]``."""
    target: str | None = getattr(args, "target", None)
    dry_run: bool = bool(getattr(args, "dry_run", False))
    force: bool = bool(getattr(args, "force", False))

    registry = AgentRegistry()
    orphans = registry.get_orphans()

    # Per-agent target: filter and validate before doing anything.
    if target:
        if target not in orphans:
            print(
                f"Agent {target!r} is not an orphan. "
                "Use `synapse kill` for normal termination."
            )
            raise SystemExit(1)
        orphans = {target: orphans[target]}

    if not orphans:
        print("No orphan agents found. (0 orphans)")
        return

    # Display summary before any destructive action.
    label = "would kill" if dry_run else "killing"
    print(f"Found {len(orphans)} orphan agent(s); {label}:")
    for agent_id, info in sorted(orphans.items()):
        parent_id = info.get("spawned_by", "?")
        pid = info.get("pid", "?")
        status = info.get("status", "?")
        marker = " [dry-run]" if dry_run else ""
        print(
            f"  - {agent_id} (pid={pid}, status={status}, spawned_by={parent_id}){marker}"
        )

    if dry_run:
        print("\nDry-run: no agents were killed. Re-run without --dry-run to kill.")
        return

    # Confirmation prompt unless --force.
    if not force:
        try:
            answer = input(f"Kill {len(orphans)} orphan agent(s)? [y/N]: ")
        except (EOFError, KeyboardInterrupt):
            print("\nAborted.")
            return
        if answer.strip().lower() not in ("y", "yes"):
            print("Aborted.")
            return

    killed = 0
    for agent_id, info in sorted(orphans.items()):
        if _kill_orphan(registry, agent_id, info):
            killed += 1

    print(f"Cleaned up {killed} orphan agent(s).")


def opportunistic_cleanup_idle_orphans(
    agents: dict[str, dict] | None = None,
) -> None:
    """Kill orphans that have been READY longer than the configured idle timeout.

    Controlled by ``SYNAPSE_ORPHAN_IDLE_TIMEOUT`` (seconds). Disabled
    when the env var is unset or non-positive. Intended for callers
    like ``synapse list`` to invoke as a best-effort background sweep —
    it must never raise into its caller's flow.

    Args:
        agents: Optional pre-loaded snapshot from ``registry.list_agents()``;
            callers can pass their own load to avoid an extra registry walk.
    """
    raw = os.environ.get(IDLE_TIMEOUT_ENV)
    try:
        timeout = float(raw) if raw else 0.0
    except ValueError:
        return
    if timeout <= 0:
        return

    registry = AgentRegistry()
    if agents is None:
        agents = registry.list_agents()
    try:
        orphans = registry.get_orphans(agents)
    except Exception:  # broad catch: opportunistic must not crash callers
        logger.exception("event=cleanup_get_orphans_failed")
        return

    now = time.time()
    for agent_id, info in orphans.items():
        if info.get("status") != READY:
            continue
        changed_at = info.get("status_changed_at")
        if not isinstance(changed_at, (int, float)):
            continue
        if (now - changed_at) < timeout:
            continue
        # Defend against a race where the parent came back between the
        # snapshot and now (cheap re-check using the same dict).
        parent_id = info.get("spawned_by")
        if parent_id:
            parent = agents.get(parent_id)
            parent_pid = parent.get("pid") if parent else None
            if isinstance(parent_pid, int) and is_process_running(parent_pid):
                continue
        try:
            _kill_orphan(registry, agent_id, info)
            logger.info(
                "event=opportunistic_orphan_kill agent_id=%s idle_s=%.1f",
                agent_id,
                now - changed_at,
            )
        except Exception:  # broad catch: never crash the host command
            logger.exception(
                "event=opportunistic_orphan_kill_failed agent_id=%s", agent_id
            )
