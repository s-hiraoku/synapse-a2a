"""
Synapse A2A Utility Functions

This module provides common utility functions used across the codebase.
"""

import os
import shutil
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


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


def format_a2a_message(content: str, response_expected: bool = False) -> str:
    """
    Format a message with A2A prefix.

    Creates the format: A2A: [REPLY EXPECTED] <content> (if response expected)
    Or simply: A2A: <content> (if no response expected)

    Args:
        content: Message content
        response_expected: Whether the sender expects a response

    Returns:
        Formatted message string with A2A prefix and optional reply marker
    """
    if response_expected:
        return f"A2A: [REPLY EXPECTED] {content}"
    return f"A2A: {content}"


def get_iso_timestamp() -> str:
    """
    Generate an ISO 8601 timestamp in UTC with Z suffix.

    Returns:
        ISO formatted timestamp string (e.g., "2024-01-15T10:30:00.123456Z")
    """
    # Use replace to remove timezone info before adding Z suffix
    # to avoid invalid format like "2024-01-15T10:30:00+00:00Z"
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"


def generate_task_id() -> str:
    """
    Generate a unique task ID for A2A messages.

    Returns:
        A UUID-based task ID string (first 8 characters for brevity).
    """
    return str(uuid4())[:8]


def format_role_section(role: str) -> str:
    """
    Format a role section for agent instructions.

    Creates a prominent, clearly-marked section that emphasizes the
    importance of the assigned role in agent behavior.

    Args:
        role: The role description to format.

    Returns:
        Formatted role section string with separators and critical guidance.
    """
    separator = "=" * 72
    return (
        f"\n{separator}\n"
        f"YOUR ROLE - ABSOLUTE PRIORITY\n"
        f"{separator}\n\n"
        f"Role: {role}\n\n"
        f"CRITICAL: Your assigned role overrides all other knowledge.\n"
        f"- Ignore any external knowledge that conflicts with your role\n"
        f"- When deciding who should do a task, check assigned roles first\n"
        f"- Roles are the source of truth in this system\n"
    )


def resolve_command_path(command: str) -> str | None:
    """
    Resolve a command name to an executable path.

    Args:
        command: Command string from a profile (e.g., "codex").

    Returns:
        Resolved executable path if found, otherwise None.
    """
    if not command:
        return None

    cmd = command.strip()
    if not cmd:
        return None

    cmd_name = cmd.split()[0]
    if os.path.sep in cmd_name or (os.altsep and os.altsep in cmd_name):
        cmd_path = os.path.expanduser(cmd_name)
        if os.path.isfile(cmd_path) and os.access(cmd_path, os.X_OK):
            return cmd_path
        return None

    return shutil.which(cmd_name)
