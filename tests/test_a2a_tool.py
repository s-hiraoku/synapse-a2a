import argparse
from pathlib import Path
from unittest.mock import MagicMock, patch

from synapse.tools.a2a import build_sender_info, cmd_send


class TestA2AToolSend:
    def test_cmd_send_uses_uds_when_available(self, monkeypatch):
        target_agent = {
            "agent_id": "synapse-claude-8100",
            "agent_type": "claude",
            "port": 8100,
            "endpoint": "http://localhost:8100",
            "pid": 123,
            "uds_path": "/tmp/agent.sock",
        }

        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = {"synapse-claude-8100": target_agent}

        mock_client = MagicMock()
        mock_client.send_to_local.return_value = MagicMock(
            id="task-1", status="working"
        )

        mock_port_open = MagicMock(return_value=False)

        monkeypatch.setattr("synapse.tools.a2a.AgentRegistry", lambda: mock_registry)
        monkeypatch.setattr("synapse.tools.a2a.A2AClient", lambda: mock_client)
        monkeypatch.setattr("synapse.tools.a2a.is_process_running", lambda pid: True)
        monkeypatch.setattr("synapse.tools.a2a.is_port_open", mock_port_open)
        monkeypatch.setattr(
            "synapse.tools.a2a._record_sent_message", lambda **kwargs: None
        )

        args = argparse.Namespace(
            target="claude",
            priority=1,
            sender=None,
            want_response=None,
            message="Hello",
        )

        # Mock Path.exists to return True for UDS socket file
        with patch.object(Path, "exists", return_value=True):
            cmd_send(args)

        mock_client.send_to_local.assert_called_once()
        call_kwargs = mock_client.send_to_local.call_args.kwargs
        assert call_kwargs.get("uds_path") == "/tmp/agent.sock"
        # local_only=False to allow HTTP fallback if UDS fails
        assert call_kwargs.get("local_only") is False
        mock_port_open.assert_not_called()


class TestBuildSenderInfoFromEnv:
    """Tests for SYNAPSE_AGENT_ID environment variable auto-detection (#128)."""

    def test_env_var_takes_priority_over_pid_matching(self, monkeypatch):
        """Environment variable should be checked before PID matching."""
        # Setup mock registry with the agent
        mock_agent = {
            "agent_id": "synapse-claude-8100",
            "agent_type": "claude",
            "port": 8100,
            "endpoint": "http://localhost:8100",
            "uds_path": "/tmp/claude.sock",
        }
        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = {"synapse-claude-8100": mock_agent}

        monkeypatch.setattr("synapse.tools.a2a.AgentRegistry", lambda: mock_registry)
        # Set the environment variable
        monkeypatch.setenv("SYNAPSE_AGENT_ID", "synapse-claude-8100")

        result = build_sender_info()

        assert result["sender_id"] == "synapse-claude-8100"
        assert result["sender_type"] == "claude"
        assert result["sender_endpoint"] == "http://localhost:8100"
        assert result["sender_uds_path"] == "/tmp/claude.sock"

    def test_env_var_not_in_registry_falls_back_to_pid(self, monkeypatch):
        """If env var agent not in registry, fall back to PID matching."""
        # Setup mock registry without the env agent
        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = {}

        monkeypatch.setattr("synapse.tools.a2a.AgentRegistry", lambda: mock_registry)
        monkeypatch.setenv("SYNAPSE_AGENT_ID", "synapse-nonexistent-9999")

        # PID matching should also fail, returning empty dict
        result = build_sender_info()

        assert result == {}

    def test_explicit_from_still_takes_priority(self, monkeypatch):
        """Explicit --from flag should take priority over env var."""
        mock_agent_claude = {
            "agent_id": "synapse-claude-8100",
            "agent_type": "claude",
            "port": 8100,
            "endpoint": "http://localhost:8100",
        }
        mock_agent_gemini = {
            "agent_id": "synapse-gemini-8110",
            "agent_type": "gemini",
            "port": 8110,
            "endpoint": "http://localhost:8110",
        }
        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = {
            "synapse-claude-8100": mock_agent_claude,
            "synapse-gemini-8110": mock_agent_gemini,
        }

        monkeypatch.setattr("synapse.tools.a2a.AgentRegistry", lambda: mock_registry)
        # Set env var to claude
        monkeypatch.setenv("SYNAPSE_AGENT_ID", "synapse-claude-8100")

        # But explicit --from is gemini
        result = build_sender_info("gemini")

        assert result["sender_id"] == "synapse-gemini-8110"
        assert result["sender_type"] == "gemini"

    def test_no_env_var_uses_pid_matching(self, monkeypatch):
        """Without env var, should fall back to PID matching."""
        mock_agent = {
            "agent_id": "synapse-codex-8120",
            "agent_type": "codex",
            "port": 8120,
            "endpoint": "http://localhost:8120",
            "pid": 12345,
        }
        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = {"synapse-codex-8120": mock_agent}

        monkeypatch.setattr("synapse.tools.a2a.AgentRegistry", lambda: mock_registry)
        # Ensure env var is not set
        monkeypatch.delenv("SYNAPSE_AGENT_ID", raising=False)
        # Mock PID matching to succeed
        monkeypatch.setattr(
            "synapse.tools.a2a.is_descendant_of", lambda child, ancestor: True
        )

        result = build_sender_info()

        assert result["sender_id"] == "synapse-codex-8120"
        assert result["sender_type"] == "codex"
