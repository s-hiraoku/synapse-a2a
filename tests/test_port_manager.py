"""Tests for port manager module."""

import os
import json
import socket
import pytest
import shutil
from pathlib import Path
from unittest.mock import patch

from synapse.port_manager import (
    PortManager,
    get_port_range,
    is_port_available,
    is_process_alive,
    PORT_RANGES,
)
from synapse.registry import AgentRegistry


@pytest.fixture
def registry():
    """Create a test registry with temp directory."""
    reg = AgentRegistry()
    reg.registry_dir = Path("/tmp/a2a_test_port_manager")
    reg.registry_dir.mkdir(parents=True, exist_ok=True)
    yield reg
    shutil.rmtree(reg.registry_dir, ignore_errors=True)


@pytest.fixture
def port_manager(registry):
    """Create a PortManager with test registry."""
    return PortManager(registry)


class TestGetPortRange:
    """Tests for get_port_range function."""

    def test_known_agent_types(self):
        """Should return correct ranges for known agent types."""
        assert get_port_range("claude") == (8100, 8109)
        assert get_port_range("gemini") == (8110, 8119)
        assert get_port_range("codex") == (8120, 8129)
        assert get_port_range("dummy") == (8190, 8199)

    def test_unknown_agent_type(self):
        """Should return a valid range for unknown agent types."""
        start, end = get_port_range("unknown_type")
        assert end - start == 9  # 10 ports (inclusive range)
        assert start >= 8200  # After known types

    def test_port_ranges_dict_consistency(self):
        """PORT_RANGES should contain all expected agent types."""
        assert "claude" in PORT_RANGES
        assert "gemini" in PORT_RANGES
        assert "codex" in PORT_RANGES
        assert "dummy" in PORT_RANGES


class TestIsPortAvailable:
    """Tests for is_port_available function."""

    def test_available_port(self):
        """Should return True for available port."""
        # Port 65432 is unlikely to be in use
        assert is_port_available(65432) is True

    def test_unavailable_port(self):
        """Should return False for unavailable port."""
        # Bind to a port temporarily
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(('localhost', 65433))
            assert is_port_available(65433) is False


class TestIsProcessAlive:
    """Tests for is_process_alive function."""

    def test_current_process_alive(self):
        """Should return True for current process."""
        assert is_process_alive(os.getpid()) is True

    def test_nonexistent_process(self):
        """Should return False for non-existent process."""
        # PID 99999999 is very unlikely to exist
        assert is_process_alive(99999999) is False


class TestPortManager:
    """Tests for PortManager class."""

    def test_get_available_port_empty_registry(self, port_manager):
        """Should return first port when registry is empty."""
        with patch('synapse.port_manager.is_port_available', return_value=True):
            port = port_manager.get_available_port("claude")
            assert port == 8100

    def test_get_available_port_skips_registered(self, port_manager, registry):
        """Should skip registered ports with live processes."""
        # Register first port with current PID (alive)
        registry.register("synapse-claude-8100", "claude", 8100)

        with patch('synapse.port_manager.is_port_available', return_value=True):
            port = port_manager.get_available_port("claude")
            assert port == 8101

    def test_get_available_port_reclaims_dead_process(self, port_manager, registry):
        """Should reclaim port from dead process."""
        # Register with fake PID
        registry.register("synapse-claude-8100", "claude", 8100)
        # Manually set a dead PID
        file_path = registry.registry_dir / "synapse-claude-8100.json"
        with open(file_path, 'r') as f:
            data = json.load(f)
        data["pid"] = 99999999  # Non-existent PID
        with open(file_path, 'w') as f:
            json.dump(data, f)

        with patch('synapse.port_manager.is_port_available', return_value=True):
            port = port_manager.get_available_port("claude")
            assert port == 8100  # Should reclaim the port

    def test_get_available_port_exhausted(self, port_manager, registry):
        """Should return None when all ports are in use."""
        # Register all ports in range
        for port in range(8100, 8110):
            registry.register(f"synapse-claude-{port}", "claude", port)

        with patch('synapse.port_manager.is_port_available', return_value=True):
            port = port_manager.get_available_port("claude")
            assert port is None

    def test_get_available_port_skips_bound_ports(self, port_manager):
        """Should skip ports that are actually bound."""
        # First call returns False (port in use), second returns True
        with patch('synapse.port_manager.is_port_available', side_effect=[False, True]):
            port = port_manager.get_available_port("claude")
            assert port == 8101  # Skipped 8100

    def test_get_running_instances_empty(self, port_manager):
        """Should return empty list when no instances running."""
        running = port_manager.get_running_instances("claude")
        assert running == []

    def test_get_running_instances(self, port_manager, registry):
        """Should return list of running instances."""
        registry.register("synapse-claude-8100", "claude", 8100)
        registry.register("synapse-claude-8101", "claude", 8101)

        running = port_manager.get_running_instances("claude")
        assert len(running) == 2

    def test_get_running_instances_filters_dead(self, port_manager, registry):
        """Should not return instances with dead processes."""
        # Register with fake dead PID
        registry.register("synapse-claude-8100", "claude", 8100)
        file_path = registry.registry_dir / "synapse-claude-8100.json"
        with open(file_path, 'r') as f:
            data = json.load(f)
        data["pid"] = 99999999  # Non-existent PID
        with open(file_path, 'w') as f:
            json.dump(data, f)

        running = port_manager.get_running_instances("claude")
        assert len(running) == 0

    def test_get_running_instances_different_type(self, port_manager, registry):
        """Should only return instances of the specified type."""
        registry.register("synapse-claude-8100", "claude", 8100)
        registry.register("synapse-gemini-8110", "gemini", 8110)

        claude_running = port_manager.get_running_instances("claude")
        gemini_running = port_manager.get_running_instances("gemini")

        assert len(claude_running) == 1
        assert len(gemini_running) == 1

    def test_format_exhaustion_error(self, port_manager, registry):
        """Should format a helpful error message."""
        registry.register("synapse-claude-8100", "claude", 8100)

        error = port_manager.format_exhaustion_error("claude")
        assert "8100-8109" in error
        assert "synapse-claude-8100" in error
        assert "synapse stop claude" in error

    def test_format_exhaustion_error_empty(self, port_manager):
        """Should format error message even when no instances running."""
        error = port_manager.format_exhaustion_error("claude")
        assert "8100-8109" in error
        assert "Running instances:" in error


class TestPortRangesNoOverlap:
    """Tests to ensure port ranges don't overlap."""

    def test_no_overlap(self):
        """Port ranges should not overlap with each other."""
        ranges = list(PORT_RANGES.values())
        for i, (start1, end1) in enumerate(ranges):
            for j, (start2, end2) in enumerate(ranges):
                if i != j:
                    # Ranges should not overlap
                    assert end1 < start2 or end2 < start1, \
                        f"Range {i} ({start1}-{end1}) overlaps with range {j} ({start2}-{end2})"

    def test_range_size(self):
        """Each range should have exactly 10 ports."""
        for agent_type, (start, end) in PORT_RANGES.items():
            assert end - start == 9, f"{agent_type} should have 10 ports (range 0-9)"
