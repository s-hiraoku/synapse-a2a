"""Tests for status unification (READY/PROCESSING system)."""

import shutil
import tempfile
from pathlib import Path

import pytest

from synapse.registry import AgentRegistry


@pytest.fixture
def temp_registry():
    """Create a test registry with temp directory."""
    reg = AgentRegistry()
    reg.registry_dir = Path(tempfile.mkdtemp(prefix="a2a_test_status_unification_"))
    yield reg
    shutil.rmtree(reg.registry_dir, ignore_errors=True)


class TestStatusUnification:
    """Tests for unified READY/PROCESSING status system."""

    def test_initial_status_is_processing(self, temp_registry):
        """Agent should start with PROCESSING status (startup in progress)."""
        temp_registry.register("synapse-claude-8100", "claude", 8100)

        # CodeRabbit fix: Use registry method instead of direct file read to get consistent status
        agent_data = temp_registry.get_agent("synapse-claude-8100")

        # Initial status should be what's set in register()
        # which should be PROCESSING for startup
        assert agent_data.get("status") == "PROCESSING"

    def test_ready_status_when_idle(self, temp_registry):
        """Agent should have READY status when in IDLE state (waiting for input)."""
        temp_registry.register("synapse-claude-8100", "claude", 8100)

        # Simulate IDLE state transition
        temp_registry.update_status("synapse-claude-8100", "READY")

        # CodeRabbit fix: Use registry method instead of direct file read
        agent_data = temp_registry.get_agent("synapse-claude-8100")

        assert agent_data.get("status") == "READY"

    def test_processing_status_when_busy(self, temp_registry):
        """Agent should have PROCESSING status when handling requests."""
        temp_registry.register("synapse-claude-8100", "claude", 8100)

        # Simulate BUSY state
        temp_registry.update_status("synapse-claude-8100", "PROCESSING")

        # CodeRabbit fix: Use registry method instead of direct file read
        agent_data = temp_registry.get_agent("synapse-claude-8100")

        assert agent_data.get("status") == "PROCESSING"

    def test_status_transition_processing_to_ready(self, temp_registry):
        """Status should transition from PROCESSING to READY when idle."""
        agent_id = "synapse-claude-8100"
        temp_registry.register(agent_id, "claude", 8100)

        # CodeRabbit fix: Verify initial PROCESSING status
        initial_data = temp_registry.get_agent(agent_id)
        assert initial_data.get("status") == "PROCESSING"

        # Transition to READY (when agent becomes idle)
        temp_registry.update_status(agent_id, "READY")

        # CodeRabbit fix: Use registry method instead of direct file read
        updated_data = temp_registry.get_agent(agent_id)

        assert updated_data.get("status") == "READY"

    def test_status_transition_ready_to_processing(self, temp_registry):
        """Status should transition from READY to PROCESSING when handling work."""
        agent_id = "synapse-claude-8100"
        temp_registry.register(agent_id, "claude", 8100)
        temp_registry.update_status(agent_id, "READY")

        # Transition to PROCESSING (when handling a request)
        temp_registry.update_status(agent_id, "PROCESSING")

        # CodeRabbit fix: Use registry method instead of direct file read
        agent_data = temp_registry.get_agent(agent_id)

        assert agent_data.get("status") == "PROCESSING"

    def test_no_old_status_values(self, temp_registry):
        """Registry should only use READY/PROCESSING, not BUSY/IDLE."""
        agent_id = "synapse-claude-8100"
        temp_registry.register(agent_id, "claude", 8100)

        # CodeRabbit fix: Use registry method instead of direct file read
        agent_data = temp_registry.get_agent(agent_id)

        status = agent_data.get("status")
        # Should not contain old status values
        assert status not in ["BUSY", "IDLE", "STARTING"]
        # Should be one of the new values
        assert status in ["READY", "PROCESSING"]

    def test_multiple_agents_different_statuses(self, temp_registry):
        """Multiple agents can have different statuses simultaneously."""
        # Agent 1: READY
        temp_registry.register("synapse-claude-8100", "claude", 8100)
        temp_registry.update_status("synapse-claude-8100", "READY")

        # Agent 2: PROCESSING
        temp_registry.register("synapse-claude-8101", "claude", 8101)
        temp_registry.update_status("synapse-claude-8101", "PROCESSING")

        agents = temp_registry.list_agents()

        assert agents["synapse-claude-8100"]["status"] == "READY"
        assert agents["synapse-claude-8101"]["status"] == "PROCESSING"
