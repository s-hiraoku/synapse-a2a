"""
Task Store — In-Memory Task Storage

Thread-safe task store for A2A protocol tasks.
Extracted from synapse/a2a_compat.py for modularity.
"""

import threading
from typing import Any, Literal
from uuid import uuid4

from synapse.a2a_models import (
    Artifact,
    Message,
    Task,
    TaskErrorModel,
    TaskState,
)
from synapse.utils import get_iso_timestamp

# Metadata key constants used by TaskStore
_EXPLICIT_REPLY_RECORDED_METADATA_KEY = "_explicit_reply_recorded"
ERROR_CODE_MISSING_REPLY = "MISSING_REPLY"
ERROR_CODE_REPLY_FAILED = "REPLY_FAILED"


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

            if not matches:
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

    def update_metadata(self, task_id: str, key: str, value: Any) -> Task | None:
        """Thread-safe metadata update for a single key."""
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return None
            metadata = task.metadata or {}
            metadata[key] = value
            task.metadata = metadata
            task.updated_at = get_iso_timestamp()
            return task

    def claim_finalization(self, task_id: str) -> Task | None:
        """Claim exclusive rights to finalize a working task.

        Also checks _explicit_reply_recorded under the same lock to avoid
        racing with the explicit reply endpoint.
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if not task or task.status != "working":
                return None
            metadata = task.metadata or {}
            if metadata.get("_finalization_claimed"):
                return None
            if metadata.get(_EXPLICIT_REPLY_RECORDED_METADATA_KEY):
                return None
            metadata["_finalization_claimed"] = True
            task.metadata = metadata
            task.updated_at = get_iso_timestamp()
            return task

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

    def record_explicit_reply(
        self,
        task_id: str,
        message: str,
        status: Literal["completed", "failed"] = "completed",
        error: TaskErrorModel | None = None,
    ) -> Task | None:
        """Atomically record an explicit reply on a task."""
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return None
            # Guard: don't overwrite if finalization already claimed or terminal
            metadata = task.metadata or {}
            if metadata.get("_finalization_claimed"):
                return None
            if task.status in ("completed", "failed", "canceled"):
                return None
            metadata[_EXPLICIT_REPLY_RECORDED_METADATA_KEY] = True
            task.metadata = metadata
            if status == "failed":
                task.artifacts = []
                task.error = error or TaskErrorModel(
                    code=ERROR_CODE_REPLY_FAILED, message=message
                )
                task.status = "failed"
            else:
                task.artifacts = [Artifact(type="text", data={"content": message})]
                task.error = None
                task.status = "completed"
            task.updated_at = get_iso_timestamp()
            return task

    def mark_missing_reply_if_unreplied(self, task_id: str) -> Task | None:
        """Fail a task as missing-reply only if no explicit reply was recorded.

        Only converts to MISSING_REPLY when the task completed normally
        (no existing error), so _finalize_working_task failures are preserved.
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return None
            if task.status != "completed":
                return task
            metadata = task.metadata or {}
            if metadata.get(_EXPLICIT_REPLY_RECORDED_METADATA_KEY):
                return task
            if task.artifacts:
                return task
            if task.error is not None:
                return task
            task.artifacts = []
            task.error = TaskErrorModel(
                code=ERROR_CODE_MISSING_REPLY,
                message="Receiver completed without explicit synapse reply",
            )
            task.status = "failed"
            task.updated_at = get_iso_timestamp()
            return task

    def list_tasks(self, context_id: str | None = None) -> list[Task]:
        """List all tasks, optionally filtered by context"""
        with self._lock:
            if context_id:
                return [t for t in self._tasks.values() if t.context_id == context_id]
            return list(self._tasks.values())


# Global task store
task_store = TaskStore()
