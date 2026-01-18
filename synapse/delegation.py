"""
Delegation Configuration Management

This module manages delegation settings for automatic task routing
between agents (Claude, Codex, Gemini).

Configuration:
- Enabled: Stored in .synapse/settings.json under "delegation.enabled"
- Instructions: Read from .synapse/delegate.md or ~/.synapse/delegate.md
"""

from pathlib import Path

# Delegate instruction file name
DELEGATE_MD_NAME = "delegate.md"


def load_delegate_instructions(
    project_path: Path | None = None,
    user_path: Path | None = None,
) -> str | None:
    """
    Load delegation instructions from delegate.md file.

    Search order:
    1. Project: .synapse/delegate.md
    2. User: ~/.synapse/delegate.md

    Args:
        project_path: Override project delegate.md path
        user_path: Override user delegate.md path

    Returns:
        Instructions content if found, None otherwise
    """
    # Default paths
    if project_path is None:
        project_path = Path.cwd() / ".synapse" / DELEGATE_MD_NAME
    if user_path is None:
        user_path = Path.home() / ".synapse" / DELEGATE_MD_NAME

    # Try project first
    for path in [project_path, user_path]:
        if path.exists():
            try:
                content = path.read_text(encoding="utf-8").strip()
                if content:
                    return content
            except OSError:
                continue

    return None


def get_delegate_instructions_path() -> str | None:
    """
    Get the path of the active delegate.md file.

    Returns:
        Path string if found, None otherwise
    """
    project_path = Path.cwd() / ".synapse" / DELEGATE_MD_NAME
    user_path = Path.home() / ".synapse" / DELEGATE_MD_NAME

    if project_path.exists():
        return str(project_path)
    if user_path.exists():
        return str(user_path)

    return None


def build_delegation_instructions(rules: str) -> str:
    """
    Build delegation instructions to inject into agent context.

    Note: This function is called only when delegation is enabled
    (delegation.enabled = true in settings.json).

    Args:
        rules: Delegation rules from delegate.md

    Returns:
        Formatted instructions string
    """
    if not rules:
        return ""

    return f"""## Delegation Rules

{rules}

### Action Instructions
- Analyze each incoming task against the rules above
- For tasks matching a delegation rule, use @agent pattern to send
- Use --response flag when you need to integrate results
- Use --no-response flag for fire-and-forget delegation
- For tasks not matching any rule: process directly yourself
"""
