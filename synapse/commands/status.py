"""Status command: show detailed agent status (#311)."""

from __future__ import annotations

import json
import time
from io import StringIO
from typing import IO, TYPE_CHECKING, Any

from synapse.commands.renderers.rich_renderer import format_elapsed

if TYPE_CHECKING:
    from synapse.file_safety import FileSafetyManager
    from synapse.history import HistoryManager
    from synapse.registry import AgentRegistry
    from synapse.task_board import TaskBoard


class StatusCommand:
    """Show detailed status for a single agent."""

    def __init__(
        self,
        registry: AgentRegistry,
        history_manager: HistoryManager | None = None,
        file_safety_manager: FileSafetyManager | None = None,
        task_board: TaskBoard | None = None,
        output: IO[str] | None = None,
    ) -> None:
        self._registry = registry
        self._history_manager = history_manager
        self._file_safety_manager = file_safety_manager
        self._task_board = task_board
        self._output = output or StringIO()

    def _write(self, text: str) -> None:
        self._output.write(text)

    def _writeln(self, text: str = "") -> None:
        self._output.write(text + "\n")

    def run(self, target: str, json_output: bool = False) -> None:
        """Run the status command.

        Args:
            target: Agent name, ID, type-port, or type to resolve.
            json_output: If True, output as JSON.
        """
        info = self._registry.resolve_agent(target)

        if info is None:
            if json_output:
                self._writeln(json.dumps({"error": f"Agent '{target}' not found"}))
            else:
                self._writeln(f"Error: Agent '{target}' not found.")
            return

        if json_output:
            self._render_json(info)
        else:
            self._render_text(info)

    def _render_json(self, info: dict[str, Any]) -> None:
        """Render agent status as JSON."""
        data: dict[str, Any] = {
            "agent_id": info.get("agent_id"),
            "agent_type": info.get("agent_type"),
            "name": info.get("name"),
            "role": info.get("role"),
            "port": info.get("port"),
            "status": info.get("status"),
            "pid": info.get("pid"),
            "working_dir": info.get("working_dir"),
            "endpoint": info.get("endpoint"),
        }

        # Uptime
        registered_at = info.get("registered_at")
        if registered_at:
            data["uptime_seconds"] = time.time() - registered_at

        # Current task
        preview = info.get("current_task_preview")
        received_at = info.get("task_received_at")
        if preview:
            data["current_task"] = {
                "preview": preview,
                "elapsed_seconds": (time.time() - received_at) if received_at else None,
            }

        # History
        data["recent_messages"] = self._get_history(info)

        # File locks
        data["file_locks"] = self._get_file_locks(info)

        # Task board
        data["assigned_tasks"] = self._get_task_board_tasks(info)

        self._writeln(json.dumps(data, indent=2))

    def _render_text(self, info: dict[str, Any]) -> None:
        """Render agent status as formatted text."""
        agent_id = info.get("agent_id", "-")

        self._writeln(f"=== Agent Status: {info.get('name') or agent_id} ===")
        self._writeln()

        # Agent Info section
        self._writeln("--- Agent Info ---")
        self._writeln(f"  ID:          {agent_id}")
        self._writeln(f"  Type:        {info.get('agent_type', '-')}")
        self._writeln(f"  Name:        {info.get('name') or '-'}")
        self._writeln(f"  Role:        {info.get('role') or '-'}")
        self._writeln(f"  Port:        {info.get('port', '-')}")
        self._writeln(f"  Status:      {info.get('status', '-')}")
        self._writeln(f"  PID:         {info.get('pid', '-')}")
        self._writeln(f"  Working Dir: {info.get('working_dir', '-')}")

        # Uptime
        registered_at = info.get("registered_at")
        if registered_at:
            uptime = time.time() - registered_at
            self._writeln(f"  Uptime:      {format_elapsed(uptime)}")

        self._writeln()

        # Current Task section
        self._writeln("--- Current Task ---")
        preview = info.get("current_task_preview")
        received_at = info.get("task_received_at")
        if preview:
            elapsed_str = ""
            if received_at:
                elapsed = time.time() - received_at
                elapsed_str = f" ({format_elapsed(elapsed)})"
            self._writeln(f"  {preview}{elapsed_str}")
        else:
            self._writeln("  None")

        self._writeln()

        # Recent Messages section
        self._writeln("--- Recent Messages ---")
        messages = self._get_history(info)
        if messages:
            for msg in messages:
                task_id = msg.get("task_id", "-")[:8]
                direction = msg.get("direction", "-")
                sender = msg.get("sender", "-")
                preview_text = msg.get("preview", "-")
                self._writeln(
                    f"  [{task_id}] {direction} from {sender}: {preview_text}"
                )
        else:
            self._writeln("  No recent messages")

        self._writeln()

        # File Locks section
        locks = self._get_file_locks(info)
        if locks:
            self._writeln("--- File Locks ---")
            for lock in locks:
                self._writeln(f"  {lock.get('file_path', '-')}")
            self._writeln()

        # Task Board section
        tasks = self._get_task_board_tasks(info)
        if tasks:
            self._writeln("--- Task Board ---")
            for task in tasks:
                task_id = getattr(task, "id", str(task))[:8]
                subject = getattr(task, "subject", str(task))
                status = getattr(task, "status", "-")
                self._writeln(f"  [{task_id}] {subject} ({status})")
            self._writeln()

    def _get_history(self, info: dict[str, Any]) -> list[dict[str, Any]]:
        """Get recent message history for the agent."""
        if not self._history_manager:
            return []
        try:
            agent_name = info.get("agent_type", "unknown")
            return self._history_manager.list_observations(
                agent_name=agent_name, limit=5
            )
        except Exception:
            return []

    def _get_file_locks(self, info: dict[str, Any]) -> list[dict[str, Any]]:
        """Get file locks held by the agent."""
        if not self._file_safety_manager or not self._file_safety_manager.enabled:
            return []
        try:
            agent_id = info.get("agent_id")
            return (
                self._file_safety_manager.list_locks(agent_name=agent_id)
                if agent_id
                else []
            )
        except Exception:
            return []

    def _get_task_board_tasks(self, info: dict[str, Any]) -> list[Any]:
        """Get tasks assigned to this agent from the task board."""
        if not self._task_board:
            return []
        try:
            agent_id = info.get("agent_id")
            return self._task_board.list_tasks(assignee=agent_id) if agent_id else []
        except Exception:
            return []
