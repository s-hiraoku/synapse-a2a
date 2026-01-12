import argparse
from pathlib import Path
from unittest.mock import MagicMock, patch

from synapse.tools.a2a import cmd_send


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
