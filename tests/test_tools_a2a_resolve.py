"""Tests for target resolution helpers used by ``synapse send``."""

import pytest

from synapse.tools.a2a import _pick_best_agent, _resolve_target_agent

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
            "status": "READY",
        },
        "synapse-claude-8101": {
            "agent_id": "synapse-claude-8101",
            "agent_type": "claude",
            "port": 8101,
            "name": "tester",
            "status": "READY",
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


def test_resolve_by_type_multiple_picks_lowest_port(agents_multiple_claude):
    """When multiple agents of same type exist, pick the one with lowest port."""
    info, error = _resolve_target_agent("claude", agents_multiple_claude)

    assert error is None
    assert info is not None
    assert info["agent_id"] == "synapse-claude-8100"
    assert info["port"] == 8100


def test_resolve_by_type_multiple_prefers_ready(agents_multiple_claude):
    """When multiple agents exist, prefer READY over lower port."""
    agents_multiple_claude["synapse-claude-8100"]["status"] = "PROCESSING"
    # Make the higher-port agent READY
    agents_multiple_claude["synapse-claude-8101"]["status"] = "READY"
    info, error = _resolve_target_agent("claude", agents_multiple_claude)

    assert error is None
    assert info is not None
    assert info["agent_id"] == "synapse-claude-8101"


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


# ============================================================================
# Self-target and sendable-only filtering
# ============================================================================


def test_resolve_target_excludes_sender_on_type_match(agents_multiple_claude):
    """Type-based resolution must not select the sending agent itself."""
    info, error = _resolve_target_agent(
        "claude",
        agents_multiple_claude,
        sender_id="synapse-claude-8100",
    )

    assert error is None
    assert info is not None
    assert info["agent_id"] == "synapse-claude-8101"


def test_resolve_target_exact_agent_id_match_to_self_returns_error(agents_with_names):
    """Explicit self-send by agent id should return a clear error."""
    info, error = _resolve_target_agent(
        "synapse-claude-8100",
        agents_with_names,
        sender_id="synapse-claude-8100",
    )

    assert info is None
    assert error == "Cannot send to self (use target: self in workflows)"


def test_resolve_target_partial_match_with_sender_in_candidates():
    """Partial matches should exclude the sender before choosing a candidate."""
    agents = {
        "synapse-claude-8100": {
            "agent_id": "synapse-claude-8100",
            "agent_type": "claude",
            "port": 8100,
            "status": "READY",
        },
        "synapse-superclaude-8102": {
            "agent_id": "synapse-superclaude-8102",
            "agent_type": "superclaude",
            "port": 8102,
            "status": "READY",
        },
    }

    info, error = _resolve_target_agent(
        "claude",
        agents,
        sender_id="synapse-claude-8100",
    )

    assert error is None
    assert info is not None
    assert info["agent_id"] == "synapse-superclaude-8102"


def test_pick_best_agent_excludes_processing():
    """READY agents should beat PROCESSING agents before ranking."""
    matches = [
        {
            "agent_id": "synapse-claude-8100",
            "agent_type": "claude",
            "port": 8100,
            "status": "PROCESSING",
        },
        {
            "agent_id": "synapse-claude-8101",
            "agent_type": "claude",
            "port": 8101,
            "status": "READY",
        },
    ]

    best = _pick_best_agent(matches)

    assert best["agent_id"] == "synapse-claude-8101"


def test_pick_best_agent_all_non_ready_returns_empty():
    """When sendable_only is enabled, all non-READY candidates are excluded."""
    matches = [
        {
            "agent_id": "synapse-claude-8100",
            "agent_type": "claude",
            "port": 8100,
            "status": "PROCESSING",
        },
        {
            "agent_id": "synapse-claude-8101",
            "agent_type": "claude",
            "port": 8101,
            "status": "WAITING",
        },
    ]

    assert _pick_best_agent(matches) == {}


def test_resolve_single_processing_match_returns_no_agent_found():
    """A single PROCESSING match must not be returned as sendable (CodeRabbit #526).

    Regression guard for the single-vs-multiple match inconsistency: previously,
    ``len(matches) == 1`` bypassed the sendable filter, so a single PROCESSING
    agent would be returned while two PROCESSING agents correctly errored out.
    """
    agents = {
        "synapse-claude-8100": {
            "agent_id": "synapse-claude-8100",
            "agent_type": "claude",
            "port": 8100,
            "status": "PROCESSING",
        },
    }

    info, error = _resolve_target_agent("claude", agents)

    assert info is None
    assert error == "No agent found matching 'claude'"


def test_resolve_single_waiting_match_returns_no_agent_found():
    """A single WAITING match must also be filtered out."""
    agents = {
        "synapse-codex-8120": {
            "agent_id": "synapse-codex-8120",
            "agent_type": "codex",
            "port": 8120,
            "status": "WAITING",
        },
    }

    info, error = _resolve_target_agent("codex", agents)

    assert info is None
    assert error == "No agent found matching 'codex'"
