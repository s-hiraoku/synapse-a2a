import argparse
import contextlib
import json
import math
import os
import shlex
import sys
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

import requests

from synapse.a2a_client import A2AClient

if TYPE_CHECKING:
    from synapse.a2a_client import A2ATask
from synapse.a2a_compat import (
    _REPLY_ARTIFACTS_METADATA_KEY,
    _REPLY_ERROR_METADATA_KEY,
    _REPLY_STATUS_METADATA_KEY,
    ERROR_CODE_REPLY_FAILED,
)
from synapse.registry import (
    AgentRegistry,
    get_valid_uds_path,
    is_port_open,
    is_process_running,
)
from synapse.reply_stack import SenderInfo
from synapse.reply_target import clear_reply_target, load_reply_target
from synapse.status import (
    DONE,
    PROCESSING,
    RATE_LIMITED,
    READY,
    SENDING_REPLY,
    SHUTTING_DOWN,
    WAITING,
    WAITING_FOR_INPUT,
)
from synapse.tools.a2a_helpers import (  # noqa: F401 -- re-export
    _add_message_source_flags,
    _add_response_mode_flags,
    _agents_in_current_working_dir,
    _are_worktree_related,
    _artifact_display_text,
    _extract_agent_type_from_id,
    _extract_sender_info_from_agent,
    _find_sender_by_pid,
    _format_ambiguous_target_error,
    _format_task_error,
    _get_current_tty,
    _get_history_manager,
    _get_response_mode,
    _get_target_display_name,
    _get_worktree_parent_dir,
    _lookup_sender_in_registry,
    _normalize_working_dir,
    _pick_best_agent,
    _process_attachments,
    _record_sent_message,
    _resolve_message,
    _resolve_target_agent,
    _suggest_spawn_type,
    _validate_explicit_sender,
    _warn_shell_expansion,
    _warn_working_dir_mismatch,
    build_sender_info,
    get_parent_pid,
    is_descendant_of,
)

_SENDING_REPLY_SOURCE_STATUSES = frozenset(
    {READY, PROCESSING, WAITING, WAITING_FOR_INPUT}
)
_SENDING_REPLY_PROTECTED_STATUSES = frozenset({DONE, SHUTTING_DOWN, RATE_LIMITED})


def _set_sending_reply_status(
    registry: AgentRegistry, sender_agent_id: str | None
) -> str | None:
    """Set the sender registry status while an outbound A2A POST is active."""
    if not sender_agent_id:
        return None
    agent_info = registry.get_agent(sender_agent_id)
    if not agent_info:
        return None
    original_status = agent_info.get("status")
    if original_status in _SENDING_REPLY_PROTECTED_STATUSES:
        return None
    if original_status not in _SENDING_REPLY_SOURCE_STATUSES:
        return None
    registry.update_status(sender_agent_id, SENDING_REPLY)
    return str(original_status)


def _restore_sending_reply_status(
    registry: AgentRegistry, sender_agent_id: str | None, original_status: str | None
) -> None:
    """Restore the sender's status after an outbound A2A POST.

    Only restores when the live status is still ``SENDING_REPLY``. If the
    controller has moved the agent to a protected status (e.g. ``DONE``,
    ``RATE_LIMITED``, ``SHUTTING_DOWN``) during the send, leave it alone so
    the protected state wins — the contract is that ``_set_sending_reply_status``
    refuses to start a SENDING_REPLY transition over those statuses, and the
    finally block must not silently undo a controller intervention either.
    """
    if not sender_agent_id or not original_status:
        return
    agent_info = registry.get_agent(sender_agent_id)
    if not agent_info:
        return
    if agent_info.get("status") != SENDING_REPLY:
        return
    registry.update_status(sender_agent_id, original_status)


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


def _wait_for_parent_intervention(
    *,
    endpoint: str,
    task_id: str,
    timeout_s: int,
    uds_path: str | None = None,
) -> "A2ATask | None":
    """Poll a child task that entered ``input_required`` until it reaches a
    terminal state.

    The Approval Gate (``synapse.approval_gate``, issue #571) handles the
    escalation side: when the child server flips a task to input_required,
    ``_on_status_change`` already sends a structured permission notification
    to the parent, and the parent's own ``_send_task_message`` handler auto-
    dispatches it through ``decide_and_apply``. That call eventually posts
    to ``/tasks/<id>/permission/{approve,deny}`` on this same child, which
    unblocks the PTY and returns the task to ``working`` → ``completed``.

    This helper therefore keeps the sender subprocess alive and simply polls
    the task until it terminates. Returns the final task on terminal state,
    or ``None`` on timeout (parent never intervened).
    """
    from synapse.a2a_client import A2ATask
    from synapse.config import COMPLETED_TASK_STATES, TASK_POLL_INTERVAL

    if not endpoint:
        return None

    base = endpoint.rstrip("/")
    url = f"{base}/tasks/{task_id}"
    deadline = time.time() + max(timeout_s, 0)
    last_task_status: str | None = None

    while time.time() < deadline:
        data: dict | None = None
        try:
            if uds_path:
                import httpx

                transport = httpx.HTTPTransport(uds=uds_path)
                with httpx.Client(transport=transport, timeout=10.0) as client:
                    uds_resp = client.get(url)
                    uds_resp.raise_for_status()
                    data = uds_resp.json()
            else:
                http_resp = requests.get(url, timeout=10)
                http_resp.raise_for_status()
                data = http_resp.json()
        except Exception:  # broad: transient HTTP errors shouldn't abort the watch
            time.sleep(TASK_POLL_INTERVAL)
            continue

        if data is None:
            time.sleep(TASK_POLL_INTERVAL)
            continue

        task = A2ATask.from_dict(data, fallback_id=task_id)
        status = task.status
        if status != last_task_status:
            print(
                f"  Task {task_id[:8]} status: {status}",
                file=sys.stderr,
            )
            last_task_status = status
        if status in COMPLETED_TASK_STATES:
            return task
        time.sleep(TASK_POLL_INTERVAL)

    return None


def cmd_send(args: argparse.Namespace) -> None:
    """Send a message to a target agent using Google A2A protocol."""
    message, source = _resolve_message(args)
    if source == "positional":
        _warn_shell_expansion(message)
    file_parts = None
    if getattr(args, "attach", None):
        file_parts = _process_attachments(args.attach)

    reg = AgentRegistry()
    agents = reg.list_agents()
    sender_id = getattr(args, "sender", None) or os.getenv("SYNAPSE_AGENT_ID")

    # Resolve target agent. --local-only restricts candidates to agents in
    # the caller's working directory so bare-type targets never fall back to
    # agents running elsewhere (used by workflow runner).
    local_only = bool(getattr(args, "local_only", False))
    target_agent, error = _resolve_target_agent(
        args.target,
        agents,
        local_only=local_only,
        sender_id=sender_id,
    )
    if error or target_agent is None:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)

    # Validate agent is actually running
    pid = target_agent.get("pid")
    port = target_agent.get("port")
    agent_id = target_agent["agent_id"]
    uds_path = get_valid_uds_path(target_agent.get("uds_path"))

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

    # Determine response_mode based on a2a.flow setting and flags
    response_mode = _get_response_mode(getattr(args, "response_mode", None))

    def _refresh_target_agent() -> dict | None:
        """Re-read the target agent's registry entry, or None if it vanished."""
        agents_now = AgentRegistry().list_agents()
        return next(
            (a for a in agents_now.values() if a.get("agent_id") == agent_id),
            None,
        )

    # Sends should not bypass status-aware delays unless the caller explicitly
    # opts out. Silent sends are fire-and-forget reply flows that can deadlock
    # if we wait; --force and priority=5 are deliberate emergency overrides.
    delay_bypassed = (
        response_mode == "silent"
        or getattr(args, "force", False)
        or getattr(args, "priority", 0) == 5
    )

    # Wait for target to leave PROCESSING unless bypassed.
    if not delay_bypassed:
        status = target_agent.get("status", "")
        if status == "PROCESSING":
            display_name = target_agent.get("name") or agent_id
            try:
                wait_timeout = int(os.environ.get("SYNAPSE_SEND_WAIT_TIMEOUT", "30"))
            except ValueError:
                wait_timeout = 30
            wait_timeout = max(wait_timeout, 0)

            waited = 0
            while waited < wait_timeout and status == "PROCESSING":
                print(
                    f"\rWaiting for {display_name} to become READY... ({waited}s)",
                    end="",
                    file=sys.stderr,
                )
                time.sleep(1)
                waited += 1

                refreshed = _refresh_target_agent()
                if refreshed:
                    target_agent = refreshed
                    status = refreshed.get("status", "")
                else:
                    break

            if waited > 0:
                print("", file=sys.stderr)
            if status == "PROCESSING":
                print(
                    f"Warning: Timed out waiting for {display_name} to become READY. Continuing send.",
                    file=sys.stderr,
                )

    # Give READY targets a short window to flip to PROCESSING before injecting
    # a message, which avoids interrupting a user who is still typing at prompt.
    if not delay_bypassed and target_agent.get("status", "") == "READY":
        try:
            ready_delay = float(os.environ.get("SYNAPSE_SEND_READY_DELAY", "2"))
        except ValueError:
            ready_delay = 2.0
        if not math.isfinite(ready_delay):
            ready_delay = 2.0
        ready_delay = max(ready_delay, 0.0)

        if ready_delay > 0:
            poll_interval = 0.25
            elapsed = 0.0
            while elapsed < ready_delay:
                time.sleep(poll_interval)
                elapsed += poll_interval

                refreshed = _refresh_target_agent()
                if refreshed:
                    target_agent = refreshed
                    if refreshed.get("status", "") == "PROCESSING":
                        break
                else:
                    break

    # Check working_dir mismatch (skip with --force)
    if not getattr(args, "force", False) and _warn_working_dir_mismatch(
        target_agent, agents
    ):
        sys.exit(1)

    # Build sender metadata
    sender_info = build_sender_info(getattr(args, "sender", None))

    # Check if build_sender_info returned an error
    if isinstance(sender_info, str):
        print(sender_info, file=sys.stderr)
        sys.exit(1)
    if not sender_info:
        print(
            "Warning: Could not identify sender agent. "
            "Set SYNAPSE_AGENT_ID or use --from.",
            file=sys.stderr,
        )

    # Add metadata (sender info and response_mode)
    client = A2AClient()
    outbound_sender_id = sender_info.get("sender_id") if sender_info else sender_id
    original_status = _set_sending_reply_status(reg, outbound_sender_id)
    try:
        task = client.send_to_local(
            endpoint=str(target_agent["endpoint"]),
            message=message,
            file_parts=file_parts,
            priority=args.priority,
            wait_for_completion=(response_mode == "wait"),
            timeout=60,
            sender_info=sender_info or None,
            response_mode=response_mode,
            uds_path=uds_path,
            registry=reg,
            sender_agent_id=sender_info.get("sender_id") if sender_info else None,
            target_agent_id=agent_id,
        )
    finally:
        _restore_sending_reply_status(reg, outbound_sender_id, original_status)

    if not task:
        print("Error sending message: local send failed", file=sys.stderr)
        print(
            "  Use SYNAPSE_LOG_LEVEL=DEBUG for details.",
            file=sys.stderr,
        )
        sys.exit(1)

    task_id = task.id or str(uuid.uuid4())
    agent_type = target_agent["agent_type"]
    agent_short = target_agent["agent_id"][:8]

    print(f"Success: Task created for {agent_type} ({agent_short}...)")
    print(f"  Task ID: {task_id}")
    print(f"  Status: {task.status}")

    task_error = getattr(task, "error", None)
    if task.status == "failed" and task_error:
        code, message = _format_task_error(task_error)
        print(f"  Error: {code} - {message}")
    elif task.artifacts:
        print("  Response:")
        for artifact in task.artifacts:
            artifact_type = artifact.get("type", "unknown")
            content = _artifact_display_text(artifact)
            if content:
                indented = str(content).replace("\n", "\n    ")
                print(f"    [{artifact_type}] {indented}")

    _record_sent_message(
        task_id=task_id,
        target_agent=target_agent,
        message=message,
        priority=args.priority,
        sender_info=sender_info,
    )

    # If the target stopped in input_required while we were waiting (wait
    # mode only), the child is blocked on parent input — typically a
    # permission prompt like "1. Yes, proceed  2. No, tell Codex what to do".
    # The A2AClient stopped polling early (#513) to surface this to the
    # caller, but we should NOT give up: the child is still running and
    # perfectly recoverable once the parent responds.
    #
    # Instead, stay alive and keep polling the task endpoint. When the
    # parent intervenes (either via POST /tasks/<id>/permission/approve, or
    # by sending a clarification message), the child's PTY unblocks, its
    # task returns to ``working``, and eventually reaches a terminal state.
    # We then print the final artifacts and exit 0 just like a normal wait.
    #
    # This preserves the invariant "parent is responsible for its children"
    # without forcing the runner/script to guess whether a busy-looking child
    # is hung or waiting for help.
    if response_mode == "wait" and task.status == "input_required":
        endpoint_url = str(target_agent.get("endpoint") or "").rstrip("/")
        display_target = target_agent.get("name") or target_agent.get("agent_id", "")
        pty_context = ""
        metadata = getattr(task, "metadata", None) or {}
        permission = metadata.get("permission") if isinstance(metadata, dict) else None
        if isinstance(permission, dict):
            pty_context = str(permission.get("pty_context", "") or "")

        print(
            f"Note: Target task {task_id} is in input_required state — "
            "waiting for parent intervention.",
            file=sys.stderr,
        )
        if endpoint_url:
            print(f"  Endpoint: {endpoint_url}", file=sys.stderr)
        print(f"  Task ID:  {task_id}", file=sys.stderr)
        if pty_context:
            preview = (
                pty_context if len(pty_context) <= 300 else pty_context[:297] + "..."
            )
            print(f"  PTY hint: {preview}", file=sys.stderr)
        if endpoint_url:
            print(
                f"  Approve:  curl -X POST {endpoint_url}/tasks/{task_id}/permission/approve",
                file=sys.stderr,
            )
        if display_target:
            quoted_target = shlex.quote(str(display_target))
            print(
                "  Or send a clarification message with: "
                f"synapse send {quoted_target} '<reply>' --local-only",
                file=sys.stderr,
            )

        try:
            intervention_timeout_s = int(
                os.environ.get("SYNAPSE_PARENT_INTERVENTION_TIMEOUT", "1800")
            )
        except ValueError:
            intervention_timeout_s = 1800
        if intervention_timeout_s < 0:
            intervention_timeout_s = 1800

        final_task = _wait_for_parent_intervention(
            endpoint=endpoint_url,
            task_id=task_id,
            timeout_s=intervention_timeout_s,
            uds_path=uds_path,
        )

        if final_task is None:
            print(
                "Error: Parent did not intervene within "
                f"{intervention_timeout_s}s; task still input_required.",
                file=sys.stderr,
            )
            sys.exit(2)

        # Update local task ref and re-display results.
        task = final_task
        print(f"  Resolved Status: {task.status}")
        task_error = getattr(task, "error", None)
        if task.status == "failed" and task_error:
            code, message = _format_task_error(task_error)
            print(f"  Error: {code} - {message}")
        elif task.artifacts:
            print("  Response:")
            for artifact in task.artifacts:
                artifact_type = artifact.get("type", "unknown")
                content = _artifact_display_text(artifact)
                if content:
                    indented = str(content).replace("\n", "\n    ")
                    print(f"    [{artifact_type}] {indented}")

        if task.status in ("failed", "canceled"):
            sys.exit(1)


def cmd_broadcast(args: argparse.Namespace) -> None:
    """Broadcast a message to all agents in current working directory."""
    message, source = _resolve_message(args)
    if source == "positional":
        _warn_shell_expansion(message)
    file_parts = None
    if getattr(args, "attach", None):
        file_parts = _process_attachments(args.attach)

    reg = AgentRegistry()
    agents = reg.list_agents()

    sender_info = build_sender_info(getattr(args, "sender", None))
    if isinstance(sender_info, str):
        print(sender_info, file=sys.stderr)
        sys.exit(1)

    sender_id = sender_info.get("sender_id") if sender_info else None
    recipients = _agents_in_current_working_dir(
        agents=agents,
        cwd=str(Path.cwd()),
        exclude_id=sender_id,
    )

    if not recipients:
        print(
            "Error: No agents found in current working directory",
            file=sys.stderr,
        )
        sys.exit(1)

    response_mode = _get_response_mode(getattr(args, "response_mode", None))
    client = A2AClient()
    sent_count = 0
    failed: list[tuple[str, str]] = []

    for target_agent in recipients:
        agent_id = target_agent.get("agent_id", "unknown")
        pid = target_agent.get("pid")
        port = target_agent.get("port")
        endpoint = target_agent.get("endpoint")
        uds_path = get_valid_uds_path(target_agent.get("uds_path"))

        if not endpoint:
            failed.append((agent_id, "missing endpoint"))
            continue

        if pid and not is_process_running(pid):
            reg.unregister(agent_id)
            failed.append((agent_id, f"process {pid} is no longer running"))
            continue

        if not uds_path and port and not is_port_open("localhost", port, timeout=1.0):
            failed.append((agent_id, f"server on port {port} is not responding"))
            continue

        task = client.send_to_local(
            endpoint=str(endpoint),
            message=message,
            file_parts=file_parts,
            priority=args.priority,
            wait_for_completion=(response_mode == "wait"),
            timeout=60,
            sender_info=sender_info or None,
            response_mode=response_mode,
            uds_path=uds_path,
            local_only=False,
            registry=reg,
            sender_agent_id=sender_id,
            target_agent_id=agent_id,
        )

        if not task:
            failed.append((agent_id, "local send failed"))
            continue

        sent_count += 1
        task_id = task.id or str(uuid.uuid4())
        _record_sent_message(
            task_id=task_id,
            target_agent=target_agent,
            message=message,
            priority=args.priority,
            sender_info=sender_info or None,
        )

    print(f"Sent: {sent_count}")
    print(f"Failed: {len(failed)}")
    for agent_id, reason in failed:
        print(f"  - {agent_id}: {reason}")

    if failed:
        sys.exit(1)


def cmd_reply(args: argparse.Namespace) -> None:
    """Reply to the last message using the reply map.

    This command retrieves the reply target from the local agent's reply map
    and sends the reply message to the original sender.

    Supports --to to reply to a specific sender and --list-targets to show
    all available reply targets.
    """
    # Determine own endpoint from sender info
    explicit_sender = getattr(args, "sender", None)
    sender_info = build_sender_info(explicit_sender)

    # Handle error case from build_sender_info
    if isinstance(sender_info, str):
        print(sender_info, file=sys.stderr)
        sys.exit(1)

    my_endpoint = sender_info.get("sender_endpoint")

    if not my_endpoint:
        print(
            "Error: Cannot determine my endpoint. Are you running in a synapse agent?",
            file=sys.stderr,
        )
        sys.exit(1)

    # Handle --list-targets
    if getattr(args, "list_targets", False):
        try:
            resp = requests.get(f"{my_endpoint}/reply-stack/list", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                sender_ids = data.get("sender_ids", [])
                targets = data.get("targets", [])
                if sender_ids:
                    print("Available reply targets:")
                    if targets:
                        for target_summary in targets:
                            sender_id = target_summary.get("sender_id", "unknown")
                            task_id = target_summary.get("sender_task_id")
                            preview = target_summary.get("message_preview")
                            received_at = target_summary.get("received_at")
                            parts = [f"  - {sender_id}"]
                            if task_id:
                                parts.append(f"task={task_id}")
                            if received_at:
                                parts.append(f"received_at={received_at}")
                            if preview:
                                parts.append(f"preview={preview}")
                            print(" | ".join(parts))
                    else:
                        for sid in sender_ids:
                            print(f"  - {sid}")
                else:
                    print("No reply targets available.")
            else:
                print(
                    f"Error: Failed to list reply targets: HTTP {resp.status_code}",
                    file=sys.stderr,
                )
                sys.exit(1)
        except requests.RequestException as e:
            print(f"Error: Failed to list reply targets: {e}", file=sys.stderr)
            sys.exit(1)
        return

    message = getattr(args, "message", "").strip()
    fail_reason = getattr(args, "fail", None)
    if fail_reason and message:
        print(
            "Error: Use either a reply message or --fail, not both.",
            file=sys.stderr,
        )
        sys.exit(1)
    if fail_reason:
        message = str(fail_reason).strip()

    if not message:
        print(
            "Error: Reply message is required unless --list-targets is used.",
            file=sys.stderr,
        )
        sys.exit(1)

    def _load_target_summaries() -> list[dict[str, str]]:
        try:
            resp = requests.get(f"{my_endpoint}/reply-stack/list", timeout=5)
        except requests.RequestException:
            return []
        if resp.status_code != 200:
            return []
        data = resp.json()
        targets = data.get("targets", [])
        if isinstance(targets, list) and targets:
            return [target for target in targets if isinstance(target, dict)]
        sender_ids = data.get("sender_ids", [])
        if isinstance(sender_ids, list):
            return [{"sender_id": sid} for sid in sender_ids if isinstance(sid, str)]
        return []

    to_sender = getattr(args, "to", None)
    if not to_sender:
        summaries = _load_target_summaries()
        if len(summaries) > 1:
            print(
                "Error: Multiple reply targets available. Use "
                "'synapse reply --list-targets' or pass --to <sender_id>.",
                file=sys.stderr,
            )
            for summary in summaries:
                sender_id = summary.get("sender_id", "unknown")
                print(f"  - {sender_id}", file=sys.stderr)
            sys.exit(1)
        if len(summaries) == 1:
            to_sender = summaries[0].get("sender_id")

    # Build reply-stack/get URL with optional sender_id
    get_url = f"{my_endpoint}/reply-stack/get"
    if to_sender:
        get_url += f"?sender_id={to_sender}"

    # Get reply target from my agent's reply map (don't pop yet)
    try:
        resp = requests.get(get_url, timeout=5)
    except requests.RequestException as e:
        print(f"Error: Failed to get reply target: {e}", file=sys.stderr)
        sys.exit(1)

    target: dict[str, str | None] | SenderInfo | None = None
    got_target_from_stack = False
    # sender_info is guaranteed to be dict here (str case exits above)
    my_agent_id = sender_info.get("sender_id")

    if resp.status_code == 404:
        if my_agent_id:
            persisted = load_reply_target(my_agent_id)
            if persisted:
                target = persisted
        if not target:
            print(
                "Error: No reply target. No pending messages to reply to.",
                file=sys.stderr,
            )
            sys.exit(1)
    elif resp.status_code != 200:
        print(
            f"Error: Failed to get reply target: HTTP {resp.status_code}",
            file=sys.stderr,
        )
        sys.exit(1)
    else:
        target = resp.json()
        got_target_from_stack = True

    if not target:
        print(
            "Error: No reply target. No pending messages to reply to.", file=sys.stderr
        )
        sys.exit(1)
    target_endpoint = target.get("sender_endpoint")
    target_uds_path = target.get("sender_uds_path")
    task_id = target.get("sender_task_id")  # May be None
    receiver_task_id = target.get("receiver_task_id")

    if not target_endpoint and not target_uds_path:
        print("Error: Reply target has no endpoint", file=sys.stderr)
        sys.exit(1)

    extra_metadata: dict[str, object] | None = None
    fail_error: dict[str, str] | None = None
    if fail_reason:
        fail_error = {"code": ERROR_CODE_REPLY_FAILED, "message": message}
        extra_metadata = {
            _REPLY_STATUS_METADATA_KEY: "failed",
            _REPLY_ERROR_METADATA_KEY: fail_error,
            _REPLY_ARTIFACTS_METADATA_KEY: [],
        }
    # receiver_task_id may be absent in legacy reply-stack entries;
    # skip local reply recording - _maybe_mark_missing_reply handles this case.
    if receiver_task_id:
        local_payload: dict[str, object] = {"message": message}
        if fail_reason:
            local_payload["status"] = "failed"
            local_payload["error"] = fail_error
        try:
            local_resp = requests.post(
                f"{my_endpoint}/tasks/{receiver_task_id}/reply",
                json=local_payload,
                timeout=5,
            )
        except requests.RequestException as e:
            print(f"Error: Failed to record local reply: {e}", file=sys.stderr)
            sys.exit(1)
        if local_resp.status_code != 200:
            print(
                f"Error: Failed to record local reply: HTTP {local_resp.status_code}",
                file=sys.stderr,
            )
            sys.exit(1)

    # Send reply using A2AClient (prefer UDS if available)
    # sender_info is guaranteed to be dict here (str case exits above)
    client = A2AClient()
    reg = AgentRegistry()
    original_status = _set_sending_reply_status(reg, my_agent_id)
    try:
        result = client.send_to_local(
            endpoint=target_endpoint or "http://localhost",
            message=message,
            priority=3,  # Normal priority for replies
            sender_info=sender_info,
            response_mode="silent",  # Reply doesn't expect a reply back
            in_reply_to=task_id,
            uds_path=target_uds_path or None,
            extra_metadata=extra_metadata,
        )
    finally:
        _restore_sending_reply_status(reg, my_agent_id, original_status)

    if not result:
        print("Error: Failed to send reply", file=sys.stderr)
        sys.exit(1)

    # Only pop from stack after successful send
    if got_target_from_stack:
        pop_url = f"{my_endpoint}/reply-stack/pop"
        if to_sender:
            pop_url += f"?sender_id={to_sender}"
        with contextlib.suppress(requests.RequestException):
            requests.get(pop_url, timeout=5)

    # Clear persisted fallback target after successful send
    if my_agent_id:
        clear_reply_target(my_agent_id)

    # Display target info (prefer UDS path if no HTTP endpoint)
    target_short = _get_target_display_name(target_endpoint, target_uds_path)
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
        "--priority", type=int, default=3, help="Priority (1-5, default: 3)"
    )
    p_send.add_argument(
        "--from",
        dest="sender",
        help="Sender Agent ID (auto-detected from env if not specified)",
    )
    _add_response_mode_flags(p_send)
    p_send.add_argument(
        "message", nargs="?", default=None, help="Content of the message"
    )
    _add_message_source_flags(p_send)
    p_send.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Send even if target is in a different working directory",
    )
    p_send.add_argument(
        "--local-only",
        dest="local_only",
        action="store_true",
        default=False,
        help=(
            "Restrict target resolution to agents in the caller's working "
            "directory. Used by workflow runner so bare-type targets never "
            "fall back to agents in other directories."
        ),
    )

    # broadcast command
    p_broadcast = subparsers.add_parser(
        "broadcast",
        help="Send message to all agents in current working directory",
    )
    p_broadcast.add_argument(
        "--priority", type=int, default=1, help="Priority (1-5, 5=Interrupt)"
    )
    p_broadcast.add_argument(
        "--from",
        dest="sender",
        help="Sender Agent ID (auto-detected from env if not specified)",
    )
    _add_response_mode_flags(p_broadcast)
    p_broadcast.add_argument(
        "message", nargs="?", default=None, help="Content of the message"
    )
    _add_message_source_flags(p_broadcast)

    # reply command - simplified reply to last message
    p_reply = subparsers.add_parser("reply", help="Reply to the last received message")
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
    p_reply.add_argument(
        "--fail",
        dest="fail",
        help="Send a failed reply with the given reason instead of a normal text reply",
    )
    p_reply.add_argument("message", nargs="?", default="", help="Reply message content")

    args = parser.parse_args()

    commands = {
        "list": cmd_list,
        "cleanup": cmd_cleanup,
        "send": cmd_send,
        "broadcast": cmd_broadcast,
        "reply": cmd_reply,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
