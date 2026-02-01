"""Tests for _resolve_target_agent function in tools/a2a.py (v0.3.11)."""

import pytest

from synapse.tools.a2a import _resolve_target_agent

# ============================================================================
# Test fixtures
# ============================================================================


@pytest.fixture
def agents_with_names():
    """Sample agents with custom names."""
    return {
        "synapse-claude-8100": {
            "agent_id": "synapse-claude-8100",
            "agent_type": "claude",
            "port": 8100,
            "name": "my-claude",
            "role": "code reviewer",
        },
        "synapse-gemini-8110": {
            "agent_id": "synapse-gemini-8110",
            "agent_type": "gemini",
            "port": 8110,
            "name": "my-gemini",
        },
        "synapse-codex-8120": {
            "agent_id": "synapse-codex-8120",
            "agent_type": "codex",
            "port": 8120,
            # No name assigned
        },
    }


@pytest.fixture
def agents_multiple_claude():
    """Sample agents with multiple claude instances."""
    return {
        "synapse-claude-8100": {
            "agent_id": "synapse-claude-8100",
            "agent_type": "claude",
            "port": 8100,
            "name": "reviewer",
        },
        "synapse-claude-8101": {
            "agent_id": "synapse-claude-8101",
            "agent_type": "claude",
            "port": 8101,
            "name": "tester",
        },
    }


# ============================================================================
# Priority 1: Custom name resolution
# ============================================================================


def test_resolve_by_custom_name(agents_with_names):
    """Should resolve agent by custom name (highest priority)."""
    info, error = _resolve_target_agent("my-claude", agents_with_names)

    assert error is None
    assert info is not None
    assert info["agent_id"] == "synapse-claude-8100"
    assert info["name"] == "my-claude"


def test_resolve_by_custom_name_gemini(agents_with_names):
    """Should resolve gemini by custom name."""
    info, error = _resolve_target_agent("my-gemini", agents_with_names)

    assert error is None
    assert info is not None
    assert info["agent_id"] == "synapse-gemini-8110"


def test_custom_name_is_case_sensitive(agents_with_names):
    """Custom name matching should be case-sensitive."""
    info, error = _resolve_target_agent("My-Claude", agents_with_names)

    # Should not find (case mismatch)
    # Falls through to other resolution methods
    assert info is None
    assert error is not None


# ============================================================================
# Priority 2: Agent ID resolution
# ============================================================================


def test_resolve_by_agent_id(agents_with_names):
    """Should resolve agent by full agent ID."""
    info, error = _resolve_target_agent("synapse-codex-8120", agents_with_names)

    assert error is None
    assert info is not None
    assert info["agent_id"] == "synapse-codex-8120"


def test_resolve_by_agent_id_when_name_exists(agents_with_names):
    """Agent ID should work even when agent has a custom name."""
    info, error = _resolve_target_agent("synapse-claude-8100", agents_with_names)

    assert error is None
    assert info is not None
    assert info["agent_id"] == "synapse-claude-8100"


# ============================================================================
# Priority 3: Type-port shorthand
# ============================================================================


def test_resolve_by_type_port(agents_with_names):
    """Should resolve agent by type-port shorthand."""
    info, error = _resolve_target_agent("claude-8100", agents_with_names)

    assert error is None
    assert info is not None
    assert info["agent_id"] == "synapse-claude-8100"


def test_resolve_by_type_port_codex(agents_with_names):
    """Should resolve codex by type-port shorthand."""
    info, error = _resolve_target_agent("codex-8120", agents_with_names)

    assert error is None
    assert info is not None
    assert info["agent_id"] == "synapse-codex-8120"


# ============================================================================
# Priority 4: Agent type (single instance)
# ============================================================================


def test_resolve_by_type_single_instance(agents_with_names):
    """Should resolve agent by type when only one instance exists."""
    info, error = _resolve_target_agent("codex", agents_with_names)

    assert error is None
    assert info is not None
    assert info["agent_id"] == "synapse-codex-8120"


def test_resolve_by_type_ambiguous(agents_multiple_claude):
    """Should return error when multiple agents of same type exist."""
    info, error = _resolve_target_agent("claude", agents_multiple_claude)

    assert info is None
    assert error is not None
    assert "Ambiguous" in error


def test_resolve_by_type_ambiguous_shows_names(agents_multiple_claude):
    """Error message should include custom names as hints."""
    info, error = _resolve_target_agent("claude", agents_multiple_claude)

    assert error is not None
    # Should suggest using custom names
    assert "reviewer" in error or "tester" in error


# ============================================================================
# Not found
# ============================================================================


def test_resolve_not_found(agents_with_names):
    """Should return error when no agent matches."""
    info, error = _resolve_target_agent("nonexistent", agents_with_names)

    assert info is None
    assert error is not None
    assert "No agent found" in error


def test_resolve_empty_agents():
    """Should return error when no agents registered."""
    info, error = _resolve_target_agent("claude", {})

    assert info is None
    assert error is not None


# ============================================================================
# Name takes priority over type
# ============================================================================


def test_name_priority_over_type():
    """Custom name 'claude' should resolve to the named agent, not type."""
    agents = {
        "synapse-gemini-8110": {
            "agent_id": "synapse-gemini-8110",
            "agent_type": "gemini",
            "port": 8110,
            "name": "claude",  # Gemini agent named "claude"
        },
        "synapse-claude-8100": {
            "agent_id": "synapse-claude-8100",
            "agent_type": "claude",
            "port": 8100,
        },
    }

    # Should find the gemini with name "claude", not the actual claude agent
    info, error = _resolve_target_agent("claude", agents)

    assert error is None
    assert info is not None
    assert info["agent_id"] == "synapse-gemini-8110"
    assert info["agent_type"] == "gemini"
