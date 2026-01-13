"""
gRPC Server for Synapse A2A.

Provides high-performance gRPC interface for A2A communication.
Requires optional 'grpc' dependencies: pip install synapse-a2a[grpc]
"""

import asyncio
import logging
import os
import time
from collections.abc import Iterator
from concurrent import futures
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

try:
    import grpc

    from synapse.proto import a2a_pb2_grpc

    GRPC_AVAILABLE = True
except ImportError:
    GRPC_AVAILABLE = False
    a2a_pb2_grpc = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


def check_grpc_available() -> bool:
    """Check if gRPC dependencies are available."""
    return GRPC_AVAILABLE


class GrpcServicerBase:
    """Base class for gRPC servicer when protobuf not available."""

    pass


# Use generated servicer base if available
if a2a_pb2_grpc is not None:
    _ServicerBase: type = a2a_pb2_grpc.A2AServiceServicer
else:
    _ServicerBase = GrpcServicerBase


class GrpcServicer(_ServicerBase):  # type: ignore[misc, unused-ignore]
    """
    gRPC servicer implementation for A2A protocol.

    Implements the A2AService defined in a2a.proto.
    """

    def __init__(
        self,
        controller: Any,
        agent_type: str,
        port: int,
        submit_seq: str = "\n",
        agent_id: str | None = None,
    ) -> None:
        super().__init__()
        self.controller = controller
        self.agent_type = agent_type
        self.port = port
        self.submit_seq = submit_seq
        self.agent_id = agent_id or f"synapse-{agent_type}-{port}"

        # In-memory task store (simplified)
        self._tasks: dict[str, dict[str, Any]] = {}

    def _create_task(
        self,
        message_text: str,
        context_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a new task."""
        task_id = str(uuid4())
        now = datetime.now(timezone.utc)

        task: dict[str, Any] = {
            "id": task_id,
            "context_id": context_id or str(uuid4()),
            "status": "submitted",
            "message": {"role": "user", "text": message_text},
            "artifacts": [],
            "error": None,
            "created_at": now,
            "updated_at": now,
            "metadata": metadata or {},
        }

        self._tasks[task_id] = task
        return task

    def _update_task_status(self, task_id: str, status: str) -> None:
        """Update task status."""
        if task_id in self._tasks:
            self._tasks[task_id]["status"] = status
            self._tasks[task_id]["updated_at"] = datetime.now(timezone.utc)

    def get_agent_card(self) -> dict[str, Any]:
        """Get agent card for discovery."""
        protocol = "https" if os.environ.get("SYNAPSE_USE_HTTPS") else "http"
        return {
            "name": f"Synapse {self.agent_type.title()} Agent",
            "description": "CLI agent wrapped with Synapse A2A (via gRPC)",
            "url": f"{protocol}://localhost:{self.port}",
            "version": "1.0.0",
            "capabilities": {
                "streaming": True,
                "push_notifications": True,
                "input_modes": ["text"],
                "output_modes": ["text"],
            },
            "skills": [
                {
                    "id": "general",
                    "name": "General Assistant",
                    "description": f"General-purpose {self.agent_type} assistant",
                    "tags": ["general", "assistant"],
                }
            ],
        }

    def send_message(
        self,
        message_text: str,
        context_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send a message to the agent."""
        if not self.controller:
            raise RuntimeError("Agent not running")

        task = self._create_task(message_text, context_id, metadata)
        self._update_task_status(task["id"], "working")

        # Send to PTY
        try:
            sender_id = (metadata or {}).get("sender", {}).get("sender_id", "unknown")
            prefixed_content = f"[A2A:{task['id'][:8]}:{sender_id}] {message_text}"
            self.controller.write(prefixed_content, submit_seq=self.submit_seq)
        except Exception as e:
            self._update_task_status(task["id"], "failed")
            task["error"] = {"code": "SEND_FAILED", "message": str(e)}

        return task

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        """Get task by ID."""
        task = self._tasks.get(task_id)

        if task and self.controller and task["status"] == "working":
            synapse_status = self.controller.status
            if synapse_status == "IDLE":
                self._update_task_status(task_id, "completed")
                # Add context as artifact
                context = self.controller.get_context()[-2000:]
                if context:
                    task["artifacts"].append(
                        {
                            "type": "text",
                            "data": {"content": context},
                        }
                    )
                task = self._tasks.get(task_id)

        return task

    def list_tasks(self, context_id: str | None = None) -> list:
        """List all tasks."""
        tasks = list(self._tasks.values())
        if context_id:
            tasks = [t for t in tasks if t.get("context_id") == context_id]
        return tasks

    def cancel_task(self, task_id: str) -> dict[str, Any]:
        """Cancel a task."""
        task = self._tasks.get(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        if task["status"] not in ["submitted", "working"]:
            raise ValueError(f"Cannot cancel task in {task['status']} state")

        if self.controller:
            self.controller.interrupt()

        self._update_task_status(task_id, "canceled")
        return {"status": "canceled", "task_id": task_id}

    def subscribe(self, task_id: str) -> Iterator[dict[str, Any]]:
        """
        Subscribe to task output stream.

        Yields events until task completes.
        """
        task = self._tasks.get(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        last_len = 0
        last_status = task["status"]

        while True:
            task = self._tasks.get(task_id)
            if not task:
                break

            # Check for new output
            if self.controller:
                context = self.controller.get_context()
                if len(context) > last_len:
                    new_content = context[last_len:]
                    last_len = len(context)
                    yield {
                        "event_type": "output",
                        "data": new_content,
                    }

            # Check for status change
            if task["status"] != last_status:
                last_status = task["status"]
                yield {
                    "event_type": "status",
                    "data": last_status,
                }

            # Check for terminal state
            if task["status"] in ["completed", "failed", "canceled"]:
                yield {
                    "event_type": "done",
                    "task": task,
                }
                break

            # Small delay
            time.sleep(0.5)

    # =========================================================================
    # gRPC Service Methods (PascalCase - required by generated servicer)
    # These wrap the snake_case methods for gRPC compatibility
    # =========================================================================

    def GetAgentCard(self, request: Any, context: Any) -> dict[str, Any]:  # noqa: N802
        """gRPC: Get agent card for discovery."""
        return self.get_agent_card()

    def SendMessage(self, request: Any, context: Any) -> dict[str, Any]:  # noqa: N802
        """gRPC: Send a message to the agent."""
        # Extract message text from protobuf
        message_text = ""
        if hasattr(request, "message") and request.message:
            for part in request.message.parts:
                if part.HasField("text_part"):
                    message_text += part.text_part.text

        context_id = request.context_id if request.context_id else None
        metadata = None
        if request.HasField("metadata"):
            metadata = dict(request.metadata.fields)

        task = self.send_message(message_text, context_id, metadata)
        return {"task": task}

    def GetTask(self, request: Any, context: Any) -> dict[str, Any]:  # noqa: N802
        """gRPC: Get task by ID."""
        task = self.get_task(request.task_id)
        return {"task": task}

    def ListTasks(self, request: Any, context: Any) -> dict[str, Any]:  # noqa: N802
        """gRPC: List all tasks."""
        context_id = request.context_id if request.context_id else None
        tasks = self.list_tasks(context_id)
        return {"tasks": tasks}

    def CancelTask(self, request: Any, context: Any) -> dict[str, Any]:  # noqa: N802
        """gRPC: Cancel a task."""
        result = self.cancel_task(request.task_id)
        return result

    def Subscribe(self, request: Any, context: Any) -> Iterator[dict[str, Any]]:  # noqa: N802
        """gRPC: Subscribe to task output stream."""
        yield from self.subscribe(request.task_id)

    def SendPriorityMessage(self, request: Any, context: Any) -> dict[str, Any]:  # noqa: N802
        """gRPC: Send a priority message."""
        message_text = ""
        if hasattr(request, "message") and request.message:
            for part in request.message.parts:
                if part.HasField("text_part"):
                    message_text += part.text_part.text

        context_id = request.context_id if request.context_id else None
        metadata = {"priority": request.priority}
        if request.HasField("metadata"):
            metadata.update(dict(request.metadata.fields))

        task = self.send_message(message_text, context_id, metadata)
        return {"task": task}


def create_grpc_server(
    controller: Any,
    agent_type: str,
    port: int,
    grpc_port: int | None = None,
    submit_seq: str = "\n",
    agent_id: str | None = None,
    max_workers: int = 10,
) -> tuple[Any, GrpcServicer] | tuple[None, None]:
    """
    Create a gRPC server for A2A communication.

    Args:
        controller: TerminalController instance
        agent_type: Agent type (claude, codex, gemini, etc.)
        port: REST API port (for agent card URL)
        grpc_port: gRPC server port (default: port + 1)
        submit_seq: Submit sequence for the CLI
        agent_id: Unique agent ID
        max_workers: Maximum worker threads

    Returns:
        Tuple of (server, servicer) if gRPC available, else (None, None)
    """
    if not GRPC_AVAILABLE:
        logger.warning(
            "gRPC not available. Install with: pip install synapse-a2a[grpc]"
        )
        return None, None

    grpc_port = grpc_port or (port + 1)

    servicer = GrpcServicer(
        controller=controller,
        agent_type=agent_type,
        port=port,
        submit_seq=submit_seq,
        agent_id=agent_id,
    )

    # Create server
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=max_workers))

    # Register the generated servicer
    if a2a_pb2_grpc is not None:
        a2a_pb2_grpc.add_A2AServiceServicer_to_server(servicer, server)

    server.add_insecure_port(f"[::]:{grpc_port}")

    logger.info(f"gRPC server configured on port {grpc_port}")

    return server, servicer


async def serve_grpc(
    controller: Any,
    agent_type: str,
    port: int,
    grpc_port: int | None = None,
    submit_seq: str = "\n",
    agent_id: str | None = None,
) -> None:
    """
    Start the gRPC server.

    Args:
        controller: TerminalController instance
        agent_type: Agent type
        port: REST API port
        grpc_port: gRPC server port
        submit_seq: Submit sequence
        agent_id: Agent ID
    """
    server, servicer = create_grpc_server(
        controller=controller,
        agent_type=agent_type,
        port=port,
        grpc_port=grpc_port,
        submit_seq=submit_seq,
        agent_id=agent_id,
    )

    if server is None:
        return

    grpc_port = grpc_port or (port + 1)

    server.start()
    logger.info(f"gRPC server started on port {grpc_port}")

    try:
        # Keep running until interrupted
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        server.stop(grace=5)
        logger.info("gRPC server stopped")
