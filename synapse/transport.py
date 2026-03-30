"""Message transport abstraction for A2A message delivery.

Provides a pluggable transport layer so that _send_task_message() can deliver
messages via PTY stdin injection (default) or alternative mechanisms like
Claude Code's channel protocol.

Phase A: Only PTYTransport exists — behavior is identical to the pre-refactor code.
Phase B (future): ChannelTransport will be added behind the --channel flag.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Protocol

from synapse.utils import format_a2a_message

if TYPE_CHECKING:
    from synapse.a2a_compat import LongMessageStore
    from synapse.controller import TerminalController

logger = logging.getLogger(__name__)


class MessageTransport(Protocol):
    """Protocol for delivering A2A messages to an agent."""

    def deliver(
        self,
        task_id: str,
        content: str,
        *,
        response_mode: str = "silent",
        sender_id: str | None = None,
        sender_name: str | None = None,
    ) -> bool:
        """Deliver a message to the agent.

        Args:
            task_id: Task ID for tracking and long-message file naming.
            content: Message content to deliver.
            response_mode: "wait", "notify", or "silent".
            sender_id: Sender agent ID (e.g. synapse-claude-8100).
            sender_name: Sender display name.

        Returns:
            True if delivered successfully, False otherwise.
        """
        ...

    def is_available(self) -> bool:
        """Return True if this transport is ready to deliver messages."""
        ...


class PTYTransport:
    """Deliver messages via PTY stdin injection (default transport).

    Wraps the existing _prepare_pty_message → format_a2a_message →
    controller.write() pipeline with no behavior change.
    """

    def __init__(
        self,
        controller: TerminalController,
        long_message_store: LongMessageStore,
        submit_seq: str = "\n",
    ) -> None:
        self._controller = controller
        self._store = long_message_store
        self._submit_seq = submit_seq

    def deliver(
        self,
        task_id: str,
        content: str,
        *,
        response_mode: str = "silent",
        sender_id: str | None = None,
        sender_name: str | None = None,
    ) -> bool:
        """Deliver via PTY stdin injection."""
        from synapse.a2a_compat import _prepare_pty_message

        pty_text, used_file = _prepare_pty_message(
            self._store,
            task_id,
            content,
            response_mode,
            sender_id=sender_id,
            sender_name=sender_name,
        )

        prefixed_content = format_a2a_message(
            pty_text,
            response_mode=response_mode if not used_file else "silent",
            sender_id=sender_id if not used_file else None,
            sender_name=sender_name if not used_file else None,
        )

        return self._controller.write(prefixed_content, submit_seq=self._submit_seq)

    def is_available(self) -> bool:
        """PTY is available when the controller process is running."""
        return self._controller.running
