"""Messaging command handlers for Synapse CLI."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def _get_a2a_tool_path() -> Path:
    """Get the path to the a2a.py tool from installed package."""
    import synapse

    return Path(synapse.__file__).parent / "tools" / "a2a.py"


def _run_a2a_command(
    cmd: list[str],
    exit_on_error: bool = False,
) -> None:
    """Run an a2a.py command and print output."""
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    if exit_on_error and result.returncode != 0:
        sys.exit(result.returncode)


def _get_send_message_threshold() -> int:
    """Get the byte-size threshold for auto temp-file fallback."""
    env_val = os.environ.get("SYNAPSE_SEND_MESSAGE_THRESHOLD")
    if env_val:
        return int(env_val)
    return 102_400


def _build_a2a_cmd(
    subcommand: str,
    message: str,
    *,
    target: str | None = None,
    priority: int | None = None,
    sender: str | None = None,
    response_mode: str | None = None,
    attachments: list[str] | None = None,
    force: bool = False,
) -> list[str]:
    """Build command arguments for a2a.py subcommand."""
    import tempfile

    cmd = [sys.executable, "-m", "synapse.tools.a2a", subcommand]

    if target:
        cmd.extend(["--target", target])
    if priority is not None:
        cmd.extend(["--priority", str(priority)])

    threshold = _get_send_message_threshold()
    if len(message.encode("utf-8")) > threshold:
        send_dir = Path(tempfile.gettempdir()) / "synapse-a2a" / "send-messages"
        send_dir.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            prefix="send-", suffix=".txt", dir=str(send_dir)
        )
        try:
            os.write(fd, message.encode("utf-8"))
            os.close(fd)
            os.chmod(tmp_path, 0o600)
        except Exception:
            os.close(fd)
            Path(tmp_path).unlink(missing_ok=True)
            raise
        cmd.extend(["--message-file", tmp_path])
    else:
        cmd.append(message)

    if attachments:
        for path in attachments:
            cmd.extend(["--attach", path])

    if sender:
        cmd.extend(["--from", sender])
    if response_mode:
        cmd.append(f"--{response_mode}")
    if force:
        cmd.append("--force")

    return cmd


def _resolve_cli_message(args: argparse.Namespace) -> str:
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


def _resolve_task_message(args: argparse.Namespace) -> str | None:
    """Resolve spawn task content from --task or --task-file."""
    task = getattr(args, "task", None)
    task_file = getattr(args, "task_file", None)

    if task is not None:
        return str(task)

    if task_file:
        if task_file == "-":
            return sys.stdin.read()
        path = Path(task_file)
        if not path.exists():
            print(f"Error: Task file not found: {task_file}", file=sys.stderr)
            sys.exit(1)
        return path.read_text(encoding="utf-8")

    return None


def cmd_send(args: argparse.Namespace) -> None:
    """Send a message to an agent."""
    message = _resolve_cli_message(args)

    cmd = _build_a2a_cmd(
        "send",
        message,
        target=args.target,
        priority=args.priority,
        sender=getattr(args, "sender", None),
        response_mode=getattr(args, "response_mode", None),
        attachments=getattr(args, "attach", None),
        force=getattr(args, "force", False),
    )
    _run_a2a_command(cmd, exit_on_error=True)


def cmd_interrupt(args: argparse.Namespace) -> None:
    """Send a priority-4 interrupt message to an agent."""
    cmd = _build_a2a_cmd(
        "send",
        args.message,
        target=args.target,
        priority=4,
        sender=getattr(args, "sender", None),
        response_mode="silent",
        force=getattr(args, "force", False),
    )
    _run_a2a_command(cmd, exit_on_error=True)


def cmd_broadcast(args: argparse.Namespace) -> None:
    """Broadcast a message to all agents in current working directory."""
    message = _resolve_cli_message(args)
    cmd = _build_a2a_cmd(
        "broadcast",
        message,
        priority=args.priority,
        sender=getattr(args, "sender", None),
        response_mode=getattr(args, "response_mode", None),
        attachments=getattr(args, "attach", None),
    )
    _run_a2a_command(cmd, exit_on_error=True)


def cmd_reply(args: argparse.Namespace) -> None:
    """Reply to the last received A2A message using reply tracking."""
    message = args.message
    sender = getattr(args, "sender", None)
    to_sender = getattr(args, "to", None)
    list_targets = getattr(args, "list_targets", False)

    cmd = [sys.executable, str(_get_a2a_tool_path()), "reply"]
    if sender:
        cmd.extend(["--from", sender])
    if to_sender:
        cmd.extend(["--to", to_sender])
    if list_targets:
        cmd.append("--list-targets")
    if message:
        cmd.append(message)

    _run_a2a_command(cmd, exit_on_error=True)
