"""Agent status constants and utilities.

Status flow:
    PROCESSING -> READY/WAITING -> PROCESSING -> ... -> DONE -> READY (after 10s)

Statuses:
    READY: Agent is idle (not processing anything)
    WAITING: Agent is waiting for user input (showing choices/prompt)
    PROCESSING: Agent is actively working (generating output, waiting for A2A response)
    DONE: Agent has completed a task (transitions to READY after timeout or new activity)
"""

from __future__ import annotations

# Status constants
READY = "READY"
WAITING = "WAITING"
PROCESSING = "PROCESSING"
DONE = "DONE"

# All valid statuses
ALL_STATUSES = frozenset({READY, WAITING, PROCESSING, DONE})

# Status display colors (for Rich TUI)
STATUS_STYLES = {
    READY: "bold green",  # Green: idle, ready for input
    WAITING: "bold cyan",  # Cyan: waiting for user input/choice
    PROCESSING: "bold yellow",  # Yellow: actively working
    DONE: "bold magenta",  # Magenta: completed successfully
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
