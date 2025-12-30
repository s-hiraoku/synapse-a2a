"""Tests for Agent Context module - x-synapse-context extension."""
import pytest
from synapse.agent_context import (
    AgentContext,
    AgentInfo,
    build_agent_card_context,
    build_bootstrap_message,
    get_other_agents_from_registry,
)


# ============================================================
# AgentInfo Model Tests
# ============================================================

class TestAgentInfo:
    """Test AgentInfo dataclass."""

    def test_agent_info_creation(self):
        """Should create AgentInfo with all fields."""
        info = AgentInfo(
            id="synapse-claude-8100",
            type="claude",
            endpoint="http://localhost:8100",
            status="IDLE"
        )
        assert info.id == "synapse-claude-8100"
        assert info.type == "claude"
        assert info.endpoint == "http://localhost:8100"
        assert info.status == "IDLE"

    def test_agent_info_default_status(self):
        """Should have default status 'unknown'."""
        info = AgentInfo(
            id="synapse-test-8000",
            type="test",
            endpoint="http://localhost:8000"
        )
        assert info.status == "unknown"


# ============================================================
# AgentContext Model Tests
# ============================================================

class TestAgentContext:
    """Test AgentContext dataclass."""

    def test_agent_context_creation(self):
        """Should create AgentContext with all fields."""
        ctx = AgentContext(
            agent_id="synapse-claude-8100",
            agent_type="claude",
            port=8100,
            other_agents=[]
        )
        assert ctx.agent_id == "synapse-claude-8100"
        assert ctx.agent_type == "claude"
        assert ctx.port == 8100
        assert ctx.other_agents == []

    def test_agent_context_with_other_agents(self):
        """Should accept list of other agents."""
        other = AgentInfo(
            id="synapse-gemini-8110",
            type="gemini",
            endpoint="http://localhost:8110"
        )
        ctx = AgentContext(
            agent_id="synapse-claude-8100",
            agent_type="claude",
            port=8100,
            other_agents=[other]
        )
        assert len(ctx.other_agents) == 1
        assert ctx.other_agents[0].id == "synapse-gemini-8110"

    def test_agent_context_default_other_agents(self):
        """Should have empty list as default for other_agents."""
        ctx = AgentContext(
            agent_id="synapse-test-8000",
            agent_type="test",
            port=8000
        )
        assert ctx.other_agents == []


# ============================================================
# build_agent_card_context Tests
# ============================================================

class TestBuildAgentCardContext:
    """Test build_agent_card_context function."""

    def test_returns_x_synapse_context(self):
        """Should return dict with x-synapse-context key."""
        ctx = AgentContext(
            agent_id="synapse-claude-8100",
            agent_type="claude",
            port=8100
        )
        result = build_agent_card_context(ctx)

        assert "x-synapse-context" in result

    def test_contains_identity(self):
        """Should contain identity field."""
        ctx = AgentContext(
            agent_id="synapse-claude-8100",
            agent_type="claude",
            port=8100
        )
        result = build_agent_card_context(ctx)

        assert result["x-synapse-context"]["identity"] == "synapse-claude-8100"

    def test_contains_agent_type(self):
        """Should contain agent_type field."""
        ctx = AgentContext(
            agent_id="synapse-gemini-8110",
            agent_type="gemini",
            port=8110
        )
        result = build_agent_card_context(ctx)

        assert result["x-synapse-context"]["agent_type"] == "gemini"

    def test_contains_port(self):
        """Should contain port field."""
        ctx = AgentContext(
            agent_id="synapse-claude-8100",
            agent_type="claude",
            port=8100
        )
        result = build_agent_card_context(ctx)

        assert result["x-synapse-context"]["port"] == 8100

    def test_contains_routing_rules(self):
        """Should contain routing_rules with required fields."""
        ctx = AgentContext(
            agent_id="synapse-claude-8100",
            agent_type="claude",
            port=8100
        )
        result = build_agent_card_context(ctx)
        rules = result["x-synapse-context"]["routing_rules"]

        assert "self_patterns" in rules
        assert "forward_command" in rules
        assert "instructions" in rules

    def test_self_patterns_include_agent_id_and_type(self):
        """self_patterns should include both agent_id and agent_type."""
        ctx = AgentContext(
            agent_id="synapse-claude-8100",
            agent_type="claude",
            port=8100
        )
        result = build_agent_card_context(ctx)
        patterns = result["x-synapse-context"]["routing_rules"]["self_patterns"]

        assert "@synapse-claude-8100" in patterns
        assert "@claude" in patterns

    def test_forward_command_contains_a2a_tool(self):
        """forward_command should contain the a2a.py tool path."""
        ctx = AgentContext(
            agent_id="synapse-claude-8100",
            agent_type="claude",
            port=8100
        )
        result = build_agent_card_context(ctx)
        cmd = result["x-synapse-context"]["routing_rules"]["forward_command"]

        assert "synapse/tools/a2a.py" in cmd
        assert "--target" in cmd
        assert "--priority" in cmd

    def test_contains_priority_levels(self):
        """Should contain priority_levels with 1 and 5."""
        ctx = AgentContext(
            agent_id="synapse-claude-8100",
            agent_type="claude",
            port=8100
        )
        result = build_agent_card_context(ctx)
        levels = result["x-synapse-context"]["priority_levels"]

        assert "1" in levels
        assert "5" in levels

    def test_contains_examples(self):
        """Should contain usage examples."""
        ctx = AgentContext(
            agent_id="synapse-claude-8100",
            agent_type="claude",
            port=8100
        )
        result = build_agent_card_context(ctx)
        examples = result["x-synapse-context"]["examples"]

        assert "send_message" in examples
        assert "emergency_interrupt" in examples
        assert "list_agents" in examples

    def test_available_agents_empty(self):
        """Should return empty list when no other agents."""
        ctx = AgentContext(
            agent_id="synapse-claude-8100",
            agent_type="claude",
            port=8100,
            other_agents=[]
        )
        result = build_agent_card_context(ctx)

        assert result["x-synapse-context"]["available_agents"] == []

    def test_available_agents_populated(self):
        """Should include other agents in available_agents."""
        other = AgentInfo(
            id="synapse-gemini-8110",
            type="gemini",
            endpoint="http://localhost:8110",
            status="IDLE"
        )
        ctx = AgentContext(
            agent_id="synapse-claude-8100",
            agent_type="claude",
            port=8100,
            other_agents=[other]
        )
        result = build_agent_card_context(ctx)
        agents = result["x-synapse-context"]["available_agents"]

        assert len(agents) == 1
        assert agents[0]["id"] == "synapse-gemini-8110"
        assert agents[0]["type"] == "gemini"
        assert agents[0]["endpoint"] == "http://localhost:8110"
        assert agents[0]["status"] == "IDLE"

    def test_multiple_other_agents(self):
        """Should include multiple other agents."""
        agents = [
            AgentInfo(id="synapse-gemini-8110", type="gemini", endpoint="http://localhost:8110"),
            AgentInfo(id="synapse-codex-8120", type="codex", endpoint="http://localhost:8120"),
        ]
        ctx = AgentContext(
            agent_id="synapse-claude-8100",
            agent_type="claude",
            port=8100,
            other_agents=agents
        )
        result = build_agent_card_context(ctx)

        assert len(result["x-synapse-context"]["available_agents"]) == 2


# ============================================================
# build_bootstrap_message Tests
# ============================================================

class TestBuildBootstrapMessage:
    """Test build_bootstrap_message function."""

    def test_contains_agent_id(self):
        """Should contain agent_id in message."""
        msg = build_bootstrap_message("synapse-claude-8100", 8100)

        assert "synapse-claude-8100" in msg

    def test_contains_port(self):
        """Should contain port in URL."""
        msg = build_bootstrap_message("synapse-claude-8100", 8100)

        assert "8100" in msg

    def test_contains_curl_command(self):
        """Should contain curl command."""
        msg = build_bootstrap_message("synapse-claude-8100", 8100)

        assert "curl" in msg

    def test_contains_agent_json_url(self):
        """Should contain .well-known/agent.json URL."""
        msg = build_bootstrap_message("synapse-claude-8100", 8100)

        assert ".well-known/agent.json" in msg

    def test_contains_x_synapse_context_reference(self):
        """Should reference x-synapse-context in extraction."""
        msg = build_bootstrap_message("synapse-claude-8100", 8100)

        assert "x-synapse-context" in msg

    def test_message_is_minimal(self):
        """Bootstrap message should be relatively short."""
        msg = build_bootstrap_message("synapse-claude-8100", 8100)

        # Should be under 500 characters (much shorter than old full instructions)
        assert len(msg) < 500

    def test_different_ports(self):
        """Should use different port in URL."""
        msg1 = build_bootstrap_message("synapse-claude-8100", 8100)
        msg2 = build_bootstrap_message("synapse-gemini-8110", 8110)

        assert "localhost:8100" in msg1
        assert "localhost:8110" in msg2


# ============================================================
# get_other_agents_from_registry Tests
# ============================================================

class TestGetOtherAgentsFromRegistry:
    """Test get_other_agents_from_registry function."""

    @pytest.fixture
    def mock_registry(self):
        """Create a mock registry."""
        from unittest.mock import MagicMock
        registry = MagicMock()
        return registry

    def test_excludes_self(self, mock_registry):
        """Should exclude self from the list."""
        mock_registry.get_live_agents.return_value = {
            "synapse-claude-8100": {
                "agent_id": "synapse-claude-8100",
                "agent_type": "claude",
                "endpoint": "http://localhost:8100",
                "status": "IDLE"
            },
            "synapse-gemini-8110": {
                "agent_id": "synapse-gemini-8110",
                "agent_type": "gemini",
                "endpoint": "http://localhost:8110",
                "status": "IDLE"
            }
        }

        result = get_other_agents_from_registry(mock_registry, "synapse-claude-8100")

        assert len(result) == 1
        assert result[0].id == "synapse-gemini-8110"

    def test_returns_empty_when_only_self(self, mock_registry):
        """Should return empty list when only self is registered."""
        mock_registry.get_live_agents.return_value = {
            "synapse-claude-8100": {
                "agent_id": "synapse-claude-8100",
                "agent_type": "claude",
                "endpoint": "http://localhost:8100",
                "status": "IDLE"
            }
        }

        result = get_other_agents_from_registry(mock_registry, "synapse-claude-8100")

        assert len(result) == 0

    def test_returns_empty_when_registry_empty(self, mock_registry):
        """Should return empty list when registry is empty."""
        mock_registry.get_live_agents.return_value = {}

        result = get_other_agents_from_registry(mock_registry, "synapse-claude-8100")

        assert len(result) == 0

    def test_returns_agent_info_objects(self, mock_registry):
        """Should return AgentInfo objects."""
        mock_registry.get_live_agents.return_value = {
            "synapse-gemini-8110": {
                "agent_id": "synapse-gemini-8110",
                "agent_type": "gemini",
                "endpoint": "http://localhost:8110",
                "status": "BUSY"
            }
        }

        result = get_other_agents_from_registry(mock_registry, "synapse-claude-8100")

        assert len(result) == 1
        assert isinstance(result[0], AgentInfo)
        assert result[0].id == "synapse-gemini-8110"
        assert result[0].type == "gemini"
        assert result[0].endpoint == "http://localhost:8110"
        assert result[0].status == "BUSY"

    def test_handles_missing_fields(self, mock_registry):
        """Should handle missing optional fields gracefully."""
        mock_registry.get_live_agents.return_value = {
            "synapse-gemini-8110": {
                "agent_id": "synapse-gemini-8110",
                # Missing agent_type, endpoint, status
            }
        }

        result = get_other_agents_from_registry(mock_registry, "synapse-claude-8100")

        assert len(result) == 1
        assert result[0].id == "synapse-gemini-8110"
        assert result[0].type == "unknown"  # Default
        assert result[0].endpoint == ""
        assert result[0].status == "unknown"
