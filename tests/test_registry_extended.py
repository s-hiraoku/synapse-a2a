"""Extended tests for synapse/registry.py covering process and port checks."""

import json
import os
import shutil
import socket
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from synapse.registry import (
    AgentRegistry,
    is_port_open,
    is_process_running,
)

# ============================================================
# Helper Functions Tests
# ============================================================


class TestHelperFunctions:
    """Tests for standalone helper functions."""

    def test_is_process_running_true(self):
        """Should return True for current process."""
        assert is_process_running(os.getpid()) is True

    def test_is_process_running_false(self):
        """Should return False for likely non-existent PID."""
        # PID 999999 is unlikely to exist on most systems
        assert is_process_running(999999) is False

    @patch("synapse.registry.os.kill")
    def test_is_process_running_permission_error(self, mock_kill):
        """Should return True on PermissionError (process exists but no permission)."""
        mock_kill.side_effect = PermissionError
        assert is_process_running(1) is True

    def test_is_port_open_true(self):
        """Should return True for an open port."""
        # Open a real port for testing
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("localhost", 0))
            s.listen(1)
            port = s.getsockname()[1]
            assert is_port_open("localhost", port) is True

    def test_is_port_open_false(self):
        """Should return False for a closed port."""
        # Find a free port and ensure it's closed
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("localhost", 0))
            port = s.getsockname()[1]

        # Now check it (socket is closed)
        assert is_port_open("localhost", port) is False

    @patch("synapse.registry.socket.create_connection")
    def test_is_port_open_timeout(self, mock_connect):
        """Should return False on timeout."""
        mock_connect.side_effect = TimeoutError
        assert is_port_open("localhost", 80) is False

    @patch("synapse.registry.socket.create_connection")
    def test_is_port_open_connection_refused(self, mock_connect):
        """Should return False on connection refused."""
        mock_connect.side_effect = ConnectionRefusedError
        assert is_port_open("localhost", 80) is False


# ============================================================
# Registry Extended Tests
# ============================================================


class TestRegistryExtended:
    """Extended tests for AgentRegistry."""

    @pytest.fixture
    def registry(self):
        """Create a temporary registry."""
        temp_dir = Path(tempfile.mkdtemp(prefix="test_registry_ext_"))
        reg = AgentRegistry()
        reg.registry_dir = temp_dir
        yield reg
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_cleanup_stale_entries(self, registry):
        """Should remove entries for dead processes."""
        # Register two agents
        # Agent 1: Alive (using current PID)
        registry.register("alive", "claude", 8100)

        # Agent 2: Dead (using nonexistent PID)
        file_path = registry.registry_dir / "dead.json"
        data = {"agent_id": "dead", "pid": 999999, "port": 8101, "status": "IDLE"}
        file_path.write_text(json.dumps(data))

        with patch("synapse.registry.is_process_running") as mock_is_running:
            # Mock check: first call (alive) -> True, second call (dead) -> False
            # Note: list_agents() iterates in file system order, which can vary.
            # So we make the mock smart enough to check the PID.
            def check_pid(pid):
                return pid == os.getpid()

            mock_is_running.side_effect = check_pid

            removed = registry.cleanup_stale_entries()

            assert "dead" in removed
            assert "alive" not in removed

            # Verify files
            assert (registry.registry_dir / "alive.json").exists()
            assert not (registry.registry_dir / "dead.json").exists()

    def test_get_live_agents(self, registry):
        """Should return only live agents and clean up stale ones."""
        # Agent 1: Alive
        registry.register("alive", "claude", 8100)

        # Agent 2: Dead
        file_path = registry.registry_dir / "dead.json"
        data = {"agent_id": "dead", "pid": 999999, "port": 8101, "status": "IDLE"}
        file_path.write_text(json.dumps(data))

        with patch("synapse.registry.is_process_running") as mock_is_running:

            def check_pid(pid):
                return pid == os.getpid()

            mock_is_running.side_effect = check_pid

            live = registry.get_live_agents()

            assert "alive" in live
            assert "dead" not in live

            # Verify cleanup happened
            assert not (registry.registry_dir / "dead.json").exists()

    def test_update_status_atomic_failure(self, registry):
        """Should handle errors during atomic status update."""
        registry.register("test", "claude", 8100)

        # Simulate OS error during rename
        with (
            patch("synapse.registry.os.replace", side_effect=OSError("Rename failed")),
            patch("synapse.registry.logger") as mock_logger,
        ):
            # The function catches OSError and returns False
            result = registry.update_status("test", "BUSY")
            assert result is False

            # Verify error was logged
            mock_logger.error.assert_called_once()

            # Verify cleanup: temp file should be gone (difficult to check directly due to mocking,
            # but we trust the logic flow if exception propagates)
            info = registry.get_agent("test")
            assert info["status"] == "PROCESSING"  # Original status

    def test_update_status_json_error(self, registry):
        """Should handle JSON decode error when reading existing file."""
        agent_id = "corrupt"
        file_path = registry.registry_dir / f"{agent_id}.json"
        file_path.write_text("{ invalid json }")

        result = registry.update_status(agent_id, "BUSY")

        assert result is False
