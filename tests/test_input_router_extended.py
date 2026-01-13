"""Extended tests for InputRouter - Refactoring Specification."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from synapse.a2a_client import A2ATask
from synapse.input_router import InputRouter


class TestInputRouterRefactorSpec:
    """Specification tests for InputRouter refactoring."""

    @pytest.fixture
    def router(self):
        mock_registry = MagicMock()
        mock_client = MagicMock()
        return InputRouter(
            registry=mock_registry,
            a2a_client=mock_client,
            self_agent_id="sender-1",
            self_agent_type="claude",
            self_port=8100,
        )

    # =========================================================================
    # 1. @AGENTS.md Pattern Parsing (parse_at_mention)
    # =========================================================================

    def test_parse_at_mention_basic(self, router):
        """Spec: parse_at_mention should extract agent name and message."""
        line = "@claude hello world"
        result = router.parse_at_mention(line)

        assert result is not None
        agent, message = result
        assert agent == "claude"
        assert message == "hello world"

    def test_parse_at_mention_quoted(self, router):
        """Spec: parse_at_mention should strip quotes from message."""
        line = '@claude "run tests"'
        result = router.parse_at_mention(line)

        assert result is not None
        _, message = result
        assert message == "run tests"

    def test_parse_at_mention_with_hyphen(self, router):
        """Spec: parse_at_mention should handle agent names with hyphens."""
        line = "@claude-8100 check status"
        result = router.parse_at_mention(line)

        assert result is not None
        agent, message = result
        assert agent == "claude-8100"
        assert message == "check status"

    # =========================================================================
    # 2. Routing Logic (route_to_agent)
    # =========================================================================

    def test_route_to_agent_local(self, router):
        """Spec: route_to_agent should delegate to local agents via A2A protocol."""
        # route_to_agent is the intended replacement/alias for send_to_agent
        router.registry.list_agents.return_value = {
            "synapse-claude-8100": {
                "agent_id": "synapse-claude-8100",
                "agent_type": "claude",
                "port": 8100,
                "endpoint": "http://localhost:8100",
                "pid": 123,
            }
        }
        router.a2a_client.send_to_local.return_value = A2ATask(
            id="t1", status="working"
        )

        with (
            patch("synapse.input_router.is_process_running", return_value=True),
            patch("synapse.input_router.is_port_open", return_value=True),
        ):
            success = router.route_to_agent("claude", "hello")
            assert success is True
            router.a2a_client.send_to_local.assert_called_once()

    def test_route_to_agent_external(self, router):
        """Spec: route_to_agent should handle external agents."""
        mock_ext = MagicMock()
        mock_ext.alias = "ext-agent"
        router.a2a_client.registry.get.return_value = mock_ext
        router.a2a_client.send_message.return_value = A2ATask(id="et1", status="done")
        router.registry.list_agents.return_value = {}

        success = router.route_to_agent("ext-agent", "hello")
        assert success is True
        assert router.is_external_agent is True

    def test_route_to_agent_skips_tcp_preflight_when_uds_present(self, router):
        """Spec: UDS targets should skip TCP preflight checks."""
        router.registry.list_agents.return_value = {
            "synapse-claude-8100": {
                "agent_id": "synapse-claude-8100",
                "agent_type": "claude",
                "port": 8100,
                "endpoint": "http://localhost:8100",
                "pid": 123,
                "uds_path": "/tmp/agent.sock",
            }
        }
        router.a2a_client.send_to_local.return_value = A2ATask(
            id="t1", status="working"
        )

        with (
            patch("synapse.input_router.is_process_running", return_value=True),
            patch("synapse.input_router.is_port_open") as mock_port_open,
            patch.object(Path, "exists", return_value=True),
        ):
            success = router.route_to_agent("claude", "hello")
            assert success is True
            # TCP preflight skipped when UDS path exists (even though local_only=False)
            mock_port_open.assert_not_called()
            call_kwargs = router.a2a_client.send_to_local.call_args.kwargs
            assert call_kwargs.get("uds_path") == "/tmp/agent.sock"
            # local_only=False to allow HTTP fallback if UDS fails
            assert call_kwargs.get("local_only") is False

    # =========================================================================
    # 3. Error Handling
    # =========================================================================

    def test_error_handling_dead_process(self, router):
        """Spec: Should detect dead processes and unregister them."""
        router.registry.list_agents.return_value = {
            "dead-agent": {
                "agent_id": "dead-agent",
                "pid": 999,
                "endpoint": "http://..",
            }
        }

        with patch("synapse.input_router.is_process_running", return_value=False):
            success = router.route_to_agent("dead-agent", "msg")
            assert success is False
            router.registry.unregister.assert_called_with("dead-agent")

    def test_route_to_agent_single_type_match(self, router):
        """Spec: Should match by agent_type if only one exists (Lines 264-265)."""
        router.registry.list_agents.return_value = {
            "synapse-claude-8100": {
                "agent_id": "synapse-claude-8100",
                "agent_type": "claude",
                "port": 8100,
                "endpoint": "http://localhost:8100",
                "pid": 123,
            }
        }
        router.a2a_client.send_to_local.return_value = A2ATask(id="t1", status="done")

        with (
            patch("synapse.input_router.is_process_running", return_value=True),
            patch("synapse.input_router.is_port_open", return_value=True),
        ):
            success = router.route_to_agent("claude", "msg")
            assert success is True

    def test_error_handling_ambiguous(self, router):
        """Spec: Should return options when multiple agents match type."""
        router.registry.list_agents.return_value = {
            "c1": {"agent_type": "claude", "port": 8100},
            "c2": {"agent_type": "claude", "port": 8101},
        }

        success = router.route_to_agent("claude", "msg")
        assert success is False
        assert len(router.ambiguous_matches) == 2

    # =========================================================================
    # 4. Coverage for missing lines
    # =========================================================================

    def test_process_char_escape_middle(self, router):
        """Covers middle of escape sequence (Lines 112-114)."""
        router.process_char("\x1b")
        output, action = router.process_char("[")
        assert output == "["
        assert router.in_escape_sequence is True

        # Termination of escape sequence
        output, action = router.process_char("A")
        assert output == "A"
        assert router.in_escape_sequence is False

    def test_process_input(self, router):
        """Covers process_input method (Lines 154-157)."""
        results = router.process_input("@claude hi\n")
        assert len(results) == 11
        assert results[-1][1] is not None  # Action callback

    def test_route_to_agent_type_port_shorthand(self, router):
        """Covers type-port shorthand resolution (Lines 258-266)."""
        router.registry.list_agents.return_value = {
            "s1": {"agent_type": "codex", "port": 8120, "endpoint": "http://.."}
        }
        router.a2a_client.send_to_local.return_value = A2ATask(id="t", status="done")

        with (
            patch("synapse.input_router.is_process_running", return_value=True),
            patch("synapse.input_router.is_port_open", return_value=True),
        ):
            success = router.route_to_agent("codex-8120", "msg")
            assert success is True

    def test_route_to_agent_task_creation_failure(self, router):
        """Covers task creation failure (Lines 302-304)."""
        router.registry.list_agents.return_value = {
            "target": {"agent_id": "target", "port": 8100, "endpoint": "http://target"}
        }
        router.a2a_client.send_to_local.return_value = None

        with (
            patch("synapse.input_router.is_process_running", return_value=True),
            patch("synapse.input_router.is_port_open", return_value=True),
        ):
            success = router.route_to_agent("target", "msg")
            assert success is False

    def test_route_to_agent_request_exception(self, router):
        """Covers request exception (Lines 306-309)."""
        router.registry.list_agents.return_value = {
            "target": {"agent_id": "target", "port": 8100, "endpoint": "http://target"}
        }
        router.a2a_client.send_to_local.side_effect = Exception("Network error")

        with (
            patch("synapse.input_router.is_process_running", return_value=True),
            patch("synapse.input_router.is_port_open", return_value=True),
        ):
            success = router.route_to_agent("target", "msg")
            assert success is False

    def test_route_to_agent_external_registry(self, router):
        """Covers external agent registry check (Lines 304-311)."""
        router.registry.list_agents.return_value = {}
        mock_ext = MagicMock()
        mock_ext.alias = "remote"
        mock_ext.url = "http://remote"
        router.a2a_client.registry.get.return_value = mock_ext
        router.a2a_client.send_message.return_value = A2ATask(id="et", status="done")

        success = router.route_to_agent("remote", "msg")
        assert success is True
        assert router.is_external_agent is True

    def test_route_to_agent_success_full(self, router):
        """Covers successful A2A send path with response."""
        router.registry.list_agents.return_value = {
            "target": {"agent_id": "target", "port": 8100, "endpoint": "http://target"}
        }
        task = A2ATask(
            id="t1",
            status="completed",
            artifacts=[{"type": "text", "data": "response"}],
        )
        router.a2a_client.send_to_local.return_value = task

        with (
            patch("synapse.input_router.is_process_running", return_value=True),
            patch("synapse.input_router.is_port_open", return_value=True),
            patch("synapse.input_router.get_settings") as mock_settings,
        ):
            mock_settings.return_value.get_a2a_flow.return_value = "roundtrip"
            success = router.route_to_agent("target", "msg")
            assert success is True
            assert router.last_response == "response"

    def test_send_to_external_agent_task_failure(self, router):
        """Covers external task failure (Lines 342-344)."""
        mock_agent = MagicMock()
        mock_agent.alias = "ext"
        router.a2a_client.send_message.return_value = None

        success = router._send_to_external_agent(mock_agent, "msg")
        assert success is False

    def test_send_to_external_agent_exception(self, router):
        """Covers external task exception (Lines 346-349)."""
        mock_agent = MagicMock()
        mock_agent.alias = "ext"
        router.a2a_client.send_message.side_effect = Exception("error")

        success = router._send_to_external_agent(mock_agent, "msg")
        assert success is False
