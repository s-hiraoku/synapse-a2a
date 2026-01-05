"""
Synapse Settings Management

This module handles loading and merging settings from .synapse/settings.json files
across different scopes (user, project, local).

Scope priority (highest to lowest):
1. Local (.synapse/settings.local.json)
2. Project (.synapse/settings.json)
3. User (~/.synapse/settings.json)
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def get_default_instructions() -> str:
    """Get default bootstrap instructions with SKILL line."""
    return """[SYNAPSE INSTRUCTIONS - DO NOT EXECUTE - READ ONLY]
Agent: {{agent_id}} | Port: {{port}}

HOW TO RECEIVE A2A MESSAGES:
Input format: [A2A:task_id:sender_id] message
Response command: python3 synapse/tools/a2a.py send --target SENDER_ID YOUR_RESPONSE

HOW TO SEND MESSAGES TO OTHER AGENTS:
When user types @agent message, use: python3 synapse/tools/a2a.py send --target AGENT MESSAGE

AVAILABLE AGENTS: claude, gemini, codex
LIST COMMAND: python3 synapse/tools/a2a.py list

SKILL: For advanced A2A features, use synapse-a2a skill

TASK HISTORY (Enable with SYNAPSE_HISTORY_ENABLED=true):
  synapse history list [--agent <name>] [--limit <n>]    - List tasks
  synapse history search <keywords>                       - Search by keywords
  synapse history stats [--agent <name>]                  - View statistics
  synapse history export --format [json|csv] [--output <file>]  - Export data
  synapse history cleanup --days <n> [--force]            - Delete old tasks"""


def get_gemini_instructions() -> str:
    """Get Gemini-specific instructions without SKILL line."""
    return """[SYNAPSE INSTRUCTIONS - DO NOT EXECUTE - READ ONLY]
Agent: {{agent_id}} | Port: {{port}}

HOW TO RECEIVE A2A MESSAGES:
Input format: [A2A:task_id:sender_id] message
Response command: python3 synapse/tools/a2a.py send --target SENDER_ID YOUR_RESPONSE

HOW TO SEND MESSAGES TO OTHER AGENTS:
When user types @agent message, use: python3 synapse/tools/a2a.py send --target AGENT MESSAGE

AVAILABLE AGENTS: claude, gemini, codex
LIST COMMAND: python3 synapse/tools/a2a.py list

TASK HISTORY (Enable with SYNAPSE_HISTORY_ENABLED=true):
  synapse history list [--agent <name>] [--limit <n>]    - List tasks
  synapse history search <keywords>                       - Search by keywords
  synapse history stats [--agent <name>]                  - View statistics
  synapse history export --format [json|csv] [--output <file>]  - Export data
  synapse history cleanup --days <n> [--force]            - Delete old tasks"""


# Default settings template
DEFAULT_SETTINGS: dict[str, Any] = {
    "env": {
        "SYNAPSE_HISTORY_ENABLED": "false",
        "SYNAPSE_AUTH_ENABLED": "false",
        "SYNAPSE_API_KEYS": "",
        "SYNAPSE_ADMIN_KEY": "",
        "SYNAPSE_ALLOW_LOCALHOST": "true",
        "SYNAPSE_USE_HTTPS": "false",
        "SYNAPSE_WEBHOOK_SECRET": "",
        "SYNAPSE_WEBHOOK_TIMEOUT": "10",
        "SYNAPSE_WEBHOOK_MAX_RETRIES": "3",
    },
    "instructions": {
        "default": get_default_instructions(),
        "claude": "",
        "gemini": get_gemini_instructions(),
        "codex": "",
    },
}


def load_settings(path: Path) -> dict[str, Any]:
    """
    Load settings from a JSON file.

    Args:
        path: Path to the settings.json file.

    Returns:
        Parsed settings dict, or empty dict if file doesn't exist or is invalid.
    """
    if not path.exists():
        return {}

    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Failed to load settings from {path}: {e}")
        return {}


def merge_settings(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """
    Merge two settings dicts, with override taking precedence.

    Performs a shallow merge at the section level (env, instructions),
    then deep merge within each section.

    Args:
        base: Base settings (lower priority).
        override: Override settings (higher priority).

    Returns:
        Merged settings dict.
    """
    result: dict[str, Any] = {}

    # Get all keys from both dicts
    all_keys = set(base.keys()) | set(override.keys())

    for key in all_keys:
        base_value = base.get(key, {})
        override_value = override.get(key, {})

        if isinstance(base_value, dict) and isinstance(override_value, dict):
            # Deep merge for dict values
            result[key] = {**base_value, **override_value}
        elif key in override:
            # Override value takes precedence
            result[key] = override_value
        else:
            # Use base value
            result[key] = base_value

    return result


@dataclass
class SynapseSettings:
    """
    Synapse settings container.

    Manages environment variables and initial instructions
    loaded from .synapse/settings.json files.
    """

    env: dict[str, str] = field(default_factory=dict)
    instructions: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_defaults(cls) -> "SynapseSettings":
        """Create settings with default values."""
        return cls(
            env=dict(DEFAULT_SETTINGS["env"]),
            instructions=dict(DEFAULT_SETTINGS["instructions"]),
        )

    @classmethod
    def load(
        cls,
        user_path: Path | None = None,
        project_path: Path | None = None,
        local_path: Path | None = None,
    ) -> "SynapseSettings":
        """
        Load and merge settings from all scopes.

        Priority (highest to lowest):
        1. Local settings (project/.synapse/settings.local.json)
        2. Project settings (project/.synapse/settings.json)
        3. User settings (~/.synapse/settings.json)
        4. Default settings

        Args:
            user_path: Path to user settings (default: ~/.synapse/settings.json)
            project_path: Path to project settings (default: ./.synapse/settings.json)
            local_path: Path to local settings (default: ./.synapse/settings.local.json)

        Returns:
            Merged SynapseSettings instance.
        """
        # Default paths
        if user_path is None:
            user_path = Path.home() / ".synapse" / "settings.json"
        if project_path is None:
            project_path = Path.cwd() / ".synapse" / "settings.json"
        if local_path is None:
            local_path = Path.cwd() / ".synapse" / "settings.local.json"

        # Start with defaults
        merged = dict(DEFAULT_SETTINGS)

        # Merge user settings (lowest priority)
        user_settings = load_settings(user_path)
        if user_settings:
            merged = merge_settings(merged, user_settings)
            logger.debug(f"Loaded user settings from {user_path}")

        # Merge project settings
        project_settings = load_settings(project_path)
        if project_settings:
            merged = merge_settings(merged, project_settings)
            logger.debug(f"Loaded project settings from {project_path}")

        # Merge local settings (highest priority)
        local_settings = load_settings(local_path)
        if local_settings:
            merged = merge_settings(merged, local_settings)
            logger.debug(f"Loaded local settings from {local_path}")

        return cls(
            env=merged.get("env", {}),
            instructions=merged.get("instructions", {}),
        )

    def get_instruction(
        self, agent_type: str, agent_id: str, port: int
    ) -> str | None:
        """
        Get the instruction for a specific agent type.

        Resolution order:
        1. Agent-specific instruction (if non-empty)
        2. Default instruction (if non-empty)
        3. None (no instruction)

        Args:
            agent_type: The agent type (claude, gemini, codex).
            agent_id: The agent ID for placeholder replacement.
            port: The port number for placeholder replacement.

        Returns:
            The instruction string with placeholders replaced, or None.
        """
        # Try agent-specific first
        instruction = self.instructions.get(agent_type, "")

        # Fall back to default
        if not instruction:
            instruction = self.instructions.get("default", "")

        # Return None if empty
        if not instruction:
            return None

        # Replace placeholders
        instruction = instruction.replace("{{agent_id}}", agent_id)
        instruction = instruction.replace("{{port}}", str(port))

        return instruction

    def apply_env(self, env: dict[str, str]) -> dict[str, str]:
        """
        Apply settings env to an environment dict.

        Only sets values that are non-empty and not already set in env.

        Args:
            env: The environment dict to update.

        Returns:
            The updated environment dict.
        """
        for key, value in self.env.items():
            # Only set non-empty values that aren't already set
            if value and key not in env:
                env[key] = value
        return env


def get_settings() -> SynapseSettings:
    """
    Get the current settings, loading from all scopes.

    This is a convenience function that creates a new SynapseSettings
    instance with the default paths.

    Returns:
        SynapseSettings instance with merged settings.
    """
    return SynapseSettings.load()
