"""Tests for tools/a2a.py - A2A CLI Tool."""

import argparse
import json
import os
from unittest.mock import MagicMock, patch

import pytest

from synapse.tools.a2a import (
    build_sender_info,
    cmd_cleanup,
    cmd_list,
    cmd_send,
    get_parent_pid,
    is_descendant_of,
    main,
)

# ============================================================
# get_parent_pid Function Tests
# ============================================================


class TestGetParentPid:
    """Test get_parent_pid() function."""

    def test_get_parent_pid_current_process(self):
        """Should get parent PID of current process."""
        # Current process should have a parent
        ppid = get_parent_pid(os.getpid())
        assert ppid > 0

    @patch("builtins.open", side_effect=FileNotFoundError())
    @patch("subprocess.run")
    def test_get_parent_pid_uses_ps_fallback(self, mock_run, mock_open):
        """Should use ps command as fallback on macOS."""
        mock_run.return_value = MagicMock(returncode=0, stdout="1234\n")

        ppid = get_parent_pid(99999)

        mock_run.assert_called_once()
        assert ppid == 1234

    @patch("builtins.open", side_effect=FileNotFoundError())
    @patch("subprocess.run")
    def test_get_parent_pid_returns_zero_on_error(self, mock_run, mock_open):
        """Should return 0 when unable to get parent PID."""
        mock_run.return_value = MagicMock(returncode=1, stdout="")

        ppid = get_parent_pid(99999)
        assert ppid == 0

    @patch("builtins.open", side_effect=FileNotFoundError())
    @patch("subprocess.run", side_effect=FileNotFoundError())
    def test_get_parent_pid_handles_missing_ps(self, mock_run, mock_open):
        """Should handle missing ps command."""
        ppid = get_parent_pid(99999)
        assert ppid == 0


# ============================================================
# is_descendant_of Function Tests
# ============================================================


class TestIsDescendantOf:
    """Test is_descendant_of() function."""

    def test_same_pid_is_descendant(self):
        """Same PID should be descendant of itself."""
        assert is_descendant_of(100, 100) is True

    @patch("synapse.tools.a2a.get_parent_pid")
    def test_direct_child_is_descendant(self, mock_get_parent):
        """Direct child should be descendant."""
        # PID 200 -> parent 100
        mock_get_parent.return_value = 100

        assert is_descendant_of(200, 100) is True

    @patch("synapse.tools.a2a.get_parent_pid")
    def test_grandchild_is_descendant(self, mock_get_parent):
        """Grandchild should be descendant."""

        # PID 300 -> 200 -> 100
        def parent_map(pid):
            return {300: 200, 200: 100}.get(pid, 0)

        mock_get_parent.side_effect = parent_map

        assert is_descendant_of(300, 100) is True

    @patch("synapse.tools.a2a.get_parent_pid")
    def test_not_descendant(self, mock_get_parent):
        """Unrelated process should not be descendant."""

        # PID 300 -> 200 -> 100 -> 1 (init)
        def parent_map(pid):
            return {300: 200, 200: 100, 100: 1}.get(pid, 0)

        mock_get_parent.side_effect = parent_map

        assert is_descendant_of(300, 999) is False

    def test_pid_1_not_descendant_of_other(self):
        """PID 1 (init) should not be descendant of arbitrary PID."""
        assert is_descendant_of(1, 999) is False

    @patch("synapse.tools.a2a.get_parent_pid")
    def test_max_depth_prevents_infinite_loop(self, mock_get_parent):
        """Should respect max_depth to prevent infinite loop."""
        # Always return a different parent to simulate long chain
        mock_get_parent.side_effect = lambda pid: pid - 1 if pid > 1 else 0

        # Start from PID 100, ancestor is 1 - but max_depth=5 won't reach it
        assert is_descendant_of(100, 1, max_depth=5) is False


# ============================================================
# build_sender_info Function Tests
# ============================================================


class TestBuildSenderInfo:
    """Test build_sender_info() function."""

    def test_invalid_sender_format_returns_error(self):
        """Invalid sender format should return error string."""
        result = build_sender_info(explicit_sender="my-agent")
        assert isinstance(result, str)
        assert "Error" in result
        assert "synapse-<type>-<port>" in result

    @patch("synapse.tools.a2a.AgentRegistry")
    @patch("synapse.tools.a2a.is_descendant_of")
    def test_auto_detect_from_registry(self, mock_is_descendant, mock_registry_cls):
        """Should auto-detect sender from registry PID matching."""
        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = {
            "synapse-claude-8100": {
                "agent_id": "synapse-claude-8100",
                "agent_type": "claude",
                "endpoint": "http://localhost:8100",
                "pid": 1234,
            }
        }
        mock_registry_cls.return_value = mock_registry
        mock_is_descendant.return_value = True

        result = build_sender_info()

        assert result["sender_id"] == "synapse-claude-8100"
        assert result["sender_type"] == "claude"
        assert result["sender_endpoint"] == "http://localhost:8100"

    @patch("synapse.tools.a2a.AgentRegistry")
    @patch("synapse.tools.a2a.is_descendant_of")
    def test_no_match_returns_empty(self, mock_is_descendant, mock_registry_cls):
        """Should return empty dict when no matching agent."""
        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = {}
        mock_registry_cls.return_value = mock_registry

        result = build_sender_info()

        assert result == {}

    @patch("synapse.tools.a2a.AgentRegistry")
    def test_handles_registry_exception(self, mock_registry_cls):
        """Should handle registry exceptions gracefully."""
        mock_registry_cls.side_effect = Exception("Registry error")

        result = build_sender_info()

        assert result == {}

    @patch("synapse.tools.a2a.AgentRegistry")
    def test_explicit_sender_by_agent_type_returns_error(self, mock_registry_cls):
        """Should return error when agent_type is used instead of ID."""
        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = {
            "synapse-gemini-8110": {
                "agent_id": "synapse-gemini-8110",
                "agent_type": "gemini",
                "endpoint": "http://localhost:8110",
                "uds_path": "/tmp/synapse-gemini-8110.sock",
            }
        }
        mock_registry_cls.return_value = mock_registry

        result = build_sender_info(explicit_sender="gemini")

        # Should return error string, not dict
        assert isinstance(result, str)
        assert "Error" in result
        assert "synapse-gemini-8110" in result

    @patch("synapse.tools.a2a.AgentRegistry")
    def test_explicit_sender_by_custom_name_returns_error(self, mock_registry_cls):
        """Should return error when custom name is used instead of ID."""
        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = {
            "synapse-claude-8100": {
                "agent_id": "synapse-claude-8100",
                "agent_type": "claude",
                "name": "ヒンメル",
                "endpoint": "http://localhost:8100",
                "uds_path": "/tmp/synapse-claude-8100.sock",
            }
        }
        mock_registry_cls.return_value = mock_registry

        result = build_sender_info(explicit_sender="ヒンメル")

        # Should return error string, not dict
        assert isinstance(result, str)
        assert "Error" in result
        assert "synapse-claude-8100" in result

    @patch("synapse.tools.a2a.AgentRegistry")
    def test_explicit_sender_with_valid_id(self, mock_registry_cls):
        """Should accept valid agent ID format."""
        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = {
            "synapse-gemini-8110": {
                "agent_id": "synapse-gemini-8110",
                "agent_type": "gemini",
                "endpoint": "http://localhost:8110",
                "uds_path": "/tmp/synapse-gemini-8110.sock",
            }
        }
        mock_registry_cls.return_value = mock_registry

        result = build_sender_info(explicit_sender="synapse-gemini-8110")

        assert isinstance(result, dict)
        assert result["sender_id"] == "synapse-gemini-8110"
        assert result["sender_type"] == "gemini"
        assert result["sender_endpoint"] == "http://localhost:8110"
        assert result["sender_uds_path"] == "/tmp/synapse-gemini-8110.sock"


# ============================================================
# cmd_list Function Tests
# ============================================================


class TestCmdList:
    """Test cmd_list() function."""

    @patch("synapse.tools.a2a.AgentRegistry")
    def test_cmd_list_prints_json(self, mock_registry_cls, capsys):
        """Should print agents as JSON."""
        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = {
            "agent-1": {"agent_type": "claude", "port": 8100}
        }
        mock_registry_cls.return_value = mock_registry

        args = argparse.Namespace(live=False)
        cmd_list(args)

        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert "agent-1" in output
        assert output["agent-1"]["agent_type"] == "claude"

    @patch("synapse.tools.a2a.AgentRegistry")
    def test_cmd_list_live_mode(self, mock_registry_cls, capsys):
        """Should use get_live_agents when --live flag is set."""
        mock_registry = MagicMock()
        mock_registry.get_live_agents.return_value = {
            "agent-1": {"agent_type": "claude", "port": 8100}
        }
        mock_registry_cls.return_value = mock_registry

        args = argparse.Namespace(live=True)
        cmd_list(args)

        mock_registry.get_live_agents.assert_called_once()
        mock_registry.list_agents.assert_not_called()

    @patch("synapse.tools.a2a.AgentRegistry")
    def test_cmd_list_empty(self, mock_registry_cls, capsys):
        """Should print empty JSON for no agents."""
        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = {}
        mock_registry_cls.return_value = mock_registry

        args = argparse.Namespace(live=False)
        cmd_list(args)

        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output == {}


# ============================================================
# cmd_cleanup Function Tests
# ============================================================


class TestCmdCleanup:
    """Test cmd_cleanup() function."""

    @patch("synapse.tools.a2a.AgentRegistry")
    def test_cmd_cleanup_removes_stale(self, mock_registry_cls, capsys):
        """Should remove stale entries and report."""
        mock_registry = MagicMock()
        mock_registry.cleanup_stale_entries.return_value = ["agent-1", "agent-2"]
        mock_registry_cls.return_value = mock_registry

        args = argparse.Namespace()
        cmd_cleanup(args)

        captured = capsys.readouterr()
        assert "Removed 2" in captured.out
        assert "agent-1" in captured.out
        assert "agent-2" in captured.out

    @patch("synapse.tools.a2a.AgentRegistry")
    def test_cmd_cleanup_no_stale(self, mock_registry_cls, capsys):
        """Should report when no stale entries found."""
        mock_registry = MagicMock()
        mock_registry.cleanup_stale_entries.return_value = []
        mock_registry_cls.return_value = mock_registry

        args = argparse.Namespace()
        cmd_cleanup(args)

        captured = capsys.readouterr()
        assert "No stale" in captured.out


# ============================================================
# cmd_send Function Tests
# ============================================================


class TestCmdSend:
    """Test cmd_send() function."""

    @patch("synapse.tools.a2a.A2AClient")
    @patch("synapse.tools.a2a.is_port_open", return_value=True)
    @patch("synapse.tools.a2a.is_process_running", return_value=True)
    @patch("synapse.tools.a2a.build_sender_info", return_value={})
    @patch("synapse.tools.a2a.AgentRegistry")
    def test_cmd_send_success(
        self,
        mock_registry_cls,
        mock_sender,
        mock_running,
        mock_port,
        mock_client_cls,
        capsys,
    ):
        """Should send message successfully."""
        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = {
            "synapse-claude-8100": {
                "agent_id": "synapse-claude-8100",
                "agent_type": "claude",
                "port": 8100,
                "pid": 1234,
                "endpoint": "http://localhost:8100",
            }
        }
        mock_registry_cls.return_value = mock_registry

        mock_client = MagicMock()
        mock_client.send_to_local.return_value = MagicMock(
            id="task-123", status="working"
        )
        mock_client_cls.return_value = mock_client

        args = argparse.Namespace(
            target="claude",
            message="hello world",
            priority=1,
            sender=None,
            want_response=None,
        )
        cmd_send(args)

        mock_client.send_to_local.assert_called_once()
        call_kwargs = mock_client.send_to_local.call_args.kwargs
        assert call_kwargs["message"] == "hello world"

        captured = capsys.readouterr()
        assert "Success" in captured.out
        assert "task-123" in captured.out

    @patch("synapse.tools.a2a.AgentRegistry")
    def test_cmd_send_agent_not_found(self, mock_registry_cls, capsys):
        """Should error when agent not found."""
        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = {}
        mock_registry_cls.return_value = mock_registry

        args = argparse.Namespace(
            target="nonexistent",
            message="hello",
            priority=1,
            sender=None,
            want_response=None,
        )

        with pytest.raises(SystemExit) as exc_info:
            cmd_send(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "No agent found" in captured.err

    @patch("synapse.tools.a2a.AgentRegistry")
    def test_cmd_send_ambiguous_target(self, mock_registry_cls, capsys):
        """Should error when multiple agents match target."""
        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = {
            "synapse-claude-8100": {
                "agent_id": "synapse-claude-8100",
                "agent_type": "claude",
            },
            "synapse-claude-8101": {
                "agent_id": "synapse-claude-8101",
                "agent_type": "claude",
            },
        }
        mock_registry_cls.return_value = mock_registry

        args = argparse.Namespace(
            target="claude",
            message="hello",
            priority=1,
            sender=None,
            want_response=None,
        )

        with pytest.raises(SystemExit) as exc_info:
            cmd_send(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Ambiguous" in captured.err

    @patch("synapse.tools.a2a.is_process_running", return_value=False)
    @patch("synapse.tools.a2a.AgentRegistry")
    def test_cmd_send_dead_process(self, mock_registry_cls, mock_running, capsys):
        """Should error and cleanup when agent process is dead."""
        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = {
            "synapse-claude-8100": {
                "agent_id": "synapse-claude-8100",
                "agent_type": "claude",
                "port": 8100,
                "pid": 99999,
                "endpoint": "http://localhost:8100",
            }
        }
        mock_registry_cls.return_value = mock_registry

        args = argparse.Namespace(
            target="claude",
            message="hello",
            priority=1,
            sender=None,
            want_response=None,
        )

        with pytest.raises(SystemExit) as exc_info:
            cmd_send(args)

        assert exc_info.value.code == 1
        mock_registry.unregister.assert_called_once_with("synapse-claude-8100")
        captured = capsys.readouterr()
        assert "no longer running" in captured.err

    @patch("synapse.tools.a2a.is_port_open", return_value=False)
    @patch("synapse.tools.a2a.is_process_running", return_value=True)
    @patch("synapse.tools.a2a.AgentRegistry")
    def test_cmd_send_port_not_responding(
        self, mock_registry_cls, mock_running, mock_port, capsys
    ):
        """Should error when port is not responding."""
        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = {
            "synapse-claude-8100": {
                "agent_id": "synapse-claude-8100",
                "agent_type": "claude",
                "port": 8100,
                "pid": 1234,
                "endpoint": "http://localhost:8100",
            }
        }
        mock_registry_cls.return_value = mock_registry

        args = argparse.Namespace(
            target="claude",
            message="hello",
            priority=1,
            sender=None,
            want_response=None,
        )

        with pytest.raises(SystemExit) as exc_info:
            cmd_send(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "not responding" in captured.err

    @patch("synapse.tools.a2a.A2AClient")
    @patch("synapse.tools.a2a.is_port_open", return_value=True)
    @patch("synapse.tools.a2a.is_process_running", return_value=True)
    @patch("synapse.tools.a2a.build_sender_info", return_value={"sender_id": "test"})
    @patch("synapse.tools.a2a.AgentRegistry")
    def test_cmd_send_includes_sender_info(
        self,
        mock_registry_cls,
        mock_sender,
        mock_running,
        mock_port,
        mock_client_cls,
    ):
        """Should include sender info in metadata."""
        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = {
            "synapse-claude-8100": {
                "agent_id": "synapse-claude-8100",
                "agent_type": "claude",
                "port": 8100,
                "pid": 1234,
                "endpoint": "http://localhost:8100",
            }
        }
        mock_registry_cls.return_value = mock_registry

        mock_client = MagicMock()
        mock_client.send_to_local.return_value = MagicMock(
            id="task-123", status="working"
        )
        mock_client_cls.return_value = mock_client

        args = argparse.Namespace(
            target="claude",
            message="hello",
            priority=1,
            sender=None,
            want_response=None,
        )
        cmd_send(args)

        call_kwargs = mock_client.send_to_local.call_args.kwargs
        assert call_kwargs["sender_info"] == {"sender_id": "test"}

    @patch("synapse.tools.a2a.A2AClient")
    @patch("synapse.tools.a2a.is_port_open", return_value=True)
    @patch("synapse.tools.a2a.is_process_running", return_value=True)
    @patch("synapse.tools.a2a.build_sender_info", return_value={})
    @patch("synapse.tools.a2a.AgentRegistry")
    def test_cmd_send_no_response_flag(
        self,
        mock_registry_cls,
        mock_sender,
        mock_running,
        mock_port,
        mock_client_cls,
    ):
        """Should set response_expected=False with --no-response flag in auto mode."""
        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = {
            "synapse-claude-8100": {
                "agent_id": "synapse-claude-8100",
                "agent_type": "claude",
                "port": 8100,
                "pid": 1234,
                "endpoint": "http://localhost:8100",
            }
        }
        mock_registry_cls.return_value = mock_registry

        mock_client = MagicMock()
        mock_client.send_to_local.return_value = MagicMock(
            id="task-123", status="working"
        )
        mock_client_cls.return_value = mock_client

        args = argparse.Namespace(
            target="claude",
            message="hello",
            priority=1,
            sender=None,
            want_response=False,  # --no-response sets this to False
        )

        with patch("synapse.tools.a2a.get_settings") as mock_settings:
            mock_settings.return_value.get_a2a_flow.return_value = "auto"
            cmd_send(args)

        call_kwargs = mock_client.send_to_local.call_args.kwargs
        assert call_kwargs["response_expected"] is False

    @patch("synapse.tools.a2a.A2AClient")
    @patch("synapse.tools.a2a.is_port_open", return_value=True)
    @patch("synapse.tools.a2a.is_process_running", return_value=True)
    @patch("synapse.tools.a2a.build_sender_info", return_value={})
    @patch("synapse.tools.a2a.AgentRegistry")
    def test_cmd_send_displays_artifacts(
        self,
        mock_registry_cls,
        mock_sender,
        mock_running,
        mock_port,
        mock_client_cls,
        capsys,
    ):
        """Should display response artifacts when present."""
        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = {
            "synapse-claude-8100": {
                "agent_id": "synapse-claude-8100",
                "agent_type": "claude",
                "port": 8100,
                "pid": 1234,
                "endpoint": "http://localhost:8100",
            }
        }
        mock_registry_cls.return_value = mock_registry

        mock_client = MagicMock()
        mock_client.send_to_local.return_value = MagicMock(
            id="task-123",
            status="completed",
            artifacts=[
                {"type": "text", "data": "Response content"},
                {"type": "code", "data": "def hello(): pass"},
            ],
        )
        mock_client_cls.return_value = mock_client

        args = argparse.Namespace(
            target="claude",
            message="hello",
            priority=1,
            sender=None,
            want_response=True,
        )

        with patch("synapse.tools.a2a.get_settings") as mock_settings:
            mock_settings.return_value.get_a2a_flow.return_value = "auto"
            cmd_send(args)

        captured = capsys.readouterr()
        assert "Response:" in captured.out
        assert "[text] Response content" in captured.out
        assert "[code] def hello(): pass" in captured.out

    @patch("synapse.tools.a2a.A2AClient")
    @patch("synapse.tools.a2a.is_port_open", return_value=True)
    @patch("synapse.tools.a2a.is_process_running", return_value=True)
    @patch("synapse.tools.a2a.build_sender_info", return_value={})
    @patch("synapse.tools.a2a.AgentRegistry")
    def test_cmd_send_displays_multiline_artifacts(
        self,
        mock_registry_cls,
        mock_sender,
        mock_running,
        mock_port,
        mock_client_cls,
        capsys,
    ):
        """Should indent multiline response artifacts."""
        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = {
            "synapse-claude-8100": {
                "agent_id": "synapse-claude-8100",
                "agent_type": "claude",
                "port": 8100,
                "pid": 1234,
                "endpoint": "http://localhost:8100",
            }
        }
        mock_registry_cls.return_value = mock_registry

        mock_client = MagicMock()
        mock_client.send_to_local.return_value = MagicMock(
            id="task-123",
            status="completed",
            artifacts=[{"type": "text", "data": "Line 1\nLine 2\nLine 3"}],
        )
        mock_client_cls.return_value = mock_client

        args = argparse.Namespace(
            target="claude",
            message="hello",
            priority=1,
            sender=None,
            want_response=True,
        )

        with patch("synapse.tools.a2a.get_settings") as mock_settings:
            mock_settings.return_value.get_a2a_flow.return_value = "auto"
            cmd_send(args)

        captured = capsys.readouterr()
        assert "Response:" in captured.out
        assert "[text] Line 1\n    Line 2\n    Line 3" in captured.out

    @patch("synapse.tools.a2a.A2AClient")
    @patch("synapse.tools.a2a.is_port_open", return_value=True)
    @patch("synapse.tools.a2a.is_process_running", return_value=True)
    @patch("synapse.tools.a2a.build_sender_info", return_value={})
    @patch("synapse.tools.a2a.AgentRegistry")
    def test_cmd_send_request_error(
        self,
        mock_registry_cls,
        mock_sender,
        mock_running,
        mock_port,
        mock_client_cls,
        capsys,
    ):
        """Should handle request errors."""
        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = {
            "synapse-claude-8100": {
                "agent_id": "synapse-claude-8100",
                "agent_type": "claude",
                "port": 8100,
                "pid": 1234,
                "endpoint": "http://localhost:8100",
            }
        }
        mock_registry_cls.return_value = mock_registry

        mock_client = MagicMock()
        mock_client.send_to_local.return_value = None
        mock_client_cls.return_value = mock_client

        args = argparse.Namespace(
            target="claude",
            message="hello",
            priority=1,
            sender=None,
            want_response=None,
        )

        with pytest.raises(SystemExit) as exc_info:
            cmd_send(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Error" in captured.err


# ============================================================
# main Function Tests
# ============================================================


class TestMainFunction:
    """Test main() function argument parsing."""

    @patch("synapse.tools.a2a.cmd_list")
    @patch("sys.argv", ["a2a.py", "list"])
    def test_main_list_command(self, mock_cmd):
        """main() should route to cmd_list for 'list' command."""
        main()
        mock_cmd.assert_called_once()
        args = mock_cmd.call_args[0][0]
        assert args.live is False

    @patch("synapse.tools.a2a.cmd_list")
    @patch("sys.argv", ["a2a.py", "list", "--live"])
    def test_main_list_with_live(self, mock_cmd):
        """main() should parse --live flag for list command."""
        main()
        args = mock_cmd.call_args[0][0]
        assert args.live is True

    @patch("synapse.tools.a2a.cmd_cleanup")
    @patch("sys.argv", ["a2a.py", "cleanup"])
    def test_main_cleanup_command(self, mock_cmd):
        """main() should route to cmd_cleanup for 'cleanup' command."""
        main()
        mock_cmd.assert_called_once()

    @patch("synapse.tools.a2a.cmd_send")
    @patch("sys.argv", ["a2a.py", "send", "--target", "claude", "hello world"])
    def test_main_send_command(self, mock_cmd):
        """main() should route to cmd_send for 'send' command."""
        main()
        mock_cmd.assert_called_once()
        args = mock_cmd.call_args[0][0]
        assert args.target == "claude"
        assert args.message == "hello world"
        assert args.priority == 1  # Default

    @patch("synapse.tools.a2a.cmd_send")
    @patch(
        "sys.argv",
        ["a2a.py", "send", "--target", "gemini", "--priority", "5", "urgent"],
    )
    def test_main_send_with_priority(self, mock_cmd):
        """main() should parse --priority flag."""
        main()
        args = mock_cmd.call_args[0][0]
        assert args.target == "gemini"
        assert args.priority == 5
        assert args.message == "urgent"

    @patch("synapse.tools.a2a.cmd_send")
    @patch(
        "sys.argv",
        ["a2a.py", "send", "--target", "claude", "--from", "my-agent", "message"],
    )
    def test_main_send_with_from(self, mock_cmd):
        """main() should parse --from flag."""
        main()
        args = mock_cmd.call_args[0][0]
        assert args.sender == "my-agent"

    @patch("synapse.tools.a2a.cmd_send")
    @patch(
        "sys.argv",
        ["a2a.py", "send", "--target", "claude", "--no-response", "message"],
    )
    def test_main_send_with_no_response(self, mock_cmd):
        """main() should parse --no-response flag."""
        main()
        args = mock_cmd.call_args[0][0]
        assert args.want_response is False

    @patch("sys.argv", ["a2a.py"])
    def test_main_no_command_exits(self):
        """main() should exit when no command provided."""
        with pytest.raises(SystemExit):
            main()


# ============================================================
# Exact Agent ID Match Tests
# ============================================================


class TestExactAgentIdMatch:
    """Test exact agent ID matching in cmd_send."""

    @patch("synapse.tools.a2a.A2AClient")
    @patch("synapse.tools.a2a.is_port_open", return_value=True)
    @patch("synapse.tools.a2a.is_process_running", return_value=True)
    @patch("synapse.tools.a2a.build_sender_info", return_value={})
    @patch("synapse.tools.a2a.AgentRegistry")
    def test_exact_agent_id_match(
        self,
        mock_registry_cls,
        mock_sender,
        mock_running,
        mock_port,
        mock_client_cls,
    ):
        """Should match by exact agent ID."""
        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = {
            "synapse-claude-8100": {
                "agent_id": "synapse-claude-8100",
                "agent_type": "claude",
                "port": 8100,
                "pid": 1234,
                "endpoint": "http://localhost:8100",
            },
            "synapse-claude-8101": {
                "agent_id": "synapse-claude-8101",
                "agent_type": "claude",
                "port": 8101,
                "pid": 1235,
                "endpoint": "http://localhost:8101",
            },
        }
        mock_registry_cls.return_value = mock_registry

        mock_client = MagicMock()
        mock_client.send_to_local.return_value = MagicMock(
            id="task-123", status="working"
        )
        mock_client_cls.return_value = mock_client

        # Use exact agent ID to avoid ambiguity
        args = argparse.Namespace(
            target="synapse-claude-8100",
            message="hello",
            priority=1,
            sender=None,
            want_response=None,
        )
        cmd_send(args)

        # Should succeed with exact match
        mock_client.send_to_local.assert_called_once()
        call_kwargs = mock_client.send_to_local.call_args.kwargs
        assert "8100" in call_kwargs["endpoint"]


# ============================================================
# Type-Port Shorthand Match Tests
# ============================================================


class TestTypePortShorthandMatch:
    """Test type-port shorthand matching (e.g., claude-8100) in cmd_send."""

    @patch("synapse.tools.a2a.A2AClient")
    @patch("synapse.tools.a2a.is_port_open", return_value=True)
    @patch("synapse.tools.a2a.is_process_running", return_value=True)
    @patch("synapse.tools.a2a.build_sender_info", return_value={})
    @patch("synapse.tools.a2a.AgentRegistry")
    def test_type_port_shorthand_match(
        self,
        mock_registry_cls,
        mock_sender,
        mock_running,
        mock_port,
        mock_client_cls,
    ):
        """Should match by type-port shorthand (e.g., claude-8100)."""
        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = {
            "synapse-claude-8100": {
                "agent_id": "synapse-claude-8100",
                "agent_type": "claude",
                "port": 8100,
                "pid": 1234,
                "endpoint": "http://localhost:8100",
            },
            "synapse-claude-8101": {
                "agent_id": "synapse-claude-8101",
                "agent_type": "claude",
                "port": 8101,
                "pid": 1235,
                "endpoint": "http://localhost:8101",
            },
        }
        mock_registry_cls.return_value = mock_registry

        mock_client = MagicMock()
        mock_client.send_to_local.return_value = MagicMock(
            id="task-123", status="working"
        )
        mock_client_cls.return_value = mock_client

        # Use type-port shorthand to target specific instance
        args = argparse.Namespace(
            target="claude-8101",
            message="hello",
            priority=1,
            sender=None,
            want_response=None,
        )
        cmd_send(args)

        # Should succeed with type-port match
        mock_client.send_to_local.assert_called_once()
        call_kwargs = mock_client.send_to_local.call_args.kwargs
        assert "8101" in call_kwargs["endpoint"]

    @patch("synapse.tools.a2a.A2AClient")
    @patch("synapse.tools.a2a.is_port_open", return_value=True)
    @patch("synapse.tools.a2a.is_process_running", return_value=True)
    @patch("synapse.tools.a2a.build_sender_info", return_value={})
    @patch("synapse.tools.a2a.AgentRegistry")
    def test_type_port_shorthand_case_insensitive(
        self,
        mock_registry_cls,
        mock_sender,
        mock_running,
        mock_port,
        mock_client_cls,
    ):
        """Should match type-port shorthand case-insensitively."""
        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = {
            "synapse-claude-8100": {
                "agent_id": "synapse-claude-8100",
                "agent_type": "claude",
                "port": 8100,
                "pid": 1234,
                "endpoint": "http://localhost:8100",
            },
        }
        mock_registry_cls.return_value = mock_registry

        mock_client = MagicMock()
        mock_client.send_to_local.return_value = MagicMock(
            id="task-123", status="working"
        )
        mock_client_cls.return_value = mock_client

        # Use uppercase type
        args = argparse.Namespace(
            target="CLAUDE-8100",
            message="hello",
            priority=1,
            sender=None,
            want_response=None,
        )
        cmd_send(args)

        # Should succeed
        mock_client.send_to_local.assert_called_once()

    @patch("synapse.tools.a2a.AgentRegistry")
    def test_type_port_shorthand_no_match(self, mock_registry_cls, capsys):
        """Should error when type-port doesn't match any agent."""
        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = {
            "synapse-claude-8100": {
                "agent_id": "synapse-claude-8100",
                "agent_type": "claude",
                "port": 8100,
                "pid": 1234,
                "endpoint": "http://localhost:8100",
            },
        }
        mock_registry_cls.return_value = mock_registry

        # Try to send to non-existent port
        args = argparse.Namespace(
            target="claude-9999",
            message="hello",
            priority=1,
            sender=None,
            want_response=None,
        )

        with pytest.raises(SystemExit) as exc_info:
            cmd_send(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "No agent found" in captured.err

    @patch("synapse.tools.a2a.AgentRegistry")
    def test_ambiguous_target_shows_hint(self, mock_registry_cls, capsys):
        """Should show type-port hints when target is ambiguous."""
        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = {
            "synapse-claude-8100": {
                "agent_id": "synapse-claude-8100",
                "agent_type": "claude",
                "port": 8100,
            },
            "synapse-claude-8101": {
                "agent_id": "synapse-claude-8101",
                "agent_type": "claude",
                "port": 8101,
            },
        }
        mock_registry_cls.return_value = mock_registry

        args = argparse.Namespace(
            target="claude",
            message="hello",
            priority=1,
            sender=None,
            want_response=None,
        )

        with pytest.raises(SystemExit) as exc_info:
            cmd_send(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Ambiguous" in captured.err
        # Should show helpful hints
        assert "Hint" in captured.err
        assert "claude-8100" in captured.err
        assert "claude-8101" in captured.err


class TestSentMessageHistory:
    """Test sent message history recording."""

    @patch("synapse.tools.a2a._get_history_manager")
    @patch("synapse.tools.a2a.A2AClient")
    @patch("synapse.tools.a2a.is_port_open", return_value=True)
    @patch("synapse.tools.a2a.is_process_running", return_value=True)
    @patch("synapse.tools.a2a.build_sender_info", return_value=None)
    @patch("synapse.tools.a2a.AgentRegistry")
    def test_sent_message_recorded_to_history(
        self,
        mock_registry_cls,
        mock_sender,
        mock_running,
        mock_port,
        mock_client_cls,
        mock_history_manager,
    ):
        """Should record sent message to history when enabled."""
        # Setup mock registry
        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = {
            "synapse-codex-8120": {
                "agent_id": "synapse-codex-8120",
                "agent_type": "codex",
                "port": 8120,
                "pid": 1234,
                "endpoint": "http://localhost:8120",
            }
        }
        mock_registry_cls.return_value = mock_registry

        mock_client = MagicMock()
        mock_client.send_to_local.return_value = MagicMock(
            id="task-456", status="working"
        )
        mock_client_cls.return_value = mock_client

        # Setup mock history manager
        mock_history = MagicMock()
        mock_history.enabled = True
        mock_history_manager.return_value = mock_history

        args = argparse.Namespace(
            target="codex",
            message="test message",
            priority=3,
            sender=None,
            want_response=None,
        )
        cmd_send(args)

        # Verify history was recorded
        mock_history.save_observation.assert_called_once()
        call_kwargs = mock_history.save_observation.call_args[1]
        # task_id is stored without prefix; direction is tracked in metadata
        assert call_kwargs["task_id"] == "task-456"
        assert call_kwargs["status"] == "sent"
        assert "@codex test message" in call_kwargs["input_text"]
        assert "direction" in call_kwargs["metadata"]
        assert call_kwargs["metadata"]["direction"] == "sent"
        assert call_kwargs["metadata"]["priority"] == 3

    @patch("synapse.tools.a2a._get_history_manager")
    @patch("synapse.tools.a2a.A2AClient")
    @patch("synapse.tools.a2a.is_port_open", return_value=True)
    @patch("synapse.tools.a2a.is_process_running", return_value=True)
    @patch("synapse.tools.a2a.build_sender_info", return_value=None)
    @patch("synapse.tools.a2a.AgentRegistry")
    def test_sent_message_not_recorded_when_disabled(
        self,
        mock_registry_cls,
        mock_sender,
        mock_running,
        mock_port,
        mock_client_cls,
        mock_history_manager,
    ):
        """Should not record sent message when history is disabled."""
        # Setup mock registry
        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = {
            "synapse-claude-8100": {
                "agent_id": "synapse-claude-8100",
                "agent_type": "claude",
                "port": 8100,
                "pid": 1234,
                "endpoint": "http://localhost:8100",
            }
        }
        mock_registry_cls.return_value = mock_registry

        mock_client = MagicMock()
        mock_client.send_to_local.return_value = MagicMock(
            id="task-789", status="working"
        )
        mock_client_cls.return_value = mock_client

        # Setup mock history manager (disabled)
        mock_history = MagicMock()
        mock_history.enabled = False
        mock_history_manager.return_value = mock_history

        args = argparse.Namespace(
            target="claude",
            message="test message",
            priority=1,
            sender=None,
            want_response=None,
        )
        cmd_send(args)

        # Verify history was NOT recorded
        mock_history.save_observation.assert_not_called()

    @patch("synapse.tools.a2a._get_history_manager")
    @patch("synapse.tools.a2a.A2AClient")
    @patch("synapse.tools.a2a.is_port_open", return_value=True)
    @patch("synapse.tools.a2a.is_process_running", return_value=True)
    @patch("synapse.tools.a2a.build_sender_info")
    @patch("synapse.tools.a2a.AgentRegistry")
    def test_sent_message_includes_sender_info(
        self,
        mock_registry_cls,
        mock_sender,
        mock_running,
        mock_port,
        mock_client_cls,
        mock_history_manager,
    ):
        """Should include sender info in history metadata."""
        # Setup mock registry
        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = {
            "synapse-gemini-8110": {
                "agent_id": "synapse-gemini-8110",
                "agent_type": "gemini",
                "port": 8110,
                "pid": 1234,
                "endpoint": "http://localhost:8110",
            }
        }
        mock_registry_cls.return_value = mock_registry

        mock_client = MagicMock()
        mock_client.send_to_local.return_value = MagicMock(
            id="task-abc", status="working"
        )
        mock_client_cls.return_value = mock_client

        # Setup sender info (simulating message from Claude)
        mock_sender.return_value = {
            "sender_id": "synapse-claude-8100",
            "sender_endpoint": "http://localhost:8100",
        }

        # Setup mock history manager
        mock_history = MagicMock()
        mock_history.enabled = True
        mock_history_manager.return_value = mock_history

        args = argparse.Namespace(
            target="gemini",
            message="hello from claude",
            priority=2,
            sender="synapse-claude-8100",
            want_response=None,
        )
        cmd_send(args)

        # Verify sender info in metadata
        call_kwargs = mock_history.save_observation.call_args[1]
        assert call_kwargs["agent_name"] == "claude"
        assert "sender" in call_kwargs["metadata"]


# ============================================================
# synapse reply Command Tests
# ============================================================


class TestCmdReply:
    """Test cmd_reply() function."""

    @patch("synapse.tools.a2a.A2AClient")
    @patch("synapse.tools.a2a.build_sender_info")
    @patch("requests.get")
    def test_cmd_reply_success(
        self,
        mock_requests_get,
        mock_sender,
        mock_client_cls,
        capsys,
    ):
        """Should reply to the last sender successfully."""
        from synapse.tools.a2a import cmd_reply

        # Setup: sender info returns endpoint
        mock_sender.return_value = {
            "sender_id": "synapse-claude-8100",
            "sender_endpoint": "http://localhost:8100",
        }

        # Mock the GET /reply-stack/get response (first call)
        mock_get_response = MagicMock()
        mock_get_response.status_code = 200
        mock_get_response.json.return_value = {
            "sender_endpoint": "http://localhost:8110",
            "sender_task_id": "abc12345",
        }
        # Mock the GET /reply-stack/pop response (second call after success)
        mock_pop_response = MagicMock()
        mock_pop_response.status_code = 200
        mock_requests_get.side_effect = [mock_get_response, mock_pop_response]

        # Mock the client
        mock_client = MagicMock()
        mock_client.send_to_local.return_value = MagicMock(
            id="task-123", status="completed"
        )
        mock_client_cls.return_value = mock_client

        args = argparse.Namespace(message="Hello back!")
        cmd_reply(args)

        # Verify reply was sent to correct endpoint
        mock_client.send_to_local.assert_called_once()
        call_kwargs = mock_client.send_to_local.call_args.kwargs
        assert call_kwargs["endpoint"] == "http://localhost:8110"
        assert call_kwargs["in_reply_to"] == "abc12345"
        assert call_kwargs["message"] == "Hello back!"

        # Verify get was called first, then pop after success
        assert len(mock_requests_get.call_args_list) == 2
        assert "/reply-stack/get" in mock_requests_get.call_args_list[0][0][0]
        assert "/reply-stack/pop" in mock_requests_get.call_args_list[1][0][0]

        captured = capsys.readouterr()
        assert "Reply sent" in captured.out

    @patch("synapse.tools.a2a.build_sender_info")
    @patch("requests.get")
    def test_cmd_reply_no_sender(
        self,
        mock_requests_get,
        mock_sender,
        capsys,
    ):
        """Should error when sender endpoint cannot be determined."""
        from synapse.tools.a2a import cmd_reply

        # Setup: sender info missing endpoint
        mock_sender.return_value = {}

        args = argparse.Namespace(message="Hello back!")

        with pytest.raises(SystemExit) as exc_info:
            cmd_reply(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Cannot determine my endpoint" in captured.err

    @patch("synapse.tools.a2a.build_sender_info")
    @patch("requests.get")
    def test_cmd_reply_empty_stack(
        self,
        mock_requests_get,
        mock_sender,
        capsys,
    ):
        """Should error when reply stack is empty."""
        from synapse.tools.a2a import cmd_reply

        # Setup: sender info with endpoint
        mock_sender.return_value = {
            "sender_id": "synapse-claude-8100",
            "sender_endpoint": "http://localhost:8100",
        }

        # Mock the GET /reply-stack/get response - 404 means empty
        mock_get_response = MagicMock()
        mock_get_response.status_code = 404
        mock_requests_get.return_value = mock_get_response

        args = argparse.Namespace(message="Hello back!")

        with pytest.raises(SystemExit) as exc_info:
            cmd_reply(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "No reply target" in captured.err

    @patch("synapse.tools.a2a.A2AClient")
    @patch("synapse.tools.a2a.build_sender_info")
    @patch("requests.get")
    def test_cmd_reply_without_task_id(
        self,
        mock_requests_get,
        mock_sender,
        mock_client_cls,
        capsys,
    ):
        """Should reply without in_reply_to when sender_task_id is missing."""
        from synapse.tools.a2a import cmd_reply

        # Setup: sender info returns endpoint
        mock_sender.return_value = {
            "sender_id": "synapse-claude-8100",
            "sender_endpoint": "http://localhost:8100",
        }

        # Mock the GET /reply-stack/get response - no task_id
        mock_get_response = MagicMock()
        mock_get_response.status_code = 200
        mock_get_response.json.return_value = {
            "sender_endpoint": "http://localhost:8110",
            # No sender_task_id
        }
        # Second call (pop) returns 200
        mock_pop_response = MagicMock()
        mock_pop_response.status_code = 200
        mock_requests_get.side_effect = [mock_get_response, mock_pop_response]

        # Mock the client
        mock_client = MagicMock()
        mock_client.send_to_local.return_value = MagicMock(
            id="task-123", status="completed"
        )
        mock_client_cls.return_value = mock_client

        args = argparse.Namespace(message="Reply without task ID")
        cmd_reply(args)

        # Verify reply was sent without in_reply_to
        call_kwargs = mock_client.send_to_local.call_args.kwargs
        assert call_kwargs["in_reply_to"] is None

    @patch("synapse.tools.a2a.cmd_reply")
    @patch("sys.argv", ["a2a.py", "reply", "Hello back!"])
    def test_main_reply_command(self, mock_cmd):
        """main() should route to cmd_reply for 'reply' command."""
        main()
        mock_cmd.assert_called_once()
        args = mock_cmd.call_args[0][0]
        assert args.message == "Hello back!"

    @patch("synapse.tools.a2a.A2AClient")
    @patch("synapse.tools.a2a.build_sender_info")
    @patch("requests.get")
    def test_cmd_reply_send_failure_preserves_target(
        self,
        mock_requests_get,
        mock_sender,
        mock_client_cls,
        capsys,
    ):
        """Should preserve reply target when send fails (peek before pop)."""
        from synapse.tools.a2a import cmd_reply

        # Setup: sender info returns endpoint
        mock_sender.return_value = {
            "sender_id": "synapse-claude-8100",
            "sender_endpoint": "http://localhost:8100",
        }

        # Mock the GET /reply-stack/get response (first call)
        mock_get_response = MagicMock()
        mock_get_response.status_code = 200
        mock_get_response.json.return_value = {
            "sender_endpoint": "http://localhost:8110",
            "sender_task_id": "abc12345",
        }
        mock_requests_get.return_value = mock_get_response

        # Mock the client - send fails
        mock_client = MagicMock()
        mock_client.send_to_local.return_value = None  # Failure
        mock_client_cls.return_value = mock_client

        args = argparse.Namespace(message="Hello back!")

        with pytest.raises(SystemExit) as exc_info:
            cmd_reply(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Failed to send reply" in captured.err

        # Verify peek was called (not pop), so target is preserved for retry
        # First call should be to /reply-stack/get
        assert "/reply-stack/get" in mock_requests_get.call_args_list[0][0][0]

    @patch("synapse.tools.a2a.A2AClient")
    @patch("synapse.tools.a2a.build_sender_info")
    @patch("requests.get")
    def test_cmd_reply_uds_path_support(
        self,
        mock_requests_get,
        mock_sender,
        mock_client_cls,
        capsys,
    ):
        """Should use UDS path for reply when available."""
        from synapse.tools.a2a import cmd_reply

        # Setup: sender info returns endpoint
        mock_sender.return_value = {
            "sender_id": "synapse-claude-8100",
            "sender_endpoint": "http://localhost:8100",
        }

        # Mock the GET /reply-stack/get response with UDS path
        mock_get_response = MagicMock()
        mock_get_response.status_code = 200
        mock_get_response.json.return_value = {
            "sender_endpoint": "http://localhost:8110",
            "sender_uds_path": "/tmp/synapse-a2a/gemini-8110.sock",
            "sender_task_id": "abc12345",
        }
        # Second call (pop) returns 200
        mock_pop_response = MagicMock()
        mock_pop_response.status_code = 200
        mock_requests_get.side_effect = [mock_get_response, mock_pop_response]

        # Mock the client
        mock_client = MagicMock()
        mock_client.send_to_local.return_value = MagicMock(
            id="task-123", status="completed"
        )
        mock_client_cls.return_value = mock_client

        args = argparse.Namespace(message="Hello via UDS!")
        cmd_reply(args)

        # Verify UDS path was passed to send_to_local
        mock_client.send_to_local.assert_called_once()
        call_kwargs = mock_client.send_to_local.call_args.kwargs
        assert call_kwargs["uds_path"] == "/tmp/synapse-a2a/gemini-8110.sock"

        captured = capsys.readouterr()
        assert "Reply sent" in captured.out

    @patch("synapse.tools.a2a.A2AClient")
    @patch("synapse.tools.a2a.build_sender_info")
    @patch("requests.get")
    def test_cmd_reply_uds_only_no_http(
        self,
        mock_requests_get,
        mock_sender,
        mock_client_cls,
        capsys,
    ):
        """Should work with UDS-only sender (no HTTP endpoint)."""
        from synapse.tools.a2a import cmd_reply

        # Setup: sender info returns endpoint
        mock_sender.return_value = {
            "sender_id": "synapse-claude-8100",
            "sender_endpoint": "http://localhost:8100",
        }

        # Mock the GET /reply-stack/get response - UDS only, no HTTP
        mock_get_response = MagicMock()
        mock_get_response.status_code = 200
        mock_get_response.json.return_value = {
            "sender_endpoint": None,  # No HTTP endpoint
            "sender_uds_path": "/tmp/synapse-a2a/gemini-8110.sock",
            "sender_task_id": "abc12345",
        }
        # Second call (pop) returns 200
        mock_pop_response = MagicMock()
        mock_pop_response.status_code = 200
        mock_requests_get.side_effect = [mock_get_response, mock_pop_response]

        # Mock the client
        mock_client = MagicMock()
        mock_client.send_to_local.return_value = MagicMock(
            id="task-123", status="completed"
        )
        mock_client_cls.return_value = mock_client

        args = argparse.Namespace(message="Hello UDS-only!")
        cmd_reply(args)

        # Verify UDS path was used
        call_kwargs = mock_client.send_to_local.call_args.kwargs
        assert call_kwargs["uds_path"] == "/tmp/synapse-a2a/gemini-8110.sock"
        # Safe fallback endpoint when no HTTP (avoids relative URL issues)
        assert call_kwargs["endpoint"] == "http://localhost"
