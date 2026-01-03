"""
Synapse A2A Utility Functions

This module provides common utility functions used across the codebase.
"""

from datetime import datetime, timezone
from typing import Any


def extract_text_from_parts(parts: list[Any]) -> str:
    """
    Extract text content from A2A message parts.

    Handles both dict-based parts and Pydantic model objects.

    Args:
        parts: List of message parts (TextPart, FilePart, DataPart, or dicts)

    Returns:
        Concatenated text content from all text parts, joined by newlines.
        Returns empty string if no text parts found.
    """
    text_contents: list[str] = []

    for part in parts:
        # Handle dict-based parts
        if isinstance(part, dict):
            if part.get("type") == "text" and "text" in part:
                text_contents.append(part["text"])
        # Handle Pydantic model objects (TextPart)
        elif hasattr(part, "type") and hasattr(part, "text") and part.type == "text":
            text_contents.append(part.text)

    return "\n".join(text_contents)


def format_a2a_message(task_id: str, sender_id: str, content: str) -> str:
    """
    Format a message with A2A task prefix.

    Creates the standard format: [A2A:<task_id>:<sender_id>] <content>

    Args:
        task_id: Task identifier (caller should truncate if needed)
        sender_id: Sender identifier
        content: Message content

    Returns:
        Formatted message string with A2A prefix
    """
    return f"[A2A:{task_id}:{sender_id}] {content}"


def get_iso_timestamp() -> str:
    """
    Generate an ISO 8601 timestamp in UTC with Z suffix.

    Returns:
        ISO formatted timestamp string (e.g., "2024-01-15T10:30:00.123456Z")
    """
    # Use replace to remove timezone info before adding Z suffix
    # to avoid invalid format like "2024-01-15T10:30:00+00:00Z"
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"
