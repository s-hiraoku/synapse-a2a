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

    def test_cmd_send_input_required_exits_nonzero(self, monkeypatch, capsys):
        """After send_to_local returns a task stuck in input_required, cmd_send
        must print pty_context/approve hints and exit non-zero so the workflow
        runner doesn't mistake an input-waiting child for a completed step.
        """
        target_agent = {
            "agent_id": "synapse-codex-9001",
            "agent_type": "codex",
            "port": 9001,
            "endpoint": "http://localhost:9001",
            "pid": 555,
        }

        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = {"synapse-codex-9001": target_agent}

        input_required_task = MagicMock()
        input_required_task.id = "task-ir-1"
        input_required_task.status = "input_required"
        input_required_task.artifacts = []
        input_required_task.metadata = {
            "permission": {
                "pty_context": "Allow Bash: rm -rf /tmp/demo? [Y/n]",
            }
        }
        input_required_task.error = None

        mock_client = MagicMock()
        mock_client.send_to_local.return_value = input_required_task

        monkeypatch.setattr("synapse.tools.a2a.AgentRegistry", lambda: mock_registry)
        monkeypatch.setattr("synapse.tools.a2a.A2AClient", lambda: mock_client)
        monkeypatch.setattr("synapse.tools.a2a.is_process_running", lambda pid: True)
        monkeypatch.setattr("synapse.tools.a2a.is_port_open", lambda *a, **k: True)
        monkeypatch.setattr(
            "synapse.tools.a2a._record_sent_message", lambda **kwargs: None
        )
        monkeypatch.setattr("synapse.tools.a2a.build_sender_info", lambda *a, **k: {})

        args = argparse.Namespace(
            target="codex",
            priority=3,
            sender=None,
            response_mode="wait",
            message="Please release",
            message_file=None,
            task_file=None,
            stdin=False,
            attach=None,
            force=False,
            local_only=True,
        )

        import pytest

        with pytest.raises(SystemExit) as exc_info:
            cmd_send(args)

        assert exc_info.value.code != 0
        captured = capsys.readouterr()
        combined = captured.out + captured.err
        assert "input_required" in combined
        assert "task-ir-1" in combined

    def test_cmd_send_local_only_restricts_to_same_working_dir(self, monkeypatch):
        """--local-only should forward local_only=True to _resolve_target_agent.

        This makes workflow send paths only resolve to agents sharing the
        caller's working directory, never falling back to agents elsewhere.
        """
        captured: dict[str, object] = {}

        def _fake_resolve(target, agents, *, local_only=False, sender_id=None):
            captured["local_only"] = local_only
            captured["target"] = target
            return None, "No agent found matching 'codex'"

        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = {}
        monkeypatch.setattr("synapse.tools.a2a.AgentRegistry", lambda: mock_registry)
        monkeypatch.setattr("synapse.tools.a2a._resolve_target_agent", _fake_resolve)

        args = argparse.Namespace(
            target="codex",
            priority=1,
            sender=None,
            response_mode="notify",
            message="Hello",
            local_only=True,
            force=False,
        )

        import pytest

        with pytest.raises(SystemExit):
            cmd_send(args)

        assert captured.get("local_only") is True
        assert captured.get("target") == "codex"
