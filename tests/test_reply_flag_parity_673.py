"""Regression tests for `synapse reply` flag parity with `synapse send` (#673)."""

import argparse
from unittest.mock import MagicMock, patch


class TestReplyFlagParity673:
    """Verify --message-file / --stdin reach send_to_local with file content."""

    def _setup_mocks(
        self, mock_sender: MagicMock, mock_get: MagicMock, mock_post: MagicMock
    ) -> MagicMock:
        mock_sender.return_value = {
            "sender_id": "synapse-claude-8100",
            "sender_endpoint": "http://localhost:8100",
        }

        list_response = MagicMock()
        list_response.status_code = 200
        list_response.json.return_value = {
            "sender_ids": ["synapse-claude-8100"],
            "targets": [{"sender_id": "synapse-claude-8100"}],
        }
        get_response = MagicMock()
        get_response.status_code = 200
        get_response.json.return_value = {
            "sender_endpoint": "http://localhost:8110",
            "sender_task_id": "abc",
            "receiver_task_id": "local-task",
        }
        pop_response = MagicMock()
        pop_response.status_code = 200
        mock_get.side_effect = [list_response, get_response, pop_response]

        local_reply_response = MagicMock()
        local_reply_response.status_code = 200
        mock_post.return_value = local_reply_response
        return MagicMock()

    @patch("synapse.tools.a2a.A2AClient")
    @patch("synapse.tools.a2a.build_sender_info")
    @patch("requests.get")
    @patch("requests.post")
    def test_message_file_loads_content(
        self,
        mock_post: MagicMock,
        mock_get: MagicMock,
        mock_sender: MagicMock,
        mock_client_cls: MagicMock,
        tmp_path,
    ):
        from synapse.tools.a2a import cmd_reply

        self._setup_mocks(mock_sender, mock_get, mock_post)
        mock_client = MagicMock()
        mock_client.send_to_local.return_value = MagicMock(
            id="task-1", status="completed"
        )
        mock_client_cls.return_value = mock_client

        msg_path = tmp_path / "reply.txt"
        msg_path.write_text("Long reply with `backticks` that would warn\n")

        args = argparse.Namespace(
            message="",
            message_file=str(msg_path),
            stdin=False,
            fail=None,
            to=None,
            list_targets=False,
            sender=None,
        )
        cmd_reply(args)

        sent_message = mock_client.send_to_local.call_args.kwargs["message"]
        assert sent_message == "Long reply with `backticks` that would warn"

    @patch("synapse.tools.a2a.A2AClient")
    @patch("synapse.tools.a2a.build_sender_info")
    @patch("requests.get")
    @patch("requests.post")
    def test_stdin_reads_content(
        self,
        mock_post: MagicMock,
        mock_get: MagicMock,
        mock_sender: MagicMock,
        mock_client_cls: MagicMock,
        monkeypatch,
    ):
        import io

        from synapse.tools.a2a import cmd_reply

        self._setup_mocks(mock_sender, mock_get, mock_post)
        mock_client = MagicMock()
        mock_client.send_to_local.return_value = MagicMock(
            id="task-1", status="completed"
        )
        mock_client_cls.return_value = mock_client

        monkeypatch.setattr("sys.stdin", io.StringIO("piped reply\n"))

        args = argparse.Namespace(
            message="",
            message_file=None,
            stdin=True,
            fail=None,
            to=None,
            list_targets=False,
            sender=None,
        )
        cmd_reply(args)

        sent_message = mock_client.send_to_local.call_args.kwargs["message"]
        assert sent_message == "piped reply"

    @patch("synapse.tools.a2a.build_sender_info")
    def test_multiple_sources_rejected(self, mock_sender: MagicMock, capsys, tmp_path):
        from synapse.tools.a2a import cmd_reply

        mock_sender.return_value = {
            "sender_id": "synapse-claude-8100",
            "sender_endpoint": "http://localhost:8100",
        }

        msg_path = tmp_path / "reply.txt"
        msg_path.write_text("from file")

        args = argparse.Namespace(
            message="positional",
            message_file=str(msg_path),
            stdin=False,
            fail=None,
            to=None,
            list_targets=False,
            sender=None,
        )
        try:
            cmd_reply(args)
            raised = False
        except SystemExit as exc:
            raised = exc.code != 0

        assert raised
        err = capsys.readouterr().err
        assert "Multiple message sources specified" in err

    @patch("synapse.tools.a2a.build_sender_info")
    def test_message_file_not_found_errors(self, mock_sender: MagicMock, capsys):
        from synapse.tools.a2a import cmd_reply

        mock_sender.return_value = {
            "sender_id": "synapse-claude-8100",
            "sender_endpoint": "http://localhost:8100",
        }

        args = argparse.Namespace(
            message="",
            message_file="/nonexistent/reply.txt",
            stdin=False,
            fail=None,
            to=None,
            list_targets=False,
            sender=None,
        )
        try:
            cmd_reply(args)
            raised = False
        except SystemExit as exc:
            raised = exc.code != 0

        assert raised
        err = capsys.readouterr().err
        assert "Message file not found" in err

    @patch("synapse.tools.a2a.A2AClient")
    @patch("synapse.tools.a2a.build_sender_info")
    @patch("requests.get")
    @patch("requests.post")
    def test_positional_still_works(
        self,
        mock_post: MagicMock,
        mock_get: MagicMock,
        mock_sender: MagicMock,
        mock_client_cls: MagicMock,
    ):
        from synapse.tools.a2a import cmd_reply

        self._setup_mocks(mock_sender, mock_get, mock_post)
        mock_client = MagicMock()
        mock_client.send_to_local.return_value = MagicMock(
            id="task-1", status="completed"
        )
        mock_client_cls.return_value = mock_client

        args = argparse.Namespace(
            message="positional reply",
            message_file=None,
            stdin=False,
            fail=None,
            to=None,
            list_targets=False,
            sender=None,
        )
        cmd_reply(args)

        sent_message = mock_client.send_to_local.call_args.kwargs["message"]
        assert sent_message == "positional reply"
