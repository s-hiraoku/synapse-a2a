"""
Delegation Configuration Management

This module manages delegation settings for automatic task routing
between agents (Claude, Codex, Gemini).

Configuration:
- Mode: Stored in .synapse/settings.json under "delegation" section
- Instructions: Read from .synapse/delegate.md (project) or ~/.synapse/delegate.md (user)
"""

from pathlib import Path
from typing import Literal

DelegationMode = Literal["orchestrator", "passthrough", "off"]

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


def build_delegation_instructions(mode: DelegationMode, rules: str) -> str:
    """
    Build delegation instructions to inject into agent context.

    Args:
        mode: Delegation mode (orchestrator/passthrough)
        rules: Delegation rules from delegate.md

    Returns:
        Formatted instructions string
    """
    if mode == "off" or not rules:
        return ""

    mode_desc = {
        "orchestrator": "分析・統合型 - タスクを分析し、適切なエージェントに委任し、結果を統合して報告",
        "passthrough": "単純転送型 - ルールに従って直接転送し、結果をそのまま返す",
    }

    return f"""## Delegation Rules (Mode: {mode})

{rules}

### Mode Description
{mode_desc.get(mode, "")}

### Action Instructions
- Analyze each incoming task against the rules above
- For tasks matching a delegation rule, use @agent pattern to send
- For orchestrator mode: wait for response, integrate results, then report to user
- For passthrough mode: forward directly and relay response as-is
- For tasks not matching any rule: process directly yourself
"""
