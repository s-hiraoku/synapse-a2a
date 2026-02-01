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
Agent: {{agent_name}} | Port: {{port}} | ID: {{agent_id}}

HOW TO RECEIVE A2A MESSAGES:
Input format: [A2A:task_id:sender_id] message
Response command: synapse send SENDER_ID "YOUR_RESPONSE" --from {{agent_id}}

HOW TO SEND MESSAGES TO OTHER AGENTS:
Use: synapse send <AGENT> "<MESSAGE>" --from {{agent_id}}

AVAILABLE AGENTS: claude, gemini, codex
LIST COMMAND: synapse list

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
Agent: {{agent_name}} | Port: {{port}} | ID: {{agent_id}}

HOW TO RECEIVE A2A MESSAGES:
Input format: [A2A:task_id:sender_id] message
Response command: synapse send SENDER_ID "YOUR_RESPONSE" --from {{agent_id}}

HOW TO SEND MESSAGES TO OTHER AGENTS:
Use: synapse send <AGENT> "<MESSAGE>" --from {{agent_id}}

AVAILABLE AGENTS: claude, gemini, codex
LIST COMMAND: synapse list

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
    "approvalMode": "required",  # "auto" | "required"
    "a2a": {
        "flow": "auto",  # "roundtrip" | "oneway" | "auto"
    },
    "delegation": {
        "enabled": False,
    },
    "resume_flags": {
        # Flags that indicate context resume (skip initial instructions)
        # Customize per agent in .synapse/settings.json
        "claude": ["--continue", "--resume", "-c", "-r"],
        "codex": ["resume"],  # codex resume [--last | <SESSION_ID>]
        "gemini": ["--resume", "-r"],  # gemini --resume/-r [<index|UUID>]
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
    approval_mode: str = field(default_factory=lambda: "required")
    a2a: dict[str, str] = field(default_factory=dict)
    delegation: dict[str, Any] = field(default_factory=dict)
    resume_flags: dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def from_defaults(cls) -> "SynapseSettings":
        """Create settings with default values."""
        return cls(
            env=dict(DEFAULT_SETTINGS["env"]),
            instructions=dict(DEFAULT_SETTINGS["instructions"]),
            approval_mode=DEFAULT_SETTINGS["approvalMode"],
            a2a=dict(DEFAULT_SETTINGS["a2a"]),
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
            approval_mode=merged.get("approvalMode", "required"),
            a2a=merged.get("a2a", {}),
            delegation=merged.get("delegation", {}),
            resume_flags=merged.get("resume_flags", {}),
        )

    def get_instruction(
        self,
        agent_type: str,
        agent_id: str,
        port: int,
        name: str | None = None,
        role: str | None = None,
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
            name: Optional custom name for the agent (used in {{agent_name}}).
            role: Optional role description for the agent (used in {{agent_role}}).

        Returns:
            The instruction string with placeholders replaced, or None.

        Note:
            Delegation rules should be manually included in the instructions
            section of .synapse/settings.json if needed. This function only
            handles placeholder replacement ({{agent_id}}, {{port}}, etc.).

            To enable delegation, configure:
            .synapse/settings.json: {"delegation": {"enabled": true}}

        Supported instruction formats:
            - String: "line1\\nline2" (escaped newlines)
            - Array: ["line1", "line2"] (joined with newlines, easier to read)
            - Filename: "default.md" (loads from .synapse/<filename>)

        Placeholders:
            - {{agent_id}}: The internal agent ID (e.g., synapse-claude-8100)
            - {{agent_name}}: Custom name if set, otherwise falls back to agent_id
            - {{agent_role}}: Role description if set, otherwise empty string
            - {{port}}: The port number
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
        # agent_name defaults to agent_id if not set (for display purposes)
        display_name = name if name else agent_id
        display_role = role if role else ""

        instruction = instruction.replace("{{agent_name}}", display_name)
        instruction = instruction.replace("{{agent_role}}", display_role)
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
            List of file paths relative to .synapse/ (e.g., ["default.md"])
        """
        files: list[str] = []

        # Check agent-specific file
        agent_instruction = self.instructions.get(agent_type, "")
        if self._is_valid_md_file(agent_instruction):
            files.append(agent_instruction)

        # Check default file (only if agent-specific is not set)
        if not agent_instruction:
            default_instruction = self.instructions.get("default", "")
            if self._is_valid_md_file(default_instruction):
                files.append(default_instruction)

        # Add optional files based on settings

        # Delegation (when enabled)
        if self.is_delegation_enabled() and self._instruction_file_exists(
            "delegate.md"
        ):
            files.append("delegate.md")

        # File safety
        if self._is_file_safety_enabled() and self._instruction_file_exists(
            "file-safety.md"
        ):
            files.append("file-safety.md")

        return files

    def get_instruction_file_paths(
        self, agent_type: str, user_dir: Path | None = None
    ) -> list[str]:
        """
        Get the list of instruction file paths with correct directory prefixes.

        Unlike get_instruction_files() which returns just filenames, this method
        returns display paths that correctly indicate whether the file is in the
        project directory (.synapse/) or user directory (~/.synapse/).

        Args:
            agent_type: The agent type (claude, gemini, codex).
            user_dir: Optional custom user directory for testing (default: Path.home()).

        Returns:
            List of display paths (e.g., [".synapse/default.md", "~/.synapse/delegate.md"])
        """
        paths: list[str] = []
        home = user_dir if user_dir else Path.home()

        # Helper to check if file exists with custom user_dir
        def file_exists(filename: str) -> bool:
            project_path = Path.cwd() / ".synapse" / filename
            user_path = home / ".synapse" / filename
            return project_path.exists() or user_path.exists()

        # Check agent-specific file
        agent_instruction = self.instructions.get(agent_type, "")
        if (
            isinstance(agent_instruction, str)
            and agent_instruction.endswith(".md")
            and file_exists(agent_instruction)
        ):
            display_path = self._get_file_display_path(agent_instruction, user_dir)
            if display_path:
                paths.append(display_path)

        # Check default file (only if agent-specific is not set)
        if not agent_instruction:
            default_instruction = self.instructions.get("default", "")
            if (
                isinstance(default_instruction, str)
                and default_instruction.endswith(".md")
                and file_exists(default_instruction)
            ):
                display_path = self._get_file_display_path(
                    default_instruction, user_dir
                )
                if display_path:
                    paths.append(display_path)

        # Delegation (when enabled)
        if self.is_delegation_enabled() and file_exists("delegate.md"):
            display_path = self._get_file_display_path("delegate.md", user_dir)
            if display_path:
                paths.append(display_path)

        # File safety
        if self._is_file_safety_enabled() and file_exists("file-safety.md"):
            display_path = self._get_file_display_path("file-safety.md", user_dir)
            if display_path:
                paths.append(display_path)

        return paths

    def _get_file_display_path(
        self, filename: str, user_dir: Path | None = None
    ) -> str | None:
        """
        Get the display path for an instruction file.

        Checks if the file exists in project or user directory and returns
        the appropriate display path.

        Args:
            filename: The filename to check (e.g., "default.md")
            user_dir: Optional custom user directory for testing.

        Returns:
            Display path like ".synapse/default.md" or "~/.synapse/default.md",
            or None if file doesn't exist in either location.
        """
        project_path = Path.cwd() / ".synapse" / filename
        home = user_dir if user_dir else Path.home()
        user_path = home / ".synapse" / filename

        # Project directory takes precedence
        if project_path.exists():
            return f".synapse/{filename}"

        if user_path.exists():
            return f"~/.synapse/{filename}"

        return None

    def _is_valid_md_file(self, instruction: object) -> bool:
        """Check if instruction is a valid .md filename that exists."""
        return (
            isinstance(instruction, str)
            and instruction.endswith(".md")
            and self._instruction_file_exists(instruction)
        )

    def _is_file_safety_enabled(self) -> bool:
        """Check if file safety is enabled via env var or settings."""
        import os

        file_safety_enabled = os.environ.get("SYNAPSE_FILE_SAFETY_ENABLED", "").lower()
        if not file_safety_enabled:
            file_safety_enabled = self.env.get(
                "SYNAPSE_FILE_SAFETY_ENABLED", "false"
            ).lower()
        return file_safety_enabled in ("true", "1")

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
        if self._is_file_safety_enabled():
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

    def get_a2a_flow(self) -> str:
        """
        Get the A2A communication flow mode.

        Returns:
            Flow mode: "roundtrip", "oneway", or "auto"
        """
        return self.a2a.get("flow", "auto")

    def is_delegation_enabled(self) -> bool:
        """
        Check if delegation is enabled.

        Returns:
            True if delegation is enabled, False otherwise.
        """
        return bool(self.delegation.get("enabled", False))

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

        Supports both exact matches (e.g., "--resume") and value forms
        (e.g., "--resume=<id>", "--resume=abc123").

        Args:
            agent_type: The agent type (claude, gemini, codex).
            tool_args: List of arguments passed to the CLI tool.

        Returns:
            True if any resume flag is present in tool_args.
        """
        flags = self.get_resume_flags(agent_type)
        if not flags:
            return False

        for arg in tool_args:
            for flag in flags:
                # Exact match (e.g., "--resume" matches "--resume")
                if arg == flag:
                    return True
                # Value form match (e.g., "--resume=abc" matches "--resume")
                # Only for flags starting with "-" (not positional like "resume")
                if flag.startswith("-") and arg.startswith(flag + "="):
                    return True
        return False

    def get_approval_mode(self) -> str:
        """
        Get the approval mode setting.

        Returns:
            Approval mode: "auto" (no confirmation) or "required" (show prompt).
            Invalid values fall back to "required".
        """
        if self.approval_mode in ("auto", "required"):
            return self.approval_mode
        return "required"

    def should_require_approval(self) -> bool:
        """
        Determine if approval is required.

        Returns:
            True if user approval is required before sending messages.
        """
        return self.get_approval_mode() == "required"


def get_settings() -> SynapseSettings:
    """
    Get the current settings, loading from all scopes.

    This is a convenience function that creates a new SynapseSettings
    instance with the default paths.

    Returns:
        SynapseSettings instance with merged settings.
    """
    return SynapseSettings.load()
