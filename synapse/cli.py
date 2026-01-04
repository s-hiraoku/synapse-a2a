#!/usr/bin/env python3
"""Synapse A2A CLI - Main entry point for agent management."""

import argparse
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import yaml

from synapse.a2a_client import get_client
from synapse.auth import generate_api_key
from synapse.controller import TerminalController
from synapse.port_manager import PORT_RANGES, PortManager, is_process_alive
from synapse.registry import AgentRegistry

# Known profiles (for shortcut detection)
KNOWN_PROFILES = set(PORT_RANGES.keys())


def install_skills() -> None:
    """Install Synapse A2A skills to ~/.claude/skills/ if not present."""
    target_dir = Path.home() / ".claude" / "skills" / "synapse-a2a"

    # Skip if already installed
    if target_dir.exists():
        return

    # Find source skills directory (from package installation)
    try:
        import synapse

        package_dir = Path(synapse.__file__).parent
        source_dir = package_dir / "skills" / "synapse-a2a"

        if source_dir.exists():
            target_dir.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source_dir, target_dir)
            print(f"\x1b[32m[Synapse]\x1b[0m Installed A2A skill to {target_dir}")
    except Exception:
        # Silently ignore installation errors
        pass


def cmd_start(args: argparse.Namespace) -> None:
    """Start an agent in background or foreground."""
    profile = args.profile
    port = args.port
    foreground = args.foreground
    ssl_cert = getattr(args, "ssl_cert", None)
    ssl_key = getattr(args, "ssl_key", None)

    # Validate SSL options
    if (ssl_cert and not ssl_key) or (ssl_key and not ssl_cert):
        print("Error: Both --ssl-cert and --ssl-key must be provided together")
        sys.exit(1)

    # Extract tool args (filter out -- if present at start)
    tool_args = getattr(args, "tool_args", [])
    if tool_args and tool_args[0] == "--":
        tool_args = tool_args[1:]

    # Auto-select port if not specified
    if port is None:
        registry = AgentRegistry()
        port_manager = PortManager(registry)
        port = port_manager.get_available_port(profile)

        if port is None:
            print(port_manager.format_exhaustion_error(profile))
            sys.exit(1)

    # Build command
    cmd = [
        sys.executable,
        "-m",
        "synapse.server",
        "--profile",
        profile,
        "--port",
        str(port),
    ]

    # Add SSL options if provided
    if ssl_cert and ssl_key:
        cmd.extend(["--ssl-cert", ssl_cert, "--ssl-key", ssl_key])

    # Set up environment with tool args (null-separated for safe parsing)
    env = os.environ.copy()
    if tool_args:
        env["SYNAPSE_TOOL_ARGS"] = "\x00".join(tool_args)

    protocol = "https" if ssl_cert else "http"

    if foreground:
        # Run in foreground
        print(f"Starting {profile} on port {port} (foreground, {protocol.upper()})...")
        if ssl_cert:
            print(f"SSL: {ssl_cert}")
        if tool_args:
            print(f"Tool args: {' '.join(tool_args)}")
        try:
            subprocess.run(cmd, env=env)
        except KeyboardInterrupt:
            print("\nStopped.")
    else:
        # Run in background
        print(f"Starting {profile} on port {port} (background, {protocol.upper()})...")
        if ssl_cert:
            print(f"SSL: {ssl_cert}")
        if tool_args:
            print(f"Tool args: {' '.join(tool_args)}")

        # Create log directory
        log_dir = os.path.expanduser("~/.synapse/logs")
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, f"{profile}.log")

        with open(log_file, "w") as log:
            process = subprocess.Popen(
                cmd, stdout=log, stderr=log, start_new_session=True, env=env
            )

        # Wait a bit and check if it started
        time.sleep(2)
        if process.poll() is None:
            print(f"Started {profile} (PID: {process.pid})")
            print(f"Logs: {log_file}")
        else:
            print(f"Failed to start {profile}. Check logs: {log_file}")
            sys.exit(1)


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


def _render_agent_table(registry: AgentRegistry) -> str:
    """
    Render the agent table output.

    Args:
        registry: AgentRegistry instance

    Returns:
        str: Formatted table output
    """
    agents = registry.list_agents()

    if not agents:
        output = ["No agents running.", ""]
        output.append("Port ranges:")
        for agent_type, (start, end) in sorted(PORT_RANGES.items()):
            output.append(f"  {agent_type}: {start}-{end}")
        return "\n".join(output)

    lines = []
    header = (
        f"{'TYPE':<10} {'PORT':<8} {'STATUS':<12} {'PID':<8} "
        f"{'WORKING_DIR':<50} ENDPOINT"
    )
    lines.append(header)
    lines.append("-" * len(header))

    live_agents = False
    for agent_id, info in agents.items():
        # Verify process is still alive
        pid = info.get("pid")
        status = info.get("status", "-")
        if pid and not is_process_alive(pid):
            # Clean up stale entry
            registry.unregister(agent_id)
            continue  # Skip showing dead entries

        live_agents = True
        lines.append(
            f"{info.get('agent_type', 'unknown'):<10} "
            f"{info.get('port', '-'):<8} "
            f"{status:<12} "
            f"{pid or '-':<8} "
            f"{info.get('working_dir', '-'):<50} "
            f"{info.get('endpoint', '-')}"
        )

    # If all agents were dead, show empty registry message
    if not live_agents:
        output = ["No agents running.", ""]
        output.append("Port ranges:")
        for agent_type, (start, end) in sorted(PORT_RANGES.items()):
            output.append(f"  {agent_type}: {start}-{end}")
        return "\n".join(output)

    return "\n".join(lines)


def cmd_list(args: argparse.Namespace) -> None:
    """List running agents (with optional watch mode)."""
    registry = AgentRegistry()
    watch_mode = getattr(args, "watch", False)
    interval = getattr(args, "interval", 2.0)

    if not watch_mode:
        # Normal mode: single output
        print(_render_agent_table(registry))
        return

    # Watch mode: continuous refresh
    print("Watch mode: Press Ctrl+C to exit\n")

    try:
        while True:
            _clear_screen()
            print(f"Synapse Agent List (refreshing every {interval}s)")
            print(f"Last updated: {time.strftime('%Y-%m-%d %H:%M:%S')}")
            print()
            print(_render_agent_table(registry))
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n\nExiting watch mode...")
        sys.exit(0)


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


def cmd_history_list(args: argparse.Namespace) -> None:
    """List task history."""
    from synapse.history import HistoryManager

    db_path = str(Path.home() / ".synapse" / "history" / "history.db")
    manager = HistoryManager.from_env(db_path=db_path)

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

    from synapse.history import HistoryManager

    db_path = str(Path.home() / ".synapse" / "history" / "history.db")
    manager = HistoryManager.from_env(db_path=db_path)

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
    from synapse.history import HistoryManager

    db_path = str(Path.home() / ".synapse" / "history" / "history.db")
    manager = HistoryManager.from_env(db_path=db_path)

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

    from synapse.history import HistoryManager

    db_path = str(Path.home() / ".synapse" / "history" / "history.db")
    manager = HistoryManager.from_env(db_path=db_path)

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
    from synapse.history import HistoryManager

    db_path = str(Path.home() / ".synapse" / "history" / "history.db")
    manager = HistoryManager.from_env(db_path=db_path)

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
    from synapse.history import HistoryManager

    db_path = str(Path.home() / ".synapse" / "history" / "history.db")
    manager = HistoryManager.from_env(db_path=db_path)

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

    # Create registry and register this agent
    registry = AgentRegistry()
    agent_id = registry.get_agent_id(profile, port)

    # Set SYNAPSE env vars for sender identification (same as server.py)
    env["SYNAPSE_AGENT_ID"] = agent_id
    env["SYNAPSE_AGENT_TYPE"] = profile
    env["SYNAPSE_PORT"] = str(port)

    # Create controller - initial instructions sent on IDLE
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

    args.func(args)


if __name__ == "__main__":
    main()
