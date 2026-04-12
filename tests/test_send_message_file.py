"""
Tests for --message-file / --stdin support in synapse send/broadcast.

Phase 1: Message input source resolution
Phase 2: Auto temp-file fallback for large messages
Phase 4: Shell expansion warning
"""

import argparse
import os
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Phase 1: _resolve_message (tools/a2a.py)
# ---------------------------------------------------------------------------
class TestResolveMessage:
    """Tests for _resolve_message() in synapse/tools/a2a.py."""

    def _make_args(
        self,
        message=None,
        message_file=None,
        task_file=None,
        stdin=False,
    ) -> argparse.Namespace:
        return argparse.Namespace(
            message=message,
            message_file=message_file,
            task_file=task_file,
            stdin=stdin,
        )

    def test_positional_message(self):
        """Positional message argument is returned as-is."""
        from synapse.tools.a2a import _resolve_message

        args = self._make_args(message="hello world")
        message, source = _resolve_message(args)
        assert message == "hello world"
        assert source == "positional"

    def test_resolve_message_returns_tuple_positional(self):
        """Positional message returns message and source tuple."""
        from synapse.tools.a2a import _resolve_message

        args = self._make_args(message="message text")
        assert _resolve_message(args) == ("message text", "positional")

    def test_message_file(self, tmp_path):
        """--message-file reads content from file."""
        from synapse.tools.a2a import _resolve_message

        msg_file = tmp_path / "msg.txt"
        msg_file.write_text("file content here", encoding="utf-8")
        args = self._make_args(message_file=str(msg_file))
        message, source = _resolve_message(args)
        assert message == "file content here"
        assert source == "message_file"

    def test_resolve_message_returns_tuple_message_file(self, tmp_path):
        """--message-file returns content and source tuple."""
        from synapse.tools.a2a import _resolve_message

        msg_file = tmp_path / "msg.txt"
        msg_file.write_text("from message file", encoding="utf-8")
        args = self._make_args(message_file=str(msg_file))
        assert _resolve_message(args) == ("from message file", "message_file")

    def test_message_file_not_found(self):
        """--message-file with nonexistent file raises SystemExit."""
        from synapse.tools.a2a import _resolve_message

        args = self._make_args(message_file="/nonexistent/path.txt")
        with pytest.raises(SystemExit):
            _resolve_message(args)

    def test_stdin_flag(self):
        """--stdin reads from sys.stdin."""
        from synapse.tools.a2a import _resolve_message

        args = self._make_args(stdin=True)
        with patch("sys.stdin", StringIO("stdin content")):
            message, source = _resolve_message(args)
            assert message == "stdin content"
            assert source == "stdin"

    def test_resolve_message_returns_tuple_stdin(self):
        """--stdin returns content and source tuple."""
        from synapse.tools.a2a import _resolve_message

        args = self._make_args(stdin=True)
        with patch("sys.stdin", StringIO("stdin tuple")):
            assert _resolve_message(args) == ("stdin tuple", "stdin")

    def test_message_file_dash_reads_stdin(self):
        """--message-file - reads from stdin."""
        from synapse.tools.a2a import _resolve_message

        args = self._make_args(message_file="-")
        with patch("sys.stdin", StringIO("stdin via dash")):
            message, source = _resolve_message(args)
            assert message == "stdin via dash"
            assert source == "message_file"

    def test_no_source_error(self):
        """No message source raises SystemExit."""
        from synapse.tools.a2a import _resolve_message

        args = self._make_args()
        with pytest.raises(SystemExit):
            _resolve_message(args)

    def test_multiple_sources_error(self):
        """Multiple message sources raise SystemExit."""
        from synapse.tools.a2a import _resolve_message

        args = self._make_args(message="hello", stdin=True)
        with pytest.raises(SystemExit):
            _resolve_message(args)

    def test_positional_and_file_error(self):
        """Positional + --message-file raises SystemExit."""
        from synapse.tools.a2a import _resolve_message

        args = self._make_args(message="hello", message_file="/tmp/x.txt")
        with pytest.raises(SystemExit):
            _resolve_message(args)

    def test_task_file_reads_content(self, tmp_path):
        """--task-file reads content from file."""
        from synapse.tools.a2a import _resolve_message

        task_file = tmp_path / "task.txt"
        task_file.write_text("task file content", encoding="utf-8")
        args = self._make_args(task_file=str(task_file))
        assert _resolve_message(args) == ("task file content", "task_file")

    def test_task_file_and_message_file_conflict(self, tmp_path):
        """--task-file conflicts with --message-file."""
        from synapse.tools.a2a import _resolve_message

        msg_file = tmp_path / "msg.txt"
        task_file = tmp_path / "task.txt"
        msg_file.write_text("message", encoding="utf-8")
        task_file.write_text("task", encoding="utf-8")
        args = self._make_args(
            message_file=str(msg_file),
            task_file=str(task_file),
        )
        with pytest.raises(SystemExit):
            _resolve_message(args)


# ---------------------------------------------------------------------------
# Phase 1: _resolve_cli_message (cli.py)
# ---------------------------------------------------------------------------
class TestResolveCliMessage:
    """Tests for _resolve_cli_message() in synapse/cli.py."""

    def _make_args(
        self,
        message=None,
        message_file=None,
        stdin=False,
    ) -> argparse.Namespace:
        return argparse.Namespace(
            message=message,
            message_file=message_file,
            stdin=stdin,
        )

    def test_positional_message(self):
        """Positional message works."""
        from synapse.cli import _resolve_cli_message

        args = self._make_args(message="hello")
        assert _resolve_cli_message(args) == "hello"

    def test_message_file(self, tmp_path):
        """--message-file reads from file."""
        from synapse.cli import _resolve_cli_message

        msg_file = tmp_path / "msg.txt"
        msg_file.write_text("from file", encoding="utf-8")
        args = self._make_args(message_file=str(msg_file))
        assert _resolve_cli_message(args) == "from file"

    def test_stdin_flag(self):
        """--stdin reads from sys.stdin."""
        from synapse.cli import _resolve_cli_message

        args = self._make_args(stdin=True)
        with patch("sys.stdin", StringIO("from stdin")):
            assert _resolve_cli_message(args) == "from stdin"

    def test_no_source_error(self):
        """No message source raises SystemExit."""
        from synapse.cli import _resolve_cli_message

        args = self._make_args()
        with pytest.raises(SystemExit):
            _resolve_cli_message(args)

    def test_multiple_sources_error(self):
        """Multiple sources raise SystemExit."""
        from synapse.cli import _resolve_cli_message

        args = self._make_args(message="hello", stdin=True)
        with pytest.raises(SystemExit):
            _resolve_cli_message(args)


# ---------------------------------------------------------------------------
# Phase 2: _build_a2a_cmd auto temp-file fallback
# ---------------------------------------------------------------------------
class TestBuildA2aCmdAutoFallback:
    """Tests for auto temp-file fallback in _build_a2a_cmd()."""

    def test_short_message_uses_positional(self):
        """Short messages are passed as positional args."""
        from synapse.cli import _build_a2a_cmd

        cmd = _build_a2a_cmd("send", "short msg", target="claude")
        # Should contain message as positional, no --message-file
        assert "short msg" in cmd
        assert "--message-file" not in cmd

    def test_large_message_uses_temp_file(self):
        """Messages > threshold are written to temp file."""
        from synapse.cli import _build_a2a_cmd

        large_msg = "x" * 200_000  # 200KB > 100KB threshold
        cmd = _build_a2a_cmd("send", large_msg, target="claude")
        assert "--message-file" in cmd
        # The positional large message should NOT be in the command
        assert large_msg not in cmd
        # The temp file should exist and contain the message
        idx = cmd.index("--message-file")
        temp_path = cmd[idx + 1]
        assert Path(temp_path).exists()
        assert Path(temp_path).read_text(encoding="utf-8") == large_msg

    def test_threshold_env_override(self):
        """SYNAPSE_SEND_MESSAGE_THRESHOLD env var overrides default."""
        from synapse.cli import _build_a2a_cmd

        # Set threshold very low (10 bytes)
        with patch.dict(os.environ, {"SYNAPSE_SEND_MESSAGE_THRESHOLD": "10"}):
            cmd = _build_a2a_cmd("send", "a" * 20, target="claude")
            assert "--message-file" in cmd

    def test_at_threshold_no_fallback(self):
        """Messages exactly at the threshold use positional arg."""
        from synapse.cli import _build_a2a_cmd

        # Default threshold is 100KB (102400 bytes)
        msg = "x" * 102_400
        with patch.dict(os.environ, {"SYNAPSE_SEND_MESSAGE_THRESHOLD": "102400"}):
            cmd = _build_a2a_cmd("send", msg, target="claude")
            # At threshold, should not fall back (only > threshold triggers)
            assert "--message-file" not in cmd


# ---------------------------------------------------------------------------
# Phase 4: Shell expansion warning
# ---------------------------------------------------------------------------
class TestShellExpansionWarning:
    """Tests for shell expansion detection in cmd_send()."""

    def test_backtick_warning(self, capsys):
        """Backtick in message triggers warning."""
        from synapse.tools.a2a import _warn_shell_expansion

        _warn_shell_expansion("check `date` here")
        captured = capsys.readouterr()
        assert "shell expansion" in captured.err.lower() or "WARNING" in captured.err

    def test_dollar_paren_warning(self, capsys):
        """$() in message triggers warning."""
        from synapse.tools.a2a import _warn_shell_expansion

        _warn_shell_expansion("check $(date) here")
        captured = capsys.readouterr()
        assert "shell expansion" in captured.err.lower() or "WARNING" in captured.err

    def test_normal_message_no_warning(self, capsys):
        """Normal message does not trigger warning."""
        from synapse.tools.a2a import _warn_shell_expansion

        _warn_shell_expansion("a normal message")
        captured = capsys.readouterr()
        assert captured.err == ""

    @patch("synapse.tools.a2a.A2AClient")
    @patch("synapse.tools.a2a.is_port_open", return_value=True)
    @patch("synapse.tools.a2a.is_process_running", return_value=True)
    @patch("synapse.tools.a2a.build_sender_info", return_value={})
    @patch("synapse.tools.a2a.AgentRegistry")
    def test_message_file_no_backtick_warning(
        self,
        mock_registry_cls,
        _mock_sender,
        _mock_running,
        _mock_port,
        mock_client_cls,
        tmp_path,
        capsys,
    ):
        """--message-file content skips shell expansion warning."""
        from synapse.tools.a2a import cmd_send

        msg_file = tmp_path / "msg.txt"
        msg_file.write_text("check `date` here", encoding="utf-8")
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
            id="task-123", status="working", artifacts=[]
        )
        mock_client_cls.return_value = mock_client

        args = argparse.Namespace(
            target="claude",
            message=None,
            message_file=str(msg_file),
            task_file=None,
            stdin=False,
            priority=1,
            sender=None,
            response_mode="notify",
            attach=None,
            force=False,
        )

        cmd_send(args)

        captured = capsys.readouterr()
        assert "WARNING" not in captured.err

    @patch("synapse.tools.a2a.A2AClient")
    @patch("synapse.tools.a2a.is_port_open", return_value=True)
    @patch("synapse.tools.a2a.is_process_running", return_value=True)
    @patch("synapse.tools.a2a.build_sender_info", return_value={})
    @patch("synapse.tools.a2a.AgentRegistry")
    def test_stdin_no_backtick_warning(
        self,
        mock_registry_cls,
        _mock_sender,
        _mock_running,
        _mock_port,
        mock_client_cls,
        capsys,
    ):
        """--stdin content skips shell expansion warning."""
        from synapse.tools.a2a import cmd_send

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
            id="task-123", status="working", artifacts=[]
        )
        mock_client_cls.return_value = mock_client

        args = argparse.Namespace(
            target="claude",
            message=None,
            message_file=None,
            task_file=None,
            stdin=True,
            priority=1,
            sender=None,
            response_mode="notify",
            attach=None,
            force=False,
        )

        with patch("sys.stdin", StringIO("check `date` here")):
            cmd_send(args)

        captured = capsys.readouterr()
        assert "WARNING" not in captured.err

    @patch("synapse.tools.a2a.A2AClient")
    @patch("synapse.tools.a2a.is_port_open", return_value=True)
    @patch("synapse.tools.a2a.is_process_running", return_value=True)
    @patch("synapse.tools.a2a.build_sender_info", return_value={})
    @patch("synapse.tools.a2a.AgentRegistry")
    def test_positional_backtick_warning_still_works(
        self,
        mock_registry_cls,
        _mock_sender,
        _mock_running,
        _mock_port,
        mock_client_cls,
        capsys,
    ):
        """Positional messages still emit shell expansion warning."""
        from synapse.tools.a2a import cmd_send

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
            id="task-123", status="working", artifacts=[]
        )
        mock_client_cls.return_value = mock_client

        args = argparse.Namespace(
            target="claude",
            message="check `date` here",
            message_file=None,
            task_file=None,
            stdin=False,
            priority=1,
            sender=None,
            response_mode="notify",
            attach=None,
            force=False,
        )

        cmd_send(args)

        captured = capsys.readouterr()
        assert "WARNING" in captured.err
