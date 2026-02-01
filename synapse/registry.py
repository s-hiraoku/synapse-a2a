import contextlib
import json
import logging
import os
import socket
import tempfile
import time
from collections.abc import Callable
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


def get_valid_uds_path(uds_path: str | None) -> str | None:
    """Return UDS path only if the socket file exists.

    Args:
        uds_path: The UDS path from agent info, or None.

    Returns:
        The path if it exists, None otherwise.
    """
    if uds_path and Path(uds_path).exists():
        return uds_path
    return None


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
        self,
        agent_id: str,
        agent_type: str,
        port: int,
        status: str = "PROCESSING",
        tty_device: str | None = None,
        name: str | None = None,
        role: str | None = None,
    ) -> Path:
        """Writes connection info to registry file.

        Args:
            agent_id: Unique agent identifier.
            agent_type: Type of agent (claude, gemini, codex).
            port: Port number for HTTP endpoint.
            status: Initial status (READY, WAITING, PROCESSING, or DONE).
            tty_device: TTY device path (e.g., /dev/ttys001) for terminal jump.
            name: Custom name for the agent (optional).
            role: Role description for the agent (optional).

        Returns:
            Path to the created registry file.
        """
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

        # Add optional name and role
        if name:
            data["name"] = name
        if role:
            data["role"] = role

        # Add tty_device if available (for terminal jump feature)
        if tty_device:
            data["tty_device"] = tty_device

        # Add Zellij pane ID if running in Zellij (for terminal jump)
        zellij_pane_id = os.environ.get("ZELLIJ_PANE_ID")
        if zellij_pane_id:
            data["zellij_pane_id"] = zellij_pane_id

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

    def _atomic_update(
        self, agent_id: str, updater: Callable[[dict], None], field_name: str
    ) -> bool:
        """
        Atomically update an agent's registry file.

        Args:
            agent_id: The unique agent identifier.
            updater: Function that modifies the data dict in place.
            field_name: Name of the field being updated (for error messages).

        Returns:
            True if updated successfully, False otherwise.
        """
        file_path = self.registry_dir / f"{agent_id}.json"
        if not file_path.exists():
            return False

        try:
            with open(file_path) as f:
                data = json.load(f)

            updater(data)

            # Atomic write: write to temp file, then rename
            temp_fd, temp_path = tempfile.mkstemp(
                dir=self.registry_dir,
                prefix=f".{agent_id}.",
                suffix=".tmp",
            )
            try:
                with os.fdopen(temp_fd, "w") as f:
                    json.dump(data, f, indent=2)
                    f.flush()
                    os.fsync(f.fileno())

                # Atomic rename (POSIX guarantee)
                os.replace(temp_path, file_path)
                return True
            except Exception:
                if os.path.exists(temp_path):
                    with contextlib.suppress(OSError):
                        os.unlink(temp_path)
                raise

        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"Failed to update {field_name} for {agent_id}: {e}")
            return False

    def update_status(self, agent_id: str, status: str) -> bool:
        """
        Update the status of a registered agent (atomic write).

        Args:
            agent_id: The unique agent identifier.
            status: New status value.

        Returns:
            True if updated successfully, False otherwise.
        """

        def set_status(data: dict) -> None:
            data["status"] = status

        return self._atomic_update(agent_id, set_status, "status")

    def update_tty_device(self, agent_id: str, tty_device: str) -> bool:
        """Update the TTY device for an agent (for terminal jump feature).

        Args:
            agent_id: The unique agent identifier.
            tty_device: TTY device path (e.g., /dev/ttys001).

        Returns:
            True if updated successfully, False otherwise.
        """

        def set_tty(data: dict) -> None:
            data["tty_device"] = tty_device

        return self._atomic_update(agent_id, set_tty, "tty_device")

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

    def update_transport(self, agent_id: str, transport: str | None) -> bool:
        """
        Update the active transport method for an agent (atomic write).

        Used by watch mode to display real-time communication status.
        Sender shows "UDS→" or "TCP→", receiver shows "→UDS" or "→TCP".

        When transport is set, it's stored in active_transport and last_transport.
        When transport is cleared (None), active_transport is removed but
        last_transport and transport_updated_at are kept for retention display.

        Args:
            agent_id: The agent identifier.
            transport: Transport string (e.g., "UDS→", "→UDS", "TCP→", "→TCP")
                       or None to clear.

        Returns:
            True if updated successfully, False otherwise.
        """

        def set_transport(data: dict) -> None:
            now = time.time()
            if transport is None:
                # Clear active_transport but keep last_transport for retention
                data.pop("active_transport", None)
                # Update timestamp when clearing (for retention countdown)
                data["transport_updated_at"] = now
            else:
                data["active_transport"] = transport
                data["last_transport"] = transport
                data["transport_updated_at"] = now

        return self._atomic_update(agent_id, set_transport, "transport")

    def get_transport_display(
        self, agent_id: str, retention_seconds: float = 3.0
    ) -> str | None:
        """
        Get the transport to display, considering retention period.

        If active_transport is set, return it.
        If active_transport is None but last_transport exists and
        transport_updated_at is within retention_seconds, return last_transport.
        Otherwise return None.

        Args:
            agent_id: The agent identifier.
            retention_seconds: How long to display last transport after clearing.

        Returns:
            Transport string to display, or None.
        """
        agent_data = self.get_agent(agent_id)
        if not agent_data:
            return None

        # If active transport is set, return it
        active = agent_data.get("active_transport")
        if isinstance(active, str) and active:
            return active

        # Check if we should display last transport due to retention
        last_transport = agent_data.get("last_transport")
        updated_at = agent_data.get("transport_updated_at")

        if isinstance(last_transport, str) and last_transport and updated_at:
            elapsed = time.time() - updated_at
            if elapsed < retention_seconds:
                return last_transport

        return None

    def resolve_agent(self, target: str) -> dict | None:
        """Resolve an agent by name, ID, type-port, or type.

        Resolution priority (highest to lowest):
        1. Custom name (exact match)
        2. Full agent ID (exact match)
        3. Type-port shorthand (e.g., "claude-8100")
        4. Type (only if single agent of that type)

        Args:
            target: The target string to resolve.

        Returns:
            Agent info dict if found, None if not found or ambiguous.
        """
        import re

        agents = self.get_live_agents()
        if not agents:
            return None

        # Priority 1: Custom name (exact match)
        for info in agents.values():
            if info.get("name") == target:
                return info

        # Priority 2: Full agent ID (exact match)
        if target in agents:
            return agents[target]

        # Priority 3: Type-port shorthand (e.g., "claude-8100")
        if match := re.match(r"^([\w-]+)-(\d+)$", target):
            agent_type, port_str = match.groups()
            port = int(port_str)
            for info in agents.values():
                if info.get("agent_type") == agent_type and info.get("port") == port:
                    return info

        # Priority 4: Type (only if single agent of that type)
        type_matches = [
            info for info in agents.values() if info.get("agent_type") == target
        ]
        return type_matches[0] if len(type_matches) == 1 else None

    def is_name_unique(self, name: str, exclude_agent_id: str | None = None) -> bool:
        """Check if a name is unique across all agents.

        Args:
            name: The name to check.
            exclude_agent_id: Optional agent ID to exclude from the check
                              (useful when updating own name).

        Returns:
            True if the name is unique, False otherwise.
        """
        agents = self.list_agents()
        for agent_id, info in agents.items():
            if exclude_agent_id and agent_id == exclude_agent_id:
                continue
            if info.get("name") == name:
                return False
        return True

    def update_name(
        self,
        agent_id: str,
        name: str | None,
        role: str | None = None,
        clear: bool = False,
    ) -> bool:
        """Update the name and/or role of a registered agent.

        Args:
            agent_id: The unique agent identifier.
            name: New name value (None to keep current, or clear if clear=True).
            role: New role value (None to keep current, or clear if clear=True).
            clear: If True, clear both name and role when they are None.

        Returns:
            True if updated successfully, False otherwise.
        """

        def set_name_role(data: dict) -> None:
            if clear:
                if name is None:
                    data.pop("name", None)
                else:
                    data["name"] = name
                if role is None:
                    data.pop("role", None)
                else:
                    data["role"] = role
            else:
                if name is not None:
                    data["name"] = name
                if role is not None:
                    data["role"] = role

        return self._atomic_update(agent_id, set_name_role, "name/role")

    def update_current_task(self, agent_id: str, task_preview: str | None) -> bool:
        """Update current task preview for an agent.

        Args:
            agent_id: The unique agent identifier.
            task_preview: Task preview text (truncated to 30 chars + "..."),
                         or None to clear.

        Returns:
            True if updated successfully, False otherwise.
        """
        # Truncate long previews to max 30 chars total (including "...")
        truncated_preview: str | None = None
        if task_preview is not None:
            if len(task_preview) > 30:
                truncated_preview = task_preview[:27] + "..."
            else:
                truncated_preview = task_preview

        def set_task_preview(data: dict) -> None:
            if truncated_preview is None:
                data.pop("current_task_preview", None)
            else:
                data["current_task_preview"] = truncated_preview

        return self._atomic_update(agent_id, set_task_preview, "current_task_preview")
