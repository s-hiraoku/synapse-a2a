"""
Reply Stack for A2A Message Routing

This module provides a map-based mechanism for tracking reply targets.
When an agent receives a message with response_expected=True, the sender info
is stored by sender_id. When the agent wants to reply, it retrieves by sender_id.

Key features:
- Map-based storage (sender_id -> SenderInfo)
- Multiple senders can coexist without overwriting each other
- Same sender's new message overwrites the previous entry
- Thread-safe operations
"""

import threading
from typing import TypedDict


class SenderInfo(TypedDict, total=False):
    """Sender information for reply routing."""

    sender_endpoint: str  # HTTP endpoint URL
    sender_task_id: str | None  # Task ID on sender's server (for in_reply_to)
    sender_uds_path: str | None  # UDS socket path (optional)


class ReplyStack:
    """
    Thread-safe map for tracking reply targets by sender_id.

    When a message is received from another agent with response_expected=True,
    the sender info is stored using sender_id as the key. When replying,
    pop by sender_id to get the target endpoint and task ID.
    """

    def __init__(self) -> None:
        self._map: dict[str, SenderInfo] = {}
        self._lock = threading.Lock()

    def set(self, sender_id: str, sender_info: SenderInfo) -> None:
        """Store sender info by sender_id. Overwrites and moves to end if exists."""
        with self._lock:
            # Remove existing entry first to ensure it moves to end
            self._map.pop(sender_id, None)
            self._map[sender_id] = sender_info

    def get(self, sender_id: str) -> SenderInfo | None:
        """Get sender info by sender_id without removing it."""
        with self._lock:
            return self._map.get(sender_id)

    def pop(self, sender_id: str | None = None) -> SenderInfo | None:
        """
        Pop and return sender info.

        Args:
            sender_id: If provided, pop specific sender. Otherwise pop last entry (LIFO).

        Returns:
            SenderInfo or None if not found/empty.
        """
        with self._lock:
            if sender_id is not None:
                return self._map.pop(sender_id, None)
            # Pop last entry (most recently added) if no sender_id specified
            if self._map:
                # popitem() returns (key, value) and removes last item in Python 3.7+
                _, info = self._map.popitem()
                return info
            return None

    def is_empty(self) -> bool:
        """Check if the map is empty."""
        with self._lock:
            return len(self._map) == 0

    def clear(self) -> None:
        """Clear all items from the map."""
        with self._lock:
            self._map.clear()

    def list_senders(self) -> list[str]:
        """Return list of all sender IDs currently stored."""
        with self._lock:
            return list(self._map.keys())

    def peek_last(self) -> SenderInfo | None:
        """
        Peek at the last entry (most recently added) without removing it.

        Returns:
            SenderInfo of the last entry, or None if empty.
        """
        with self._lock:
            if self._map:
                # Get last key using reversed iterator
                key = next(reversed(self._map))
                return self._map[key]
            return None


# Global reply stack instance
_reply_stack: ReplyStack | None = None
_reply_stack_lock = threading.Lock()


def get_reply_stack() -> ReplyStack:
    """Get the global reply stack instance."""
    global _reply_stack
    with _reply_stack_lock:
        if _reply_stack is None:
            _reply_stack = ReplyStack()
        return _reply_stack
