"""
Google A2A Protocol Data Models

Pydantic models for the Google A2A protocol compatibility layer.
Extracted from synapse/a2a_compat.py for modularity.
"""

from typing import Any, Literal

from pydantic import BaseModel

# Task state mapping from Google A2A spec
TaskState = Literal[
    "submitted",  # Task received
    "working",  # Task in progress
    "input_required",  # Waiting for additional input
    "completed",  # Task finished successfully
    "failed",  # Task failed
    "canceled",  # Task was canceled
]


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


class HistoryUpdateRequest(BaseModel):
    """Request to update sender-side history status."""

    task_id: str
    status: Literal["completed", "failed", "canceled"]
    output_summary: str | None = None


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
