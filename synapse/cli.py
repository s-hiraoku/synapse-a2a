#!/usr/bin/env python3
"""Synapse A2A CLI - Main entry point for agent management."""

from __future__ import annotations

import argparse
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from synapse.history import HistoryManager

from synapse.a2a_client import get_client
from synapse.auth import generate_api_key
from synapse.commands.list import ListCommand
from synapse.commands.start import StartCommand
from synapse.controller import TerminalController
from synapse.delegation import (
    get_delegate_instructions_path,
    load_delegate_instructions,
)
from synapse.port_manager import PORT_RANGES, PortManager, is_process_alive
from synapse.registry import AgentRegistry, is_port_open

# Known profiles (for shortcut detection)
KNOWN_PROFILES = set(PORT_RANGES.keys())


def install_skills() -> None:
    """Install Synapse A2A skills to ~/.claude/skills/ and copy to ~/.codex/skills/."""
    try:
        import synapse

        package_dir = Path(synapse.__file__).parent
        skills_to_install = ["synapse-a2a", "delegation"]

        for skill_name in skills_to_install:
            claude_target = Path.home() / ".claude" / "skills" / skill_name

            # Skip if already installed in .claude
            if claude_target.exists():
                # Still try to copy to .codex if not present
                _copy_skill_to_codex(claude_target, skill_name)
                continue

            source_dir = package_dir / "skills" / skill_name

            if source_dir.exists():
                claude_target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(source_dir, claude_target)
                print(
                    f"\x1b[32m[Synapse]\x1b[0m Installed {skill_name} skill to {claude_target}"
                )
                # Copy to .codex as well
                _copy_skill_to_codex(claude_target, skill_name)
    except Exception:
        # Silently ignore installation errors
        pass


def _copy_skill_to_codex(source_dir: Path, skill_name: str) -> None:
    """Copy a skill from .claude to .codex (Codex doesn't support plugins)."""
    try:
        codex_target = Path.home() / ".codex" / "skills" / skill_name
        if codex_target.exists():
            return
        codex_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source_dir, codex_target)
        print(f"\x1b[32m[Synapse]\x1b[0m Copied {skill_name} skill to {codex_target}")
    except Exception:
        # Silently ignore copy errors
        pass


_START_COMMAND = StartCommand(subprocess_module=subprocess)


def cmd_start(args: argparse.Namespace) -> None:
    """Start an agent in background or foreground."""
    _START_COMMAND.run(args)


def _stop_agent(registry: AgentRegistry, info: dict) -> None:
    """Stop a single agent given its info dict."""
    agent_id = info.get("agent_id")
    pid = info.get("pid")

    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
            print(f"Stopped {agent_id} (PID: {pid})")
            if isinstance(agent_id, str):
                registry.unregister(agent_id)
        except ProcessLookupError:
            print(f"Process {pid} not found. Cleaning up registry...")
            if isinstance(agent_id, str):
                registry.unregister(agent_id)
    else:
        print(f"No PID found for {agent_id}")


def cmd_stop(args: argparse.Namespace) -> None:
    """Stop a running agent."""
    profile = args.profile
    registry = AgentRegistry()
    port_manager = PortManager(registry)

    running = port_manager.get_running_instances(profile)

    if not running:
        print(f"No running agent found for profile: {profile}")
        sys.exit(1)

    # If --all flag is set, stop all instances
    if getattr(args, "all", False):
        for info in running:
            _stop_agent(registry, info)
        return

    # If multiple instances, show list and stop the oldest (first)
    if len(running) == 1:
        target = running[0]
    else:
        print(f"Multiple {profile} instances running:")
        for i, info in enumerate(running):
            print(f"  [{i}] {info['agent_id']} (PID: {info.get('pid', '?')})")
        target = running[0]
        print(f"Stopping {target['agent_id']} (use --all to stop all)")

    _stop_agent(registry, target)


def _clear_screen() -> None:
    """Clear terminal screen (cross-platform)."""
    os.system("cls" if os.name == "nt" else "clear")


def cmd_list(args: argparse.Namespace) -> None:
    """List running agents (with optional watch mode)."""
    list_command = ListCommand(
        AgentRegistry,
        is_process_alive,
        is_port_open,
        _clear_screen,
        time,
        print,
    )
    list_command.run(args)


def cmd_logs(args: argparse.Namespace) -> None:
    """Show logs for an agent."""
    profile = args.profile
    log_file = os.path.expanduser(f"~/.synapse/logs/{profile}.log")

    if not os.path.exists(log_file):
        print(f"No logs found for {profile}")
        sys.exit(1)

    if args.follow:
        # Follow mode (like tail -f)
        subprocess.run(["tail", "-f", log_file])
    else:
        # Show last N lines
        subprocess.run(["tail", "-n", str(args.lines), log_file])


# ============================================================
# History Commands
# ============================================================


def _get_history_manager() -> HistoryManager:
    """Get HistoryManager with settings env applied.

    Applies env settings from .synapse/settings.json before checking
    SYNAPSE_HISTORY_ENABLED environment variable.
    """
    from synapse.history import HistoryManager
    from synapse.settings import get_settings

    # Apply settings env to os.environ
    settings = get_settings()
    env_dict = dict(os.environ)
    settings.apply_env(env_dict)
    os.environ.update(env_dict)

    db_path = str(Path.home() / ".synapse" / "history" / "history.db")
    return HistoryManager.from_env(db_path=db_path)


def cmd_history_list(args: argparse.Namespace) -> None:
    """List task history."""
    manager = _get_history_manager()

    if not manager.enabled:
        print("History is disabled. Enable with: SYNAPSE_HISTORY_ENABLED=true")
        return

    observations = manager.list_observations(
        limit=args.limit, agent_name=args.agent if args.agent else None
    )

    if not observations:
        print("No task history found.")
        return

    # Print table header
    print(
        f"{'Task ID':<36} {'Agent':<10} {'Status':<12} {'Timestamp':<19} {'Input (first 40 chars)':<42}"
    )
    print("-" * 119)

    # Print each observation
    for obs in observations:
        task_id = obs["task_id"][:36]
        agent = obs["agent_name"][:10]
        status = obs["status"][:12]
        timestamp = obs["timestamp"][:19] if obs["timestamp"] else "N/A"
        input_preview = (
            obs["input"][:40].replace("\n", " ") if obs["input"] else "(empty)"
        )
        print(
            f"{task_id:<36} {agent:<10} {status:<12} {timestamp:<19} {input_preview:<42}"
        )

    print(f"\nShowing {len(observations)} entries (limit: {args.limit})")
    if args.agent:
        print(f"Filtered by agent: {args.agent}")


def cmd_history_show(args: argparse.Namespace) -> None:
    """Show detailed task information."""
    import json

    manager = _get_history_manager()

    if not manager.enabled:
        print("History is disabled. Enable with: SYNAPSE_HISTORY_ENABLED=true")
        return

    observation = manager.get_observation(args.task_id)

    if not observation:
        print(f"Task not found: {args.task_id}")
        sys.exit(1)

    # Print task details
    print(f"Task ID:        {observation['task_id']}")
    print(f"Agent:          {observation['agent_name']}")
    print(f"Status:         {observation['status']}")
    print(f"Session ID:     {observation['session_id']}")
    print(f"Timestamp:      {observation['timestamp']}")

    print("\n" + "=" * 80)
    print("INPUT:")
    print("=" * 80)
    print(observation["input"] or "(empty)")

    print("\n" + "=" * 80)
    print("OUTPUT:")
    print("=" * 80)
    print(observation["output"] or "(empty)")

    if observation.get("metadata"):
        print("\n" + "=" * 80)
        print("METADATA:")
        print("=" * 80)
        print(json.dumps(observation["metadata"], indent=2))


def cmd_history_search(args: argparse.Namespace) -> None:
    """Search task history by keywords."""
    manager = _get_history_manager()

    if not manager.enabled:
        print("History is disabled. Enable with: SYNAPSE_HISTORY_ENABLED=true")
        return

    observations = manager.search_observations(
        keywords=args.keywords,
        logic=args.logic,
        case_sensitive=args.case_sensitive,
        limit=args.limit,
        agent_name=args.agent if args.agent else None,
    )

    if not observations:
        print(f"No matches found for: {', '.join(args.keywords)}")
        return

    # Print table header
    print(
        f"{'Task ID':<36} {'Agent':<10} {'Status':<12} {'Timestamp':<19} {'Input (first 40 chars)':<42}"
    )
    print("-" * 119)

    # Print each observation
    for obs in observations:
        task_id = obs["task_id"][:36]
        agent = obs["agent_name"][:10]
        status = obs["status"][:12]
        timestamp = obs["timestamp"][:19] if obs["timestamp"] else "N/A"
        input_preview = (
            obs["input"][:40].replace("\n", " ") if obs["input"] else "(empty)"
        )
        print(
            f"{task_id:<36} {agent:<10} {status:<12} {timestamp:<19} {input_preview:<42}"
        )

    print(f"\nFound {len(observations)} matches")
    print(f"Keywords: {', '.join(args.keywords)} (logic: {args.logic})")
    if args.agent:
        print(f"Filtered by agent: {args.agent}")


def cmd_history_cleanup(args: argparse.Namespace) -> None:
    """Clean up old task history."""
    import sqlite3

    manager = _get_history_manager()

    if not manager.enabled:
        print("History is disabled. Enable with: SYNAPSE_HISTORY_ENABLED=true")
        return

    # Validate arguments
    if args.days is None and args.max_size is None:
        print("Error: Specify --days or --max-size")
        sys.exit(1)

    if args.days is not None and args.max_size is not None:
        print("Error: Specify only one of --days or --max-size")
        sys.exit(1)

    db_path = manager.db_path

    # Dry-run mode: Show what would be deleted
    if args.dry_run:
        if args.days:
            # Count observations older than N days
            try:
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                cutoff_sql = f"datetime('now', '-{args.days} days')"
                cursor.execute(
                    f"SELECT COUNT(*) FROM observations WHERE timestamp < {cutoff_sql}"
                )
                count = cursor.fetchone()[0]
                conn.close()
                print(f"Would delete {count} observations older than {args.days} days")
            except Exception as e:
                print(f"Error checking observations: {e}", file=sys.stderr)
        else:
            # Show current size and target
            try:
                current_size_mb = Path(db_path).stat().st_size / (1024 * 1024)
                print(f"Current database size: {current_size_mb:.2f} MB")
                print(f"Target size: {args.max_size} MB")
                if current_size_mb > args.max_size:
                    print("Would delete oldest observations to reach target size")
                else:
                    print("No cleanup needed (already under target size)")
            except Exception as e:
                print(f"Error checking database: {e}", file=sys.stderr)
        return

    # Confirm deletion (unless --force flag)
    if not args.force:
        response = input(
            "This will permanently delete observations. Continue? (yes/no): "
        )
        if response.lower() not in ("yes", "y"):
            print("Cancelled.")
            return

    # Execute cleanup
    print("Cleaning up...")
    if args.days:
        result = manager.cleanup_old_observations(
            days=args.days,
            vacuum=not args.no_vacuum,
        )
        print(
            f"Deleted {result['deleted_count']} observations older than {args.days} days"
        )
    else:
        result = manager.cleanup_by_size(
            max_size_mb=args.max_size,
            vacuum=not args.no_vacuum,
        )
        print(f"Deleted {result['deleted_count']} observations to reach target size")

    if not args.no_vacuum and result["vacuum_reclaimed_mb"] > 0:
        print(f"Reclaimed {result['vacuum_reclaimed_mb']:.2f} MB of disk space")


def cmd_history_stats(args: argparse.Namespace) -> None:
    """Show task history statistics."""
    manager = _get_history_manager()

    if not manager.enabled:
        print("History is disabled. Enable with: SYNAPSE_HISTORY_ENABLED=true")
        return

    stats = manager.get_statistics(agent_name=args.agent if args.agent else None)

    if not stats or stats["total_tasks"] == 0:
        print("No task history found.")
        return

    # Print statistics (section-based format)
    print("=" * 60)
    print("TASK HISTORY STATISTICS")
    print("=" * 60)
    print()

    # Overall metrics
    print(f"Total Tasks:     {stats['total_tasks']}")
    print(f"Completed:       {stats['completed']}")
    print(f"Failed:          {stats['failed']}")
    print(f"Canceled:        {stats['canceled']}")
    print(f"Success Rate:    {stats['success_rate']:.1f}%")
    print()

    # Database info
    print(f"Database Size:   {stats['db_size_mb']:.2f} MB")
    if stats["oldest_task"]:
        print(f"Oldest Task:     {stats['oldest_task']}")
        print(f"Newest Task:     {stats['newest_task']}")
        print(f"Date Range:      {stats['date_range_days']} days")
    print()

    # Agent breakdown (if not filtering by specific agent)
    if stats["by_agent"]:
        print("=" * 60)
        print("BY AGENT")
        print("=" * 60)
        print()
        print(
            f"{'Agent':<10} {'Total':<8} {'Completed':<10} {'Failed':<8} {'Canceled':<8}"
        )
        print("-" * 60)

        for agent, counts in sorted(stats["by_agent"].items()):
            print(
                f"{agent:<10} {counts['total']:<8} {counts['completed']:<10} "
                f"{counts['failed']:<8} {counts['canceled']:<8}"
            )
        print()

    if args.agent:
        print(f"(Filtered by agent: {args.agent})")


def cmd_history_export(args: argparse.Namespace) -> None:
    """Export task history in specified format."""
    manager = _get_history_manager()

    if not manager.enabled:
        print("History is disabled. Enable with: SYNAPSE_HISTORY_ENABLED=true")
        return

    # Get export format
    export_format = args.format.lower()
    if export_format not in ("json", "csv"):
        print(f"Error: Invalid format '{export_format}'. Use 'json' or 'csv'.")
        sys.exit(1)

    # Export with optional filters
    exported_data = manager.export_observations(
        format=export_format,
        agent_name=args.agent if args.agent else None,
        limit=args.limit if args.limit else None,
    )

    # Output to file or stdout
    if args.output:
        try:
            with open(args.output, "w") as f:
                f.write(exported_data)
            print(f"Exported to {args.output}")
        except OSError as e:
            print(f"Error writing to file: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        # Output to stdout
        print(exported_data)


def cmd_send(args: argparse.Namespace) -> None:
    """Send a message to an agent."""
    target = args.target
    message = args.message
    priority = args.priority
    wait_response = args.wait

    # Use the existing a2a tool
    cmd = [
        sys.executable,
        "synapse/tools/a2a.py",
        "send",
        "--target",
        target,
        "--priority",
        str(priority),
        message,
    ]

    env = os.environ.copy()
    env["PYTHONPATH"] = "."

    result = subprocess.run(cmd, env=env, capture_output=True, text=True)
    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)

    if wait_response:
        # TODO: Implement response waiting
        print("(--return not yet implemented)")


# ============================================================
# File Safety Commands
# ============================================================


def cmd_file_safety_status(args: argparse.Namespace) -> None:
    """Show file safety statistics."""
    from synapse.file_safety import FileSafetyManager

    manager = FileSafetyManager.from_env()

    if not manager.enabled:
        print("File safety is disabled. Enable with: SYNAPSE_FILE_SAFETY_ENABLED=true")
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
        print("File safety is disabled. Enable with: SYNAPSE_FILE_SAFETY_ENABLED=true")
        return

    locks = manager.list_locks(
        agent_name=args.agent if hasattr(args, "agent") else None
    )

    if not locks:
        print("No active file locks.")
        return

    print(f"{'File Path':<50} {'Agent':<15} {'Expires At':<20}")
    print("-" * 85)

    for lock in locks:
        file_path = lock["file_path"][:50]
        agent = lock["agent_name"][:15]
        expires = lock["expires_at"][:20] if lock.get("expires_at") else "N/A"
        print(f"{file_path:<50} {agent:<15} {expires:<20}")

    print(f"\nTotal: {len(locks)} active locks")


def cmd_file_safety_lock(args: argparse.Namespace) -> None:
    """Acquire a lock on a file."""
    from synapse.file_safety import FileSafetyManager, LockStatus

    manager = FileSafetyManager.from_env()

    if not manager.enabled:
        print("File safety is disabled. Enable with: SYNAPSE_FILE_SAFETY_ENABLED=true")
        return

    result = manager.acquire_lock(
        file_path=args.file,
        agent_name=args.agent,
        task_id=args.task_id if hasattr(args, "task_id") else None,
        duration_seconds=args.duration if hasattr(args, "duration") else None,
        intent=args.intent if hasattr(args, "intent") else None,
    )

    status = result["status"]
    if status == LockStatus.ACQUIRED:
        print(f"Lock acquired on {args.file}")
        print(f"Expires at: {result.get('expires_at')}")
    elif status == LockStatus.RENEWED:
        print(f"Lock renewed on {args.file}")
        print(f"New expiration: {result.get('expires_at')}")
    elif status == LockStatus.ALREADY_LOCKED:
        print(
            f"File is already locked by {result.get('lock_holder')}",
            file=sys.stderr,
        )
        print(f"Expires at: {result.get('expires_at')}", file=sys.stderr)
        sys.exit(1)
    elif status == LockStatus.FAILED:
        print(
            f"Failed to acquire lock: {result.get('error', 'unknown error')}",
            file=sys.stderr,
        )
        sys.exit(1)
    else:
        print(f"Unexpected lock status: {status}", file=sys.stderr)
        sys.exit(1)


def cmd_file_safety_unlock(args: argparse.Namespace) -> None:
    """Release a lock on a file."""
    from synapse.file_safety import FileSafetyManager

    manager = FileSafetyManager.from_env()

    if not manager.enabled:
        print("File safety is disabled. Enable with: SYNAPSE_FILE_SAFETY_ENABLED=true")
        return

    if manager.release_lock(args.file, args.agent):
        print(f"Lock released on {args.file}")
    else:
        print(f"No lock found for {args.file} by {args.agent}")
        sys.exit(1)


def cmd_file_safety_history(args: argparse.Namespace) -> None:
    """Show modification history for a file."""
    from synapse.file_safety import FileSafetyManager

    manager = FileSafetyManager.from_env()

    if not manager.enabled:
        print("File safety is disabled. Enable with: SYNAPSE_FILE_SAFETY_ENABLED=true")
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
        print("File safety is disabled. Enable with: SYNAPSE_FILE_SAFETY_ENABLED=true")
        return

    mods = manager.get_recent_modifications(
        limit=args.limit,
        agent_name=args.agent if hasattr(args, "agent") and args.agent else None,
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
        file_path = mod["file_path"][-40:]  # Show last 40 chars
        print(f"{timestamp:<20} {agent:<12} {change_type:<8} {file_path:<40}")

    print(f"\nShowing {len(mods)} recent modifications")


def cmd_file_safety_record(args: argparse.Namespace) -> None:
    """Record a file modification."""
    from synapse.file_safety import FileSafetyManager

    manager = FileSafetyManager.from_env()

    if not manager.enabled:
        print("File safety is disabled. Enable with: SYNAPSE_FILE_SAFETY_ENABLED=true")
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
        print("File safety is disabled. Enable with: SYNAPSE_FILE_SAFETY_ENABLED=true")
        return

    # Confirm
    if not args.force:
        response = input(
            f"Delete modification records older than {args.days} days? (yes/no): "
        )
        if response.lower() not in ("yes", "y"):
            print("Cancelled.")
            return

    deleted = manager.cleanup_old_modifications(days=args.days)
    print(f"Deleted {deleted} modification records older than {args.days} days")

    # Also cleanup expired locks
    expired_locks = manager.cleanup_expired_locks()
    if expired_locks > 0:
        print(f"Cleaned up {expired_locks} expired locks")


def cmd_file_safety_debug(args: argparse.Namespace) -> None:
    """Show debug information for file safety troubleshooting."""
    from synapse.file_safety import FileSafetyManager

    print("=" * 60)
    print("FILE SAFETY DEBUG INFORMATION")
    print("=" * 60)

    # Environment variables
    print("\n[Environment Variables]")
    env_vars = [
        "SYNAPSE_FILE_SAFETY_ENABLED",
        "SYNAPSE_FILE_SAFETY_RETENTION_DAYS",
        "SYNAPSE_LOG_LEVEL",
    ]
    for var in env_vars:
        value = os.environ.get(var, "(not set)")
        print(f"  {var}: {value}")

    # Settings file locations
    print("\n[Settings Files]")
    settings_paths = [
        Path.cwd() / ".synapse" / "settings.json",
        Path.home() / ".synapse" / "settings.json",
    ]
    for path in settings_paths:
        status = "exists" if path.exists() else "not found"
        print(f"  {path}: {status}")

    # Database info
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

    # Instruction files
    print("\n[Instruction Files]")
    instruction_files = [
        Path.cwd() / ".synapse" / "file-safety.md",
        Path.home() / ".synapse" / "file-safety.md",
    ]
    for path in instruction_files:
        status = "exists" if path.exists() else "not found"
        print(f"  {path}: {status}")

    # Log file locations
    print("\n[Log Files]")
    log_dir = Path.home() / ".synapse" / "logs"
    if log_dir.exists():
        log_files = list(log_dir.glob("*.log"))
        if log_files:
            for lf in sorted(log_files)[-5:]:  # Show last 5
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


# ============================================================
# External Agent Management Commands
# ============================================================


def cmd_external_add(args: argparse.Namespace) -> None:
    """Add an external A2A agent."""
    client = get_client()
    agent = client.discover(args.url, alias=args.alias)

    if agent:
        print(f"Added external agent: {agent.name}")
        print(f"  Alias: {agent.alias}")
        print(f"  URL: {agent.url}")
        print(f"  Description: {agent.description}")
        if agent.skills:
            skills_str = ", ".join(s.get("name", s.get("id", "")) for s in agent.skills)
            print(f"  Skills: {skills_str}")
    else:
        print(f"Failed to add agent from {args.url}")
        sys.exit(1)


def cmd_external_list(args: argparse.Namespace) -> None:
    """List external A2A agents."""
    client = get_client()
    agents = client.list_agents()

    if not agents:
        print("No external agents registered.")
        print("Use 'synapse external add <url>' to add one.")
        return

    print(f"{'ALIAS':<15} {'NAME':<20} {'URL':<40} {'LAST SEEN'}")
    print("-" * 90)
    for agent in agents:
        last_seen = agent.last_seen[:19] if agent.last_seen else "Never"
        print(f"{agent.alias:<15} {agent.name:<20} {agent.url:<40} {last_seen}")


def cmd_external_remove(args: argparse.Namespace) -> None:
    """Remove an external A2A agent."""
    client = get_client()

    if client.remove_agent(args.alias):
        print(f"Removed external agent: {args.alias}")
    else:
        print(f"Agent '{args.alias}' not found")
        sys.exit(1)


def cmd_external_send(args: argparse.Namespace) -> None:
    """Send a message to an external A2A agent."""
    client = get_client()

    task = client.send_message(args.alias, args.message, wait_for_completion=args.wait)

    if task:
        print(f"Task ID: {task.id}")
        print(f"Status: {task.status}")
        if task.artifacts:
            print("Artifacts:")
            for artifact in task.artifacts:
                print(f"  - {artifact}")
    else:
        print(f"Failed to send message to {args.alias}")
        sys.exit(1)


def cmd_external_info(args: argparse.Namespace) -> None:
    """Show detailed info about an external agent."""
    client = get_client()
    agent = client.registry.get(args.alias)

    if not agent:
        print(f"Agent '{args.alias}' not found")
        sys.exit(1)

    print(f"Name: {agent.name}")
    print(f"Alias: {agent.alias}")
    print(f"URL: {agent.url}")
    print(f"Description: {agent.description}")
    print(f"Added: {agent.added_at}")
    print(f"Last Seen: {agent.last_seen or 'Never'}")

    if agent.capabilities:
        print("\nCapabilities:")
        for key, value in agent.capabilities.items():
            print(f"  {key}: {value}")

    if agent.skills:
        print("\nSkills:")
        for skill in agent.skills:
            print(f"  - {skill.get('name', skill.get('id', 'Unknown'))}")
            if skill.get("description"):
                print(f"    {skill['description']}")


# ============================================================
# Auth Management Commands
# ============================================================


def cmd_auth_generate_key(args: argparse.Namespace) -> None:
    """Generate a new API key."""
    count = getattr(args, "count", 1)
    export_format = getattr(args, "export", False)

    keys = [generate_api_key() for _ in range(count)]

    if export_format:
        # Output in export format
        if count == 1:
            print(f"export SYNAPSE_API_KEYS={keys[0]}")
        else:
            print(f"export SYNAPSE_API_KEYS={','.join(keys)}")
    else:
        # Simple output
        for key in keys:
            print(key)


# ============================================================
# Settings Commands (init, reset)
# ============================================================


def _prompt_scope_selection() -> str | None:
    """
    Prompt user to select a scope for settings.

    Returns:
        "user", "project", or None if cancelled.
    """
    print("\n? Where do you want to create settings.json?")
    print("  [1] User scope (~/.synapse/settings.json)")
    print("  [2] Project scope (./.synapse/settings.json)")
    print("  [q] Cancel")
    print()

    while True:
        choice = input("Enter choice [1/2/q]: ").strip().lower()
        if choice == "1":
            return "user"
        elif choice == "2":
            return "project"
        elif choice == "q":
            return None
        else:
            print("Invalid choice. Please enter 1, 2, or q.")


def _prompt_reset_scope_selection() -> str | None:
    """
    Prompt user to select which settings to reset.

    Returns:
        "user", "project", "both", or None if cancelled.
    """
    print("\n? Which settings do you want to reset?")
    print("  [1] User scope (~/.synapse/settings.json)")
    print("  [2] Project scope (./.synapse/settings.json)")
    print("  [3] Both")
    print("  [q] Cancel")
    print()

    while True:
        choice = input("Enter choice [1/2/3/q]: ").strip().lower()
        if choice == "1":
            return "user"
        elif choice == "2":
            return "project"
        elif choice == "3":
            return "both"
        elif choice == "q":
            return None
        else:
            print("Invalid choice. Please enter 1, 2, 3, or q.")


def _write_default_settings(path: Path) -> bool:
    """
    Write default settings to the specified path.

    Args:
        path: Path to write settings.json.

    Returns:
        True if successful, False otherwise.
    """
    import json

    from synapse.settings import DEFAULT_SETTINGS

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_SETTINGS, f, indent=2, ensure_ascii=False)
        return True
    except OSError as e:
        print(f"Error writing settings: {e}")
        return False


def _copy_claude_skills_to_codex(base_dir: Path, force: bool = False) -> list[str]:
    """
    Copy synapse-a2a skills from .claude to .codex directory.

    Claude Code supports plugins, so skills are installed via:
        /plugin marketplace add s-hiraoku/synapse-a2a
        /plugin install synapse-a2a@s-hiraoku/synapse-a2a

    Codex does not support plugins, so this function copies the skills
    from .claude/skills/synapse-a2a to .codex/skills/synapse-a2a.

    Args:
        base_dir: Base directory (e.g., Path.home() or Path.cwd())
        force: If True, overwrite existing skills in .codex

    Returns:
        List of paths where skills were copied to
    """
    installed: list[str] = []

    # Source: .claude/skills/synapse-a2a (installed via plugin marketplace)
    claude_skills_path = base_dir / ".claude" / "skills" / "synapse-a2a"

    # Destination: .codex/skills/synapse-a2a
    codex_skills_path = base_dir / ".codex" / "skills" / "synapse-a2a"

    # Only copy if source exists
    if not claude_skills_path.exists():
        return installed

    # Check if destination already exists
    if codex_skills_path.exists() and not force:
        return installed

    # Copy skills to .codex
    try:
        import shutil

        # Create parent directories
        codex_skills_path.parent.mkdir(parents=True, exist_ok=True)

        # Remove existing if force
        if codex_skills_path.exists() and force:
            shutil.rmtree(codex_skills_path)

        # Copy directory tree
        shutil.copytree(claude_skills_path, codex_skills_path)
        installed.append(str(codex_skills_path))
    except OSError:
        # Silently ignore copy errors
        pass

    return installed


def cmd_init(args: argparse.Namespace) -> None:
    """Initialize settings.json and install skills."""
    scope = getattr(args, "scope", None)

    # If scope not provided via flag, prompt interactively
    if scope is None:
        scope = _prompt_scope_selection()

    if scope is None:
        print("Cancelled.")
        return

    # Determine paths based on scope
    if scope == "user":
        settings_path = Path.home() / ".synapse" / "settings.json"
        skills_base = Path.home()
    else:  # project
        settings_path = Path.cwd() / ".synapse" / "settings.json"
        skills_base = Path.cwd()

    # Check if settings file already exists
    if settings_path.exists():
        response = (
            input(f"\n{settings_path} already exists. Overwrite? (y/N): ")
            .strip()
            .lower()
        )
        if response not in ("y", "yes"):
            print("Cancelled.")
            return

    # Write default settings
    if _write_default_settings(settings_path):
        print(f"✔ Created {settings_path}")
    else:
        sys.exit(1)

    # Copy skills from .claude to .codex (Codex doesn't support plugins)
    installed = _copy_claude_skills_to_codex(skills_base, force=False)
    for path in installed:
        print(f"✔ Copied skill to {path}")


def cmd_reset(args: argparse.Namespace) -> None:
    """Reset settings.json and reinstall skills to defaults."""
    scope = getattr(args, "scope", None)

    # If scope not provided via flag, prompt interactively
    if scope is None:
        scope = _prompt_reset_scope_selection()

    if scope is None:
        print("Cancelled.")
        return

    # Determine paths and skill bases
    user_path = Path.home() / ".synapse" / "settings.json"
    project_path = Path.cwd() / ".synapse" / "settings.json"

    paths_to_reset = []
    skill_bases = []
    if scope == "user":
        paths_to_reset.append(user_path)
        skill_bases.append(Path.home())
    elif scope == "project":
        paths_to_reset.append(project_path)
        skill_bases.append(Path.cwd())
    else:  # both
        paths_to_reset.extend([user_path, project_path])
        skill_bases.extend([Path.home(), Path.cwd()])

    # Confirm
    force = getattr(args, "force", False)
    if not force:
        print("\nThis will reset the following to defaults:")
        print("\nSettings:")
        for p in paths_to_reset:
            exists = "exists" if p.exists() else "will be created"
            print(f"  - {p} ({exists})")
        print("\nSkills (will be reinstalled):")
        for base in skill_bases:
            for agent in [".claude", ".codex"]:
                skill_path = base / agent / "skills" / "synapse-a2a"
                exists = "exists" if skill_path.exists() else "will be created"
                print(f"  - {skill_path} ({exists})")
        response = input("\nContinue? (y/N): ").strip().lower()
        if response not in ("y", "yes"):
            print("Cancelled.")
            return

    # Reset settings
    for path in paths_to_reset:
        if _write_default_settings(path):
            print(f"✔ Reset {path}")
        else:
            print(f"✗ Failed to reset {path}")

    # Re-copy skills from .claude to .codex (force=True to overwrite)
    for base in skill_bases:
        installed = _copy_claude_skills_to_codex(base, force=True)
        for installed_path in installed:
            print(f"✔ Re-copied skill to {installed_path}")


# ============================================================
# Delegation Commands
# ============================================================


def cmd_delegate_status(args: argparse.Namespace) -> None:
    """Show current delegation configuration."""
    from synapse.settings import get_settings

    settings = get_settings()
    mode = settings.get_delegation_mode()
    instructions_path = get_delegate_instructions_path()
    instructions = load_delegate_instructions()

    print("=== Delegation Configuration ===")
    print(f"Mode: {mode}")

    if instructions_path:
        print(f"Instructions: {instructions_path}")
    else:
        print("Instructions: (not found)")

    is_active = mode in ("orchestrator", "passthrough") and instructions is not None
    print(f"Status: {'active' if is_active else 'inactive'}")
    print()

    if instructions:
        print("Rules:")
        for line in instructions.strip().split("\n")[:10]:  # Show first 10 lines
            print(f"  {line}")
        lines = instructions.strip().split("\n")
        if len(lines) > 10:
            print(f"  ... ({len(lines) - 10} more lines)")
    else:
        print("No delegation instructions found.")
        print()
        print("To set up delegation:")
        print("  1. Set mode in .synapse/settings.json:")
        print('     {"delegation": {"mode": "orchestrator"}}')
        print("  2. Create .synapse/delegate.md with your rules")

    print("================================")


def cmd_delegate_set(args: argparse.Namespace) -> None:
    """Set delegation mode in settings.json."""
    import json

    mode = args.mode
    scope = getattr(args, "scope", "project")

    # Determine settings path
    if scope == "user":
        settings_path = Path.home() / ".synapse" / "settings.json"
    else:
        settings_path = Path.cwd() / ".synapse" / "settings.json"

    # Load existing settings
    settings_data: dict = {}
    if settings_path.exists():
        try:
            with open(settings_path, encoding="utf-8") as f:
                settings_data = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass

    # Update delegation mode
    if "delegation" not in settings_data:
        settings_data["delegation"] = {}
    settings_data["delegation"]["mode"] = mode

    # Save settings
    try:
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(settings_data, f, indent=2, ensure_ascii=False)
        print(f"Delegation mode set to '{mode}' in {settings_path}")

        if mode != "off":
            instructions_path = get_delegate_instructions_path()
            if instructions_path:
                print(f"Instructions will be loaded from: {instructions_path}")
            else:
                print()
                print("Note: Create .synapse/delegate.md with your delegation rules.")
                print("Example:")
                print("  # Delegation Rules")
                print("  コーディングはCodexに任せる")
                print("  リサーチはGeminiに依頼する")
    except OSError as e:
        print(f"Failed to save settings: {e}")
        sys.exit(1)


def cmd_delegate_off(args: argparse.Namespace) -> None:
    """Disable delegation."""
    args.mode = "off"
    args.scope = getattr(args, "scope", "project")
    cmd_delegate_set(args)


def cmd_auth_setup(args: argparse.Namespace) -> None:
    """Generate API keys and show setup instructions."""
    api_key = generate_api_key()
    admin_key = generate_api_key()

    print("=" * 60)
    print("Synapse A2A Authentication Setup")
    print("=" * 60)
    print()
    print("Generated keys:")
    print(f"  API Key:   {api_key}")
    print(f"  Admin Key: {admin_key}")
    print()
    print("Add these to your shell configuration (~/.bashrc, ~/.zshrc):")
    print()
    print("  export SYNAPSE_AUTH_ENABLED=true")
    print(f"  export SYNAPSE_API_KEYS={api_key}")
    print(f"  export SYNAPSE_ADMIN_KEY={admin_key}")
    print()
    print("Or run with environment variables:")
    print()
    print("  SYNAPSE_AUTH_ENABLED=true \\")
    print(f"  SYNAPSE_API_KEYS={api_key} \\")
    print(f"  SYNAPSE_ADMIN_KEY={admin_key} \\")
    print("  synapse claude")
    print()
    print("Client usage:")
    print()
    print(f"  curl -H 'X-API-Key: {api_key}' http://localhost:8100/tasks")
    print()
    print("=" * 60)
    print("IMPORTANT: Save these keys securely. They cannot be recovered.")
    print("=" * 60)


def cmd_run_interactive(profile: str, port: int, tool_args: list | None = None) -> None:
    """Run an agent in interactive mode with input routing."""
    tool_args = tool_args or []

    # Load profile
    profile_path = os.path.join(
        os.path.dirname(__file__), "profiles", f"{profile}.yaml"
    )
    if not os.path.exists(profile_path):
        print(f"Profile '{profile}' not found")
        sys.exit(1)

    with open(profile_path) as f:
        config = yaml.safe_load(f)

    # Load submit sequence from profile (decode escape sequences)
    submit_seq = config.get("submit_sequence", "\n").encode().decode("unicode_escape")
    startup_delay = config.get("startup_delay", 3)

    # Parse idle detection config (with backward compatibility)
    idle_detection = config.get("idle_detection", {})
    if not idle_detection:
        # Legacy mode: Use top-level idle_regex
        idle_regex = config.get("idle_regex")
        if idle_regex:
            idle_detection = {
                "strategy": "pattern",
                "pattern": idle_regex,
                "timeout": 1.5,
            }

    # Merge profile args with CLI tool args
    profile_args = config.get("args", [])
    all_args = profile_args + tool_args

    # Merge environment
    env = os.environ.copy()
    if "env" in config:
        env.update(config["env"])

    # Apply settings from .synapse/settings.json
    from synapse.settings import get_settings

    synapse_settings = get_settings()
    synapse_settings.apply_env(env)

    # Check if resume mode (--continue, --resume, etc.)
    # Skip initial instructions if resuming a previous session
    is_resume = synapse_settings.is_resume_mode(profile, all_args)
    if is_resume:
        print(
            "\x1b[32m[Synapse]\x1b[0m Resume mode detected, "
            "skipping initial instructions"
        )

    # Create registry and register this agent
    registry = AgentRegistry()
    agent_id = registry.get_agent_id(profile, port)

    # Set SYNAPSE env vars for sender identification (same as server.py)
    env["SYNAPSE_AGENT_ID"] = agent_id
    env["SYNAPSE_AGENT_TYPE"] = profile
    env["SYNAPSE_PORT"] = str(port)

    # Create controller - initial instructions sent on IDLE (unless resume mode)
    controller = TerminalController(
        command=config["command"],
        args=all_args,
        idle_detection=idle_detection if idle_detection else None,
        idle_regex=(
            config.get("idle_regex") if not idle_detection else None
        ),  # Backward compat
        env=env,
        registry=registry,
        agent_id=agent_id,
        agent_type=profile,
        submit_seq=submit_seq,
        startup_delay=startup_delay,
        port=port,
        skip_initial_instructions=is_resume,
    )

    # Register agent
    registry.register(agent_id, profile, port, status="PROCESSING")

    # Handle Ctrl+C gracefully
    def cleanup(signum: int, frame: object) -> None:
        print("\n\x1b[32m[Synapse]\x1b[0m Shutting down...")
        registry.unregister(agent_id)
        controller.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    print(f"\x1b[32m[Synapse]\x1b[0m Starting {profile} on port {port}")
    print(f"\x1b[32m[Synapse]\x1b[0m Submit sequence: {repr(submit_seq)}")
    msg = "Use @Agent 'message' to send (response expected by default)"
    print(f"\x1b[32m[Synapse]\x1b[0m {msg}")
    msg2 = "Use @Agent --non-response 'message' to send without response"
    print(f"\x1b[32m[Synapse]\x1b[0m {msg2}")
    print("\x1b[32m[Synapse]\x1b[0m Press Ctrl+C twice to exit")
    print()
    print("\x1b[32m[Synapse]\x1b[0m Google A2A endpoints:")
    print(
        f"\x1b[32m[Synapse]\x1b[0m   Agent Card: http://localhost:{port}/.well-known/agent.json"
    )
    print(f"\x1b[32m[Synapse]\x1b[0m   Tasks API:  http://localhost:{port}/tasks/send")
    print()

    try:
        # Start the API server in background
        import threading

        import uvicorn

        from synapse.server import create_app

        app = create_app(
            controller,
            registry,
            agent_id,
            port,
            submit_seq,
            agent_type=profile,
            registry=registry,
        )

        def run_server() -> None:
            uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")

        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()

        # Give server time to start
        time.sleep(1)

        # Initial instructions are sent via on_first_idle callback
        # when the agent reaches IDLE state (detected by idle_regex)

        # Run interactive mode
        controller.run_interactive()

    except KeyboardInterrupt:
        pass
    finally:
        print("\n\x1b[32m[Synapse]\x1b[0m Shutting down...")
        registry.unregister(agent_id)
        controller.stop()


def main() -> None:
    # Install A2A skills if not present
    install_skills()

    # Check for shortcut: synapse claude [--port PORT] [-- TOOL_ARGS...]
    if len(sys.argv) >= 2 and sys.argv[1] in KNOWN_PROFILES:
        profile = sys.argv[1]

        # Find -- separator to split synapse args from tool args
        try:
            separator_idx = sys.argv.index("--")
            synapse_args = sys.argv[2:separator_idx]
            tool_args = sys.argv[separator_idx + 1 :]
        except ValueError:
            synapse_args = sys.argv[2:]
            tool_args = []

        # Parse --port from synapse_args
        port = None
        if "--port" in synapse_args:
            idx = synapse_args.index("--port")
            if idx + 1 < len(synapse_args):
                try:
                    port = int(synapse_args[idx + 1])
                except ValueError:
                    print(f"Invalid port: {synapse_args[idx + 1]}")
                    sys.exit(1)

        # Auto-select available port if not specified
        if port is None:
            registry = AgentRegistry()
            port_manager = PortManager(registry)
            port = port_manager.get_available_port(profile)

            if port is None:
                print(port_manager.format_exhaustion_error(profile))
                sys.exit(1)

        assert port is not None  # Type narrowing for mypy/ty
        cmd_run_interactive(profile, port, tool_args)
        return

    parser = argparse.ArgumentParser(
        description="Synapse A2A - Agent-to-Agent Communication",
        prog="synapse",
        epilog="Shortcuts: synapse claude, synapse gemini --port 8102",
    )
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # start (background)
    p_start = subparsers.add_parser("start", help="Start an agent in background")
    p_start.add_argument("profile", help="Agent profile (claude, codex, gemini, dummy)")
    p_start.add_argument("--port", type=int, help="Server port (default: auto)")
    p_start.add_argument(
        "--foreground", "-f", action="store_true", help="Run in foreground"
    )
    p_start.add_argument("--ssl-cert", help="SSL certificate file path (enables HTTPS)")
    p_start.add_argument("--ssl-key", help="SSL private key file path")
    p_start.add_argument(
        "tool_args",
        nargs=argparse.REMAINDER,
        help="Arguments after -- are passed to the CLI tool",
    )
    p_start.set_defaults(func=cmd_start)

    # stop
    p_stop = subparsers.add_parser("stop", help="Stop an agent")
    p_stop.add_argument("profile", help="Agent profile to stop")
    p_stop.add_argument(
        "--all", "-a", action="store_true", help="Stop all instances of this profile"
    )
    p_stop.set_defaults(func=cmd_stop)

    # list
    p_list = subparsers.add_parser("list", help="List running agents")
    p_list.add_argument(
        "--watch",
        "-w",
        action="store_true",
        help="Watch mode: continuously refresh the agent list",
    )
    p_list.add_argument(
        "--interval",
        "-i",
        type=float,
        default=2.0,
        help="Refresh interval in seconds (default: 2.0, only used with --watch)",
    )
    p_list.set_defaults(func=cmd_list)

    # logs
    p_logs = subparsers.add_parser("logs", help="Show agent logs")
    p_logs.add_argument("profile", help="Agent profile")
    p_logs.add_argument("-f", "--follow", action="store_true", help="Follow log output")
    p_logs.add_argument(
        "-n", "--lines", type=int, default=50, help="Number of lines to show"
    )
    p_logs.set_defaults(func=cmd_logs)

    # send
    p_send = subparsers.add_parser("send", help="Send a message to an agent")
    p_send.add_argument("target", help="Target agent (claude, codex, gemini)")
    p_send.add_argument("message", help="Message to send")
    p_send.add_argument("--priority", "-p", type=int, default=1, help="Priority (1-5)")
    p_send.add_argument(
        "--return", "-r", dest="wait", action="store_true", help="Wait for response"
    )
    p_send.set_defaults(func=cmd_send)

    # history - Task history management
    p_history = subparsers.add_parser("history", help="View and manage task history")
    history_subparsers = p_history.add_subparsers(
        dest="history_command", help="History commands"
    )

    # history list
    p_hist_list = history_subparsers.add_parser("list", help="List task history")
    p_hist_list.add_argument(
        "--agent", "-a", help="Filter by agent name (e.g., claude, gemini, codex)"
    )
    p_hist_list.add_argument(
        "--limit",
        "-n",
        type=int,
        default=50,
        help="Maximum number of entries (default: 50)",
    )
    p_hist_list.set_defaults(func=cmd_history_list)

    # history show
    p_hist_show = history_subparsers.add_parser("show", help="Show task details")
    p_hist_show.add_argument("task_id", help="Task ID to display")
    p_hist_show.set_defaults(func=cmd_history_show)

    # history search
    p_hist_search = history_subparsers.add_parser(
        "search", help="Search task history by keywords"
    )
    p_hist_search.add_argument(
        "keywords",
        nargs="+",
        help="Search keywords (searches in input and output fields)",
    )
    p_hist_search.add_argument(
        "--logic",
        choices=["OR", "AND"],
        default="OR",
        help="Search logic: OR (any keyword) or AND (all keywords). Default: OR",
    )
    p_hist_search.add_argument(
        "--case-sensitive",
        action="store_true",
        help="Enable case-sensitive search (default: case-insensitive)",
    )
    p_hist_search.add_argument("--agent", "-a", help="Filter results by agent name")
    p_hist_search.add_argument(
        "--limit",
        "-n",
        type=int,
        default=50,
        help="Maximum number of results to return (default: 50)",
    )
    p_hist_search.set_defaults(func=cmd_history_search)

    # history cleanup
    p_hist_cleanup = history_subparsers.add_parser(
        "cleanup", help="Clean up old task history"
    )
    p_hist_cleanup.add_argument(
        "--days",
        type=int,
        help="Delete observations older than N days",
    )
    p_hist_cleanup.add_argument(
        "--max-size",
        type=int,
        help="Keep database under N megabytes (delete oldest records)",
    )
    p_hist_cleanup.add_argument(
        "--no-vacuum",
        action="store_true",
        help="Skip VACUUM after deletion (faster but doesn't reclaim disk space)",
    )
    p_hist_cleanup.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without actually deleting",
    )
    p_hist_cleanup.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Skip confirmation prompt (useful for automation)",
    )
    p_hist_cleanup.set_defaults(func=cmd_history_cleanup)

    # history stats
    p_hist_stats = history_subparsers.add_parser("stats", help="Show usage statistics")
    p_hist_stats.add_argument(
        "--agent", "-a", help="Show statistics for specific agent only"
    )
    p_hist_stats.set_defaults(func=cmd_history_stats)

    # history export
    p_hist_export = history_subparsers.add_parser(
        "export", help="Export task history to JSON or CSV"
    )
    p_hist_export.add_argument(
        "--format",
        "-f",
        choices=["json", "csv"],
        default="json",
        help="Export format (default: json)",
    )
    p_hist_export.add_argument(
        "--agent", "-a", help="Export only observations from specific agent"
    )
    p_hist_export.add_argument(
        "--limit",
        "-n",
        type=int,
        help="Maximum number of observations to export",
    )
    p_hist_export.add_argument(
        "--output",
        "-o",
        help="Output file path (default: stdout)",
    )
    p_hist_export.set_defaults(func=cmd_history_export)

    # external - External A2A agent management
    p_external = subparsers.add_parser("external", help="Manage external A2A agents")
    external_subparsers = p_external.add_subparsers(
        dest="external_command", help="External agent commands"
    )

    # external add
    p_ext_add = external_subparsers.add_parser("add", help="Add an external A2A agent")
    p_ext_add.add_argument("url", help="Agent URL (e.g., https://agent.example.com)")
    p_ext_add.add_argument("--alias", "-a", help="Short alias for the agent")
    p_ext_add.set_defaults(func=cmd_external_add)

    # external list
    p_ext_list = external_subparsers.add_parser("list", help="List external agents")
    p_ext_list.set_defaults(func=cmd_external_list)

    # external remove
    p_ext_rm = external_subparsers.add_parser("remove", help="Remove an external agent")
    p_ext_rm.add_argument("alias", help="Agent alias to remove")
    p_ext_rm.set_defaults(func=cmd_external_remove)

    # external send
    p_ext_send = external_subparsers.add_parser(
        "send", help="Send message to external agent"
    )
    p_ext_send.add_argument("alias", help="Agent alias")
    p_ext_send.add_argument("message", help="Message to send")
    p_ext_send.add_argument(
        "--wait", "-w", action="store_true", help="Wait for completion"
    )
    p_ext_send.set_defaults(func=cmd_external_send)

    # external info
    p_ext_info = external_subparsers.add_parser("info", help="Show agent details")
    p_ext_info.add_argument("alias", help="Agent alias")
    p_ext_info.set_defaults(func=cmd_external_info)

    # auth - Authentication management
    p_auth = subparsers.add_parser("auth", help="Manage API key authentication")
    auth_subparsers = p_auth.add_subparsers(dest="auth_command", help="Auth commands")

    # auth generate-key
    p_auth_gen = auth_subparsers.add_parser(
        "generate-key", help="Generate a new API key"
    )
    p_auth_gen.add_argument(
        "--count", "-n", type=int, default=1, help="Number of keys to generate"
    )
    p_auth_gen.add_argument(
        "--export", "-e", action="store_true", help="Output in export format"
    )
    p_auth_gen.set_defaults(func=cmd_auth_generate_key)

    # auth setup
    p_auth_setup = auth_subparsers.add_parser(
        "setup", help="Generate keys and show setup instructions"
    )
    p_auth_setup.set_defaults(func=cmd_auth_setup)

    # init - Initialize settings
    p_init = subparsers.add_parser(
        "init", help="Initialize .synapse/settings.json with defaults"
    )
    p_init.add_argument(
        "--scope",
        choices=["user", "project"],
        help="Scope for settings file (user: ~/.synapse, project: ./.synapse)",
    )
    p_init.set_defaults(func=cmd_init)

    # reset - Reset settings to defaults
    p_reset = subparsers.add_parser(
        "reset", help="Reset .synapse/settings.json to defaults"
    )
    p_reset.add_argument(
        "--scope",
        choices=["user", "project", "both"],
        help="Which settings to reset",
    )
    p_reset.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Skip confirmation prompt",
    )
    p_reset.set_defaults(func=cmd_reset)

    # delegate - Delegation management
    p_delegate = subparsers.add_parser(
        "delegate", help="Configure automatic task delegation between agents"
    )
    delegate_subparsers = p_delegate.add_subparsers(
        dest="delegate_command", help="Delegation commands"
    )

    # delegate status
    p_del_status = delegate_subparsers.add_parser(
        "status", help="Show current delegation configuration"
    )
    p_del_status.set_defaults(func=cmd_delegate_status)

    # delegate set
    p_del_set = delegate_subparsers.add_parser(
        "set", help="Set delegation mode in settings.json"
    )
    p_del_set.add_argument(
        "mode",
        choices=["orchestrator", "passthrough", "off"],
        help="Delegation mode: orchestrator (analyze & integrate), passthrough (direct forward), off (disable)",
    )
    p_del_set.add_argument(
        "--scope",
        choices=["user", "project"],
        default="project",
        help="Settings scope: user (~/.synapse) or project (./.synapse)",
    )
    p_del_set.set_defaults(func=cmd_delegate_set)

    # delegate off
    p_del_off = delegate_subparsers.add_parser("off", help="Disable delegation")
    p_del_off.set_defaults(func=cmd_delegate_off)

    # file-safety - File locking and modification tracking
    p_file_safety = subparsers.add_parser(
        "file-safety",
        help="File locking and modification tracking for multi-agent safety",
    )
    file_safety_subparsers = p_file_safety.add_subparsers(
        dest="file_safety_command", help="File safety commands"
    )

    # file-safety status
    p_fs_status = file_safety_subparsers.add_parser(
        "status", help="Show file safety statistics"
    )
    p_fs_status.set_defaults(func=cmd_file_safety_status)

    # file-safety locks
    p_fs_locks = file_safety_subparsers.add_parser(
        "locks", help="List active file locks"
    )
    p_fs_locks.add_argument("--agent", "-a", help="Filter by agent name")
    p_fs_locks.set_defaults(func=cmd_file_safety_locks)

    # file-safety lock
    p_fs_lock = file_safety_subparsers.add_parser(
        "lock", help="Acquire a lock on a file"
    )
    p_fs_lock.add_argument("file", help="File path to lock")
    p_fs_lock.add_argument("agent", help="Agent name acquiring the lock")
    p_fs_lock.add_argument("--task-id", help="Task ID associated with the lock")
    p_fs_lock.add_argument(
        "--duration",
        type=int,
        default=300,
        help="Lock duration in seconds (default: 300)",
    )
    p_fs_lock.add_argument("--intent", help="Description of intended changes")
    p_fs_lock.set_defaults(func=cmd_file_safety_lock)

    # file-safety unlock
    p_fs_unlock = file_safety_subparsers.add_parser(
        "unlock", help="Release a lock on a file"
    )
    p_fs_unlock.add_argument("file", help="File path to unlock")
    p_fs_unlock.add_argument("agent", help="Agent name releasing the lock")
    p_fs_unlock.set_defaults(func=cmd_file_safety_unlock)

    # file-safety history
    p_fs_history = file_safety_subparsers.add_parser(
        "history", help="Show modification history for a file"
    )
    p_fs_history.add_argument("file", help="File path to show history for")
    p_fs_history.add_argument(
        "--limit", "-n", type=int, default=20, help="Maximum number of entries"
    )
    p_fs_history.set_defaults(func=cmd_file_safety_history)

    # file-safety recent
    p_fs_recent = file_safety_subparsers.add_parser(
        "recent", help="Show recent file modifications"
    )
    p_fs_recent.add_argument("--agent", "-a", help="Filter by agent name")
    p_fs_recent.add_argument(
        "--limit", "-n", type=int, default=50, help="Maximum number of entries"
    )
    p_fs_recent.set_defaults(func=cmd_file_safety_recent)

    # file-safety record
    p_fs_record = file_safety_subparsers.add_parser(
        "record", help="Record a file modification"
    )
    p_fs_record.add_argument("file_path", help="Path to the modified file")
    p_fs_record.add_argument("agent", help="Agent name that made the change")
    p_fs_record.add_argument("task_id", help="Task ID for this modification")
    p_fs_record.add_argument(
        "--type",
        "-t",
        choices=["CREATE", "MODIFY", "DELETE"],
        default="MODIFY",
        help="Type of change (default: MODIFY)",
    )
    p_fs_record.add_argument(
        "--intent", "-i", help="Description of why the change was made"
    )
    p_fs_record.set_defaults(func=cmd_file_safety_record)

    # file-safety cleanup
    p_fs_cleanup = file_safety_subparsers.add_parser(
        "cleanup", help="Clean up old modification records"
    )
    p_fs_cleanup.add_argument(
        "--days",
        type=int,
        default=30,
        help="Delete records older than N days (default: 30)",
    )
    p_fs_cleanup.add_argument(
        "--force", "-f", action="store_true", help="Skip confirmation prompt"
    )
    p_fs_cleanup.set_defaults(func=cmd_file_safety_cleanup)

    # file-safety debug
    p_fs_debug = file_safety_subparsers.add_parser(
        "debug", help="Show debug information for troubleshooting"
    )
    p_fs_debug.set_defaults(func=cmd_file_safety_debug)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    # Handle history subcommand without action
    if args.command == "history" and (
        not hasattr(args, "history_command") or args.history_command is None
    ):
        p_history.print_help()
        sys.exit(1)

    # Handle external subcommand without action
    if args.command == "external" and (
        not hasattr(args, "external_command") or args.external_command is None
    ):
        p_external.print_help()
        sys.exit(1)

    # Handle auth subcommand without action
    if args.command == "auth" and (
        not hasattr(args, "auth_command") or args.auth_command is None
    ):
        p_auth.print_help()
        sys.exit(1)

    # Handle delegate subcommand without action (show status by default)
    if args.command == "delegate" and (
        not hasattr(args, "delegate_command") or args.delegate_command is None
    ):
        cmd_delegate_status(args)
        return

    # Handle file-safety subcommand without action (show status by default)
    if args.command == "file-safety" and (
        not hasattr(args, "file_safety_command") or args.file_safety_command is None
    ):
        cmd_file_safety_status(args)
        return

    args.func(args)


if __name__ == "__main__":
    main()
