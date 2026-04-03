import argparse
import logging
import os
import re
import shlex
import subprocess
import sys
import uuid
from pathlib import Path

from synapse.history import HistoryManager
from synapse.paths import get_history_db_path
from synapse.registry import AgentRegistry
from synapse.settings import get_settings

logger = logging.getLogger(__name__)


def _artifact_display_text(artifact: dict) -> str:
    """Extract display text from an artifact payload."""
    data = artifact.get("data")
    if isinstance(data, dict) and "content" in data:
        return str(data["content"])
    if data is not None:
        return str(data)
    return str(artifact.get("text", ""))


def _get_history_manager() -> HistoryManager:
    """Get history manager instance from environment."""
    db_path = get_history_db_path()
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
    except (subprocess.TimeoutExpired, ValueError, FileNotFoundError, PermissionError):
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
    """Extract sender info fields from agent registry entry."""
    sender_info: dict[str, str] = {"sender_id": agent_id}
    field_mapping = {
        "agent_type": "sender_type",
        "endpoint": "sender_endpoint",
        "uds_path": "sender_uds_path",
        "name": "sender_name",
    }
    for registry_key, sender_key in field_mapping.items():
        value = info.get(registry_key)
        if value:
            sender_info[sender_key] = value
    return sender_info


def _validate_explicit_sender(sender: str) -> str | None:
    """Validate explicit sender format and return helpful error if invalid."""
    if re.match(r"^synapse-[\w-]+-\d+$", sender):
        return None

    try:
        reg = AgentRegistry()
        agents = reg.list_agents()
        for agent_id, info in agents.items():
            if info.get("name") == sender:
                return (
                    f"Error: --from requires agent ID, not custom name.\n"
                    f"Use: --from {agent_id}"
                )
            if info.get("agent_type", "").lower() == sender.lower():
                return (
                    f"Error: --from requires agent ID, not agent type.\n"
                    f"Use: --from {agent_id}"
                )
    except Exception:
        pass

    return (
        "Error: --from requires agent ID format (synapse-<type>-<port>).\n"
        "Example: --from $SYNAPSE_AGENT_ID (or synapse-claude-8100)"
    )


def _lookup_sender_in_registry(agent_id: str) -> dict[str, str]:
    """Look up sender info from the agent registry."""
    try:
        reg = AgentRegistry()
        agents = reg.list_agents()
        if agent_id in agents:
            return _extract_sender_info_from_agent(agent_id, agents[agent_id])
    except Exception:
        pass
    return {"sender_id": agent_id}


def _get_current_tty() -> str | None:
    """Return the TTY device name for the current process, or None."""
    for fd in (0, 1, 2):
        try:
            tty = os.ttyname(fd)
            if tty:
                return tty
        except (OSError, ValueError):
            continue
    return None


def _find_sender_by_pid() -> dict[str, str]:
    """Find sender info by matching current process ancestry to registered agents."""
    try:
        reg = AgentRegistry()
        agents = reg.list_agents()
        current_pid = os.getpid()

        for agent_id, info in agents.items():
            agent_pid = info.get("pid")
            if agent_pid and is_descendant_of(current_pid, agent_pid):
                return _extract_sender_info_from_agent(agent_id, info)

        current_tty = _get_current_tty()
        if current_tty:
            for agent_id, info in agents.items():
                if info.get("tty_device") == current_tty:
                    return _extract_sender_info_from_agent(agent_id, info)

    except Exception as e:
        logger.error("Error in _find_sender_by_pid: %s", e, exc_info=True)
    return {}


def build_sender_info(explicit_sender: str | None = None) -> dict | str:
    """Build sender info using explicit sender, environment variable, or PID matching."""
    if not explicit_sender:
        env_sender = os.environ.get("SYNAPSE_AGENT_ID")
        if env_sender:
            return _lookup_sender_in_registry(env_sender)
        return _find_sender_by_pid()

    error = _validate_explicit_sender(explicit_sender)
    if error:
        return error

    return _lookup_sender_in_registry(explicit_sender)


def _format_task_error(task_error: object) -> tuple[str, str]:
    """Extract an error code/message pair from a task error payload."""
    if isinstance(task_error, dict):
        return (
            str(task_error.get("code", "UNKNOWN_ERROR")),
            str(task_error.get("message", "Task failed")),
        )

    return (
        str(getattr(task_error, "code", "UNKNOWN_ERROR")),
        str(getattr(task_error, "message", "Task failed")),
    )


def _record_sent_message(
    task_id: str,
    target_agent: dict[str, object],
    message: str,
    priority: int,
    sender_info: dict[str, str] | None,
) -> None:
    """Record sent message to history database."""
    try:
        history = _get_history_manager()
        if not history.enabled:
            return

        sender_name = "user"
        if sender_info:
            sender_name = sender_info.get("sender_type") or sender_name
            if sender_name == "user":
                sender_id = sender_info.get("sender_id", "")
                parts = sender_id.split("-") if sender_id else []
                if len(parts) >= 3 and parts[0] == "synapse":
                    sender_name = parts[1]

        metadata = {
            "direction": "sent",
            "target_agent_id": target_agent.get("agent_id"),
            "target_agent_type": target_agent.get("agent_type"),
            "priority": priority,
        }
        if sender_info:
            metadata["sender"] = sender_info

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
        logger.debug("Failed to record sent message to history", exc_info=True)


def _pick_best_agent(matches: list[dict]) -> dict:
    """Pick the best agent from multiple candidates."""

    def _sort_key(a: dict) -> tuple[int, int]:
        status = a.get("status") or ""
        ready = 0 if status.upper() == "READY" else 1
        port = a.get("port") or 99999
        return (ready, int(port))

    return sorted(matches, key=_sort_key)[0]


def _resolve_target_agent(
    target: str,
    agents: dict[str, dict],
    *,
    local_only: bool = False,
) -> tuple[dict | None, str | None]:
    """Resolve target agent from name/id."""
    if local_only:
        cwd = os.getcwd()
        normalized_cwd = _normalize_working_dir(cwd)

        def _is_same_dir(info: dict) -> bool:
            agent_dir = _normalize_working_dir(info.get("working_dir"))
            return agent_dir is None or agent_dir == normalized_cwd

        local_agents = {k: v for k, v in agents.items() if _is_same_dir(v)}
    else:
        local_agents = agents

    for info in local_agents.values():
        if info.get("name") == target:
            return info, None

    if target in local_agents:
        return local_agents[target], None

    target_lower = target.lower()

    type_port_match = re.match(r"^([\w-]+)-(\d+)$", target_lower)
    if type_port_match:
        target_type, port_str = type_port_match.groups()
        target_port = int(port_str)
        for info in local_agents.values():
            if (
                info.get("agent_type", "").lower() == target_type
                and info.get("port") == target_port
            ):
                return info, None

    matches = [
        a
        for a in local_agents.values()
        if target_lower in a.get("agent_type", "").lower()
    ]

    if len(matches) == 1:
        return matches[0], None

    if len(matches) > 1:
        return _pick_best_agent(matches), None

    return None, f"No agent found matching '{target}'"


def _format_ambiguous_target_error(target: str, matches: list[dict]) -> str:
    """Format error message for ambiguous target resolution."""
    agent_ids = [m.get("agent_id", "unknown") for m in matches]
    error = f"Ambiguous target '{target}'. Found {len(matches)} agents: {agent_ids}"

    lines = ["  Use a specific identifier to target the right agent:"]
    for m in matches:
        agent_id = m.get("agent_id", "unknown")
        name = m.get("name")
        identifier = shlex.quote(name) if name else agent_id
        hint = f"  # {agent_id}" if name else ""
        lines.append(f'    synapse send {identifier} "<message>"{hint}')

    return error + "\n" + "\n".join(lines)


def _extract_agent_type_from_id(agent_id: str) -> str | None:
    """Extract agent type from an agent ID like 'synapse-claude-8100'."""
    parts = agent_id.split("-")
    if len(parts) >= 2:
        return parts[1]
    return None


def _suggest_spawn_type(target_type: str, sender_type: str | None) -> str:
    """Pick an agent type to suggest for spawning, avoiding the sender's own type."""
    from synapse.port_manager import PORT_RANGES

    if not sender_type or target_type != sender_type:
        return target_type

    for agent_type in PORT_RANGES:
        if agent_type != sender_type and agent_type != "dummy":
            return agent_type

    return target_type


def _get_response_mode(response_mode_arg: str | None) -> str:
    """Resolve response mode from settings and CLI flags."""
    if response_mode_arg:
        return response_mode_arg
    settings = get_settings()
    flow = settings.get_a2a_flow()
    flow_defaults = {"oneway": "silent", "roundtrip": "wait"}
    return flow_defaults.get(flow, "notify")


def _normalize_working_dir(path_str: str | None) -> str | None:
    """Normalize a working directory path for stable comparisons."""
    if not path_str:
        return None
    try:
        return str(Path(path_str).expanduser().resolve())
    except OSError:
        return os.path.abspath(os.path.expanduser(path_str))


_WORKTREE_SEGMENT = os.sep + ".synapse" + os.sep + "worktrees" + os.sep


def _get_worktree_parent_dir(path: str | None) -> str | None:
    """If *path* is under ``.synapse/worktrees/``, return the parent repo root."""
    if not path:
        return None
    idx = path.find(_WORKTREE_SEGMENT)
    if idx == -1:
        return None
    return path[:idx]


def _are_worktree_related(path_a: str, path_b: str) -> bool:
    """Return True if two paths belong to the same repo via worktree relationship."""
    parent_a = _get_worktree_parent_dir(path_a)
    parent_b = _get_worktree_parent_dir(path_b)
    # Both are worktrees of the same parent
    if parent_a and parent_b:
        return parent_a == parent_b
    # a is parent repo, b is its worktree
    if parent_b and parent_b == path_a:
        return True
    # a is worktree, b is its parent repo
    return bool(parent_a and parent_a == path_b)


def _agents_in_current_working_dir(
    agents: dict[str, dict],
    cwd: str,
    exclude_id: str | None = None,
) -> list[dict]:
    """Return agents whose working_dir matches current working directory."""
    normalized_cwd = _normalize_working_dir(cwd)
    if not normalized_cwd:
        return []

    result = []
    for agent in agents.values():
        if agent.get("agent_id") == exclude_id:
            continue
        norm_dir = _normalize_working_dir(agent.get("working_dir"))
        if not norm_dir:
            continue
        if norm_dir == normalized_cwd or _are_worktree_related(
            normalized_cwd, norm_dir
        ):
            result.append(agent)
    return result


def _warn_working_dir_mismatch(
    target_agent: dict,
    agents: dict[str, dict],
) -> bool:
    """Check and warn if sender CWD differs from target's working_dir."""
    target_dir = target_agent.get("working_dir")
    if not target_dir:
        return False

    cwd = os.getcwd()
    normalized_cwd = _normalize_working_dir(cwd)
    normalized_target = _normalize_working_dir(target_dir)

    if normalized_cwd == normalized_target:
        return False

    # Worktree agents belong to the same repo -- no mismatch
    if (
        normalized_cwd
        and normalized_target
        and _are_worktree_related(normalized_cwd, normalized_target)
    ):
        return False

    display_name = target_agent.get("name") or target_agent.get("agent_id", "unknown")

    print(
        f'Warning: Target agent "{display_name}" is in a different directory:',
        file=sys.stderr,
    )
    print(f"  Sender:  {cwd}", file=sys.stderr)
    print(f"  Target:  {target_dir}", file=sys.stderr)

    target_id = target_agent.get("agent_id")
    same_dir = _agents_in_current_working_dir(agents, cwd, exclude_id=target_id)

    if same_dir:
        print("Agents in current directory:", file=sys.stderr)
        for a in same_dir:
            name = a.get("name") or a.get("agent_id", "?")
            atype = a.get("agent_type", "?")
            status = a.get("status", "?")
            print(f"  {name} ({atype}) - {status}", file=sys.stderr)
    else:
        sender_id = os.environ.get("SYNAPSE_AGENT_ID", "")
        sender_type = _extract_agent_type_from_id(sender_id) if sender_id else None
        suggest_type = _suggest_spawn_type(
            target_agent.get("agent_type", "claude"), sender_type
        )
        print("No agents in current directory. Spawn one with:", file=sys.stderr)
        print(f"  synapse spawn {suggest_type} --name <name>", file=sys.stderr)

    print("Use --force to send anyway.", file=sys.stderr)
    return True


def _resolve_message(args: argparse.Namespace) -> str:
    """Resolve message content from positional arg, --message-file, or --stdin."""
    sources: list[str] = []
    if getattr(args, "message", None):
        sources.append("positional")
    if getattr(args, "message_file", None):
        sources.append("--message-file")
    if getattr(args, "stdin", False):
        sources.append("--stdin")

    if len(sources) > 1:
        print(
            f"Error: Multiple message sources specified: {', '.join(sources)}. "
            "Use exactly one of: positional argument, --message-file, or --stdin.",
            file=sys.stderr,
        )
        sys.exit(1)

    if len(sources) == 0:
        print(
            "Error: No message provided. Use a positional argument, "
            "--message-file PATH, or --stdin.",
            file=sys.stderr,
        )
        sys.exit(1)

    if getattr(args, "stdin", False):
        return sys.stdin.read()

    message_file = getattr(args, "message_file", None)
    if message_file:
        if message_file == "-":
            return sys.stdin.read()
        path = Path(message_file)
        if not path.exists():
            print(f"Error: Message file not found: {message_file}", file=sys.stderr)
            sys.exit(1)
        return path.read_text(encoding="utf-8")

    return str(args.message)


def _process_attachments(file_paths: list[str]) -> list[dict]:
    """Stage attachment files into a temp dir and return FilePart dicts."""
    import shutil
    import tempfile

    if not file_paths:
        return []

    staging_dir = Path(tempfile.gettempdir()) / "synapse-a2a" / "attachments"
    staging_dir.mkdir(parents=True, exist_ok=True)

    parts: list[dict] = []
    for file_path in file_paths:
        src = Path(file_path)
        if not src.exists():
            print(f"Error: Attachment file not found: {file_path}", file=sys.stderr)
            sys.exit(1)
        if not src.is_file():
            print(f"Error: Attachment path is not a file: {file_path}", file=sys.stderr)
            sys.exit(1)

        staged_path = staging_dir / f"{uuid.uuid4()}-{src.name}"
        try:
            shutil.copy2(src, staged_path)
        except OSError as e:
            print(
                f"Error: Failed to stage attachment '{file_path}': {e}",
                file=sys.stderr,
            )
            sys.exit(1)

        parts.append(
            {
                "type": "file",
                "file": {"name": src.name, "uri": f"file://{staged_path}"},
            }
        )

    return parts


def _warn_shell_expansion(message: str) -> None:
    """Warn if message contains shell expansion characters."""
    patterns = [
        (r"`[^`]+`", "backtick command substitution"),
        (r"\$\([^)]+\)", "$() command substitution"),
        (r"\$\{[^}]+\}", "${} variable expansion"),
    ]
    for pattern, desc in patterns:
        if re.search(pattern, message):
            print(
                f"WARNING: Message contains {desc} which may be expanded by the shell.\n"
                "  Consider using --message-file or --stdin to avoid shell expansion:\n"
                '    echo "your message" | synapse send <target> --stdin\n'
                "    synapse send <target> --message-file /path/to/message.txt",
                file=sys.stderr,
            )
            return


def _get_target_display_name(endpoint: str | None, uds_path: str | None) -> str:
    """Get a short display name for the target agent."""
    if endpoint and ":" in endpoint:
        return endpoint.rsplit(":", 1)[-1]
    if endpoint:
        return endpoint
    if uds_path:
        return Path(uds_path).name
    return "unknown"


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


def _add_message_source_flags(parser: argparse.ArgumentParser) -> None:
    """Add --message-file, --stdin, and --attach flags to a parser."""
    parser.add_argument(
        "--message-file",
        "-F",
        dest="message_file",
        help="Read message from file (use '-' for stdin)",
    )
    parser.add_argument(
        "--stdin",
        action="store_true",
        default=False,
        help="Read message from stdin",
    )
    parser.add_argument(
        "--attach",
        "-a",
        action="append",
        dest="attach",
        help="Attach a file to the message (repeatable)",
    )
