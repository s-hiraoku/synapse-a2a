import argparse
import sys
import json
import os
import subprocess
import requests
from synapse.registry import AgentRegistry, is_port_open, is_process_running


def get_parent_pid(pid: int) -> int:
    """Get parent PID of a process (cross-platform)."""
    try:
        # Try /proc first (Linux)
        with open(f"/proc/{pid}/stat", "r") as f:
            stat = f.read().split()
            return int(stat[3])
    except (FileNotFoundError, PermissionError, IndexError):
        pass

    # Fallback: use ps command (macOS/BSD)
    try:
        result = subprocess.run(
            ["ps", "-o", "ppid=", "-p", str(pid)],
            capture_output=True,
            text=True,
            timeout=2
        )
        if result.returncode == 0:
            return int(result.stdout.strip())
    except (subprocess.TimeoutExpired, ValueError, FileNotFoundError):
        pass

    return 0


def is_descendant_of(child_pid: int, ancestor_pid: int, max_depth: int = 15) -> bool:
    """Check if child_pid is a descendant of ancestor_pid."""
    current = child_pid
    for _ in range(max_depth):
        if current == ancestor_pid:
            return True
        if current <= 1:
            return False
        parent = get_parent_pid(current)
        if parent == 0 or parent == current:
            return False
        current = parent
    return False


def build_sender_info(explicit_sender: str = None) -> dict:
    """
    Build sender info using Registry PID matching.

    Identifies the sender by checking which registered agent's PID
    is an ancestor of the current process.

    Returns dict with sender_id, sender_type, sender_endpoint if available.
    """
    sender_info = {}

    # Explicit --from flag takes priority
    if explicit_sender:
        return {"sender_id": explicit_sender}

    # Primary method: Registry PID matching
    # Find which agent's process is an ancestor of current process
    try:
        reg = AgentRegistry()
        agents = reg.list_agents()
        current_pid = os.getpid()

        for agent_id, info in agents.items():
            agent_pid = info.get("pid")
            if agent_pid and is_descendant_of(current_pid, agent_pid):
                sender_info["sender_id"] = agent_id
                sender_info["sender_type"] = info.get("agent_type")
                sender_info["sender_endpoint"] = info.get("endpoint")
                return sender_info
    except Exception:
        pass

    return sender_info

def cmd_list(args):
    """List all available agents."""
    reg = AgentRegistry()
    if args.live:
        agents = reg.get_live_agents()
    else:
        agents = reg.list_agents()
    print(json.dumps(agents, indent=2))


def cmd_cleanup(args):
    """Remove stale registry entries for dead agents."""
    reg = AgentRegistry()
    removed = reg.cleanup_stale_entries()
    if removed:
        print(f"Removed {len(removed)} stale registry entries:")
        for agent_id in removed:
            print(f"  - {agent_id}")
    else:
        print("No stale entries found.")

def cmd_send(args):
    """Send a message to a target agent using Google A2A protocol."""
    reg = AgentRegistry()
    agents = reg.list_agents()

    # 1. Resolve Target
    target_agent = None

    # Check if exact match by ID
    if args.target in agents:
        target_agent = agents[args.target]
    else:
        # Fuzzy match by agent_type (e.g. 'claude')
        matches = [a for a in agents.values() if args.target.lower() in a['agent_type'].lower()]
        if len(matches) == 1:
            target_agent = matches[0]
        elif len(matches) > 1:
            print(f"Error: Ambiguous target '{args.target}'. Multiple agents found: {[m['agent_id'] for m in matches]}", file=sys.stderr)
            sys.exit(1)
        else:
             print(f"Error: No agent found matching '{args.target}'", file=sys.stderr)
             sys.exit(1)

    # 2. Validate agent is actually running
    pid = target_agent.get('pid')
    port = target_agent.get('port')
    agent_id = target_agent['agent_id']

    # Check if process is still alive
    if pid and not is_process_running(pid):
        print(f"Error: Agent '{agent_id}' process (PID {pid}) is no longer running.", file=sys.stderr)
        print(f"  Hint: Remove stale registry with: rm ~/.a2a/registry/{agent_id}.json", file=sys.stderr)
        reg.unregister(agent_id)  # Auto-cleanup
        print(f"  (Registry entry has been automatically removed)", file=sys.stderr)
        sys.exit(1)

    # Check if port is reachable (fast 1-second check)
    if port and not is_port_open("localhost", port, timeout=1.0):
        print(f"Error: Agent '{agent_id}' server on port {port} is not responding.", file=sys.stderr)
        print(f"  The process may be running but the A2A server is not started.", file=sys.stderr)
        print(f"  Hint: Start the server with: synapse start {target_agent['agent_type']} --port {port}", file=sys.stderr)
        sys.exit(1)

    # 3. Build sender metadata
    sender_info = build_sender_info(getattr(args, 'sender', None))

    # 4. Send Request using Google A2A protocol
    url = f"{target_agent['endpoint']}/tasks/send-priority?priority={args.priority}"
    payload = {
        "message": {
            "role": "user",
            "parts": [{"type": "text", "text": args.message}]
        }
    }

    # Add sender info to metadata if available
    if sender_info:
        payload["metadata"] = {"sender": sender_info}

    try:
        # Use tuple timeout: (connect_timeout, read_timeout)
        resp = requests.post(url, json=payload, timeout=(3, 30))
        resp.raise_for_status()
        result = resp.json()
        task = result.get("task", result)
        print(f"Success: Task created for {target_agent['agent_type']} ({target_agent['agent_id'][:8]}...)")
        print(f"  Task ID: {task.get('id', 'N/A')}")
        print(f"  Status: {task.get('status', 'N/A')}")

    except requests.RequestException as e:
        print(f"Error sending message: {e}", file=sys.stderr)
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Synapse A2A Client Tool")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # list command
    p_list = subparsers.add_parser("list", help="List active agents")
    p_list.add_argument("--live", action="store_true", help="Only show live agents (auto-cleanup stale)")

    # cleanup command
    subparsers.add_parser("cleanup", help="Remove stale registry entries")

    # send command
    p_send = subparsers.add_parser("send", help="Send message to an agent")
    p_send.add_argument("--target", required=True, help="Target Agent ID or Type (e.g. 'claude')")
    p_send.add_argument("--priority", type=int, default=1, help="Priority (1-5, 5=Interrupt)")
    p_send.add_argument("--from", dest="sender", help="Sender Agent ID (auto-detected from env if not specified)")
    p_send.add_argument("message", help="Content of the message")

    args = parser.parse_args()

    if args.command == "list":
        cmd_list(args)
    elif args.command == "cleanup":
        cmd_cleanup(args)
    elif args.command == "send":
        cmd_send(args)

if __name__ == "__main__":
    main()
