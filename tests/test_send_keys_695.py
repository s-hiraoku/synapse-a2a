"""Tests for synapse send-keys (issue #695).

Covers:
- escape sequence decoding (\\r, \\x1b, etc.)
- --no-escape preserves literal text
- HTTP endpoint authorization shape (require_auth integration is exercised
  by the A2A server's existing fixtures, so we test only the controller
  delegation path here)
- error path: missing data + missing --enter
"""

from __future__ import annotations

import argparse
import json
from unittest.mock import MagicMock, patch

import pytest

from synapse.commands import send_keys


def _ns(**overrides: object) -> argparse.Namespace:
    base = {
        "target": "synapse-codex-9999",
        "data": "a",
        "escape": True,
        "enter": False,
        "json": False,
    }
    base.update(overrides)
    return argparse.Namespace(**base)


def test_decode_data_escape_decodes_backslash_r() -> None:
    assert send_keys._decode_data("a\\r", escape=True) == "a\r"


def test_decode_data_escape_decodes_esc() -> None:
    assert send_keys._decode_data("\\x1b", escape=True) == "\x1b"


def test_decode_data_no_escape_preserves_literal() -> None:
    assert send_keys._decode_data("a\\r", escape=False) == "a\\r"


def test_cmd_send_keys_requires_data_or_enter(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        send_keys.cmd_send_keys(_ns(data=None, enter=False))
    assert exc_info.value.code == 2
    err = capsys.readouterr().err
    assert "provide DATA" in err


def test_cmd_send_keys_enter_with_no_data_sends_empty_string_with_submit_seq(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--enter alone is allowed; sends empty data with \\r submit_seq."""
    fake_resp = MagicMock()
    fake_resp.read.return_value = json.dumps({"ok": True, "bytes_written": 0}).encode()
    fake_resp.__enter__ = lambda s: s
    fake_resp.__exit__ = lambda *_: None

    captured: dict[str, object] = {}

    def fake_urlopen(req, timeout):  # type: ignore[no-untyped-def]
        captured["url"] = req.full_url
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return fake_resp

    with (
        patch.object(
            send_keys, "_resolve_endpoint", return_value="http://localhost:9999"
        ),
        patch("urllib.request.urlopen", side_effect=fake_urlopen),
    ):
        send_keys.cmd_send_keys(_ns(data=None, enter=True))

    assert captured["url"] == "http://localhost:9999/pty/write"
    assert captured["body"] == {"data": "", "submit_seq": "\r"}


def test_cmd_send_keys_decodes_data_before_post(
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake_resp = MagicMock()
    fake_resp.read.return_value = json.dumps({"ok": True, "bytes_written": 2}).encode()
    fake_resp.__enter__ = lambda s: s
    fake_resp.__exit__ = lambda *_: None

    captured: dict[str, object] = {}

    def fake_urlopen(req, timeout):  # type: ignore[no-untyped-def]
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return fake_resp

    with (
        patch.object(
            send_keys, "_resolve_endpoint", return_value="http://localhost:9999"
        ),
        patch("urllib.request.urlopen", side_effect=fake_urlopen),
    ):
        send_keys.cmd_send_keys(_ns(data="y\\r", escape=True))

    assert captured["body"]["data"] == "y\r"


def test_cmd_send_keys_reports_failure_when_endpoint_returns_not_ok(
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake_resp = MagicMock()
    fake_resp.read.return_value = json.dumps({"ok": False}).encode()
    fake_resp.__enter__ = lambda s: s
    fake_resp.__exit__ = lambda *_: None

    with (
        patch.object(
            send_keys, "_resolve_endpoint", return_value="http://localhost:9999"
        ),
        patch("urllib.request.urlopen", return_value=fake_resp),
    ):
        with pytest.raises(SystemExit) as exc_info:
            send_keys.cmd_send_keys(_ns(data="a"))
        assert exc_info.value.code == 1

    err = capsys.readouterr().err
    assert "PTY write reported failure" in err
