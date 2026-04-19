#!/usr/bin/env python3
"""Synapse A2A CLI - Main entry point for agent management."""

from __future__ import annotations

import argparse
import contextlib
import errno
import json
import logging
import os
import shutil
import signal
import sqlite3
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Literal, cast

import yaml

from synapse.agent_profiles import (
    AgentProfileError,
    AgentProfileStore,
    suggest_petname_ids,
)
from synapse.auth import generate_api_key
from synapse.commands import history as history_commands
from synapse.commands import memory as memory_commands
from synapse.commands import messaging as messaging_commands
from synapse.commands.cleanup import cmd_cleanup
from synapse.commands.doctor import cmd_doctor
from synapse.commands.external import (
    cmd_external_add,
    cmd_external_info,
    cmd_external_list,
    cmd_external_remove,
    cmd_external_send,
)
from synapse.commands.file_safety_cmd import (
    cmd_file_safety_cleanup,
    cmd_file_safety_cleanup_locks,
    cmd_file_safety_debug,
    cmd_file_safety_history,
    cmd_file_safety_lock,
    cmd_file_safety_locks,
    cmd_file_safety_recent,
    cmd_file_safety_record,
    cmd_file_safety_status,
    cmd_file_safety_unlock,
)
from synapse.commands.history import (
    cmd_history_cleanup,
    cmd_history_export,
    cmd_history_list,
    cmd_history_search,
    cmd_history_show,
    cmd_history_stats,
    cmd_trace,
)
from synapse.commands.list import ListCommand
from synapse.commands.memory import (
    cmd_memory_delete,
    cmd_memory_list,
    cmd_memory_save,
    cmd_memory_search,
    cmd_memory_show,
    cmd_memory_stats,
)
from synapse.commands.messaging import (
    cmd_broadcast,
    cmd_interrupt,
    cmd_reply,
    cmd_send,
)
from synapse.commands.multiagent import (
    cmd_multiagent_init,
    cmd_multiagent_list,
    cmd_multiagent_run,
    cmd_multiagent_show,
    cmd_multiagent_status,
    cmd_multiagent_stop,
)
from synapse.commands.session import (
    cmd_session_delete,
    cmd_session_list,
    cmd_session_restore,
    cmd_session_save,
    cmd_session_sessions,
    cmd_session_show,
)
from synapse.commands.spawn_cmd import (
    _extract_tool_args,
    _warn_synapse_flags_in_tool_args,
    cmd_spawn,
    cmd_team_start,
)
from synapse.commands.start import StartCommand
from synapse.commands.workflow import (
    cmd_workflow_create,
    cmd_workflow_delete,
    cmd_workflow_list,
    cmd_workflow_run,
    cmd_workflow_show,
    cmd_workflow_status,
    cmd_workflow_sync,
)
from synapse.controller import TerminalController
from synapse.logging_config import setup_logging
from synapse.port_manager import (
    PORT_RANGES,
    PortManager,
    is_process_alive,
)
from synapse.registry import AgentRegistry, NameConflictError, is_port_open
from synapse.utils import resolve_command_path

# Known profiles (for shortcut detection)
KNOWN_PROFILES = set(PORT_RANGES.keys())
logger = logging.getLogger(__name__)

# Compatibility aliases used by tests and by command modules that still
# reference helper functions via ``synapse.cli``.
_get_history_manager = history_commands._get_history_manager
_memory_broadcast_notify = memory_commands._memory_broadcast_notify
_build_a2a_cmd = messaging_commands._build_a2a_cmd
_get_a2a_tool_path = messaging_commands._get_a2a_tool_path
_get_send_message_threshold = messaging_commands._get_send_message_threshold
_resolve_cli_message = messaging_commands._resolve_cli_message
_resolve_task_message = messaging_commands._resolve_task_message
_run_a2a_command = messaging_commands._run_a2a_command


def install_skills() -> None:
    """Install Synapse A2A skills to ~/.claude/skills/ and copy to ~/.agents/skills/."""
    try:
        import synapse

        package_dir = Path(synapse.__file__).parent
        skills_to_install = ["synapse-a2a", "synapse-reinst"]

        for skill_name in skills_to_install:
            claude_target = Path.home() / ".claude" / "skills" / skill_name

            # Skip if already installed in .claude
            if claude_target.exists():
                # Still try to copy to .agents if not present
                _copy_skill_to_agents(claude_target, skill_name)
                continue

            source_dir = package_dir / "skills" / skill_name

            if source_dir.exists():
                claude_target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(source_dir, claude_target)
                msg = f"Installed {skill_name} skill to {claude_target}"
                print(f"\x1b[32m[Synapse]\x1b[0m {msg}")
                # Copy to .agents as well
                _copy_skill_to_agents(claude_target, skill_name)
    except Exception:  # broad catch: best-effort skill install must never block startup
        pass


def _copy_skill_to_agents(
    source_dir: Path,
    skill_name: str,
    *,
    base_dir: Path | None = None,
    force: bool = False,
    quiet: bool = False,
) -> str | None:
    """Copy a skill to .agents/skills/ (Codex/OpenCode/Gemini/Copilot use .agents/skills/).

    Args:
        source_dir: Source skill directory to copy from.
        skill_name: Name of the skill (used as target directory name).
        base_dir: Base directory for .agents/. Defaults to Path.home().
        force: If True, overwrite existing skill.
        quiet: If True, suppress output messages.

    Returns the destination path string if copied, None otherwise.
    """
    try:
        target_base = base_dir or Path.home()
        agents_target = target_base / ".agents" / "skills" / skill_name
        if agents_target.exists() and not force:
            return None
        if agents_target.exists() and force:
            shutil.rmtree(agents_target)
        agents_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source_dir, agents_target)
        if not quiet:
            print(
                f"\x1b[32m[Synapse]\x1b[0m Copied {skill_name} skill to {agents_target}"
            )
        return str(agents_target)
    except OSError:
        return None


_START_COMMAND = StartCommand(subprocess_module=subprocess)


def cmd_start(args: argparse.Namespace) -> None:
    """Start an agent in background or foreground."""
    _START_COMMAND.run(args)


_STOP_SIGTERM_WAIT = 5  # seconds to wait for SIGTERM before SIGKILL


def _stop_agent(registry: AgentRegistry, info: dict) -> None:
    """Stop a single agent given its info dict.

    Sends SIGTERM, waits up to _STOP_SIGTERM_WAIT seconds for the process
    to exit, then escalates to SIGKILL if it is still alive.
    """
    agent_id = info.get("agent_id")
    pid = info.get("pid")

    if not pid:
        print(f"No PID found for {agent_id}")
        return

    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        print(f"Process {pid} not found. Cleaning up registry...")
        if isinstance(agent_id, str):
            registry.unregister(agent_id)
        return

    # Wait for process to exit after SIGTERM
    for _ in range(_STOP_SIGTERM_WAIT * 10):
        if not is_process_alive(pid):
            break
        time.sleep(0.1)

    if is_process_alive(pid):
        try:
            os.kill(pid, signal.SIGKILL)
            print(f"Escalated to SIGKILL for {agent_id} (PID: {pid})")
        except ProcessLookupError:
            pass
    else:
        print(f"Stopped {agent_id} (PID: {pid})")

    if isinstance(agent_id, str):
        registry.unregister(agent_id)


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


def _send_shutdown_request(agent_info: dict, timeout_seconds: int = 30) -> bool:
    """Send a graceful shutdown request to an agent via A2A message.

    Args:
        agent_info: Agent info dict with port, agent_id, etc.
        timeout_seconds: How long to wait for agent acknowledgment.

    Returns:
        True if agent acknowledged the shutdown, False on timeout/error.
    """
    port = agent_info.get("port")

    if not port:
        return False

    try:
        import httpx
    except ImportError:
        return False

    try:
        url = f"http://localhost:{port}/tasks/send"
        payload = {
            "message": {
                "role": "user",
                "parts": [
                    {
                        "type": "text",
                        "text": "Shutdown requested. Please save your work and prepare to exit.",
                    }
                ],
            },
            "metadata": {"type": "shutdown_request"},
        }
        headers = _get_auth_headers()

        # Use a short timeout for the HTTP request itself
        request_timeout = min(timeout_seconds, 10)
        response = httpx.post(
            url, json=payload, headers=headers, timeout=request_timeout
        )
        return bool(response.status_code == 200)
    except (httpx.HTTPError, OSError):
        return False


def _try_cleanup_worktree(agent_info: dict, merge: bool = False) -> None:
    """Clean up a worktree if the agent was running in one.

    Any exception is caught and logged so that callers (cmd_kill,
    cmd_run_interactive) are never interrupted by cleanup failures.
    """
    wt_path = agent_info.get("worktree_path")
    wt_branch = agent_info.get("worktree_branch")
    if not wt_path or not wt_branch:
        return

    try:
        from synapse.worktree import cleanup_worktree, worktree_info_from_registry

        wt_base = agent_info.get("worktree_base_branch", "")
        wt_info = worktree_info_from_registry(wt_path, wt_branch, wt_base)
        is_tty = sys.stdin.isatty() and sys.stdout.isatty()
        cleanup_worktree(wt_info, interactive=is_tty, merge=merge)
    except Exception:  # broad catch: cleanup must never interrupt callers
        logging.getLogger(__name__).warning(
            "Worktree cleanup failed for %s", wt_path, exc_info=True
        )


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
        else:
            print(f"Agent not found: {target}")
            print("Run 'synapse list' to see running agents.")
        sys.exit(1)

    agent_id: str = agent_info["agent_id"]
    name = agent_info.get("name")
    pid = agent_info.get("pid")
    display_name = name or agent_id
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

    if not pid:
        print(f"No PID found for {display_name}")
        return

    # Check for graceful shutdown settings
    from synapse.settings import get_settings

    settings = get_settings()
    shutdown = settings.get_shutdown_settings()

    if not force and shutdown.get("graceful_enabled", True):
        timeout_seconds = shutdown.get("timeout_seconds", 30)

        # Budget the total timeout across phases: HTTP + grace + escalation
        http_timeout = min(timeout_seconds, 10)
        remaining = max(timeout_seconds - http_timeout, 0)
        grace_period = min(max(remaining // 3, 1), remaining)
        escalation_wait = max(remaining - grace_period, 0)

        # 1. Set status to SHUTTING_DOWN
        registry.update_status(agent_id, "SHUTTING_DOWN")

        # 2. Send graceful shutdown request via A2A
        logger.info(
            "event=graceful_shutdown_request agent_id=%s target=%s timeout_seconds=%s",
            agent_id,
            target,
            http_timeout,
        )
        print(f"Sending shutdown request to {display_name}...")
        acknowledged = _send_shutdown_request(agent_info, timeout_seconds=http_timeout)
        logger.info(
            "event=graceful_shutdown_result agent_id=%s target=%s acknowledged=%s",
            agent_id,
            target,
            acknowledged,
        )

        if acknowledged:
            print(f"Shutdown acknowledged by {display_name}.")
        else:
            print(f"No response from {display_name} after shutdown request.")

        # 3. Wait grace period then send SIGTERM
        print(f"Waiting {grace_period}s grace period before SIGTERM...")
        time.sleep(grace_period)

        try:
            os.kill(pid, signal.SIGTERM)
            print(f"Sent SIGTERM to {display_name} (PID: {pid})")
        except ProcessLookupError:
            print(f"Process {pid} already exited. Cleaning up registry...")

        # 4. Wait for process to exit, then escalate to SIGKILL if needed
        time.sleep(escalation_wait)

        if is_process_alive(pid):
            try:
                os.kill(pid, signal.SIGKILL)
                print(f"Escalated to SIGKILL for {display_name} (PID: {pid})")
            except ProcessLookupError:
                print(f"Process {pid} exited during escalation.")
    else:
        # Force kill or graceful disabled: use SIGKILL
        try:
            os.kill(pid, signal.SIGKILL)
            print(f"Killed {display_name} (PID: {pid})")
        except ProcessLookupError:
            print(f"Process {pid} not found. Cleaning up registry...")

    registry.unregister(agent_id)

    no_merge = getattr(args, "no_merge", False)
    _try_cleanup_worktree(agent_info, merge=not no_merge)


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
    display_name = name or agent_id

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


def cmd_set_summary(args: argparse.Namespace) -> None:
    """Set or clear an agent's work summary."""
    target = args.target
    clear = getattr(args, "clear", False)
    auto = getattr(args, "auto", False)
    summary_text = getattr(args, "summary", None)

    registry = AgentRegistry()
    agent_info = registry.resolve_agent(target)

    if agent_info is None:
        print(f"Agent not found: {target}")
        print("Run 'synapse list' to see running agents.")
        sys.exit(1)

    agent_id: str = agent_info["agent_id"]

    if clear:
        result = registry.update_summary(agent_id, None)
        if result:
            print(f"Cleared summary for {agent_id}")
        else:
            print(f"Failed to clear summary for {agent_id}")
            sys.exit(1)
        return

    if auto:
        # Auto-generate from git info
        working_dir = agent_info.get("working_dir", os.getcwd())
        try:
            branch = subprocess.check_output(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=working_dir,
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
            try:
                files_output = subprocess.check_output(
                    ["git", "diff", "--name-only", "HEAD~1"],
                    cwd=working_dir,
                    text=True,
                    stderr=subprocess.DEVNULL,
                ).strip()
            except subprocess.CalledProcessError:
                # Fallback for repos with a single commit
                files_output = subprocess.check_output(
                    ["git", "diff", "--name-only", "HEAD"],
                    cwd=working_dir,
                    text=True,
                    stderr=subprocess.DEVNULL,
                ).strip()
            recent_files = (
                ", ".join(files_output.splitlines()[:3]) if files_output else "none"
            )
            summary_text = f"branch: {branch} | recent: {recent_files}"
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("Failed to auto-generate summary from git info.")
            sys.exit(1)

    if not summary_text:
        print("Provide a summary text, --auto, or --clear.")
        sys.exit(1)

    result = registry.update_summary(agent_id, summary_text)
    if result:
        print(f"Updated summary for {agent_id}")
    else:
        print(f"Failed to update summary for {agent_id}")
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
    # "is True" guards against MagicMock truthiness in tests
    if getattr(args, "json_output", False) is True:
        list_command.run_json(args)
    else:
        list_command.run(args)


def cmd_status(args: argparse.Namespace) -> None:
    """Show detailed status for a specific agent."""
    import sys

    from synapse.commands.status import StatusCommand
    from synapse.file_safety import FileSafetyManager
    from synapse.history import HistoryManager
    from synapse.paths import get_history_db_path

    registry = AgentRegistry()
    try:
        history = HistoryManager(get_history_db_path())
    except (OSError, sqlite3.Error):
        history = None
    try:
        file_safety = FileSafetyManager.from_env()
    except (OSError, ValueError, KeyError):
        file_safety = None

    cmd = StatusCommand(
        registry=registry,
        history_manager=history,
        file_safety_manager=file_safety,
        output=sys.stdout,
    )
    cmd.run(args.target, json_output=getattr(args, "json_output", False))


def cmd_merge(args: argparse.Namespace) -> None:
    """Merge worktree agent branches into the current branch."""
    from synapse.commands.merge import merge_all, merge_single

    target = getattr(args, "target", None)
    merge_all_flag = getattr(args, "all", False)
    dry_run = getattr(args, "dry_run", False)
    resolve_with = getattr(args, "resolve_with", None)

    if not target and not merge_all_flag:
        print("Specify a target agent or use --all.")
        sys.exit(1)

    if target and merge_all_flag:
        print("Error: Cannot specify both a target agent and --all.")
        sys.exit(1)

    if merge_all_flag and resolve_with:
        print("Error: --resolve-with cannot be used together with --all.")
        sys.exit(1)

    registry = AgentRegistry()

    if merge_all_flag:
        _success_count, failure_count = merge_all(registry, dry_run=dry_run)
        if failure_count:
            sys.exit(1)
        return

    if target is None:
        # Unreachable: the guard above ensures target or --all. Defensive check for mypy.
        sys.exit(1)
    agent_info = registry.resolve_agent(target)
    if agent_info is None:
        print(f"Agent not found: {target}")
        print("Run 'synapse list' to see running agents.")
        sys.exit(1)

    if resolve_with and registry.resolve_agent(resolve_with) is None:
        print(f"Resolver agent not found: {resolve_with}")
        sys.exit(1)

    if not merge_single(
        agent_info,
        dry_run=dry_run,
        resolve_with=resolve_with,
        registry=registry,
    ):
        sys.exit(1)


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


def cmd_agents_list(args: argparse.Namespace) -> None:
    """List saved agent definitions."""
    _ = args
    store = AgentProfileStore()
    items = store.list_all()

    if not items:
        print("No saved agents. Use 'synapse agents add ...' to create one.")
        return

    # TUI table for interactive terminals, fallback to plain text otherwise.
    if sys.stdout.isatty():
        try:
            from rich import box
            from rich.console import Console
            from rich.table import Table

            table = Table(
                title="Saved Agents",
                box=box.ROUNDED,
                show_header=True,
                header_style="bold cyan",
            )
            table.add_column("ID", style="green")
            table.add_column("NAME")
            table.add_column("PROFILE")
            table.add_column("ROLE")
            table.add_column("SKILL_SET")
            table.add_column("SCOPE", style="yellow")
            for item in items:
                table.add_row(
                    item.profile_id,
                    item.name,
                    item.profile,
                    item.role or "-",
                    item.skill_set or "-",
                    item.scope,
                )
            Console().print(table)
            return
        except ImportError:
            pass

    print(f"{'ID':<20} {'NAME':<20} {'PROFILE':<10} {'SCOPE':<8}")
    print("-" * 62)
    for item in items:
        print(
            f"{item.profile_id:<20} {item.name:<20} {item.profile:<10} {item.scope:<8}"
        )


def cmd_agents_show(args: argparse.Namespace) -> None:
    """Show one saved agent definition."""
    store = AgentProfileStore()
    try:
        item = store.resolve(args.id_or_name)
    except AgentProfileError as e:
        print(f"Error: {e}")
        sys.exit(1)
    if item is None:
        print(f"Saved agent not found: {args.id_or_name}")
        sys.exit(1)

    print(f"ID:        {item.profile_id}")
    print(f"Name:      {item.name}")
    print(f"Profile:   {item.profile}")
    print(f"Role:      {item.role or '-'}")
    print(f"Skill Set: {item.skill_set or '-'}")
    print(f"Scope:     {item.scope}")
    if item.path:
        print(f"Path:      {item.path}")


def cmd_agents_add(args: argparse.Namespace) -> None:
    """Add or update a saved agent definition."""
    if args.profile not in KNOWN_PROFILES:
        print(
            f"Unknown profile '{args.profile}'. "
            f"Choose from: {', '.join(sorted(KNOWN_PROFILES))}"
        )
        sys.exit(1)

    store = AgentProfileStore()
    try:
        item = store.add(
            profile_id=args.id,
            name=args.name,
            profile=args.profile,
            role=args.role,
            skill_set=args.skill_set,
            scope=args.scope,
        )
    except AgentProfileError as e:
        print(f"Error: {e}")
        sys.exit(1)

    print(
        f"Saved agent '{item.profile_id}' ({item.name}) "
        f"for profile '{item.profile}' in {item.scope} scope."
    )


def cmd_agents_delete(args: argparse.Namespace) -> None:
    """Delete a saved agent definition."""
    store = AgentProfileStore()
    try:
        deleted = store.delete(args.id_or_name)
    except AgentProfileError as e:
        print(f"Error: {e}")
        sys.exit(1)
    if not deleted:
        print(f"Saved agent not found: {args.id_or_name}")
        sys.exit(1)
    print(f"Deleted saved agent: {args.id_or_name}")


def _input_with_default(
    label: str,
    default: str | None,
    *,
    input_func: Callable[[str], str] | None = None,
) -> str | None:
    """Prompt for free-text input with an optional suggested default."""
    if input_func is None:
        input_func = input
    if default:
        raw = input_func(f"{label} [Enter = {default}]: ").strip()
        return raw if raw else default
    return input_func(f"{label} [Enter to skip]: ").strip() or None


def _maybe_prompt_save_agent_profile(
    *,
    profile: str,
    name: str | None,
    role: str | None,
    skill_set: str | None,
    headless: bool,
    is_tty: bool,
    input_func: Callable[[str], str] = input,
    print_func: Callable[[str], None] = print,
    store: AgentProfileStore | None = None,
) -> None:
    """Prompt to save current interactive agent definition on exit."""
    if os.environ.get("SYNAPSE_AGENT_SAVE_PROMPT_ENABLED", "true").lower() in {
        "0",
        "false",
        "no",
        "off",
    }:
        return

    if headless or not is_tty or not name:
        return

    # Skip if an identical profile already exists in the store.
    resolved_store = store or AgentProfileStore()
    from synapse.worktree import is_path_in_worktree

    is_worktree = is_path_in_worktree(resolved_store.project_root)
    default_scope: Literal["project", "user"] = "user" if is_worktree else "project"

    for existing in resolved_store.list_all():
        if (
            existing.profile == profile
            and existing.name == name
            and existing.role == role
            and existing.skill_set == skill_set
        ):
            return

    save = input_func("Save this agent definition for reuse? [y/N]: ").strip().lower()
    if save not in {"y", "yes"}:
        return

    suggestions = suggest_petname_ids(name, role, skill_set, profile)
    suggested_id = suggestions[0] if suggestions else None

    while True:
        profile_id = _input_with_default(
            "Saved agent ID", suggested_id, input_func=input_func
        )
        if not profile_id:
            print_func("Skipped: no saved agent ID provided.")
            return
        try:
            AgentProfileStore._validate_profile_id(profile_id)
        except AgentProfileError as e:
            print_func(f"Invalid saved agent ID: {e}")
            if suggestions:
                print_func("Try one of: " + ", ".join(suggestions))
            continue
        break

    if is_worktree:
        scope_prompt = (
            "Scope [project/user] "
            "(default: user - project scope in a worktree is deleted on cleanup): "
        )
    else:
        scope_prompt = "Scope [project/user] (default: project): "
    raw_scope = input_func(scope_prompt).strip().lower()
    if not raw_scope:
        scope = default_scope
    elif raw_scope in {"project", "user"}:
        scope = cast(Literal["project", "user"], raw_scope)
    else:
        print_func("Invalid scope. Use 'project' or 'user'.")
        return

    try:
        resolved_store.add(
            profile_id=profile_id,
            name=name,
            profile=profile,
            role=role,
            skill_set=skill_set,
            scope=scope,
        )
    except AgentProfileError as e:
        print_func(f"Failed to save agent definition: {e}")
        return
    print_func(f"Saved agent definition: {profile_id} ({name})")


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


def cmd_wiki_ingest(args: argparse.Namespace) -> None:
    """Ingest a source file into the wiki."""
    from synapse.wiki import cmd_wiki_ingest as _cmd_wiki_ingest

    _cmd_wiki_ingest(args)


def cmd_wiki_query(args: argparse.Namespace) -> None:
    """Query wiki pages from the index."""
    from synapse.wiki import cmd_wiki_query as _cmd_wiki_query

    _cmd_wiki_query(args)


def cmd_wiki_lint(args: argparse.Namespace) -> None:
    """Validate wiki consistency."""
    from synapse.wiki import cmd_wiki_lint as _cmd_wiki_lint

    _cmd_wiki_lint(args)


def cmd_wiki_status(args: argparse.Namespace) -> None:
    """Show wiki status."""
    from synapse.wiki import cmd_wiki_status as _cmd_wiki_status

    _cmd_wiki_status(args)


def cmd_wiki_refresh(args: argparse.Namespace) -> None:
    """Refresh stale wiki pages."""
    from synapse.wiki import cmd_wiki_refresh as _cmd_wiki_refresh

    _cmd_wiki_refresh(args)


def cmd_wiki_init(args: argparse.Namespace) -> None:
    """Initialize wiki with skeleton pages."""
    from synapse.wiki import cmd_wiki_init as _cmd_wiki_init

    _cmd_wiki_init(args)


def cmd_worktree_prune(args: argparse.Namespace) -> None:
    """Prune orphan worktrees."""
    from synapse.worktree import prune_worktrees

    pruned = prune_worktrees()
    if not pruned:
        print("[Synapse] No orphan worktrees found.")
        return
    for name in pruned:
        print(f"  Pruned: {name}")
    print(f"[Synapse] Pruned {len(pruned)} orphan worktree(s).")


def cmd_mcp_serve(args: argparse.Namespace) -> None:
    """Serve Synapse MCP resources over stdio."""
    from synapse.mcp.server import SynapseMCPServer, serve_stdio
    from synapse.tools.a2a import _extract_agent_type_from_id

    agent_id = args.agent_id
    agent_type = args.agent_type or _extract_agent_type_from_id(agent_id)

    server = SynapseMCPServer(
        agent_type=agent_type or "default",
        agent_id=agent_id,
        port=args.port,
    )
    serve_stdio(server)


# ============================================================
# Auth Management Commands
# ============================================================


def cmd_auth_generate_key(args: argparse.Namespace) -> None:
    """Generate a new API key."""
    count = getattr(args, "count", 1)
    export_format = getattr(args, "export", False)

    if count < 1:
        print("Error: --count must be >= 1", file=sys.stderr)
        sys.exit(1)

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


def _prompt_menu_selection(
    title: str, options: dict[str, str], prompt_hint: str
) -> str | None:
    """
    Generic menu selection prompt.

    Args:
        title: Title displayed above the menu.
        options: Dict mapping key (e.g., "1") to display label.
        prompt_hint: Hint shown in the input prompt (e.g., "[1/2/q]").

    Returns:
        The selected value (e.g., "user", "project") or None if cancelled.
    """
    # Build options mapping: {"1": "user", "2": "project", "q": None}
    key_to_value: dict[str, str | None] = {}
    print(f"\n? {title}")
    for key, label in options.items():
        if key == "q":
            key_to_value["q"] = None
        else:
            # Extract value from label like "User scope (~/.synapse/...)" -> "user"
            value = label.split()[0].lower()
            key_to_value[key] = value
        print(f"  [{key}] {label}")
    print()

    while True:
        choice = input(f"Enter choice {prompt_hint}: ").strip().lower()
        if choice in key_to_value:
            return key_to_value[choice]
        print(f"Invalid choice. Please enter one of: {', '.join(key_to_value.keys())}.")


def _prompt_scope_selection() -> str | None:
    """Prompt user to select a scope for settings."""
    return _prompt_menu_selection(
        title="Where do you want to create settings.json?",
        options={
            "1": "User scope (~/.synapse/settings.json)",
            "2": "Project scope (./.synapse/settings.json)",
            "q": "Cancel",
        },
        prompt_hint="[1/2/q]",
    )


def _prompt_reset_scope_selection() -> str | None:
    """Prompt user to select which settings to reset."""
    return _prompt_menu_selection(
        title="Which settings do you want to reset?",
        options={
            "1": "User scope (~/.synapse/settings.json)",
            "2": "Project scope (./.synapse/settings.json)",
            "3": "Both",
            "q": "Cancel",
        },
        prompt_hint="[1/2/3/q]",
    )


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


def _smart_merge_settings(template_file: Path, existing_file: Path) -> None:
    """Merge template settings.json into existing one, preserving user values.

    New keys from the template are added; existing user values are kept.
    This ensures upgrades add new config options without losing customization.
    """
    from synapse.settings import merge_settings

    try:
        template_data = json.loads(template_file.read_text(encoding="utf-8"))
        existing_data = json.loads(existing_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning(
            "Smart merge failed for %s: %s — overwriting", existing_file, exc
        )
        shutil.copy2(template_file, existing_file)
        return

    # merge_settings(base, override): override values take precedence.
    # Use template as base, existing as override → user values preserved, new keys added.
    merged = merge_settings(template_data, existing_data)
    existing_file.write_text(
        json.dumps(merged, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def _copy_synapse_templates(target_dir: Path) -> bool:
    """
    Copy template files from synapse/templates/.synapse/ to target directory.

    This merges template files into the target .synapse/ directory,
    preserving any user-generated data (agents/, databases, sessions/,
    workflows/, worktrees/, etc.) that is not part of the templates.

    Only files that exist in the templates are overwritten; all other
    files and directories in the target are left untouched.

    Args:
        target_dir: Target directory path (e.g., ~/.synapse or ./.synapse)

    Returns:
        True if successful, False otherwise.
    """
    try:
        # Find templates directory relative to synapse package
        import synapse

        package_dir = Path(synapse.__file__).parent
        templates_dir = package_dir / "templates" / ".synapse"

        if not templates_dir.exists():
            print(f"Error: Templates directory not found: {templates_dir}")
            return False

        # Ensure target directory exists
        target_dir.mkdir(parents=True, exist_ok=True)

        # Merge: copy each template file individually, preserving non-template data
        resolved_target = target_dir.resolve()
        for src_file in templates_dir.rglob("*"):
            if not src_file.is_file():
                continue
            # Reject symlinks in source tree
            if src_file.is_symlink():
                print(f"Warning: Skipping symlink in templates: {src_file}")
                continue
            rel_path = src_file.relative_to(templates_dir)
            dst_file = target_dir / rel_path
            # Reject if destination resolves outside target_dir (symlink traversal)
            if not dst_file.resolve().is_relative_to(resolved_target):
                print(f"Warning: Skipping path escaping target dir: {dst_file}")
                continue
            # Reject if any parent component is a symlink
            for parent in dst_file.relative_to(target_dir).parents:
                parent_path = target_dir / parent
                if parent_path != target_dir and parent_path.is_symlink():
                    print(f"Warning: Skipping path with symlink parent: {dst_file}")
                    break
            else:
                dst_file.parent.mkdir(parents=True, exist_ok=True)
                # Smart merge for settings.json: add new keys, preserve user values
                if rel_path.name == "settings.json" and dst_file.exists():
                    _smart_merge_settings(src_file, dst_file)
                else:
                    shutil.copy2(src_file, dst_file)

        return True

    except OSError as e:
        print(f"Error copying templates: {e}")
        return False


def _copy_claude_skills_to_agents(base_dir: Path, force: bool = False) -> list[str]:
    """Copy synapse skills from .claude to .agents directory.

    Codex, OpenCode, Gemini, and Copilot use .agents/skills/ for skill discovery, so this
    copies each skill from .claude/skills/<name> to .agents/skills/<name>.

    Args:
        base_dir: Base directory (e.g., Path.home() or Path.cwd())
        force: If True, overwrite existing skills in .agents

    Returns:
        List of paths where skills were copied to
    """
    installed: list[str] = []
    skill_names = ["synapse-a2a", "synapse-reinst"]

    for skill_name in skill_names:
        source = base_dir / ".claude" / "skills" / skill_name
        if not source.exists():
            continue
        result = _copy_skill_to_agents(
            source, skill_name, base_dir=base_dir, force=force, quiet=True
        )
        if result:
            installed.append(result)

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

    # Copy skills from .claude to .agents (Codex/OpenCode/Gemini/Copilot use .agents/skills/)
    installed = _copy_claude_skills_to_agents(skills_base, force=False)
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
            for agent_dir in [".claude", ".agents"]:
                for skill_name in ["synapse-a2a", "synapse-reinst"]:
                    skill_path = base / agent_dir / "skills" / skill_name
                    exists = "exists" if skill_path.exists() else "will be created"
                    print(f"  - {skill_path} ({exists})")
        response = input("\nContinue? (y/N): ").strip().lower()
        if response not in ("y", "yes"):
            print("Cancelled.")
            return

    # Reset settings
    had_error = False
    for path in paths_to_reset:
        if _write_default_settings(path):
            print(f"✔ Reset {path}")
        else:
            print(f"✗ Failed to reset {path}")
            had_error = True

    # Re-copy skills from .claude to .agents (force=True to overwrite)
    for base in skill_bases:
        installed = _copy_claude_skills_to_agents(base, force=True)
        for installed_path in installed:
            print(f"✔ Re-copied skill to {installed_path}")

    if had_error:
        sys.exit(1)


def cmd_config(args: argparse.Namespace) -> None:
    """Interactive configuration management."""
    import sys

    no_rich = getattr(args, "no_rich", False)

    # Use Rich TUI if stdout is TTY and not explicitly disabled
    use_rich = sys.stdout.isatty() and not no_rich

    if use_rich:
        from synapse.commands.config import RichConfigCommand

        rich_cmd = RichConfigCommand()
        rich_cmd.run()
    else:
        from synapse.commands.config import ConfigCommand

        legacy_cmd = ConfigCommand()
        legacy_cmd.run()


def cmd_config_show(args: argparse.Namespace) -> None:
    """Show current settings."""
    from synapse.commands.config import ConfigCommand

    cmd = ConfigCommand()
    scope = getattr(args, "scope", None)
    cmd.show(scope=scope)


def cmd_skills(args: argparse.Namespace) -> None:
    """Interactive skill manager TUI."""
    from synapse.commands.skill_manager import SkillManagerCommand

    cmd = SkillManagerCommand()
    cmd.run()


def cmd_skills_list(args: argparse.Namespace) -> None:
    """List all skills."""
    from synapse.commands.skill_manager import cmd_skills_list as _list

    scope = getattr(args, "scope", None)
    _list(scope_filter=scope)


def cmd_skills_show(args: argparse.Namespace) -> None:
    """Show skill details."""
    from synapse.commands.skill_manager import cmd_skills_show as _show

    scope = getattr(args, "scope", None)
    _show(args.name, scope=scope)


def cmd_skills_delete(args: argparse.Namespace) -> None:
    """Delete a skill."""
    from synapse.commands.skill_manager import cmd_skills_delete as _delete

    scope = getattr(args, "scope", None)
    force = getattr(args, "force", False)
    _delete(args.name, scope=scope, force=force)


def cmd_skills_move(args: argparse.Namespace) -> None:
    """Move a skill to another scope."""
    from synapse.commands.skill_manager import cmd_skills_move as _move

    _move(args.name, target_scope=args.to)


def cmd_skills_deploy(args: argparse.Namespace) -> None:
    """Deploy a skill to agent directories."""
    from synapse.commands.skill_manager import cmd_skills_deploy as _deploy

    agents = [a.strip() for a in args.agent.split(",")] if args.agent else ["claude"]
    scope = getattr(args, "deploy_scope", "user")
    _deploy(args.name, agents=agents, scope=scope)


def cmd_skills_import(args: argparse.Namespace) -> None:
    """Import a skill to the central synapse store."""
    from synapse.commands.skill_manager import cmd_skills_import as _import

    from_scope = getattr(args, "from_scope", None)
    _import(args.name, from_scope=from_scope)


def cmd_skills_add(args: argparse.Namespace) -> None:
    """Add a skill from a repository via npx."""
    from synapse.paths import get_synapse_skills_dir
    from synapse.skills import add_skill_from_repo

    skills_dir = Path(get_synapse_skills_dir())
    synapse_dir = skills_dir.parent
    result = add_skill_from_repo(args.repo, synapse_dir=synapse_dir)

    for msg in result.messages:
        print(f"  {msg}")

    if result.imported:
        print(f"\n  Imported {len(result.imported)} skill(s) to {skills_dir}")


def cmd_skills_create(args: argparse.Namespace) -> None:
    """Create a new skill in the central store."""
    from synapse.commands.skill_manager import cmd_skills_create as _create

    name = getattr(args, "name", None)
    _create(name=name)


def cmd_skills_set(args: argparse.Namespace) -> None:
    """Interactive skill set management (via skills TUI)."""
    from synapse.commands.skill_manager import SkillManagerCommand

    cmd = SkillManagerCommand()
    cmd._skill_set_menu()


def cmd_skills_set_list(args: argparse.Namespace) -> None:
    """List all skill sets."""
    from synapse.commands.skill_manager import cmd_skills_set_list as _list

    _list()


def cmd_skills_set_show(args: argparse.Namespace) -> None:
    """Show skill set details."""
    from synapse.commands.skill_manager import cmd_skills_set_show as _show

    _show(args.name)


def cmd_skills_apply(args: argparse.Namespace) -> None:
    """Apply a skill set to a running agent."""
    from synapse.commands.skill_manager import cmd_skills_apply as _apply

    ok = _apply(
        target=args.target,
        set_name=args.set_name,
        dry_run=args.dry_run,
    )
    if not ok:
        sys.exit(1)


def cmd_canvas_serve(args: argparse.Namespace) -> None:
    """Start Canvas server."""
    from synapse.canvas.server import create_app
    from synapse.config import CANVAS_DEFAULT_PORT

    port = args.port or CANVAS_DEFAULT_PORT
    try:
        import uvicorn
    except ImportError:
        print(
            "Error: uvicorn is required. Install with: uv add uvicorn", file=sys.stderr
        )
        sys.exit(1)

    app = create_app()
    if not args.no_open:
        import threading

        url = f"http://localhost:{port}"
        threading.Thread(
            target=_wait_and_open_browser, args=(url,), daemon=True
        ).start()
    print(f"Starting Canvas server on http://localhost:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


def cmd_canvas_post(args: argparse.Namespace) -> None:
    """Post a card to Canvas."""
    from synapse.canvas.protocol import FORMAT_REGISTRY
    from synapse.commands.canvas import (
        ensure_server_running,
        get_canvas_post_example,
        post_shortcut,
    )
    from synapse.config import CANVAS_DEFAULT_PORT

    example_format = getattr(args, "example", None)
    if example_format:
        if example_format not in FORMAT_REGISTRY:
            print(
                f"Error: Unknown format '{example_format}'. Valid: {', '.join(FORMAT_REGISTRY)}",
                file=sys.stderr,
            )
            sys.exit(1)
        print(get_canvas_post_example(example_format))
        return

    fmt = args.format
    if fmt not in FORMAT_REGISTRY:
        print(
            f"Error: Unknown format '{fmt}'. Valid: {', '.join(FORMAT_REGISTRY)}",
            file=sys.stderr,
        )
        sys.exit(1)

    body = args.body
    if getattr(args, "stdin", False) or body == "-":
        body = sys.stdin.read()
    if body is None and not getattr(args, "file", None):
        print(
            "Error: body is required unless --stdin, --file, or --example is used",
            file=sys.stderr,
        )
        sys.exit(1)

    port = args.port or CANVAS_DEFAULT_PORT
    ensure_server_running(port=port)

    tags = [t.strip() for t in args.tags.split(",")] if args.tags else None
    result = post_shortcut(
        format_name=fmt,
        body=body,
        title=args.title,
        agent_id=args.agent_id,
        agent_name=args.agent_name,
        card_id=args.card_id,
        pinned=args.pinned,
        tags=tags,
        lang=args.lang,
        port=port,
        file_path=getattr(args, "file", None),
    )
    if result:
        print(f"Card posted: {result['card_id']}")
    else:
        print("Failed to post card", file=sys.stderr)
        sys.exit(1)


def cmd_canvas_list(args: argparse.Namespace) -> None:
    """List cards on Canvas."""
    from synapse.canvas.store import CanvasStore
    from synapse.paths import get_canvas_db_path

    store = CanvasStore(db_path=get_canvas_db_path())
    cards = store.list_cards(
        agent_id=args.agent_id,
        search=args.search,
        content_type=args.type,
    )
    if not cards:
        print("No cards found.")
        return

    for card in cards:
        pin = " [pinned]" if card.get("pinned") else ""
        agent = card.get("agent_name") or card.get("agent_id", "?")
        title = card.get("title") or "(untitled)"
        print(f"  {card['card_id']}  {title}  ({agent}){pin}")


def cmd_canvas_delete(args: argparse.Namespace) -> None:
    """Delete a card from Canvas."""
    from synapse.canvas.store import CanvasStore
    from synapse.paths import get_canvas_db_path

    store = CanvasStore(db_path=get_canvas_db_path())
    ok = store.delete_card(args.card_id, agent_id=args.agent_id)
    if ok:
        print(f"Deleted card: {args.card_id}")
    else:
        print(
            f"Failed to delete card '{args.card_id}' (not found or not owned)",
            file=sys.stderr,
        )
        sys.exit(1)


def cmd_canvas_clear(args: argparse.Namespace) -> None:
    """Clear all cards from Canvas."""
    from synapse.canvas.store import CanvasStore
    from synapse.paths import get_canvas_db_path

    store = CanvasStore(db_path=get_canvas_db_path())
    count = store.clear_all(agent_id=args.agent_id)
    print(f"Cleared {count} card(s).")


def cmd_canvas_post_raw(args: argparse.Namespace) -> None:
    """Post raw Canvas message JSON (supports composite cards)."""
    from synapse.commands.canvas import ensure_server_running, post_card
    from synapse.config import CANVAS_DEFAULT_PORT

    port = args.port or CANVAS_DEFAULT_PORT
    ensure_server_running(port=port)

    raw = args.json_data
    if raw == "-":
        raw = sys.stdin.read()

    result = post_card(raw, port=port)
    if result:
        print(f"Card posted: {result['card_id']}")
    else:
        sys.exit(1)


def cmd_canvas_briefing(args: argparse.Namespace) -> None:
    """Post a briefing card from JSON data or file."""
    from synapse.commands.canvas import ensure_server_running, post_briefing
    from synapse.config import CANVAS_DEFAULT_PORT

    port = args.port or CANVAS_DEFAULT_PORT
    ensure_server_running(port=port)

    json_data = getattr(args, "json_data", None)
    if json_data == "-":
        json_data = sys.stdin.read()

    file_path = getattr(args, "file", None)
    tags = args.tags.split(",") if args.tags else None

    result = post_briefing(
        json_data=json_data,
        file_path=file_path,
        title=args.title,
        summary=getattr(args, "summary", ""),
        agent_id=args.agent_id,
        agent_name=getattr(args, "agent_name", ""),
        card_id=args.card_id,
        pinned=args.pinned,
        tags=tags,
        port=port,
    )
    if result:
        print(f"Briefing posted: {result['card_id']}")
    else:
        sys.exit(1)


def cmd_canvas_plan(args: argparse.Namespace) -> None:
    """Post a plan card from JSON data or file."""
    from synapse.commands.canvas import ensure_server_running, post_plan
    from synapse.config import CANVAS_DEFAULT_PORT

    port = args.port or CANVAS_DEFAULT_PORT
    ensure_server_running(port=port)

    json_data = getattr(args, "json_data", None)
    if json_data == "-":
        json_data = sys.stdin.read()

    file_path = getattr(args, "file", None)
    tags = args.tags.split(",") if args.tags else None

    result = post_plan(
        json_data=json_data,
        file_path=file_path,
        title=args.title,
        agent_id=args.agent_id,
        agent_name=getattr(args, "agent_name", ""),
        card_id=args.card_id,
        pinned=args.pinned,
        tags=tags,
        port=port,
    )
    if result:
        print(f"Plan posted: {result['card_id']}")
    else:
        sys.exit(1)


def _wait_and_open_browser(url: str, timeout: float = 10.0) -> None:
    """Poll Canvas health endpoint until ready, then open in browser."""
    import time
    import urllib.error
    import urllib.request

    health_url = url.rstrip("/") + "/api/health"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            resp = urllib.request.urlopen(health_url, timeout=1)
            if resp.status == 200:
                _open_canvas_browser(url)
                return
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(0.3)


def _open_canvas_browser(url: str) -> None:
    """Open *url* in the default browser and log the action."""
    import webbrowser

    webbrowser.open(url)
    print(f"Opened {url} in browser")


def cmd_canvas_open(args: argparse.Namespace) -> None:
    """Open Canvas in browser."""
    from synapse.commands.canvas import ensure_server_running
    from synapse.config import CANVAS_DEFAULT_PORT

    port = args.port or CANVAS_DEFAULT_PORT
    ensure_server_running(port=port)

    _open_canvas_browser(f"http://localhost:{port}")


def cmd_canvas_status(args: argparse.Namespace) -> None:
    """Show Canvas server status."""
    from synapse.commands.canvas import canvas_status
    from synapse.config import CANVAS_DEFAULT_PORT

    port = args.port or CANVAS_DEFAULT_PORT
    canvas_status(port=port)


def cmd_canvas_logs(args: argparse.Namespace) -> None:
    """Show Canvas server logs."""
    from synapse.commands.canvas import LOG_FILE

    if not os.path.exists(LOG_FILE):
        print(f"No log file found at {LOG_FILE}")
        return

    if args.follow:
        os.execlp("tail", "tail", "-f", "-n", str(args.lines), LOG_FILE)
    else:
        with open(LOG_FILE) as f:
            lines = f.readlines()
            for line in lines[-args.lines :]:
                print(line, end="")


def cmd_canvas_stop(args: argparse.Namespace) -> None:
    """Stop Canvas server."""
    from synapse.commands.canvas import canvas_stop
    from synapse.config import CANVAS_DEFAULT_PORT

    port = getattr(args, "port", None) or CANVAS_DEFAULT_PORT
    canvas_stop(port=port)


def cmd_canvas_link(args: argparse.Namespace) -> None:
    """Post a link-preview card with OGP metadata."""
    from synapse.commands.canvas import ensure_server_running, post_link_preview
    from synapse.config import CANVAS_DEFAULT_PORT

    port = getattr(args, "port", None) or CANVAS_DEFAULT_PORT
    ensure_server_running(port)

    tags = [t.strip() for t in args.tags.split(",")] if args.tags else None
    result = post_link_preview(
        url=args.url,
        title=args.title,
        agent_id=args.agent_id,
        agent_name=getattr(args, "agent_name", ""),
        card_id=getattr(args, "card_id", None),
        pinned=args.pinned,
        tags=tags,
        port=port,
    )
    if result:
        print(f"Link preview card created: {result.get('card_id', '')}")
    else:
        print("Failed to create link preview card", file=sys.stderr)
        sys.exit(1)


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


def interactive_agent_setup(
    agent_id: str,
    port: int,
    profile: str = "",
    current_name: str | None = None,
    current_role: str | None = None,
    current_skill_set: str | None = None,
    existing_names: set[str] | None = None,
) -> tuple[str | None, str | None, str | None]:
    """Interactively prompt for agent name, role, and skill set.

    Args:
        agent_id: The agent ID (e.g., synapse-claude-8100).
        port: The port number.
        profile: The agent profile type (e.g., "claude", "gemini").
        current_name: Current name if already specified.
        current_role: Current role if already specified.
        current_skill_set: Current skill set if already specified.

    Returns:
        Tuple of (name, role, skill_set), any of which may be None.
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

    try:
        # Name selection
        name = current_name
        if name is None:
            print("Would you like to give this agent a name? (optional)")
            print("Name allows you to call this agent by name instead of ID.")
            print('Example: synapse send my-claude "hello"')
            print()
            suggestions = suggest_petname_ids(profile, exclude=existing_names)
            suggested_name = suggestions[0] if suggestions else None
            name = _input_with_default("Name", suggested_name)
            print()

        # Role selection
        role = current_role
        if role is None:
            print("Would you like to assign a role? (optional)")
            print("Role is a free-form description of this agent's responsibility.")
            print('Example: "test writer", "code reviewer", "documentation"')
            print()
            role = input("Role [Enter to skip]: ").strip() or None

        # Integrated Skill Set selection
        skill_set = current_skill_set
        if skill_set is None:
            from synapse.skills import load_skill_sets

            if load_skill_sets():
                skill_set = interactive_skill_set_setup()
            else:
                print("\nSkill sets are not defined. Skipping selection.")

        print("=" * 80)
        if name or role or skill_set:
            role_str = f" | Role: {role}" if role else ""
            skill_str = f" | Skill Set: {skill_set}" if skill_set else ""
            print(f"Agent: {name or agent_id}{role_str}{skill_str}")
        print()

        return name, role, skill_set

    except (EOFError, KeyboardInterrupt):
        print("\n\x1b[33m[Synapse]\x1b[0m Setup skipped")
        return current_name, current_role, current_skill_set
    finally:
        # Restore original terminal settings
        if original_settings is not None and termios is not None:
            with contextlib.suppress(termios.error):
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, original_settings)


# ============================================================
# Plan Approval Commands (B3)
# ============================================================


def _get_auth_headers() -> dict[str, str]:
    """Build auth headers if SYNAPSE_AUTH_ENABLED is set.

    Returns:
        Dict with X-API-Key header if an API key is available, else empty dict.
    """
    if os.environ.get("SYNAPSE_AUTH_ENABLED", "").lower() != "true":
        return {}
    api_keys = os.environ.get("SYNAPSE_API_KEYS", "")
    if api_keys:
        # Use the first key from the comma-separated list
        first_key = api_keys.split(",")[0].strip()
        if first_key:
            return {"X-API-Key": first_key}
    return {}


def _post_to_task_agent(task_id: str, action: str, payload: dict | None = None) -> bool:
    """Post an action to the agent that owns a task.

    Iterates over all live agents and attempts to POST to the task action
    endpoint on each until one succeeds.

    Args:
        task_id: The task ID to act on.
        action: The action path suffix (e.g. "approve", "reject").
        payload: JSON payload to send with the request.

    Returns:
        True if an agent accepted the request, False otherwise.
    """
    import httpx

    registry = AgentRegistry()
    agents = registry.get_live_agents()
    headers = _get_auth_headers()

    for info in agents.values():
        port = info.get("port")
        if not port:
            continue
        try:
            response = httpx.post(
                f"http://localhost:{port}/tasks/{task_id}/{action}",
                json=payload or {},
                headers=headers,
                timeout=5.0,
            )
            if response.status_code == 200:
                return True
        except (httpx.HTTPError, OSError):
            continue

    return False


def cmd_approve(args: argparse.Namespace) -> None:
    """Approve a plan for a task."""
    task_id = args.task_id

    if _post_to_task_agent(task_id, "approve"):
        print(f"Approved task {task_id[:8]}")
    else:
        print(f"Could not find task {task_id[:8]} on any running agent.")
        sys.exit(1)


def cmd_reject(args: argparse.Namespace) -> None:
    """Reject a plan for a task."""
    task_id = args.task_id
    reason = getattr(args, "reason", "") or ""

    if _post_to_task_agent(task_id, "reject", {"reason": reason}):
        print(f"Rejected task {task_id[:8]}")
        if reason:
            print(f"Reason: {reason}")
    else:
        print(f"Could not find task {task_id[:8]} on any running agent.")
        sys.exit(1)


def interactive_skill_set_setup() -> str | None:
    """Interactively prompt for skill set selection.

    Shows available skill sets from .synapse/skill_sets.json and lets the
    user pick one using a simple numbered list.

    Returns:
        Selected skill set name, or None if skipped.
    """
    from synapse.skills import load_skill_sets

    sets = load_skill_sets()
    if not sets:
        return None

    items: list[tuple[str, object]] = [
        (name, sets[name]) for name in sorted(sets.keys())
    ]

    def _skills_count(ssd: object) -> int:
        skills = getattr(ssd, "skills", None)
        return len(skills) if isinstance(skills, list) else 0

    # Preferred interactive UI: arrow-key navigation with simple_term_menu.
    try:
        from simple_term_menu import TerminalMenu

        rows: list[str] = []
        for idx, (name, ssd) in enumerate(items, 1):
            rows.append(f"{idx}. {name} - {_skills_count(ssd)} skills")
        rows.append("Skip (no skill set)")

        menu = TerminalMenu(
            rows,
            title="Skill Set Selector",
            menu_cursor="> ",
            menu_cursor_style=("fg_yellow", "bold"),
            menu_highlight_style=("fg_yellow", "bold"),
            cycle_cursor=True,
            clear_screen=False,
            skip_empty_entries=True,
            show_search_hint=True,
        )
        selected_idx: int | None = menu.show()
        if selected_idx is None:
            return None
        if 0 <= selected_idx < len(items):
            return items[selected_idx][0]
        return None
    except ImportError:
        pass

    # Fallback: plain numbered prompt.
    while True:
        print("\nSelect a skill set (optional):")
        for idx, (name, ssd) in enumerate(items, 1):
            desc = getattr(ssd, "description", "") or ""
            print(f"  [{idx}] {name} ({_skills_count(ssd)} skills) {desc}")
        print("  [Enter] Skip")

        try:
            choice = input("Select skill set [number/name]: ").strip()
        except (EOFError, KeyboardInterrupt):
            return None

        if not choice:
            return None

        if choice.isdigit():
            row_idx = int(choice) - 1
            if 0 <= row_idx < len(items):
                return items[row_idx][0]
            print("Invalid selection number.")
            continue

        for name, _ in items:
            if name == choice:
                return name
        lower = choice.lower()
        for name, _ in items:
            if name.lower() == lower:
                return name

        print("Unknown skill set. Use a row number or exact name.")


def cmd_run_interactive(
    profile: str,
    port: int,
    tool_args: list | None = None,
    name: str | None = None,
    role: str | None = None,
    no_setup: bool = False,
    delegate_mode: bool = False,
    skill_set: str | None = None,
    headless: bool = False,
    profile_store: AgentProfileStore | None = None,
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
        delegate_mode: If True, run agent in manager/delegate mode.
        skill_set: Optional skill set name to apply at startup.
        headless: If True, skip all interactive prompts (startup animation,
            setup, approval). Used by spawn to start agents non-interactively.
            A2A server and initial instructions are still sent.
    """
    # headless implies no_setup
    if headless:
        no_setup = True
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

    # Create registry and agent ID before settings/bootstrap work so we can
    # switch to file logging before any startup warnings are emitted.
    registry = AgentRegistry()
    agent_id = registry.get_agent_id(profile, port)

    # Reconfigure logging for interactive agent startup: suppress stderr
    # (would corrupt the agent TUI) and enable file logging instead.
    if "PYTEST_CURRENT_TEST" not in os.environ:
        setup_logging(agent_name=agent_id)

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

    has_mcp_bootstrap = not is_resume and synapse_settings.has_mcp_bootstrap_config(
        profile
    )
    if has_mcp_bootstrap:
        print(
            "\x1b[32m[Synapse]\x1b[0m MCP bootstrap detected, "
            "sending minimal startup bootstrap"
        )

    # Show startup animation before approval prompt (skip in headless mode)
    if not headless:
        from synapse.startup_tui import show_startup_animation

        show_startup_animation(
            agent_type=profile,
            agent_id=agent_id,
            port=port,
        )

    # Interactive agent setup (name/role/skill-set) if not fully provided via CLI
    agent_name = name
    agent_role = role
    selected_skill_set = skill_set
    if (
        not no_setup
        and sys.stdin.isatty()
        and (name is None or role is None or skill_set is None)
    ):
        taken_names: set[str] = {
            n
            for info in registry.list_agents().values()
            if (n := info.get("name")) is not None
        }
        agent_name, agent_role, selected_skill_set = interactive_agent_setup(
            agent_id,
            port,
            profile=profile,
            current_name=name,
            current_role=role,
            current_skill_set=skill_set,
            existing_names=taken_names,
        )

    if agent_name and not registry.is_name_unique(
        agent_name, exclude_agent_id=agent_id
    ):
        print(f"Name '{agent_name}' is already taken by another agent.")
        sys.exit(1)

    # Ensure core skills (synapse-a2a) are always available (best-effort).
    # This should never prevent an agent from starting (or tests from running).
    core_msgs: list[str] = []
    try:
        from synapse.skills import ensure_core_skills

        try:
            core_msgs = ensure_core_skills(profile)
        except OSError:
            core_msgs = []
    except ImportError:
        core_msgs = []

    for msg in core_msgs:
        print(f"\x1b[32m[Synapse]\x1b[0m {msg}")

    if selected_skill_set:
        from synapse.skills import apply_skill_set

        result = apply_skill_set(selected_skill_set, profile)
        for msg in result.messages:
            print(f"\x1b[32m[Synapse]\x1b[0m {msg}")

    # Check if approval is required for initial instructions (skip in headless mode)
    skip_initial_instructions = is_resume
    if (
        not headless
        and not skip_initial_instructions
        and synapse_settings.should_require_approval()
    ):
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
            has_mcp_bootstrap = False

    # Set SYNAPSE env vars for sender identification (same as server.py)
    env["SYNAPSE_AGENT_ID"] = agent_id
    env["SYNAPSE_AGENT_TYPE"] = profile
    env["SYNAPSE_PORT"] = str(port)

    # Per-profile write delay (None = use default WRITE_PROCESSING_DELAY)
    write_delay = config.get("write_delay")
    submit_retry_delay = config.get("submit_retry_delay")
    bracketed_paste = config.get("bracketed_paste", False)
    typing_char_delay = config.get("typing_char_delay")
    typing_max_chars = config.get("typing_max_chars")
    submit_confirm_timeout = config.get("submit_confirm_timeout")
    submit_confirm_poll_interval = config.get("submit_confirm_poll_interval")
    submit_confirm_retries = config.get("submit_confirm_retries")
    long_submit_confirm_timeout = config.get("long_submit_confirm_timeout")
    long_submit_confirm_retries = config.get("long_submit_confirm_retries")

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
        mcp_bootstrap=has_mcp_bootstrap,
        input_ready_pattern=input_ready_pattern,
        name=agent_name,
        role=agent_role,
        delegate_mode=delegate_mode,
        skill_set=selected_skill_set,
        write_delay=write_delay,
        submit_retry_delay=submit_retry_delay,
        bracketed_paste=bracketed_paste,
        typing_char_delay=typing_char_delay,
        typing_max_chars=typing_max_chars,
        submit_confirm_timeout=submit_confirm_timeout,
        submit_confirm_poll_interval=submit_confirm_poll_interval,
        submit_confirm_retries=submit_confirm_retries,
        long_submit_confirm_timeout=long_submit_confirm_timeout,
        long_submit_confirm_retries=long_submit_confirm_retries,
    )

    # Handle Ctrl+C gracefully
    def cleanup(signum: int, frame: object) -> None:
        print("\n\x1b[32m[Synapse]\x1b[0m Shutting down...")
        controller.stop()
        registry.unregister(agent_id)
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    # Initialize worktree locals before try so finally always has them
    worktree_path: str | None = None
    worktree_branch: str | None = None
    worktree_base_branch: str | None = None

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
        worktree_path = os.environ.get("SYNAPSE_WORKTREE_PATH")
        worktree_branch = os.environ.get("SYNAPSE_WORKTREE_BRANCH")
        worktree_base_branch = os.environ.get("SYNAPSE_WORKTREE_BASE_BRANCH")
        spawned_by = os.environ.get("SYNAPSE_SPAWNED_BY") or None
        try:
            registry.register(
                agent_id,
                profile,
                port,
                status="PROCESSING",
                name=agent_name,
                role=agent_role,
                skill_set=selected_skill_set,
                worktree_path=worktree_path,
                worktree_branch=worktree_branch,
                worktree_base_branch=worktree_base_branch,
                spawned_by=spawned_by,
            )
        except NameConflictError as e:
            print(f"Error: {e}")
            sys.exit(1)

        # Initial instructions are sent via on_first_idle callback
        # when the agent reaches IDLE state (detected by idle_regex)

        # Run interactive mode
        controller.run_interactive()

    except KeyboardInterrupt:
        pass
    finally:
        # Never block shutdown on optional save prompt failures.
        with contextlib.suppress(Exception):
            _maybe_prompt_save_agent_profile(
                profile=profile,
                name=agent_name,
                role=agent_role,
                skill_set=selected_skill_set,
                headless=headless,
                is_tty=sys.stdin.isatty() and sys.stdout.isatty(),
                store=profile_store,
            )
        print("\n\x1b[32m[Synapse]\x1b[0m Shutting down...")
        controller.stop()
        registry.unregister(agent_id)

        _try_cleanup_worktree(
            {
                "worktree_path": worktree_path,
                "worktree_branch": worktree_branch,
                "worktree_base_branch": worktree_base_branch,
            }
        )


def _add_response_mode_flags(parser: argparse.ArgumentParser) -> None:
    """Add --wait / --notify / --silent mutually exclusive response mode flags."""
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--wait",
        dest="response_mode",
        action="store_const",
        const="wait",
        default=None,
        help="Wait synchronously for response (blocks until done)",
    )
    group.add_argument(
        "--notify",
        dest="response_mode",
        action="store_const",
        const="notify",
        help="Return immediately, receive async notification on completion (default)",
    )
    group.add_argument(
        "--silent",
        dest="response_mode",
        action="store_const",
        const="silent",
        help="Fire and forget — no response or notification",
    )


def main() -> None:
    argv = sys.argv
    interactive_shortcut = len(argv) >= 2 and argv[1] in KNOWN_PROFILES

    if "PYTEST_CURRENT_TEST" not in os.environ and not interactive_shortcut:
        setup_logging()

    skip_install_skills = (
        len(sys.argv) >= 3 and sys.argv[1] == "mcp" and sys.argv[2] == "serve"
    )
    if not skip_install_skills:
        # Install A2A skills if not present
        install_skills()

    # Check for shortcut: synapse claude [--port PORT] [--name NAME] [--role ROLE]
    #                     [--no-setup] [-- TOOL_ARGS...]
    if interactive_shortcut:
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
                    value = synapse_args[idx + 1]
                    if value.startswith("-"):
                        return None
                    return value
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

        # Parse --name, --role, and --delegate-mode from synapse_args
        name = parse_arg("--name") or parse_arg("-n")
        role = parse_arg("--role") or parse_arg("-r")
        skill_set_arg = parse_arg("--skill-set") or parse_arg("-S")
        no_setup = "--no-setup" in synapse_args
        headless = "--headless" in synapse_args
        delegate_mode = "--delegate-mode" in synapse_args

        # Parse --worktree / -w (optional name value)
        worktree_arg: str | bool | None = None
        if "--worktree" in synapse_args or "-w" in synapse_args:
            wt_val = parse_arg("--worktree") or parse_arg("-w")
            worktree_arg = wt_val if wt_val else True

        # Resolve --agent / -A flag from saved agent definitions
        has_agent_flag = "--agent" in synapse_args or "-A" in synapse_args
        agent_arg = parse_arg("--agent") or parse_arg("-A")
        startup_store: AgentProfileStore | None = None
        if has_agent_flag and not agent_arg:
            print("Error: --agent/-A requires a value.", file=sys.stderr)
            sys.exit(1)
        if agent_arg:
            store = AgentProfileStore()
            startup_store = store
            try:
                saved = store.resolve(agent_arg)
            except AgentProfileError as e:
                print(f"Error: {e}", file=sys.stderr)
                sys.exit(1)
            if saved is None:
                print(
                    f"Error: Unknown saved agent: {agent_arg}\n"
                    "Run 'synapse agents list' to see saved agents.",
                    file=sys.stderr,
                )
                sys.exit(1)
            if saved.profile != profile:
                print(
                    f"Error: Saved agent '{agent_arg}' uses profile "
                    f"'{saved.profile}', but you ran 'synapse {profile}'.",
                    file=sys.stderr,
                )
                sys.exit(1)
            # CLI args override saved values
            name = name or saved.name
            role = role or saved.role
            skill_set_arg = skill_set_arg or saved.skill_set

        explicit_port = port is not None

        # Auto-select available port if not specified
        if port is None:
            registry = AgentRegistry()
            port_manager = PortManager(registry)
            port = port_manager.get_available_port(profile)

            if port is None:
                print(port_manager.format_exhaustion_error(profile))
                sys.exit(1)

        assert port is not None  # Type narrowing for mypy/ty

        # Create worktree if requested and set env vars
        if worktree_arg:
            from synapse.worktree import create_worktree as _create_wt

            wt_name = worktree_arg if isinstance(worktree_arg, str) else None
            try:
                wt_info = _create_wt(name=wt_name)
            except (RuntimeError, ValueError) as e:
                print(f"Error creating worktree: {e}", file=sys.stderr)
                sys.exit(1)
            os.chdir(wt_info.path)
            os.environ["SYNAPSE_WORKTREE_PATH"] = str(wt_info.path)
            os.environ["SYNAPSE_WORKTREE_BRANCH"] = wt_info.branch
            os.environ["SYNAPSE_WORKTREE_BASE_BRANCH"] = wt_info.base_branch
            print(
                f"\x1b[32m[Synapse]\x1b[0m Worktree: {wt_info.path} ({wt_info.branch})"
            )

        while True:
            try:
                cmd_run_interactive(
                    profile,
                    port,
                    tool_args,
                    name=name,
                    role=role,
                    no_setup=no_setup,
                    delegate_mode=delegate_mode,
                    skill_set=skill_set_arg,
                    headless=headless,
                    profile_store=startup_store,
                )
                break
            except OSError as e:
                if explicit_port or e.errno != errno.EADDRINUSE:
                    raise

                registry = AgentRegistry()
                port_manager = PortManager(registry)
                next_port = port_manager.get_available_port(profile)
                if next_port is None or next_port == port:
                    raise
                port = next_port
        return

    from importlib.metadata import PackageNotFoundError, version

    try:
        pkg_version = version("synapse-a2a")
    except PackageNotFoundError:
        pkg_version = "unknown"

    parser = argparse.ArgumentParser(
        description="""Synapse A2A - Multi-Agent Collaboration Framework

Synapse wraps CLI agents (Claude Code, Codex, Gemini, OpenCode, Copilot) with
Google A2A Protocol, enabling seamless inter-agent communication.

Features: Agent Teams, Session Save/Restore, Shared Memory,
Skills System, File Safety, History & Tracing, Worktree Isolation.""",
        prog="synapse",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Profile Shortcuts:
  synapse claude                          Start Claude directly (interactive mode)
  synapse codex                           Start Codex directly (interactive mode)
  synapse gemini                          Start Gemini directly (interactive mode)
  synapse opencode                        Start OpenCode directly (interactive mode)
  synapse copilot                         Start Copilot directly (interactive mode)

Examples:
  synapse claude                          Start Claude agent (interactive mode)
  synapse team start claude gemini codex  Start a multi-agent team
  synapse session save review-team        Save team configuration
  synapse session restore review-team     Restore saved team
  synapse spawn gemini --worktree         Spawn agent in isolated worktree
  synapse list                            Watch running agents (Rich TUI)
  synapse send codex "Review this" --wait Send message and wait for reply
  synapse tasks create "Fix auth" -d "..."  Create a shared task
  synapse memory save key "value"         Save to shared memory
  synapse skills list                     List available skills
  synapse history list                    View task history

Environment Variables:
  SYNAPSE_HISTORY_ENABLED=false           Disable task history (enabled by default)
  SYNAPSE_FILE_SAFETY_ENABLED=true        Enable file locking for multi-agent safety
  SYNAPSE_AUTH_ENABLED=true               Enable API key authentication

Run 'synapse <command> --help' for detailed usage.

Documentation: https://github.com/s-hiraoku/synapse-a2a""",
    )
    parser.add_argument(
        "--version", "-V", action="version", version=f"%(prog)s {pkg_version}"
    )
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")

    # doctor
    p_doctor = subparsers.add_parser(
        "doctor",
        help="Run Synapse health checks",
        description="Run Synapse health checks and detect orphan managed resources.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_doctor.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Project root to check (default: current directory)",
    )
    p_doctor.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 when orphan listeners or stale sockets are found",
    )
    p_doctor.add_argument(
        "--clean",
        action="store_true",
        help="Clean orphan listeners and stale sockets after confirmation",
    )
    p_doctor.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Skip cleanup confirmation prompts",
    )
    p_doctor.set_defaults(func=cmd_doctor)

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
    # tool_args are extracted from sys.argv before parse_args() —
    # see the _extract_tool_args_from_argv() call in main().
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
    p_kill.add_argument(
        "--no-merge",
        action="store_true",
        default=False,
        help="Skip auto-merge of worktree branch (default: merge automatically)",
    )
    p_kill.set_defaults(func=cmd_kill)

    # cleanup (orphaned spawned agents — issue #332)
    p_cleanup = subparsers.add_parser(
        "cleanup",
        help="Kill orphaned spawned agents (parent crashed/cleared)",
        description="""Kill orphaned child agents whose spawning parent is no longer alive.

An orphan is an agent registered with `spawned_by` whose parent's registry
entry has been removed OR whose parent PID is no longer running. This is a
manual recovery tool for the case where a parent agent crashed, had its
context cleared, or was killed before it could clean up its children.

Existing `synapse kill` semantics are unchanged; this command never touches
root agents (no `spawned_by`) and never touches children with a live parent.""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  synapse cleanup --dry-run           List orphans without killing
  synapse cleanup                     Kill every orphan (with confirmation)
  synapse cleanup -f                  Kill every orphan, no prompt
  synapse cleanup synapse-claude-8200 Kill one specific orphan

Set SYNAPSE_ORPHAN_IDLE_TIMEOUT=<seconds> to enable opportunistic cleanup
of orphans that have been READY longer than the timeout (off by default).""",
    )
    p_cleanup.add_argument(
        "target",
        nargs="?",
        default=None,
        metavar="AGENT",
        help="Optional specific orphan agent to kill (default: all orphans)",
    )
    p_cleanup.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="List orphans without killing them",
    )
    p_cleanup.add_argument(
        "--force",
        "-f",
        action="store_true",
        default=False,
        help="Skip confirmation prompt",
    )
    p_cleanup.set_defaults(func=cmd_cleanup)

    # merge
    p_merge = subparsers.add_parser(
        "merge",
        help="Merge worktree agent branch",
    )
    p_merge.add_argument("target", nargs="?", default=None)
    p_merge.add_argument("--all", action="store_true", default=False)
    p_merge.add_argument("--dry-run", action="store_true", default=False)
    p_merge.add_argument("--resolve-with", dest="resolve_with", default=None)
    p_merge.set_defaults(func=cmd_merge)

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

    # set-summary
    p_set_summary = subparsers.add_parser(
        "set-summary",
        help="Set agent work summary",
        description="""Set or clear a persistent work summary for a running agent.

Unlike the ephemeral task preview (30 chars), summary is longer (up to 120 chars)
and persists until explicitly changed or cleared.

Target resolution priority:
  1. Custom name (my-claude) - highest priority
  2. Full agent ID (synapse-claude-8100)
  3. Type-port shorthand (claude-8100)
  4. Type (claude) - only if single instance""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  synapse set-summary claude "Working on auth refactor"
  synapse set-summary my-claude --auto
  synapse set-summary claude --clear""",
    )
    p_set_summary.add_argument(
        "target",
        metavar="TARGET",
        help="Agent name, ID (synapse-claude-8100), type-port (claude-8100), or type",
    )
    p_set_summary.add_argument(
        "summary",
        nargs="?",
        default=None,
        help="Summary text (up to 120 chars)",
    )
    _summary_mode = p_set_summary.add_mutually_exclusive_group()
    _summary_mode.add_argument(
        "--clear",
        "-c",
        action="store_true",
        help="Clear the summary",
    )
    _summary_mode.add_argument(
        "--auto",
        "-a",
        action="store_true",
        help="Auto-generate from git branch and recent files",
    )
    p_set_summary.set_defaults(func=cmd_set_summary)

    # list
    p_list = subparsers.add_parser(
        "list",
        help="List running agents",
        description="Show all running Synapse agents with their status and ports.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  synapse list              Show running agents (Rich TUI with auto-update)
  synapse list --json       Output agent list as JSON (for AI/scripts)

Columns:
  ID            Agent identifier
  NAME          Custom name (set via synapse rename)
  STATUS        Current status (READY, PROCESSING, etc.)
  CURRENT       Current task preview
  TRANSPORT     Transport status (UDS/TCP)
  WORKING_DIR   Working directory
  EDITING_FILE  File being edited (requires SYNAPSE_FILE_SAFETY_ENABLED=true)

  Customize columns: synapse config → list.columns
  Manage file locks: synapse file-safety locks

Interactive controls:
  1-9         Select agent by number
  ↑/↓/hjkl    Navigate selection
  Enter       Jump to terminal
  K           Kill agent (with confirmation)
  /           Filter by TYPE or WORKING_DIR
  ESC         Clear filter/selection
  q           Quit

Status meanings:
  READY       Agent is idle and waiting for input
  WAITING     Agent is showing selection UI
  PROCESSING  Agent is actively processing a task
  DONE        Task completed (auto-transitions to READY)""",
    )
    p_list.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output agent list as JSON (for programmatic use)",
    )
    p_list.add_argument(
        "--plain",
        action="store_true",
        dest="plain_output",
        help="Force one-shot plain-text output without the Rich TUI",
    )
    p_list.set_defaults(func=cmd_list)

    # status
    p_status = subparsers.add_parser(
        "status",
        help="Show detailed agent status",
        description="Show detailed status for a specific agent.",
    )
    p_status.add_argument("target", help="Agent name, ID, type-port, or type")
    p_status.add_argument(
        "--json", action="store_true", dest="json_output", help="Output as JSON"
    )
    p_status.set_defaults(func=cmd_status)

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
  3    Normal tasks (default)
  4    Urgent follow-ups
  5    Critical/emergency tasks""",
    )
    p_send.add_argument("target", help="Target agent (claude, codex, gemini)")
    p_send.add_argument("message", nargs="?", default=None, help="Message to send")
    p_send.add_argument(
        "--message-file",
        "-F",
        dest="message_file",
        help="Read message from file (use '-' for stdin)",
    )
    p_send.add_argument(
        "--stdin",
        action="store_true",
        default=False,
        help="Read message from stdin",
    )
    p_send.add_argument(
        "--priority", "-p", type=int, default=3, help="Priority level 1-5 (default: 3)"
    )
    p_send.add_argument(
        "--from", "-f", dest="sender", help="Sender agent ID (for reply identification)"
    )
    p_send.add_argument(
        "--attach",
        "-a",
        action="append",
        dest="attach",
        help="Attach a file to the message (repeatable)",
    )
    _add_response_mode_flags(p_send)
    p_send.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Send even if target is in a different working directory",
    )
    p_send.set_defaults(func=cmd_send)

    # interrupt (ergonomic shorthand for priority-4 send --silent)
    p_interrupt = subparsers.add_parser(
        "interrupt",
        help="Send an urgent interrupt message to an agent (priority 4, fire-and-forget)",
        description="Shorthand for 'synapse send <target> <message> -p 4 --silent'.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  synapse interrupt claude "Stop and review"
  synapse interrupt gemini "Check status" --from $SYNAPSE_AGENT_ID""",
    )
    p_interrupt.add_argument("target", help="Target agent (claude, codex, gemini)")
    p_interrupt.add_argument("message", help="Interrupt message to send")
    p_interrupt.add_argument(
        "--from", "-f", dest="sender", help="Sender agent ID (for reply identification)"
    )
    p_interrupt.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Send even if target is in a different working directory",
    )
    p_interrupt.set_defaults(func=cmd_interrupt)

    # broadcast
    p_broadcast = subparsers.add_parser(
        "broadcast",
        help="Send a message to all agents in current working directory",
        description="Broadcast an A2A message to running agents in the current working directory.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  synapse broadcast "Status check"                Send to all agents in current directory
  synapse broadcast "Urgent update" -p 4          Send urgent message
  synapse broadcast "FYI only" --silent           Fire-and-forget broadcast""",
    )
    p_broadcast.add_argument(
        "message", nargs="?", default=None, help="Message to broadcast"
    )
    p_broadcast.add_argument(
        "--message-file",
        "-F",
        dest="message_file",
        help="Read message from file (use '-' for stdin)",
    )
    p_broadcast.add_argument(
        "--stdin",
        action="store_true",
        default=False,
        help="Read message from stdin",
    )
    p_broadcast.add_argument(
        "--priority", "-p", type=int, default=1, help="Priority level 1-5 (default: 1)"
    )
    p_broadcast.add_argument(
        "--from", "-f", dest="sender", help="Sender agent ID (for reply identification)"
    )
    p_broadcast.add_argument(
        "--attach",
        "-a",
        action="append",
        dest="attach",
        help="Attach a file to the message (repeatable)",
    )
    _add_response_mode_flags(p_broadcast)
    p_broadcast.set_defaults(func=cmd_broadcast)

    # reply - Reply to last received A2A message
    p_reply = subparsers.add_parser(
        "reply",
        help="Reply to the last received A2A message",
        description="Reply to the last received A2A message using reply tracking.",
        epilog="""Examples:
  synapse reply "Here is my response"      Reply to the last message
  synapse reply "Task completed!"          Send completion reply
  synapse reply "Done" --from $SYNAPSE_AGENT_ID   Reply with explicit sender (for sandboxed envs)
  synapse reply "Done" --to sender-agent-id       Reply to a specific sender
  synapse reply --list-targets                     List available reply targets""",
    )
    p_reply.add_argument(
        "--from",
        dest="sender",
        help="Your agent ID (required in sandboxed environments like Codex)",
    )
    p_reply.add_argument(
        "--to",
        dest="to",
        help="Reply to a specific sender ID (default: last message)",
    )
    p_reply.add_argument(
        "--list-targets",
        action="store_true",
        default=False,
        help="List available reply targets and exit",
    )
    p_reply.add_argument("message", nargs="?", default="", help="Reply message content")
    p_reply.set_defaults(func=cmd_reply)

    # trace - Trace task id across history and file-safety records
    p_trace = subparsers.add_parser(
        "trace",
        help="Trace a task ID across history and file modifications",
        description="Show task history details and file-safety modifications for the same task ID.",
    )
    p_trace.add_argument("task_id", help="Task ID to trace")
    p_trace.set_defaults(func=cmd_trace)

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
        help="Agent type (claude, gemini, codex, opencode, copilot). If omitted, shows default.",
    )
    p_inst_show.set_defaults(func=cmd_instructions_show)

    # instructions files
    p_inst_files = instructions_subparsers.add_parser(
        "files", help="List instruction files"
    )
    p_inst_files.add_argument(
        "agent_type",
        nargs="?",
        help="Agent type (claude, gemini, codex, opencode, copilot). If omitted, shows default.",
    )
    p_inst_files.set_defaults(func=cmd_instructions_files)

    # instructions send
    p_inst_send = instructions_subparsers.add_parser(
        "send", help="Send instructions to a running agent"
    )
    p_inst_send.add_argument(
        "target",
        help="Target agent: profile (claude, gemini, codex, opencode, copilot) or agent ID",
    )
    p_inst_send.add_argument(
        "--preview",
        "-p",
        action="store_true",
        help="Preview instruction without sending",
    )
    p_inst_send.set_defaults(func=cmd_instructions_send)

    # mcp - Minimal MCP server for bootstrap resources
    p_mcp = subparsers.add_parser(
        "mcp",
        help="Serve Synapse MCP resources",
        description="Serve Synapse bootstrap resources over MCP stdio transport.",
    )
    mcp_subparsers = p_mcp.add_subparsers(dest="mcp_command", metavar="SUBCOMMAND")

    p_mcp_serve = mcp_subparsers.add_parser(
        "serve", help="Serve MCP resources over stdio"
    )
    p_mcp_serve.add_argument(
        "--agent-id",
        default=os.environ.get("SYNAPSE_AGENT_ID", "synapse-mcp"),
        help="Agent ID used for instruction placeholder resolution",
    )
    p_mcp_serve.add_argument(
        "--agent-type",
        default=None,
        help="Agent type used for instruction resolution (defaults to type inferred from agent ID)",
    )
    p_mcp_serve.add_argument(
        "--port",
        type=int,
        default=0,
        help="Port value used for instruction placeholder resolution",
    )
    p_mcp_serve.set_defaults(func=cmd_mcp_serve)

    # history - Task history management
    p_history = subparsers.add_parser(
        "history",
        help="View and manage task history",
        description="""View and manage A2A task history.

History is enabled by default (v0.3.13+). To disable: SYNAPSE_HISTORY_ENABLED=false""",
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

    # wiki - LLM wiki management
    p_wiki = subparsers.add_parser("wiki", help="LLM Wiki knowledge management")
    wiki_subparsers = p_wiki.add_subparsers(dest="wiki_command", metavar="SUBCOMMAND")

    p_wiki_ingest = wiki_subparsers.add_parser(
        "ingest", help="Ingest a source into the wiki"
    )
    p_wiki_ingest.add_argument("source", help="Path to source file")
    p_wiki_ingest.add_argument(
        "--scope", choices=["project", "global"], default="project"
    )
    p_wiki_ingest.set_defaults(func=cmd_wiki_ingest)

    p_wiki_query = wiki_subparsers.add_parser("query", help="Query the wiki")
    p_wiki_query.add_argument("question", help="Question to search for")
    p_wiki_query.add_argument(
        "--scope", choices=["project", "global"], default="project"
    )
    p_wiki_query.set_defaults(func=cmd_wiki_query)

    p_wiki_lint = wiki_subparsers.add_parser("lint", help="Check wiki consistency")
    p_wiki_lint.add_argument(
        "--scope", choices=["project", "global"], default="project"
    )
    p_wiki_lint.set_defaults(func=cmd_wiki_lint)

    p_wiki_status = wiki_subparsers.add_parser("status", help="Show wiki status")
    p_wiki_status.add_argument(
        "--scope", choices=["project", "global"], default="project"
    )
    p_wiki_status.set_defaults(func=cmd_wiki_status)

    p_wiki_refresh = wiki_subparsers.add_parser(
        "refresh", help="Detect and refresh stale pages"
    )
    p_wiki_refresh.add_argument(
        "--scope", choices=["project", "global"], default="project"
    )
    p_wiki_refresh.add_argument(
        "--apply", action="store_true", help="Update source_commit in stale pages"
    )
    p_wiki_refresh.set_defaults(func=cmd_wiki_refresh)

    p_wiki_init = wiki_subparsers.add_parser(
        "init", help="Initialize wiki with skeleton pages"
    )
    p_wiki_init.add_argument(
        "--scope", choices=["project", "global"], default="project"
    )
    p_wiki_init.set_defaults(func=cmd_wiki_init)

    # worktree - Git worktree management
    p_worktree = subparsers.add_parser(
        "worktree",
        help="Manage git worktrees",
        description="Manage Synapse git worktrees.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n  synapse worktree prune",
    )
    worktree_subparsers = p_worktree.add_subparsers(
        dest="worktree_command", metavar="SUBCOMMAND"
    )

    p_wt_prune = worktree_subparsers.add_parser(
        "prune", help="Remove orphan worktrees whose directories no longer exist"
    )
    p_wt_prune.set_defaults(func=cmd_worktree_prune)

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

Creates settings file and copies skills to .agents (if .claude skills exist).""",
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

Also re-copies skills from .claude to .agents.""",
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
  synapse config                    Interactive editor (effective values)
  synapse config show               Show effective settings (read-only)
  synapse config show --scope user  Show user settings only""",
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
  synapse file-safety debug        Show troubleshooting info

Integration with synapse list:
  When file-safety is enabled, active locks appear in the EDITING_FILE column
  of 'synapse list', showing which file each agent is currently editing.""",
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
        "locks",
        help="List active file locks (also shown in 'synapse list' EDITING_FILE column)",
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
    p_fs_lock.add_argument(
        "--wait",
        action="store_true",
        help="Wait until the lock becomes available",
    )
    p_fs_lock.add_argument(
        "--wait-timeout",
        type=float,
        default=None,
        help="Max seconds to wait for the lock (default: wait forever)",
    )
    p_fs_lock.add_argument(
        "--wait-interval",
        type=float,
        default=2.0,
        help="Seconds between lock retry attempts (default: 2.0)",
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

    # memory - Shared Memory
    p_memory = subparsers.add_parser(
        "memory",
        help="Shared memory for cross-agent knowledge sharing",
        description="Manage the shared memory knowledge base for cross-agent collaboration.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  synapse memory save auth-pattern "Use OAuth2 with PKCE" --tags auth,security
  synapse memory save repo-tip "Use uv" --scope project
  synapse memory list --scope global
  synapse memory search "auth" --scope private
  synapse memory show auth-pattern
  synapse memory stats
  synapse memory delete auth-pattern --force""",
    )
    memory_subparsers = p_memory.add_subparsers(
        dest="memory_command", metavar="SUBCOMMAND"
    )

    p_mem_save = memory_subparsers.add_parser("save", help="Save a memory entry")
    p_mem_save.add_argument("key", help="Memory key (e.g., auth-pattern)")
    p_mem_save.add_argument("content", help="Memory content")
    p_mem_save.add_argument("--tags", help="Comma-separated tags (e.g., arch,security)")
    p_mem_save.add_argument(
        "--scope",
        choices=["global", "project", "private"],
        default="global",
        help="Memory visibility scope (default: global)",
    )
    p_mem_save.add_argument(
        "--notify", action="store_true", help="Broadcast notification to other agents"
    )
    p_mem_save.set_defaults(func=cmd_memory_save)

    p_mem_list = memory_subparsers.add_parser("list", help="List memories")
    p_mem_list.add_argument("--author", help="Filter by author agent ID")
    p_mem_list.add_argument("--tags", help="Filter by tags (comma-separated)")
    p_mem_list.add_argument(
        "--scope",
        choices=["global", "project", "private"],
        default="global",
        help="Filter by visibility scope (default: global)",
    )
    p_mem_list.add_argument(
        "--limit", "-n", type=int, default=50, help="Max entries (default: 50)"
    )
    p_mem_list.set_defaults(func=cmd_memory_list)

    p_mem_show = memory_subparsers.add_parser("show", help="Show memory details")
    p_mem_show.add_argument("id_or_key", help="Memory ID or key")
    p_mem_show.set_defaults(func=cmd_memory_show)

    p_mem_search = memory_subparsers.add_parser("search", help="Search memories")
    p_mem_search.add_argument("query", help="Search query")
    p_mem_search.add_argument(
        "--scope",
        choices=["global", "project", "private"],
        default="global",
        help="Filter by visibility scope (default: global)",
    )
    p_mem_search.set_defaults(func=cmd_memory_search)

    p_mem_delete = memory_subparsers.add_parser("delete", help="Delete a memory")
    p_mem_delete.add_argument("id_or_key", help="Memory ID or key")
    p_mem_delete.add_argument(
        "--force", "-f", action="store_true", help="Skip confirmation"
    )
    p_mem_delete.set_defaults(func=cmd_memory_delete)

    p_mem_stats = memory_subparsers.add_parser("stats", help="Show memory statistics")
    p_mem_stats.set_defaults(func=cmd_memory_stats)

    # team - Team management (B6)
    p_team = subparsers.add_parser(
        "team",
        help="Team management commands",
        description="Manage teams of agents.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Quick Start:
  synapse team start claude gemini
  synapse team start claude gemini codex --worktree

Run 'synapse team <subcommand> --help' for detailed usage.""",
    )
    team_subparsers = p_team.add_subparsers(dest="team_command", metavar="SUBCOMMAND")

    p_team_start = team_subparsers.add_parser(
        "start",
        help="Start multiple agents with split panes",
        description="""Start multiple agents in terminal panes (tmux, iTerm2, zellij, etc.).
        
Extended Specification:
  You can specify name, role, and skill set using colon-separated format:
  'profile:name:role:skill_set'
  
  Examples:
    synapse team start claude gemini
    synapse team start claude:Reviewer:code-review:dev-set gemini:Searcher
    synapse team start codex::unittest:none""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_team_start.add_argument(
        "agents",
        nargs="+",
        help="Agent specs to start (profile[:name[:role[:skill_set]]])",
    )
    p_team_start.add_argument(
        "--layout",
        default="split",
        choices=["split", "horizontal", "vertical"],
        help="Pane layout (default: split)",
    )
    p_team_start.add_argument(
        "--all-new",
        action="store_true",
        help="Start all agents in new panes/tabs instead of using current terminal",
    )
    p_team_start.add_argument(
        "--worktree",
        "-w",
        nargs="?",
        const=True,
        default=None,
        metavar="NAME",
        help="Create git worktree per agent for isolated work (default: enabled for 2+ agents; optional NAME prefix)",
    )
    p_team_start.add_argument(
        "--no-worktree",
        dest="worktree",
        action="store_false",
        help="Disable worktree isolation (agents share the working directory)",
    )
    p_team_start.add_argument(
        "--branch",
        "-b",
        default=None,
        help="Base branch for worktree (default: remote default branch)",
    )
    p_team_start.add_argument(
        "--no-auto-approve",
        action="store_true",
        default=False,
        help="Disable automatic tool approval (both CLI flag and runtime)",
    )
    p_team_start.set_defaults(func=cmd_team_start)

    # session - Session save/restore
    p_session = subparsers.add_parser(
        "session",
        help="Save and restore team configurations",
        description="Save running agent configurations as named snapshots and restore them later.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Quick Start:
  synapse session save review-team
  synapse session list
  synapse session show review-team
  synapse session restore review-team

Run 'synapse session <subcommand> --help' for detailed usage.""",
    )
    session_subparsers = p_session.add_subparsers(
        dest="session_command", metavar="SUBCOMMAND"
    )

    def _add_scope_filter_args(p: argparse.ArgumentParser) -> None:
        scope_group = p.add_mutually_exclusive_group()
        scope_group.add_argument(
            "--project",
            action="store_true",
            default=False,
            help="Project scope (default): .synapse/sessions/",
        )
        scope_group.add_argument(
            "--user",
            action="store_true",
            default=False,
            help="User scope: ~/.synapse/sessions/",
        )
        scope_group.add_argument(
            "--workdir",
            metavar="DIR",
            help="Use DIR/.synapse/sessions/ as session store (for list/show/restore/delete)",
        )

    # session save
    p_session_save = session_subparsers.add_parser(
        "save",
        help="Save running agents as a named session",
    )
    p_session_save.add_argument("session_name", help="Session name")
    _add_scope_filter_args(p_session_save)
    p_session_save.set_defaults(func=cmd_session_save)

    # session list
    p_session_list = session_subparsers.add_parser(
        "list",
        help="List saved sessions",
    )
    _add_scope_filter_args(p_session_list)
    p_session_list.set_defaults(func=cmd_session_list)

    # session show
    p_session_show = session_subparsers.add_parser(
        "show",
        help="Show session details",
    )
    p_session_show.add_argument("session_name", help="Session name")
    _add_scope_filter_args(p_session_show)
    p_session_show.set_defaults(func=cmd_session_show)

    # session restore
    p_session_restore = session_subparsers.add_parser(
        "restore",
        help="Restore a saved session by spawning agents",
    )
    p_session_restore.add_argument("session_name", help="Session name to restore")
    _add_scope_filter_args(p_session_restore)
    p_session_restore.add_argument(
        "--worktree",
        "-w",
        nargs="?",
        const=True,
        default=None,
        metavar="NAME",
        help="Create git worktree per agent (overrides saved worktree settings)",
    )
    p_session_restore.add_argument(
        "--resume",
        action="store_true",
        default=False,
        help="Resume each agent's previous CLI session (conversation history)",
    )
    p_session_restore.set_defaults(func=cmd_session_restore)

    # session delete
    p_session_delete = session_subparsers.add_parser(
        "delete",
        help="Delete a saved session",
    )
    p_session_delete.add_argument("session_name", help="Session name to delete")
    _add_scope_filter_args(p_session_delete)
    p_session_delete.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Delete without confirmation",
    )
    p_session_delete.set_defaults(func=cmd_session_delete)

    # session sessions (CLI tool session listing)
    p_session_sessions = session_subparsers.add_parser(
        "sessions",
        help="List CLI tool sessions from filesystem",
    )
    p_session_sessions.add_argument(
        "--profile",
        choices=["claude", "gemini", "codex", "copilot"],
        help="Filter by CLI tool profile",
    )
    p_session_sessions.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of sessions to show (default: 20)",
    )
    p_session_sessions.set_defaults(func=cmd_session_sessions)

    # ── workflow ─────────────────────────────────────────────
    p_workflow = subparsers.add_parser(
        "workflow",
        help="Create, manage, and run saved message workflows",
        description="Save reusable YAML message sequences and replay them.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Quick Start:
  synapse workflow create my-review
  synapse workflow list
  synapse workflow show my-review
  synapse workflow run my-review --dry-run
  synapse workflow run my-review

Run 'synapse workflow <subcommand> --help' for detailed usage.""",
    )
    workflow_subparsers = p_workflow.add_subparsers(
        dest="workflow_command", metavar="SUBCOMMAND"
    )

    def _add_workflow_scope_args(p: argparse.ArgumentParser) -> None:
        scope_group = p.add_mutually_exclusive_group()
        scope_group.add_argument(
            "--project",
            action="store_true",
            default=False,
            help="Project scope (default): .synapse/workflows/",
        )
        scope_group.add_argument(
            "--user",
            action="store_true",
            default=False,
            help="User scope: ~/.synapse/workflows/",
        )

    # workflow create
    p_workflow_create = workflow_subparsers.add_parser(
        "create",
        help="Create a new workflow template",
    )
    p_workflow_create.add_argument("workflow_name", help="Workflow name")
    _add_workflow_scope_args(p_workflow_create)
    p_workflow_create.add_argument(
        "--force", "-f", action="store_true", help="Overwrite if exists"
    )
    p_workflow_create.set_defaults(func=cmd_workflow_create)

    # workflow list
    p_workflow_list = workflow_subparsers.add_parser(
        "list",
        help="List saved workflows",
    )
    _add_workflow_scope_args(p_workflow_list)
    p_workflow_list.set_defaults(func=cmd_workflow_list)

    # workflow show
    p_workflow_show = workflow_subparsers.add_parser(
        "show",
        help="Show workflow details",
    )
    p_workflow_show.add_argument("workflow_name", help="Workflow name")
    _add_workflow_scope_args(p_workflow_show)
    p_workflow_show.set_defaults(func=cmd_workflow_show)

    # workflow run
    p_workflow_run = workflow_subparsers.add_parser(
        "run",
        help="Execute a workflow",
    )
    p_workflow_run.add_argument("workflow_name", help="Workflow name to execute")
    _add_workflow_scope_args(p_workflow_run)
    p_workflow_run.add_argument(
        "--dry-run",
        action="store_true",
        help="Print steps without sending",
    )
    p_workflow_run.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Don't abort on first step failure",
    )
    p_workflow_run.add_argument(
        "--auto-spawn",
        action="store_true",
        help="Auto-spawn agents that are not running (target is used as profile name)",
    )
    p_workflow_run.add_argument(
        "--async",
        dest="run_async",
        action="store_true",
        default=False,
        help="Run in background (returns run_id)",
    )
    p_workflow_run.set_defaults(func=cmd_workflow_run)

    # workflow status
    p_workflow_status = workflow_subparsers.add_parser(
        "status",
        help="Show workflow run status",
    )
    p_workflow_status.add_argument("run_id", help="Workflow run ID")
    p_workflow_status.set_defaults(func=cmd_workflow_status)

    # workflow delete
    p_workflow_delete = workflow_subparsers.add_parser(
        "delete",
        help="Delete a saved workflow",
    )
    p_workflow_delete.add_argument("workflow_name", help="Workflow name to delete")
    _add_workflow_scope_args(p_workflow_delete)
    p_workflow_delete.add_argument(
        "--force", "-f", action="store_true", help="Delete without confirmation"
    )
    p_workflow_delete.set_defaults(func=cmd_workflow_delete)

    # workflow sync
    p_workflow_sync = workflow_subparsers.add_parser(
        "sync",
        help="Sync workflow YAMLs to skill directories",
    )
    p_workflow_sync.set_defaults(func=cmd_workflow_sync)

    # ── multiagent (map) ──────────────────────────────────────
    p_multiagent = subparsers.add_parser(
        "multiagent",
        aliases=["map", "ma"],
        help="Multi-agent coordination patterns",
        description="Multi-agent coordination patterns.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Quick Start:
  synapse map init generator-verifier --name my-review
  synapse map list
  synapse map show my-review
  synapse map run my-review --task "Review the auth module" --dry-run
  synapse map run my-review --task "Review the auth module"

Run 'synapse multiagent <subcommand> --help' for detailed usage.""",
    )
    multiagent_subparsers = p_multiagent.add_subparsers(
        dest="multiagent_command", metavar="SUBCOMMAND"
    )

    def _add_multiagent_scope_args(p: argparse.ArgumentParser) -> None:
        scope_group = p.add_mutually_exclusive_group()
        scope_group.add_argument(
            "--project",
            action="store_true",
            default=False,
            help="Project scope (default): .synapse/patterns/",
        )
        scope_group.add_argument(
            "--user",
            action="store_true",
            default=False,
            help="User scope: ~/.synapse/patterns/",
        )

    p_ma_init = multiagent_subparsers.add_parser("init", help="Create pattern template")
    p_ma_init.add_argument(
        "pattern_type",
        help=(
            "Pattern type (generator-verifier, orchestrator-subagent, "
            "agent-teams, message-bus, shared-state)"
        ),
    )
    p_ma_init.add_argument("--name", "-n", help="Pattern name (default: pattern type)")
    _add_multiagent_scope_args(p_ma_init)
    p_ma_init.add_argument(
        "--force", "-f", action="store_true", help="Overwrite if exists"
    )
    p_ma_init.set_defaults(func=cmd_multiagent_init)

    p_ma_list = multiagent_subparsers.add_parser("list", help="List defined patterns")
    _add_multiagent_scope_args(p_ma_list)
    p_ma_list.set_defaults(func=cmd_multiagent_list)

    p_ma_show = multiagent_subparsers.add_parser("show", help="Show pattern details")
    p_ma_show.add_argument("pattern_name", help="Pattern name")
    _add_multiagent_scope_args(p_ma_show)
    p_ma_show.set_defaults(func=cmd_multiagent_show)

    p_ma_run = multiagent_subparsers.add_parser("run", help="Execute a pattern")
    p_ma_run.add_argument("pattern_name", help="Pattern name or built-in type")
    p_ma_run.add_argument("--task", "-t", required=True, help="Task description")
    _add_multiagent_scope_args(p_ma_run)
    p_ma_run.add_argument(
        "--dry-run", action="store_true", help="Preview without executing"
    )
    p_ma_run.add_argument(
        "--async", dest="run_async", action="store_true", help="Run in background"
    )
    p_ma_run.set_defaults(func=cmd_multiagent_run)

    p_ma_status = multiagent_subparsers.add_parser("status", help="Check run status")
    p_ma_status.add_argument("run_id", help="Pattern run ID")
    p_ma_status.set_defaults(func=cmd_multiagent_status)

    p_ma_stop = multiagent_subparsers.add_parser("stop", help="Stop running pattern")
    p_ma_stop.add_argument("run_id", help="Pattern run ID")
    p_ma_stop.set_defaults(func=cmd_multiagent_stop)

    # spawn - Spawn single agent in new pane
    p_spawn = subparsers.add_parser(
        "spawn",
        help="Spawn a single agent in a new terminal pane",
        description="""Spawn a single agent in a new terminal pane.

Unlike 'synapse start' (background), this opens an interactive terminal.
Unlike 'synapse team start' (multiple agents), this spawns exactly one.

Outputs '{agent_id} {port}' on success for scripting use.""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  synapse spawn claude                          Spawn Claude in a new pane
  synapse spawn silent-snake                    Spawn by saved agent ID
  synapse spawn Alice                           Spawn by saved agent name
  synapse spawn gemini --port 8115              Spawn Gemini on specific port
  synapse spawn claude --name Tester --role "test writer"
  synapse spawn claude --terminal tmux          Use specific terminal""",
    )
    p_spawn.add_argument(
        "profile",
        help="Agent profile, saved agent ID, or saved agent name",
    )
    p_spawn.add_argument(
        "--port",
        type=int,
        help="Explicit port (default: auto-assigned from profile range)",
    )
    p_spawn.add_argument(
        "--name",
        "-n",
        help="Custom agent name",
    )
    p_spawn.add_argument(
        "--role",
        "-r",
        help="Agent role description",
    )
    p_spawn.add_argument(
        "--skill-set",
        "-S",
        dest="skill_set",
        help="Skill set to activate",
    )
    p_spawn.add_argument(
        "--terminal",
        help="Terminal app to use (default: auto-detect)",
    )
    task_group = p_spawn.add_mutually_exclusive_group()
    task_group.add_argument(
        "--task",
        dest="task",
        default=None,
        help="Send a task message after the spawned agent becomes ready",
    )
    task_group.add_argument(
        "--task-file",
        dest="task_file",
        default=None,
        help="Read the task message from a file ('-' to read from stdin)",
    )
    p_spawn.add_argument(
        "--task-timeout",
        dest="task_timeout",
        type=int,
        default=30,
        help="Seconds to wait for the spawned agent before sending the task (default: 30)",
    )
    _add_response_mode_flags(p_spawn)
    p_spawn.add_argument(
        "--worktree",
        "-w",
        nargs="?",
        const=True,
        default=None,
        metavar="NAME",
        help="Create git worktree for isolated work (optional NAME)",
    )
    p_spawn.add_argument(
        "--branch",
        "-b",
        default=None,
        help="Base branch for worktree (default: remote default branch). Only used with --worktree.",
    )
    p_spawn.add_argument(
        "--no-auto-approve",
        action="store_true",
        default=False,
        help="Disable automatic tool approval (both CLI flag and runtime)",
    )
    # tool_args are extracted from sys.argv before parse_args() —
    # see the _extract_tool_args_from_argv() call in main().
    p_spawn.set_defaults(func=cmd_spawn)

    # agents - Saved agent definition management
    p_agents = subparsers.add_parser(
        "agents",
        help="Manage saved agent definitions",
        description="""Manage reusable agent definitions used by `synapse spawn`.

IDs must use petname format, e.g. `silent-snake`.""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    agents_subparsers = p_agents.add_subparsers(
        dest="agents_command", metavar="SUBCOMMAND"
    )

    p_agents_list = agents_subparsers.add_parser("list", help="List saved agents")
    p_agents_list.set_defaults(func=cmd_agents_list)

    p_agents_show = agents_subparsers.add_parser(
        "show", help="Show details for a saved agent"
    )
    p_agents_show.add_argument("id_or_name", help="Saved agent ID or display name")
    p_agents_show.set_defaults(func=cmd_agents_show)

    p_agents_add = agents_subparsers.add_parser(
        "add", help="Add or update a saved agent"
    )
    p_agents_add.add_argument("id", help="Saved agent ID (petname format)")
    p_agents_add.add_argument("--name", required=True, help="Display name")
    p_agents_add.add_argument(
        "--profile",
        required=True,
        help="Agent profile (claude, codex, gemini, opencode, copilot)",
    )
    p_agents_add.add_argument("--role", help="Role description or @role-file")
    p_agents_add.add_argument("--skill-set", "-S", dest="skill_set", help="Skill set")
    p_agents_add.add_argument(
        "--scope",
        choices=["project", "user"],
        default="project",
        help="Storage scope (default: project)",
    )
    p_agents_add.set_defaults(func=cmd_agents_add)

    p_agents_delete = agents_subparsers.add_parser(
        "delete", help="Delete a saved agent by ID or name"
    )
    p_agents_delete.add_argument("id_or_name", help="Saved agent ID or display name")
    p_agents_delete.set_defaults(func=cmd_agents_delete)

    # approve - Plan approval (B3)
    p_approve = subparsers.add_parser(
        "approve",
        help="Approve a plan for a task",
    )
    p_approve.add_argument("task_id", help="Task ID to approve")
    p_approve.set_defaults(func=cmd_approve)

    # reject - Plan rejection (B3)
    p_reject = subparsers.add_parser(
        "reject",
        help="Reject a plan for a task",
    )
    p_reject.add_argument("task_id", help="Task ID to reject")
    p_reject.add_argument("reason", nargs="?", default="", help="Rejection reason")
    p_reject.set_defaults(func=cmd_reject)

    # skills - Skill manager (browse, delete, move, deploy, import, create, add, sets)
    p_skills = subparsers.add_parser(
        "skills",
        help="Browse and manage skills",
        description="""Browse, delete, move, deploy, import, and create skills across scopes.

Scopes:
  synapse  Skills in ~/.synapse/skills/ (central store)
  user     Skills in ~/.<agent>/skills/
  project  Skills in ./.<agent>/skills/
  plugin   Skills in ./plugins/*/skills/ (read-only)""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  synapse skills                                          Interactive skill manager
  synapse skills list                                     List all skills
  synapse skills list --scope synapse                     List synapse-scope skills
  synapse skills show agent-memory                        Show skill details
  synapse skills delete agent-memory -f                   Delete a skill
  synapse skills move agent-memory --to project           Move to project scope
  synapse skills deploy code-quality --agent claude,codex Deploy to agent dirs
  synapse skills import agent-memory                      Import to central store
  synapse skills add github.com/user/skills               Add from repository
  synapse skills create                                   Create new skill
  synapse skills set list                                 List skill sets
  synapse skills set show reviewer                        Show skill set details""",
    )
    p_skills.set_defaults(func=cmd_skills)

    # skills subcommands
    skills_subparsers = p_skills.add_subparsers(
        dest="skills_command", metavar="SUBCOMMAND"
    )

    # skills list
    p_sk_list = skills_subparsers.add_parser("list", help="List all skills")
    p_sk_list.add_argument(
        "--scope",
        choices=["synapse", "user", "project", "plugin"],
        help="Filter by scope",
    )
    p_sk_list.set_defaults(func=cmd_skills_list)

    # skills show
    p_sk_show = skills_subparsers.add_parser("show", help="Show skill details")
    p_sk_show.add_argument("name", help="Skill name")
    p_sk_show.add_argument(
        "--scope",
        choices=["synapse", "user", "project", "plugin"],
        help="Scope to look in (if same name exists in multiple scopes)",
    )
    p_sk_show.set_defaults(func=cmd_skills_show)

    # skills delete
    p_sk_delete = skills_subparsers.add_parser("delete", help="Delete a skill")
    p_sk_delete.add_argument("name", help="Skill name to delete")
    p_sk_delete.add_argument(
        "--scope",
        choices=["synapse", "user", "project"],
        help="Scope to delete from",
    )
    p_sk_delete.add_argument(
        "--force", "-f", action="store_true", help="Skip confirmation"
    )
    p_sk_delete.set_defaults(func=cmd_skills_delete)

    # skills move
    p_sk_move = skills_subparsers.add_parser(
        "move", help="Move a skill to another scope"
    )
    p_sk_move.add_argument("name", help="Skill name to move")
    p_sk_move.add_argument(
        "--to",
        required=True,
        choices=["user", "project"],
        help="Target scope",
    )
    p_sk_move.set_defaults(func=cmd_skills_move)

    # skills deploy
    p_sk_deploy = skills_subparsers.add_parser(
        "deploy", help="Deploy a skill to agent directories"
    )
    p_sk_deploy.add_argument("name", help="Skill name to deploy")
    p_sk_deploy.add_argument(
        "--agent",
        default="claude",
        help="Target agents (comma-separated, e.g. claude,gemini,codex,opencode,copilot). Default: claude",
    )
    p_sk_deploy.add_argument(
        "--scope",
        dest="deploy_scope",
        choices=["user", "project"],
        default="user",
        help="Deploy scope (default: user)",
    )
    p_sk_deploy.set_defaults(func=cmd_skills_deploy)

    # skills import
    p_sk_import = skills_subparsers.add_parser(
        "import", help="Import a skill to ~/.synapse/skills/"
    )
    p_sk_import.add_argument("name", help="Skill name to import")
    p_sk_import.add_argument(
        "--from",
        dest="from_scope",
        choices=["user", "project"],
        help="Source scope to import from",
    )
    p_sk_import.set_defaults(func=cmd_skills_import)

    # skills add
    p_sk_add = skills_subparsers.add_parser(
        "add", help="Add a skill from a repository via npx"
    )
    p_sk_add.add_argument("repo", help="Repository URL or identifier")
    p_sk_add.set_defaults(func=cmd_skills_add)

    # skills create
    p_sk_create = skills_subparsers.add_parser(
        "create", help="Create a new skill in ~/.synapse/skills/"
    )
    p_sk_create.add_argument("name", nargs="?", default=None, help="Skill name")
    p_sk_create.set_defaults(func=cmd_skills_create)

    # skills set (skill set management)
    p_sk_set = skills_subparsers.add_parser(
        "set", help="Manage skill sets (named groups of skills)"
    )
    p_sk_set.set_defaults(func=cmd_skills_set)

    sk_set_subparsers = p_sk_set.add_subparsers(
        dest="set_command", metavar="SUBCOMMAND"
    )

    # skills set list
    p_sk_set_list = sk_set_subparsers.add_parser("list", help="List all skill sets")
    p_sk_set_list.set_defaults(func=cmd_skills_set_list)

    # skills set show
    p_sk_set_show = sk_set_subparsers.add_parser("show", help="Show skill set details")
    p_sk_set_show.add_argument("name", help="Skill set name")
    p_sk_set_show.set_defaults(func=cmd_skills_set_show)

    # skills apply <target> <set_name> [--dry-run]
    p_sk_apply = skills_subparsers.add_parser(
        "apply", help="Apply a skill set to a running agent"
    )
    p_sk_apply.add_argument("target", help="Agent name, ID, or type")
    p_sk_apply.add_argument("set_name", help="Skill set name to apply")
    p_sk_apply.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Preview changes without applying",
    )
    p_sk_apply.set_defaults(func=cmd_skills_apply)

    # ── canvas ───────────────────────────────────────────────────
    p_canvas = subparsers.add_parser(
        "canvas",
        help="Canvas board — shared visual output surface",
        description="Post and view rich content cards (diagrams, tables, code, etc.) in the browser.",
    )
    canvas_subparsers = p_canvas.add_subparsers(
        dest="canvas_command", metavar="SUBCOMMAND"
    )

    # canvas serve
    p_canvas_serve = canvas_subparsers.add_parser("serve", help="Start Canvas server")
    p_canvas_serve.add_argument(
        "--port", type=int, default=None, help="Server port (default: 3000)"
    )
    p_canvas_serve.add_argument(
        "--no-open",
        action="store_true",
        help="Do not open Canvas in the browser after starting the server",
    )
    p_canvas_serve.set_defaults(func=cmd_canvas_serve)

    # canvas post <format> <body> [options]
    p_canvas_post = canvas_subparsers.add_parser("post", help="Post a card to Canvas")
    p_canvas_post.add_argument(
        "format",
        nargs="?",
        default=None,
        help="Content format (mermaid, markdown, html, artifact, table, json, diff, code, chart, image, progress, terminal, dependency-graph, cost, ...)",
    )
    p_canvas_post.add_argument(
        "body",
        nargs="?",
        default=None,
        help="Content body (or '-' / --stdin to read from stdin)",
    )
    p_canvas_post.add_argument(
        "--stdin",
        action="store_true",
        help="Read body from stdin",
    )
    p_canvas_post.add_argument(
        "--example",
        default=None,
        help="Print a working example command for the given format and exit",
    )
    p_canvas_post.add_argument("--title", default="", help="Card title")
    p_canvas_post.add_argument(
        "--agent-id", default=os.environ.get("SYNAPSE_AGENT_ID", "cli"), help="Agent ID"
    )
    p_canvas_post.add_argument("--agent-name", default="", help="Agent display name")
    p_canvas_post.add_argument("--card-id", default=None, help="Card ID for upsert")
    p_canvas_post.add_argument(
        "--pinned", action="store_true", default=False, help="Pin card (no TTL expiry)"
    )
    p_canvas_post.add_argument("--tags", default=None, help="Comma-separated tags")
    p_canvas_post.add_argument(
        "--lang", default=None, help="Language hint (for code format)"
    )
    p_canvas_post.add_argument("--port", type=int, default=None, help="Server port")
    p_canvas_post.add_argument(
        "--file", default=None, help="Read body from file instead of argument"
    )
    p_canvas_post.set_defaults(func=cmd_canvas_post)

    # canvas list [options]
    p_canvas_list = canvas_subparsers.add_parser("list", help="List cards")
    p_canvas_list.add_argument("--agent-id", default=None, help="Filter by agent ID")
    p_canvas_list.add_argument("--type", default=None, help="Filter by content type")
    p_canvas_list.add_argument("--search", default=None, help="Search by title")
    p_canvas_list.set_defaults(func=cmd_canvas_list)

    # canvas delete <card_id>
    p_canvas_delete = canvas_subparsers.add_parser("delete", help="Delete a card")
    p_canvas_delete.add_argument("card_id", help="Card ID to delete")
    p_canvas_delete.add_argument(
        "--agent-id", default=os.environ.get("SYNAPSE_AGENT_ID", "cli"), help="Agent ID"
    )
    p_canvas_delete.set_defaults(func=cmd_canvas_delete)

    # canvas clear
    p_canvas_clear = canvas_subparsers.add_parser("clear", help="Clear all cards")
    p_canvas_clear.add_argument(
        "--agent-id", default=None, help="Clear only this agent's cards"
    )
    p_canvas_clear.set_defaults(func=cmd_canvas_clear)

    # canvas briefing [json_data] — Post a briefing card
    p_canvas_briefing = canvas_subparsers.add_parser(
        "briefing", help="Post a briefing card (structured report with sections)"
    )
    p_canvas_briefing.add_argument(
        "json_data",
        nargs="?",
        default=None,
        help="Briefing JSON data (or '-' for stdin)",
    )
    p_canvas_briefing.add_argument(
        "--file", default=None, help="Read briefing from JSON file"
    )
    p_canvas_briefing.add_argument("--title", default="", help="Briefing title")
    p_canvas_briefing.add_argument(
        "--summary", default="", help="Executive summary text"
    )
    p_canvas_briefing.add_argument(
        "--agent-id",
        default=os.environ.get("SYNAPSE_AGENT_ID", "cli"),
        help="Agent ID",
    )
    p_canvas_briefing.add_argument(
        "--agent-name", default="", help="Agent display name"
    )
    p_canvas_briefing.add_argument("--card-id", default=None, help="Card ID for upsert")
    p_canvas_briefing.add_argument(
        "--pinned",
        action="store_true",
        default=False,
        help="Pin card (no TTL expiry)",
    )
    p_canvas_briefing.add_argument("--tags", default=None, help="Comma-separated tags")
    p_canvas_briefing.add_argument("--port", type=int, default=None, help="Server port")
    p_canvas_briefing.set_defaults(func=cmd_canvas_briefing)

    # canvas plan [json_data] — Post a plan card
    p_canvas_plan = canvas_subparsers.add_parser(
        "plan", help="Post a plan card (Mermaid DAG + step list with status tracking)"
    )
    p_canvas_plan.add_argument(
        "json_data",
        nargs="?",
        default=None,
        help="Plan JSON data (or '-' for stdin)",
    )
    p_canvas_plan.add_argument("--file", default=None, help="Read plan from JSON file")
    p_canvas_plan.add_argument("--title", default="", help="Plan title")
    p_canvas_plan.add_argument(
        "--agent-id",
        default=os.environ.get("SYNAPSE_AGENT_ID", "cli"),
        help="Agent ID",
    )
    p_canvas_plan.add_argument("--agent-name", default="", help="Agent display name")
    p_canvas_plan.add_argument("--card-id", default=None, help="Card ID for upsert")
    p_canvas_plan.add_argument(
        "--pinned",
        action="store_true",
        default=True,
        help="Pin card (default: true for plans)",
    )
    p_canvas_plan.add_argument("--tags", default=None, help="Comma-separated tags")
    p_canvas_plan.add_argument("--port", type=int, default=None, help="Server port")
    p_canvas_plan.set_defaults(func=cmd_canvas_plan)

    # canvas post-raw <json> — raw JSON (supports composite cards)
    p_canvas_raw = canvas_subparsers.add_parser(
        "post-raw", help="Post raw Canvas message JSON (supports composite cards)"
    )
    p_canvas_raw.add_argument(
        "json_data", help="Raw Canvas message JSON (or '-' for stdin)"
    )
    p_canvas_raw.add_argument("--port", type=int, default=None, help="Server port")
    p_canvas_raw.set_defaults(func=cmd_canvas_post_raw)

    # canvas open
    p_canvas_open = canvas_subparsers.add_parser("open", help="Open Canvas in browser")
    p_canvas_open.add_argument("--port", type=int, default=None, help="Server port")
    p_canvas_open.set_defaults(func=cmd_canvas_open)

    # canvas status
    p_canvas_status = canvas_subparsers.add_parser(
        "status", help="Show Canvas server status"
    )
    p_canvas_status.add_argument("--port", type=int, default=None, help="Server port")
    p_canvas_status.set_defaults(func=cmd_canvas_status)

    # canvas logs
    p_canvas_logs = canvas_subparsers.add_parser("logs", help="Show Canvas server logs")
    p_canvas_logs.add_argument(
        "-n",
        "--lines",
        type=int,
        default=50,
        help="Number of lines to show (default: 50)",
    )
    p_canvas_logs.add_argument(
        "-f", "--follow", action="store_true", default=False, help="Follow log output"
    )
    p_canvas_logs.set_defaults(func=cmd_canvas_logs)

    # canvas stop
    p_canvas_stop = canvas_subparsers.add_parser("stop", help="Stop Canvas server")
    p_canvas_stop.add_argument(
        "--port", "-p", type=int, default=None, help="Canvas server port"
    )
    p_canvas_stop.set_defaults(func=cmd_canvas_stop)

    # canvas link <url> — Post a link-preview card
    p_canvas_link = canvas_subparsers.add_parser(
        "link", help="Post a link-preview card with OGP metadata"
    )
    p_canvas_link.add_argument("url", help="URL to preview")
    p_canvas_link.add_argument("--title", default="", help="Card title (default: URL)")
    p_canvas_link.add_argument(
        "--agent-id",
        default=os.environ.get("SYNAPSE_AGENT_ID", "cli"),
        help="Agent ID",
    )
    p_canvas_link.add_argument("--agent-name", default="", help="Agent name")
    p_canvas_link.add_argument("--card-id", default=None, help="Card ID for updates")
    p_canvas_link.add_argument(
        "--pinned", action="store_true", default=False, help="Pin card"
    )
    p_canvas_link.add_argument("--tags", default=None, help="Comma-separated tags")
    p_canvas_link.add_argument("--port", type=int, default=None, help="Server port")
    p_canvas_link.set_defaults(func=cmd_canvas_link)

    # Pre-extract tool_args from sys.argv for commands that support '--'.
    # argparse.REMAINDER had a bug where it swallowed named options (--name,
    # --role) as positional tool_args.  Instead, we split sys.argv at '--'
    # ourselves and let argparse see only the clean portion.
    #
    # Only extract for commands that actually accept tool_args (start, spawn,
    # team start) so that other commands' '--' remains intact for argparse.
    argv = sys.argv[1:]
    _TOOL_ARGS_COMMANDS = {"start", "spawn", "team", "session"}
    first_positional = next((a for a in argv if not a.startswith("-")), None)
    if first_positional in _TOOL_ARGS_COMMANDS:
        cli_argv, tool_args_extra = _extract_tool_args(argv)
        # Warn if known Synapse flags ended up in tool_args
        _warn_synapse_flags_in_tool_args(tool_args_extra)
    else:
        cli_argv, tool_args_extra = argv, []
    args = parser.parse_args(cli_argv)
    # Attach tool_args so cmd_spawn / cmd_start / cmd_team_start can read them.
    args.tool_args = tool_args_extra

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    # Map of subcommands that require a subcommand action
    subcommand_parsers = {
        "history": ("history_command", p_history),
        "wiki": ("wiki_command", p_wiki),
        "memory": ("memory_command", p_memory),
        "external": ("external_command", p_external),
        "auth": ("auth_command", p_auth),
        "instructions": ("instructions_command", p_instructions),
        "mcp": ("mcp_command", p_mcp),
        "team": ("team_command", p_team),
        "session": ("session_command", p_session),
        "workflow": ("workflow_command", p_workflow),
        "multiagent": ("multiagent_command", p_multiagent),
        "map": ("multiagent_command", p_multiagent),
        "ma": ("multiagent_command", p_multiagent),
        "agents": ("agents_command", p_agents),
        "canvas": ("canvas_command", p_canvas),
        "worktree": ("worktree_command", p_worktree),
    }

    # Handle subcommands without action (print help)
    if args.command in subcommand_parsers:
        attr_name, subparser = subcommand_parsers[args.command]
        if getattr(args, attr_name, None) is None:
            subparser.print_help()
            sys.exit(1)

    # Handle file-safety subcommand without action (show status by default)
    if (
        args.command == "file-safety"
        and getattr(args, "file_safety_command", None) is None
    ):
        cmd_file_safety_status(args)
        return

    args.func(args)


if __name__ == "__main__":
    main()
