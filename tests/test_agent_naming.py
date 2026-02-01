"""Tests for agent naming and role functionality (v0.3.11)."""

import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from synapse.registry import AgentRegistry


@pytest.fixture
def registry():
    """Setup: Use a temp directory for registry."""
    reg = AgentRegistry()
    reg.registry_dir = Path("/tmp/a2a_test_naming_registry")
    reg.registry_dir.mkdir(parents=True, exist_ok=True)
    yield reg
    # Teardown: Cleanup temp directory
    shutil.rmtree(reg.registry_dir, ignore_errors=True)


# ============================================================================
# Registration with name and role
# ============================================================================


def test_register_with_name_and_role(registry):
    """Should register agent with name and role."""
    agent_id = "synapse-claude-8100"
    registry.register(
        agent_id,
        "claude",
        8100,
        name="my-claude",
        role="コードレビュー担当",
    )

    info = registry.get_agent(agent_id)
    assert info is not None
    assert info["name"] == "my-claude"
    assert info["role"] == "コードレビュー担当"


def test_register_with_name_only(registry):
    """Should register agent with name but no role."""
    agent_id = "synapse-claude-8100"
    registry.register(agent_id, "claude", 8100, name="my-claude")

    info = registry.get_agent(agent_id)
    assert info["name"] == "my-claude"
    assert info.get("role") is None


def test_register_with_role_only(registry):
    """Should register agent with role but no name."""
    agent_id = "synapse-claude-8100"
    registry.register(agent_id, "claude", 8100, role="テスト担当")

    info = registry.get_agent(agent_id)
    assert info.get("name") is None
    assert info["role"] == "テスト担当"


def test_register_without_name_role(registry):
    """Should register agent without name or role (backward compatibility)."""
    agent_id = "synapse-claude-8100"
    registry.register(agent_id, "claude", 8100)

    info = registry.get_agent(agent_id)
    assert info.get("name") is None
    assert info.get("role") is None


# ============================================================================
# Agent resolution by name
# ============================================================================


def test_resolve_agent_by_name(registry):
    """Should resolve agent by custom name."""
    registry.register("synapse-claude-8100", "claude", 8100, name="my-claude")
    registry.register("synapse-gemini-8110", "gemini", 8110, name="my-gemini")

    info = registry.resolve_agent("my-claude")
    assert info is not None
    assert info["agent_id"] == "synapse-claude-8100"


def test_resolve_agent_by_id(registry):
    """Should resolve agent by full ID."""
    registry.register("synapse-claude-8100", "claude", 8100, name="my-claude")

    info = registry.resolve_agent("synapse-claude-8100")
    assert info is not None
    assert info["agent_id"] == "synapse-claude-8100"


def test_resolve_agent_by_type_port(registry):
    """Should resolve agent by type-port shorthand."""
    registry.register("synapse-claude-8100", "claude", 8100)

    info = registry.resolve_agent("claude-8100")
    assert info is not None
    assert info["agent_id"] == "synapse-claude-8100"


def test_resolve_agent_by_type_single(registry):
    """Should resolve agent by type when only one instance exists."""
    registry.register("synapse-claude-8100", "claude", 8100)

    info = registry.resolve_agent("claude")
    assert info is not None
    assert info["agent_id"] == "synapse-claude-8100"


def test_resolve_agent_by_type_ambiguous(registry):
    """Should return None when multiple agents of same type exist."""
    registry.register("synapse-claude-8100", "claude", 8100)
    registry.register("synapse-claude-8101", "claude", 8101)

    info = registry.resolve_agent("claude")
    assert info is None  # Ambiguous


def test_resolve_agent_not_found(registry):
    """Should return None for non-existent target."""
    registry.register("synapse-claude-8100", "claude", 8100)

    info = registry.resolve_agent("nonexistent")
    assert info is None


def test_name_priority_over_type(registry):
    """Custom name should have priority over type resolution."""
    # Agent named "claude" (not the type, the custom name)
    registry.register("synapse-gemini-8110", "gemini", 8110, name="claude")
    # Actual claude agent
    registry.register("synapse-claude-8100", "claude", 8100)

    # Should resolve to the one named "claude" (gemini), not type "claude"
    info = registry.resolve_agent("claude")
    assert info is not None
    assert info["agent_id"] == "synapse-gemini-8110"
    assert info["agent_type"] == "gemini"


def test_resolve_agent_priority_order(registry):
    """Verify resolution priority: name > ID > type-port > type."""
    # Register multiple agents
    registry.register("synapse-claude-8100", "claude", 8100, name="primary")
    registry.register("synapse-gemini-8110", "gemini", 8110, name="synapse-claude-8100")

    # Name "primary" should resolve to claude
    info = registry.resolve_agent("primary")
    assert info["agent_id"] == "synapse-claude-8100"

    # ID "synapse-claude-8100" should resolve to claude (not gemini with that name)
    # Actually, name takes priority, so this should be gemini
    info = registry.resolve_agent("synapse-claude-8100")
    # Name has highest priority
    assert info["agent_id"] == "synapse-gemini-8110"


# ============================================================================
# Name uniqueness validation
# ============================================================================


def test_is_name_unique_true(registry):
    """Should return True when name is unique."""
    registry.register("synapse-claude-8100", "claude", 8100, name="my-claude")

    assert registry.is_name_unique("other-name") is True


def test_is_name_unique_false(registry):
    """Should return False when name is already taken."""
    registry.register("synapse-claude-8100", "claude", 8100, name="my-claude")

    assert registry.is_name_unique("my-claude") is False


def test_is_name_unique_exclude_self(registry):
    """Should return True when checking own name with exclusion."""
    registry.register("synapse-claude-8100", "claude", 8100, name="my-claude")

    # When updating own name, exclude self from check
    assert (
        registry.is_name_unique("my-claude", exclude_agent_id="synapse-claude-8100")
        is True
    )


def test_is_name_unique_case_sensitive(registry):
    """Names should be case-sensitive."""
    registry.register("synapse-claude-8100", "claude", 8100, name="my-claude")

    assert registry.is_name_unique("My-Claude") is True
    assert registry.is_name_unique("MY-CLAUDE") is True


def test_is_name_unique_empty_registry(registry):
    """Should return True when registry is empty."""
    assert registry.is_name_unique("any-name") is True


# ============================================================================
# Update name and role
# ============================================================================


def test_update_name_and_role(registry):
    """Should update both name and role."""
    agent_id = "synapse-claude-8100"
    registry.register(agent_id, "claude", 8100)

    result = registry.update_name(agent_id, "my-claude", role="テスト担当")
    assert result is True

    info = registry.get_agent(agent_id)
    assert info["name"] == "my-claude"
    assert info["role"] == "テスト担当"


def test_update_name_only(registry):
    """Should update name only, keeping role unchanged."""
    agent_id = "synapse-claude-8100"
    registry.register(agent_id, "claude", 8100, role="original-role")

    result = registry.update_name(agent_id, "new-name")
    assert result is True

    info = registry.get_agent(agent_id)
    assert info["name"] == "new-name"
    assert info["role"] == "original-role"


def test_update_role_only(registry):
    """Should update role only, keeping name unchanged."""
    agent_id = "synapse-claude-8100"
    registry.register(agent_id, "claude", 8100, name="original-name")

    result = registry.update_name(agent_id, None, role="new-role")
    assert result is True

    info = registry.get_agent(agent_id)
    assert info["name"] == "original-name"
    assert info["role"] == "new-role"


def test_clear_name_and_role(registry):
    """Should clear name and role when both are None."""
    agent_id = "synapse-claude-8100"
    registry.register(agent_id, "claude", 8100, name="my-claude", role="テスト担当")

    result = registry.update_name(agent_id, None, role=None, clear=True)
    assert result is True

    info = registry.get_agent(agent_id)
    assert info.get("name") is None
    assert info.get("role") is None


def test_update_name_nonexistent_agent(registry):
    """Should return False for non-existent agent."""
    result = registry.update_name("nonexistent", "new-name")
    assert result is False


def test_update_name_preserves_other_fields(registry):
    """update_name should not modify other fields."""
    agent_id = "synapse-claude-8100"
    registry.register(agent_id, "claude", 8100, status="READY")

    registry.update_name(agent_id, "my-claude", role="テスト担当")

    info = registry.get_agent(agent_id)
    assert info["agent_type"] == "claude"
    assert info["port"] == 8100
    assert info["status"] == "READY"


# ============================================================================
# Edge cases
# ============================================================================


def test_name_with_special_characters(registry):
    """Should handle names with special characters."""
    agent_id = "synapse-claude-8100"
    registry.register(agent_id, "claude", 8100, name="my_claude-v2.0")

    info = registry.resolve_agent("my_claude-v2.0")
    assert info is not None
    assert info["agent_id"] == agent_id


def test_role_with_unicode(registry):
    """Should handle roles with unicode characters."""
    agent_id = "synapse-claude-8100"
    registry.register(agent_id, "claude", 8100, role="コードレビュー担当 🔍")

    info = registry.get_agent(agent_id)
    assert info["role"] == "コードレビュー担当 🔍"


def test_resolve_agent_with_live_check(registry):
    """resolve_agent should use get_live_agents for process check."""
    agent_id = "synapse-claude-8100"
    registry.register(agent_id, "claude", 8100, name="my-claude")

    # Mock get_live_agents to return the agent
    with patch.object(registry, "get_live_agents") as mock_live:
        mock_live.return_value = {agent_id: registry.get_agent(agent_id)}
        info = registry.resolve_agent("my-claude")
        assert info is not None
        mock_live.assert_called_once()
