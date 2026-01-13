"""Tests for response option flag unification between synapse send and a2a.py send.

Issue #96: synapse send と a2a.py send でレスポンス待機のデフォルト動作とフラグ名が不整合

Requirements:
1. Flag name unification: Use --response/--no-response (not --return)
2. Default behavior unification: Both default to NOT waiting for response (safer)
3. synapse send should pass --response/--no-response to a2a.py send
"""

import argparse
import sys
from unittest.mock import MagicMock, patch

import pytest


class TestSynapseSendResponseFlags:
    """Tests for synapse send command response flags."""

    def test_synapse_send_has_response_flag(self, capsys):
        """synapse send should have --response flag (not --return)."""
        from synapse.cli import main

        with (
            patch("synapse.cli.install_skills"),
            patch("synapse.cli.cmd_send") as mock_cmd_send,
            patch.object(
                sys, "argv", ["synapse", "send", "claude", "hello", "--response"]
            ),
        ):
            main()
            args = mock_cmd_send.call_args[0][0]
            assert hasattr(args, "want_response")
            assert args.want_response is True

    def test_synapse_send_has_no_response_flag(self):
        """synapse send should have --no-response flag."""
        from synapse.cli import main

        with (
            patch("synapse.cli.install_skills"),
            patch("synapse.cli.cmd_send") as mock_cmd_send,
            patch.object(
                sys, "argv", ["synapse", "send", "claude", "hello", "--no-response"]
            ),
        ):
            main()
            args = mock_cmd_send.call_args[0][0]
            assert hasattr(args, "want_response")
            assert args.want_response is False

    def test_synapse_send_default_no_wait(self):
        """synapse send should default to NOT waiting for response."""
        from synapse.cli import main

        with (
            patch("synapse.cli.install_skills"),
            patch("synapse.cli.cmd_send") as mock_cmd_send,
            patch.object(sys, "argv", ["synapse", "send", "claude", "hello"]),
        ):
            main()
            args = mock_cmd_send.call_args[0][0]
            # Default should be None (auto mode in a2a.py will default to False)
            assert args.want_response is None

    def test_synapse_send_passes_response_flag_to_a2a(self):
        """synapse send should pass --response to a2a.py send."""
        from synapse.cli import cmd_send

        mock_args = MagicMock()
        mock_args.target = "claude"
        mock_args.message = "hello"
        mock_args.priority = 1
        mock_args.sender = None
        mock_args.reply_to = None
        mock_args.want_response = True

        with patch("synapse.cli.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="Success", stderr="")
            cmd_send(mock_args)

            cmd = mock_run.call_args[0][0]
            assert "--response" in cmd

    def test_synapse_send_passes_no_response_flag_to_a2a(self):
        """synapse send should pass --no-response to a2a.py send."""
        from synapse.cli import cmd_send

        mock_args = MagicMock()
        mock_args.target = "claude"
        mock_args.message = "hello"
        mock_args.priority = 1
        mock_args.sender = None
        mock_args.reply_to = None
        mock_args.want_response = False

        with patch("synapse.cli.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="Success", stderr="")
            cmd_send(mock_args)

            cmd = mock_run.call_args[0][0]
            assert "--no-response" in cmd

    def test_synapse_send_no_flag_when_default(self):
        """synapse send should not pass any response flag when want_response is None."""
        from synapse.cli import cmd_send

        mock_args = MagicMock()
        mock_args.target = "claude"
        mock_args.message = "hello"
        mock_args.priority = 1
        mock_args.sender = None
        mock_args.reply_to = None
        mock_args.want_response = None

        with patch("synapse.cli.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="Success", stderr="")
            cmd_send(mock_args)

            cmd = mock_run.call_args[0][0]
            # Neither --response nor --no-response should be present
            assert "--response" not in cmd
            assert "--no-response" not in cmd


class TestA2aSendResponseFlags:
    """Tests for a2a.py send command response flags."""

    def test_a2a_send_default_no_wait(self):
        """a2a.py send should default to NOT waiting for response in auto mode."""
        from synapse.tools.a2a import cmd_send

        mock_args = argparse.Namespace(
            target="claude",
            message="hello",
            priority=1,
            sender=None,
            reply_to=None,
            want_response=None,  # Default value
        )

        with (
            patch("synapse.tools.a2a.AgentRegistry") as mock_registry_cls,
            patch("synapse.tools.a2a.is_process_running", return_value=True),
            patch("synapse.tools.a2a.is_port_open", return_value=True),
            patch("synapse.tools.a2a.build_sender_info", return_value={}),
            patch("synapse.tools.a2a.A2AClient") as mock_client_cls,
            patch("synapse.tools.a2a.get_settings") as mock_settings,
        ):
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

            mock_settings.return_value.get_a2a_flow.return_value = "auto"

            cmd_send(mock_args)

            # Default should be False (not waiting)
            call_kwargs = mock_client.send_to_local.call_args.kwargs
            assert call_kwargs["response_expected"] is False

    def test_a2a_send_response_flag_waits(self):
        """a2a.py send with --response should wait for response."""
        from synapse.tools.a2a import cmd_send

        mock_args = argparse.Namespace(
            target="claude",
            message="hello",
            priority=1,
            sender=None,
            reply_to=None,
            want_response=True,
        )

        with (
            patch("synapse.tools.a2a.AgentRegistry") as mock_registry_cls,
            patch("synapse.tools.a2a.is_process_running", return_value=True),
            patch("synapse.tools.a2a.is_port_open", return_value=True),
            patch("synapse.tools.a2a.build_sender_info", return_value={}),
            patch("synapse.tools.a2a.A2AClient") as mock_client_cls,
            patch("synapse.tools.a2a.get_settings") as mock_settings,
        ):
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

            mock_settings.return_value.get_a2a_flow.return_value = "auto"

            cmd_send(mock_args)

            call_kwargs = mock_client.send_to_local.call_args.kwargs
            assert call_kwargs["response_expected"] is True


class TestResponseFlagConsistency:
    """Tests for consistency between synapse send and a2a.py send."""

    def test_both_commands_have_same_flag_names(self):
        """Both commands should use --response/--no-response flags."""
        from synapse.cli import main

        # Test --response flag
        with (
            patch("synapse.cli.install_skills"),
            patch("synapse.cli.cmd_send") as mock_cmd_send,
            patch.object(
                sys, "argv", ["synapse", "send", "claude", "hello", "--response"]
            ),
        ):
            main()
            args = mock_cmd_send.call_args[0][0]
            assert args.want_response is True

        # Test --no-response flag
        with (
            patch("synapse.cli.install_skills"),
            patch("synapse.cli.cmd_send") as mock_cmd_send,
            patch.object(
                sys, "argv", ["synapse", "send", "claude", "hello", "--no-response"]
            ),
        ):
            main()
            args = mock_cmd_send.call_args[0][0]
            assert args.want_response is False

    def test_deprecated_return_flag_not_present(self):
        """The deprecated --return flag should not be present."""
        from synapse.cli import main

        # --return flag should cause an error
        with (
            patch("synapse.cli.install_skills"),
            patch("synapse.cli.cmd_send"),
            patch.object(
                sys, "argv", ["synapse", "send", "claude", "hello", "--return"]
            ),
            pytest.raises(SystemExit),
        ):
            main()
