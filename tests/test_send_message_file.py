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
from unittest.mock import patch

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
        stdin=False,
    ) -> argparse.Namespace:
        return argparse.Namespace(
            message=message,
            message_file=message_file,
            stdin=stdin,
        )

    def test_positional_message(self):
        """Positional message argument is returned as-is."""
        from synapse.tools.a2a import _resolve_message

        args = self._make_args(message="hello world")
        assert _resolve_message(args) == "hello world"

    def test_message_file(self, tmp_path):
        """--message-file reads content from file."""
        from synapse.tools.a2a import _resolve_message

        msg_file = tmp_path / "msg.txt"
        msg_file.write_text("file content here", encoding="utf-8")
        args = self._make_args(message_file=str(msg_file))
        assert _resolve_message(args) == "file content here"

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
            assert _resolve_message(args) == "stdin content"

    def test_message_file_dash_reads_stdin(self):
        """--message-file - reads from stdin."""
        from synapse.tools.a2a import _resolve_message

        args = self._make_args(message_file="-")
        with patch("sys.stdin", StringIO("stdin via dash")):
            assert _resolve_message(args) == "stdin via dash"

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
