import json
import os
import shutil
import subprocess
import sys
import textwrap
import threading
from contextlib import contextmanager
from pathlib import Path

import pytest

from synapse.registry import AgentRegistry, NameConflictError, resolve_uds_path
from synapse.status import STATUS_STYLES, WAITING_FOR_INPUT, is_valid_status


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
        assert data["status"] == "PROCESSING"

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


def test_waiting_for_input_is_valid_registry_status(registry):
    """WAITING_FOR_INPUT should be a first-class registry status."""
    agent_id = "test_waiting_for_input_agent"
    registry.register(agent_id, "claude", 8100)

    assert is_valid_status(WAITING_FOR_INPUT) is True
    assert WAITING_FOR_INPUT in STATUS_STYLES
    assert registry.update_status(agent_id, WAITING_FOR_INPUT) is True
    assert registry.get_agent(agent_id)["status"] == WAITING_FOR_INPUT


def test_register_includes_endpoint(registry):
    """Registered agent should include endpoint URL."""
    agent_id = "test_endpoint_agent"
    registry.register(agent_id, "claude", 8100)

    agents = registry.list_agents()
    assert agents[agent_id]["endpoint"] == "http://localhost:8100"


def test_register_includes_uds_path(registry, monkeypatch, tmp_path):
    """Registered agent should include resolved UDS path."""
    monkeypatch.setenv("SYNAPSE_UDS_DIR", str(tmp_path))
    agent_id = "test_uds_agent"
    registry.register(agent_id, "claude", 8100)

    agents = registry.list_agents()
    uds_path = agents[agent_id]["uds_path"]
    assert uds_path == str(resolve_uds_path(agent_id))
    assert uds_path.startswith(str(tmp_path))


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
    with open(corrupted_file, "w") as f:
        f.write("{ invalid json }")

    # Should only return the valid agent
    agents = registry.list_agents()
    assert len(agents) == 1
    assert "valid_agent" in agents


def test_list_agents_empty_registry(registry):
    """list_agents should return empty dict when no agents registered."""
    agents = registry.list_agents()
    assert agents == {}


# --- Issue #332: parent-child tracking + orphan detection -----------------

# A PID that is virtually guaranteed not to map to a live process on any
# POSIX system in test (max PID is typically 32768 or 4194304; anything above
# INT32_MAX is invalid). Used to simulate a dead parent PID without risking
# an accidental hit on a real process.
_DEAD_PID = 2**31 - 1


def test_spawned_by_recorded_in_registry(registry):
    """register() should persist spawned_by when the child is spawned by a parent."""
    registry.register(
        "child_agent",
        "claude",
        8200,
        spawned_by="synapse-codex-8100",
    )

    agents = registry.list_agents()
    assert agents["child_agent"]["spawned_by"] == "synapse-codex-8100"


def test_get_orphans_finds_dead_parent_pid(registry):
    """A child whose parent registry exists but whose parent PID is dead is an orphan."""
    parent_file = registry.registry_dir / "synapse-codex-8100.json"
    with open(parent_file, "w") as f:
        json.dump(
            {
                "agent_id": "synapse-codex-8100",
                "agent_type": "codex",
                "port": 8100,
                "pid": _DEAD_PID,
                "status": "READY",
            },
            f,
        )
    registry.register(
        "synapse-claude-8200",
        "claude",
        8200,
        spawned_by="synapse-codex-8100",
    )

    orphans = registry.get_orphans()
    assert "synapse-claude-8200" in orphans
    assert orphans["synapse-claude-8200"]["spawned_by"] == "synapse-codex-8100"


def test_get_orphans_finds_missing_parent_entry(registry):
    """A child whose parent registry entry is gone is an orphan."""
    registry.register(
        "synapse-claude-8200",
        "claude",
        8200,
        spawned_by="synapse-codex-9999",
    )

    orphans = registry.get_orphans()
    assert "synapse-claude-8200" in orphans


def test_get_orphans_excludes_live_parent(registry):
    """A child whose parent process is live (same as test process) is not an orphan."""
    parent_file = registry.registry_dir / "synapse-codex-8100.json"
    with open(parent_file, "w") as f:
        json.dump(
            {
                "agent_id": "synapse-codex-8100",
                "agent_type": "codex",
                "port": 8100,
                "pid": os.getpid(),
                "status": "READY",
            },
            f,
        )
    registry.register(
        "synapse-claude-8200",
        "claude",
        8200,
        spawned_by="synapse-codex-8100",
    )

    orphans = registry.get_orphans()
    assert "synapse-claude-8200" not in orphans


def test_get_orphans_excludes_agents_with_no_spawned_by(registry):
    """Root agents (no spawned_by) are never orphans."""
    registry.register("synapse-claude-8100", "claude", 8100)

    orphans = registry.get_orphans()
    assert "synapse-claude-8100" not in orphans


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


def test_register_raises_if_atomic_write_lost(registry):
    """Register should fail if the written file cannot be verified."""
    original_write = registry._write_json_atomic

    def truncate_after_write(file_path: Path, data: dict) -> None:
        original_write(file_path, data)
        file_path.write_text("", encoding="utf-8")

    registry._write_json_atomic = truncate_after_write  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="Registry write verification failed"):
        registry.register("lost-write-agent", "claude", 8100)


def test_atexit_unregister_on_normal_exit(tmp_path):
    """A normal Python exit should remove the registry file registered by the process."""
    registry_dir = tmp_path / "registry"
    uds_dir = tmp_path / "uds"
    script = textwrap.dedent(
        """
        import sys
        from pathlib import Path
        from synapse.registry import AgentRegistry

        registry = AgentRegistry()
        path = registry.register("atexit-agent", "claude", 8100)
        assert Path(path).exists()
        sys.exit(0)
        """
    )
    env = os.environ.copy()
    env["SYNAPSE_REGISTRY_DIR"] = str(registry_dir)
    env["SYNAPSE_UDS_DIR"] = str(uds_dir)
    env["PYTHONPATH"] = os.getcwd()

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=os.getcwd(),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert not (registry_dir / "atexit-agent.json").exists()


def test_register_rejects_duplicate_custom_name(registry):
    """Register should reject duplicate custom names across different agent IDs."""
    registry.register("agent_a", "claude", 8100, name="Alice")
    with pytest.raises(NameConflictError):
        registry.register("agent_b", "gemini", 8110, name="Alice")


def test_register_allows_same_agent_id_same_name_overwrite(registry):
    """Re-registering the same agent ID with same name should be allowed."""
    registry.register("agent_same", "claude", 8100, name="Alice")
    registry.register("agent_same", "claude", 8100, name="Alice", status="READY")
    assert registry.get_agent("agent_same")["status"] == "READY"


def test_register_duplicate_name_concurrent_only_one_succeeds(registry):
    """Concurrent same-name registration should allow only one writer."""
    errors: list[Exception] = []
    barrier = threading.Barrier(2)

    def register_one(agent_id: str, port: int) -> None:
        try:
            barrier.wait(timeout=2.0)
            registry.register(agent_id, "codex", port, name="Alice")
        except Exception as e:  # noqa: BLE001 - collect for assertion
            errors.append(e)

    t1 = threading.Thread(target=register_one, args=("agent_c1", 8122))
    t2 = threading.Thread(target=register_one, args=("agent_c2", 8123))
    t1.start()
    t2.start()
    t1.join(timeout=2.0)
    t2.join(timeout=2.0)

    # Exactly one NameConflictError is expected.
    conflicts = [e for e in errors if isinstance(e, NameConflictError)]
    assert len(conflicts) == 1

    named = [
        info for info in registry.list_agents().values() if info.get("name") == "Alice"
    ]
    assert len(named) == 1


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
    with open(corrupted_file, "w") as f:
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


def test_atomic_updates_use_registry_write_lock(registry):
    """update_* operations should all run under registry-wide write lock."""
    agent_id = "test_write_lock_updates"
    registry.register(agent_id, "claude", 8100, name="lock-agent")

    entered = 0

    @contextmanager
    def fake_lock():
        nonlocal entered
        entered += 1
        yield

    registry._registry_write_lock = fake_lock  # type: ignore[method-assign]

    assert registry.update_status(agent_id, "READY") is True
    assert registry.update_transport(agent_id, "UDS→") is True
    assert registry.update_name(agent_id, "lock-agent-renamed") is True
    assert entered == 3


# ============================================================================
# Tests for update_transport (Transport Display Feature)
# ============================================================================


def test_update_transport_sender(registry):
    """update_transport sets sender format (UDS→)."""
    agent_id = "test_transport_sender"
    registry.register(agent_id, "claude", 8100)

    result = registry.update_transport(agent_id, "UDS→")
    assert result is True

    info = registry.get_agent(agent_id)
    assert info["active_transport"] == "UDS→"


def test_update_transport_receiver(registry):
    """update_transport sets receiver format (→UDS)."""
    agent_id = "test_transport_receiver"
    registry.register(agent_id, "gemini", 8110)

    result = registry.update_transport(agent_id, "→UDS")
    assert result is True

    info = registry.get_agent(agent_id)
    assert info["active_transport"] == "→UDS"


def test_update_transport_tcp(registry):
    """update_transport works with TCP format."""
    agent_id = "test_transport_tcp"
    registry.register(agent_id, "claude", 8100)

    # Sender TCP
    result = registry.update_transport(agent_id, "TCP→")
    assert result is True
    assert registry.get_agent(agent_id)["active_transport"] == "TCP→"

    # Receiver TCP
    result = registry.update_transport(agent_id, "→TCP")
    assert result is True
    assert registry.get_agent(agent_id)["active_transport"] == "→TCP"


def test_update_transport_clear(registry):
    """update_transport clears active_transport with None."""
    agent_id = "test_transport_clear"
    registry.register(agent_id, "claude", 8100)

    # Set transport
    registry.update_transport(agent_id, "UDS→")
    assert registry.get_agent(agent_id)["active_transport"] == "UDS→"

    # Clear transport
    result = registry.update_transport(agent_id, None)
    assert result is True

    info = registry.get_agent(agent_id)
    assert info.get("active_transport") is None


def test_update_transport_nonexistent(registry):
    """update_transport returns False for non-existent agent."""
    result = registry.update_transport("nonexistent", "UDS→")
    assert result is False


def test_update_transport_preserves_other_fields(registry):
    """update_transport should not modify other fields."""
    agent_id = "test_transport_preserve"
    registry.register(agent_id, "claude", 8100, status="READY")

    registry.update_transport(agent_id, "UDS→")

    info = registry.get_agent(agent_id)
    assert info["agent_type"] == "claude"
    assert info["port"] == 8100
    assert info["status"] == "READY"
    assert info["active_transport"] == "UDS→"


# ── update_session_id ────────────────────────────────────────


def test_update_session_id(registry):
    """update_session_id should write and read back the session_id."""
    agent_id = "test_session_id"
    registry.register(agent_id, "claude", 8100)

    result = registry.update_session_id(agent_id, "conv-abc-123")
    assert result is True

    info = registry.get_agent(agent_id)
    assert info["session_id"] == "conv-abc-123"


def test_update_session_id_none_clears(registry):
    """update_session_id(None) should remove the session_id key."""
    agent_id = "test_session_id_clear"
    registry.register(agent_id, "claude", 8100)

    registry.update_session_id(agent_id, "conv-xyz")
    registry.update_session_id(agent_id, None)

    info = registry.get_agent(agent_id)
    assert "session_id" not in info


def test_update_session_id_nonexistent(registry):
    """update_session_id returns False for non-existent agent."""
    result = registry.update_session_id("nonexistent", "conv-123")
    assert result is False
