import argparse
from pathlib import Path
from unittest.mock import MagicMock, patch

from synapse.tools.a2a import cmd_send


class TestA2AHelperReexports:
    def test_a2a_reexports_extracted_helpers(self):
        from synapse.tools import a2a, a2a_helpers

        helper_names = [
            "get_parent_pid",
            "is_descendant_of",
            "_extract_sender_info_from_agent",
            "_validate_explicit_sender",
            "_lookup_sender_in_registry",
            "_get_current_tty",
            "_find_sender_by_pid",
            "build_sender_info",
            "_pick_best_agent",
            "_resolve_target_agent",
            "_format_ambiguous_target_error",
            "_extract_agent_type_from_id",
            "_suggest_spawn_type",
            "_resolve_message",
            "_process_attachments",
            "_warn_shell_expansion",
            "_artifact_display_text",
            "_format_task_error",
            "_get_target_display_name",
            "_get_history_manager",
            "_record_sent_message",
            "_normalize_working_dir",
            "_agents_in_current_working_dir",
            "_warn_working_dir_mismatch",
            "_get_response_mode",
            "_add_response_mode_flags",
            "_add_message_source_flags",
        ]

        for name in helper_names:
            assert getattr(a2a, name) is getattr(a2a_helpers, name)


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
            response_mode="notify",
            message="Hello",
        )

        # Mock Path.exists to return True for UDS socket file
        with patch.object(Path, "exists", return_value=True):
            cmd_send(args)

        mock_client.send_to_local.assert_called_once()
        call_kwargs = mock_client.send_to_local.call_args.kwargs
        assert call_kwargs.get("uds_path") == "/tmp/agent.sock"
        # local_only defaults to False (allows HTTP fallback if UDS fails)
        assert call_kwargs.get("local_only", False) is False
        mock_port_open.assert_not_called()
