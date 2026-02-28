"""Tests for file-based reply target persistence."""

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
    monkeypatch.setenv("SYNAPSE_REGISTRY_DIR", str(tmp_path))
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
    monkeypatch.setenv("SYNAPSE_REGISTRY_DIR", str(tmp_path))
    agent_id = "synapse-codex-8122"
    sender_info = {"sender_endpoint": "http://localhost:8110"}
    reply_file = Path(tmp_path) / f"{agent_id}.reply.json"

    save_reply_target(agent_id, sender_info)
    assert reply_file.exists()

    clear_reply_target(agent_id)

    assert not reply_file.exists()


def test_load_missing(tmp_path, monkeypatch) -> None:
    """load_reply_target should return None when no persistence file exists."""
    monkeypatch.setenv("SYNAPSE_REGISTRY_DIR", str(tmp_path))
    assert load_reply_target("missing-agent") is None


def test_save_overwrites(tmp_path, monkeypatch) -> None:
    """Second save should overwrite the previous sender info."""
    monkeypatch.setenv("SYNAPSE_REGISTRY_DIR", str(tmp_path))
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


@patch("synapse.a2a_compat.save_reply_target")
def test_send_task_message_persists_reply_target(mock_save_reply_target) -> None:
    """A2A message with response_expected should persist reply target to file."""
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
            "response_expected": True,
            "sender_task_id": "task-123",
            "sender": {
                "sender_id": "synapse-claude-8100",
                "sender_endpoint": "http://localhost:8100",
            },
        },
    }
    resp = client.post("/tasks/send", json=payload)

    assert resp.status_code == 200
    mock_save_reply_target.assert_called_once_with(
        "synapse-codex-8122",
        {
            "sender_endpoint": "http://localhost:8100",
            "sender_task_id": "task-123",
        },
    )
