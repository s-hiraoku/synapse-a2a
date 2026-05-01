"""Regression tests for reply --to diagnostics on missing sender targets."""

import argparse
from unittest.mock import MagicMock, patch

import pytest
from requests import RequestException


def _reply_args(to: str = "synapse-claude-9999") -> argparse.Namespace:
    return argparse.Namespace(
        message="done",
        message_file=None,
        stdin=False,
        fail=None,
        sender="synapse-codex-8121",
        to=to,
        list_targets=False,
    )


def _sender_info() -> dict[str, str]:
    return {
        "sender_id": "synapse-codex-8121",
        "sender_endpoint": "http://localhost:8121",
    }


def _response(status_code: int, payload: dict[str, object] | None = None) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.ok = status_code < 400
    response.json.return_value = payload or {}
    return response


def _target() -> dict[str, str | None]:
    return {
        "sender_endpoint": "http://localhost:8104",
        "sender_uds_path": None,
        "sender_task_id": "parent-task-123",
    }


@patch("synapse.tools.a2a.build_sender_info", return_value=_sender_info())
def test_reply_to_unknown_sender_lists_available_senders(mock_build, capsys) -> None:
    """Missing --to target should show available sender IDs from targets shape."""
    from synapse.tools.a2a import cmd_reply

    def fake_get(url: str, timeout: int = 5) -> MagicMock:
        if "/reply-stack/get" in url:
            return _response(404)
        if "/reply-stack/list" in url:
            return _response(
                200,
                {
                    "targets": [
                        {"sender_id": "synapse-claude-8104"},
                        {"sender_id": "synapse-gemini-8110"},
                    ],
                    "sender_ids": ["legacy-shape"],
                },
            )
        raise AssertionError(f"unexpected URL: {url}")

    with (
        patch("synapse.tools.a2a.requests.get", side_effect=fake_get),
        patch("synapse.tools.a2a.load_reply_target", return_value=None),
        pytest.raises(SystemExit) as exc_info,
    ):
        cmd_reply(_reply_args())

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "No reply target for sender 'synapse-claude-9999'." in captured.err
    assert "Stack has: synapse-claude-8104, synapse-gemini-8110" in captured.err
    assert "legacy-shape" not in captured.err


@patch("synapse.tools.a2a.build_sender_info", return_value=_sender_info())
def test_reply_to_with_empty_stack_says_empty(mock_build, capsys) -> None:
    """Missing --to target should distinguish an empty reply stack."""
    from synapse.tools.a2a import cmd_reply

    def fake_get(url: str, timeout: int = 5) -> MagicMock:
        if "/reply-stack/get" in url:
            return _response(404)
        if "/reply-stack/list" in url:
            return _response(200, {"targets": [], "sender_ids": []})
        raise AssertionError(f"unexpected URL: {url}")

    with (
        patch("synapse.tools.a2a.requests.get", side_effect=fake_get),
        patch("synapse.tools.a2a.load_reply_target", return_value=None),
        pytest.raises(SystemExit) as exc_info,
    ):
        cmd_reply(_reply_args("synapse-claude-8104"))

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "No reply target for sender 'synapse-claude-8104'." in captured.err
    assert "Reply stack is empty." in captured.err


@patch("synapse.tools.a2a._restore_sending_reply_status")
@patch("synapse.tools.a2a._set_sending_reply_status", return_value=None)
@patch("synapse.tools.a2a.AgentRegistry")
@patch("synapse.tools.a2a.A2AClient")
@patch("synapse.tools.a2a.build_sender_info", return_value=_sender_info())
def test_reply_to_existing_sender_succeeds(
    mock_build,
    mock_client_cls,
    mock_registry_cls,
    mock_set_status,
    mock_restore_status,
    capsys,
) -> None:
    """Existing --to target should keep the normal send and pop behavior."""
    from synapse.tools.a2a import cmd_reply

    mock_client = MagicMock()
    mock_client.send_to_local.return_value = MagicMock(id="reply-task")
    mock_client_cls.return_value = mock_client

    def fake_get(url: str, timeout: int = 5) -> MagicMock:
        if "/reply-stack/get" in url:
            return _response(200, _target())
        if "/reply-stack/pop" in url:
            return _response(200, _target())
        raise AssertionError(f"unexpected URL: {url}")

    with (
        patch("synapse.tools.a2a.requests.get", side_effect=fake_get) as mock_get,
        patch("synapse.tools.a2a.clear_reply_target") as mock_clear,
    ):
        cmd_reply(_reply_args("synapse-claude-8104"))

    captured = capsys.readouterr()
    assert "Reply sent to 8104" in captured.out
    assert (
        mock_client.send_to_local.call_args.kwargs["in_reply_to"] == "parent-task-123"
    )
    assert any(
        "reply-stack/pop?sender_id=synapse-claude-8104" in call.args[0]
        for call in mock_get.call_args_list
    )
    mock_clear.assert_called_once_with("synapse-codex-8121")


@patch("synapse.tools.a2a._restore_sending_reply_status")
@patch("synapse.tools.a2a._set_sending_reply_status", return_value=None)
@patch("synapse.tools.a2a.AgentRegistry")
@patch("synapse.tools.a2a.A2AClient")
@patch("synapse.tools.a2a.build_sender_info", return_value=_sender_info())
def test_reply_persisted_fallback_still_works(
    mock_build,
    mock_client_cls,
    mock_registry_cls,
    mock_set_status,
    mock_restore_status,
) -> None:
    """Persisted reply target should still be used when stack lookup is 404."""
    from synapse.tools.a2a import cmd_reply

    mock_client = MagicMock()
    mock_client.send_to_local.return_value = MagicMock(id="reply-task")
    mock_client_cls.return_value = mock_client

    with (
        patch(
            "synapse.tools.a2a.requests.get", return_value=_response(404)
        ) as mock_get,
        patch("synapse.tools.a2a.load_reply_target", return_value=_target()),
        patch("synapse.tools.a2a.clear_reply_target"),
    ):
        cmd_reply(_reply_args("synapse-claude-8104"))

    assert mock_client.send_to_local.called
    assert not any(
        "reply-stack/list" in call.args[0] for call in mock_get.call_args_list
    )


@patch("synapse.tools.a2a.build_sender_info", return_value=_sender_info())
def test_reply_list_endpoint_unavailable_falls_back_silently(
    mock_build, capsys
) -> None:
    """Diagnostic list failures should preserve the original missing-target error."""
    from synapse.tools.a2a import cmd_reply

    def fake_get(url: str, timeout: int = 5) -> MagicMock:
        if "/reply-stack/get" in url:
            return _response(404)
        if "/reply-stack/list" in url:
            raise RequestException("list endpoint down")
        raise AssertionError(f"unexpected URL: {url}")

    with (
        patch("synapse.tools.a2a.requests.get", side_effect=fake_get),
        patch("synapse.tools.a2a.load_reply_target", return_value=None),
        pytest.raises(SystemExit) as exc_info,
    ):
        cmd_reply(_reply_args("synapse-claude-8104"))

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "No reply target. No pending messages to reply to." in captured.err
    assert "list endpoint down" not in captured.err
