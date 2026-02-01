#!/usr/bin/env python3
"""Synapse A2A CLI - Main entry point for agent management."""

from __future__ import annotations

import argparse
import contextlib
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
from synapse.port_manager import PORT_RANGES, PortManager, is_process_alive
from synapse.registry import AgentRegistry, is_port_open
from synapse.utils import resolve_command_path

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
                msg = f"Installed {skill_name} skill to {claude_target}"
                print(f"\x1b[32m[Synapse]\x1b[0m {msg}")
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
    target_id = args.target
    registry = AgentRegistry()
    port_manager = PortManager(registry)

    # Check if target is an agent ID (e.g., synapse-claude-8100)
    if target_id.startswith("synapse-"):
        # Direct agent ID lookup
        agent_info = registry.get_agent(target_id)
        if agent_info:
            _stop_agent(registry, agent_info)
            return
        else:
            print(f"Agent not found: {target_id}")
            sys.exit(1)

    # Otherwise, treat as profile name
    profile = target_id
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


def cmd_kill(args: argparse.Namespace) -> None:
    """Kill a running agent by name, ID, or type."""
    target = args.target
    force = getattr(args, "force", False)

    registry = AgentRegistry()
    agent_info = registry.resolve_agent(target)

    if agent_info is None:
        # Check if multiple agents of same type
        agents = registry.get_live_agents()
        type_matches = [
            info for info in agents.values() if info.get("agent_type") == target
        ]
        if len(type_matches) > 1:
            print(
                f"Ambiguous target '{target}': multiple agents of type '{target}' running."
            )
            print("Use agent ID or name instead:")
            for info in type_matches:
                name = info.get("name")
                name_str = f" ({name})" if name else ""
                print(f"  {info['agent_id']}{name_str}")
            sys.exit(1)
        else:
            print(f"Agent not found: {target}")
            print("Run 'synapse list' to see running agents.")
            sys.exit(1)

    agent_id: str = agent_info["agent_id"]
    name = agent_info.get("name")
    pid = agent_info.get("pid")

    # Display info and ask for confirmation
    display_name = name if name else agent_id
    if not force:
        try:
            confirm = (
                input(f"Kill {display_name} (PID: {pid})? [y/N]: ").strip().lower()
            )
            if confirm != "y":
                print("Aborted.")
                return
        except (EOFError, KeyboardInterrupt):
            print("\nAborted.")
            return

    if pid:
        try:
            os.kill(pid, signal.SIGKILL)
            print(f"Killed {display_name} (PID: {pid})")
            registry.unregister(agent_id)
        except ProcessLookupError:
            print(f"Process {pid} not found. Cleaning up registry...")
            registry.unregister(agent_id)
    else:
        print(f"No PID found for {display_name}")


def cmd_jump(args: argparse.Namespace) -> None:
    """Jump to the terminal of a running agent."""
    from synapse.terminal_jump import jump_to_terminal

    target = args.target
    registry = AgentRegistry()
    agent_info = registry.resolve_agent(target)

    if agent_info is None:
        print(f"Agent not found: {target}")
        print("Run 'synapse list' to see running agents.")
        sys.exit(1)

    agent_id = agent_info.get("agent_id")
    name = agent_info.get("name")
    tty_device = agent_info.get("tty_device")

    display_name = name if name else agent_id

    if not tty_device and not agent_info.get("zellij_pane_id"):
        print(f"No TTY device available for {display_name}.")
        print(
            "Terminal jump requires the agent to have a TTY device or Zellij pane ID."
        )
        sys.exit(1)

    if jump_to_terminal(agent_info):
        print(f"Jumped to {display_name}")
    else:
        print(f"Failed to jump to {display_name}")
        print("Make sure your terminal supports this feature.")
        print("Supported: iTerm2, Terminal.app, Ghostty, VS Code, tmux, Zellij")
        sys.exit(1)


def cmd_rename(args: argparse.Namespace) -> None:
    """Assign or update name/role for a running agent."""
    target = args.target
    new_name = getattr(args, "name", None)
    new_role = getattr(args, "role", None)
    clear = getattr(args, "clear", False)

    registry = AgentRegistry()
    agent_info = registry.resolve_agent(target)

    if agent_info is None:
        print(f"Agent not found: {target}")
        print("Run 'synapse list' to see running agents.")
        sys.exit(1)

    agent_id: str = agent_info["agent_id"]

    # Check name uniqueness if setting a new name
    if new_name and not registry.is_name_unique(new_name, exclude_agent_id=agent_id):
        print(f"Name '{new_name}' is already taken by another agent.")
        sys.exit(1)

    # Update name and/or role
    result = registry.update_name(agent_id, new_name, role=new_role, clear=clear)

    if result:
        if clear:
            print(f"Cleared name and role for {agent_id}")
        else:
            updated = []
            if new_name:
                updated.append(f"name='{new_name}'")
            if new_role:
                updated.append(f"role='{new_role}'")
            if updated:
                print(f"Updated {agent_id}: {', '.join(updated)}")
            else:
                print(f"No changes made to {agent_id}")
    else:
        print(f"Failed to update {agent_id}")
        sys.exit(1)


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


def _print_history_table(observations: list[dict]) -> None:
    """Print observations in a formatted table."""
    hdr = f"{'Task ID':<36} {'Agent':<10} {'Status':<12} {'Timestamp':<19}"
    print(f"{hdr} {'Input (first 40 chars)':<42}")
    print("-" * 119)

    for obs in observations:
        task_id = obs["task_id"][:36]
        agent = obs["agent_name"][:10]
        status = obs["status"][:12]
        timestamp = obs["timestamp"][:19] if obs["timestamp"] else "N/A"
        input_preview = (
            obs["input"][:40].replace("\n", " ") if obs["input"] else "(empty)"
        )
        row = f"{task_id:<36} {agent:<10} {status:<12} {timestamp:<19}"
        print(f"{row} {input_preview:<42}")


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

    _print_history_table(observations)

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

    _print_history_table(observations)

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
        count = result["deleted_count"]
        print(f"Deleted {count} observations older than {args.days} days")
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
        hdr = f"{'Agent':<10} {'Total':<8} {'Completed':<10} {'Failed':<8}"
        print(f"{hdr} {'Canceled':<8}")
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
    sender = getattr(args, "sender", None)
    want_response = getattr(args, "want_response", None)

    # Get the a2a.py tool path from installed package
    import synapse

    package_dir = Path(synapse.__file__).parent
    a2a_tool = package_dir / "tools" / "a2a.py"

    cmd = [
        sys.executable,
        str(a2a_tool),
        "send",
        "--target",
        target,
        "--priority",
        str(priority),
        message,
    ]

    # Add sender if specified
    if sender:
        cmd.extend(["--from", sender])

    # Pass response flag to a2a.py (unified with a2a.py send)
    if want_response is True:
        cmd.append("--response")
    elif want_response is False:
        cmd.append("--no-response")
    # If None, don't pass any flag (a2a.py defaults to --response)

    result = subprocess.run(cmd, capture_output=True, text=True)
    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)


def cmd_reply(args: argparse.Namespace) -> None:
    """Reply to the last received A2A message using reply tracking."""
    message = args.message
    sender = getattr(args, "sender", None)

    # Get the a2a.py tool path from installed package
    import synapse

    package_dir = Path(synapse.__file__).parent
    a2a_tool = package_dir / "tools" / "a2a.py"

    cmd = [
        sys.executable,
        str(a2a_tool),
        "reply",
        message,
    ]

    # Add sender if specified
    if sender:
        cmd.extend(["--from", sender])

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    if result.returncode != 0:
        sys.exit(result.returncode)


# ============================================================
# Instructions Commands
# ============================================================


def cmd_instructions_show(args: argparse.Namespace) -> None:
    """Show instruction content for an agent type."""
    from synapse.commands.instructions import InstructionsCommand

    cmd = InstructionsCommand()
    agent_type = getattr(args, "agent_type", None)
    cmd.show(agent_type=agent_type)


def cmd_instructions_files(args: argparse.Namespace) -> None:
    """List instruction files for an agent type."""
    from synapse.commands.instructions import InstructionsCommand

    cmd = InstructionsCommand()
    agent_type = getattr(args, "agent_type", None)
    cmd.files(agent_type=agent_type)


def cmd_instructions_send(args: argparse.Namespace) -> None:
    """Send initial instructions to a running agent."""
    from synapse.commands.instructions import InstructionsCommand

    cmd = InstructionsCommand()
    success = cmd.send(target=args.target, preview=args.preview)
    if not success:
        sys.exit(1)


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
    import os

    from synapse.file_safety import FileSafetyManager

    manager = FileSafetyManager.from_env()

    if not manager.enabled:
        print("File safety is disabled. Enable with: SYNAPSE_FILE_SAFETY_ENABLED=true")
        return

    # Get locks with stale information
    locks = manager.list_locks(
        agent_name=args.agent if hasattr(args, "agent") and args.agent else None,
        agent_type=args.type if hasattr(args, "type") and args.type else None,
        include_stale=True,
    )

    if not locks:
        print("No active file locks.")
        return

    # Check for stale locks
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

        # Determine if lock is stale
        if pid:
            is_alive = manager._is_process_running(pid)
            status = "LIVE" if is_alive else "STALE"
            if is_alive:
                live_count += 1
            else:
                stale_count += 1
        else:
            status = "UNKNOWN"
            live_count += 1  # Assume old locks without PID are live

        pid_str = str(pid) if pid else "-"
        print(f"{file_path:<40} {agent:<20} {pid_str:<8} {status:<8} {expires:<20}")

    print(f"\nTotal: {len(locks)} locks ({live_count} live, {stale_count} stale)")

    if stale_count > 0:
        print(f"\nWarning: {stale_count} stale lock(s) from dead processes detected.")
        print("Run 'synapse file-safety cleanup-locks' to clean them up.")


def _resolve_agent_info(
    agent_name: str,
) -> tuple[str, str | None, int | None]:
    """Resolve agent name to (agent_id, agent_type, pid).

    Lookup order:
    1. Exact match by agent_id in registry
    2. Match by agent_type (short name like "claude") in live agents
    3. Parse agent_type from agent_id format "synapse-{type}-{port}"

    Returns:
        Tuple of (agent_id, agent_type, pid). agent_type and pid may be None.
    """
    from synapse.registry import AgentRegistry

    agent_id = agent_name
    agent_type = None
    pid = None

    with contextlib.suppress(Exception):
        registry = AgentRegistry()
        agent_info = registry.get_agent(agent_id)

        # Try to find by agent_type if exact match fails
        if not agent_info:
            for aid, info in registry.get_live_agents().items():
                if info.get("agent_type") == agent_id:
                    agent_info = info
                    agent_id = aid
                    break

        if agent_info:
            pid = agent_info.get("pid")
            agent_type = agent_info.get("agent_type")

    # Fallback: extract agent_type from agent_id format "synapse-{type}-{port}"
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
        print("File safety is disabled. Enable with: SYNAPSE_FILE_SAFETY_ENABLED=true")
        return

    agent_id, agent_type, pid = _resolve_agent_info(args.agent)

    result = manager.acquire_lock(
        file_path=args.file,
        agent_id=agent_id,
        agent_type=agent_type,
        task_id=args.task_id if hasattr(args, "task_id") else None,
        duration_seconds=args.duration if hasattr(args, "duration") else None,
        intent=args.intent if hasattr(args, "intent") else None,
        pid=pid,
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

    force = getattr(args, "force", False)
    agent = getattr(args, "agent", None)

    if not force and not agent:
        print("Error: Agent name is required unless using --force", file=sys.stderr)
        sys.exit(1)

    if force:
        # Force unlock regardless of owner
        if manager.force_unlock(args.file):
            print(f"Lock force-released on {args.file}")
        else:
            print(f"No lock found for {args.file}")
            sys.exit(1)
    else:
        # Normal unlock (requires agent ownership)
        # agent is guaranteed to be str here due to earlier check
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
        print("File safety is disabled. Enable with: SYNAPSE_FILE_SAFETY_ENABLED=true")
        return

    # First show what will be cleaned
    stale_locks = manager.get_stale_locks()

    if not stale_locks:
        print("No stale locks found.")
        return

    print(f"Found {len(stale_locks)} stale lock(s) from dead processes:")
    for lock in stale_locks:
        pid = lock.get("pid")
        agent = lock.get("agent_id")
        print(f"  - {lock['file_path']} (pid={pid}, agent={agent})")

    # Check for --force or prompt for confirmation
    force = getattr(args, "force", False)
    if not force:
        response = input("\nClean up these locks? [y/N]: ").strip().lower()
        if response != "y":
            print("Aborted.")
            return

    # Clean up
    cleaned = manager.cleanup_stale_locks()
    print(f"\nCleaned up {cleaned} stale lock(s).")


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


def _copy_synapse_templates(target_dir: Path) -> bool:
    """
    Copy template files from synapse/templates/.synapse/ to target directory.

    This copies all template files including settings.json, default.md,
    file-safety.md, etc. to the target .synapse/ directory.

    Uses atomic replacement to avoid data loss:
    1. Copy templates to a temporary directory
    2. If target exists, back it up
    3. Rename temp to target
    4. Clean up backup on success

    Args:
        target_dir: Target directory path (e.g., ~/.synapse or ./.synapse)

    Returns:
        True if successful, False otherwise.
    """
    import tempfile

    try:
        # Find templates directory relative to synapse package
        import synapse

        package_dir = Path(synapse.__file__).parent
        templates_dir = package_dir / "templates" / ".synapse"

        if not templates_dir.exists():
            print(f"Error: Templates directory not found: {templates_dir}")
            return False

        # Create temp directory in same parent for atomic rename
        parent_dir = target_dir.parent
        parent_dir.mkdir(parents=True, exist_ok=True)

        tmp_dir = Path(tempfile.mkdtemp(dir=parent_dir, prefix=".synapse_tmp_"))
        backup_dir = target_dir.with_suffix(".bak")

        try:
            # Step 1: Copy templates to temp directory
            # Remove the mkdtemp-created dir first, copytree needs non-existent target
            tmp_dir.rmdir()
            shutil.copytree(templates_dir, tmp_dir)

            # Step 2: If target exists, back it up
            if target_dir.exists():
                # Remove old backup if exists
                if backup_dir.exists():
                    shutil.rmtree(backup_dir)
                target_dir.rename(backup_dir)

            # Step 3: Rename temp to target (atomic on same filesystem)
            tmp_dir.rename(target_dir)

            # Step 4: Clean up backup on success
            if backup_dir.exists():
                shutil.rmtree(backup_dir)

            return True

        except Exception as e:
            # Restore from backup if something went wrong
            if backup_dir.exists() and not target_dir.exists():
                try:
                    backup_dir.rename(target_dir)
                except OSError:
                    print(f"Warning: Failed to restore backup from {backup_dir}")

            # Clean up temp directory if it still exists
            if tmp_dir.exists():
                with contextlib.suppress(OSError):
                    shutil.rmtree(tmp_dir)

            raise e

    except OSError as e:
        print(f"Error copying templates: {e}")
        return False


def _copy_claude_skills_to_codex(base_dir: Path, force: bool = False) -> list[str]:
    """
    Copy synapse-a2a skills from .claude to .codex directory.

    Claude Code supports skills via skills.sh:
        npx skills add s-hiraoku/synapse-a2a

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
    """Initialize .synapse/ directory with settings and template files."""
    scope = getattr(args, "scope", None)

    # If scope not provided via flag, prompt interactively
    if scope is None:
        scope = _prompt_scope_selection()

    if scope is None:
        print("Cancelled.")
        return

    # Determine paths based on scope
    if scope == "user":
        synapse_dir = Path.home() / ".synapse"
        skills_base = Path.home()
    else:  # project
        synapse_dir = Path.cwd() / ".synapse"
        skills_base = Path.cwd()

    # Check if .synapse directory already exists
    if synapse_dir.exists():
        response = (
            input(f"\n{synapse_dir} already exists. Overwrite? (y/N): ").strip().lower()
        )
        if response not in ("y", "yes"):
            print("Cancelled.")
            return

    # Copy template files to .synapse directory
    if _copy_synapse_templates(synapse_dir):
        print(f"✔ Created {synapse_dir}")
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


def cmd_config(args: argparse.Namespace) -> None:
    """Interactive configuration management."""
    import sys

    scope = getattr(args, "scope", None)
    no_rich = getattr(args, "no_rich", False)

    # Use Rich TUI if stdout is TTY and not explicitly disabled
    use_rich = sys.stdout.isatty() and not no_rich

    if use_rich:
        from synapse.commands.config import RichConfigCommand

        # Default to user scope if not specified
        rich_cmd = RichConfigCommand(scope=scope or "user")
        rich_cmd.run()
    else:
        from synapse.commands.config import ConfigCommand

        legacy_cmd = ConfigCommand()
        legacy_cmd.run(scope=scope)


def cmd_config_show(args: argparse.Namespace) -> None:
    """Show current settings."""
    from synapse.commands.config import ConfigCommand

    cmd = ConfigCommand()
    scope = getattr(args, "scope", None)
    cmd.show(scope=scope)


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


def interactive_agent_setup(agent_id: str, port: int) -> tuple[str | None, str | None]:
    """Interactively prompt for agent name and role.

    Args:
        agent_id: The agent ID (e.g., synapse-claude-8100).
        port: The port number.

    Returns:
        Tuple of (name, role), either or both may be None.
    """
    import contextlib
    import sys

    # Enable readline for line editing (backspace, arrow keys, etc.)
    with contextlib.suppress(ImportError):
        import readline  # noqa: F401 - enables line editing for input()

    # Save original terminal settings to restore later
    original_settings = None
    termios = None
    try:
        import termios as termios_module

        termios = termios_module
        if sys.stdin.isatty():
            with contextlib.suppress(termios.error):
                original_settings = termios.tcgetattr(sys.stdin)
    except ImportError:
        pass  # termios not available on Windows

    print("\n\x1b[32m[Synapse]\x1b[0m Agent Setup")
    print("=" * 80)
    print(f"Agent ID: {agent_id} | Port: {port}")
    print()
    print("Would you like to give this agent a name? (optional)")
    print("Name allows you to call this agent by name instead of ID.")
    print('Example: synapse send my-claude "hello"')
    print()

    try:
        name = input("Name [Enter to skip]: ").strip() or None

        print()
        print("Would you like to assign a role? (optional)")
        print("Role is a free-form description of this agent's responsibility.")
        print('Example: "test writer", "code reviewer", "documentation"')
        print()

        role = input("Role [Enter to skip]: ").strip() or None

        print("=" * 80)
        if name or role:
            name_str = name if name else agent_id
            role_str = f" | Role: {role}" if role else ""
            print(f"Agent: {name_str}{role_str}")
        print()

        return name, role

    except (EOFError, KeyboardInterrupt):
        print("\n\x1b[33m[Synapse]\x1b[0m Setup skipped")
        return None, None
    finally:
        # Restore original terminal settings
        if original_settings is not None and termios is not None:
            with contextlib.suppress(termios.error):
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, original_settings)


def cmd_run_interactive(
    profile: str,
    port: int,
    tool_args: list | None = None,
    name: str | None = None,
    role: str | None = None,
    no_setup: bool = False,
) -> None:
    """Run an agent in interactive mode with A2A server.

    Handles agent I/O directly via PTY. The approval flow determines whether
    to show a confirmation prompt before sending initial instructions
    (approvalMode: "required") or skip it (approvalMode: "auto").

    Waits for agent TUI readiness using either input_ready_pattern detection
    or timeout-based fallback before sending initial instructions.

    Args:
        profile: Agent profile name (claude, codex, gemini, etc.)
        port: Port number for the A2A server.
        tool_args: Arguments to pass to the underlying CLI tool.
        name: Optional custom name for the agent.
        role: Optional role description for the agent.
        no_setup: If True, skip interactive setup prompt.
    """
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

    command = config.get("command")
    if not command:
        print(f"Error: Profile '{profile}' is missing 'command' field.")
        sys.exit(1)
    if not resolve_command_path(command):
        print(f"Error: Required command '{command}' is not installed or not on PATH.")
        print("  Hint: Install it and try again.")
        sys.exit(1)

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

    # Parse waiting detection config
    waiting_detection = config.get("waiting_detection", {})

    # Parse input ready pattern for initial instruction timing
    input_ready_pattern = config.get("input_ready_pattern")

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

    # Show startup animation before approval prompt
    from synapse.startup_tui import show_startup_animation

    show_startup_animation(
        agent_type=profile,
        agent_id=agent_id,
        port=port,
    )

    # Interactive agent setup (name/role) if not provided via CLI
    agent_name = name
    agent_role = role
    if not no_setup and name is None and role is None and sys.stdin.isatty():
        agent_name, agent_role = interactive_agent_setup(agent_id, port)

    # Check if approval is required for initial instructions
    skip_initial_instructions = is_resume
    if not is_resume and synapse_settings.should_require_approval():
        from synapse.approval import prompt_for_approval

        response = prompt_for_approval(
            agent_id=agent_id,
            port=port,
        )

        if response == "abort":
            print("\x1b[33m[Synapse]\x1b[0m Aborted by user")
            sys.exit(0)
        elif response == "skip":
            print("\x1b[32m[Synapse]\x1b[0m Starting without initial instructions")
            skip_initial_instructions = True

    # Set SYNAPSE env vars for sender identification (same as server.py)
    env["SYNAPSE_AGENT_ID"] = agent_id
    env["SYNAPSE_AGENT_TYPE"] = profile
    env["SYNAPSE_PORT"] = str(port)

    # Create controller - initial instructions sent on IDLE (unless resume mode)
    controller = TerminalController(
        command=config["command"],
        args=all_args,
        idle_detection=idle_detection if idle_detection else None,
        waiting_detection=waiting_detection if waiting_detection else None,
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
        skip_initial_instructions=skip_initial_instructions,
        input_ready_pattern=input_ready_pattern,
        name=name,
        role=role,
    )

    # Handle Ctrl+C gracefully
    def cleanup(signum: int, frame: object) -> None:
        print("\n\x1b[32m[Synapse]\x1b[0m Shutting down...")
        registry.unregister(agent_id)
        controller.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    try:
        # Start the API server in background (TCP + UDS)
        import threading

        import uvicorn

        from synapse.registry import resolve_uds_path
        from synapse.server import create_app

        app = create_app(
            controller,
            registry,
            agent_id,
            port,
            submit_seq,
            agent_type=profile,
        )

        # Setup UDS server (directory created by resolve_uds_path)
        uds_path = resolve_uds_path(agent_id)
        uds_path.unlink(missing_ok=True)

        uds_config = uvicorn.Config(app, uds=str(uds_path), log_level="warning")
        uds_config.lifespan = "off"
        uds_server = uvicorn.Server(uds_config)

        def run_uds_server() -> None:
            uds_server.run()

        uds_thread = threading.Thread(target=run_uds_server, daemon=True)
        uds_thread.start()

        # Setup TCP server
        def run_tcp_server() -> None:
            uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")

        tcp_thread = threading.Thread(target=run_tcp_server, daemon=True)
        tcp_thread.start()

        # Give servers time to start
        time.sleep(1)

        # Register agent after listeners are up (UDS first, then TCP)
        registry.register(
            agent_id,
            profile,
            port,
            status="PROCESSING",
            name=agent_name,
            role=agent_role,
        )

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

    # Check for shortcut: synapse claude [--port PORT] [--name NAME] [--role ROLE]
    #                     [--no-setup] [-- TOOL_ARGS...]
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

        # Helper to parse a flag with value
        def parse_arg(flag: str) -> str | None:
            if flag in synapse_args:
                idx = synapse_args.index(flag)
                if idx + 1 < len(synapse_args):
                    return synapse_args[idx + 1]
            return None

        # Parse --port from synapse_args
        port = None
        port_str = parse_arg("--port")
        if port_str:
            try:
                port = int(port_str)
            except ValueError:
                print(f"Invalid port: {port_str}")
                sys.exit(1)

        # Parse --name and --role from synapse_args
        name = parse_arg("--name") or parse_arg("-n")
        role = parse_arg("--role") or parse_arg("-r")
        no_setup = "--no-setup" in synapse_args

        # Auto-select available port if not specified
        if port is None:
            registry = AgentRegistry()
            port_manager = PortManager(registry)
            port = port_manager.get_available_port(profile)

            if port is None:
                print(port_manager.format_exhaustion_error(profile))
                sys.exit(1)

        assert port is not None  # Type narrowing for mypy/ty
        cmd_run_interactive(
            profile, port, tool_args, name=name, role=role, no_setup=no_setup
        )
        return

    from importlib.metadata import version

    try:
        pkg_version = version("synapse-a2a")
    except Exception:
        pkg_version = "unknown"

    parser = argparse.ArgumentParser(
        description="""Synapse A2A - Multi-Agent Collaboration Framework

Synapse wraps CLI agents (Claude Code, Codex, Gemini) with Google A2A Protocol,
enabling seamless inter-agent communication and task delegation.""",
        prog="synapse",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  synapse claude                    Start Claude agent (interactive mode)
  synapse gemini --port 8111        Start Gemini on specific port
  synapse claude -- --continue      Pass --continue flag to Claude Code
  synapse list -w                   Watch running agents in real-time
  synapse send codex "Review this"  Send message to Codex agent
  synapse history list              View task history

Environment Variables:
  SYNAPSE_HISTORY_ENABLED=true      Enable task history tracking
  SYNAPSE_FILE_SAFETY_ENABLED=true  Enable file locking for multi-agent safety
  SYNAPSE_AUTH_ENABLED=true         Enable API key authentication

Documentation: https://github.com/s-hiraoku/synapse-a2a""",
    )
    parser.add_argument(
        "--version", "-V", action="version", version=f"%(prog)s {pkg_version}"
    )
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")

    # start (background)
    p_start = subparsers.add_parser(
        "start",
        help="Start an agent in background mode",
        description="Start an agent as a background daemon process with A2A server.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  synapse start claude              Start Claude in background
  synapse start gemini --port 8111  Start Gemini on specific port
  synapse start claude -f           Start in foreground (attached)
  synapse start claude -- --resume  Pass --resume to Claude Code""",
    )
    p_start.add_argument(
        "profile",
        help="Agent profile to start (claude, codex, gemini, dummy)",
    )
    p_start.add_argument(
        "--port",
        type=int,
        help="A2A server port (default: auto-assigned from profile range)",
    )
    p_start.add_argument(
        "--foreground", "-f", action="store_true", help="Run in foreground (attached)"
    )
    p_start.add_argument("--ssl-cert", help="SSL certificate file for HTTPS")
    p_start.add_argument("--ssl-key", help="SSL private key file for HTTPS")
    p_start.add_argument(
        "tool_args",
        nargs=argparse.REMAINDER,
        help="Arguments after -- are passed to the underlying CLI tool",
    )
    p_start.set_defaults(func=cmd_start)

    # stop
    p_stop = subparsers.add_parser(
        "stop",
        help="Stop a running agent",
        description="""Stop a running agent by profile name or specific agent ID.

You can specify either:
  - Profile name (claude, codex, gemini): Stops instances of that profile
  - Agent ID (synapse-claude-8100): Stops the specific agent instance

Use 'synapse list' to see running agents and their IDs.""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  synapse stop claude                  Stop the oldest Claude instance
  synapse stop gemini -a               Stop all Gemini instances
  synapse stop synapse-claude-8100     Stop specific agent by ID
  synapse stop synapse-codex-8120      Stop specific Codex instance

Tip: Copy the agent ID from 'synapse list' output for precise control.""",
    )
    p_stop.add_argument(
        "target",
        metavar="TARGET",
        help="Profile name (claude, codex, gemini) or agent ID (synapse-claude-8100)",
    )
    p_stop.add_argument(
        "--all",
        "-a",
        action="store_true",
        help="Stop all instances of the specified profile (ignored for agent IDs)",
    )
    p_stop.set_defaults(func=cmd_stop)

    # kill
    p_kill = subparsers.add_parser(
        "kill",
        help="Kill a running agent immediately",
        description="""Kill a running agent by name, ID, or type.

Target resolution priority:
  1. Custom name (my-claude) - highest priority
  2. Full agent ID (synapse-claude-8100)
  3. Type-port shorthand (claude-8100)
  4. Type (claude) - only if single instance""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  synapse kill my-claude            Kill agent by custom name
  synapse kill synapse-claude-8100  Kill agent by ID
  synapse kill claude-8100          Kill agent by type-port
  synapse kill claude               Kill agent by type (if only one)
  synapse kill claude -f            Kill without confirmation

Tip: Use 'synapse list' to see running agents with their names and IDs.""",
    )
    p_kill.add_argument(
        "target",
        metavar="TARGET",
        help="Agent name, ID (synapse-claude-8100), type-port (claude-8100), or type",
    )
    p_kill.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Kill without confirmation prompt",
    )
    p_kill.set_defaults(func=cmd_kill)

    # jump
    p_jump = subparsers.add_parser(
        "jump",
        help="Jump to an agent's terminal",
        description="""Jump to the terminal window running a specific agent.

Target resolution priority:
  1. Custom name (my-claude) - highest priority
  2. Full agent ID (synapse-claude-8100)
  3. Type-port shorthand (claude-8100)
  4. Type (claude) - only if single instance

Supported terminals: iTerm2, Terminal.app, Ghostty, VS Code, tmux, Zellij""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  synapse jump my-claude            Jump by custom name
  synapse jump synapse-claude-8100  Jump by agent ID
  synapse jump claude-8100          Jump by type-port
  synapse jump claude               Jump by type (if only one)""",
    )
    p_jump.add_argument(
        "target",
        metavar="TARGET",
        help="Agent name, ID (synapse-claude-8100), type-port (claude-8100), or type",
    )
    p_jump.set_defaults(func=cmd_jump)

    # rename
    p_rename = subparsers.add_parser(
        "rename",
        help="Assign name and role to an agent",
        description="""Assign or update a custom name and/or role for a running agent.

Name allows you to call an agent by a custom name instead of its ID.
Role is a free-form description of the agent's responsibility.

Target resolution priority:
  1. Custom name (my-claude) - highest priority
  2. Full agent ID (synapse-claude-8100)
  3. Type-port shorthand (claude-8100)
  4. Type (claude) - only if single instance""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  synapse rename synapse-claude-8100 --name my-claude
  synapse rename my-claude --role "Code reviewer"
  synapse rename claude --name reviewer --role "Reviews all PRs"
  synapse rename my-claude --clear    Clear name and role""",
    )
    p_rename.add_argument(
        "target",
        metavar="TARGET",
        help="Agent name, ID (synapse-claude-8100), type-port (claude-8100), or type",
    )
    p_rename.add_argument(
        "--name",
        "-n",
        help="Custom name for the agent",
    )
    p_rename.add_argument(
        "--role",
        "-r",
        help="Role description for the agent",
    )
    p_rename.add_argument(
        "--clear",
        "-c",
        action="store_true",
        help="Clear name and role",
    )
    p_rename.set_defaults(func=cmd_rename)

    # list
    p_list = subparsers.add_parser(
        "list",
        help="List running agents",
        description="Show all running Synapse agents with their status and ports.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  synapse list              Show running agents (Rich TUI with auto-update)

Interactive controls:
  1-9         Select agent by number
  ↑/↓         Navigate selection
  Enter/j     Jump to terminal
  k           Kill agent (with confirmation)
  /           Filter by TYPE or WORKING_DIR
  ESC         Clear filter/selection
  q           Quit

Status meanings:
  READY       Agent is idle and waiting for input
  WAITING     Agent is showing selection UI
  PROCESSING  Agent is actively processing a task
  DONE        Task completed (auto-transitions to READY)""",
    )
    p_list.set_defaults(func=cmd_list)

    # logs
    p_logs = subparsers.add_parser(
        "logs",
        help="Show agent logs",
        description="View log output for a specific agent profile.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  synapse logs claude        Show last 50 lines of Claude logs
  synapse logs gemini -f     Follow Gemini logs in real-time
  synapse logs codex -n 100  Show last 100 lines

Log files are stored in: ~/.synapse/logs/""",
    )
    p_logs.add_argument("profile", help="Agent profile (claude, codex, gemini)")
    p_logs.add_argument(
        "-f", "--follow", action="store_true", help="Follow log output (like tail -f)"
    )
    p_logs.add_argument(
        "-n",
        "--lines",
        type=int,
        default=50,
        help="Number of lines to show (default: 50)",
    )
    p_logs.set_defaults(func=cmd_logs)

    # send
    p_send = subparsers.add_parser(
        "send",
        help="Send a message to an agent",
        description="Send an A2A message to a running agent.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  synapse send claude "Hello"            Send message to Claude
  synapse send codex "Review this" -p 3  Send with normal priority
  synapse send gemini "Write tests" -p 5 Send with critical priority

Priority levels:
  1-2  Low priority, background tasks
  3    Normal tasks (default: 1)
  4    Urgent follow-ups
  5    Critical/emergency tasks""",
    )
    p_send.add_argument("target", help="Target agent (claude, codex, gemini)")
    p_send.add_argument("message", help="Message to send")
    p_send.add_argument(
        "--priority", "-p", type=int, default=1, help="Priority level 1-5 (default: 1)"
    )
    p_send.add_argument(
        "--from", "-f", dest="sender", help="Sender agent ID (for reply identification)"
    )
    # Response control: mutually exclusive group (unified with a2a.py send)
    response_group = p_send.add_mutually_exclusive_group()
    response_group.add_argument(
        "--response",
        dest="want_response",
        action="store_true",
        default=None,
        help="Wait for and receive response from target agent",
    )
    response_group.add_argument(
        "--no-response",
        dest="want_response",
        action="store_false",
        help="Do not wait for response (fire and forget)",
    )
    p_send.set_defaults(func=cmd_send)

    # reply - Reply to last received A2A message
    p_reply = subparsers.add_parser(
        "reply",
        help="Reply to the last received A2A message",
        description="Reply to the last received A2A message using reply tracking.",
        epilog="""Examples:
  synapse reply "Here is my response"      Reply to the last message
  synapse reply "Task completed!"          Send completion reply
  synapse reply "Done" --from codex        Reply with explicit sender (for sandboxed envs)""",
    )
    p_reply.add_argument(
        "--from",
        dest="sender",
        help="Your agent ID (required in sandboxed environments like Codex)",
    )
    p_reply.add_argument("message", help="Reply message content")
    p_reply.set_defaults(func=cmd_reply)

    # instructions - Manage and send initial instructions
    p_instructions = subparsers.add_parser(
        "instructions",
        help="Manage and send initial instructions to agents",
        description="""Manage and send initial instructions to running agents.

Initial instructions are automatically sent when agents start, but can be
re-sent manually using this command (useful for --resume mode or recovery).""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  synapse instructions show                   Show default instruction
  synapse instructions show claude            Show Claude's instruction
  synapse instructions files claude           List instruction files
  synapse instructions send claude            Send instructions to Claude
  synapse instructions send synapse-claude-8100  Send to specific agent
  synapse instructions send claude --preview  Preview without sending""",
    )
    instructions_subparsers = p_instructions.add_subparsers(
        dest="instructions_command", metavar="SUBCOMMAND"
    )

    # instructions show
    p_inst_show = instructions_subparsers.add_parser(
        "show", help="Show instruction content"
    )
    p_inst_show.add_argument(
        "agent_type",
        nargs="?",
        help="Agent type (claude, gemini, codex). If omitted, shows default.",
    )
    p_inst_show.set_defaults(func=cmd_instructions_show)

    # instructions files
    p_inst_files = instructions_subparsers.add_parser(
        "files", help="List instruction files"
    )
    p_inst_files.add_argument(
        "agent_type",
        nargs="?",
        help="Agent type (claude, gemini, codex). If omitted, shows default.",
    )
    p_inst_files.set_defaults(func=cmd_instructions_files)

    # instructions send
    p_inst_send = instructions_subparsers.add_parser(
        "send", help="Send instructions to a running agent"
    )
    p_inst_send.add_argument(
        "target",
        help="Target agent: profile name (claude, codex, gemini) or agent ID",
    )
    p_inst_send.add_argument(
        "--preview",
        "-p",
        action="store_true",
        help="Preview instruction without sending",
    )
    p_inst_send.set_defaults(func=cmd_instructions_send)

    # history - Task history management
    p_history = subparsers.add_parser(
        "history",
        help="View and manage task history",
        description="""View and manage A2A task history.

Requires SYNAPSE_HISTORY_ENABLED=true to be set.""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  synapse history list                  List recent tasks
  synapse history list -a claude -n 20  List 20 Claude tasks
  synapse history show <task_id>        Show task details
  synapse history search "test"         Search for tasks
  synapse history stats                 Show usage statistics
  synapse history export -f csv -o tasks.csv  Export to CSV""",
    )
    history_subparsers = p_history.add_subparsers(
        dest="history_command", metavar="SUBCOMMAND"
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
    p_external = subparsers.add_parser(
        "external",
        help="Manage external A2A agents",
        description="""Connect to and manage external A2A-compatible agents.

External agents are non-local agents accessible via HTTP/HTTPS.""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  synapse external add https://agent.example.com -a myagent
  synapse external list
  synapse external send myagent "Hello"
  synapse external info myagent
  synapse external remove myagent""",
    )
    external_subparsers = p_external.add_subparsers(
        dest="external_command", metavar="SUBCOMMAND"
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
    p_auth = subparsers.add_parser(
        "auth",
        help="Manage API key authentication",
        description="""Generate and manage API keys for secure A2A communication.

Enable authentication with SYNAPSE_AUTH_ENABLED=true.""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  synapse auth setup         Generate keys and show setup instructions
  synapse auth generate-key  Generate a single API key
  synapse auth generate-key -n 3 -e  Generate 3 keys in export format""",
    )
    auth_subparsers = p_auth.add_subparsers(dest="auth_command", metavar="SUBCOMMAND")

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
        "init",
        help="Initialize Synapse configuration",
        description="""Initialize .synapse/settings.json with default configuration.

Creates settings file and copies skills to .codex (if .claude skills exist).""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  synapse init              Interactive scope selection
  synapse init --scope user     Create ~/.synapse/settings.json
  synapse init --scope project  Create ./.synapse/settings.json""",
    )
    p_init.add_argument(
        "--scope",
        choices=["user", "project"],
        help="Scope: user (~/.synapse) or project (./.synapse)",
    )
    p_init.set_defaults(func=cmd_init)

    # reset - Reset settings to defaults
    p_reset = subparsers.add_parser(
        "reset",
        help="Reset Synapse configuration to defaults",
        description="""Reset .synapse/settings.json to default values.

Also re-copies skills from .claude to .codex.""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  synapse reset                  Interactive scope selection
  synapse reset --scope user     Reset ~/.synapse/settings.json
  synapse reset --scope project  Reset ./.synapse/settings.json
  synapse reset --scope both -f  Reset both without confirmation""",
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

    # config - Interactive settings management
    p_config = subparsers.add_parser(
        "config",
        help="Interactive settings management",
        description="""Interactively configure Synapse settings using a TUI.

Opens an interactive menu to browse and modify settings in .synapse/settings.json.""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  synapse config                  Interactive mode (prompts for scope)
  synapse config --scope user     Edit user settings directly
  synapse config --scope project  Edit project settings directly
  synapse config show             Show merged settings (read-only)
  synapse config show --scope user  Show user settings only""",
    )
    p_config.add_argument(
        "--scope",
        choices=["user", "project"],
        help="Settings scope to edit (user or project)",
    )
    p_config.add_argument(
        "--no-rich",
        action="store_true",
        help="Use legacy questionary-based interface instead of Rich TUI",
    )
    p_config.set_defaults(func=cmd_config)

    # config subcommands
    config_subparsers = p_config.add_subparsers(
        dest="config_command", metavar="SUBCOMMAND"
    )

    # config show
    p_config_show = config_subparsers.add_parser(
        "show", help="Show current settings (read-only)"
    )
    p_config_show.add_argument(
        "--scope",
        choices=["user", "project", "merged"],
        default="merged",
        help="Settings scope to display (default: merged)",
    )
    p_config_show.set_defaults(func=cmd_config_show)

    # file-safety - File locking and modification tracking
    p_file_safety = subparsers.add_parser(
        "file-safety",
        help="File locking and modification tracking",
        description="""File locking and modification tracking for multi-agent safety.

Prevents file conflicts when multiple agents edit files simultaneously.
Requires SYNAPSE_FILE_SAFETY_ENABLED=true to be set.""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  synapse file-safety              Show status (default)
  synapse file-safety locks        List active file locks
  synapse file-safety lock src/main.py myagent  Acquire lock
  synapse file-safety unlock src/main.py myagent  Release lock
  synapse file-safety recent       Show recent modifications
  synapse file-safety history src/main.py  Show file history
  synapse file-safety debug        Show troubleshooting info""",
    )
    file_safety_subparsers = p_file_safety.add_subparsers(
        dest="file_safety_command", metavar="SUBCOMMAND"
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
    p_fs_locks.add_argument(
        "--type", "-t", help="Filter by agent type (claude, gemini, codex)"
    )
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
    p_fs_unlock.add_argument(
        "agent", nargs="?", help="Agent name releasing the lock (optional with --force)"
    )
    p_fs_unlock.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Force unlock regardless of owner",
    )
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

    # file-safety cleanup-locks
    p_fs_cleanup_locks = file_safety_subparsers.add_parser(
        "cleanup-locks", help="Clean up stale locks from dead processes"
    )
    p_fs_cleanup_locks.add_argument(
        "--force", "-f", action="store_true", help="Skip confirmation prompt"
    )
    p_fs_cleanup_locks.set_defaults(func=cmd_file_safety_cleanup_locks)

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

    # Handle instructions subcommand without action
    if args.command == "instructions" and (
        not hasattr(args, "instructions_command") or args.instructions_command is None
    ):
        p_instructions.print_help()
        sys.exit(1)

    # Handle file-safety subcommand without action (show status by default)
    if args.command == "file-safety" and (
        not hasattr(args, "file_safety_command") or args.file_safety_command is None
    ):
        cmd_file_safety_status(args)
        return

    args.func(args)


if __name__ == "__main__":
    main()
