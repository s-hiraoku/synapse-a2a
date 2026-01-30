"""
Google A2A Protocol Compatibility Layer

This module provides Google A2A protocol compatible endpoints while
maintaining Synapse A2A's unique PTY-wrapping capabilities.

Google A2A Spec: https://a2a-protocol.org/latest/specification/
"""

import asyncio
import json
import logging
import os
import sys
import threading
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from synapse.a2a_client import get_client
from synapse.auth import require_auth
from synapse.config import CONTEXT_RECENT_SIZE
from synapse.controller import TerminalController
from synapse.error_detector import detect_task_status, is_input_required
from synapse.history import HistoryManager
from synapse.output_parser import parse_output
from synapse.registry import AgentRegistry
from synapse.reply_stack import SenderInfo as ReplyStackSenderInfo
from synapse.reply_stack import get_reply_stack
from synapse.utils import extract_text_from_parts, format_a2a_message, get_iso_timestamp
from synapse.webhooks import (
    dispatch_event,
    get_webhook_registry,
)

if TYPE_CHECKING:
    from synapse.a2a_client import ExternalAgent

# Task state mapping from Google A2A spec
TaskState = Literal[
    "submitted",  # Task received
    "working",  # Task in progress
    "input_required",  # Waiting for additional input
    "completed",  # Task finished successfully
    "failed",  # Task failed
    "canceled",  # Task was canceled
]


# ============================================================
# Helper Functions (Refactored)
# ============================================================


@dataclass
class SenderInfo:
    """Extracted sender information from metadata."""

    sender_id: str | None = None
    sender_endpoint: str | None = None
    sender_uds_path: str | None = None
    sender_task_id: str | None = None

    def has_reply_target(self) -> bool:
        """Check if there's enough info to send a reply."""
        return bool(self.sender_id and (self.sender_endpoint or self.sender_uds_path))

    def to_reply_stack_entry(self) -> ReplyStackSenderInfo:
        """Convert to SenderInfo TypedDict for reply stack storage."""
        entry: ReplyStackSenderInfo = {}
        if self.sender_endpoint:
            entry["sender_endpoint"] = self.sender_endpoint
        if self.sender_uds_path:
            entry["sender_uds_path"] = self.sender_uds_path
        if self.sender_task_id:
            entry["sender_task_id"] = self.sender_task_id
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
        sender_endpoint=sender.get("sender_endpoint"),
        sender_uds_path=sender.get("sender_uds_path"),
        sender_task_id=metadata.get("sender_task_id"),
    )


def _dispatch_task_event(event_type: str, payload: dict[str, Any]) -> None:
    """Dispatch a task event asynchronously via webhook.

    Args:
        event_type: Event type (e.g., "task.completed", "task.failed")
        payload: Event payload dict
    """
    asyncio.create_task(dispatch_event(get_webhook_registry(), event_type, payload))


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


def map_synapse_status_to_a2a(synapse_status: str) -> TaskState:
    """Map Synapse status to Google A2A task state"""
    mapping: dict[str, TaskState] = {
        "STARTING": "submitted",
        "BUSY": "working",
        "IDLE": "completed",
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
        if use_markdown:
            return f"```{language}\n{content}\n```"
        return f"[Code: {language}]\n{content}"

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


# ============================================================
# Pydantic Models (Google A2A Compatible)
# ============================================================


class TextPart(BaseModel):
    """Text content part"""

    type: Literal["text"] = "text"
    text: str


class FilePart(BaseModel):
    """File reference part"""

    type: Literal["file"] = "file"
    file: dict[str, Any]


class DataPart(BaseModel):
    """Structured data part"""

    type: Literal["data"] = "data"
    data: dict[str, Any]


# Union type for parts
Part = TextPart | FilePart | DataPart


class Message(BaseModel):
    """A2A Message with role and parts"""

    role: Literal["user", "agent"] = "user"
    parts: list[TextPart | FilePart | DataPart]


class Artifact(BaseModel):
    """Task output artifact"""

    type: str = "text"
    data: Any


class TaskErrorModel(BaseModel):
    """A2A Task Error (for failed tasks)"""

    code: str
    message: str
    data: dict[str, Any] | None = None


class Task(BaseModel):
    """A2A Task with lifecycle"""

    id: str
    status: TaskState
    message: Message | None = None
    artifacts: list[Artifact] = []
    error: TaskErrorModel | None = None  # Error info for failed tasks
    created_at: str
    updated_at: str
    context_id: str | None = None
    metadata: dict[str, Any] = {}


class SendMessageRequest(BaseModel):
    """Request to send a message"""

    message: Message
    context_id: str | None = None
    metadata: dict[str, Any] = {}


class SendMessageResponse(BaseModel):
    """Response after sending a message"""

    task: Task


class CreateTaskRequest(BaseModel):
    """Request to create a task (without sending to PTY)."""

    message: Message
    metadata: dict[str, Any] | None = None


class CreateTaskResponse(BaseModel):
    """Response with created task."""

    task: Task


class AgentSkill(BaseModel):
    """Agent capability/skill definition"""

    id: str
    name: str
    description: str
    parameters: dict[str, Any] | None = None


class AgentCapabilities(BaseModel):
    """Agent capabilities declaration"""

    streaming: bool = False
    pushNotifications: bool = False  # noqa: N815 (A2A protocol spec)
    multiTurn: bool = True  # noqa: N815 (A2A protocol spec)


class AgentCard(BaseModel):
    """Google A2A Agent Card for discovery"""

    name: str
    description: str
    url: str
    version: str = "1.0.0"
    capabilities: AgentCapabilities
    skills: list[AgentSkill] = []
    securitySchemes: dict[str, Any] = {}  # noqa: N815 (A2A protocol spec)
    # Synapse A2A extensions
    extensions: dict[str, Any] = {}


# ============================================================
# Task Store (In-Memory)
# ============================================================


class TaskStore:
    """Thread-safe in-memory task storage"""

    def __init__(self) -> None:
        self._tasks: dict[str, Task] = {}
        self._lock = threading.Lock()

    def create(
        self,
        message: Message,
        context_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Task:
        """Create a new task with optional metadata (including sender info)"""
        now = get_iso_timestamp()
        task = Task(
            id=str(uuid4()),
            status="submitted",
            message=message,
            artifacts=[],
            created_at=now,
            updated_at=now,
            context_id=context_id,
            metadata=metadata or {},
        )
        with self._lock:
            self._tasks[task.id] = task
        return task

    def get(self, task_id: str) -> Task | None:
        """Get a task by ID"""
        with self._lock:
            return self._tasks.get(task_id)

    def get_by_prefix(self, prefix: str) -> Task | None:
        """Get a task by ID prefix (for --reply-to with short IDs).

        Args:
            prefix: Full UUID or prefix (e.g., "54241e7e" from PTY display)

        Returns:
            Task if exactly one match found, None if no match

        Raises:
            ValueError: If prefix matches multiple tasks (ambiguous)
        """
        prefix_lower = prefix.lower()
        with self._lock:
            # Exact match first
            if prefix_lower in self._tasks:
                return self._tasks[prefix_lower]

            # Prefix match
            matches = [
                task
                for task_id, task in self._tasks.items()
                if task_id.lower().startswith(prefix_lower)
            ]

            if len(matches) == 0:
                return None
            if len(matches) == 1:
                return matches[0]
            # Multiple matches - ambiguous
            raise ValueError(
                f"Ambiguous task ID prefix '{prefix}': matches {len(matches)} tasks"
            )

    def update_status(self, task_id: str, status: TaskState) -> Task | None:
        """Update task status"""
        with self._lock:
            if task_id in self._tasks:
                task = self._tasks[task_id]
                task.status = status
                task.updated_at = get_iso_timestamp()
                return task
        return None

    def add_artifact(self, task_id: str, artifact: Artifact) -> Task | None:
        """Add artifact to task"""
        with self._lock:
            if task_id in self._tasks:
                task = self._tasks[task_id]
                task.artifacts.append(artifact)
                task.updated_at = get_iso_timestamp()
                return task
        return None

    def set_error(self, task_id: str, error: TaskErrorModel) -> Task | None:
        """Set error on a task"""
        with self._lock:
            if task_id in self._tasks:
                task = self._tasks[task_id]
                task.error = error
                task.status = "failed"
                task.updated_at = get_iso_timestamp()
                return task
        return None

    def list_tasks(self, context_id: str | None = None) -> list[Task]:
        """List all tasks, optionally filtered by context"""
        with self._lock:
            if context_id:
                return [t for t in self._tasks.values() if t.context_id == context_id]
            return list(self._tasks.values())


# Global task store
task_store = TaskStore()

# Global history manager
_history_db_path = str(Path.home() / ".synapse" / "history" / "history.db")
history_manager = HistoryManager.from_env(db_path=_history_db_path)

# Logger for A2A operations
logger = logging.getLogger(__name__)


async def _send_response_to_sender(
    task: Task,
    sender_endpoint: str,
    self_agent_id: str,
    sender_task_id: str | None = None,
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
    payload = {
        "message": {"role": "agent", "parts": response_parts},
        "metadata": {
            "sender": {
                "sender_id": self_agent_id,
            },
            "response_expected": False,  # Response to response not needed
            "in_reply_to": reply_to_id,  # Reference to sender's task
        },
    }

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
# A2A Router Factory
# ============================================================


def create_a2a_router(
    controller: TerminalController | None,
    agent_type: str,
    port: int,
    submit_seq: str = "\n",
    agent_id: str | None = None,
    registry: AgentRegistry | None = None,
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

    Returns:
        FastAPI APIRouter with A2A endpoints
    """
    # Generate agent_id if not provided
    if agent_id is None:
        agent_id = f"synapse-{agent_type}-{port}"
    router = APIRouter(tags=["Google A2A Compatible"])

    def _send_task_message(
        request: SendMessageRequest, priority: int = 1
    ) -> SendMessageResponse:
        """Create a task and send message to controller with optional priority."""
        # Extract text from message parts
        text_content = extract_text_from_parts(request.message.parts)
        if not text_content:
            raise HTTPException(status_code=400, detail="No text content in message")

        metadata = request.metadata or {}
        in_reply_to = metadata.get("in_reply_to")

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

            task_store.add_artifact(
                full_task_id, Artifact(type="text", data={"content": text_content})
            )
            task_store.update_status(full_task_id, "completed")
            updated_task = task_store.get(full_task_id)
            if not updated_task:
                raise HTTPException(
                    status_code=500, detail="Task disappeared unexpectedly"
                )
            return SendMessageResponse(task=updated_task)

        if not controller:
            raise HTTPException(status_code=503, detail="Agent not running")

        # Create task with metadata (may include sender info)
        task = task_store.create(
            request.message, request.context_id, metadata=request.metadata
        )

        # Update to working
        task_store.update_status(task.id, "working")

        # Priority 5 = interrupt first
        if priority >= 5:
            controller.interrupt()

        # Push sender info to reply stack for simplified reply routing
        # Only store if response_expected=True (sender is waiting for reply)
        response_expected = (
            request.metadata.get("response_expected", False)
            if request.metadata
            else False
        )
        if response_expected:
            sender_info = _extract_sender_info(request.metadata)
            if sender_info.has_reply_target() and sender_info.sender_id:
                reply_stack = get_reply_stack()
                reply_stack.set(
                    sender_info.sender_id, sender_info.to_reply_stack_entry()
                )

        # Send to PTY with A2A prefix
        # Format: A2A: [REPLY EXPECTED] <message> (if response expected)
        # Or: A2A: <message> (if no response expected)
        try:
            prefixed_content = format_a2a_message(
                text_content, response_expected=response_expected
            )
            controller.write(prefixed_content, submit_seq=submit_seq)
        except Exception as e:
            task_store.update_status(task.id, "failed")
            msg = f"Failed to send: {e!s}"
            raise HTTPException(status_code=500, detail=msg) from e

        # Get updated task
        updated_task = task_store.get(task.id)
        if not updated_task:
            raise HTTPException(status_code=500, detail="Task disappeared unexpectedly")
        return SendMessageResponse(task=updated_task)

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
        extensions = {
            "synapse": {
                "agent_id": agent_id,
                "pty_wrapped": True,
                "priority_interrupt": True,
                "at_agent_syntax": True,
                "submit_sequence": repr(submit_seq),
                "addressable_as": [
                    f"@{agent_id}",
                    f"@{agent_type}",
                ],
            },
        }

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
                            "default": 1,
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
        return _send_task_message(request)

    @router.post("/tasks/create", response_model=CreateTaskResponse)
    async def create_task(  # noqa: B008
        request: CreateTaskRequest, _: Any = Depends(require_auth)
    ) -> CreateTaskResponse:
        """
        Create a task without sending to PTY.

        This endpoint is used by --response flag to create a task on the
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

            # Check for input_required state first
            if is_input_required(context):
                task_store.update_status(task_id, "input_required")
            elif synapse_status == "IDLE":
                # Agent is idle, analyze output for errors
                status, error = detect_task_status(context[-CONTEXT_RECENT_SIZE:])

                if status == "failed" and error:
                    # Set error and failed status
                    task_store.set_error(
                        task_id,
                        TaskErrorModel(
                            code=error.code, message=error.message, data=error.data
                        ),
                    )
                    # Dispatch webhook for failed task
                    _dispatch_task_event(
                        "task.failed",
                        {
                            "task_id": task_id,
                            "error": {"code": error.code, "message": error.message},
                        },
                    )
                else:
                    task_store.update_status(task_id, "completed")
                    # Dispatch webhook for completed task
                    _dispatch_task_event("task.completed", {"task_id": task_id})

                # Parse and add output as structured artifacts (before history saving)
                recent_context = context[-CONTEXT_RECENT_SIZE:]
                if recent_context:
                    segments = parse_output(recent_context)
                    if segments:
                        # Add each parsed segment as an artifact
                        for seg in segments:
                            artifact_data: dict[str, Any] = {"content": seg.content}
                            if seg.metadata:
                                artifact_data["metadata"] = seg.metadata
                            task_store.add_artifact(
                                task_id, Artifact(type=seg.type, data=artifact_data)
                            )
                    else:
                        # Fallback to raw text if parsing fails
                        task_store.add_artifact(
                            task_id, Artifact(type="text", data=recent_context)
                        )

                # Save to history after all task updates are complete
                updated_task = task_store.get(task_id)
                if updated_task:
                    _save_task_to_history(
                        updated_task,
                        agent_id=agent_id or "unknown",
                        agent_name=agent_type or "unknown",
                        task_status=updated_task.status,
                    )

                    # Send response back to sender if response_expected
                    metadata = updated_task.metadata or {}
                    response_expected = metadata.get("response_expected", False)
                    sender_info = _extract_sender_info(metadata)

                    if response_expected and sender_info.sender_endpoint:
                        # Send response asynchronously
                        asyncio.create_task(
                            _send_response_to_sender(
                                updated_task,
                                sender_info.sender_endpoint,
                                agent_id or "unknown",
                                sender_task_id=sender_info.sender_task_id,
                            )
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
        request: SendMessageRequest, priority: int = 1, _: Any = Depends(require_auth)
    ) -> SendMessageResponse:
        """
        Send a message with priority (Synapse extension).

        Priority 5 sends SIGINT before the message for interrupt.
        Requires authentication when SYNAPSE_AUTH_ENABLED=true.
        """
        return _send_task_message(request, priority=priority)

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
    # Reply Stack (Synapse Extension)
    # --------------------------------------------------------

    class ReplyTarget(BaseModel):
        """Reply target information."""

        sender_endpoint: str | None = None
        sender_uds_path: str | None = None
        sender_task_id: str | None = None

    @router.get("/reply-stack/get", response_model=ReplyTarget)
    async def get_reply_target(_: Any = Depends(require_auth)) -> ReplyTarget:
        """
        Get a reply target without removing it.

        Returns the most recently received sender endpoint (HTTP and/or UDS) and task ID.
        Does NOT remove the entry - use /reply-stack/pop after successful reply.
        Returns 404 if no reply targets exist.
        Requires authentication when SYNAPSE_AUTH_ENABLED=true.
        """
        reply_stack = get_reply_stack()
        info = reply_stack.peek_last()
        if not info:
            raise HTTPException(status_code=404, detail="No reply target")
        return ReplyTarget(
            sender_endpoint=info.get("sender_endpoint"),
            sender_uds_path=info.get("sender_uds_path"),
            sender_task_id=info.get("sender_task_id"),
        )

    @router.get("/reply-stack/pop", response_model=ReplyTarget)
    async def pop_reply_target(_: Any = Depends(require_auth)) -> ReplyTarget:
        """
        Pop a reply target from the map.

        Returns the first available sender endpoint (HTTP and/or UDS) and task ID.
        Removes the entry after returning.
        Returns 404 if no reply targets exist.
        Requires authentication when SYNAPSE_AUTH_ENABLED=true.
        """
        reply_stack = get_reply_stack()
        info = reply_stack.pop()
        if not info:
            raise HTTPException(status_code=404, detail="No reply target")
        return ReplyTarget(
            sender_endpoint=info.get("sender_endpoint"),
            sender_uds_path=info.get("sender_uds_path"),
            sender_task_id=info.get("sender_task_id"),
        )

    return router
