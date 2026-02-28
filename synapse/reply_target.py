"""File-based persistence for reply targets."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import cast

from synapse.paths import get_reply_target_dir
from synapse.reply_stack import SenderInfo

logger = logging.getLogger(__name__)

_SAFE_AGENT_ID = re.compile(r"^[a-zA-Z0-9._-]+$")


def _get_reply_target_path(agent_id: str) -> Path:
    """Return the reply target persistence file path for an agent."""
    if not agent_id or not _SAFE_AGENT_ID.match(agent_id):
        raise ValueError(f"Invalid agent_id for reply target path: {agent_id!r}")
    return Path(get_reply_target_dir()) / f"{agent_id}.reply.json"


def save_reply_target(agent_id: str, sender_info: SenderInfo) -> None:
    """Persist reply target sender information for an agent."""
    reply_file = _get_reply_target_path(agent_id)
    reply_file.parent.mkdir(parents=True, exist_ok=True)
    reply_file.write_text(json.dumps(sender_info), encoding="utf-8")


def load_reply_target(agent_id: str) -> SenderInfo | None:
    """Load persisted reply target sender information for an agent."""
    try:
        reply_file = _get_reply_target_path(agent_id)
        if not reply_file.exists():
            return None
        return cast(SenderInfo, json.loads(reply_file.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError, ValueError) as e:
        logger.warning("Failed to load reply target for %s: %s", agent_id, e)
        return None


def clear_reply_target(agent_id: str) -> None:
    """Delete persisted reply target sender information for an agent."""
    reply_file = _get_reply_target_path(agent_id)
    reply_file.unlink(missing_ok=True)
