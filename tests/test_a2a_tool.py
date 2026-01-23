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


class TestContextOption:
    """Tests for --context option in send command (#24)."""

    def _setup_mocks(self, monkeypatch):
        """Set up common mocks for send command tests."""
        target_agent = {
            "agent_id": "synapse-gemini-8110",
            "agent_type": "gemini",
            "port": 8110,
            "endpoint": "http://localhost:8110",
            "pid": 456,
        }
        sender_agent = {
            "agent_id": "synapse-claude-8100",
            "agent_type": "claude",
            "port": 8100,
            "endpoint": "http://localhost:8100",
            "working_dir": "/path/to/project",
        }

        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = {
            "synapse-gemini-8110": target_agent,
            "synapse-claude-8100": sender_agent,
        }

        mock_client = MagicMock()
        mock_client.send_to_local.return_value = MagicMock(
            id="task-1", status="working", artifacts=[]
        )

        monkeypatch.setattr("synapse.tools.a2a.AgentRegistry", lambda: mock_registry)
        monkeypatch.setattr("synapse.tools.a2a.A2AClient", lambda: mock_client)
        monkeypatch.setattr("synapse.tools.a2a.is_process_running", lambda pid: True)
        monkeypatch.setattr(
            "synapse.tools.a2a.is_port_open", lambda *args, **kwargs: True
        )
        monkeypatch.setattr(
            "synapse.tools.a2a._record_sent_message", lambda **kwargs: None
        )

        return mock_client, sender_agent

    def test_context_flag_adds_context_to_message(self, monkeypatch):
        """--context should prepend context information to the message."""
        mock_client, sender_agent = self._setup_mocks(monkeypatch)

        args = argparse.Namespace(
            target="gemini",
            priority=1,
            sender="claude",
            want_response=None,
            reply_to=None,
            context=True,
            files=None,
            message="What is this error?",
        )

        cmd_send(args)

        mock_client.send_to_local.assert_called_once()
        call_kwargs = mock_client.send_to_local.call_args.kwargs
        message = call_kwargs.get("message")

        # Message should contain context prefix
        assert "【コンテキスト】" in message or "[Context]" in message
        assert "synapse-claude-8100" in message
        assert "/path/to/project" in message
        assert "What is this error?" in message

    def test_context_flag_off_sends_raw_message(self, monkeypatch):
        """Without --context, message should be sent as-is."""
        mock_client, _ = self._setup_mocks(monkeypatch)

        args = argparse.Namespace(
            target="gemini",
            priority=1,
            sender="claude",
            want_response=None,
            reply_to=None,
            context=False,
            files=None,
            message="Simple message",
        )

        cmd_send(args)

        mock_client.send_to_local.assert_called_once()
        call_kwargs = mock_client.send_to_local.call_args.kwargs
        message = call_kwargs.get("message")

        # Message should be raw, no context prefix
        assert "【コンテキスト】" not in message
        assert "[Context]" not in message
        assert message == "Simple message"

    def test_context_with_files_includes_file_info(self, monkeypatch, tmp_path):
        """--context with --files should include file information."""
        mock_client, _ = self._setup_mocks(monkeypatch)

        # Create a test file
        test_file = tmp_path / "test.py"
        test_file.write_text("def hello():\n    print('Hello')\n")

        args = argparse.Namespace(
            target="gemini",
            priority=1,
            sender="claude",
            want_response=None,
            reply_to=None,
            context=True,
            files=str(test_file),
            message="Review this code",
        )

        cmd_send(args)

        mock_client.send_to_local.assert_called_once()
        call_kwargs = mock_client.send_to_local.call_args.kwargs
        message = call_kwargs.get("message")

        # Message should include file content or reference
        assert "test.py" in message
        assert "Review this code" in message
