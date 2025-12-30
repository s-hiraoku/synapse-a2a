"""Port management for Synapse A2A multi-instance support."""

import socket
import os
from typing import Tuple, Optional, Dict, List

# Port range definitions (agent_type -> (start, end) inclusive)
PORT_RANGES: Dict[str, Tuple[int, int]] = {
    "claude": (8100, 8109),
    "gemini": (8110, 8119),
    "codex": (8120, 8129),
    "dummy": (8190, 8199),
}

DEFAULT_PORT_RANGE_SIZE = 10
DEFAULT_BASE_PORT = 8200  # For unknown agent types


def get_port_range(agent_type: str) -> Tuple[int, int]:
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
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(('localhost', port))
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
    try:
        os.kill(pid, 0)  # Signal 0 checks if process exists
        return True
    except (OSError, ProcessLookupError):
        return False


class PortManager:
    """Manages port allocation for multi-instance agent support."""

    def __init__(self, registry):
        """
        Initialize PortManager with an AgentRegistry.

        Args:
            registry: AgentRegistry instance for tracking running agents.
        """
        self.registry = registry

    def get_available_port(self, agent_type: str) -> Optional[int]:
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
            agent_id = f"synapse-{agent_type}-{port}"

            # Check if registered
            if agent_id in agents:
                info = agents[agent_id]
                pid = info.get("pid")

                # Check if process is still alive
                if pid and is_process_alive(pid):
                    # Port is in use by a live process
                    continue
                else:
                    # Process is dead, clean up stale entry
                    self.registry.unregister(agent_id)

            # Check actual port availability
            if is_port_available(port):
                return port

        return None

    def get_running_instances(self, agent_type: str) -> List[Dict]:
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

        for port in range(start_port, end_port + 1):
            agent_id = f"synapse-{agent_type}-{port}"
            if agent_id in agents:
                info = agents[agent_id]
                pid = info.get("pid")
                if pid and is_process_alive(pid):
                    running.append(info)

        return running

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

        lines = [
            f"Error: All ports in range {start_port}-{end_port} are in use for '{agent_type}'.",
            "",
            "Running instances:",
        ]

        for info in running:
            agent_id = info.get("agent_id", "unknown")
            pid = info.get("pid", "?")
            lines.append(f"  {agent_id} (PID: {pid})")

        lines.extend([
            "",
            f"Use 'synapse stop {agent_type}' to stop an instance, or specify --port manually.",
        ])

        return "\n".join(lines)
