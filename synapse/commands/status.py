"""Status command: show detailed agent status (#311)."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections import Counter
from collections.abc import Callable
from io import StringIO
from typing import IO, TYPE_CHECKING, Any

from synapse.commands.renderers.rich_renderer import format_elapsed

if TYPE_CHECKING:
    from synapse.file_safety import FileSafetyManager
    from synapse.history import HistoryManager
    from synapse.registry import AgentRegistry


class StatusCommand:
    """Show detailed status for a single agent."""

    def __init__(
        self,
        registry: AgentRegistry,
        history_manager: HistoryManager | None = None,
        file_safety_manager: FileSafetyManager | None = None,
        output: IO[str] | None = None,
        debug_waiting_fetcher: Callable[[str], dict[str, Any]] | None = None,
    ) -> None:
        self._registry = registry
        self._history_manager = history_manager
        self._file_safety_manager = file_safety_manager
        self._output = output or StringIO()
        self._debug_waiting_fetcher = debug_waiting_fetcher or self._http_get_json

    def _write(self, text: str) -> None:
        self._output.write(text)

    def _writeln(self, text: str = "") -> None:
        self._output.write(text + "\n")

    def run(
        self, target: str, json_output: bool = False, debug_waiting: bool = False
    ) -> None:
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
            if debug_waiting:
                self._render_waiting_debug(info)

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
        if "renderer_available" in info:
            data["renderer_available"] = info.get("renderer_available")

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
        self._writeln(f"  Status:      {self._format_status(info)}")
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

    def _format_status(self, info: dict[str, Any]) -> str:
        status = str(info.get("status", "-"))
        renderer_available = info.get("renderer_available")
        if renderer_available is False:
            return f"{status} (renderer: off)"
        if renderer_available is True:
            return f"{status} (renderer: on)"
        return status

    def _http_get_json(self, url: str) -> dict[str, Any]:
        with urllib.request.urlopen(url, timeout=3.0) as response:
            payload = response.read().decode("utf-8")
        data = json.loads(payload)
        return data if isinstance(data, dict) else {}

    def _render_waiting_debug(self, info: dict[str, Any]) -> None:
        endpoint = info.get("endpoint")
        if not endpoint:
            self._writeln("--- WAITING Detection Debug ---")
            self._writeln("  No endpoint registered")
            return

        self._writeln("--- WAITING Detection Debug ---")
        try:
            payload = self._debug_waiting_fetcher(f"{endpoint}/debug/waiting")
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            self._writeln(f"  Failed to fetch debug data: {exc}")
            return

        attempts = payload.get("attempts") or []
        if not isinstance(attempts, list):
            attempts = []

        total = len(attempts)
        matched = sum(1 for item in attempts if item.get("pattern_matched") is True)
        ratio = (matched / total * 100.0) if total else 0.0
        path_counts = Counter(str(item.get("path_used") or "-") for item in attempts)
        confidence_counts = Counter(
            str(item.get("confidence", 0.0)) for item in attempts
        )
        idle_gate_drops = sum(
            1
            for item in attempts
            if item.get("pattern_matched") is True
            and item.get("idle_gate_passed") is not True
        )

        self._writeln(f"  Renderer: {self._renderer_label(payload)}")
        self._writeln(f"  Total attempts: {total}")
        self._writeln(f"  Pattern matched: {matched}/{total} ({ratio:.1f}%)")
        self._writeln(f"  Path usage: {self._format_counter(path_counts)}")
        self._writeln(f"  Confidence: {self._format_counter(confidence_counts)}")
        self._writeln(f"  Idle gate drops: {idle_gate_drops}")

        if not attempts:
            self._writeln("  No recent attempts")
            return

        self._writeln()
        self._writeln("  Recent attempts:")
        for item in attempts:
            path = item.get("path_used") or "-"
            source = item.get("pattern_source") or "-"
            confidence = item.get("confidence", 0.0)
            idle = "yes" if item.get("idle_gate_passed") is True else "no"
            matched_text = "yes" if item.get("pattern_matched") is True else "no"
            hex_prefix = item.get("new_data_hex_prefix") or "-"
            tail = str(item.get("rendered_text_tail") or "").replace("\n", "\\n")
            self._writeln(
                f"  - {path} {source} {confidence} idle={idle} matched={matched_text}"
            )
            self._writeln(f"    hex: {hex_prefix}")
            self._writeln(f"    tail: {tail}")

    def _renderer_label(self, payload: dict[str, Any]) -> str:
        renderer_available = payload.get("renderer_available")
        if renderer_available is True:
            return "on"
        if renderer_available is False:
            return "off"
        return "unknown"

    def _format_counter(self, counter: Counter[str]) -> str:
        if not counter:
            return "-"
        return ", ".join(f"{key}={counter[key]}" for key in sorted(counter))

    def _get_history(self, info: dict[str, Any]) -> list[dict[str, Any]]:
        """Get recent message history for the agent."""
        if not self._history_manager:
            return []
        try:
            agent_name = info.get("agent_type", "unknown")
            return self._history_manager.list_observations(
                agent_name=agent_name, limit=5
            )
        except Exception:  # broad catch: history lookup is optional status info
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
        except Exception:  # broad catch: lock lookup is optional status info
            return []
