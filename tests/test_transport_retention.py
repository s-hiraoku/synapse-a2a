"""Tests for transport display retention feature.

The transport display should persist for a configurable duration (default 3s)
so that users can observe communication events in watch mode even though
the actual communication completes in milliseconds.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from synapse.registry import AgentRegistry


class TestTransportRetention:
    """Tests for transport state retention in registry."""

    @pytest.fixture
    def registry(self, tmp_path: Path) -> AgentRegistry:
        """Create a registry with a temporary directory."""
        reg = AgentRegistry()
        reg.registry_dir = tmp_path
        return reg

    @pytest.fixture
    def agent_file(self, registry: AgentRegistry) -> Path:
        """Create a test agent file."""
        agent_id = "synapse-claude-8100"
        file_path = registry.registry_dir / f"{agent_id}.json"
        data = {
            "agent_id": agent_id,
            "agent_type": "claude",
            "port": 8100,
            "status": "READY",
            "pid": 12345,
            "working_dir": "/tmp",
            "endpoint": "http://localhost:8100",
        }
        with open(file_path, "w") as f:
            json.dump(data, f)
        return file_path

    def test_update_transport_stores_timestamp(
        self, registry: AgentRegistry, agent_file: Path
    ) -> None:
        """update_transport should store both transport value and timestamp."""
        agent_id = "synapse-claude-8100"

        # Update transport
        result = registry.update_transport(agent_id, "UDS→")
        assert result is True

        # Read the file and verify
        with open(agent_file) as f:
            data = json.load(f)

        assert data.get("active_transport") == "UDS→"
        assert "transport_updated_at" in data
        # Timestamp should be recent (within last 1 second)
        assert time.time() - data["transport_updated_at"] < 1.0

    def test_clear_transport_keeps_timestamp(
        self, registry: AgentRegistry, agent_file: Path
    ) -> None:
        """Clearing transport should keep the timestamp for retention display."""
        agent_id = "synapse-claude-8100"

        # Set transport first
        registry.update_transport(agent_id, "TCP→")

        # Small delay to make timestamps distinguishable
        time.sleep(0.01)

        # Clear transport (what happens after communication completes)
        result = registry.update_transport(agent_id, None)
        assert result is True

        # Read and verify - transport cleared but timestamp remains
        with open(agent_file) as f:
            data = json.load(f)

        assert data.get("active_transport") is None
        assert "transport_updated_at" in data

    def test_get_transport_display_within_retention(
        self, registry: AgentRegistry, agent_file: Path
    ) -> None:
        """get_transport_display returns last transport within retention period."""
        agent_id = "synapse-claude-8100"

        # Set transport
        registry.update_transport(agent_id, "UDS→")

        # Immediately clear (simulating fast communication)
        registry.update_transport(agent_id, None)

        # Should still show "UDS→" within retention period
        display = registry.get_transport_display(agent_id, retention_seconds=3.0)
        assert display == "UDS→"

    def test_get_transport_display_after_retention(
        self, registry: AgentRegistry, agent_file: Path
    ) -> None:
        """get_transport_display returns None after retention period expires."""
        agent_id = "synapse-claude-8100"

        # Set transport with old timestamp
        with open(agent_file) as f:
            data = json.load(f)

        data["active_transport"] = None
        data["last_transport"] = "UDS→"
        data["transport_updated_at"] = time.time() - 5.0  # 5 seconds ago

        with open(agent_file, "w") as f:
            json.dump(data, f)

        # Should return None (retention period of 3s has passed)
        display = registry.get_transport_display(agent_id, retention_seconds=3.0)
        assert display is None

    def test_get_transport_display_active_transport(
        self, registry: AgentRegistry, agent_file: Path
    ) -> None:
        """get_transport_display returns active_transport when set."""
        agent_id = "synapse-claude-8100"

        # Set active transport
        registry.update_transport(agent_id, "→TCP")

        # Should return the active transport
        display = registry.get_transport_display(agent_id, retention_seconds=3.0)
        assert display == "→TCP"

    def test_get_transport_display_no_transport_history(
        self, registry: AgentRegistry, agent_file: Path
    ) -> None:
        """get_transport_display returns None when no transport ever set."""
        agent_id = "synapse-claude-8100"

        # No transport set
        display = registry.get_transport_display(agent_id, retention_seconds=3.0)
        assert display is None

    def test_get_transport_display_agent_not_found(
        self, registry: AgentRegistry
    ) -> None:
        """get_transport_display returns None for non-existent agent."""
        display = registry.get_transport_display("nonexistent", retention_seconds=3.0)
        assert display is None


class TestListCommandTransportRetention:
    """Tests for transport retention display in list command."""

    def test_get_agent_data_uses_retention(self, tmp_path: Path) -> None:
        """List command should use get_transport_display with retention."""
        from synapse.commands.list import ListCommand

        # Create mock registry
        mock_registry = MagicMock(spec=AgentRegistry)
        mock_registry.list_agents.return_value = {
            "synapse-claude-8100": {
                "agent_id": "synapse-claude-8100",
                "agent_type": "claude",
                "port": 8100,
                "status": "READY",
                "pid": 12345,
                "working_dir": "/tmp",
                "endpoint": "http://localhost:8100",
            }
        }
        # Return retained transport
        mock_registry.get_transport_display.return_value = "UDS→"

        cmd = ListCommand(
            registry_factory=lambda: mock_registry,
            is_process_alive=lambda pid: True,
            is_port_open=lambda *args, **kwargs: True,
            clear_screen=lambda: None,
            time_module=MagicMock(),
            print_func=lambda x: None,
        )

        with patch("synapse.commands.list.FileSafetyManager") as mock_fs:
            mock_fs.from_env.return_value.enabled = False
            agents, _, _ = cmd._get_agent_data(mock_registry)

        # Verify get_transport_display was called with retention
        mock_registry.get_transport_display.assert_called_once_with(
            "synapse-claude-8100", retention_seconds=3.0
        )

        # Verify output contains the retained transport
        assert len(agents) == 1
        assert agents[0]["transport"] == "UDS→"

    def test_get_agent_data_shows_transport_column(self, tmp_path: Path) -> None:
        """Transport column should always be present in agent data."""
        from synapse.commands.list import ListCommand

        mock_registry = MagicMock(spec=AgentRegistry)
        mock_registry.list_agents.return_value = {
            "synapse-claude-8100": {
                "agent_id": "synapse-claude-8100",
                "agent_type": "claude",
                "port": 8100,
                "status": "READY",
                "pid": 12345,
                "working_dir": "/tmp",
                "endpoint": "http://localhost:8100",
            }
        }
        mock_registry.get_transport_display.return_value = "-"

        cmd = ListCommand(
            registry_factory=lambda: mock_registry,
            is_process_alive=lambda pid: True,
            is_port_open=lambda *args, **kwargs: True,
            clear_screen=lambda: None,
            time_module=MagicMock(),
            print_func=lambda x: None,
        )

        with patch("synapse.commands.list.FileSafetyManager") as mock_fs:
            mock_fs.from_env.return_value.enabled = False
            agents, _, _ = cmd._get_agent_data(mock_registry)

        # Transport should always be included
        assert len(agents) == 1
        assert "transport" in agents[0]


class TestTransportRetentionIntegration:
    """Integration tests for transport retention with real registry."""

    @pytest.fixture
    def registry(self, tmp_path: Path) -> AgentRegistry:
        """Create a registry with a temporary directory."""
        reg = AgentRegistry()
        reg.registry_dir = tmp_path
        return reg

    def test_full_communication_cycle(self, registry: AgentRegistry) -> None:
        """Test a full send/receive cycle with retention."""
        agent_id = "synapse-claude-8100"

        # Register agent
        registry.register(agent_id, "claude", 8100, "READY")

        # Simulate communication start (sender)
        registry.update_transport(agent_id, "UDS→")

        # Verify active transport
        display = registry.get_transport_display(agent_id, retention_seconds=3.0)
        assert display == "UDS→"

        # Simulate communication end (sender clears)
        registry.update_transport(agent_id, None)

        # Should still show due to retention
        display = registry.get_transport_display(agent_id, retention_seconds=3.0)
        assert display == "UDS→"

    def test_multiple_communications_updates_display(
        self, registry: AgentRegistry
    ) -> None:
        """Multiple communications should update the displayed transport."""
        agent_id = "synapse-claude-8100"

        # Register agent
        registry.register(agent_id, "claude", 8100, "READY")

        # First communication (UDS)
        registry.update_transport(agent_id, "UDS→")
        registry.update_transport(agent_id, None)

        display = registry.get_transport_display(agent_id, retention_seconds=3.0)
        assert display == "UDS→"

        # Second communication (TCP fallback)
        registry.update_transport(agent_id, "TCP→")
        registry.update_transport(agent_id, None)

        # Should show latest transport
        display = registry.get_transport_display(agent_id, retention_seconds=3.0)
        assert display == "TCP→"
