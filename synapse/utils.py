"""
Synapse A2A Utility Functions

This module provides common utility functions used across the codebase.
"""

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypeGuard
from uuid import uuid4


class RoleFileNotFoundError(Exception):
    """Raised when a role file reference points to a non-existent file."""

    pass


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


def extract_file_parts(parts: list[Any]) -> list[dict]:
    """Extract FilePart dicts from a mixed A2A parts list (dict/Pydantic both ok)."""

    def _to_dict(obj: Any) -> dict | None:
        if hasattr(obj, "model_dump"):
            try:
                dumped = obj.model_dump()
                return dumped if isinstance(dumped, dict) else None
            except Exception:
                return None
        if hasattr(obj, "dict"):
            try:
                dumped = obj.dict()
                return dumped if isinstance(dumped, dict) else None
            except Exception:
                return None
        return None

    file_parts: list[dict] = []
    for part in parts:
        if isinstance(part, dict):
            if part.get("type") == "file" and isinstance(part.get("file"), dict):
                file_parts.append(part)
            continue

        dumped = _to_dict(part)
        if (
            dumped
            and dumped.get("type") == "file"
            and isinstance(dumped.get("file"), dict)
        ):
            file_parts.append(dumped)
            continue

        if getattr(part, "type", None) != "file":
            continue

        file_obj = getattr(part, "file", None)
        if isinstance(file_obj, dict):
            file_parts.append({"type": "file", "file": file_obj})
            continue

        # Best-effort attribute extraction for Pydantic-like models.
        name = getattr(file_obj, "name", None) if file_obj is not None else None
        uri = getattr(file_obj, "uri", None) if file_obj is not None else None
        file_parts.append({"type": "file", "file": {"name": name, "uri": uri}})

    return file_parts


def format_file_parts_for_pty(file_parts: list[dict]) -> str:
    """Format FilePart dicts for PTY display."""
    if not file_parts:
        return ""

    lines: list[str] = ["[ATTACHMENTS]"]
    for part in file_parts:
        file_obj = part.get("file") if isinstance(part, dict) else None
        name = ""
        uri = ""
        if isinstance(file_obj, dict):
            name = str(file_obj.get("name", "") or "")
            uri = str(file_obj.get("uri", "") or "")
        lines.append(f"  - {name}: {uri}")
    return "\n".join(lines)


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


def format_skill_set_section(name: str, description: str, skills: list[str]) -> str:
    """
    Format a skill set section for agent instructions.

    Creates a section that informs the agent about its assigned skill set,
    including the set's purpose and which skills are included.

    Args:
        name: Skill set name (e.g., "architect").
        description: Human-readable description of the skill set.
        skills: List of skill names in the set.

    Returns:
        Formatted skill set section string.
    """
    separator = "=" * 72
    skills_list = "\n".join(f"  - {s}" for s in skills)
    return (
        f"\n{separator}\n"
        f"SKILL SET\n"
        f"{separator}\n\n"
        f"Active skill set: {name}\n"
        f"Purpose: {description}\n\n"
        f"Available skills:\n"
        f"{skills_list}\n\n"
        f"Use these skills to guide your work.\n"
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


# ============================================================================
# Role file reference functions
# ============================================================================


def is_role_file_reference(role: str | None) -> TypeGuard[str]:
    """
    Check if a role value is a file reference (starts with @).

    This is a TypeGuard that narrows role to str when True.

    Args:
        role: The role value to check.

    Returns:
        True if the role is a file reference (and role is str), False otherwise.
    """
    if not role or not isinstance(role, str):
        return False
    # Must start with @ followed by a non-whitespace character
    return role.startswith("@") and len(role) > 1 and not role[1].isspace()


def extract_role_file_path(role: str | None) -> str | None:
    """
    Extract the file path from a role file reference.

    Args:
        role: The role value (e.g., "@./roles/reviewer.md").

    Returns:
        The file path without the @ prefix, or None if not a file reference.
    """
    if not is_role_file_reference(role):
        return None
    return role[1:]  # Remove @ prefix


def resolve_role_value(
    role: str | None, agent_id: str, registry_dir: Path
) -> str | None:
    """
    Resolve a role value, copying file if it's a file reference.

    If role starts with @, the referenced file is copied to the registry's
    roles directory and the new path (with @ prefix) is returned.

    Args:
        role: The role value (string or @file reference).
        agent_id: The agent ID (used for naming the copied file).
        registry_dir: Path to the registry directory.

    Returns:
        The resolved role value:
        - Original string if not a file reference
        - "@{copied_path}" if file reference
        - None if role is None

    Raises:
        RoleFileNotFoundError: If the referenced file does not exist.
    """
    if role is None:
        return None

    if not is_role_file_reference(role):
        return role

    # Extract and expand the file path (role[1:] is safe here due to is_role_file_reference check)
    file_path_str = role[1:]  # Remove @ prefix
    file_path = Path(os.path.expanduser(file_path_str)).resolve()

    if not file_path.exists():
        raise RoleFileNotFoundError(f"Role file not found: {file_path}")

    # Create roles directory if needed
    roles_dir = registry_dir / "roles"
    roles_dir.mkdir(parents=True, exist_ok=True)

    # Copy file to registry with agent-specific name
    dest_path = roles_dir / f"{agent_id}-role.md"
    shutil.copy2(file_path, dest_path)

    return f"@{dest_path}"


def get_role_content(role: str | None) -> str | None:
    """
    Get the actual role content, reading from file if it's a reference.

    Args:
        role: The role value (string or @file reference).

    Returns:
        The role content as a string, or None if role is None.

    Raises:
        RoleFileNotFoundError: If the referenced file does not exist.
    """
    if role is None:
        return None

    if not is_role_file_reference(role):
        return role

    # Read from file (role[1:] is safe here due to is_role_file_reference check)
    file_path_str = role[1:]  # Remove @ prefix
    file_path = Path(os.path.expanduser(file_path_str))

    if not file_path.exists():
        raise RoleFileNotFoundError(f"Role file not found: {file_path}")

    return file_path.read_text(encoding="utf-8")


def get_role_display(role: str | None) -> str | None:
    """
    Get a display-friendly version of the role value.

    For file references, returns just the filename with @ prefix.
    For strings, returns as-is.

    Args:
        role: The role value (string or @file reference).

    Returns:
        Display-friendly role string, or None if role is None.
    """
    if role is None:
        return None

    if not is_role_file_reference(role):
        return role

    # Extract filename only for display
    file_path_str = role[1:]  # Remove @ prefix
    file_path = Path(file_path_str)
    return f"@{file_path.name}"
