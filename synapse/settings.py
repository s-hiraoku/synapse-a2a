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
        "SYNAPSE_FILE_SAFETY_ENABLED": "false",
        "SYNAPSE_FILE_SAFETY_RETENTION_DAYS": "30",
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
    "delegation": {
        "mode": "off",  # "orchestrator" | "passthrough" | "off"
    },
    "resume_flags": {
        # Flags that indicate context resume (skip initial instructions)
        # Customize per agent in .synapse/settings.json
        "claude": ["--continue", "--resume", "-c"],
        "codex": [],  # Add flags when confirmed
        "gemini": [],  # Add flags when confirmed
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
            data = json.load(f)
            if isinstance(data, dict):
                return dict(data)
            return {}
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

    Manages environment variables, initial instructions, and delegation settings
    loaded from .synapse/settings.json files.
    """

    env: dict[str, str] = field(default_factory=dict)
    instructions: dict[str, str] = field(default_factory=dict)
    delegation: dict[str, str] = field(default_factory=dict)
    resume_flags: dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def from_defaults(cls) -> "SynapseSettings":
        """Create settings with default values."""
        return cls(
            env=dict(DEFAULT_SETTINGS["env"]),
            instructions=dict(DEFAULT_SETTINGS["instructions"]),
            delegation=dict(DEFAULT_SETTINGS["delegation"]),
            resume_flags=dict(DEFAULT_SETTINGS["resume_flags"]),
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
            delegation=merged.get("delegation", {}),
            resume_flags=merged.get("resume_flags", {}),
        )

    def get_instruction(self, agent_type: str, agent_id: str, port: int) -> str | None:
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

        Note:
            Delegation rules should be manually included in the instructions
            section of .synapse/settings.json if needed. This function only
            handles placeholder replacement ({{agent_id}}, {{port}}).

            To enable delegation, configure both:
            1. .synapse/settings.json: {"delegation": {"mode": "orchestrator"}}
            2. Include delegation rules in the "instructions" section

        Supported instruction formats:
            - String: "line1\\nline2" (escaped newlines)
            - Array: ["line1", "line2"] (joined with newlines, easier to read)
            - Filename: "default.md" (loads from .synapse/<filename>)
        """

        # Try agent-specific first
        instruction = self.instructions.get(agent_type, "")

        # Fall back to default
        if not instruction:
            instruction = self.instructions.get("default", "")

        # Handle array format: join with newlines
        if isinstance(instruction, list):
            instruction = "\n".join(instruction)

        # Handle file reference: load from .synapse/<filename>
        if isinstance(instruction, str) and instruction.endswith(".md"):
            instruction = self._load_instruction_file(instruction)

        # Return None if empty
        if not instruction:
            return None

        # Append file-safety instructions if enabled
        instruction = self._append_optional_instructions(instruction)

        # Replace placeholders
        instruction = instruction.replace("{{agent_id}}", agent_id)
        instruction = instruction.replace("{{port}}", str(port))

        return instruction

    def get_instruction_files(self, agent_type: str) -> list[str]:
        """
        Get the list of instruction files to read for a specific agent type.

        Returns paths relative to .synapse/ directory. The agent should read
        these files in order to get full instructions.

        Resolution order:
        1. Agent-specific file (if configured and exists)
        2. Default file (if configured and exists)
        3. Optional files based on settings (e.g., file-safety.md)

        Args:
            agent_type: The agent type (claude, gemini, codex).

        Returns:
            List of file paths relative to .synapse/ (e.g., ["default.md", "file-safety.md"])
        """
        import os

        files: list[str] = []

        # Check agent-specific file
        agent_instruction = self.instructions.get(agent_type, "")
        if (
            agent_instruction
            and isinstance(agent_instruction, str)
            and agent_instruction.endswith(".md")
            and self._instruction_file_exists(agent_instruction)
        ):
            files.append(agent_instruction)

        # Check default file (only if agent-specific is not set)
        if not agent_instruction:
            default_instruction = self.instructions.get("default", "")
            if (
                default_instruction
                and isinstance(default_instruction, str)
                and default_instruction.endswith(".md")
                and self._instruction_file_exists(default_instruction)
            ):
                files.append(default_instruction)

        # Add optional files based on settings

        # Delegation (when mode is orchestrator or passthrough)
        delegation_mode = self.get_delegation_mode()
        if delegation_mode in (
            "orchestrator",
            "passthrough",
        ) and self._instruction_file_exists("delegate.md"):
            files.append("delegate.md")

        # File safety
        file_safety_enabled = os.environ.get("SYNAPSE_FILE_SAFETY_ENABLED", "").lower()
        if not file_safety_enabled:
            file_safety_enabled = self.env.get(
                "SYNAPSE_FILE_SAFETY_ENABLED", "false"
            ).lower()

        if file_safety_enabled in ("true", "1") and self._instruction_file_exists(
            "file-safety.md"
        ):
            files.append("file-safety.md")

        return files

    def _instruction_file_exists(self, filename: str) -> bool:
        """Check if an instruction file exists in .synapse directory."""
        from pathlib import Path

        project_path = Path.cwd() / ".synapse" / filename
        user_path = Path.home() / ".synapse" / filename

        return project_path.exists() or user_path.exists()

    def _append_optional_instructions(self, instruction: str) -> str:
        """
        Append optional instruction files based on environment variables or settings.

        Currently supports:
        - SYNAPSE_FILE_SAFETY_ENABLED=true: appends .synapse/file-safety.md

        Priority: Environment variable > settings.json > default (false)

        Args:
            instruction: The base instruction string.

        Returns:
            Instruction with optional content appended.
        """
        import os

        # Check file safety enabled (env var takes priority over settings)
        file_safety_enabled = os.environ.get("SYNAPSE_FILE_SAFETY_ENABLED", "").lower()
        if not file_safety_enabled:
            # Fall back to settings.json
            file_safety_enabled = self.env.get(
                "SYNAPSE_FILE_SAFETY_ENABLED", "false"
            ).lower()

        if file_safety_enabled in ("true", "1"):
            file_safety_content = self._load_instruction_file("file-safety.md")
            if file_safety_content:
                instruction = instruction + "\n\n" + file_safety_content

        return instruction

    def _load_instruction_file(self, filename: str) -> str:
        """
        Load instruction content from a file in .synapse directory.

        Search order:
        1. Project: .synapse/<filename>
        2. User: ~/.synapse/<filename>

        Args:
            filename: The filename to load (e.g., "default.md")

        Returns:
            File content if found, empty string otherwise.
        """
        from pathlib import Path

        project_path = Path.cwd() / ".synapse" / filename
        user_path = Path.home() / ".synapse" / filename

        for path in [project_path, user_path]:
            if path.exists():
                try:
                    return path.read_text(encoding="utf-8")
                except OSError:
                    continue

        return ""

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

    def get_delegation_mode(self) -> str:
        """
        Get the delegation mode.

        Returns:
            Delegation mode: "orchestrator", "passthrough", or "off"
        """
        return self.delegation.get("mode", "off")

    def get_resume_flags(self, agent_type: str) -> list[str]:
        """
        Get resume flags for a specific agent type.

        These flags indicate that the agent is resuming a previous session
        and should skip initial instructions.

        Args:
            agent_type: The agent type (claude, gemini, codex).

        Returns:
            List of CLI flags that indicate resume mode.
        """
        flags = self.resume_flags.get(agent_type, [])
        if isinstance(flags, list):
            return flags
        return []

    def is_resume_mode(self, agent_type: str, tool_args: list[str]) -> bool:
        """
        Check if tool arguments contain any resume flag for the agent type.

        Args:
            agent_type: The agent type (claude, gemini, codex).
            tool_args: List of arguments passed to the CLI tool.

        Returns:
            True if any resume flag is present in tool_args.
        """
        flags = set(self.get_resume_flags(agent_type))
        if not flags:
            return False
        return bool(flags & set(tool_args))


def get_settings() -> SynapseSettings:
    """
    Get the current settings, loading from all scopes.

    This is a convenience function that creates a new SynapseSettings
    instance with the default paths.

    Returns:
        SynapseSettings instance with merged settings.
    """
    return SynapseSettings.load()
