"""Tests for controller status synchronization to registry."""

import json
from unittest.mock import patch

import pytest

from synapse.controller import TerminalController
from synapse.registry import AgentRegistry


@pytest.fixture
def temp_registry_dir(tmp_path):
    """Create a temporary registry directory."""
    return tmp_path


@pytest.fixture
def temp_registry(temp_registry_dir):
    """Create a test registry with temp directory."""
    reg = AgentRegistry()
    reg.registry_dir = temp_registry_dir
    return reg


class TestStatusSyncToRegistry:
    """Tests for status synchronization from controller to registry."""

    def test_status_sync_to_registry_on_ready(self, temp_registry):
        """Status should sync to registry when transitioning to READY."""
        agent_id = "test-agent-8100"

        # Create controller
        controller = TerminalController(
            command="echo",
            idle_regex="BRACKETED_PASTE_MODE",
            registry=temp_registry,
            agent_id=agent_id,
            agent_type="test",
            port=8100,
        )

        # Register the agent
        temp_registry.register(agent_id, "test", 8100, status="PROCESSING")

        # Initial state: PROCESSING
        assert controller.status == "PROCESSING"

        # Simulate idle detection (BRACKETED_PASTE_MODE pattern)
        idle_output = b"\x1b[?2004h"
        controller.output_buffer = idle_output

        with patch("synapse.controller.threading.Thread"):
            controller._check_idle_state(idle_output)

        # Controller status should be READY
        assert controller.status == "READY"

        # Registry should be updated
        registry_data = temp_registry.get_agent(agent_id)
        assert registry_data is not None
        assert registry_data.get("status") == "READY"

    def test_status_sync_to_registry_on_processing(self, temp_registry):
        """Status should sync to registry when transitioning to PROCESSING."""
        agent_id = "test-agent-2"

        # Create controller
        controller = TerminalController(
            command="echo",
            idle_regex="BRACKETED_PASTE_MODE",
            registry=temp_registry,
            agent_id=agent_id,
            agent_type="test",
            port=8101,
        )

        # Register and set status to READY
        temp_registry.register(agent_id, "test", 8101, status="PROCESSING")

        idle_output = b"\x1b[?2004h"
        controller.output_buffer = idle_output
        with patch("synapse.controller.threading.Thread"):
            controller._check_idle_state(idle_output)
        assert controller.status == "READY"

        # Now simulate non-idle output (no BRACKETED_PASTE_MODE)
        busy_output = b"some agent output"
        controller.output_buffer = busy_output
        controller._check_idle_state(busy_output)

        # Controller status should be PROCESSING
        assert controller.status == "PROCESSING"

        # Registry should be updated
        registry_data = temp_registry.get_agent(agent_id)
        assert registry_data is not None
        assert registry_data.get("status") == "PROCESSING"

    def test_status_only_updates_when_changed(self, temp_registry):
        """Registry should only update when status actually changes (performance)."""
        agent_id = "test-agent-3"

        # Create controller
        controller = TerminalController(
            command="echo",
            idle_regex="BRACKETED_PASTE_MODE",
            registry=temp_registry,
            agent_id=agent_id,
            agent_type="test",
            port=8102,
        )

        # Register agent first
        temp_registry.register(agent_id, "test", 8102, status="PROCESSING")

        # Count registry updates
        update_count = 0
        original_update = temp_registry.update_status

        def count_updates(*args, **kwargs):
            nonlocal update_count
            update_count += 1
            return original_update(*args, **kwargs)

        with patch.object(temp_registry, "update_status", side_effect=count_updates):
            # Send same idle output multiple times (READY → READY)
            idle_output = b"\x1b[?2004h"
            controller.output_buffer = idle_output

            with patch("synapse.controller.threading.Thread"):
                # First time: PROCESSING → READY (should update)
                controller._check_idle_state(idle_output)
                first_count = update_count

                # Second time: READY → READY (should NOT update)
                controller._check_idle_state(idle_output + b"more data")
                second_count = update_count

        # Should only update once (on first transition)
        assert first_count == 1
        assert second_count == 1  # No additional update

    def test_status_persisted_in_registry_file(self, temp_registry):
        """Status should be persisted in registry JSON file."""
        agent_id = "test-agent-4"

        controller = TerminalController(
            command="echo",
            idle_regex="BRACKETED_PASTE_MODE",
            registry=temp_registry,
            agent_id=agent_id,
            agent_type="test",
            port=8103,
        )

        # Register the agent
        temp_registry.register(agent_id, "test", 8103, status="PROCESSING")

        # Transition to READY
        idle_output = b"\x1b[?2004h"
        controller.output_buffer = idle_output
        with patch("synapse.controller.threading.Thread"):
            controller._check_idle_state(idle_output)

        # Read registry file directly
        registry_file = temp_registry.registry_dir / f"{agent_id}.json"
        assert registry_file.exists()

        with open(registry_file) as f:
            data = json.load(f)

        assert data.get("status") == "READY"
