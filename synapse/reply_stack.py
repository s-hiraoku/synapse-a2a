"""
Reply Stack for A2A Message Routing

This module provides a stack-based mechanism for tracking reply targets.
When an agent receives a message, the sender info is pushed to the stack.
When the agent wants to reply, it pops from the stack to get the target.
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
    Thread-safe stack for tracking reply targets.

    When a message is received from another agent, the sender info is pushed.
    When replying, pop to get the target endpoint and task ID.
    """

    def __init__(self) -> None:
        self._stack: list[SenderInfo] = []
        self._lock = threading.Lock()

    def push(self, sender_info: SenderInfo) -> None:
        """Push sender info onto the stack."""
        with self._lock:
            self._stack.append(sender_info)

    def pop(self) -> SenderInfo | None:
        """Pop and return the top sender info, or None if empty."""
        with self._lock:
            if self._stack:
                return self._stack.pop()
            return None

    def peek(self) -> SenderInfo | None:
        """Return the top sender info without removing it."""
        with self._lock:
            if self._stack:
                return self._stack[-1]
            return None

    def is_empty(self) -> bool:
        """Check if the stack is empty."""
        with self._lock:
            return len(self._stack) == 0

    def clear(self) -> None:
        """Clear all items from the stack."""
        with self._lock:
            self._stack.clear()


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
