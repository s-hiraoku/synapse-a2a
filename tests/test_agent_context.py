"""Tests for Agent Context module - initial instructions generation."""
import pytest
from synapse.agent_context import (
    AgentContext,
    AgentInfo,
    build_initial_instructions,
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
# build_initial_instructions Tests
# ============================================================

class TestBuildInitialInstructions:
    """Test build_initial_instructions function."""

    def test_returns_string(self):
        """Should return a string."""
        ctx = AgentContext(
            agent_id="synapse-claude-8100",
            agent_type="claude",
            port=8100
        )
        result = build_initial_instructions(ctx)
        assert isinstance(result, str)

    def test_contains_identity(self):
        """Should contain agent identity information."""
        ctx = AgentContext(
            agent_id="synapse-claude-8100",
            agent_type="claude",
            port=8100
        )
        result = build_initial_instructions(ctx)

        assert "synapse-claude-8100" in result
        assert "claude" in result
        assert "8100" in result

    def test_contains_a2a_tool_command(self):
        """Should contain the a2a.py tool command."""
        ctx = AgentContext(
            agent_id="synapse-claude-8100",
            agent_type="claude",
            port=8100
        )
        result = build_initial_instructions(ctx)

        assert "synapse/tools/a2a.py" in result
        assert "--target" in result
        assert "--priority" in result

    def test_contains_sender_identification(self):
        """Should contain sender identification and reply instructions."""
        ctx = AgentContext(
            agent_id="synapse-claude-8100",
            agent_type="claude",
            port=8100
        )
        result = build_initial_instructions(ctx)

        assert "A2A:" in result
        assert "sender_id" in result
        assert "How to Reply" in result
        assert "IMPORTANT" in result

    def test_contains_target_resolution(self):
        """Should explain target resolution patterns."""
        ctx = AgentContext(
            agent_id="synapse-claude-8100",
            agent_type="claude",
            port=8100
        )
        result = build_initial_instructions(ctx)

        assert "@type" in result
        assert "@type-port" in result

    def test_no_other_agents(self):
        """Should show 'no other agents' message when alone."""
        ctx = AgentContext(
            agent_id="synapse-claude-8100",
            agent_type="claude",
            port=8100,
            other_agents=[]
        )
        result = build_initial_instructions(ctx)

        assert "No other agents" in result

    def test_with_other_agents(self):
        """Should list other agents when available."""
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
        result = build_initial_instructions(ctx)

        assert "synapse-gemini-8110" in result
        assert "gemini" in result

    def test_multiple_other_agents(self):
        """Should list all other agents."""
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
        result = build_initial_instructions(ctx)

        assert "synapse-gemini-8110" in result
        assert "synapse-codex-8120" in result


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
        """Should contain port in message."""
        msg = build_bootstrap_message("synapse-claude-8100", 8100)

        assert "8100" in msg

    def test_message_is_minimal(self):
        """Bootstrap message should be short with essential commands only."""
        msg = build_bootstrap_message("synapse-claude-8100", 8100)

        # Should be minimal (identity + routing + reply + list, ~500 chars)
        assert len(msg) < 550
        # Should contain essential commands
        assert "a2a.py send" in msg
        assert "a2a.py list" in msg
        # Should contain routing and reply instructions
        assert "ROUTING" in msg
        assert "REPLY" in msg
        # Should have clear "do not process" marker
        assert "DO NOT PROCESS" in msg

    def test_different_ports(self):
        """Should use different port in message."""
        msg1 = build_bootstrap_message("synapse-claude-8100", 8100)
        msg2 = build_bootstrap_message("synapse-gemini-8110", 8110)

        assert "8100" in msg1
        assert "8110" in msg2


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
