#!/usr/bin/env python3
"""Synapse A2A CLI - Main entry point for agent management."""

import argparse
import os
import sys
import signal
import asyncio
import subprocess
import time
import yaml
from synapse.registry import AgentRegistry
from synapse.controller import TerminalController
from synapse.a2a_client import get_client
from synapse.port_manager import PortManager, PORT_RANGES, is_process_alive

# Known profiles (for shortcut detection)
KNOWN_PROFILES = set(PORT_RANGES.keys())


def cmd_start(args):
    """Start an agent in background or foreground."""
    profile = args.profile
    port = args.port
    foreground = args.foreground

    # Extract tool args (filter out -- if present at start)
    tool_args = getattr(args, 'tool_args', [])
    if tool_args and tool_args[0] == '--':
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
        sys.executable, "-m", "synapse.server",
        "--profile", profile,
        "--port", str(port)
    ]

    # Set up environment with tool args (null-separated for safe parsing)
    env = os.environ.copy()
    if tool_args:
        env["SYNAPSE_TOOL_ARGS"] = '\x00'.join(tool_args)

    if foreground:
        # Run in foreground
        print(f"Starting {profile} on port {port} (foreground)...")
        if tool_args:
            print(f"Tool args: {' '.join(tool_args)}")
        try:
            subprocess.run(cmd, env=env)
        except KeyboardInterrupt:
            print("\nStopped.")
    else:
        # Run in background
        print(f"Starting {profile} on port {port} (background)...")
        if tool_args:
            print(f"Tool args: {' '.join(tool_args)}")

        # Create log directory
        log_dir = os.path.expanduser("~/.synapse/logs")
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, f"{profile}.log")

        with open(log_file, "w") as log:
            process = subprocess.Popen(
                cmd,
                stdout=log,
                stderr=log,
                start_new_session=True,
                env=env
            )

        # Wait a bit and check if it started
        time.sleep(2)
        if process.poll() is None:
            print(f"Started {profile} (PID: {process.pid})")
            print(f"Logs: {log_file}")
        else:
            print(f"Failed to start {profile}. Check logs: {log_file}")
            sys.exit(1)


def _stop_agent(registry, info):
    """Stop a single agent given its info dict."""
    agent_id = info.get("agent_id")
    pid = info.get("pid")

    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
            print(f"Stopped {agent_id} (PID: {pid})")
            registry.unregister(agent_id)
        except ProcessLookupError:
            print(f"Process {pid} not found. Cleaning up registry...")
            registry.unregister(agent_id)
    else:
        print(f"No PID found for {agent_id}")


def cmd_stop(args):
    """Stop a running agent."""
    profile = args.profile
    registry = AgentRegistry()
    port_manager = PortManager(registry)

    running = port_manager.get_running_instances(profile)

    if not running:
        print(f"No running agent found for profile: {profile}")
        sys.exit(1)

    # If --all flag is set, stop all instances
    if getattr(args, 'all', False):
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


def cmd_list(args):
    """List running agents."""
    registry = AgentRegistry()
    agents = registry.list_agents()

    if not agents:
        print("No agents running.")
        print("\nPort ranges:")
        for agent_type, (start, end) in sorted(PORT_RANGES.items()):
            print(f"  {agent_type}: {start}-{end}")
        return

    print(f"{'TYPE':<10} {'PORT':<8} {'STATUS':<10} {'PID':<8} {'ENDPOINT'}")
    print("-" * 60)
    for agent_id, info in agents.items():
        # Verify process is still alive
        pid = info.get('pid')
        status = info.get('status', '-')
        if pid and not is_process_alive(pid):
            status = "DEAD"
            # Clean up stale entry
            registry.unregister(agent_id)
            continue  # Skip showing dead entries

        print(f"{info.get('agent_type', 'unknown'):<10} "
              f"{info.get('port', '-'):<8} "
              f"{status:<10} "
              f"{pid or '-':<8} "
              f"{info.get('endpoint', '-')}")


def cmd_logs(args):
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


def cmd_send(args):
    """Send a message to an agent."""
    target = args.target
    message = args.message
    priority = args.priority
    wait_response = args.wait

    # Use the existing a2a tool
    cmd = [
        sys.executable, "synapse/tools/a2a.py",
        "send",
        "--target", target,
        "--priority", str(priority),
        message
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

def cmd_external_add(args):
    """Add an external A2A agent."""
    client = get_client()
    agent = client.discover(args.url, alias=args.alias)

    if agent:
        print(f"Added external agent: {agent.name}")
        print(f"  Alias: {agent.alias}")
        print(f"  URL: {agent.url}")
        print(f"  Description: {agent.description}")
        if agent.skills:
            print(f"  Skills: {', '.join(s.get('name', s.get('id', '')) for s in agent.skills)}")
    else:
        print(f"Failed to add agent from {args.url}")
        sys.exit(1)


def cmd_external_list(args):
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


def cmd_external_remove(args):
    """Remove an external A2A agent."""
    client = get_client()

    if client.remove_agent(args.alias):
        print(f"Removed external agent: {args.alias}")
    else:
        print(f"Agent '{args.alias}' not found")
        sys.exit(1)


def cmd_external_send(args):
    """Send a message to an external A2A agent."""
    client = get_client()

    task = client.send_message(
        args.alias,
        args.message,
        wait_for_completion=args.wait
    )

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


def cmd_external_info(args):
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
            if skill.get('description'):
                print(f"    {skill['description']}")


def cmd_run_interactive(profile: str, port: int, tool_args: list = None):
    """Run an agent in interactive mode with input routing."""
    tool_args = tool_args or []

    # Load profile
    profile_path = os.path.join(
        os.path.dirname(__file__), 'profiles', f"{profile}.yaml"
    )
    if not os.path.exists(profile_path):
        print(f"Profile '{profile}' not found")
        sys.exit(1)

    with open(profile_path, 'r') as f:
        config = yaml.safe_load(f)

    # Load submit sequence from profile (decode escape sequences)
    submit_seq = config.get('submit_sequence', '\n').encode().decode('unicode_escape')
    startup_delay = config.get('startup_delay', 3)

    # Merge profile args with CLI tool args
    profile_args = config.get('args', [])
    all_args = profile_args + tool_args

    # Merge environment
    env = os.environ.copy()
    if 'env' in config:
        env.update(config['env'])

    # Create registry and register this agent
    registry = AgentRegistry()
    agent_id = registry.get_agent_id(profile, port)

    # Set SYNAPSE env vars for sender identification (same as server.py)
    env["SYNAPSE_AGENT_ID"] = agent_id
    env["SYNAPSE_AGENT_TYPE"] = profile
    env["SYNAPSE_PORT"] = str(port)

    # Create controller
    controller = TerminalController(
        command=config['command'],
        args=all_args,
        idle_regex=config['idle_regex'],
        env=env,
        registry=registry,
        agent_id=agent_id,
        agent_type=profile,
        submit_seq=submit_seq,
        startup_delay=startup_delay,
        port=port,
    )

    # Register agent
    registry.register(agent_id, profile, port, status="BUSY")

    # Handle Ctrl+C gracefully
    def cleanup(signum, frame):
        print("\n\x1b[32m[Synapse]\x1b[0m Shutting down...")
        registry.unregister(agent_id)
        controller.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    print(f"\x1b[32m[Synapse]\x1b[0m Starting {profile} on port {port}")
    print(f"\x1b[32m[Synapse]\x1b[0m Submit sequence: {repr(submit_seq)}")
    print(f"\x1b[32m[Synapse]\x1b[0m Use @Agent to send messages to other agents")
    print(f"\x1b[32m[Synapse]\x1b[0m Use @Agent --response 'message' to get response here")
    print(f"\x1b[32m[Synapse]\x1b[0m Press Ctrl+C twice to exit")
    print()
    print(f"\x1b[32m[Synapse]\x1b[0m Google A2A endpoints:")
    print(f"\x1b[32m[Synapse]\x1b[0m   Agent Card: http://localhost:{port}/.well-known/agent.json")
    print(f"\x1b[32m[Synapse]\x1b[0m   Tasks API:  http://localhost:{port}/tasks/send")
    print()

    try:
        # Start the API server in background
        import threading
        from synapse.server import create_app
        import uvicorn

        app = create_app(controller, registry, agent_id, port, submit_seq, agent_type=profile, registry=registry)

        def run_server():
            uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")

        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()

        # Give server time to start
        time.sleep(1)

        # Send minimal initial A2A instructions
        from synapse.server import send_initial_instructions

        def send_initial():
            try:
                asyncio.run(send_initial_instructions(
                    controller,
                    agent_id,
                    port,
                    submit_seq
                ))
            except Exception:
                pass  # Best-effort

        threading.Thread(target=send_initial, daemon=True).start()

        # Run interactive mode
        controller.run_interactive()

    except KeyboardInterrupt:
        pass
    finally:
        print("\n\x1b[32m[Synapse]\x1b[0m Shutting down...")
        registry.unregister(agent_id)
        controller.stop()


def main():
    # Check for shortcut: synapse claude [--port PORT] [-- TOOL_ARGS...]
    if len(sys.argv) >= 2 and sys.argv[1] in KNOWN_PROFILES:
        profile = sys.argv[1]

        # Find -- separator to split synapse args from tool args
        try:
            separator_idx = sys.argv.index('--')
            synapse_args = sys.argv[2:separator_idx]
            tool_args = sys.argv[separator_idx + 1:]
        except ValueError:
            synapse_args = sys.argv[2:]
            tool_args = []

        # Parse --port from synapse_args
        port = None
        if '--port' in synapse_args:
            idx = synapse_args.index('--port')
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

        cmd_run_interactive(profile, port, tool_args)
        return

    parser = argparse.ArgumentParser(
        description="Synapse A2A - Agent-to-Agent Communication",
        prog="synapse",
        epilog="Shortcuts: synapse claude, synapse gemini --port 8102"
    )
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # start (background)
    p_start = subparsers.add_parser("start", help="Start an agent in background")
    p_start.add_argument("profile", help="Agent profile (claude, codex, gemini, dummy)")
    p_start.add_argument("--port", type=int, help="Server port (default: auto)")
    p_start.add_argument("--foreground", "-f", action="store_true", help="Run in foreground")
    p_start.add_argument("tool_args", nargs=argparse.REMAINDER,
                         help="Arguments after -- are passed to the CLI tool")
    p_start.set_defaults(func=cmd_start)

    # stop
    p_stop = subparsers.add_parser("stop", help="Stop an agent")
    p_stop.add_argument("profile", help="Agent profile to stop")
    p_stop.add_argument("--all", "-a", action="store_true",
                        help="Stop all instances of this profile")
    p_stop.set_defaults(func=cmd_stop)

    # list
    p_list = subparsers.add_parser("list", help="List running agents")
    p_list.set_defaults(func=cmd_list)

    # logs
    p_logs = subparsers.add_parser("logs", help="Show agent logs")
    p_logs.add_argument("profile", help="Agent profile")
    p_logs.add_argument("-f", "--follow", action="store_true", help="Follow log output")
    p_logs.add_argument("-n", "--lines", type=int, default=50, help="Number of lines to show")
    p_logs.set_defaults(func=cmd_logs)

    # send
    p_send = subparsers.add_parser("send", help="Send a message to an agent")
    p_send.add_argument("target", help="Target agent (claude, codex, gemini)")
    p_send.add_argument("message", help="Message to send")
    p_send.add_argument("--priority", "-p", type=int, default=1, help="Priority (1-5)")
    p_send.add_argument("--return", "-r", dest="wait", action="store_true", help="Wait for response")
    p_send.set_defaults(func=cmd_send)

    # external - External A2A agent management
    p_external = subparsers.add_parser("external", help="Manage external A2A agents")
    external_subparsers = p_external.add_subparsers(dest="external_command", help="External agent commands")

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
    p_ext_send = external_subparsers.add_parser("send", help="Send message to external agent")
    p_ext_send.add_argument("alias", help="Agent alias")
    p_ext_send.add_argument("message", help="Message to send")
    p_ext_send.add_argument("--wait", "-w", action="store_true", help="Wait for completion")
    p_ext_send.set_defaults(func=cmd_external_send)

    # external info
    p_ext_info = external_subparsers.add_parser("info", help="Show agent details")
    p_ext_info.add_argument("alias", help="Agent alias")
    p_ext_info.set_defaults(func=cmd_external_info)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    # Handle external subcommand without action
    if args.command == "external" and (not hasattr(args, 'external_command') or args.external_command is None):
        p_external.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
