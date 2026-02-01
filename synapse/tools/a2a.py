import argparse
import contextlib
import json
import logging
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path

import requests

from synapse.a2a_client import A2AClient
from synapse.history import HistoryManager
from synapse.registry import (
    AgentRegistry,
    get_valid_uds_path,
    is_port_open,
    is_process_running,
)
from synapse.settings import get_settings

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


def _extract_sender_info_from_agent(agent_id: str, info: dict) -> dict[str, str]:
    """Extract sender info fields from agent registry entry.

    Args:
        agent_id: The agent's unique identifier
        info: Agent info dict from registry

    Returns:
        Dict with sender_id and optional sender_type, sender_endpoint, sender_uds_path
    """
    sender_info: dict[str, str] = {"sender_id": agent_id}
    if info.get("agent_type"):
        sender_info["sender_type"] = info["agent_type"]
    if info.get("endpoint"):
        sender_info["sender_endpoint"] = info["endpoint"]
    if info.get("uds_path"):
        sender_info["sender_uds_path"] = info["uds_path"]
    return sender_info


def build_sender_info(explicit_sender: str | None = None) -> dict:
    """
    Build sender info using Registry PID matching.

    Identifies the sender by checking which registered agent's PID
    is an ancestor of the current process.

    Returns dict with sender_id, sender_type, sender_endpoint, sender_uds_path.
    """
    # Explicit --from flag takes priority
    if explicit_sender:
        # Even with explicit sender, look up endpoint and uds_path from registry
        try:
            reg = AgentRegistry()
            agents = reg.list_agents()
            # Try exact match first
            if explicit_sender in agents:
                return _extract_sender_info_from_agent(
                    explicit_sender, agents[explicit_sender]
                )
            # Try fuzzy match by agent_type
            for agent_id, info in agents.items():
                agent_type = info.get("agent_type", "").lower()
                if (
                    explicit_sender.lower() in agent_id.lower()
                    or explicit_sender.lower() == agent_type
                ):
                    return _extract_sender_info_from_agent(agent_id, info)
        except Exception:
            pass
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
                return _extract_sender_info_from_agent(agent_id, info)
    except Exception:
        pass

    return {}


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


def _resolve_target_agent(
    target: str, agents: dict[str, dict]
) -> tuple[dict | None, str | None]:
    """Resolve target agent from name/id.

    Matching priority:
    1. Custom name (exact match, case-sensitive)
    2. Exact match on agent_id (e.g., synapse-claude-8100)
    3. Match on type-port shorthand (e.g., claude-8100)
    4. Match on agent_type if only one exists (e.g., claude)

    Returns:
        Tuple of (agent_info, error_message). If successful, error_message is None.
    """
    target_lower = target.lower()

    # Priority 1: Custom name (exact match, case-sensitive)
    for info in agents.values():
        if info.get("name") == target:
            return info, None

    # Priority 2: Exact match by ID
    if target in agents:
        return agents[target], None

    # Priority 3: Type-port shorthand (e.g., claude-8100, gpt-4-8120)
    type_port_match = re.match(r"^([\w-]+)-(\d+)$", target_lower)
    if type_port_match:
        target_type = type_port_match.group(1)
        target_port = int(type_port_match.group(2))
        for info in agents.values():
            if (
                info.get("agent_type", "").lower() == target_type
                and info.get("port") == target_port
            ):
                return info, None

    # Priority 4: Fuzzy match by agent_type
    matches = [
        a for a in agents.values() if target_lower in a.get("agent_type", "").lower()
    ]

    if len(matches) == 1:
        return matches[0], None

    if len(matches) > 1:
        agent_ids = [m.get("agent_id", "unknown") for m in matches]
        # Include custom names in hint
        options = []
        for m in matches:
            name = m.get("name")
            if name:
                options.append(name)
            elif m.get("port"):
                options.append(f"{m.get('agent_type', 'unknown')}-{m['port']}")
        error = f"Ambiguous target '{target}'. Found: {agent_ids}"
        if options:
            error += f"\n  Hint: Use specific identifier like: {', '.join(options)}"
        return None, error

    return None, f"No agent found matching '{target}'"


def cmd_send(args: argparse.Namespace) -> None:
    """Send a message to a target agent using Google A2A protocol."""
    reg = AgentRegistry()
    agents = reg.list_agents()

    # Resolve target agent
    target_agent, error = _resolve_target_agent(args.target, agents)
    if error or target_agent is None:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)

    # Validate agent is actually running
    pid = target_agent.get("pid")
    port = target_agent.get("port")
    agent_id = target_agent["agent_id"]
    uds_path = get_valid_uds_path(target_agent.get("uds_path"))
    # Allow HTTP fallback if UDS fails (don't set local_only=True)
    local_only = False

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
    if not uds_path and port and not is_port_open("localhost", port, timeout=1.0):
        print(
            f"Error: Agent '{agent_id}' server on port {port} is not responding.",
            file=sys.stderr,
        )
        print(
            "  The process may be running but the A2A server is not started.",
            file=sys.stderr,
        )
        agent_type = target_agent["agent_type"]
        print(
            f"  Hint: Start the server with: synapse start {agent_type} --port {port}",
            file=sys.stderr,
        )
        sys.exit(1)

    # Build sender metadata
    sender_info = build_sender_info(getattr(args, "sender", None))

    # Send request using Google A2A protocol
    # Determine response_expected based on a2a.flow setting and flags
    settings = get_settings()
    flow = settings.get_a2a_flow()
    want_response = getattr(args, "want_response", None)

    # Flow modes: roundtrip always waits, oneway never waits, auto uses flag
    # Default to False (not waiting) for safety - see issue #96
    if flow == "oneway":
        response_expected = False
    elif flow == "roundtrip":
        response_expected = True
    else:  # auto
        response_expected = want_response if want_response is not None else False

    # Add metadata (sender info and response_expected)
    client = A2AClient()
    task = client.send_to_local(
        endpoint=str(target_agent["endpoint"]),
        message=args.message,
        priority=args.priority,
        wait_for_completion=response_expected,
        timeout=60,
        sender_info=sender_info or None,
        response_expected=response_expected,
        uds_path=uds_path if isinstance(uds_path, str) else None,
        local_only=local_only,
        registry=reg,
        sender_agent_id=sender_info.get("sender_id") if sender_info else None,
        target_agent_id=agent_id,
    )

    if not task:
        print("Error sending message: local send failed", file=sys.stderr)
        sys.exit(1)

    task_id = task.id or str(uuid.uuid4())
    agent_type = target_agent["agent_type"]
    agent_short = target_agent["agent_id"][:8]
    print(f"Success: Task created for {agent_type} ({agent_short}...)")
    print(f"  Task ID: {task_id}")
    print(f"  Status: {task.status}")

    if task.artifacts:
        print("  Response:")
        for artifact in task.artifacts:
            artifact_type = artifact.get("type", "unknown")
            content = artifact.get("data") or artifact.get("text", "")
            if content:
                indented = str(content).replace("\n", "\n    ")
                print(f"    [{artifact_type}] {indented}")

    # Record sent message to history
    _record_sent_message(
        task_id=task_id,
        target_agent=target_agent,
        message=args.message,
        priority=args.priority,
        sender_info=sender_info,
    )


def cmd_reply(args: argparse.Namespace) -> None:
    """Reply to the last message using the reply map.

    This command retrieves the reply target from the local agent's reply map
    and sends the reply message to the original sender.
    """
    # Determine own endpoint from sender info
    explicit_sender = getattr(args, "sender", None)
    sender_info = build_sender_info(explicit_sender)
    my_endpoint = sender_info.get("sender_endpoint")

    if not my_endpoint:
        print(
            "Error: Cannot determine my endpoint. Are you running in a synapse agent?",
            file=sys.stderr,
        )
        sys.exit(1)

    # Get reply target from my agent's reply map (don't pop yet)
    try:
        resp = requests.get(f"{my_endpoint}/reply-stack/get", timeout=5)
    except requests.RequestException as e:
        print(f"Error: Failed to get reply target: {e}", file=sys.stderr)
        sys.exit(1)

    if resp.status_code == 404:
        print(
            "Error: No reply target. No pending messages to reply to.", file=sys.stderr
        )
        sys.exit(1)
    elif resp.status_code != 200:
        print(
            f"Error: Failed to get reply target: HTTP {resp.status_code}",
            file=sys.stderr,
        )
        sys.exit(1)

    target = resp.json()
    target_endpoint = target.get("sender_endpoint")
    target_uds_path = target.get("sender_uds_path")
    task_id = target.get("sender_task_id")  # May be None

    if not target_endpoint and not target_uds_path:
        print("Error: Reply target has no endpoint", file=sys.stderr)
        sys.exit(1)

    # Send reply using A2AClient (prefer UDS if available)
    client = A2AClient()
    if target_uds_path:
        # Use UDS for reply
        result = client.send_to_local(
            endpoint=target_endpoint or "",
            message=args.message,
            priority=3,  # Normal priority for replies
            sender_info=sender_info,
            response_expected=False,  # Reply doesn't expect a reply back
            in_reply_to=task_id,
            uds_path=target_uds_path,
        )
    else:
        # Use HTTP for reply
        result = client.send_to_local(
            endpoint=target_endpoint or "",
            message=args.message,
            priority=3,  # Normal priority for replies
            sender_info=sender_info,
            response_expected=False,  # Reply doesn't expect a reply back
            in_reply_to=task_id,
        )

    if not result:
        print("Error: Failed to send reply", file=sys.stderr)
        sys.exit(1)

    # Only pop from stack after successful send
    with contextlib.suppress(requests.RequestException):
        requests.get(f"{my_endpoint}/reply-stack/pop", timeout=5)

    # Display target info (prefer UDS path if no HTTP endpoint)
    if target_endpoint and ":" in target_endpoint:
        target_short = target_endpoint.split(":")[-1]
    elif target_endpoint:
        target_short = target_endpoint
    elif target_uds_path:
        target_short = Path(target_uds_path).name
    else:
        target_short = "unknown"
    print(f"Reply sent to {target_short}")
    if task_id:
        print(f"  In reply to task: {task_id[:8]}...")


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
    # Response control: mutually exclusive group
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
    p_send.add_argument("message", help="Content of the message")

    # reply command - simplified reply to last message
    p_reply = subparsers.add_parser("reply", help="Reply to the last received message")
    p_reply.add_argument(
        "--from",
        dest="sender",
        help="Your agent ID (required in sandboxed environments like Codex)",
    )
    p_reply.add_argument("message", help="Reply message content")

    args = parser.parse_args()

    if args.command == "list":
        cmd_list(args)
    elif args.command == "cleanup":
        cmd_cleanup(args)
    elif args.command == "send":
        cmd_send(args)
    elif args.command == "reply":
        cmd_reply(args)


if __name__ == "__main__":
    main()
