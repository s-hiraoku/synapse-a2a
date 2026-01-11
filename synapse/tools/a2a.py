import argparse
import json
import logging
import os
import subprocess
import sys
import uuid
from pathlib import Path

import requests

from synapse.history import HistoryManager
from synapse.registry import AgentRegistry, is_port_open, is_process_running

logger = logging.getLogger(__name__)


def _get_history_manager() -> HistoryManager:
    """Get history manager instance from environment."""
    db_path = str(Path.home() / ".synapse" / "history.db")
    return HistoryManager.from_env(db_path)


def get_parent_pid(pid: int) -> int:
    """Get parent PID of a process (cross-platform)."""
    try:
        # Try /proc first (Linux)
        with open(f"/proc/{pid}/stat") as f:
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
            timeout=2,
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


def build_sender_info(explicit_sender: str | None = None) -> dict:
    """
    Build sender info using Registry PID matching.

    Identifies the sender by checking which registered agent's PID
    is an ancestor of the current process.

    Returns dict with sender_id, sender_type, sender_endpoint if available.
    """
    sender_info: dict[str, str] = {}

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
                agent_type = info.get("agent_type")
                if agent_type:
                    sender_info["sender_type"] = agent_type
                endpoint = info.get("endpoint")
                if endpoint:
                    sender_info["sender_endpoint"] = endpoint
                return sender_info
    except Exception:
        pass

    return sender_info


def cmd_list(args: argparse.Namespace) -> None:
    """List all available agents."""
    reg = AgentRegistry()
    agents = reg.get_live_agents() if args.live else reg.list_agents()
    print(json.dumps(agents, indent=2))


def cmd_cleanup(args: argparse.Namespace) -> None:
    """Remove stale registry entries for dead agents."""
    reg = AgentRegistry()
    removed = reg.cleanup_stale_entries()
    if removed:
        print(f"Removed {len(removed)} stale registry entries:")
        for agent_id in removed:
            print(f"  - {agent_id}")
    else:
        print("No stale entries found.")


def _record_sent_message(
    task_id: str,
    target_agent: dict[str, object],
    message: str,
    priority: int,
    sender_info: dict[str, str] | None,
) -> None:
    """Record sent message to history database.

    Args:
        task_id: The task ID returned from the target agent
        target_agent: Target agent information dict
        message: The message that was sent
        priority: Priority level (1-5)
        sender_info: Sender information dict (optional)
    """
    try:
        history = _get_history_manager()
        if not history.enabled:
            return

        # Determine sender agent name
        sender_name = "user"
        if sender_info:
            # Prefer explicit sender_type if available
            sender_name = sender_info.get("sender_type") or sender_name
            # Fallback: extract from sender_id (e.g., "synapse-claude-8100" -> "claude")
            if sender_name == "user":
                sender_id = sender_info.get("sender_id", "")
                parts = sender_id.split("-") if sender_id else []
                if len(parts) >= 3 and parts[0] == "synapse":
                    sender_name = parts[1]

        # Build metadata
        metadata = {
            "direction": "sent",
            "target_agent_id": target_agent.get("agent_id"),
            "target_agent_type": target_agent.get("agent_type"),
            "priority": priority,
        }
        if sender_info:
            metadata["sender"] = sender_info

        # Save to history
        # Use task_id as-is; direction is already recorded in metadata
        history.save_observation(
            task_id=task_id,
            agent_name=sender_name,
            session_id="a2a-send",
            input_text=f"@{target_agent.get('agent_type')} {message}",
            output_text=f"Task sent to {target_agent.get('agent_id')}",
            status="sent",
            metadata=metadata,
        )
    except Exception:
        # Non-critical error - log at debug level for troubleshooting
        logger.debug("Failed to record sent message to history", exc_info=True)


def cmd_send(args: argparse.Namespace) -> None:
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
        matches = [
            a for a in agents.values() if args.target.lower() in a["agent_type"].lower()
        ]
        if len(matches) == 1:
            target_agent = matches[0]
        elif len(matches) > 1:
            print(
                f"Error: Ambiguous target '{args.target}'. Multiple agents found: {[m['agent_id'] for m in matches]}",
                file=sys.stderr,
            )
            sys.exit(1)
        else:
            print(f"Error: No agent found matching '{args.target}'", file=sys.stderr)
            sys.exit(1)

    # 2. Validate agent is actually running
    pid = target_agent.get("pid")
    port = target_agent.get("port")
    agent_id = target_agent["agent_id"]

    # Check if process is still alive
    if pid and not is_process_running(pid):
        print(
            f"Error: Agent '{agent_id}' process (PID {pid}) is no longer running.",
            file=sys.stderr,
        )
        print(
            f"  Hint: Remove stale registry with: rm ~/.a2a/registry/{agent_id}.json",
            file=sys.stderr,
        )
        reg.unregister(agent_id)  # Auto-cleanup
        print("  (Registry entry has been automatically removed)", file=sys.stderr)
        sys.exit(1)

    # Check if port is reachable (fast 1-second check)
    if port and not is_port_open("localhost", port, timeout=1.0):
        print(
            f"Error: Agent '{agent_id}' server on port {port} is not responding.",
            file=sys.stderr,
        )
        print(
            "  The process may be running but the A2A server is not started.",
            file=sys.stderr,
        )
        print(
            f"  Hint: Start the server with: synapse start {target_agent['agent_type']} --port {port}",
            file=sys.stderr,
        )
        sys.exit(1)

    # 3. Build sender metadata
    sender_info = build_sender_info(getattr(args, "sender", None))

    # 4. Send Request using Google A2A protocol
    url = f"{target_agent['endpoint']}/tasks/send-priority?priority={args.priority}"
    payload: dict[str, object] = {
        "message": {"role": "user", "parts": [{"type": "text", "text": args.message}]}
    }

    # Add metadata (sender info and response_required)
    metadata: dict[str, object] = {}
    if sender_info:
        metadata["sender"] = sender_info
    # Default: response_required is True, --non-response sets it to False
    metadata["response_required"] = not getattr(args, "non_response", False)
    payload["metadata"] = metadata

    try:
        # Use tuple timeout: (connect_timeout, read_timeout)
        resp = requests.post(url, json=payload, timeout=(3, 30))
        resp.raise_for_status()
        result = resp.json()
        task = result.get("task", result)
        task_id = task.get("id", str(uuid.uuid4()))
        print(
            f"Success: Task created for {target_agent['agent_type']} ({target_agent['agent_id'][:8]}...)"
        )
        print(f"  Task ID: {task_id}")
        print(f"  Status: {task.get('status', 'N/A')}")

        # Record sent message to history
        _record_sent_message(
            task_id=task_id,
            target_agent=target_agent,
            message=args.message,
            priority=args.priority,
            sender_info=sender_info,
        )

    except requests.RequestException as e:
        print(f"Error sending message: {e}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    """Parse command-line arguments and execute A2A client operations."""
    parser = argparse.ArgumentParser(description="Synapse A2A Client Tool")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # list command
    p_list = subparsers.add_parser("list", help="List active agents")
    p_list.add_argument(
        "--live", action="store_true", help="Only show live agents (auto-cleanup stale)"
    )

    # cleanup command
    subparsers.add_parser("cleanup", help="Remove stale registry entries")

    # send command
    p_send = subparsers.add_parser("send", help="Send message to an agent")
    p_send.add_argument(
        "--target", required=True, help="Target Agent ID or Type (e.g. 'claude')"
    )
    p_send.add_argument(
        "--priority", type=int, default=1, help="Priority (1-5, 5=Interrupt)"
    )
    p_send.add_argument(
        "--from",
        dest="sender",
        help="Sender Agent ID (auto-detected from env if not specified)",
    )
    p_send.add_argument(
        "--non-response",
        dest="non_response",
        action="store_true",
        help="Do not require response from receiver (default: response required)",
    )
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
