import os
import json
import hashlib
import socket
from pathlib import Path
from typing import Dict, List, Optional


def is_process_running(pid: int) -> bool:
    """Check if a process is still running."""
    try:
        os.kill(pid, 0)  # Signal 0 only checks existence
        return True
    except (ProcessLookupError, PermissionError):
        return False


def is_port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    """Check if a port is open (fast check)."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False

class AgentRegistry:
    def __init__(self):
        self.registry_dir = Path.home() / ".a2a" / "registry"
        self.registry_dir.mkdir(parents=True, exist_ok=True)
        self.hostname = socket.gethostname()

    def get_agent_id(self, agent_type: str, port: int) -> str:
        """Generates a unique agent ID in format: synapse-{agent_type}-{port}."""
        return f"synapse-{agent_type}-{port}"

    def register(self, agent_id: str, agent_type: str, port: int, status: str = "STARTING"):
        """Writes connection info to registry file."""
        data = {
            "agent_id": agent_id,
            "agent_type": agent_type,
            "port": port,
            "status": status,
            "pid": os.getpid(),
            "working_dir": os.getcwd(),
            "endpoint": f"http://localhost:{port}"
        }
        
        file_path = self.registry_dir / f"{agent_id}.json"
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2)
            
        return file_path

    def unregister(self, agent_id: str):
        """Removes the registry file."""
        file_path = self.registry_dir / f"{agent_id}.json"
        if file_path.exists():
            file_path.unlink()

    def list_agents(self) -> Dict[str, dict]:
        """Returns all currently registered agents."""
        agents = {}
        for p in self.registry_dir.glob("*.json"):
            try:
                with open(p, 'r') as f:
                    data = json.load(f)
                    agents[data['agent_id']] = data
            except (json.JSONDecodeError, OSError):
                continue
        return agents

    def get_agent(self, agent_id: str) -> Optional[dict]:
        """
        Get info for a specific agent by ID.

        Args:
            agent_id: The unique agent identifier.

        Returns:
            Agent info dict, or None if not found.
        """
        file_path = self.registry_dir / f"{agent_id}.json"
        if not file_path.exists():
            return None

        try:
            with open(file_path, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

    def update_status(self, agent_id: str, status: str) -> bool:
        """
        Update the status of a registered agent.

        Args:
            agent_id: The unique agent identifier.
            status: New status value.

        Returns:
            True if updated successfully, False otherwise.
        """
        file_path = self.registry_dir / f"{agent_id}.json"
        if not file_path.exists():
            return False

        try:
            with open(file_path, 'r') as f:
                data = json.load(f)

            data["status"] = status

            with open(file_path, 'w') as f:
                json.dump(data, f, indent=2)

            return True
        except (json.JSONDecodeError, OSError):
            return False

    def cleanup_stale_entries(self) -> List[str]:
        """
        Remove registry entries for agents whose processes are no longer running.

        Returns:
            List of agent IDs that were removed.
        """
        removed = []
        for agent_id, info in list(self.list_agents().items()):
            pid = info.get('pid')
            if pid and not is_process_running(pid):
                self.unregister(agent_id)
                removed.append(agent_id)
        return removed

    def get_live_agents(self) -> Dict[str, dict]:
        """
        Returns only agents that are confirmed to be running.
        Automatically cleans up stale entries.
        """
        self.cleanup_stale_entries()
        return self.list_agents()
