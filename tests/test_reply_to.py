"""Tests for reply --to feature (Item 5)."""

import argparse
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from synapse.reply_stack import ReplyStack

# ============================================================
# Reply Stack list_senders Tests
# ============================================================


class TestReplyStackListSenders:
    """Test ReplyStack.list_senders() method."""

    def test_list_senders_empty(self):
        """Empty stack returns empty list."""
        stack = ReplyStack()
        assert stack.list_senders() == []

    def test_list_senders_returns_all_sender_ids(self):
        """Should return all stored sender IDs."""
        stack = ReplyStack()
        stack.set("sender-a", {"sender_endpoint": "http://a:8100"})
        stack.set("sender-b", {"sender_endpoint": "http://b:8110"})
        senders = stack.list_senders()
        assert "sender-a" in senders
        assert "sender-b" in senders
        assert len(senders) == 2

    def test_list_senders_does_not_modify_stack(self):
        """list_senders should not remove entries."""
        stack = ReplyStack()
        stack.set("sender-a", {"sender_endpoint": "http://a:8100"})
        stack.list_senders()
        assert not stack.is_empty()


# ============================================================
# Reply Stack get/pop by sender_id Tests
# ============================================================


class TestReplyStackGetBySender:
    """Test ReplyStack get/pop with sender_id parameter."""

    def test_get_by_sender_id(self):
        """get(sender_id) should return specific sender's info."""
        stack = ReplyStack()
        stack.set("sender-a", {"sender_endpoint": "http://a:8100"})
        stack.set("sender-b", {"sender_endpoint": "http://b:8110"})

        result = stack.get("sender-a")
        assert result is not None
        assert result["sender_endpoint"] == "http://a:8100"

    def test_get_by_sender_id_not_found(self):
        """get(sender_id) should return None for unknown sender."""
        stack = ReplyStack()
        stack.set("sender-a", {"sender_endpoint": "http://a:8100"})

        result = stack.get("sender-unknown")
        assert result is None

    def test_pop_by_sender_id(self):
        """pop(sender_id) should remove and return specific sender."""
        stack = ReplyStack()
        stack.set("sender-a", {"sender_endpoint": "http://a:8100"})
        stack.set("sender-b", {"sender_endpoint": "http://b:8110"})

        result = stack.pop("sender-a")
        assert result is not None
        assert result["sender_endpoint"] == "http://a:8100"

        # sender-a should be gone
        assert stack.get("sender-a") is None
        # sender-b should still be there
        assert stack.get("sender-b") is not None


# ============================================================
# A2A Compat Endpoint Tests (reply-stack/list, get, pop with sender_id)
# ============================================================


class TestReplyStackEndpoints:
    """Test reply-stack HTTP endpoints via FastAPI TestClient."""

    def _create_test_app(self):
        """Create a FastAPI test app with A2A compat routes."""
        from fastapi import FastAPI

        from synapse.a2a_compat import create_a2a_router
        from synapse.reply_stack import ReplyStack

        # Use a fresh reply stack
        test_stack = ReplyStack()

        app = FastAPI()
        controller = MagicMock()
        controller.agent_id = "synapse-claude-8100"
        controller.agent_type = "claude"
        controller.port = 8100
        controller.context_recent = ""
        controller.get_status.return_value = "READY"

        with patch("synapse.a2a_compat.get_reply_stack", return_value=test_stack):
            router = create_a2a_router(
                controller=controller,
                agent_type="claude",
                port=8100,
                agent_id="synapse-claude-8100",
            )
            app.include_router(router)

        return app, test_stack

    def test_reply_stack_list_endpoint(self):
        """GET /reply-stack/list should return all sender IDs."""
        app, stack = self._create_test_app()
        stack.set("sender-a", {"sender_endpoint": "http://a:8100"})
        stack.set("sender-b", {"sender_endpoint": "http://b:8110"})

        client = TestClient(app)
        with patch("synapse.a2a_compat.get_reply_stack", return_value=stack):
            resp = client.get("/reply-stack/list")

        assert resp.status_code == 200
        data = resp.json()
        assert "sender_ids" in data
        assert "sender-a" in data["sender_ids"]
        assert "sender-b" in data["sender_ids"]

    def test_reply_stack_get_by_sender(self):
        """GET /reply-stack/get?sender_id=X should return specific sender."""
        app, stack = self._create_test_app()
        stack.set("sender-a", {"sender_endpoint": "http://a:8100"})
        stack.set("sender-b", {"sender_endpoint": "http://b:8110"})

        client = TestClient(app)
        with patch("synapse.a2a_compat.get_reply_stack", return_value=stack):
            resp = client.get("/reply-stack/get?sender_id=sender-a")

        assert resp.status_code == 200
        data = resp.json()
        assert data["sender_endpoint"] == "http://a:8100"

    def test_reply_stack_pop_by_sender(self):
        """GET /reply-stack/pop?sender_id=X should pop specific sender."""
        app, stack = self._create_test_app()
        stack.set("sender-a", {"sender_endpoint": "http://a:8100"})
        stack.set("sender-b", {"sender_endpoint": "http://b:8110"})

        client = TestClient(app)
        with patch("synapse.a2a_compat.get_reply_stack", return_value=stack):
            resp = client.get("/reply-stack/pop?sender_id=sender-a")

        assert resp.status_code == 200
        data = resp.json()
        assert data["sender_endpoint"] == "http://a:8100"

        # sender-a should be removed
        assert stack.get("sender-a") is None
        # sender-b should still exist
        assert stack.get("sender-b") is not None


# ============================================================
# CLI reply --to Tests
# ============================================================


class TestCliReplyWithToFlag:
    """Test cmd_reply with --to flag."""

    @patch("synapse.tools.a2a.requests.get")
    @patch("synapse.tools.a2a.A2AClient")
    @patch("synapse.tools.a2a.build_sender_info")
    def test_cli_reply_with_to_flag(self, mock_build, mock_client_cls, mock_get):
        """--to flag should add sender_id param to reply-stack requests."""
        from synapse.tools.a2a import cmd_reply

        mock_build.return_value = {
            "sender_id": "synapse-claude-8100",
            "sender_endpoint": "http://localhost:8100",
        }

        # Mock GET /reply-stack/get?sender_id=sender-a
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "sender_endpoint": "http://localhost:8110",
            "sender_uds_path": None,
            "sender_task_id": "task-123",
        }
        mock_get.return_value = mock_resp

        # Mock A2AClient.send_to_local
        mock_client = MagicMock()
        mock_client.send_to_local.return_value = MagicMock(id="reply-task-1")
        mock_client_cls.return_value = mock_client

        args = argparse.Namespace(
            message="My reply",
            sender="synapse-claude-8100",
            to="sender-a",
            list_targets=False,
        )
        cmd_reply(args)

        # Verify the GET request includes sender_id parameter
        get_calls = [c for c in mock_get.call_args_list if "reply-stack/get" in str(c)]
        assert len(get_calls) >= 1
        get_url = get_calls[0][0][0]
        assert "sender_id=sender-a" in get_url

    @patch("synapse.tools.a2a.requests.get")
    @patch("synapse.tools.a2a.build_sender_info")
    def test_cli_reply_list_targets(self, mock_build, mock_get, capsys):
        """--list-targets should list available reply targets."""
        from synapse.tools.a2a import cmd_reply

        mock_build.return_value = {
            "sender_id": "synapse-claude-8100",
            "sender_endpoint": "http://localhost:8100",
        }

        # Mock GET /reply-stack/list
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "sender_ids": ["sender-a", "sender-b"],
        }
        mock_get.return_value = mock_resp

        args = argparse.Namespace(
            message="unused",
            sender="synapse-claude-8100",
            to=None,
            list_targets=True,
        )
        cmd_reply(args)

        captured = capsys.readouterr()
        assert "sender-a" in captured.out
        assert "sender-b" in captured.out

    @patch("synapse.tools.a2a.requests.get")
    @patch("synapse.tools.a2a.build_sender_info")
    def test_cli_reply_list_targets_http_error_exits(
        self, mock_build, mock_get, capsys
    ):
        """--list-targets should exit 1 on non-200 response."""
        from synapse.tools.a2a import cmd_reply

        mock_build.return_value = {
            "sender_id": "synapse-claude-8100",
            "sender_endpoint": "http://localhost:8100",
        }

        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_get.return_value = mock_resp

        args = argparse.Namespace(
            message="unused",
            sender="synapse-claude-8100",
            to=None,
            list_targets=True,
        )

        with pytest.raises(SystemExit) as exc_info:
            cmd_reply(args)
        assert exc_info.value.code == 1

        captured = capsys.readouterr()
        assert "Failed to list reply targets: HTTP 500" in captured.err

    @patch("synapse.tools.a2a.requests.get")
    @patch("synapse.tools.a2a.build_sender_info")
    def test_cli_reply_list_targets_request_exception_exits(
        self, mock_build, mock_get, capsys
    ):
        """--list-targets should exit 1 on request exception."""
        from requests import RequestException

        from synapse.tools.a2a import cmd_reply

        mock_build.return_value = {
            "sender_id": "synapse-claude-8100",
            "sender_endpoint": "http://localhost:8100",
        }
        mock_get.side_effect = RequestException("network down")

        args = argparse.Namespace(
            message="unused",
            sender="synapse-claude-8100",
            to=None,
            list_targets=True,
        )

        with pytest.raises(SystemExit) as exc_info:
            cmd_reply(args)
        assert exc_info.value.code == 1

        captured = capsys.readouterr()
        assert "Failed to list reply targets: network down" in captured.err
