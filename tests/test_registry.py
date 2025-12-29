import os
import json
import pytest
import shutil
from pathlib import Path
from synapse.registry import AgentRegistry

@pytest.fixture
def registry():
    # Setup: Use a temp directory for registry
    reg = AgentRegistry()
    reg.registry_dir = Path("/tmp/a2a_test_registry")
    reg.registry_dir.mkdir(parents=True, exist_ok=True)
    yield reg
    # Teardown: Cleanup temp directory
    shutil.rmtree(reg.registry_dir, ignore_errors=True)

def test_get_agent_id(registry):
    id1 = registry.get_agent_id("claude", 8100)
    id2 = registry.get_agent_id("claude", 8100)
    id3 = registry.get_agent_id("gemini", 8100)
    id4 = registry.get_agent_id("claude", 8101)

    assert id1 == id2  # Deterministic
    assert id1 != id3  # Different agent type
    assert id1 != id4  # Different port
    assert id1 == "synapse-claude-8100"  # New format
    assert id3 == "synapse-gemini-8100"
    assert id4 == "synapse-claude-8101"

def test_register_unregister(registry):
    agent_id = "test_agent_123"
    registry.register(agent_id, "claude", 8100)
    
    expected_file = registry.registry_dir / f"{agent_id}.json"
    assert expected_file.exists()
    
    with open(expected_file) as f:
        data = json.load(f)
        assert data["agent_id"] == agent_id
        assert data["port"] == 8100
        assert data["status"] == "STARTING"

    registry.unregister(agent_id)
    assert not expected_file.exists()

def test_list_agents(registry):
    registry.register("id1", "claude", 8100)
    registry.register("id2", "gemini", 8101)

    agents = registry.list_agents()
    assert len(agents) == 2
    assert "id1" in agents
    assert "id2" in agents
    assert agents["id1"]["agent_type"] == "claude"


def test_register_with_custom_status(registry):
    """Should support custom status on registration."""
    agent_id = "test_busy_agent"
    registry.register(agent_id, "claude", 8100, status="BUSY")

    expected_file = registry.registry_dir / f"{agent_id}.json"
    with open(expected_file) as f:
        data = json.load(f)
        assert data["status"] == "BUSY"


def test_register_includes_endpoint(registry):
    """Registered agent should include endpoint URL."""
    agent_id = "test_endpoint_agent"
    registry.register(agent_id, "claude", 8100)

    agents = registry.list_agents()
    assert agents[agent_id]["endpoint"] == "http://localhost:8100"


def test_register_includes_pid_and_working_dir(registry):
    """Registered agent should include PID and working directory."""
    agent_id = "test_pid_agent"
    registry.register(agent_id, "claude", 8100)

    agents = registry.list_agents()
    assert "pid" in agents[agent_id]
    assert "working_dir" in agents[agent_id]
    assert agents[agent_id]["pid"] == os.getpid()


def test_unregister_nonexistent_agent(registry):
    """Unregistering non-existent agent should not raise error."""
    # Should not raise any exception
    registry.unregister("nonexistent_agent_id")


def test_list_agents_handles_corrupted_json(registry):
    """list_agents should skip corrupted JSON files."""
    # Create a valid agent
    registry.register("valid_agent", "claude", 8100)

    # Create a corrupted JSON file
    corrupted_file = registry.registry_dir / "corrupted_agent.json"
    with open(corrupted_file, 'w') as f:
        f.write("{ invalid json }")

    # Should only return the valid agent
    agents = registry.list_agents()
    assert len(agents) == 1
    assert "valid_agent" in agents


def test_list_agents_empty_registry(registry):
    """list_agents should return empty dict when no agents registered."""
    agents = registry.list_agents()
    assert agents == {}


def test_get_agent_id_format(registry):
    """Agent ID should follow synapse-{type}-{port} format."""
    agent_id = registry.get_agent_id("codex", 8101)

    assert agent_id.startswith("synapse-")
    assert "codex" in agent_id
    assert "8101" in agent_id
    assert agent_id == "synapse-codex-8101"


def test_register_overwrites_existing(registry):
    """Registering same agent_id should overwrite existing entry."""
    agent_id = "overwrite_test"

    registry.register(agent_id, "claude", 8100, status="STARTING")
    registry.register(agent_id, "claude", 8100, status="IDLE")

    agents = registry.list_agents()
    assert len(agents) == 1
    assert agents[agent_id]["status"] == "IDLE"


def test_get_agent_existing(registry):
    """Should return agent info for existing agent."""
    agent_id = "test_get_agent"
    registry.register(agent_id, "claude", 8100)

    info = registry.get_agent(agent_id)
    assert info is not None
    assert info["agent_id"] == agent_id
    assert info["agent_type"] == "claude"
    assert info["port"] == 8100


def test_get_agent_nonexistent(registry):
    """Should return None for non-existent agent."""
    info = registry.get_agent("nonexistent")
    assert info is None


def test_get_agent_corrupted_json(registry):
    """Should return None for corrupted JSON file."""
    # Create a corrupted JSON file
    corrupted_file = registry.registry_dir / "corrupted_agent.json"
    with open(corrupted_file, 'w') as f:
        f.write("{ invalid json }")

    info = registry.get_agent("corrupted_agent")
    assert info is None


def test_update_status(registry):
    """Should update agent status."""
    agent_id = "test_update_status"
    registry.register(agent_id, "claude", 8100, status="STARTING")

    result = registry.update_status(agent_id, "IDLE")
    assert result is True

    info = registry.get_agent(agent_id)
    assert info["status"] == "IDLE"


def test_update_status_nonexistent(registry):
    """Should return False for non-existent agent."""
    result = registry.update_status("nonexistent", "IDLE")
    assert result is False


def test_update_status_multiple_times(registry):
    """Should support multiple status updates."""
    agent_id = "test_multi_status"
    registry.register(agent_id, "claude", 8100, status="STARTING")

    registry.update_status(agent_id, "BUSY")
    assert registry.get_agent(agent_id)["status"] == "BUSY"

    registry.update_status(agent_id, "IDLE")
    assert registry.get_agent(agent_id)["status"] == "IDLE"
