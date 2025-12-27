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
    id1 = registry.get_agent_id("claude", "/tmp/project")
    id2 = registry.get_agent_id("claude", "/tmp/project")
    id3 = registry.get_agent_id("gemini", "/tmp/project")

    assert id1 == id2  # Deterministic
    assert id1 != id3  # Different agent type
    assert len(id1) == 64  # SHA256 hex digest length

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
