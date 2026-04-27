"""Agent status constants and utilities.

Status flow:
    PROCESSING -> READY/WAITING/WAITING_FOR_INPUT -> PROCESSING -> ... -> DONE -> READY (after 10s)
    PROCESSING/READY/WAITING_FOR_INPUT -> RATE_LIMITED (on LLM provider rate-limit error;
        next controller PTY tick overwrites RATE_LIMITED when fresh output is observed)
    READY/PROCESSING/WAITING/WAITING_FOR_INPUT -> SENDING_REPLY -> previous status
        (while an agent is posting an outbound A2A send/reply)

Statuses:
    READY: Agent is idle (not processing anything)
    WAITING: Agent is waiting for user input (showing choices/prompt)
    WAITING_FOR_INPUT: Agent has an A2A task waiting for a non-permission response
    PROCESSING: Agent is actively working (generating output, waiting for A2A response)
    DONE: Agent has completed a task (transitions to READY after timeout or new activity)
    RATE_LIMITED: Agent hit an LLM provider rate limit
    SENDING_REPLY: Agent is sending an outbound A2A reply/message
"""

from __future__ import annotations

# Status constants
READY = "READY"
WAITING = "WAITING"
WAITING_FOR_INPUT = "WAITING_FOR_INPUT"
PROCESSING = "PROCESSING"
DONE = "DONE"
RATE_LIMITED = "RATE_LIMITED"
SENDING_REPLY = "SENDING_REPLY"
SHUTTING_DOWN = "SHUTTING_DOWN"

# All valid statuses
ALL_STATUSES = frozenset(
    {
        READY,
        WAITING,
        WAITING_FOR_INPUT,
        PROCESSING,
        DONE,
        RATE_LIMITED,
        SENDING_REPLY,
        SHUTTING_DOWN,
    }
)

# Status display colors (for Rich TUI)
STATUS_STYLES = {
    READY: "bold green",  # Green: idle, ready for input
    WAITING: "bold cyan",  # Cyan: waiting for user input/choice
    WAITING_FOR_INPUT: "bold orange3",  # Orange: waiting for A2A/human response
    PROCESSING: "bold yellow",  # Yellow: actively working
    DONE: "bold blue",  # Blue: completed successfully
    RATE_LIMITED: "bold magenta",  # Magenta: LLM provider rate limit hit
    SENDING_REPLY: "bold cyan",  # Cyan: outbound A2A send/reply in progress
    SHUTTING_DOWN: "bold red",  # Red: graceful shutdown in progress
}

# DONE status auto-transition timeout (seconds)
DONE_TIMEOUT_SECONDS = 10.0


def is_valid_status(status: str) -> bool:
    """Check if a status string is valid.

    Args:
        status: Status string to validate.

    Returns:
        True if valid, False otherwise.
    """
    return status in ALL_STATUSES


def get_status_style(status: str) -> str:
    """Get Rich style for a status.

    Args:
        status: Status string.

    Returns:
        Rich style string, or empty string for unknown status.
    """
    return STATUS_STYLES.get(status, "")
