"""Tests for file-based reply target persistence."""

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from synapse.a2a_compat import create_a2a_router
from synapse.reply_target import (
    clear_reply_target,
    load_reply_target,
    save_reply_target,
)


def test_save_and_load(tmp_path, monkeypatch) -> None:
    """save_reply_target should persist data and load_reply_target should return it."""
    monkeypatch.setenv("SYNAPSE_REPLY_TARGET_DIR", str(tmp_path))
    agent_id = "synapse-codex-8122"
    sender_info = {
        "sender_endpoint": "http://localhost:8110",
        "sender_task_id": "task-123",
        "sender_uds_path": "/tmp/sender.sock",
    }

    save_reply_target(agent_id, sender_info)
    loaded = load_reply_target(agent_id)

    assert loaded == sender_info


def test_clear(tmp_path, monkeypatch) -> None:
    """clear_reply_target should remove the persistence file."""
    monkeypatch.setenv("SYNAPSE_REPLY_TARGET_DIR", str(tmp_path))
    agent_id = "synapse-codex-8122"
    sender_info = {"sender_endpoint": "http://localhost:8110"}
    reply_file = Path(tmp_path) / f"{agent_id}.reply.json"

    save_reply_target(agent_id, sender_info)
    assert reply_file.exists()

    clear_reply_target(agent_id)

    assert not reply_file.exists()


def test_clear_swallows_permission_error(tmp_path, monkeypatch, caplog) -> None:
    """clear_reply_target should log and suppress PermissionError."""
    monkeypatch.setenv("SYNAPSE_REPLY_TARGET_DIR", str(tmp_path))
    monkeypatch.setattr(logging.getLogger("synapse"), "propagate", True)
    caplog.set_level(logging.WARNING, logger="synapse.reply_target")

    def raise_permission_error(self: Path, missing_ok: bool = False) -> None:
        raise PermissionError("denied")

    monkeypatch.setattr(Path, "unlink", raise_permission_error)

    clear_reply_target("synapse-codex-8122")

    assert "Failed to clear reply target" in caplog.text


def test_clear_swallows_oserror(tmp_path, monkeypatch, caplog) -> None:
    """clear_reply_target should log and suppress generic OSError."""
    monkeypatch.setenv("SYNAPSE_REPLY_TARGET_DIR", str(tmp_path))
    monkeypatch.setattr(logging.getLogger("synapse"), "propagate", True)
    caplog.set_level(logging.WARNING, logger="synapse.reply_target")

    def raise_oserror(self: Path, missing_ok: bool = False) -> None:
        raise OSError(30, "Read-only file system")

    monkeypatch.setattr(Path, "unlink", raise_oserror)

    clear_reply_target("synapse-codex-8122")

    assert "Failed to clear reply target" in caplog.text


def test_clear_swallows_invalid_agent_id(tmp_path, monkeypatch, caplog) -> None:
    """clear_reply_target should log and suppress invalid agent IDs."""
    monkeypatch.setenv("SYNAPSE_REPLY_TARGET_DIR", str(tmp_path))
    monkeypatch.setattr(logging.getLogger("synapse"), "propagate", True)
    caplog.set_level(logging.WARNING, logger="synapse.reply_target")

    clear_reply_target("../etc/passwd")

    assert "Failed to clear reply target" in caplog.text


def test_load_missing(tmp_path, monkeypatch) -> None:
    """load_reply_target should return None when no persistence file exists."""
    monkeypatch.setenv("SYNAPSE_REPLY_TARGET_DIR", str(tmp_path))
    assert load_reply_target("missing-agent") is None


def test_save_overwrites(tmp_path, monkeypatch) -> None:
    """Second save should overwrite the previous sender info."""
    monkeypatch.setenv("SYNAPSE_REPLY_TARGET_DIR", str(tmp_path))
    agent_id = "synapse-codex-8122"

    save_reply_target(agent_id, {"sender_endpoint": "http://localhost:8100"})
    save_reply_target(
        agent_id,
        {
            "sender_endpoint": "http://localhost:8110",
            "sender_task_id": "latest-task",
        },
    )

    loaded = load_reply_target(agent_id)
    assert loaded == {
        "sender_endpoint": "http://localhost:8110",
        "sender_task_id": "latest-task",
    }


def test_load_missing_saved_at_is_still_supported(tmp_path, monkeypatch) -> None:
    """Existing persistence files without saved_at should still load."""
    monkeypatch.setenv("SYNAPSE_REPLY_TARGET_DIR", str(tmp_path))
    agent_id = "synapse-codex-8122"
    reply_file = Path(tmp_path) / f"{agent_id}.reply.json"
    reply_file.write_text('{"sender_endpoint": "http://localhost:8110"}')

    loaded = load_reply_target(agent_id)

    assert loaded == {"sender_endpoint": "http://localhost:8110"}


def test_load_expired_target_returns_none(tmp_path, monkeypatch) -> None:
    """Persisted reply targets older than the TTL should be ignored."""
    monkeypatch.setenv("SYNAPSE_REPLY_TARGET_DIR", str(tmp_path))
    monkeypatch.setenv("SYNAPSE_REPLY_TARGET_TTL_SECONDS", "600")
    agent_id = "synapse-codex-8122"
    reply_file = Path(tmp_path) / f"{agent_id}.reply.json"
    expired_at = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    reply_file.write_text(
        "{"
        '"sender_endpoint": "http://localhost:8110", '
        '"sender_task_id": "task-123", '
        f'"saved_at": "{expired_at}"'
        "}"
    )

    loaded = load_reply_target(agent_id)

    assert loaded is None
    assert not reply_file.exists()


@patch("synapse.a2a_compat.save_reply_target")
def test_send_task_message_persists_reply_target(mock_save_reply_target) -> None:
    """A2A message with response_mode should persist reply target to file."""
    app = FastAPI()
    controller = MagicMock()
    controller.agent_ready = True
    controller.write = MagicMock()

    router = create_a2a_router(
        controller=controller,
        agent_type="codex",
        port=8122,
        agent_id="synapse-codex-8122",
    )
    app.include_router(router)
    client = TestClient(app)

    payload = {
        "message": {"role": "user", "parts": [{"type": "text", "text": "hello"}]},
        "metadata": {
            "response_mode": "wait",
            "sender_task_id": "task-123",
            "sender": {
                "sender_id": "synapse-claude-8100",
                "sender_endpoint": "http://localhost:8100",
            },
        },
    }
    resp = client.post("/tasks/send", json=payload)

    assert resp.status_code == 200
    mock_save_reply_target.assert_called_once()
    agent_id, sender_info = mock_save_reply_target.call_args.args
    assert agent_id == "synapse-codex-8122"
    assert sender_info["sender_id"] == "synapse-claude-8100"
    assert sender_info["sender_endpoint"] == "http://localhost:8100"
    assert sender_info["sender_task_id"] == "task-123"
    assert sender_info["message_preview"] == "hello"
    assert "received_at" in sender_info
