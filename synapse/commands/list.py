"""List command implementation for Synapse CLI."""

from __future__ import annotations

import argparse
import os
from collections.abc import Callable
from typing import Any, Protocol

from synapse.file_safety import FileSafetyManager
from synapse.port_manager import PORT_RANGES
from synapse.registry import AgentRegistry


class _TimeModule(Protocol):
    """Protocol for time module interface."""

    def strftime(self, format: str) -> str: ...
    def sleep(self, seconds: float) -> None: ...


class ListCommand:
    """List running agents (with optional watch mode)."""

    def __init__(
        self,
        registry_factory: Callable[[], AgentRegistry],
        is_process_alive: Callable[[int], bool],
        is_port_open: Callable[..., bool],
        clear_screen: Callable[[], None],
        time_module: _TimeModule | Any,
        print_func: Callable[[str], None],
    ) -> None:
        self._registry_factory = registry_factory
        self._is_process_alive = is_process_alive
        self._is_port_open = is_port_open
        self._clear_screen = clear_screen
        self._time = time_module
        self._print = print_func

    def _format_empty_message(self) -> str:
        """Format the 'no agents running' message with port ranges."""
        lines = ["No agents running.", "", "Port ranges:"]
        for agent_type, (start, end) in sorted(PORT_RANGES.items()):
            lines.append(f"  {agent_type}: {start}-{end}")
        return "\n".join(lines)

    def _render_agent_table(self, registry: AgentRegistry) -> str:
        """
        Render the agent table output.

        Args:
            registry: AgentRegistry instance

        Returns:
            str: Formatted table output
        """
        agents = registry.list_agents()

        if not agents:
            return self._format_empty_message()

        file_safety = FileSafetyManager.from_env()
        show_file_safety = file_safety.enabled

        lines = []
        if show_file_safety:
            header = (
                f"{'TYPE':<10} {'PORT':<8} {'STATUS':<12} {'PID':<8} "
                f"{'WORKING_DIR':<50} {'EDITING FILE':<30} ENDPOINT"
            )
        else:
            header = (
                f"{'TYPE':<10} {'PORT':<8} {'STATUS':<12} {'PID':<8} "
                f"{'WORKING_DIR':<50} ENDPOINT"
            )
        lines.append(header)
        lines.append("-" * len(header))

        live_agents = False
        for agent_id, info in agents.items():
            # Verify agent is still alive (PID check + port check)
            pid = info.get("pid")
            port = info.get("port")
            status = info.get("status", "-")

            # Check 1: PID must be alive
            if pid and not self._is_process_alive(pid):
                registry.unregister(agent_id)
                continue

            # Check 2: Port must be open (agent server responding)
            # Skip port check for PROCESSING agents (server may still be starting)
            if (
                status != "PROCESSING"
                and port
                and not self._is_port_open("localhost", port, timeout=0.5)
            ):
                registry.unregister(agent_id)
                continue

            live_agents = True

            # Build base row fields
            base_row = (
                f"{info.get('agent_type', 'unknown'):<10} "
                f"{info.get('port', '-'):<8} "
                f"{status:<12} "
                f"{pid or '-':<8} "
                f"{info.get('working_dir', '-'):<50} "
            )

            if show_file_safety:
                # Use agent_type for filtering (e.g., "claude", "gemini")
                agent_type = info.get("agent_type", "")
                locks = file_safety.list_locks(
                    agent_type=agent_type, include_stale=False
                )
                editing_file = "-"
                if locks:
                    file_path = locks[0].get("file_path")
                    if file_path:
                        editing_file = os.path.basename(file_path)
                lines.append(
                    f"{base_row}{editing_file:<30} {info.get('endpoint', '-')}"
                )
            else:
                lines.append(f"{base_row}{info.get('endpoint', '-')}")

        # If all agents were dead, show empty registry message
        if not live_agents:
            return self._format_empty_message()

        # Check for stale locks and add warning
        if show_file_safety:
            stale_locks = file_safety.get_stale_locks()
            if stale_locks:
                lines.append("")
                lines.append(
                    f"Warning: {len(stale_locks)} stale lock(s) from dead processes detected."
                )
                lines.append(
                    "Run 'synapse file-safety cleanup-locks' to clean them up."
                )

        return "\n".join(lines)

    def run(self, args: argparse.Namespace) -> None:
        """List running agents (with optional watch mode)."""
        registry = self._registry_factory()
        watch_mode = getattr(args, "watch", False)
        interval = getattr(args, "interval", 2.0)

        if not watch_mode:
            # Normal mode: single output
            self._print(self._render_agent_table(registry))
            return

        # Watch mode: continuous refresh
        self._print("Watch mode: Press Ctrl+C to exit\n")

        # Get version for display
        try:
            from importlib.metadata import version

            pkg_version = version("synapse-a2a")
        except Exception:
            pkg_version = "unknown"

        try:
            while True:
                self._clear_screen()
                self._print(
                    f"Synapse A2A v{pkg_version} - Agent List (refreshing every {interval}s)"
                )
                self._print(f"Last updated: {self._time.strftime('%Y-%m-%d %H:%M:%S')}")
                self._print("")
                self._print(self._render_agent_table(registry))
                self._time.sleep(interval)
        except KeyboardInterrupt:
            self._print("\n\nExiting watch mode...")
            raise SystemExit(0) from None
