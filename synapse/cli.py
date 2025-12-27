#!/usr/bin/env python3
"""Synapse A2A CLI - Main entry point for agent management."""

import argparse
import os
import sys
import signal
import subprocess
import time
from synapse.registry import AgentRegistry


def cmd_start(args):
    """Start an agent in background or foreground."""
    profile = args.profile
    port = args.port
    foreground = args.foreground

    # Build command
    cmd = [
        sys.executable, "-m", "synapse.server",
        "--profile", profile,
        "--port", str(port)
    ]

    if foreground:
        # Run in foreground
        print(f"Starting {profile} on port {port} (foreground)...")
        try:
            subprocess.run(cmd)
        except KeyboardInterrupt:
            print("\nStopped.")
    else:
        # Run in background
        print(f"Starting {profile} on port {port} (background)...")

        # Create log directory
        log_dir = os.path.expanduser("~/.synapse/logs")
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, f"{profile}.log")

        with open(log_file, "w") as log:
            process = subprocess.Popen(
                cmd,
                stdout=log,
                stderr=log,
                start_new_session=True
            )

        # Wait a bit and check if it started
        time.sleep(2)
        if process.poll() is None:
            print(f"Started {profile} (PID: {process.pid})")
            print(f"Logs: {log_file}")
        else:
            print(f"Failed to start {profile}. Check logs: {log_file}")
            sys.exit(1)


def cmd_stop(args):
    """Stop a running agent."""
    profile = args.profile
    registry = AgentRegistry()
    agents = registry.list_agents()

    # Find agent by profile/type
    found = None
    for agent_id, info in agents.items():
        if info.get("agent_type") == profile:
            found = (agent_id, info)
            break

    if not found:
        print(f"No running agent found for profile: {profile}")
        sys.exit(1)

    agent_id, info = found
    pid = info.get("pid")

    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
            print(f"Stopped {profile} (PID: {pid})")
            registry.unregister(agent_id)
        except ProcessLookupError:
            print(f"Process {pid} not found. Cleaning up registry...")
            registry.unregister(agent_id)
    else:
        print(f"No PID found for {profile}")


def cmd_list(args):
    """List running agents."""
    registry = AgentRegistry()
    agents = registry.list_agents()

    if not agents:
        print("No agents running.")
        return

    print(f"{'TYPE':<10} {'PORT':<8} {'STATUS':<10} {'PID':<8} {'ENDPOINT'}")
    print("-" * 60)
    for agent_id, info in agents.items():
        print(f"{info.get('agent_type', 'unknown'):<10} "
              f"{info.get('port', '-'):<8} "
              f"{info.get('status', '-'):<10} "
              f"{info.get('pid', '-'):<8} "
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


def main():
    parser = argparse.ArgumentParser(
        description="Synapse A2A - Agent-to-Agent Communication",
        prog="synapse"
    )
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # start
    p_start = subparsers.add_parser("start", help="Start an agent")
    p_start.add_argument("profile", help="Agent profile (claude, codex, gemini, dummy)")
    p_start.add_argument("--port", type=int, default=8100, help="Server port")
    p_start.add_argument("--foreground", "-f", action="store_true", help="Run in foreground")
    p_start.set_defaults(func=cmd_start)

    # stop
    p_stop = subparsers.add_parser("stop", help="Stop an agent")
    p_stop.add_argument("profile", help="Agent profile to stop")
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

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
