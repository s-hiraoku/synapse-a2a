"""
Google A2A Protocol Compatibility Layer

This module provides Google A2A protocol compatible endpoints while
maintaining Synapse A2A's unique PTY-wrapping capabilities.

Google A2A Spec: https://a2a-protocol.org/latest/specification/
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime
from uuid import uuid4
import threading

from synapse.a2a_client import get_client, ExternalAgent, A2ATask

# Task state mapping from Google A2A spec
TaskState = Literal[
    "submitted",      # Task received
    "working",        # Task in progress
    "input_required", # Waiting for additional input
    "completed",      # Task finished successfully
    "failed",         # Task failed
    "canceled",       # Task was canceled
]


def map_synapse_status_to_a2a(synapse_status: str) -> TaskState:
    """Map Synapse status to Google A2A task state"""
    mapping = {
        "STARTING": "submitted",
        "BUSY": "working",
        "IDLE": "completed",
        "NOT_STARTED": "submitted",
    }
    return mapping.get(synapse_status, "working")


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
    file: Dict[str, Any]


class DataPart(BaseModel):
    """Structured data part"""
    type: Literal["data"] = "data"
    data: Dict[str, Any]


# Union type for parts
Part = TextPart | FilePart | DataPart


class Message(BaseModel):
    """A2A Message with role and parts"""
    role: Literal["user", "agent"] = "user"
    parts: List[TextPart | FilePart | DataPart]


class Artifact(BaseModel):
    """Task output artifact"""
    type: str = "text"
    data: Any


class Task(BaseModel):
    """A2A Task with lifecycle"""
    id: str
    status: TaskState
    message: Optional[Message] = None
    artifacts: List[Artifact] = []
    created_at: str
    updated_at: str
    context_id: Optional[str] = None
    metadata: Dict[str, Any] = {}


class SendMessageRequest(BaseModel):
    """Request to send a message"""
    message: Message
    context_id: Optional[str] = None
    metadata: Dict[str, Any] = {}


class SendMessageResponse(BaseModel):
    """Response after sending a message"""
    task: Task


class AgentSkill(BaseModel):
    """Agent capability/skill definition"""
    id: str
    name: str
    description: str
    parameters: Optional[Dict[str, Any]] = None


class AgentCapabilities(BaseModel):
    """Agent capabilities declaration"""
    streaming: bool = False
    pushNotifications: bool = False
    multiTurn: bool = True


class AgentCard(BaseModel):
    """Google A2A Agent Card for discovery"""
    name: str
    description: str
    url: str
    version: str = "1.0.0"
    capabilities: AgentCapabilities
    skills: List[AgentSkill] = []
    securitySchemes: Dict[str, Any] = {}
    # Synapse A2A extensions
    extensions: Dict[str, Any] = {}


# ============================================================
# Task Store (In-Memory)
# ============================================================

class TaskStore:
    """Thread-safe in-memory task storage"""

    def __init__(self):
        self._tasks: Dict[str, Task] = {}
        self._lock = threading.Lock()

    def create(
        self,
        message: Message,
        context_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Task:
        """Create a new task with optional metadata (including sender info)"""
        now = datetime.utcnow().isoformat() + "Z"
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

    def get(self, task_id: str) -> Optional[Task]:
        """Get a task by ID"""
        with self._lock:
            return self._tasks.get(task_id)

    def update_status(self, task_id: str, status: TaskState) -> Optional[Task]:
        """Update task status"""
        with self._lock:
            if task_id in self._tasks:
                task = self._tasks[task_id]
                task.status = status
                task.updated_at = datetime.utcnow().isoformat() + "Z"
                return task
        return None

    def add_artifact(self, task_id: str, artifact: Artifact) -> Optional[Task]:
        """Add artifact to task"""
        with self._lock:
            if task_id in self._tasks:
                task = self._tasks[task_id]
                task.artifacts.append(artifact)
                task.updated_at = datetime.utcnow().isoformat() + "Z"
                return task
        return None

    def list_tasks(self, context_id: Optional[str] = None) -> List[Task]:
        """List all tasks, optionally filtered by context"""
        with self._lock:
            if context_id:
                return [t for t in self._tasks.values() if t.context_id == context_id]
            return list(self._tasks.values())


# Global task store
task_store = TaskStore()


# ============================================================
# External Agent Models
# ============================================================

class DiscoverAgentRequest(BaseModel):
    """Request to discover an external agent"""
    url: str
    alias: Optional[str] = None


class ExternalAgentInfo(BaseModel):
    """External agent information"""
    name: str
    alias: str
    url: str
    description: str = ""
    capabilities: Dict[str, Any] = {}
    skills: List[Dict[str, Any]] = []
    added_at: str = ""
    last_seen: Optional[str] = None


class SendExternalMessageRequest(BaseModel):
    """Request to send message to external agent"""
    message: str
    wait_for_completion: bool = False
    timeout: int = 60


class ExternalTaskResponse(BaseModel):
    """Response from external agent task"""
    id: str
    status: str
    artifacts: List[Dict[str, Any]] = []


# ============================================================
# A2A Router Factory
# ============================================================

def create_a2a_router(
    controller,
    agent_type: str,
    port: int,
    submit_seq: str = "\n",
    agent_id: str = None,
    registry = None
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

    # --------------------------------------------------------
    # Agent Card (Discovery)
    # --------------------------------------------------------

    @router.get("/.well-known/agent.json", response_model=AgentCard)
    async def get_agent_card():
        """
        Return Agent Card for discovery.

        This endpoint follows the Google A2A specification for agent discovery.
        Agent Card is a "business card" - it only contains discovery information,
        not internal instructions (which are sent via A2A Task at startup).
        """
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
            url=f"http://localhost:{port}",
            version="1.0.0",
            capabilities=AgentCapabilities(
                streaming=False,  # Not yet supported
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
                            "default": 1
                        }
                    }
                ),
            ],
            securitySchemes={},  # No auth for local use
            extensions=extensions,
        )

    # --------------------------------------------------------
    # Task Management
    # --------------------------------------------------------

    @router.post("/tasks/send", response_model=SendMessageResponse)
    async def send_message(request: SendMessageRequest):
        """
        Send a message to the agent (Google A2A compatible).

        Creates a task and sends the message content to the CLI via PTY.
        """
        if not controller:
            raise HTTPException(status_code=503, detail="Agent not running")

        # Extract text from message parts
        text_content = ""
        for part in request.message.parts:
            if isinstance(part, TextPart) or (hasattr(part, 'type') and part.type == "text"):
                text_content += part.text + "\n"

        text_content = text_content.strip()
        if not text_content:
            raise HTTPException(status_code=400, detail="No text content in message")

        # Create task with metadata (may include sender info)
        task = task_store.create(
            request.message,
            request.context_id,
            metadata=request.metadata
        )

        # Update to working
        task_store.update_status(task.id, "working")

        # Send to PTY with A2A task reference for sender identification
        try:
            # Extract sender_id if available
            sender_id = request.metadata.get("sender", {}).get("sender_id", "unknown") if request.metadata else "unknown"
            # Format: [A2A:task_id:sender_id] message
            # Reply instructions are in initial Task, not per-message
            prefixed_content = f"[A2A:{task.id[:8]}:{sender_id}] {text_content}"
            controller.write(prefixed_content, submit_seq=submit_seq)
        except Exception as e:
            task_store.update_status(task.id, "failed")
            raise HTTPException(status_code=500, detail=f"Failed to send: {str(e)}")

        # Get updated task
        task = task_store.get(task.id)
        return SendMessageResponse(task=task)

    @router.get("/tasks/{task_id}", response_model=Task)
    async def get_task(task_id: str):
        """
        Get task status and results.

        Maps Synapse IDLE/BUSY status to A2A task states.
        """
        task = task_store.get(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        # Update status based on controller state
        if controller and task.status == "working":
            synapse_status = controller.status
            a2a_status = map_synapse_status_to_a2a(synapse_status)

            if a2a_status == "completed":
                task_store.update_status(task_id, "completed")
                # Add output as artifact
                context = controller.get_context()[-2000:]
                if context:
                    task_store.add_artifact(task_id, Artifact(
                        type="text",
                        data=context
                    ))

            task = task_store.get(task_id)

        return task

    @router.get("/tasks", response_model=List[Task])
    async def list_tasks(context_id: Optional[str] = None):
        """List all tasks, optionally filtered by context."""
        return task_store.list_tasks(context_id)

    @router.post("/tasks/{task_id}/cancel")
    async def cancel_task(task_id: str):
        """
        Cancel a running task.

        Sends SIGINT to the CLI process (Synapse extension).
        """
        task = task_store.get(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        if task.status not in ["submitted", "working"]:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot cancel task in {task.status} state"
            )

        # Interrupt the CLI
        if controller:
            controller.interrupt()

        task_store.update_status(task_id, "canceled")
        return {"status": "canceled", "task_id": task_id}

    # --------------------------------------------------------
    # Synapse Extensions (Priority Interrupt)
    # --------------------------------------------------------

    @router.post("/tasks/send-priority", response_model=SendMessageResponse)
    async def send_priority_message(
        request: SendMessageRequest,
        priority: int = 1
    ):
        """
        Send a message with priority (Synapse extension).

        Priority 5 sends SIGINT before the message for interrupt.
        """
        if not controller:
            raise HTTPException(status_code=503, detail="Agent not running")

        # Extract text
        text_content = ""
        for part in request.message.parts:
            if isinstance(part, TextPart) or (hasattr(part, 'type') and part.type == "text"):
                text_content += part.text + "\n"

        text_content = text_content.strip()
        if not text_content:
            raise HTTPException(status_code=400, detail="No text content in message")

        # Create task with metadata (may include sender info)
        task = task_store.create(
            request.message,
            request.context_id,
            metadata=request.metadata
        )
        task_store.update_status(task.id, "working")

        # Priority 5 = interrupt first
        if priority >= 5:
            controller.interrupt()

        # Send to PTY with A2A task reference for sender identification
        try:
            # Extract sender_id if available
            sender_id = request.metadata.get("sender", {}).get("sender_id", "unknown") if request.metadata else "unknown"
            # Format: [A2A:task_id:sender_id] message
            # Reply instructions are in initial Task, not per-message
            prefixed_content = f"[A2A:{task.id[:8]}:{sender_id}] {text_content}"
            controller.write(prefixed_content, submit_seq=submit_seq)
        except Exception as e:
            task_store.update_status(task.id, "failed")
            raise HTTPException(status_code=500, detail=f"Failed to send: {str(e)}")

        task = task_store.get(task.id)
        return SendMessageResponse(task=task)

    # --------------------------------------------------------
    # External Agent Management (Google A2A Client)
    # --------------------------------------------------------

    @router.post("/external/discover", response_model=ExternalAgentInfo)
    async def discover_external_agent(request: DiscoverAgentRequest):
        """
        Discover and register an external Google A2A agent.

        Fetches the Agent Card from the given URL and registers the agent.
        """
        client = get_client()
        agent = client.discover(request.url, alias=request.alias)

        if not agent:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to discover agent at {request.url}"
            )

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

    @router.get("/external/agents", response_model=List[ExternalAgentInfo])
    async def list_external_agents():
        """
        List all registered external agents.
        """
        client = get_client()
        agents = client.list_agents()

        return [
            ExternalAgentInfo(
                name=agent.name,
                alias=agent.alias,
                url=agent.url,
                description=agent.description,
                capabilities=agent.capabilities,
                skills=agent.skills,
                added_at=agent.added_at,
                last_seen=agent.last_seen,
            )
            for agent in agents
        ]

    @router.get("/external/agents/{alias}", response_model=ExternalAgentInfo)
    async def get_external_agent(alias: str):
        """
        Get details of a specific external agent.
        """
        client = get_client()
        agent = client.registry.get(alias)

        if not agent:
            raise HTTPException(status_code=404, detail=f"Agent '{alias}' not found")

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

    @router.delete("/external/agents/{alias}")
    async def remove_external_agent(alias: str):
        """
        Remove an external agent from the registry.
        """
        client = get_client()

        if not client.remove_agent(alias):
            raise HTTPException(status_code=404, detail=f"Agent '{alias}' not found")

        return {"status": "removed", "alias": alias}

    @router.post("/external/agents/{alias}/send", response_model=ExternalTaskResponse)
    async def send_to_external_agent(alias: str, request: SendExternalMessageRequest):
        """
        Send a message to an external Google A2A agent.

        Uses the Google A2A protocol to communicate with the external agent.
        """
        client = get_client()
        agent = client.registry.get(alias)

        if not agent:
            raise HTTPException(status_code=404, detail=f"Agent '{alias}' not found")

        task = client.send_message(
            alias,
            request.message,
            wait_for_completion=request.wait_for_completion,
            timeout=request.timeout
        )

        if not task:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to send message to {alias}"
            )

        return ExternalTaskResponse(
            id=task.id,
            status=task.status,
            artifacts=task.artifacts,
        )

    return router
