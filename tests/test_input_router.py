"""Tests for InputRouter - @Agent pattern detection and A2A routing."""
import pytest
from unittest.mock import MagicMock, patch
from synapse.input_router import InputRouter
from synapse.a2a_client import A2ATask


# ============================================================
# Pattern Detection Tests
# ============================================================

class TestPatternDetection:
    """Test @Agent pattern detection."""

    @pytest.fixture
    def router(self):
        """Create InputRouter with mock registry."""
        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = {}
        mock_client = MagicMock()
        mock_client.registry.get.return_value = None
        return InputRouter(registry=mock_registry, a2a_client=mock_client)

    def test_detect_agent_pattern(self, router):
        """Should detect @Agent pattern."""
        # Type "@claude hello"
        for char in "@claude hello":
            router.process_char(char)

        output, action = router.process_char('\n')

        assert action is not None  # Should have send action
        assert output == ""  # Should suppress output

    def test_detect_agent_with_response_flag(self, router):
        """Should detect --response flag."""
        for char in "@claude --response what is 2+2":
            router.process_char(char)

        output, action = router.process_char('\n')
        assert action is not None

    def test_normal_input_passes_through(self, router):
        """Normal input should pass through."""
        output, action = router.process_char('a')
        assert output == 'a'
        assert action is None

    def test_escape_sequence_handling(self, router):
        """Escape sequences should be handled."""
        output, action = router.process_char('\x1b')
        assert action is None

    def test_control_char_clears_buffer(self, router):
        """Control chars should clear buffer."""
        for char in "@claude":
            router.process_char(char)

        router.process_char('\x03')  # Ctrl+C
        assert router.line_buffer == ""

    def test_backspace_edits_buffer(self, router):
        """Backspace should edit buffer."""
        for char in "@claude":
            router.process_char(char)

        router.process_char('\x7f')  # Backspace
        assert router.line_buffer == "@claud"


# ============================================================
# Agent Resolution Tests
# ============================================================

class TestAgentResolution:
    """Test agent resolution (local vs external)."""

    @pytest.fixture
    def mock_registry(self):
        """Create mock registry with local agents."""
        registry = MagicMock()
        registry.list_agents.return_value = {
            "agent-123": {
                "agent_id": "agent-123",
                "agent_type": "claude",
                "endpoint": "http://localhost:8001"
            }
        }
        return registry

    @pytest.fixture
    def mock_a2a_client(self):
        """Create mock A2A client."""
        client = MagicMock()
        client.registry.get.return_value = None
        client.send_to_local.return_value = A2ATask(
            id="task-1",
            status="working",
            artifacts=[]
        )
        return client

    def test_send_to_local_agent(self, mock_registry, mock_a2a_client):
        """Should send to local agent using A2A protocol."""
        router = InputRouter(registry=mock_registry, a2a_client=mock_a2a_client)

        result = router.send_to_agent("claude", "hello")

        assert result is True
        mock_a2a_client.send_to_local.assert_called_once()
        # Verify A2A protocol is used
        call_args = mock_a2a_client.send_to_local.call_args
        assert call_args.kwargs["endpoint"] == "http://localhost:8001"
        assert call_args.kwargs["message"] == "hello"
        assert call_args.kwargs["priority"] == 1

    def test_send_to_external_agent(self, mock_registry, mock_a2a_client):
        """Should send to external agent via A2AClient."""
        from synapse.a2a_client import ExternalAgent

        external = ExternalAgent(name="Remote", url="http://remote.com", alias="remote")
        mock_a2a_client.registry.get.return_value = external
        mock_a2a_client.send_message.return_value = A2ATask(
            id="ext-task",
            status="submitted",
            artifacts=[]
        )

        mock_registry.list_agents.return_value = {}  # No local agents
        router = InputRouter(registry=mock_registry, a2a_client=mock_a2a_client)

        result = router.send_to_agent("remote", "hello external")

        assert result is True
        assert router.is_external_agent is True
        mock_a2a_client.send_message.assert_called_once()

    def test_agent_not_found(self, mock_registry, mock_a2a_client):
        """Should return False when agent not found."""
        mock_registry.list_agents.return_value = {}
        mock_a2a_client.registry.get.return_value = None

        router = InputRouter(registry=mock_registry, a2a_client=mock_a2a_client)
        result = router.send_to_agent("nonexistent", "hello")

        assert result is False


# ============================================================
# Response Handling Tests
# ============================================================

class TestResponseHandling:
    """Test response handling from agents."""

    @pytest.fixture
    def mock_registry(self):
        registry = MagicMock()
        registry.list_agents.return_value = {
            "agent-1": {
                "agent_type": "claude",
                "endpoint": "http://localhost:8001"
            }
        }
        return registry

    def test_extract_text_from_artifacts(self, mock_registry):
        """Should extract text from artifacts."""
        mock_client = MagicMock()
        mock_client.registry.get.return_value = None
        mock_client.send_to_local.return_value = A2ATask(
            id="task-1",
            status="completed",
            artifacts=[
                {"type": "text", "data": "First response"},
                {"type": "text", "data": "Second response"}
            ]
        )

        router = InputRouter(registry=mock_registry, a2a_client=mock_client)

        # Send with want_response=True
        result = router.send_to_agent("claude", "hello", want_response=True)

        assert result is True
        assert router.last_response == "First response\nSecond response"

    def test_no_artifacts_returns_none(self, mock_registry):
        """Should return None when no artifacts."""
        mock_client = MagicMock()
        mock_client.registry.get.return_value = None
        mock_client.send_to_local.return_value = A2ATask(
            id="task-1",
            status="working",
            artifacts=[]
        )

        router = InputRouter(registry=mock_registry, a2a_client=mock_client)
        router.send_to_agent("claude", "hello", want_response=True)

        assert router.last_response is None


# ============================================================
# Feedback Message Tests
# ============================================================

class TestFeedbackMessages:
    """Test feedback message generation."""

    @pytest.fixture
    def router(self):
        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = {}
        mock_client = MagicMock()
        mock_client.registry.get.return_value = None
        return InputRouter(registry=mock_registry, a2a_client=mock_client)

    def test_local_success_feedback(self, router):
        """Should generate green feedback for local agent."""
        router.is_external_agent = False
        msg = router.get_feedback_message("claude", True)

        assert "claude" in msg
        assert "local" in msg
        assert "\x1b[32m" in msg  # Green color

    def test_external_success_feedback(self, router):
        """Should generate magenta feedback for external agent."""
        router.is_external_agent = True
        msg = router.get_feedback_message("remote", True)

        assert "remote" in msg
        assert "ext" in msg
        assert "\x1b[35m" in msg  # Magenta color

    def test_failure_feedback(self, router):
        """Should generate red feedback for failure."""
        msg = router.get_feedback_message("unknown", False)

        assert "not found" in msg
        assert "\x1b[31m" in msg  # Red color

    def test_feedback_with_response(self, router):
        """Should include response in feedback."""
        router.is_external_agent = False
        router.last_response = "This is the response"
        msg = router.get_feedback_message("claude", True)

        assert "This is the response" in msg


# ============================================================
# Integration Tests
# ============================================================

class TestInputRouterIntegration:
    """Integration tests for InputRouter."""

    def test_full_agent_command_flow(self):
        """Test complete flow: input -> detect -> send."""
        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = {
            "agent-1": {
                "agent_type": "gemini",
                "endpoint": "http://localhost:8002"
            }
        }

        mock_client = MagicMock()
        mock_client.registry.get.return_value = None
        mock_client.send_to_local.return_value = A2ATask(
            id="task-123",
            status="working",
            artifacts=[]
        )

        router = InputRouter(registry=mock_registry, a2a_client=mock_client)

        # Simulate typing "@gemini help me"
        for char in "@gemini help me":
            output, action = router.process_char(char)
            if char != '@':  # @ starts the pattern
                assert action is None

        # Press Enter
        output, action = router.process_char('\n')

        # Should have an action
        assert action is not None

        # Execute the action
        result = action()
        assert result is True

        # Verify A2A client was called with correct params
        mock_client.send_to_local.assert_called_once()
        call_args = mock_client.send_to_local.call_args
        assert call_args.kwargs["message"] == "help me"
        assert call_args.kwargs["endpoint"] == "http://localhost:8002"

    def test_reset_clears_state(self):
        """Test reset clears all state."""
        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = {}
        mock_client = MagicMock()
        mock_client.registry.get.return_value = None

        router = InputRouter(registry=mock_registry, a2a_client=mock_client)

        # Add some state
        router.line_buffer = "test"
        router.is_external_agent = True

        router.reset()

        assert router.line_buffer == ""
        assert router.is_external_agent is False

    def test_synapse_agent_id_format(self):
        """Test routing with synapse-{type}-{port} agent ID format."""
        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = {
            "synapse-gemini-8102": {
                "agent_id": "synapse-gemini-8102",
                "agent_type": "gemini",
                "endpoint": "http://localhost:8102"
            }
        }

        mock_client = MagicMock()
        mock_client.registry.get.return_value = None
        mock_client.send_to_local.return_value = A2ATask(
            id="task-456",
            status="working",
            artifacts=[]
        )

        router = InputRouter(registry=mock_registry, a2a_client=mock_client)

        # Simulate typing "@synapse-gemini-8102 test message"
        for char in "@synapse-gemini-8102 test message":
            output, action = router.process_char(char)

        # Press Enter
        output, action = router.process_char('\n')

        # Should have an action
        assert action is not None

        # Execute the action
        result = action()
        assert result is True

        # Verify A2A client was called with correct params
        mock_client.send_to_local.assert_called_once()
        call_args = mock_client.send_to_local.call_args
        assert call_args.kwargs["message"] == "test message"
        assert call_args.kwargs["endpoint"] == "http://localhost:8102"

    def test_synapse_agent_id_with_short_message(self):
        """Test routing with synapse ID format and short message like 'test'."""
        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = {
            "synapse-gemini-8102": {
                "agent_id": "synapse-gemini-8102",
                "agent_type": "gemini",
                "endpoint": "http://localhost:8102"
            }
        }

        mock_client = MagicMock()
        mock_client.registry.get.return_value = None
        mock_client.send_to_local.return_value = A2ATask(
            id="task-789",
            status="working",
            artifacts=[]
        )

        router = InputRouter(registry=mock_registry, a2a_client=mock_client)

        # Simulate typing "@synapse-gemini-8102 test"
        for char in "@synapse-gemini-8102 test":
            router.process_char(char)

        # Press Enter
        output, action = router.process_char('\n')

        assert action is not None
        result = action()
        assert result is True

        # Verify the message "test" was extracted correctly
        call_args = mock_client.send_to_local.call_args
        assert call_args.kwargs["message"] == "test"

    def test_normal_input_passes_through(self):
        """Normal input should pass through to PTY."""
        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = {}
        mock_client = MagicMock()
        mock_client.registry.get.return_value = None

        router = InputRouter(registry=mock_registry, a2a_client=mock_client)

        # Type "hello" - each character should pass through
        outputs = []
        for char in "hello":
            output, action = router.process_char(char)
            outputs.append(output)
            assert action is None

        # All characters should be returned (for sending to PTY)
        assert outputs == ["h", "e", "l", "l", "o"]

        # Enter should also pass through
        output, action = router.process_char('\n')
        assert output == '\n'
        assert action is None

    def test_at_prefixed_input_also_passes_through(self):
        """Input starting with @ passes through until Enter detects pattern."""
        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = {}
        mock_client = MagicMock()
        mock_client.registry.get.return_value = None

        router = InputRouter(registry=mock_registry, a2a_client=mock_client)

        # Type "@test" - characters pass through (echoed by PTY)
        outputs = []
        for char in "@test":
            output, action = router.process_char(char)
            outputs.append(output)
            assert action is None

        # All characters should pass through
        assert outputs == ["@", "t", "e", "s", "t"]

    def test_backspace_passes_through(self):
        """Backspace should pass through to PTY."""
        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = {}
        mock_client = MagicMock()
        mock_client.registry.get.return_value = None

        router = InputRouter(registry=mock_registry, a2a_client=mock_client)

        # Type "@hel"
        for char in "@hel":
            router.process_char(char)

        # Press backspace - should pass through
        output, action = router.process_char('\x7f')
        assert output == '\x7f'  # Passes through to PTY
        assert router.line_buffer == "@he"  # Buffer updated


# ============================================================
# Multiple Agent Resolution Tests
# ============================================================

class TestMultipleAgentResolution:
    """Test agent resolution when multiple agents of same type exist."""

    def test_single_agent_by_type(self):
        """Single agent of type should match with @type."""
        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = {
            "synapse-codex-8120": {
                "agent_id": "synapse-codex-8120",
                "agent_type": "codex",
                "port": 8120,
                "endpoint": "http://localhost:8120"
            }
        }

        mock_client = MagicMock()
        mock_client.registry.get.return_value = None
        mock_client.send_to_local.return_value = A2ATask(
            id="task-1", status="working", artifacts=[]
        )

        router = InputRouter(registry=mock_registry, a2a_client=mock_client)

        # @codex should work when only one codex exists
        for char in "@codex hello":
            router.process_char(char)
        output, action = router.process_char('\n')

        assert action is not None
        result = action()
        assert result is True

    def test_multiple_agents_by_type_fails(self):
        """Multiple agents of same type should fail with @type."""
        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = {
            "synapse-codex-8120": {
                "agent_id": "synapse-codex-8120",
                "agent_type": "codex",
                "port": 8120,
                "endpoint": "http://localhost:8120"
            },
            "synapse-codex-8130": {
                "agent_id": "synapse-codex-8130",
                "agent_type": "codex",
                "port": 8130,
                "endpoint": "http://localhost:8130"
            }
        }

        mock_client = MagicMock()
        mock_client.registry.get.return_value = None

        router = InputRouter(registry=mock_registry, a2a_client=mock_client)

        # @codex should fail when multiple codex agents exist
        for char in "@codex hello":
            router.process_char(char)
        output, action = router.process_char('\n')

        assert action is not None
        result = action()
        assert result is False
        assert router.ambiguous_matches is not None
        assert "@codex-8120" in router.ambiguous_matches or "@codex-8130" in router.ambiguous_matches

    def test_type_port_shorthand_resolves(self):
        """@type-port shorthand should resolve specific agent."""
        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = {
            "synapse-codex-8120": {
                "agent_id": "synapse-codex-8120",
                "agent_type": "codex",
                "port": 8120,
                "endpoint": "http://localhost:8120"
            },
            "synapse-codex-8130": {
                "agent_id": "synapse-codex-8130",
                "agent_type": "codex",
                "port": 8130,
                "endpoint": "http://localhost:8130"
            }
        }

        mock_client = MagicMock()
        mock_client.registry.get.return_value = None
        mock_client.send_to_local.return_value = A2ATask(
            id="task-1", status="working", artifacts=[]
        )

        router = InputRouter(registry=mock_registry, a2a_client=mock_client)

        # @codex-8120 should work
        for char in "@codex-8120 hello":
            router.process_char(char)
        output, action = router.process_char('\n')

        assert action is not None
        result = action()
        assert result is True

        # Verify correct endpoint was called
        call_args = mock_client.send_to_local.call_args
        assert call_args.kwargs["endpoint"] == "http://localhost:8120"

    def test_ambiguous_feedback_message(self):
        """Ambiguous matches should show options in feedback."""
        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = {}
        mock_client = MagicMock()
        mock_client.registry.get.return_value = None

        router = InputRouter(registry=mock_registry, a2a_client=mock_client)
        router.ambiguous_matches = ["@codex-8120", "@codex-8130"]

        msg = router.get_feedback_message("codex", False)

        assert "Multiple" in msg
        assert "@codex-8120" in msg
        assert "@codex-8130" in msg
        assert "\x1b[33m" in msg  # Yellow/warning color
