"""
Google A2A Protocol Compatibility Layer

This module provides Google A2A protocol compatible endpoints while
maintaining Synapse A2A's unique PTY-wrapping capabilities.

Google A2A Spec: https://a2a-protocol.org/latest/specification/
"""

import asyncio
import hashlib
import json
import logging
import os
import sys
import threading
import time
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from synapse._pty_sanitize import (
    printable_len as _printable_len,
)
from synapse._pty_sanitize import (
    strip_control_bytes,
    tail_printable,
)
from synapse.a2a_client import get_client
from synapse.auth import require_auth
from synapse.config import (
    AGENT_READY_TIMEOUT,
    CONTEXT_RECENT_SIZE,
)
from synapse.controller import TerminalController
from synapse.error_detector import detect_task_status
from synapse.history import HistoryManager
from synapse.long_message import (
    LongMessageStore,
    format_file_reference,
    get_long_message_store,
)
from synapse.output_parser import (
    SENT_MESSAGE_COMPARE_LEN,
    clean_copilot_response,
    parse_output,
)
from synapse.paths import get_history_db_path
from synapse.registry import AgentRegistry
from synapse.reply_stack import SenderInfo as ReplyStackSenderInfo
from synapse.reply_stack import get_reply_stack
from synapse.reply_target import save_reply_target
from synapse.status import (
    PROCESSING,
    RATE_LIMITED,
    READY,
    WAITING,
    WAITING_FOR_INPUT,
)
from synapse.terminal_jump import create_panes, detect_terminal_app
from synapse.utils import (
    extract_file_parts,
    extract_text_from_parts,
    format_a2a_message,
    format_file_parts_for_pty,
    get_iso_timestamp,
)
from synapse.webhooks import (
    dispatch_event,
    get_webhook_registry,
)

if TYPE_CHECKING:
    from synapse.a2a_client import ExternalAgent
    from synapse.transport import MessageTransport

# Re-export data models for backward compatibility
from synapse.a2a_models import (  # noqa: F401, E402
    AgentCapabilities,
    AgentCard,
    AgentSkill,
    Artifact,
    CreateTaskRequest,
    CreateTaskResponse,
    DataPart,
    FilePart,
    HistoryUpdateRequest,
    Message,
    Part,
    SendMessageRequest,
    SendMessageResponse,
    Task,
    TaskErrorModel,
    TaskState,
    TextPart,
)
from synapse.task_store import (  # noqa: F401, E402
    _EXPLICIT_REPLY_RECORDED_METADATA_KEY,
    ERROR_CODE_MISSING_REPLY,
    ERROR_CODE_REPLY_FAILED,
    TaskStore,
    task_store,
)

# ============================================================
# Helper Functions (Refactored)
# ============================================================


@dataclass
class SenderInfo:
    """Extracted sender information from metadata."""

    sender_id: str | None = None
    sender_name: str | None = None
    sender_endpoint: str | None = None
    sender_uds_path: str | None = None
    sender_task_id: str | None = None
    receiver_task_id: str | None = None

    def has_reply_target(self) -> bool:
        """Check if there's enough info to send a reply."""
        return bool(self.sender_id and (self.sender_endpoint or self.sender_uds_path))

    def to_reply_stack_entry(self) -> ReplyStackSenderInfo:
        """Convert to SenderInfo TypedDict for reply stack storage."""
        entry: ReplyStackSenderInfo = {}
        if self.sender_id:
            entry["sender_id"] = self.sender_id
        if self.sender_endpoint:
            entry["sender_endpoint"] = self.sender_endpoint
        if self.sender_uds_path:
            entry["sender_uds_path"] = self.sender_uds_path
        if self.sender_task_id:
            entry["sender_task_id"] = self.sender_task_id
        if self.receiver_task_id:
            entry["receiver_task_id"] = self.receiver_task_id
        return entry


def _extract_sender_info(metadata: dict[str, Any] | None) -> SenderInfo:
    """Extract sender info from request/task metadata.

    Args:
        metadata: The metadata dict containing sender info

    Returns:
        SenderInfo dataclass with extracted values
    """
    if not metadata:
        return SenderInfo()

    sender = metadata.get("sender", {})
    return SenderInfo(
        sender_id=sender.get("sender_id"),
        sender_name=sender.get("sender_name"),
        sender_endpoint=sender.get("sender_endpoint"),
        sender_uds_path=sender.get("sender_uds_path"),
        sender_task_id=metadata.get("sender_task_id"),
        receiver_task_id=metadata.get("receiver_task_id"),
    )


def _dispatch_task_event(event_type: str, payload: dict[str, Any]) -> None:
    """Dispatch a task event asynchronously via webhook.

    Args:
        event_type: Event type (e.g., "task.completed", "task.failed")
        payload: Event payload dict
    """
    registry = get_webhook_registry()
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # Called from sync callback threads (no running event loop).
        # Run dispatch in a dedicated daemon thread to avoid dropping events.
        def _run_in_thread() -> None:
            try:
                asyncio.run(dispatch_event(registry, event_type, payload))
            except Exception:
                logger.exception(
                    "Failed to dispatch webhook event in thread: %s", event_type
                )

        threading.Thread(target=_run_in_thread, daemon=True).start()
        return

    loop.create_task(dispatch_event(registry, event_type, payload))


def _convert_agent_to_info(agent: "ExternalAgent") -> "ExternalAgentInfo":
    """Convert ExternalAgent object to ExternalAgentInfo response model.

    Args:
        agent: ExternalAgent object from A2A client

    Returns:
        ExternalAgentInfo for API response
    """
    # ExternalAgentInfo is defined later in this file
    return ExternalAgentInfo(
        name=agent.name,
        alias=agent.alias,
        url=agent.url,
        description=agent.description,
        capabilities=agent.capabilities,
        skills=agent.skills,
        added_at=agent.added_at,
        last_seen=agent.last_seen,
    )


def _resolve_response_mode(metadata: dict) -> str:
    """Resolve response mode from metadata, handling backward compatibility.

    Accepts both new ``response_mode`` key and legacy ``response_expected``
    boolean.  Falls back to ``"notify"`` when neither key is present.
    """
    if "response_mode" in metadata:
        return str(metadata["response_mode"])
    # Backward compat: map old boolean to new mode
    if "response_expected" in metadata:
        return "wait" if metadata["response_expected"] else "silent"
    return "notify"


def _prepare_pty_message(
    store: LongMessageStore,
    task_id: str,
    content: str,
    response_mode: str = "silent",
    sender_id: str | None = None,
    sender_name: str | None = None,
) -> tuple[str, bool]:
    """Prepare message content for PTY, storing to file if too long.

    If the content exceeds the TUI character limit, it is stored in a file
    and a reference message is returned instead.

    Args:
        store: LongMessageStore instance
        task_id: Task ID for file naming
        content: Original message content
        response_mode: Response mode ("wait", "notify", or "silent")
        sender_id: Sender agent ID for file reference
        sender_name: Sender display name for file reference

    Returns:
        Tuple of (pty_text, used_file_storage) where pty_text is the content
        to send to PTY and used_file_storage indicates if a file was created.
    """
    if not store.needs_file_storage(content):
        return content, False

    file_path = store.store_message(task_id, content)
    reference = format_file_reference(
        file_path, response_mode, sender_id=sender_id, sender_name=sender_name
    )
    logger.info(f"Long message stored to {file_path} for task {task_id[:8]}")
    return reference, True


def map_synapse_status_to_a2a(synapse_status: str) -> TaskState:
    """Map Synapse status to Google A2A task state"""
    mapping: dict[str, TaskState] = {
        "STARTING": "submitted",
        "BUSY": "working",
        WAITING: "input_required",
        WAITING_FOR_INPUT: "input_required",
        "READY": "completed",
        "DONE": "completed",
        "NOT_STARTED": "submitted",
    }
    return mapping.get(synapse_status, "working")


def _format_artifact_text(artifact: "Artifact", use_markdown: bool = False) -> str:
    """Format an artifact as text for history or response.

    Args:
        artifact: The Artifact to format
        use_markdown: If True, format code blocks with markdown fences

    Returns:
        Formatted text representation of the artifact
    """
    if artifact.type == "code":
        code_data = artifact.data if isinstance(artifact.data, dict) else {}
        language = code_data.get("metadata", {}).get("language", "text")
        content = code_data.get("content", str(artifact.data))
        prefix = f"```{language}\n" if use_markdown else f"[Code: {language}]\n"
        suffix = "\n```" if use_markdown else ""
        return f"{prefix}{content}{suffix}"

    if artifact.type == "text":
        if isinstance(artifact.data, str):
            return artifact.data
        return str(artifact.data.get("content", artifact.data))

    return f"[{artifact.type}] {artifact.data}"


def _save_task_to_history(
    task: "Task", agent_id: str, agent_name: str, task_status: str
) -> None:
    """Save completed task to history database.

    Args:
        task: The completed Task object
        agent_id: Agent ID that processed the task
        agent_name: Agent name (claude, gemini, codex)
        task_status: Final status (completed, failed, canceled)
    """
    if not history_manager.enabled:
        return

    try:
        input_text = ""
        if task.message and task.message.parts:
            input_text = extract_text_from_parts(task.message.parts)

        output_parts = [_format_artifact_text(a) for a in task.artifacts]
        output_text = "\n".join(output_parts) if output_parts else ""

        metadata = task.metadata.copy() if task.metadata else {}
        if task.error:
            metadata["error"] = {
                "code": task.error.code,
                "message": task.error.message,
                "data": task.error.data,
            }

        # Token tracking: parse usage from output (non-blocking)
        try:
            from synapse.token_parser import parse_tokens

            token_usage = parse_tokens(agent_name, output_text)
            if token_usage:
                metadata["tokens"] = token_usage.to_dict()
        except Exception:
            pass  # Never block history save

        history_manager.save_observation(
            task_id=task.id,
            agent_name=agent_name,
            session_id=task.context_id or "default",
            input_text=input_text,
            output_text=output_text,
            status=task_status,
            metadata=metadata,
        )
    except Exception as e:
        print(f"Warning: Failed to save task to history: {e}", file=sys.stderr)


# (Models moved to synapse.a2a_models — re-exported above)


# (TaskStore moved to synapse.task_store — re-exported above)

# Global history manager
_history_db_path = get_history_db_path()
history_manager = HistoryManager.from_env(db_path=_history_db_path)

# Logger for A2A operations
logger = logging.getLogger(__name__)

_CONTEXT_START_METADATA_KEY = "_context_start"
_SENT_MESSAGE_METADATA_KEY = "_sent_message"
_REPLY_ARTIFACTS_METADATA_KEY = "reply_artifacts"
_REPLY_STATUS_METADATA_KEY = "reply_status"
_REPLY_ERROR_METADATA_KEY = "reply_error"
# Permission escalation metadata — populated by the child when it notifies
# its parent that a task is stuck in input_required. Used by the Approval
# Gate on the parent side to auto-approve/deny or escalate to human. See
# synapse/approval_gate.py and issue #571.
_PERMISSION_ESCALATION_METADATA_KEY = "permission_escalation"

# Permission notification dedupe guards (see #582, #586). Notifications
# are keyed by (task_id + sanitised pty_context tail) hash; the same
# hash is suppressed within _PERMISSION_NOTIFICATION_MIN_INTERVAL_SECONDS.
# The window also rate-limits distinct hashes to protect against
# WAITING→READY→WAITING oscillation from streaming output.
_PERMISSION_NOTIFICATION_MIN_INTERVAL_SECONDS = 5.0
_PERMISSION_CONTEXT_FALLBACK = "[permission context unavailable]"
_PERMISSION_CONTEXT_MIN_PRINTABLE = 10

# Allowed values for `waiting_source` in permission metadata. Mirrors
# the literals emitted by IdleDetector; centralised so a single typo
# can't silently downgrade a "regex" detection to "none".
_WAITING_SOURCE_VALUES = frozenset({"regex", "heuristic", "none"})


def _load_reply_artifacts(metadata: dict[str, Any]) -> list[Artifact] | None:
    """Deserialize structured reply artifacts from metadata."""
    raw_artifacts = metadata.get(_REPLY_ARTIFACTS_METADATA_KEY)
    if raw_artifacts is None:
        return None
    return [Artifact.model_validate(artifact) for artifact in raw_artifacts]


def _load_reply_error(metadata: dict[str, Any]) -> TaskErrorModel | None:
    """Deserialize structured reply error from metadata."""
    raw_error = metadata.get(_REPLY_ERROR_METADATA_KEY)
    if raw_error is None:
        return None
    result: TaskErrorModel = TaskErrorModel.model_validate(raw_error)
    return result


def _is_trivial_reply_text(text: str) -> bool:
    """Return True for PTY noise that should not become a reply artifact."""
    stripped = text.strip()
    if not stripped:
        return True
    if len(stripped) > 3:
        return False
    return all(not ch.isalnum() for ch in stripped)


def _has_meaningful_response_content(text: str) -> bool:
    """Return True when cleaned response text contains usable content."""
    if _is_trivial_reply_text(text):
        return False
    segments = parse_output(text)
    if not segments:
        return False
    return any(
        seg.type != "text" or not _is_trivial_reply_text(seg.content)
        for seg in segments
    )


def _response_content_score(text: str) -> int:
    """Score cleaned response text to choose richer context over trivial deltas."""
    if not text:
        return 0
    segments = parse_output(text)
    if not segments:
        return 0
    score = 0
    for seg in segments:
        if seg.type == "text":
            stripped = seg.content.strip()
            if not stripped:
                continue
            if len(stripped) <= 3 and "\n" not in stripped:
                score += len(stripped)
            else:
                score += len(stripped) + 20
        else:
            score += len(seg.content.strip()) + 40
    return score


def _strip_trivial_trailing_lines(text: str) -> str:
    """Drop trailing PTY-noise lines when earlier lines contain the real reply."""
    lines = text.splitlines()
    while len(lines) > 1:
        stripped = lines[-1].strip()
        if not stripped:
            lines.pop()
            continue
        if len(stripped) <= 3 and "\n" not in stripped:
            lines.pop()
            continue
        if _is_trivial_reply_text(stripped):
            lines.pop()
            continue
        break
    return "\n".join(lines).strip()


def _select_response_context(
    full_context: str, recent_context: str, metadata: dict[str, Any]
) -> str:
    """Choose the best response context, falling back when delta is only PTY noise."""
    sent_msg = metadata.get(_SENT_MESSAGE_METADATA_KEY)
    candidates: list[str] = []
    context_start = metadata.get(_CONTEXT_START_METADATA_KEY)
    if isinstance(context_start, int) and 0 <= context_start <= len(full_context):
        delta = full_context[context_start:]
        if delta.strip():
            candidates.append(delta)
    for candidate in (recent_context, full_context):
        if candidate and candidate not in candidates:
            candidates.append(candidate)

    cleaned_candidates = [
        _strip_trivial_trailing_lines(clean_copilot_response(candidate, sent_msg))
        for candidate in candidates
        if candidate
    ]
    best_cleaned = ""
    best_score = 0
    for cleaned in cleaned_candidates:
        if not _has_meaningful_response_content(cleaned):
            continue
        score = _response_content_score(cleaned)
        if score > best_score:
            best_cleaned = cleaned
            best_score = score
    if best_cleaned:
        return best_cleaned
    return cleaned_candidates[0] if cleaned_candidates else ""


def _find_active_working_task() -> Task | None:
    """Return the current active working task, if any.

    Only considers incoming tasks (those being executed by this agent).
    Outgoing wait/notify tasks (direction=outgoing) are excluded since they
    represent tasks *sent* to other agents, not work this agent is doing.
    """
    for task in task_store.list_tasks():
        if task.status == "working":
            meta = task.metadata or {}
            if meta.get("direction") == "outgoing":
                continue
            return task
    return None


def _mark_missing_reply(task: Task) -> Task:
    """Fail a wait/notify task when no explicit reply was recorded."""
    updated = task_store.mark_missing_reply_if_unreplied(task.id)
    return updated or task


def _maybe_mark_missing_reply(task: Task, resp_mode: str) -> Task:
    """Mark task as missing-reply if it's a wait/notify without explicit reply.

    Re-reads metadata from the task store to avoid TOCTOU races with the
    explicit reply endpoint.
    """
    if resp_mode not in ("wait", "notify"):
        return task
    updated = task_store.mark_missing_reply_if_unreplied(task.id)
    return updated or task


async def _send_response_to_sender(
    task: Task,
    sender_endpoint: str,
    self_agent_id: str,
    sender_task_id: str | None = None,
    *,
    self_endpoint: str | None = None,
    self_agent_type: str | None = None,
) -> bool:
    """
    Send task response back to the original sender.

    This implements the A2A response mechanism where completed tasks
    are sent back to the sender_endpoint specified in metadata.

    Args:
        task: The completed task with artifacts
        sender_endpoint: The endpoint URL of the sender agent
        self_agent_id: This agent's ID for sender identification
        sender_task_id: The task ID on the sender's server (for in_reply_to)
        self_endpoint: The child's own endpoint (e.g. http://localhost:8126),
            used to populate the structured permission_escalation metadata
            so the parent's Approval Gate can call back directly.
        self_agent_type: The child's profile type (e.g. ``"codex"``), used
            by the parent's Approval Gate to apply per-profile policy.

    Returns:
        True if response was sent successfully, False otherwise
    """
    response_parts = [
        {"type": "text", "text": _format_artifact_text(a, use_markdown=True)}
        for a in task.artifacts
    ]

    if not response_parts:
        response_parts.append(
            {
                "type": "text",
                "text": f"[Task {task.id[:8]} completed with status: {task.status}]",
            }
        )

    # Build A2A request payload
    # Use sender_task_id (the task ID on sender's server) for in_reply_to
    # This ensures the reply is correctly routed back to the sender's waiting task
    reply_to_id = sender_task_id if sender_task_id else task.id
    response_metadata: dict[str, Any] = {
        "sender": {
            "sender_id": self_agent_id,
        },
        "response_mode": "silent",  # Response to response not needed
        "in_reply_to": reply_to_id,  # Reference to sender's task
        _REPLY_ARTIFACTS_METADATA_KEY: [
            artifact.model_dump(mode="json") for artifact in task.artifacts
        ],
        _REPLY_STATUS_METADATA_KEY: task.status,
    }
    # If the child is notifying the parent about a stuck input_required task,
    # include a structured escalation block so the parent's Approval Gate can
    # decide/apply without having to parse the artifact text. The legacy
    # artifact-based notification still ships alongside, so human operators
    # and older parents see the same text as before.
    if task.status == "input_required" and self_endpoint:
        permission_block = (task.metadata or {}).get("permission")
        if isinstance(permission_block, dict):
            escalation: dict[str, Any] = {
                "task_id": task.id,
                "child_endpoint": self_endpoint.rstrip("/"),
                "child_agent_id": self_agent_id,
                "permission": dict(permission_block),
            }
            if self_agent_type:
                escalation["child_agent_type"] = self_agent_type
            response_metadata[_PERMISSION_ESCALATION_METADATA_KEY] = escalation
    payload = {
        "message": {"role": "agent", "parts": response_parts},
        "metadata": response_metadata,
    }
    if task.error is not None:
        response_metadata[_REPLY_ERROR_METADATA_KEY] = task.error.model_dump(
            mode="json"
        )

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Send to sender's /tasks/send endpoint
            url = f"{sender_endpoint}/tasks/send"
            response = await client.post(url, json=payload)
            response.raise_for_status()
            logger.info(f"Response sent to {sender_endpoint} for task {task.id[:8]}")
            return True
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        logger.warning(f"Failed to send response to {sender_endpoint}: HTTP {status}")
        return False
    except httpx.RequestError as e:
        logger.warning(f"Failed to send response to {sender_endpoint}: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error sending response to {sender_endpoint}: {e}")
        return False


async def _notify_sender_completion(
    task: Task,
    sender_endpoint: str,
    sender_uds_path: str | None = None,
    sender_task_id: str | None = None,
    status: str | None = None,
) -> bool:
    """Notify sender to update history for no-response tasks.

    Uses UDS first (when available), then falls back to HTTP.
    Best effort: failures are logged and return False.
    """
    callback_task_id = sender_task_id or task.id
    callback_status = status or task.status

    output_parts = [_format_artifact_text(a) for a in task.artifacts]
    output_summary = "\n".join(output_parts) if output_parts else None

    payload = {
        "task_id": callback_task_id,
        "status": callback_status,
        "output_summary": output_summary,
    }

    # Try UDS first, fall through to HTTP on failure
    if sender_uds_path and os.path.exists(sender_uds_path):
        try:
            transport = httpx.AsyncHTTPTransport(uds=sender_uds_path)
            async with httpx.AsyncClient(transport=transport, timeout=10.0) as client:
                resp = await client.post(
                    "http://localhost/history/update", json=payload
                )
                resp.raise_for_status()
                logger.info(
                    "Completion callback sent via UDS for task %s",
                    callback_task_id[:8],
                )
                return True
        except httpx.HTTPError as e:
            logger.warning(
                "UDS completion callback failed for %s, falling back to HTTP: %s",
                callback_task_id[:8],
                e,
            )

    # HTTP fallback
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            url = f"{sender_endpoint}/history/update"
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            logger.info(
                "Completion callback sent to %s for task %s",
                sender_endpoint,
                callback_task_id[:8],
            )
            return True
    except httpx.HTTPStatusError as e:
        logger.warning(
            "Failed to send completion callback to %s: HTTP %s",
            sender_endpoint,
            e.response.status_code,
        )
    except httpx.RequestError as e:
        logger.warning(
            "Failed to send completion callback to %s: %s", sender_endpoint, e
        )
    except Exception as e:
        logger.error(
            "Unexpected completion callback error to %s: %s", sender_endpoint, e
        )
    return False


# ============================================================
# External Agent Models
# ============================================================


class DiscoverAgentRequest(BaseModel):
    """Request to discover an external agent"""

    url: str
    alias: str | None = None


class ExternalAgentInfo(BaseModel):
    """External agent information"""

    name: str
    alias: str
    url: str
    description: str = ""
    capabilities: dict[str, Any] = {}
    skills: list[dict[str, Any]] = []
    added_at: str = ""
    last_seen: str | None = None


class SendExternalMessageRequest(BaseModel):
    """Request to send message to external agent"""

    message: str
    wait_for_completion: bool = False
    timeout: int = 60


class ExternalTaskResponse(BaseModel):
    """Response from external agent task"""

    id: str
    status: str
    artifacts: list[dict[str, Any]] = []


# ============================================================
# Request / Response models for Team & Spawn endpoints
# ============================================================


class TeamStartRequest(BaseModel):
    """Request to start multiple agents with split panes."""

    agents: list[str] = Field(..., min_length=1)
    layout: Literal["split", "horizontal", "vertical"] = "split"
    terminal: str | None = None
    tool_args: list[str] | None = None


class AgentStartStatus(BaseModel):
    """Status of a single agent start attempt."""

    agent_type: str
    status: str  # "submitted" | "failed"
    reason: str | None = None


class TeamStartResponse(BaseModel):
    """Response after starting a team of agents."""

    started: list[AgentStartStatus]
    terminal_used: str | None = None


class SpawnRequest(BaseModel):
    """Request to spawn a single agent in a new terminal pane."""

    profile: str = Field(..., description="Agent profile (claude, gemini, etc.)")
    port: int | None = None
    name: str | None = None
    role: str | None = None
    skill_set: str | None = None
    terminal: str | None = None
    tool_args: list[str] | None = None
    worktree: str | bool | None = None


class SpawnResponse(BaseModel):
    """Response after spawning an agent."""

    agent_id: str | None = None
    port: int | None = None
    terminal_used: str | None = None
    status: str  # "submitted" | "failed"
    reason: str | None = None
    worktree_path: str | None = None
    worktree_branch: str | None = None


# ============================================================
# Shared Memory Helpers
# ============================================================


def _memory_broadcast_notify_api(key: str) -> None:
    """Broadcast a notification about a saved memory to other agents (API-side)."""
    import os

    from synapse.a2a_client import A2AClient
    from synapse.registry import AgentRegistry

    try:
        registry = AgentRegistry()
        client = A2AClient()
        agents = registry.list_agents()
        my_id = os.environ.get("SYNAPSE_AGENT_ID", "")
        for agent_id, agent_info in agents.items():
            if agent_id == my_id:
                continue
            name = agent_info.get("name") or agent_id
            endpoint = agent_info.get("endpoint", "")
            if not endpoint:
                logger.warning("Memory notify skipped for %s: no endpoint", name)
                continue
            try:
                task = client.send_to_local(
                    endpoint=endpoint,
                    message=f"[Memory updated] Key '{key}' was saved. Use `synapse memory show {key}` to view.",
                    priority=1,
                    response_mode="silent",
                    sender_agent_id=my_id,
                    target_agent_id=agent_id,
                )
                if task is None:
                    logger.warning("Memory notify failed for %s: no response", name)
                else:
                    logger.info("Memory notify sent to %s for key '%s'", name, key)
            except Exception as e:
                logger.warning("Memory notify failed for %s: %s", name, e)
    except Exception as e:
        logger.warning("Memory broadcast failed: %s", e)


# ============================================================
# A2A Router Factory
# ============================================================


def create_a2a_router(
    controller: TerminalController | None,
    agent_type: str,
    port: int,
    submit_seq: str = "\n",
    agent_id: str | None = None,
    registry: AgentRegistry | None = None,
    transport: "MessageTransport | None" = None,
    approve_response: str = "",
    deny_response: str = "",
) -> APIRouter:
    """
    Create Google A2A compatible router.

    Args:
        controller: TerminalController instance
        agent_type: Agent type (claude, codex, gemini, etc.)
        port: Server port
        submit_seq: Submit sequence for the CLI
        agent_id: Unique agent ID (e.g., synapse-claude-8100)
        registry: AgentRegistry instance for discovering other agents
        transport: Message transport for delivery (default: PTYTransport)
        approve_response: PTY response to accept a runtime permission prompt
        deny_response: PTY response to reject a runtime permission prompt

    Returns:
        FastAPI APIRouter with A2A endpoints
    """
    # Generate agent_id if not provided
    if agent_id is None:
        agent_id = f"synapse-{agent_type}-{port}"

    # Build default PTY transport if none provided
    if transport is None and controller is not None:
        from synapse.transport import PTYTransport

        transport = PTYTransport(controller, get_long_message_store(), submit_seq)
    router = APIRouter(tags=["Google A2A Compatible"])

    def _run_async_from_sync(coro: Any) -> None:
        """Dispatch an async coroutine from a sync callback thread."""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            asyncio.run_coroutine_threadsafe(coro, loop)
        else:
            asyncio.run(coro)

    def _resolve_pty_context(task_metadata: dict[str, Any]) -> str:
        """Produce a sanitised, length-capped context tail for notifications.

        Order of preference:
        1. controller.get_rendered_context() if available (pyte-rendered)
        2. controller.get_context() (already ANSI-stripped in most cases)
        3. task metadata current_task_preview
        4. task metadata _sent_message (first 200 chars)
        5. a fixed placeholder

        Control-byte sanitisation runs after each source so a context
        full of CSI escapes or line-overwrite bytes cannot slip through.
        """
        sources: list[str] = []
        if controller is not None:
            get_rendered = getattr(controller, "get_rendered_context", None)
            if callable(get_rendered):
                try:
                    value = get_rendered()
                    if isinstance(value, str):
                        sources.append(value)
                except Exception as exc:
                    logger.debug("get_rendered_context failed: %s", exc)
            try:
                value = controller.get_context()
                if isinstance(value, str):
                    sources.append(value)
            except Exception as exc:
                logger.debug("controller.get_context failed: %s", exc)

        for raw in sources:
            tail = tail_printable(raw, limit=512)
            if tail and _printable_len(tail) >= _PERMISSION_CONTEXT_MIN_PRINTABLE:
                return tail

        preview = task_metadata.get("current_task_preview")
        if isinstance(preview, str):
            cleaned_preview = strip_control_bytes(preview).strip()
            if (
                cleaned_preview
                and _printable_len(cleaned_preview) >= _PERMISSION_CONTEXT_MIN_PRINTABLE
            ):
                return cleaned_preview[:512]

        sent = task_metadata.get(_SENT_MESSAGE_METADATA_KEY)
        if isinstance(sent, str):
            cleaned_sent = strip_control_bytes(sent).strip()[:200]
            if (
                cleaned_sent
                and _printable_len(cleaned_sent) >= _PERMISSION_CONTEXT_MIN_PRINTABLE
            ):
                return cleaned_sent

        return _PERMISSION_CONTEXT_FALLBACK

    def _build_permission_metadata(
        task_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        metadata = task_metadata or {}
        raw_confidence = (
            getattr(controller, "last_waiting_confidence", None)
            if controller is not None
            else None
        )
        if not isinstance(raw_confidence, (int, float)):
            raw_confidence = metadata.get("waiting_confidence", 0.0)
        try:
            waiting_confidence = max(0.0, min(1.0, float(raw_confidence)))
        except (TypeError, ValueError):
            waiting_confidence = 0.0

        raw_source = (
            getattr(controller, "last_waiting_source", None)
            if controller is not None
            else None
        )
        if raw_source not in _WAITING_SOURCE_VALUES:
            raw_source = metadata.get("waiting_source", "none")
        waiting_source = raw_source if raw_source in _WAITING_SOURCE_VALUES else "none"

        return {
            "pty_context": _resolve_pty_context(metadata),
            "agent_type": agent_type,
            "detected_at": time.time(),
            "waiting_confidence": waiting_confidence,
            "waiting_source": waiting_source,
        }

    def _build_permission_notification(task: Task) -> Task:
        permission = (task.metadata or {}).get("permission", {})
        approve_url = f"http://localhost:{port}/tasks/{task.id}/permission/approve"
        deny_url = f"http://localhost:{port}/tasks/{task.id}/permission/deny"
        notification_text = (
            f"[Task {task.id}] Status: {task.status}\n"
            f"Permission context: {permission.get('pty_context', '')}\n"
            f"Approve: POST {approve_url}\n"
            f"Deny: POST {deny_url}"
        )
        notification_task: Task = task.model_copy()
        notification_task.artifacts = [
            Artifact(type="text", data={"content": notification_text})
        ]
        return notification_task

    def _sync_registry_rate_limited_status(error_code: str | None) -> None:
        if error_code != RATE_LIMITED or registry is None or agent_id is None:
            return
        agent_info = registry.get_agent(agent_id)
        if agent_info and agent_info.get("status") in (
            PROCESSING,
            READY,
            WAITING_FOR_INPUT,
        ):
            registry.update_status(agent_id, RATE_LIMITED)

    def _finalize_working_task(
        task_id: str, full_context: str, recent_context: str
    ) -> Task | None:
        """Detect completion status, add artifacts, save history, and clear preview.

        Shared by ``_on_status_change`` (sync callback) and ``get_task`` (async
        endpoint) to avoid duplicating the finalization pipeline.

        Returns:
            The updated Task after finalization, or None if the task vanished.
        """
        task = task_store.claim_finalization(task_id)
        if not task:
            return None

        metadata = task.metadata or {}
        response_context = _select_response_context(
            full_context, recent_context, metadata
        )
        output_summary = response_context[:200]

        status, error = detect_task_status(response_context)
        if status == "failed" and error:
            task_store.set_error(
                task_id,
                TaskErrorModel(code=error.code, message=error.message, data=error.data),
            )
            _dispatch_task_event(
                "task.failed",
                {
                    "task_id": task_id,
                    "error": {"code": error.code, "message": error.message},
                },
            )
            _sync_registry_rate_limited_status(error.code)
        else:
            task_store.update_status(task_id, "completed")
            _dispatch_task_event("task.completed", {"task_id": task_id})

        # Add artifacts from parsed output
        if response_context and status != "failed":
            segments = parse_output(response_context)
            if segments:
                meaningful_segments = [
                    seg
                    for seg in segments
                    if seg.type != "text" or not _is_trivial_reply_text(seg.content)
                ]
                for seg in meaningful_segments:
                    artifact_data: dict[str, Any] = {"content": seg.content}
                    if seg.metadata:
                        artifact_data["metadata"] = seg.metadata
                    task_store.add_artifact(
                        task_id, Artifact(type=seg.type, data=artifact_data)
                    )
            elif not _is_trivial_reply_text(response_context):
                task_store.add_artifact(
                    task_id, Artifact(type="text", data=response_context)
                )

        # Compound signal: clear task active to allow READY transition (#314)
        if controller:
            controller.clear_task_active()

        # Clear task preview in registry
        if registry and agent_id:
            registry.update_current_task(agent_id, None)

        # Save to history
        updated = task_store.get(task_id)
        if updated:
            _save_task_to_history(
                updated,
                agent_id=agent_id or "unknown",
                agent_name=agent_type or "unknown",
                task_status=updated.status,
            )
            if controller:
                controller.record_task_completed(
                    task_id=task_id,
                    duration=controller.task_duration_seconds(updated.created_at),
                    status=updated.status,
                    output_summary=output_summary,
                )

        return updated

    # Register controller callback for notify/wait completion detection.
    # When status transitions to READY or DONE, check working tasks.
    if controller:

        def _has_non_permission_input_required_task() -> bool:
            for task in task_store.list_tasks():
                if task.status != "input_required":
                    continue
                metadata = task.metadata or {}
                if not isinstance(metadata.get("permission"), dict):
                    return True
            return False

        def _has_only_terminal_tasks() -> bool:
            tasks = task_store.list_tasks()
            if not tasks:
                return False
            return all(
                task.status in ("completed", "failed", "canceled") for task in tasks
            )

        def _is_permission_waiting_status(new_status: str) -> bool:
            if new_status == WAITING:
                return True
            if getattr(controller, "status", None) == WAITING:
                return True
            waiting_source = getattr(controller, "last_waiting_source", "none")
            return waiting_source not in (None, "", "none")

        def _sync_registry_input_wait_status(new_status: str) -> None:
            if registry is None or agent_id is None:
                return
            if _is_permission_waiting_status(new_status):
                registry.update_status(agent_id, WAITING)
                return
            if _has_non_permission_input_required_task():
                registry.update_status(agent_id, WAITING_FOR_INPUT)
            if _has_only_terminal_tasks():
                agent_info = registry.get_agent(agent_id)
                if agent_info and agent_info.get("status") in (
                    "PROCESSING",
                    WAITING_FOR_INPUT,
                ):
                    registry.update_status(agent_id, "READY")

        def _on_status_change(old: str, new: str) -> None:
            if new == WAITING:
                for task in task_store.list_tasks():
                    if task.status != "working":
                        continue
                    metadata = task.metadata or {}
                    permission = _build_permission_metadata(metadata)
                    now = time.time()
                    digest = hashlib.sha256(
                        f"{task.id}\0{permission['pty_context']}".encode()
                    ).hexdigest()[:16]
                    raw_prior = metadata.get("permission")
                    prior: dict[str, Any] = (
                        raw_prior if isinstance(raw_prior, dict) else {}
                    )
                    prior_sent_at = prior.get("notification_sent_at") or 0.0
                    prior_hash = prior.get("notification_hash")
                    within_window = (
                        prior_sent_at
                        and now - prior_sent_at
                        < _PERMISSION_NOTIFICATION_MIN_INTERVAL_SECONDS
                    )
                    # Two-stage dedupe:
                    #   1. Within window → drop unconditionally (oscillation).
                    #   2. Same payload outside window → drop too, so a stuck
                    #      WAITING task showing the same prompt does not re-send.
                    if within_window or (prior_sent_at and prior_hash == digest):
                        continue

                    permission["notification_hash"] = digest
                    permission["notification_sent_at"] = now
                    permission["notifications_sent"] = (
                        int(prior.get("notifications_sent") or 0) + 1
                    )
                    task_store.update_metadata(task.id, "permission", permission)
                    updated = task_store.update_status(task.id, "input_required")
                    if not updated:
                        continue
                    si = _extract_sender_info(updated.metadata)
                    if not si.sender_endpoint:
                        continue
                    notification_task = _build_permission_notification(updated)
                    coro = _send_response_to_sender(
                        notification_task,
                        si.sender_endpoint,
                        agent_id or "unknown",
                        sender_task_id=si.sender_task_id,
                        self_endpoint=f"http://localhost:{port}",
                        self_agent_type=agent_type,
                    )
                    _run_async_from_sync(coro)
                _sync_registry_input_wait_status(new)
                return

            if old == WAITING:
                for task in task_store.list_tasks():
                    metadata = task.metadata or {}
                    if task.status == "input_required" and isinstance(
                        metadata.get("permission"), dict
                    ):
                        task_store.update_status(task.id, "working")
                # Fall through to the READY/DONE finalization below so
                # that WAITING → READY completes working tasks normally.

            _sync_registry_input_wait_status(new)

            if new not in ("READY", "DONE"):
                return
            for task in task_store.list_tasks():
                if task.status != "working":
                    continue
                tid = task.id
                metadata = task.metadata or {}
                resp_mode = _resolve_response_mode(metadata)
                if resp_mode == "silent":
                    # Silent tasks still need cleanup (#314)
                    context = controller.get_context()
                    recent_ctx = context[-CONTEXT_RECENT_SIZE:]
                    _finalize_working_task(tid, context, recent_ctx)
                    continue
                # Guard: only complete if still working
                current = task_store.get(tid)
                if not current or current.status != "working":
                    continue
                context = controller.get_context()
                recent_context = context[-CONTEXT_RECENT_SIZE:]

                updated = _finalize_working_task(tid, context, recent_context)

                # Send response back to sender (sync context — needs event loop dispatch)
                if updated:
                    si = _extract_sender_info(metadata)
                    if si.sender_endpoint:
                        if resp_mode in ("wait", "notify"):
                            updated = _maybe_mark_missing_reply(updated, resp_mode)
                        coro = _send_response_to_sender(
                            updated,
                            si.sender_endpoint,
                            agent_id or "unknown",
                            sender_task_id=si.sender_task_id,
                        )
                        _run_async_from_sync(coro)
            _sync_registry_input_wait_status(new)

        controller.on_status_change(_on_status_change)

    async def _send_task_message(
        request: SendMessageRequest, priority: int = 3
    ) -> SendMessageResponse:
        """Create a task and send message to controller with optional priority."""
        # Extract text from message parts
        text_content = extract_text_from_parts(request.message.parts)
        if not text_content:
            raise HTTPException(status_code=400, detail="No text content in message")

        file_parts = extract_file_parts(request.message.parts)
        attachments_txt = format_file_parts_for_pty(file_parts)
        pty_payload_text = (
            f"{text_content}\n\n{attachments_txt}" if attachments_txt else text_content
        )

        metadata = request.metadata or {}
        in_reply_to = metadata.get("in_reply_to")

        # Approval Gate (issue #571): if this incoming message carries a
        # structured permission escalation from a child, run it through the
        # gate before involving PTY or task_store write paths. The gate
        # auto-approves / denies / escalates based on policy so non-interactive
        # parents (workflow runners, nested spawns) never silently deadlock
        # on a child's permission prompt.
        escalation = metadata.get(_PERMISSION_ESCALATION_METADATA_KEY)
        if isinstance(escalation, dict) and escalation.get("task_id"):
            try:
                from synapse.approval_gate import (
                    decide_and_apply,
                    get_default_deduper,
                    request_from_a2a_metadata,
                )

                # ``request_from_a2a_metadata`` reads the permission block
                # from ``metadata["permission"]``, so wrap the dict in the
                # same shape the child's task_store writes rather than
                # unwrapping it (CodeRabbit review on #570).
                permission_block = escalation.get("permission") or {}
                gate_request = request_from_a2a_metadata(
                    task_id=str(escalation.get("task_id", "")),
                    endpoint=str(escalation.get("child_endpoint", "")),
                    target_agent_id=str(escalation.get("child_agent_id", "")),
                    target_agent_type=str(escalation.get("child_agent_type", "")),
                    metadata={"permission": dict(permission_block)},
                )
                # Dedupe guard: a child stuck on the same blocked-state
                # screen (e.g. usage-limit banner) mints a fresh task_id
                # every few seconds, so task-id dedupe on its own is not
                # enough. Suppress repeat escalations that share the same
                # (target_agent_id, pty_context) within the TTL window —
                # the original decision already did whatever was possible
                # for that screen. Record the duplicate as a completed
                # task so observers see the request was handled.
                if get_default_deduper().seen(gate_request):
                    logger.info(
                        "approval_gate: deduped repeat escalation task=%s on %s",
                        gate_request.task_id,
                        gate_request.target_agent_id,
                    )
                    escalation_task = task_store.create(
                        request.message,
                        request.context_id,
                        metadata={
                            **metadata,
                            "handled_by_approval_gate": True,
                            "approval_gate_deduped": True,
                        },
                    )
                    task_store.update_status(escalation_task.id, "completed")
                    updated_escalation = task_store.get(escalation_task.id)
                    if updated_escalation is None:
                        raise HTTPException(
                            status_code=500, detail="Escalation task disappeared"
                        )
                    return SendMessageResponse(task=updated_escalation)
                gate_decision, gate_ok = decide_and_apply(gate_request)
                logger.info(
                    "approval_gate: incoming escalation task=%s decision=%s ok=%s",
                    gate_request.task_id,
                    gate_decision.value,
                    gate_ok,
                )
                # Record an in-memory task for history/visibility, then return
                # without touching the PTY. We intentionally skip reply-stack
                # bookkeeping and controller writes because this was a
                # machine-to-machine escalation, not a user-visible message.
                escalation_task = task_store.create(
                    request.message,
                    request.context_id,
                    metadata={
                        **metadata,
                        "handled_by_approval_gate": True,
                        "approval_gate_decision": gate_decision.value,
                    },
                )
                task_store.update_status(
                    escalation_task.id,
                    "completed" if gate_ok else "failed",
                )
                updated_escalation = task_store.get(escalation_task.id)
                if updated_escalation is None:
                    raise HTTPException(
                        status_code=500, detail="Escalation task disappeared"
                    )
                return SendMessageResponse(task=updated_escalation)
            except HTTPException:
                raise
            except Exception as exc:  # broad: gate errors should not block PTY path
                # Don't fall through to the legacy PTY path: the legacy path
                # treats ``reply_status == "input_required"`` as a completed
                # reply (everything except ``"failed"`` is completed), which
                # silently confirms the child's blocked task back to the
                # waiting ``synapse send --wait`` subprocess. Record the
                # escalation as a failed local task instead so the gate
                # failure is visible and the sender's poll loop keeps waiting
                # for a real resolution (CodeRabbit review on #570).
                logger.warning(
                    "approval_gate: dispatch failed for incoming escalation: %s",
                    exc,
                )
                escalation_task = task_store.create(
                    request.message,
                    request.context_id,
                    metadata={
                        **metadata,
                        "handled_by_approval_gate": False,
                        "approval_gate_error": str(exc),
                    },
                )
                task_store.update_status(escalation_task.id, "failed")
                updated_escalation = task_store.get(escalation_task.id)
                if updated_escalation is None:
                    raise HTTPException(
                        status_code=500, detail="Escalation task disappeared"
                    ) from exc
                return SendMessageResponse(task=updated_escalation)

        if in_reply_to:
            # Support prefix match for short IDs from PTY display
            try:
                existing_task = task_store.get_by_prefix(in_reply_to)
            except ValueError as e:
                # Ambiguous prefix - multiple tasks match
                raise HTTPException(status_code=400, detail=str(e)) from e

            if not existing_task:
                raise HTTPException(status_code=404, detail="Task not found")

            # Use the full task ID for subsequent operations
            full_task_id = existing_task.id
            has_structured_reply = (
                _REPLY_ARTIFACTS_METADATA_KEY in metadata
                or _REPLY_STATUS_METADATA_KEY in metadata
                or _REPLY_ERROR_METADATA_KEY in metadata
            )
            reply_artifacts = _load_reply_artifacts(metadata)
            reply_status = metadata.get(_REPLY_STATUS_METADATA_KEY)
            reply_error = _load_reply_error(metadata)

            if reply_artifacts is not None:
                existing_task.artifacts = list(reply_artifacts)
                existing_task.updated_at = get_iso_timestamp()
            elif not has_structured_reply:
                task_store.add_artifact(
                    full_task_id, Artifact(type="text", data={"content": text_content})
                )

            if reply_status == "failed":
                if reply_error is not None:
                    task_store.set_error(full_task_id, reply_error)
                else:
                    task_store.update_status(full_task_id, "failed")
            else:
                task_store.update_status(full_task_id, "completed")

            # Write reply to PTY so the agent can see it and continue conversation
            if controller:
                reply_sender = _extract_sender_info(metadata)
                pty_text, used_file = _prepare_pty_message(
                    get_long_message_store(),
                    full_task_id,
                    pty_payload_text,
                    sender_id=reply_sender.sender_id,
                    sender_name=reply_sender.sender_name,
                )
                prefixed = format_a2a_message(
                    pty_text,
                    sender_id=reply_sender.sender_id if not used_file else None,
                    sender_name=reply_sender.sender_name if not used_file else None,
                )
                try:
                    written = controller.write(prefixed, submit_seq=submit_seq)
                    if not written:
                        logger.error("Reply write failed: agent process not running")
                        task_store.update_status(full_task_id, "failed")
                        raise HTTPException(
                            status_code=500,
                            detail="Failed to deliver reply: agent process not running",
                        )
                except OSError as e:
                    logger.error(f"Reply write failed: {e}")
                    task_store.update_status(full_task_id, "failed")
                    raise HTTPException(
                        status_code=500,
                        detail=f"Failed to deliver reply: {e!s}",
                    ) from e

            updated_task = task_store.get(full_task_id)
            if not updated_task:
                raise HTTPException(
                    status_code=500, detail="Task disappeared unexpectedly"
                )
            return SendMessageResponse(task=updated_task)

        if not controller:
            raise HTTPException(status_code=503, detail="Agent not running")

        active_task = _find_active_working_task()
        if active_task and priority < 5:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Agent already has a working task "
                    f"({active_task.id[:8]}). Retry after it completes."
                ),
                headers={"Retry-After": "2"},
            )

        # Readiness Gate: wait for agent initialization to complete.
        # Priority >= 5 (emergency interrupt) bypasses the gate.
        # Offload blocking Event.wait to a thread to avoid stalling the event loop.
        if priority < 5 and not controller.agent_ready:
            ready = await asyncio.to_thread(
                controller.wait_until_ready, timeout=AGENT_READY_TIMEOUT
            )
            if not ready:
                raise HTTPException(
                    status_code=503,
                    detail="Agent not ready (initializing). Retry after a few seconds.",
                    headers={"Retry-After": "5"},
                )

        # Create task with metadata (may include sender info)
        task_metadata = dict(request.metadata or {})
        task_metadata[_CONTEXT_START_METADATA_KEY] = len(controller.get_context())
        task_metadata[_SENT_MESSAGE_METADATA_KEY] = text_content[
            :SENT_MESSAGE_COMPARE_LEN
        ]
        task = task_store.create(
            request.message, request.context_id, metadata=task_metadata
        )

        # Update to working
        task_store.update_status(task.id, "working")

        # Compound signal: mark task active to suppress premature READY (#314)
        controller.set_task_active()

        try:
            # Update current task preview in registry (for synapse list display)
            # Note: update_current_task handles truncation internally
            if registry and agent_id:
                registry.update_current_task(agent_id, text_content)

            # Priority 5 = interrupt first
            if priority >= 5:
                controller.interrupt()

            # Push sender info to reply stack for simplified reply routing
            # Store when response_mode is "wait" or "notify" (sender expects a reply)
            metadata = request.metadata or {}
            response_mode = _resolve_response_mode(metadata)
            sender_info = _extract_sender_info(request.metadata)
            controller.record_task_received(
                message=text_content,
                sender=sender_info.sender_id,
                priority=priority,
            )
            if (
                response_mode in ("wait", "notify")
                and sender_info.has_reply_target()
                and sender_info.sender_id
            ):
                reply_stack = get_reply_stack()
                reply_entry = sender_info.to_reply_stack_entry()
                reply_entry["receiver_task_id"] = task.id
                reply_entry["message_preview"] = text_content[:80]
                reply_entry["received_at"] = datetime.now(timezone.utc).isoformat()
                reply_stack.set(sender_info.sender_id, reply_entry)
                if agent_id:
                    try:
                        await asyncio.to_thread(
                            save_reply_target, agent_id, reply_entry
                        )
                    except Exception as e:
                        logger.warning(
                            "Failed to persist reply target for %s: %s", agent_id, e
                        )

            # Deliver message via transport (PTY by default, Channel in future)
            written = (
                transport.deliver(
                    task.id,
                    pty_payload_text,
                    response_mode=response_mode,
                    sender_id=sender_info.sender_id,
                    sender_name=sender_info.sender_name,
                )
                if transport
                else False
            )
            if not written:
                controller.clear_task_active()
                task_store.update_status(task.id, "failed")
                raise HTTPException(
                    status_code=500,
                    detail="Failed to send: agent process not running",
                )
        except HTTPException:
            raise  # Re-raise our own HTTPException from write check above
        except Exception as e:
            controller.clear_task_active()  # Release on any preparation/send failure
            task_store.update_status(task.id, "failed")
            msg = f"Failed to send: {e!s}"
            raise HTTPException(status_code=500, detail=msg) from e

        # Get updated task
        updated_task = task_store.get(task.id)
        if not updated_task:
            raise HTTPException(status_code=500, detail="Task disappeared unexpectedly")
        return SendMessageResponse(task=updated_task)

    # --------------------------------------------------------
    # Debug: rendered PTY snapshot (issue #572)
    # --------------------------------------------------------

    @router.get("/debug/pty")
    async def get_debug_pty(_: Any = Depends(require_auth)) -> dict[str, Any]:
        """Return the child's rendered virtual terminal state.

        Used to diagnose waiting_detection misses: the raw PTY byte
        stream is replayed against a ``pyte`` screen so callers see the
        text as the TUI would have drawn it, with cursor motion and
        erase sequences already resolved.
        """
        if controller is None or not hasattr(controller, "pty_snapshot"):
            raise HTTPException(status_code=503, detail="pty renderer not available")
        try:
            snapshot: dict[str, Any] = controller.pty_snapshot()
        except Exception as exc:
            raise HTTPException(
                status_code=503, detail="pty renderer not available"
            ) from exc
        return snapshot

    @router.get("/debug/waiting")
    async def get_debug_waiting(_: Any = Depends(require_auth)) -> dict[str, Any]:
        """Return recent WAITING-detection attempts."""
        if controller is None or not hasattr(controller, "waiting_debug_snapshot"):
            raise HTTPException(
                status_code=503, detail="waiting debug data not available"
            )
        snapshot: dict[str, Any] = controller.waiting_debug_snapshot()
        return snapshot

    # --------------------------------------------------------
    # Agent Card (Discovery)
    # --------------------------------------------------------

    @router.get("/.well-known/agent.json", response_model=AgentCard)
    async def get_agent_card() -> AgentCard:
        """
        Return Agent Card for discovery.

        This endpoint follows the Google A2A specification for agent discovery.
        Agent Card is a "business card" - it only contains discovery information,
        not internal instructions (which are sent via A2A Task at startup).
        """
        # Determine protocol based on SSL configuration
        use_https = os.environ.get("SYNAPSE_USE_HTTPS", "").lower() == "true"
        protocol = "https" if use_https else "http"

        # Build extensions (synapse-specific metadata only, no x-synapse-context)
        synapse_ext: dict[str, Any] = {
            "agent_id": agent_id,
            "pty_wrapped": True,
            "priority_interrupt": True,
            "at_agent_syntax": True,
            "submit_sequence": repr(submit_seq),
            "addressable_as": [
                f"@{agent_id}",
                f"@{agent_type}",
            ],
        }
        if registry:
            agent_data = registry.get_agent(agent_id)
            if agent_data and agent_data.get("summary"):
                synapse_ext["summary"] = agent_data["summary"]
        extensions = {"synapse": synapse_ext}

        return AgentCard(
            name=f"Synapse {agent_type.capitalize()}",
            description=f"PTY-wrapped {agent_type} CLI agent with A2A communication",
            url=f"{protocol}://localhost:{port}",
            version="1.0.0",
            capabilities=AgentCapabilities(
                streaming=True,  # SSE streaming via /tasks/{id}/subscribe
                pushNotifications=False,  # Not yet supported
                multiTurn=True,
            ),
            skills=[
                AgentSkill(
                    id="chat",
                    name="Chat",
                    description="Send messages to the CLI agent",
                ),
                AgentSkill(
                    id="interrupt",
                    name="Interrupt",
                    description="Interrupt current processing (Synapse extension)",
                    parameters={
                        "priority": {
                            "type": "integer",
                            "description": "Priority level (5 for interrupt)",
                            "default": 3,
                        }
                    },
                ),
            ],
            securitySchemes={},  # No auth for local use
            extensions=extensions,
        )

    # --------------------------------------------------------
    # Task Management
    # --------------------------------------------------------

    @router.post("/tasks/send", response_model=SendMessageResponse)
    async def send_message(  # noqa: B008
        request: SendMessageRequest, _: Any = Depends(require_auth)
    ) -> SendMessageResponse:
        """
        Send a message to the agent (Google A2A compatible).

        Creates a task and sends the message content to the CLI via PTY.
        Requires authentication when SYNAPSE_AUTH_ENABLED=true.
        """
        return await _send_task_message(request)

    @router.post("/tasks/create", response_model=CreateTaskResponse)
    async def create_task(  # noqa: B008
        request: CreateTaskRequest, _: Any = Depends(require_auth)
    ) -> CreateTaskResponse:
        """
        Create a task without sending to PTY.

        This endpoint is used by --wait/--notify modes to create a task on the
        sender's server before sending to the target agent. The task is
        created in "working" status, waiting for the reply via --reply-to.

        Requires authentication when SYNAPSE_AUTH_ENABLED=true.
        """
        task = task_store.create(
            request.message,
            metadata=request.metadata,
        )
        task_store.update_status(task.id, "working")
        return CreateTaskResponse(task=task)

    @router.post("/history/update")
    async def update_history(  # noqa: B008
        request: HistoryUpdateRequest, _: Any = Depends(require_auth)
    ) -> dict[str, Any]:
        """Update an existing history observation by task ID."""
        updated = history_manager.update_observation_status(
            task_id=request.task_id,
            status=request.status,
            output_text=request.output_summary,
            metadata_update={"completion_callback": True},
        )
        if not updated:
            raise HTTPException(status_code=404, detail="Task not found in history")

        return {"updated": True, "task_id": request.task_id, "status": request.status}

    # --------------------------------------------------------
    # Reply / Task Utility Endpoints
    # NOTE: These must be defined BEFORE /tasks/{task_id} to avoid route conflicts
    # --------------------------------------------------------

    class ExplicitReplyRequest(BaseModel):
        """Request model for explicitly completing a task via synapse reply."""

        message: str
        status: Literal["completed", "failed"] = "completed"
        error: TaskErrorModel | None = None

    @router.post("/tasks/{task_id}/reply")
    async def record_explicit_reply(
        task_id: str,
        request: ExplicitReplyRequest,
        _: Any = Depends(require_auth),
    ) -> Task:
        """Record an explicit synapse reply on the receiver's local task."""
        updated = task_store.record_explicit_reply(
            task_id,
            message=request.message,
            status=request.status,
            error=request.error,
        )
        if not updated:
            raise HTTPException(status_code=404, detail="Task not found")
        return updated

    # --------------------------------------------------------
    # Shared Memory Endpoints
    # --------------------------------------------------------

    class MemorySaveRequest(BaseModel):
        """Request model for saving a memory."""

        key: str
        content: str
        author: str
        tags: list[str] | None = None
        notify: bool = False

    def _require_shared_memory() -> Any:
        """Return SharedMemory instance or raise 503 if disabled."""
        from synapse.shared_memory import SharedMemory

        mem = SharedMemory.from_env()
        if not mem.enabled:
            raise HTTPException(status_code=503, detail="Shared memory is disabled")
        return mem

    @router.get("/memory/list")
    async def list_memories(
        author: str | None = None,
        tags: str | None = None,
        limit: int = 50,
        _: Any = Depends(require_auth),
    ) -> dict[str, Any]:
        """List memories with optional filters."""
        mem = _require_shared_memory()
        limit = max(1, min(limit, 100))
        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
        memories = mem.list_memories(author=author, tags=tag_list, limit=limit)
        return {"memories": memories}

    @router.post("/memory/save")
    async def save_memory(
        request: MemorySaveRequest, _: Any = Depends(require_auth)
    ) -> dict[str, Any]:
        """Save or update a memory entry."""
        mem = _require_shared_memory()
        result = mem.save(
            key=request.key,
            content=request.content,
            author=request.author,
            tags=request.tags,
        )
        if not result:
            raise HTTPException(status_code=503, detail="Shared memory is disabled")
        if request.notify:
            threading.Thread(
                target=_memory_broadcast_notify_api,
                args=(request.key,),
                daemon=True,
            ).start()
        return dict(result)

    @router.get("/memory/search")
    async def search_memories(q: str, _: Any = Depends(require_auth)) -> dict[str, Any]:
        """Search memories by key, content, or tags."""
        mem = _require_shared_memory()
        results = mem.search(q)
        return {"memories": results}

    @router.get("/memory/{id_or_key}")
    async def get_memory(
        id_or_key: str, _: Any = Depends(require_auth)
    ) -> dict[str, Any]:
        """Get a memory by ID or key."""
        mem = _require_shared_memory()
        result = mem.get(id_or_key)
        if not result:
            raise HTTPException(
                status_code=404, detail=f"Memory not found: {id_or_key}"
            )
        return dict(result)

    @router.delete("/memory/{id_or_key}")
    async def delete_memory(
        id_or_key: str, _: Any = Depends(require_auth)
    ) -> dict[str, Any]:
        """Delete a memory by ID or key."""
        mem = _require_shared_memory()
        deleted = mem.delete(id_or_key)
        if not deleted:
            raise HTTPException(
                status_code=404, detail=f"Memory not found: {id_or_key}"
            )
        return {"deleted": True, "id_or_key": id_or_key}

    # --------------------------------------------------------
    # Plan Approval Endpoints (B3: Plan Approval Workflow)
    # NOTE: Must be before /tasks/{task_id} to avoid route conflicts
    # --------------------------------------------------------

    class ApproveRejectRequest(BaseModel):
        """Request model for approve/reject."""

        reason: str = ""

    @router.post("/tasks/{task_id}/approve")
    async def approve_task(
        task_id: str,
        request: ApproveRejectRequest | None = None,
        _: Any = Depends(require_auth),
    ) -> dict[str, Any]:
        """Approve a plan for a task."""
        task = task_store.get(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        task_store.update_status(task_id, "working")

        if controller:
            approval_msg = (
                f"[A2A:PLAN_APPROVED:{task_id[:8]}] "
                "Your plan has been approved. Proceed with implementation."
            )
            try:
                written = controller.write(approval_msg, submit_seq=submit_seq)
                if not written:
                    logger.error("Approval write failed: agent process not running")
                    raise HTTPException(
                        status_code=500,
                        detail="Failed to deliver approval: agent process not running",
                    )
            except OSError as e:
                logger.error(f"Approval write failed: {e}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to deliver approval: {e!s}",
                ) from e

        return {"approved": True, "task_id": task_id}

    @router.post("/tasks/{task_id}/reject")
    async def reject_task(
        task_id: str,
        request: ApproveRejectRequest | None = None,
        _: Any = Depends(require_auth),
    ) -> dict[str, Any]:
        """Reject a plan for a task."""
        task = task_store.get(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        reason = request.reason if request else ""
        task_store.update_status(task_id, "input_required")

        if controller:
            rejection_msg = f"[A2A:PLAN_REJECTED:{task_id[:8]}] Your plan was rejected."
            if reason:
                rejection_msg += f" Reason: {reason}"
            rejection_msg += " Please revise your plan."
            try:
                written = controller.write(rejection_msg, submit_seq=submit_seq)
                if not written:
                    logger.error("Rejection write failed: agent process not running")
                    raise HTTPException(
                        status_code=500,
                        detail="Failed to deliver rejection: agent process not running",
                    )
            except OSError as e:
                logger.error(f"Rejection write failed: {e}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to deliver rejection: {e!s}",
                ) from e

        return {"rejected": True, "task_id": task_id, "reason": reason}

    async def _handle_permission_decision(
        task_id: str, response_text: str, label: str
    ) -> dict[str, Any]:
        """Shared logic for permission approve/deny endpoints."""
        task = task_store.get(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        if task.status != "input_required":
            raise HTTPException(
                status_code=400, detail="Task is not awaiting permission input"
            )
        if not controller:
            raise HTTPException(status_code=503, detail="Agent not running")

        try:
            written = controller.write(response_text, submit_seq=submit_seq)
            if not written:
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to deliver {label}: agent process not running",
                )
        except OSError as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to deliver {label}: {e!s}",
            ) from e

        task_store.update_status(task_id, "working")
        return {"status": label, "task_id": task_id}

    @router.post("/tasks/{task_id}/permission/approve")
    async def approve_permission(
        task_id: str,
        _: Any = Depends(require_auth),
    ) -> dict[str, Any]:
        """Approve a runtime permission prompt for an input_required task."""
        return await _handle_permission_decision(task_id, approve_response, "approved")

    @router.post("/tasks/{task_id}/permission/deny")
    async def deny_permission(
        task_id: str,
        _: Any = Depends(require_auth),
    ) -> dict[str, Any]:
        """Deny a runtime permission prompt for an input_required task."""
        return await _handle_permission_decision(task_id, deny_response, "denied")

    # --------------------------------------------------------
    # Task Management (continued)
    # --------------------------------------------------------

    @router.get("/tasks/{task_id}", response_model=Task)
    async def get_task(task_id: str, _: Any = Depends(require_auth)) -> Task:  # noqa: B008
        """
        Get task status and results.

        Maps Synapse IDLE/BUSY status to A2A task states.
        Detects errors in CLI output and sets failed status accordingly.
        Requires authentication when SYNAPSE_AUTH_ENABLED=true.
        """
        task = task_store.get(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        # Update status based on controller state
        if controller and task.status == "working":
            synapse_status = controller.status
            context = controller.get_context()

            # NOTE: the previous code checked ``is_input_required(context)``
            # here and wrote ``input_required`` into task_store. That was a
            # rogue write in a GET handler — a read-only endpoint should not
            # have side effects. The ``_on_status_change`` callback is now
            # the single writer for ``input_required`` transitions (issue
            # #569). Removing this branch also prevents PTY context remnants
            # from re-setting ``input_required`` after the controller has
            # already exited WAITING.
            if synapse_status in ("READY", "DONE"):
                recent_context = context[-CONTEXT_RECENT_SIZE:]
                updated_task = _finalize_working_task(task_id, context, recent_context)

                # Dispatch response or notification based on response_mode
                if updated_task:
                    metadata = updated_task.metadata or {}
                    resp_mode = _resolve_response_mode(metadata)
                    sender_info = _extract_sender_info(metadata)

                    if sender_info.sender_endpoint:
                        if resp_mode in ("wait", "notify"):
                            updated_task = _maybe_mark_missing_reply(
                                updated_task, resp_mode
                            )
                            coro = _send_response_to_sender(
                                updated_task,
                                sender_info.sender_endpoint,
                                agent_id or "unknown",
                                sender_task_id=sender_info.sender_task_id,
                            )
                            try:
                                asyncio.create_task(coro)
                            except Exception:
                                coro.close()
                                logger.exception(
                                    "Failed to create sender response task for %s",
                                    task_id,
                                )
                        else:
                            coro = _notify_sender_completion(
                                task=updated_task,
                                sender_endpoint=sender_info.sender_endpoint,
                                sender_uds_path=sender_info.sender_uds_path,
                                sender_task_id=sender_info.sender_task_id,
                                status=updated_task.status,
                            )
                            try:
                                asyncio.create_task(coro)
                            except Exception:
                                coro.close()
                                logger.exception(
                                    "Failed to create sender notification task for %s",
                                    task_id,
                                )

            updated_task = task_store.get(task_id)
            if updated_task:
                task = updated_task

        return task

    @router.get("/tasks", response_model=list[Task])
    async def list_tasks(  # noqa: B008
        context_id: str | None = None, _: Any = Depends(require_auth)
    ) -> list[Task]:
        """List all tasks, optionally filtered by context. Requires authentication."""
        return task_store.list_tasks(context_id)

    @router.post("/tasks/{task_id}/cancel")
    async def cancel_task(
        task_id: str, _: Any = Depends(require_auth)
    ) -> dict[str, str]:  # noqa: B008
        """
        Cancel a running task.

        Sends SIGINT to the CLI process (Synapse extension).
        Requires authentication when SYNAPSE_AUTH_ENABLED=true.
        """
        task = task_store.get(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        if task.status not in ["submitted", "working"]:
            raise HTTPException(
                status_code=400, detail=f"Cannot cancel task in {task.status} state"
            )

        # Interrupt the CLI
        if controller:
            controller.interrupt()

        task_store.update_status(task_id, "canceled")

        # Dispatch webhook for canceled task
        _dispatch_task_event("task.canceled", {"task_id": task_id})

        # Save to history
        updated_task = task_store.get(task_id)
        if updated_task:
            _save_task_to_history(
                updated_task,
                agent_id=agent_id or "unknown",
                agent_name=agent_type or "unknown",
                task_status="canceled",
            )

        return {"status": "canceled", "task_id": task_id}

    # --------------------------------------------------------
    # SSE Streaming
    # --------------------------------------------------------

    @router.get("/tasks/{task_id}/subscribe")
    async def subscribe_to_task(  # noqa: B008
        task_id: str, _: Any = Depends(require_auth)
    ) -> StreamingResponse:
        """
        Subscribe to task output via Server-Sent Events.

        Streams CLI output in real-time until task completes.
        Event types:
        - output: New CLI output data
        - status: Task status change
        - done: Task completed (final event)
        Requires authentication when SYNAPSE_AUTH_ENABLED=true.
        """
        task = task_store.get(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        async def event_generator() -> "AsyncGenerator[str, None]":
            last_len = 0
            last_status = task.status

            while True:
                current_task = task_store.get(task_id)
                if not current_task:
                    err = {"type": "error", "message": "Task not found"}
                    yield f"data: {json.dumps(err)}\n\n"
                    break

                # Check for status change
                if current_task.status != last_status:
                    last_status = current_task.status
                    evt = {"type": "status", "status": current_task.status}
                    yield f"data: {json.dumps(evt)}\n\n"

                # Stream new output if controller is available
                if controller:
                    context = controller.get_context()
                    if len(context) > last_len:
                        new_content = context[last_len:]
                        last_len = len(context)
                        evt = {"type": "output", "data": new_content}
                        yield f"data: {json.dumps(evt)}\n\n"

                # Check for terminal states
                if current_task.status in ("completed", "failed", "canceled"):
                    # Send final task state with artifacts and error
                    final_data: dict[str, object] = {
                        "type": "done",
                        "status": current_task.status,
                        "artifacts": [
                            {"type": a.type, "data": a.data}
                            for a in current_task.artifacts
                        ],
                    }
                    if current_task.error:
                        final_data["error"] = {
                            "code": current_task.error.code,
                            "message": current_task.error.message,
                        }
                    yield f"data: {json.dumps(final_data)}\n\n"
                    break

                await asyncio.sleep(0.1)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # Disable nginx buffering
            },
        )

    # --------------------------------------------------------
    # Synapse Extensions (Priority Interrupt)
    # --------------------------------------------------------

    @router.post("/tasks/send-priority", response_model=SendMessageResponse)
    async def send_priority_message(  # noqa: B008
        request: SendMessageRequest, priority: int = 3, _: Any = Depends(require_auth)
    ) -> SendMessageResponse:
        """
        Send a message with priority (Synapse extension).

        Priority 5 sends SIGINT before the message for interrupt.
        Requires authentication when SYNAPSE_AUTH_ENABLED=true.
        """
        return await _send_task_message(request, priority=priority)

    # --------------------------------------------------------
    # External Agent Management (Google A2A Client)
    # --------------------------------------------------------

    @router.post("/external/discover", response_model=ExternalAgentInfo)
    async def discover_external_agent(  # noqa: B008
        request: DiscoverAgentRequest, _: Any = Depends(require_auth)
    ) -> ExternalAgentInfo:
        """
        Discover and register an external Google A2A agent.

        Fetches the Agent Card from the given URL and registers the agent.
        Requires authentication when SYNAPSE_AUTH_ENABLED=true.
        """
        client = get_client()
        agent = client.discover(request.url, alias=request.alias)

        if not agent:
            raise HTTPException(
                status_code=400, detail=f"Failed to discover agent at {request.url}"
            )

        return _convert_agent_to_info(agent)

    @router.get("/external/agents", response_model=list[ExternalAgentInfo])
    async def list_external_agents(
        _: Any = Depends(require_auth),
    ) -> list[ExternalAgentInfo]:
        """
        List all registered external agents.
        Requires authentication when SYNAPSE_AUTH_ENABLED=true.
        """
        client = get_client()
        agents = client.list_agents()

        return [_convert_agent_to_info(agent) for agent in agents]

    @router.get("/external/agents/{alias}", response_model=ExternalAgentInfo)
    async def get_external_agent(
        alias: str, _: Any = Depends(require_auth)
    ) -> ExternalAgentInfo:
        """
        Get details of a specific external agent.
        Requires authentication when SYNAPSE_AUTH_ENABLED=true.
        """
        client = get_client()
        agent = client.registry.get(alias)

        if not agent:
            raise HTTPException(status_code=404, detail=f"Agent '{alias}' not found")

        return _convert_agent_to_info(agent)

    @router.delete("/external/agents/{alias}")
    async def remove_external_agent(
        alias: str, _: Any = Depends(require_auth)
    ) -> dict[str, str]:
        """
        Remove an external agent from the registry.
        Requires authentication when SYNAPSE_AUTH_ENABLED=true.
        """
        client = get_client()

        if not client.remove_agent(alias):
            raise HTTPException(status_code=404, detail=f"Agent '{alias}' not found")

        return {"status": "removed", "alias": alias}

    @router.post("/external/agents/{alias}/send", response_model=ExternalTaskResponse)
    async def send_to_external_agent(
        alias: str, request: SendExternalMessageRequest, _: Any = Depends(require_auth)
    ) -> ExternalTaskResponse:
        """
        Send a message to an external Google A2A agent.

        Uses the Google A2A protocol to communicate with the external agent.
        Requires authentication when SYNAPSE_AUTH_ENABLED=true.
        """
        client = get_client()
        agent = client.registry.get(alias)

        if not agent:
            raise HTTPException(status_code=404, detail=f"Agent '{alias}' not found")

        task = client.send_message(
            alias,
            request.message,
            wait_for_completion=request.wait_for_completion,
            timeout=request.timeout,
        )

        if not task:
            raise HTTPException(
                status_code=500, detail=f"Failed to send message to {alias}"
            )

        return ExternalTaskResponse(
            id=task.id,
            status=task.status,
            artifacts=task.artifacts,
        )

    # --------------------------------------------------------
    # Webhook Management
    # --------------------------------------------------------

    class WebhookRequest(BaseModel):
        """Request to register a webhook."""

        url: str
        events: list[str] | None = None
        secret: str | None = None

    class WebhookResponse(BaseModel):
        """Webhook registration response."""

        url: str
        events: list[str]
        enabled: bool
        created_at: datetime

    class WebhookDeliveryResponse(BaseModel):
        """Webhook delivery record."""

        webhook_url: str
        event_type: str
        event_id: str
        status_code: int | None
        success: bool
        attempts: int
        error: str | None
        delivered_at: datetime | None

    @router.post("/webhooks", response_model=WebhookResponse)
    async def register_webhook(
        request: WebhookRequest, _: Any = Depends(require_auth)
    ) -> WebhookResponse:
        """
        Register a webhook for task notifications.

        Events:
        - task.completed: Task finished successfully
        - task.failed: Task failed with error
        - task.canceled: Task was canceled

        Requires authentication when SYNAPSE_AUTH_ENABLED=true.
        """
        registry = get_webhook_registry()

        try:
            webhook = registry.register(
                url=request.url,
                events=request.events,
                secret=request.secret,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

        return WebhookResponse(
            url=webhook.url,
            events=webhook.events,
            enabled=webhook.enabled,
            created_at=webhook.created_at,
        )

    @router.get("/webhooks", response_model=list[WebhookResponse])
    async def list_webhooks(_: Any = Depends(require_auth)) -> list[WebhookResponse]:
        """
        List all registered webhooks.
        Requires authentication when SYNAPSE_AUTH_ENABLED=true.
        """
        registry = get_webhook_registry()

        return [
            WebhookResponse(
                url=w.url,
                events=w.events,
                enabled=w.enabled,
                created_at=w.created_at,
            )
            for w in registry.list_webhooks()
        ]

    @router.delete("/webhooks")
    async def unregister_webhook(
        url: str, _: Any = Depends(require_auth)
    ) -> dict[str, str]:
        """
        Unregister a webhook.
        Requires authentication when SYNAPSE_AUTH_ENABLED=true.
        """
        registry = get_webhook_registry()

        if not registry.unregister(url):
            raise HTTPException(status_code=404, detail="Webhook not found")

        return {"status": "removed", "url": url}

    @router.get("/webhooks/deliveries", response_model=list[WebhookDeliveryResponse])
    async def list_webhook_deliveries(
        limit: int = 20, _: Any = Depends(require_auth)
    ) -> list[WebhookDeliveryResponse]:
        """
        Get recent webhook delivery attempts.
        Requires authentication when SYNAPSE_AUTH_ENABLED=true.
        """
        registry = get_webhook_registry()
        deliveries = registry.get_recent_deliveries(limit)

        return [
            WebhookDeliveryResponse(
                webhook_url=d.webhook_url,
                event_type=d.event.event_type,
                event_id=d.event.id,
                status_code=d.status_code,
                success=d.success,
                attempts=d.attempts,
                error=d.error,
                delivered_at=d.delivered_at,
            )
            for d in deliveries
        ]

    # --------------------------------------------------------
    # Team Management (B6: Agent-Initiated Team Spawning)
    # --------------------------------------------------------

    @router.post("/team/start", response_model=TeamStartResponse)
    async def start_team(
        request: TeamStartRequest,
        _: Any = Depends(require_auth),
    ) -> TeamStartResponse:
        """
        Start multiple agents with split panes via A2A protocol.

        Detects the current terminal (tmux, iTerm2, Terminal.app) and
        creates split panes for each agent. Falls back to background
        process spawning when no supported terminal is detected.

        Requires authentication when SYNAPSE_AUTH_ENABLED=true.
        """
        import shlex
        import subprocess

        from synapse.server import load_profile

        terminal = request.terminal or detect_terminal_app()

        started: list[AgentStartStatus] = []

        # Try pane creation if terminal is available
        if terminal:
            commands = create_panes(
                request.agents,
                request.layout,
                terminal,
                tool_args=request.tool_args,
            )
            if commands:
                for cmd in commands:
                    subprocess.run(shlex.split(cmd))
                started = [
                    AgentStartStatus(agent_type=agent, status="submitted")
                    for agent in request.agents
                ]
                return TeamStartResponse(started=started, terminal_used=terminal)

        # Fallback: validate profiles and spawn background processes
        for agent_type in request.agents:
            try:
                load_profile(agent_type)
            except FileNotFoundError:
                started.append(
                    AgentStartStatus(
                        agent_type=agent_type,
                        status="failed",
                        reason=f"Unknown agent type: {agent_type}",
                    )
                )
                continue

            try:
                fallback_cmd = ["synapse", agent_type]
                if request.tool_args:
                    fallback_cmd += ["--"] + request.tool_args
                subprocess.Popen(
                    fallback_cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                started.append(
                    AgentStartStatus(
                        agent_type=agent_type,
                        status="submitted",
                    )
                )
            except OSError as e:
                started.append(
                    AgentStartStatus(
                        agent_type=agent_type,
                        status="failed",
                        reason=f"Failed to spawn process: {e}",
                    )
                )

        return TeamStartResponse(started=started, terminal_used=None)

    # --------------------------------------------------------
    # Spawn Single Agent (Synapse Extension)
    # --------------------------------------------------------

    @router.post("/spawn", response_model=SpawnResponse)
    async def spawn_single_agent(
        request: SpawnRequest,
        _: Any = Depends(require_auth),
    ) -> SpawnResponse:
        """Spawn a single agent in a new terminal pane via A2A protocol.

        Requires authentication when SYNAPSE_AUTH_ENABLED=true.
        """
        from functools import partial

        from starlette.concurrency import run_in_threadpool

        from synapse.spawn import spawn_agent

        try:
            result = await run_in_threadpool(
                partial(
                    spawn_agent,
                    profile=request.profile,
                    port=request.port,
                    name=request.name,
                    role=request.role,
                    skill_set=request.skill_set,
                    terminal=request.terminal,
                    tool_args=request.tool_args,
                    worktree=request.worktree,
                )
            )
            return SpawnResponse(
                agent_id=result.agent_id,
                port=result.port,
                terminal_used=result.terminal_used,
                status=result.status,
                worktree_path=result.worktree_path,
                worktree_branch=result.worktree_branch,
            )
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=SpawnResponse(
                    status="failed",
                    reason=str(e),
                ).model_dump(),
            ) from e

    # --------------------------------------------------------
    # Reply Stack (Synapse Extension)
    # --------------------------------------------------------

    class ReplyTarget(BaseModel):
        """Reply target information."""

        sender_endpoint: str | None = None
        sender_uds_path: str | None = None
        sender_task_id: str | None = None
        receiver_task_id: str | None = None
        message_preview: str | None = None
        received_at: str | None = None

    class ReplyTargetSummary(BaseModel):
        """Reply target summary with disambiguation metadata."""

        sender_id: str
        sender_endpoint: str | None = None
        sender_uds_path: str | None = None
        sender_task_id: str | None = None
        receiver_task_id: str | None = None
        message_preview: str | None = None
        received_at: str | None = None

    class ReplyTargetList(BaseModel):
        """List of reply target sender IDs."""

        sender_ids: list[str]
        targets: list[ReplyTargetSummary] = []

    @router.get("/reply-stack/list", response_model=ReplyTargetList)
    async def list_reply_targets(
        _: Any = Depends(require_auth),
    ) -> ReplyTargetList:
        """
        List all sender IDs in the reply stack.

        Returns a list of sender IDs that can be used with --to flag.
        Requires authentication when SYNAPSE_AUTH_ENABLED=true.
        """
        reply_stack = get_reply_stack()
        return ReplyTargetList(
            sender_ids=reply_stack.list_senders(),
            targets=[
                ReplyTargetSummary(
                    sender_id=target["sender_id"],
                    sender_endpoint=target.get("sender_endpoint"),
                    sender_uds_path=target.get("sender_uds_path"),
                    sender_task_id=target.get("sender_task_id"),
                    receiver_task_id=target.get("receiver_task_id"),
                    message_preview=target.get("message_preview"),
                    received_at=target.get("received_at"),
                )
                for target in reply_stack.list_targets()
            ],
        )

    @router.get("/reply-stack/get", response_model=ReplyTarget)
    async def get_reply_target(
        sender_id: str | None = None, _: Any = Depends(require_auth)
    ) -> ReplyTarget:
        """
        Get a reply target without removing it.

        If sender_id is provided, returns that specific sender's info.
        Otherwise returns the most recently received sender (LIFO).
        Does NOT remove the entry - use /reply-stack/pop after successful reply.
        Returns 404 if no reply targets exist.
        Requires authentication when SYNAPSE_AUTH_ENABLED=true.
        """
        reply_stack = get_reply_stack()
        info = reply_stack.get(sender_id) if sender_id else reply_stack.peek_last()
        if not info:
            raise HTTPException(status_code=404, detail="No reply target")
        return ReplyTarget(
            sender_endpoint=info.get("sender_endpoint"),
            sender_uds_path=info.get("sender_uds_path"),
            sender_task_id=info.get("sender_task_id"),
            receiver_task_id=info.get("receiver_task_id"),
            message_preview=info.get("message_preview"),
            received_at=info.get("received_at"),
        )

    @router.get("/reply-stack/pop", response_model=ReplyTarget)
    async def pop_reply_target(
        sender_id: str | None = None, _: Any = Depends(require_auth)
    ) -> ReplyTarget:
        """
        Pop a reply target from the map.

        If sender_id is provided, pops that specific sender's entry.
        Otherwise pops the last entry (LIFO).
        Removes the entry after returning.
        Returns 404 if no reply targets exist.
        Requires authentication when SYNAPSE_AUTH_ENABLED=true.
        """
        reply_stack = get_reply_stack()
        info = reply_stack.pop(sender_id)
        if not info:
            raise HTTPException(status_code=404, detail="No reply target")
        return ReplyTarget(
            sender_endpoint=info.get("sender_endpoint"),
            sender_uds_path=info.get("sender_uds_path"),
            sender_task_id=info.get("sender_task_id"),
            receiver_task_id=info.get("receiver_task_id"),
            message_preview=info.get("message_preview"),
            received_at=info.get("received_at"),
        )

    # ================================================================
    # Canvas proxy endpoints — /canvas/cards CRUD
    # ================================================================

    from synapse.canvas.protocol import CanvasMessage, validate_message
    from synapse.canvas.store import CanvasStore
    from synapse.paths import get_canvas_db_path

    canvas_db = os.environ.get("SYNAPSE_CANVAS_DB_PATH") or get_canvas_db_path()
    canvas_store = CanvasStore(db_path=canvas_db)

    @router.post("/canvas/cards", status_code=201, response_model=None)
    async def canvas_post_card(request: Request) -> Any:
        """Create or update a Canvas card (proxy to local store)."""
        body = await request.json()
        msg = CanvasMessage.from_dict(body)
        errors = validate_message(msg)
        if errors:
            raise HTTPException(status_code=422, detail=errors)

        if isinstance(msg.content, list):
            content_json = json.dumps(
                [
                    {
                        "format": b.format,
                        "body": b.body,
                        **({} if not b.lang else {"lang": b.lang}),
                    }
                    for b in msg.content
                ],
                ensure_ascii=False,
            )
        else:
            d: dict[str, Any] = {"format": msg.content.format, "body": msg.content.body}
            if msg.content.lang:
                d["lang"] = msg.content.lang
            content_json = json.dumps(d, ensure_ascii=False)

        if msg.card_id:
            existing = canvas_store.get_card(msg.card_id)
            result = canvas_store.upsert_card(
                card_id=msg.card_id,
                agent_id=msg.agent_id,
                content=content_json,
                title=msg.title,
                agent_name=msg.agent_name or None,
                pinned=msg.pinned,
                tags=msg.tags or None,
                template=msg.template,
                template_data=msg.template_data or None,
            )
            if result is None:
                raise HTTPException(
                    status_code=403,
                    detail=f"Card '{msg.card_id}' is owned by a different agent",
                )
            if existing is not None:
                return JSONResponse(content=result, status_code=200)
            return result
        else:
            return canvas_store.add_card(
                agent_id=msg.agent_id,
                content=content_json,
                title=msg.title,
                agent_name=msg.agent_name or None,
                pinned=msg.pinned,
                tags=msg.tags or None,
                template=msg.template,
                template_data=msg.template_data or None,
            )

    @router.get("/canvas/cards")
    async def canvas_list_cards(
        agent_id: str | None = None,
        search: str | None = None,
        type: str | None = None,
    ) -> list[dict[str, Any]]:
        """List Canvas cards."""
        return canvas_store.list_cards(
            agent_id=agent_id, search=search, content_type=type
        )

    @router.get("/canvas/cards/{card_id}")
    async def canvas_get_card(card_id: str) -> dict[str, Any]:
        """Get a single Canvas card."""
        card = canvas_store.get_card(card_id)
        if card is None:
            raise HTTPException(status_code=404, detail="Card not found")
        return card

    @router.delete("/canvas/cards/{card_id}")
    async def canvas_delete_card(card_id: str, request: Request) -> dict[str, str]:
        """Delete a Canvas card."""
        x_agent_id = request.headers.get("X-Agent-Id", "")
        card = canvas_store.get_card(card_id)
        if card is None:
            raise HTTPException(status_code=404, detail="Card not found")
        if card["agent_id"] != x_agent_id:
            raise HTTPException(
                status_code=403, detail="Cannot delete another agent's card"
            )
        canvas_store.delete_card(card_id, agent_id=x_agent_id)
        return {"deleted": card_id}

    return router
