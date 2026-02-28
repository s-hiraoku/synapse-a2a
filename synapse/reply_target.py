"""File-based persistence for reply targets."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from synapse.paths import get_registry_dir
from synapse.reply_stack import SenderInfo


def _get_reply_target_path(agent_id: str) -> Path:
    """Return the reply target persistence file path for an agent."""
    return Path(get_registry_dir()) / f"{agent_id}.reply.json"


def save_reply_target(agent_id: str, sender_info: SenderInfo) -> None:
    """Persist reply target sender information for an agent."""
    reply_file = _get_reply_target_path(agent_id)
    reply_file.parent.mkdir(parents=True, exist_ok=True)
    reply_file.write_text(json.dumps(sender_info), encoding="utf-8")


def load_reply_target(agent_id: str) -> SenderInfo | None:
    """Load persisted reply target sender information for an agent."""
    reply_file = _get_reply_target_path(agent_id)
    if not reply_file.exists():
        return None
    return cast(SenderInfo, json.loads(reply_file.read_text(encoding="utf-8")))


def clear_reply_target(agent_id: str) -> None:
    """Delete persisted reply target sender information for an agent."""
    reply_file = _get_reply_target_path(agent_id)
    reply_file.unlink(missing_ok=True)
