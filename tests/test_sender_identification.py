"""Tests for A2A sender identification feature."""
import os
import pytest
from unittest.mock import MagicMock, patch


# ============================================================
# CLI Tool: build_sender_info Tests
# ============================================================

class TestBuildSenderInfo:
    """Test build_sender_info function in a2a.py CLI tool."""

    def test_auto_detect_from_env_vars(self):
        """Should auto-detect sender info from environment variables."""
        from synapse.tools.a2a import build_sender_info

        with patch.dict(os.environ, {
            "SYNAPSE_AGENT_ID": "synapse-claude-8100",
            "SYNAPSE_AGENT_TYPE": "claude",
            "SYNAPSE_PORT": "8100"
        }):
            sender = build_sender_info()

            assert sender["sender_id"] == "synapse-claude-8100"
            assert sender["sender_type"] == "claude"
            assert sender["sender_endpoint"] == "http://localhost:8100"

    def test_explicit_sender_overrides_env(self):
        """--from flag should override env-detected sender_id."""
        from synapse.tools.a2a import build_sender_info

        with patch.dict(os.environ, {
            "SYNAPSE_AGENT_ID": "synapse-claude-8100",
            "SYNAPSE_AGENT_TYPE": "claude",
            "SYNAPSE_PORT": "8100"
        }):
            sender = build_sender_info(explicit_sender="external-agent")

            assert sender["sender_id"] == "external-agent"
            # Other fields still from env
            assert sender["sender_type"] == "claude"
            assert sender["sender_endpoint"] == "http://localhost:8100"

    def test_empty_when_no_env_vars(self):
        """Should return empty dict when no env vars are set."""
        from synapse.tools.a2a import build_sender_info

        with patch.dict(os.environ, {}, clear=True):
            # Remove any existing SYNAPSE_ vars
            env = {k: v for k, v in os.environ.items() if not k.startswith("SYNAPSE_")}
            with patch.dict(os.environ, env, clear=True):
                sender = build_sender_info()
                assert sender == {}

    def test_explicit_sender_without_env(self):
        """--from flag works even without env vars."""
        from synapse.tools.a2a import build_sender_info

        with patch.dict(os.environ, {}, clear=True):
            env = {k: v for k, v in os.environ.items() if not k.startswith("SYNAPSE_")}
            with patch.dict(os.environ, env, clear=True):
                sender = build_sender_info(explicit_sender="manual-sender")
                assert sender == {"sender_id": "manual-sender"}

    def test_partial_env_vars(self):
        """Should handle partial env var availability."""
        from synapse.tools.a2a import build_sender_info

        with patch.dict(os.environ, {
            "SYNAPSE_AGENT_ID": "synapse-gemini-8110",
            # Missing SYNAPSE_AGENT_TYPE and SYNAPSE_PORT
        }, clear=False):
            # First clear any existing SYNAPSE_ vars
            for key in list(os.environ.keys()):
                if key.startswith("SYNAPSE_") and key != "SYNAPSE_AGENT_ID":
                    del os.environ[key]

            sender = build_sender_info()

            assert sender["sender_id"] == "synapse-gemini-8110"
            assert "sender_type" not in sender
            assert "sender_endpoint" not in sender


# ============================================================
# InputRouter: Sender Info Tests
# ============================================================

class TestInputRouterSenderInfo:
    """Test InputRouter sender_info functionality."""

    def test_constructor_accepts_self_identity(self):
        """InputRouter should accept self-identity parameters."""
        from synapse.input_router import InputRouter

        router = InputRouter(
            self_agent_id="synapse-claude-8100",
            self_agent_type="claude",
            self_port=8100
        )

        assert router.self_agent_id == "synapse-claude-8100"
        assert router.self_agent_type == "claude"
        assert router.self_port == 8100

    def test_constructor_defaults_to_none(self):
        """Self-identity should default to None."""
        from synapse.input_router import InputRouter

        router = InputRouter()

        assert router.self_agent_id is None
        assert router.self_agent_type is None
        assert router.self_port is None

    def test_send_to_agent_includes_sender_info(self):
        """send_to_agent should include sender_info when self-identity is set."""
        from synapse.input_router import InputRouter
        from unittest.mock import MagicMock

        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = {
            "synapse-gemini-8110": {
                "agent_id": "synapse-gemini-8110",
                "agent_type": "gemini",
                "endpoint": "http://localhost:8110",
                "pid": 12345,
                "port": 8110
            }
        }

        mock_client = MagicMock()
        mock_client.send_to_local.return_value = MagicMock(
            id="task-123",
            status="working",
            artifacts=[]
        )

        router = InputRouter(
            registry=mock_registry,
            a2a_client=mock_client,
            self_agent_id="synapse-claude-8100",
            self_agent_type="claude",
            self_port=8100
        )

        # Mock process and port checks
        with patch('synapse.input_router.is_process_running', return_value=True):
            with patch('synapse.input_router.is_port_open', return_value=True):
                result = router.send_to_agent("gemini", "Hello from Claude!")

        # Verify sender_info was passed
        mock_client.send_to_local.assert_called_once()
        call_kwargs = mock_client.send_to_local.call_args.kwargs
        assert "sender_info" in call_kwargs
        assert call_kwargs["sender_info"]["sender_id"] == "synapse-claude-8100"
        assert call_kwargs["sender_info"]["sender_type"] == "claude"
        assert call_kwargs["sender_info"]["sender_endpoint"] == "http://localhost:8100"

    def test_send_to_agent_no_sender_info_without_self_identity(self):
        """send_to_agent should not include sender_info when self-identity is not set."""
        from synapse.input_router import InputRouter
        from unittest.mock import MagicMock

        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = {
            "synapse-gemini-8110": {
                "agent_id": "synapse-gemini-8110",
                "agent_type": "gemini",
                "endpoint": "http://localhost:8110",
                "pid": 12345,
                "port": 8110
            }
        }

        mock_client = MagicMock()
        mock_client.send_to_local.return_value = MagicMock(
            id="task-123",
            status="working",
            artifacts=[]
        )

        # No self-identity set
        router = InputRouter(
            registry=mock_registry,
            a2a_client=mock_client
        )

        with patch('synapse.input_router.is_process_running', return_value=True):
            with patch('synapse.input_router.is_port_open', return_value=True):
                result = router.send_to_agent("gemini", "Hello!")

        # Verify sender_info is None
        call_kwargs = mock_client.send_to_local.call_args.kwargs
        assert call_kwargs.get("sender_info") is None


# ============================================================
# A2A Client: sender_info Parameter Tests
# ============================================================

class TestA2AClientSenderInfo:
    """Test A2AClient.send_to_local sender_info handling."""

    def test_send_to_local_includes_sender_in_payload(self):
        """send_to_local should include sender info in request payload."""
        from synapse.a2a_client import A2AClient
        import requests

        with patch.object(requests, 'post') as mock_post:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "task": {
                    "id": "task-123",
                    "status": "working"
                }
            }
            mock_response.raise_for_status = MagicMock()
            mock_post.return_value = mock_response

            client = A2AClient()
            sender_info = {
                "sender_id": "synapse-claude-8100",
                "sender_type": "claude",
                "sender_endpoint": "http://localhost:8100"
            }

            client.send_to_local(
                endpoint="http://localhost:8110",
                message="Hello!",
                sender_info=sender_info
            )

            # Verify the request payload contains sender metadata
            call_args = mock_post.call_args
            payload = call_args.kwargs.get("json") or call_args[1].get("json")

            assert "metadata" in payload
            assert "sender" in payload["metadata"]
            assert payload["metadata"]["sender"]["sender_id"] == "synapse-claude-8100"

    def test_send_to_local_no_metadata_without_sender(self):
        """send_to_local should not include metadata when sender_info is None."""
        from synapse.a2a_client import A2AClient
        import requests

        with patch.object(requests, 'post') as mock_post:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "task": {
                    "id": "task-123",
                    "status": "working"
                }
            }
            mock_response.raise_for_status = MagicMock()
            mock_post.return_value = mock_response

            client = A2AClient()

            client.send_to_local(
                endpoint="http://localhost:8110",
                message="Hello!"
                # No sender_info
            )

            # Verify no metadata in payload
            call_args = mock_post.call_args
            payload = call_args.kwargs.get("json") or call_args[1].get("json")

            assert "metadata" not in payload
