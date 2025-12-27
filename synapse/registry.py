import os
import json
import hashlib
import socket
from pathlib import Path
from typing import Dict, Optional

class AgentRegistry:
    def __init__(self):
        self.registry_dir = Path.home() / ".a2a" / "registry"
        self.registry_dir.mkdir(parents=True, exist_ok=True)
        self.hostname = socket.gethostname()

    def get_agent_id(self, agent_type: str, working_dir: str) -> str:
        """Generates a consistent unique ID based on environment."""
        # Normalize path
        abs_work_dir = os.path.abspath(working_dir)
        raw_key = f"{self.hostname}|{abs_work_dir}|{agent_type}"
        return hashlib.sha256(raw_key.encode('utf-8')).hexdigest()

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
