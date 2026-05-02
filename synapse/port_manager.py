"""Port management for Synapse A2A multi-instance support."""

import logging
import os
import socket
import time
from typing import TYPE_CHECKING

from synapse.registry import is_process_running, resolve_uds_path
from synapse.status import PROCESSING

if TYPE_CHECKING:
    from synapse.registry import AgentRegistry

logger = logging.getLogger(__name__)


class PortExhaustionError(RuntimeError):
    """Raised when no free port is available in an agent type's port range.

    Distinguished from a generic registry write error so callers (cli.py
    spawn path) can present the existing exhaustion-help text without
    catching unrelated runtime errors.
    """


# Port range definitions (agent_type -> (start, end) inclusive)
PORT_RANGES: dict[str, tuple[int, int]] = {
    "claude": (8100, 8109),
    "gemini": (8110, 8119),
    "codex": (8120, 8129),
    "opencode": (8130, 8139),
    "copilot": (8140, 8149),
    "admin": (8150, 8159),
    "dummy": (8190, 8199),
}

DEFAULT_PORT_RANGE_SIZE = 10
DEFAULT_BASE_PORT = 8200  # For unknown agent types


def get_port_range(agent_type: str) -> tuple[int, int]:
    """
    Get the port range for an agent type.

    Args:
        agent_type: The type of agent (claude, gemini, codex, etc.)

    Returns:
        Tuple of (start_port, end_port) inclusive.
    """
    if agent_type in PORT_RANGES:
        return PORT_RANGES[agent_type]

    # For unknown types, calculate a range based on alphabetical order
    # This ensures consistency across runs
    known_types = sorted(PORT_RANGES.keys())
    type_index = len(known_types)  # Start after known types

    start = DEFAULT_BASE_PORT + (type_index * DEFAULT_PORT_RANGE_SIZE)
    end = start + DEFAULT_PORT_RANGE_SIZE - 1
    return (start, end)


def is_port_available(port: int) -> bool:
    """
    Check if a port is available for binding.

    Args:
        port: Port number to check.

    Returns:
        True if port is available, False otherwise.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("0.0.0.0", port))
            return True
    except OSError:
        return False


def is_process_alive(pid: int) -> bool:
    """
    Check if a process with given PID is still running.

    Args:
        pid: Process ID to check.

    Returns:
        True if process exists, False otherwise.
    """
    return is_process_running(pid)


class PortManager:
    """Manages port allocation for multi-instance agent support."""

    def __init__(self, registry: "AgentRegistry") -> None:
        """
        Initialize PortManager with an AgentRegistry.

        Args:
            registry: AgentRegistry instance for tracking running agents.
        """
        self.registry = registry

    def get_available_port(self, agent_type: str) -> int | None:
        """
        Find the first available port in the range for agent_type.

        Also cleans up stale registry entries for dead processes.

        Args:
            agent_type: The type of agent to get a port for.

        Returns:
            Available port number, or None if all ports are in use.
        """
        start_port, end_port = get_port_range(agent_type)
        agents = self.registry.list_agents()

        for port in range(start_port, end_port + 1):
            registered = [
                (agent_id, info)
                for agent_id, info in agents.items()
                if info.get("port") == port
            ]

            live_registered = False
            for agent_id, info in registered:
                pid = info.get("pid")
                if pid and is_process_alive(pid):
                    live_registered = True
                    break
                self.registry.unregister(agent_id)
                agents.pop(agent_id, None)

            if live_registered:
                continue

            if not is_port_available(port):
                logger.warning(
                    "Detected orphan listener on port %s with no live registry "
                    "entry. Run 'synapse doctor --clean' to inspect and clean "
                    "up orphan processes.",
                    port,
                )
                continue

            return port

        return None

    def allocate_and_register(
        self,
        agent_type: str,
        *,
        name: str | None = None,
        pid: int | None = None,
    ) -> tuple[int, str]:
        """Atomically reserve a free port and write a placeholder registry entry.

        Holds ``AgentRegistry.registry_write_lock`` (a cross-process flock)
        for both free-port discovery AND the placeholder write, eliminating
        the issue #715 race window in which two parallel spawns could both
        receive the same free port from ``get_available_port`` and then race
        to overwrite each other's registry file.

        The placeholder is committed with ``status=PROCESSING`` and the
        caller's pid (defaults to ``os.getpid()``). The full register call
        with worktree metadata, role, etc. happens later via
        ``AgentRegistry.update_*`` once setup completes.

        Args:
            agent_type: Agent type whose port range to draw from.
            name: Optional custom name (validated for collisions inside the lock).
            pid: PID to record (defaults to current process). Pre-set for tests.

        Returns:
            Tuple of (allocated_port, agent_id).

        Raises:
            PortExhaustionError: All ports in range are taken or have orphan listeners.
            NameConflictError: ``name`` collides with an existing entry.
        """
        if pid is None:
            pid = os.getpid()
        start_port, end_port = get_port_range(agent_type)

        with self.registry.registry_write_lock():
            agents = self.registry.list_agents()
            free_port = self._find_free_port_locked(
                agent_type, start_port, end_port, agents
            )
            if free_port is None:
                raise PortExhaustionError(
                    f"All ports in range {start_port}-{end_port} are in use "
                    f"for '{agent_type}'."
                )

            agent_id = self.registry.get_agent_id(agent_type, free_port)
            now = time.time()
            data: dict = {
                "agent_id": agent_id,
                "agent_type": agent_type,
                "port": free_port,
                "status": PROCESSING,
                "status_updated_at": now,
                "last_status_change_at": now,
                "registered_at": now,
                "pid": pid,
                "working_dir": os.getcwd(),
                "endpoint": f"http://localhost:{free_port}",
                "uds_path": str(resolve_uds_path(agent_id)),
            }
            if name:
                data["name"] = name

            self.registry._register_locked(agent_id, data, name=name)
            return free_port, agent_id

    def _find_free_port_locked(
        self,
        agent_type: str,
        start_port: int,
        end_port: int,
        agents: dict[str, dict],
    ) -> int | None:
        """Find the first port in [start_port, end_port] that is not held by a
        live registered agent and not held by an orphan listener.

        MUST be called with ``registry.registry_write_lock`` held — otherwise
        the snapshot of ``agents`` becomes stale before the caller writes.

        Mirrors the policy of ``get_available_port`` (skip live, clean dead,
        skip orphan listener, take the first remaining), but operates on a
        caller-supplied agents snapshot so the entire decision is consistent
        with the lock-held registry view.
        """
        del agent_type  # only used by callers for range derivation
        for port in range(start_port, end_port + 1):
            registered = [
                (agent_id, info)
                for agent_id, info in agents.items()
                if info.get("port") == port
            ]
            live_registered = False
            for agent_id, info in registered:
                pid = info.get("pid")
                if pid and is_process_alive(pid):
                    live_registered = True
                    break
                self.registry.unregister(agent_id)
                agents.pop(agent_id, None)
            if live_registered:
                continue
            if not is_port_available(port):
                logger.warning(
                    "Detected orphan listener on port %s with no live registry "
                    "entry. Run 'synapse doctor --clean' to inspect and clean "
                    "up orphan processes.",
                    port,
                )
                continue
            return port
        return None

    def get_running_instances(self, agent_type: str) -> list[dict]:
        """
        Get list of running instances for an agent type.

        Args:
            agent_type: The type of agent to list.

        Returns:
            List of agent info dicts for running instances.
        """
        start_port, end_port = get_port_range(agent_type)
        agents = self.registry.list_agents()
        running = []

        for info in agents.values():
            if info.get("agent_type") != agent_type:
                continue
            port = info.get("port")
            if port is None or not (start_port <= port <= end_port):
                continue
            pid = info.get("pid")
            if pid and is_process_alive(pid):
                running.append(info)

        return sorted(running, key=lambda info: info.get("port", 0))

    def format_exhaustion_error(self, agent_type: str) -> str:
        """
        Format an error message when all ports are exhausted.

        Args:
            agent_type: The type of agent that ran out of ports.

        Returns:
            Formatted error message string.
        """
        start_port, end_port = get_port_range(agent_type)
        running = self.get_running_instances(agent_type)

        port_range = f"{start_port}-{end_port}"
        lines = [
            f"Error: All ports in range {port_range} are in use for '{agent_type}'.",
            "",
            "Running instances:",
        ]

        for info in running:
            agent_id = info.get("agent_id", "unknown")
            pid = info.get("pid", "?")
            lines.append(f"  {agent_id} (PID: {pid})")

        hint = f"Use 'synapse stop {agent_type}' to stop an instance"
        lines.extend(["", f"{hint}, or specify --port manually."])
        lines.append(
            "Run 'synapse doctor --clean' to detect and clean up orphan processes."
        )

        return "\n".join(lines)
