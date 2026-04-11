"""File-safety command handlers for Synapse CLI."""

from __future__ import annotations

import argparse
import contextlib
import os
import sys
import time
from pathlib import Path

FILE_SAFETY_DISABLED_MSG = (
    "File safety is disabled. Enable with: SYNAPSE_FILE_SAFETY_ENABLED=true"
)


def cmd_file_safety_status(args: argparse.Namespace) -> None:
    """Show file safety statistics."""
    from synapse.file_safety import FileSafetyManager

    manager = FileSafetyManager.from_env()

    if not manager.enabled:
        print(FILE_SAFETY_DISABLED_MSG)
        return

    stats = manager.get_statistics()

    if not stats:
        print("No file safety data found.")
        return

    print("=" * 60)
    print("FILE SAFETY STATISTICS")
    print("=" * 60)
    print()
    print(f"Active Locks:        {stats.get('active_locks', 0)}")
    print(f"Total Modifications: {stats.get('total_modifications', 0)}")
    print()

    by_type = stats.get("by_change_type", {})
    if by_type:
        print("By Change Type:")
        for change_type, count in by_type.items():
            print(f"  {change_type}: {count}")
        print()

    by_agent = stats.get("by_agent", {})
    if by_agent:
        print("By Agent:")
        for agent, count in by_agent.items():
            print(f"  {agent}: {count}")
        print()

    most_modified = stats.get("most_modified_files", [])
    if most_modified:
        print("Most Modified Files:")
        for item in most_modified[:5]:
            print(f"  {item['file_path']}: {item['count']} modifications")


def cmd_file_safety_locks(args: argparse.Namespace) -> None:
    """List active file locks."""
    from synapse.file_safety import FileSafetyManager

    manager = FileSafetyManager.from_env()

    if not manager.enabled:
        print(FILE_SAFETY_DISABLED_MSG)
        return

    locks = manager.list_locks(
        agent_name=getattr(args, "agent", None),
        agent_type=getattr(args, "type", None),
        include_stale=True,
    )

    if not locks:
        print("No active file locks.")
        return

    stale_count = 0
    live_count = 0

    print(
        f"{'File Path':<40} {'Agent':<20} {'PID':<8} {'Status':<8} {'Expires At':<20}"
    )
    print("-" * 100)

    for lock in locks:
        file_path = os.path.basename(lock["file_path"])[:40]
        agent = (lock.get("agent_id") or lock.get("agent_name", "unknown"))[:20]
        pid = lock.get("pid")
        expires = lock["expires_at"][:20] if lock.get("expires_at") else "N/A"

        if pid:
            is_alive = manager._is_process_running(pid)
            status = "LIVE" if is_alive else "STALE"
            if is_alive:
                live_count += 1
            else:
                stale_count += 1
        else:
            status = "UNKNOWN"
            live_count += 1

        pid_str = str(pid) if pid else "-"
        print(f"{file_path:<40} {agent:<20} {pid_str:<8} {status:<8} {expires:<20}")

    print(f"\nTotal: {len(locks)} locks ({live_count} live, {stale_count} stale)")

    if stale_count > 0:
        print(f"\nWarning: {stale_count} stale lock(s) from dead processes detected.")
        print("Run 'synapse file-safety cleanup-locks' to clean them up.")


def _resolve_agent_info(
    agent_name: str,
) -> tuple[str, str | None, int | None]:
    """Resolve agent name to (agent_id, agent_type, pid)."""
    from synapse.registry import AgentRegistry

    agent_id = agent_name
    agent_type = None
    pid = None

    with contextlib.suppress(Exception):
        registry = AgentRegistry()
        agent_info = registry.get_agent(agent_id)

        if not agent_info:
            for aid, info in registry.get_live_agents().items():
                if info.get("agent_type") == agent_id:
                    agent_info = info
                    agent_id = aid
                    break

        if agent_info:
            pid = agent_info.get("pid")
            agent_type = agent_info.get("agent_type")

    if not agent_type and agent_id.startswith("synapse-"):
        parts = agent_id.split("-")
        if len(parts) >= 3:
            agent_type = parts[1]

    return agent_id, agent_type, pid


def cmd_file_safety_lock(args: argparse.Namespace) -> None:
    """Acquire a lock on a file."""
    from synapse.file_safety import FileSafetyManager, LockStatus

    manager = FileSafetyManager.from_env()

    if not manager.enabled:
        print(FILE_SAFETY_DISABLED_MSG)
        return

    agent_id, agent_type, pid = _resolve_agent_info(args.agent)
    wait = getattr(args, "wait", False)
    wait_timeout = getattr(args, "wait_timeout", None)
    wait_interval = getattr(args, "wait_interval", 2.0)
    start_time = time.monotonic()

    while True:
        result = manager.acquire_lock(
            file_path=args.file,
            agent_id=agent_id,
            agent_type=agent_type,
            task_id=getattr(args, "task_id", None),
            duration_seconds=getattr(args, "duration", None),
            intent=getattr(args, "intent", None),
            pid=pid,
        )

        status = result["status"]
        if status == LockStatus.ACQUIRED:
            print(f"Lock acquired on {args.file}")
            print(f"Expires at: {result.get('expires_at')}")
            return
        if status == LockStatus.RENEWED:
            print(f"Lock renewed on {args.file}")
            print(f"New expiration: {result.get('expires_at')}")
            return
        if status == LockStatus.ALREADY_LOCKED:
            if not wait:
                print(
                    f"File is already locked by {result.get('lock_holder')}",
                    file=sys.stderr,
                )
                print(f"Expires at: {result.get('expires_at')}", file=sys.stderr)
                sys.exit(1)
            elapsed = time.monotonic() - start_time
            if wait_timeout is not None and elapsed >= wait_timeout:
                print(f"Timed out waiting for lock on {args.file}")
                sys.exit(1)
            lock_holder = result.get("lock_holder")
            if lock_holder:
                print(f"Waiting for lock on {args.file} (held by {lock_holder})...")
            else:
                print(f"Waiting for lock on {args.file}...")
            if result.get("expires_at"):
                print(f"Current lock expires at: {result.get('expires_at')}")
            if wait_timeout is not None:
                remaining = wait_timeout - elapsed
                sleep_time = min(float(wait_interval), max(0.0, remaining))
            else:
                sleep_time = max(0.0, float(wait_interval))
            time.sleep(sleep_time)
            continue
        if status == LockStatus.FAILED:
            print(
                f"Failed to acquire lock: {result.get('error', 'unknown error')}",
                file=sys.stderr,
            )
            sys.exit(1)
        print(f"Unexpected lock status: {status}", file=sys.stderr)
        sys.exit(1)


def cmd_file_safety_unlock(args: argparse.Namespace) -> None:
    """Release a lock on a file."""
    from synapse.file_safety import FileSafetyManager

    manager = FileSafetyManager.from_env()

    if not manager.enabled:
        print(FILE_SAFETY_DISABLED_MSG)
        return

    force = getattr(args, "force", False)
    agent = getattr(args, "agent", None)

    if not force and not agent:
        print("Error: Agent name is required unless using --force", file=sys.stderr)
        sys.exit(1)

    if force:
        if manager.force_unlock(args.file):
            print(f"Lock force-released on {args.file}")
        else:
            print(f"No lock found for {args.file}")
            sys.exit(1)
    else:
        if manager.release_lock(args.file, str(agent)):
            print(f"Lock released on {args.file}")
        else:
            print(f"No lock found for {args.file} by {agent}")
            sys.exit(1)


def cmd_file_safety_cleanup_locks(args: argparse.Namespace) -> None:
    """Clean up stale locks from dead processes."""
    from synapse.file_safety import FileSafetyManager

    manager = FileSafetyManager.from_env()

    if not manager.enabled:
        print(FILE_SAFETY_DISABLED_MSG)
        return

    stale_locks = manager.get_stale_locks()

    if not stale_locks:
        print("No stale locks found.")
        return

    print(f"Found {len(stale_locks)} stale lock(s) from dead processes:")
    for lock in stale_locks:
        pid = lock.get("pid")
        agent = lock.get("agent_id")
        print(f"  - {lock['file_path']} (pid={pid}, agent={agent})")

    force = getattr(args, "force", False)
    if not force:
        response = input("\nClean up these locks? [y/N]: ").strip().lower()
        if response != "y":
            print("Aborted.")
            return

    cleaned = manager.cleanup_stale_locks()
    print(f"\nCleaned up {cleaned} stale lock(s).")


def cmd_file_safety_history(args: argparse.Namespace) -> None:
    """Show modification history for a file."""
    from synapse.file_safety import FileSafetyManager

    manager = FileSafetyManager.from_env()

    if not manager.enabled:
        print(FILE_SAFETY_DISABLED_MSG)
        return

    history = manager.get_file_history(args.file, limit=args.limit)

    if not history:
        print(f"No modification history found for {args.file}")
        return

    print(f"Modification history for: {args.file}")
    print("=" * 80)

    for mod in history:
        print(f"\n[{mod['timestamp']}] {mod['agent_name']} - {mod['change_type']}")
        if mod.get("intent"):
            print(f"  Intent: {mod['intent']}")
        if mod.get("affected_lines"):
            print(f"  Lines: {mod['affected_lines']}")
        print(f"  Task ID: {mod['task_id']}")


def cmd_file_safety_recent(args: argparse.Namespace) -> None:
    """Show recent file modifications."""
    from synapse.file_safety import FileSafetyManager

    manager = FileSafetyManager.from_env()

    if not manager.enabled:
        print(FILE_SAFETY_DISABLED_MSG)
        return

    mods = manager.get_recent_modifications(
        limit=args.limit,
        agent_name=getattr(args, "agent", None),
    )

    if not mods:
        print("No recent modifications found.")
        return

    print(f"{'Timestamp':<20} {'Agent':<12} {'Type':<8} {'File':<40}")
    print("-" * 80)

    for mod in mods:
        timestamp = mod["timestamp"][:20] if mod.get("timestamp") else "N/A"
        agent = mod["agent_name"][:12]
        change_type = mod["change_type"][:8]
        file_path = mod["file_path"][-40:]
        print(f"{timestamp:<20} {agent:<12} {change_type:<8} {file_path:<40}")

    print(f"\nShowing {len(mods)} recent modifications")


def cmd_file_safety_record(args: argparse.Namespace) -> None:
    """Record a file modification."""
    from synapse.file_safety import FileSafetyManager

    manager = FileSafetyManager.from_env()

    if not manager.enabled:
        print(FILE_SAFETY_DISABLED_MSG)
        return

    record_id = manager.record_modification(
        file_path=args.file_path,
        agent_name=args.agent,
        task_id=args.task_id,
        change_type=args.type,
        intent=args.intent,
    )

    if record_id:
        print(f"Recorded modification (ID: {record_id})")
        print(f"  File: {args.file_path}")
        print(f"  Agent: {args.agent}")
        print(f"  Type: {args.type}")
        if args.intent:
            print(f"  Intent: {args.intent}")
    else:
        print("Failed to record modification")


def cmd_file_safety_cleanup(args: argparse.Namespace) -> None:
    """Clean up old modification records."""
    from synapse.file_safety import FileSafetyManager

    manager = FileSafetyManager.from_env()

    if not manager.enabled:
        print(FILE_SAFETY_DISABLED_MSG)
        return

    if not args.force:
        response = input(
            f"Delete modification records older than {args.days} days? (yes/no): "
        )
        if response.lower() not in ("yes", "y"):
            print("Cancelled.")
            return

    deleted = manager.cleanup_old_modifications(days=args.days)
    print(f"Deleted {deleted} modification records older than {args.days} days")

    expired_locks = manager.cleanup_expired_locks()
    if expired_locks > 0:
        print(f"Cleaned up {expired_locks} expired locks")


def cmd_file_safety_debug(args: argparse.Namespace) -> None:
    """Show debug information for file safety troubleshooting."""
    from synapse.file_safety import FileSafetyManager

    print("=" * 60)
    print("FILE SAFETY DEBUG INFORMATION")
    print("=" * 60)

    print("\n[Environment Variables]")
    env_vars = [
        "SYNAPSE_FILE_SAFETY_ENABLED",
        "SYNAPSE_FILE_SAFETY_RETENTION_DAYS",
        "SYNAPSE_LOG_LEVEL",
    ]
    for var in env_vars:
        value = os.environ.get(var, "(not set)")
        print(f"  {var}: {value}")

    print("\n[Settings Files]")
    settings_paths = [
        Path.cwd() / ".synapse" / "settings.json",
        Path.home() / ".synapse" / "settings.json",
    ]
    for path in settings_paths:
        status = "exists" if path.exists() else "not found"
        print(f"  {path}: {status}")

    print("\n[Database]")
    manager = FileSafetyManager.from_env()
    print(f"  Enabled: {manager.enabled}")
    print(f"  DB Path: {manager.db_path}")
    print(f"  DB Exists: {Path(manager.db_path).exists()}")
    print(f"  Retention Days: {manager.retention_days}")

    if manager.enabled:
        stats = manager.get_statistics()
        print(f"  Active Locks: {stats['active_locks']}")
        print(f"  Total Modifications: {stats['total_modifications']}")

    print("\n[Instruction Files]")
    instruction_files = [
        Path.cwd() / ".synapse" / "file-safety.md",
        Path.home() / ".synapse" / "file-safety.md",
    ]
    for path in instruction_files:
        status = "exists" if path.exists() else "not found"
        print(f"  {path}: {status}")

    print("\n[Log Files]")
    log_dir = Path.home() / ".synapse" / "logs"
    if log_dir.exists():
        log_files = list(log_dir.glob("*.log"))
        if log_files:
            for lf in sorted(log_files)[-5:]:
                print(f"  {lf}")
        else:
            print("  (no log files)")
    else:
        print(f"  Log directory not found: {log_dir}")

    print("\n[Debug Tips]")
    print("  - Enable debug logging: SYNAPSE_LOG_LEVEL=DEBUG synapse ...")
    print("  - Enable file logging: SYNAPSE_LOG_FILE=true synapse ...")
    print("  - View active locks: synapse file-safety locks")
    print("  - View recent mods: synapse file-safety recent")
