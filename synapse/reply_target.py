"""File-based persistence for reply targets."""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import cast

from synapse.paths import get_reply_target_dir
from synapse.reply_stack import SenderInfo

logger = logging.getLogger(__name__)

_SAFE_AGENT_ID = re.compile(r"^[a-zA-Z0-9._-]+$")
_DEFAULT_REPLY_TARGET_TTL = timedelta(minutes=30)


def _get_reply_target_ttl() -> timedelta:
    """Get reply target TTL from environment or use the default."""
    raw = os.environ.get("SYNAPSE_REPLY_TARGET_TTL_SECONDS")
    if raw is None:
        return _DEFAULT_REPLY_TARGET_TTL
    try:
        seconds = int(raw)
    except ValueError:
        logger.warning(
            "Invalid SYNAPSE_REPLY_TARGET_TTL_SECONDS=%r, using default", raw
        )
        return _DEFAULT_REPLY_TARGET_TTL
    if seconds <= 0:
        return timedelta(seconds=0)
    return timedelta(seconds=seconds)


def _get_reply_target_path(agent_id: str) -> Path:
    """Return the reply target persistence file path for an agent."""
    if not agent_id or not _SAFE_AGENT_ID.match(agent_id):
        raise ValueError(f"Invalid agent_id for reply target path: {agent_id!r}")
    return Path(get_reply_target_dir()) / f"{agent_id}.reply.json"


def save_reply_target(agent_id: str, sender_info: SenderInfo) -> None:
    """Persist reply target sender information for an agent."""
    reply_file = _get_reply_target_path(agent_id)
    reply_file.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(sender_info)
    payload["saved_at"] = datetime.now(timezone.utc).isoformat()
    reply_file.write_text(json.dumps(payload), encoding="utf-8")


def load_reply_target(agent_id: str) -> SenderInfo | None:
    """Load persisted reply target sender information for an agent."""
    try:
        reply_file = _get_reply_target_path(agent_id)
        if not reply_file.exists():
            return None
        payload = cast(dict, json.loads(reply_file.read_text(encoding="utf-8")))
        saved_at = payload.get("saved_at")
        if isinstance(saved_at, str):
            saved_dt = datetime.fromisoformat(saved_at)
            if saved_dt.tzinfo is None:
                saved_dt = saved_dt.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) - saved_dt > _get_reply_target_ttl():
                reply_file.unlink(missing_ok=True)
                return None
            payload.pop("saved_at", None)
        return cast(SenderInfo, payload)
    except (json.JSONDecodeError, OSError, ValueError) as e:
        logger.warning("Failed to load reply target for %s: %s", agent_id, e)
        return None


def clear_reply_target(agent_id: str) -> None:
    """Delete persisted reply target sender information for an agent."""
    reply_file = _get_reply_target_path(agent_id)
    reply_file.unlink(missing_ok=True)
