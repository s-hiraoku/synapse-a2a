import contextlib
import json
import logging
import os
import socket
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


def _ensure_uds_dir(path: Path) -> None:
    """Ensure UDS directory exists with permissions accessible by sandboxed apps."""
    path.mkdir(parents=True, exist_ok=True)
    # Use 755 so sandboxed apps (like Codex CLI) can access UDS sockets
    with contextlib.suppress(OSError):
        path.chmod(0o755)


def resolve_uds_path(agent_id: str) -> Path:
    """Resolve UDS path for a local agent.

    Uses /tmp/synapse-a2a/ by default for compatibility with sandboxed apps.
    Can be overridden via SYNAPSE_UDS_DIR environment variable.
    """
    # Allow override via SYNAPSE_UDS_DIR, default to /tmp for sandbox compatibility
    uds_dir = os.environ.get("SYNAPSE_UDS_DIR")
    base_dir = Path(uds_dir) if uds_dir else Path("/tmp/synapse-a2a")

    _ensure_uds_dir(base_dir)
    return base_dir / f"{agent_id}.sock"


def is_process_running(pid: int) -> bool:
    """Check if a process is still running."""
    try:
        os.kill(pid, 0)  # Signal 0 only checks existence
        return True
    except ProcessLookupError:
        return False  # Process does not exist
    except PermissionError:
        return True  # Process exists but we don't have permission to signal it


def is_port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    """Check if a port is open (fast check)."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (TimeoutError, ConnectionRefusedError, OSError):
        return False


class AgentRegistry:
    def __init__(self) -> None:
        self.registry_dir = Path.home() / ".a2a" / "registry"
        self.registry_dir.mkdir(parents=True, exist_ok=True)
        self.hostname = socket.gethostname()

    def get_agent_id(self, agent_type: str, port: int) -> str:
        """Generates a unique agent ID in format: synapse-{agent_type}-{port}."""
        return f"synapse-{agent_type}-{port}"

    def register(
        self, agent_id: str, agent_type: str, port: int, status: str = "PROCESSING"
    ) -> Path:
        """Writes connection info to registry file."""
        data = {
            "agent_id": agent_id,
            "agent_type": agent_type,
            "port": port,
            "status": status,
            "pid": os.getpid(),
            "working_dir": os.getcwd(),
            "endpoint": f"http://localhost:{port}",
            "uds_path": str(resolve_uds_path(agent_id)),
        }

        file_path = self.registry_dir / f"{agent_id}.json"
        with open(file_path, "w") as f:
            json.dump(data, f, indent=2)

        return file_path

    def unregister(self, agent_id: str) -> None:
        """Removes the registry file."""
        file_path = self.registry_dir / f"{agent_id}.json"
        if file_path.exists():
            file_path.unlink()

    def list_agents(self) -> dict[str, dict]:
        """Returns all currently registered agents."""
        agents = {}
        for p in self.registry_dir.glob("*.json"):
            try:
                with open(p) as f:
                    data = json.load(f)
                    agents[data["agent_id"]] = data
            except (json.JSONDecodeError, OSError):
                continue
        return agents

    def get_agent(self, agent_id: str) -> dict | None:
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
            with open(file_path) as f:
                data = json.load(f)
                return data if isinstance(data, dict) else None
        except (json.JSONDecodeError, OSError):
            return None

    def update_status(self, agent_id: str, status: str) -> bool:
        """
        Update the status of a registered agent (atomic write).

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
            # Read current data
            with open(file_path) as f:
                data = json.load(f)

            data["status"] = status

            # Atomic write: write to temp file, then rename
            # This ensures watch mode always reads complete JSON
            temp_fd, temp_path = tempfile.mkstemp(
                dir=self.registry_dir,
                prefix=f".{agent_id}.",
                suffix=".tmp",
            )
            try:
                with os.fdopen(temp_fd, "w") as f:
                    json.dump(data, f, indent=2)
                    f.flush()
                    # Force write to disk for critical updates
                    os.fsync(f.fileno())

                # Atomic rename (POSIX guarantee)
                # This prevents watch mode from seeing partial files
                os.replace(temp_path, file_path)
                return True
            except Exception:
                # Cleanup temp file on error
                if os.path.exists(temp_path):
                    with contextlib.suppress(OSError):
                        os.unlink(temp_path)
                raise

        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"Failed to update status for {agent_id}: {e}")
            return False

    def cleanup_stale_entries(self) -> list[str]:
        """
        Remove registry entries for agents whose processes are no longer running.

        Returns:
            List of agent IDs that were removed.
        """
        removed = []
        for agent_id, info in list(self.list_agents().items()):
            pid = info.get("pid")
            if pid and not is_process_running(pid):
                self.unregister(agent_id)
                removed.append(agent_id)
        return removed

    def get_live_agents(self) -> dict[str, dict]:
        """
        Returns only agents that are confirmed to be running.
        Automatically cleans up stale entries.
        """
        self.cleanup_stale_entries()
        return self.list_agents()
