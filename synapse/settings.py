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
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from synapse.utils import RoleFileNotFoundError, get_role_content

logger = logging.getLogger(__name__)


def get_default_instructions() -> str:
    """Get default bootstrap instructions with SKILL line."""
    return """[SYNAPSE INSTRUCTIONS - DO NOT EXECUTE - READ ONLY]
Agent: {{agent_name}} | Port: {{port}} | ID: {{agent_id}}

HOW TO RECEIVE A2A MESSAGES:
Input format: A2A: [From: NAME (SENDER_ID)] message
Response command: synapse send SENDER_ID "YOUR_RESPONSE" --from {{agent_id}}

HOW TO SEND MESSAGES TO OTHER AGENTS:
Use: synapse send <AGENT> "<MESSAGE>" --from {{agent_id}}

AVAILABLE AGENTS: claude, gemini, codex
LIST COMMAND: synapse list

SKILL: For advanced A2A features, use synapse-a2a skill

FILE SAFETY (Multi-Agent Coordination):
- Before editing ANY file, check: synapse file-safety locks
- If another agent has lock, WAIT or coordinate with them
- Lock before edit: synapse file-safety lock <file> {{agent_id}}
- Unlock after edit: synapse file-safety unlock <file> {{agent_id}}

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
Input format: A2A: [From: NAME (SENDER_ID)] message
Response command: synapse send SENDER_ID "YOUR_RESPONSE" --from {{agent_id}}

HOW TO SEND MESSAGES TO OTHER AGENTS:
Use: synapse send <AGENT> "<MESSAGE>" --from {{agent_id}}

AVAILABLE AGENTS: claude, gemini, codex
LIST COMMAND: synapse list

FILE SAFETY (Multi-Agent Coordination):
- Before editing ANY file, check: synapse file-safety locks
- If another agent has lock, WAIT or coordinate with them
- Lock before edit: synapse file-safety lock <file> {{agent_id}}
- Unlock after edit: synapse file-safety unlock <file> {{agent_id}}

TASK HISTORY (Enable with SYNAPSE_HISTORY_ENABLED=true):
  synapse history list [--agent <name>] [--limit <n>]    - List tasks
  synapse history search <keywords>                       - Search by keywords
  synapse history stats [--agent <name>]                  - View statistics
  synapse history export --format [json|csv] [--output <file>]  - Export data
  synapse history cleanup --days <n> [--force]            - Delete old tasks"""


# Default settings template
DEFAULT_SETTINGS: dict[str, Any] = {
    "env": {
        "SYNAPSE_HISTORY_ENABLED": "true",
        "SYNAPSE_FILE_SAFETY_ENABLED": "true",
        "SYNAPSE_FILE_SAFETY_DB_PATH": ".synapse/file_safety.db",
        "SYNAPSE_FILE_SAFETY_RETENTION_DAYS": "30",
        "SYNAPSE_AUTH_ENABLED": "false",
        "SYNAPSE_API_KEYS": "",
        "SYNAPSE_ADMIN_KEY": "",
        "SYNAPSE_ALLOW_LOCALHOST": "true",
        "SYNAPSE_USE_HTTPS": "false",
        "SYNAPSE_WEBHOOK_SECRET": "",
        "SYNAPSE_WEBHOOK_TIMEOUT": "10",
        "SYNAPSE_WEBHOOK_MAX_RETRIES": "3",
        # Long message file storage settings
        # Messages exceeding threshold are stored in files instead of PTY paste
        "SYNAPSE_LONG_MESSAGE_THRESHOLD": "200",  # Character count (TUI limit ~200-300)
        "SYNAPSE_LONG_MESSAGE_TTL": "3600",  # File retention in seconds (1 hour)
        "SYNAPSE_LONG_MESSAGE_DIR": "",  # Default: /tmp/synapse-a2a/messages/
        # Task board settings
        "SYNAPSE_TASK_BOARD_ENABLED": "true",
        "SYNAPSE_TASK_BOARD_DB_PATH": ".synapse/task_board.db",
        # Shared memory settings
        "SYNAPSE_SHARED_MEMORY_ENABLED": "true",
        "SYNAPSE_SHARED_MEMORY_DB_PATH": ".synapse/memory.db",
        # Learning mode settings
        "SYNAPSE_LEARNING_MODE_ENABLED": "false",
        "SYNAPSE_LEARNING_MODE_TRANSLATION": "false",
        # Proactive mode settings
        "SYNAPSE_PROACTIVE_MODE_ENABLED": "false",
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
    "resume_flags": {
        # Flags that indicate context resume (skip initial instructions)
        # Customize per agent in .synapse/settings.json
        "claude": ["--continue", "--resume", "-c", "-r"],
        "codex": ["resume"],  # codex resume [--last | <SESSION_ID>]
        "gemini": ["--resume", "-r"],  # gemini --resume/-r [<index|UUID>]
    },
    "list": {
        # Columns to display in synapse list command
        # Available: ID, NAME, TYPE, ROLE, STATUS, CURRENT, TRANSPORT,
        #            WORKING_DIR, EDITING_FILE (requires file-safety enabled)
        "columns": [
            "ID",
            "NAME",
            "STATUS",
            "CURRENT",
            "TRANSPORT",
            "WORKING_DIR",
            "EDITING_FILE",
        ],
    },
    "shutdown": {
        "timeout_seconds": 30,
        "graceful_enabled": True,
    },
    "delegate_mode": {
        "deny_file_locks": True,
        "instruction_template": (
            "\n\n[MANAGER MODE]\n"
            "You are a manager. Do NOT edit files directly.\n"
            "Instead, use `synapse send` to delegate tasks to other agents.\n"
            "Focus on: task analysis, splitting, assignment, and review.\n"
            "Use `synapse list` to check agent availability.\n"
            "Use `synapse tasks` to manage the shared task board."
        ),
    },
    "hooks": {
        "on_idle": "",
        "on_task_completed": "",
    },
}

# Known top-level settings keys for validation
KNOWN_SETTINGS_KEYS: set[str] = {
    "env",
    "instructions",
    "approvalMode",
    "a2a",
    "resume_flags",
    "list",
    "shutdown",
    "delegate_mode",
    "hooks",
    "skill_sets",
}

# Deprecated settings keys with migration messages
DEPRECATED_SETTINGS_KEYS: dict[str, str] = {
    "delegation": (
        "The 'delegation' setting was removed in v0.3.19. "
        "Use 'synapse send' for inter-agent communication. "
        "You can safely remove this key from your settings."
    ),
}


def _warn_unknown_keys(settings: dict[str, Any], path: Path) -> None:
    """
    Log warnings for unknown top-level settings keys.

    Deprecated keys get a specific migration message.
    Unknown keys get a generic warning with known keys listed.

    Args:
        settings: The loaded settings dictionary.
        path: Path to the settings file (for log message).
    """
    unknown_keys = set(settings.keys()) - KNOWN_SETTINGS_KEYS
    for key in sorted(unknown_keys):
        if key in DEPRECATED_SETTINGS_KEYS:
            logger.warning(
                f"Deprecated settings key '{key}' in {path}: "
                f"{DEPRECATED_SETTINGS_KEYS[key]}"
            )
        else:
            logger.warning(
                f"Unknown settings key '{key}' in {path}. "
                f"Known keys: {', '.join(sorted(KNOWN_SETTINGS_KEYS))}"
            )


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
                result = dict(data)
                _warn_unknown_keys(result, path)
                return result
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

    Manages environment variables, initial instructions, and other settings
    loaded from .synapse/settings.json files.
    """

    env: dict[str, str] = field(default_factory=dict)
    instructions: dict[str, str] = field(default_factory=dict)
    approval_mode: str = field(default_factory=lambda: "required")
    a2a: dict[str, str] = field(default_factory=dict)
    resume_flags: dict[str, list[str]] = field(default_factory=dict)
    list_config: dict[str, Any] = field(default_factory=dict)
    shutdown_config: dict[str, Any] = field(default_factory=dict)
    delegate_mode_config: dict[str, Any] = field(default_factory=dict)
    hooks_config: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_defaults(cls) -> "SynapseSettings":
        """Create settings with default values."""
        return cls(
            env=dict(DEFAULT_SETTINGS["env"]),
            instructions=dict(DEFAULT_SETTINGS["instructions"]),
            approval_mode=DEFAULT_SETTINGS["approvalMode"],
            a2a=dict(DEFAULT_SETTINGS["a2a"]),
            resume_flags=dict(DEFAULT_SETTINGS["resume_flags"]),
            list_config=dict(DEFAULT_SETTINGS["list"]),
            shutdown_config=dict(DEFAULT_SETTINGS["shutdown"]),
            delegate_mode_config=dict(DEFAULT_SETTINGS["delegate_mode"]),
            hooks_config=dict(DEFAULT_SETTINGS["hooks"]),
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
            resume_flags=merged.get("resume_flags", {}),
            list_config=merged.get("list", {}),
            shutdown_config=merged.get("shutdown", {}),
            delegate_mode_config=merged.get("delegate_mode", {}),
            hooks_config=merged.get("hooks", {}),
        )

    def get_instruction(
        self,
        agent_type: str,
        agent_id: str,
        port: int,
        name: str | None = None,
        role: str | None = None,
    ) -> str | None:
        """Get the full instruction for a specific agent type."""
        return self._resolve_instruction(
            agent_type=agent_type,
            agent_id=agent_id,
            port=port,
            name=name,
            role=role,
            include_optional=True,
        )

    def get_static_instruction_resource(
        self,
        agent_type: str,
        *,
        agent_id: str = "current-agent",
        port: int = 0,
        name: str = "current agent",
    ) -> str | None:
        """Get a static instruction document suitable for MCP resources."""
        return self._resolve_instruction(
            agent_type=agent_type,
            agent_id=agent_id,
            port=port,
            name=name,
            role=None,
            include_optional=False,
        )

    def _resolve_instruction(
        self,
        agent_type: str,
        agent_id: str,
        port: int,
        name: str | None = None,
        role: str | None = None,
        include_optional: bool = True,
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

        if include_optional:
            instruction = self._append_optional_instructions(instruction)

        # Replace placeholders
        # agent_name defaults to agent_id if not set (for display purposes)
        display_name = name if name else agent_id
        # Role may be a string or @file reference - get_role_content handles both
        role_content: str | None = None
        if role:
            try:
                role_content = get_role_content(role)
            except RoleFileNotFoundError:
                logger.warning(f"Role file not found: {role}")
                role_content = None
        display_role = role_content if role_content else ""

        # Process conditional sections: {{#var}}content{{/var}}
        # If var is truthy, include content; otherwise remove entire section
        instruction = self._process_conditional_sections(
            instruction,
            {
                "agent_role": display_role,
                "learning_mode": "enabled" if self._is_learning_mode_enabled() else "",
                "learning_translation": "enabled"
                if self._is_learning_translation_enabled()
                else "",
            },
        )

        instruction = instruction.replace("{{agent_name}}", display_name)
        instruction = instruction.replace("{{agent_role}}", display_role)
        instruction = instruction.replace("{{agent_id}}", agent_id)
        instruction = instruction.replace("{{port}}", str(port))

        return instruction

    def get_instruction_file_content(
        self,
        filename: str,
        *,
        user_dir: Path | None = None,
        agent_id: str = "current-agent",
        port: int = 0,
    ) -> str:
        """Load a specific instruction file from project or user scope."""
        content = self._load_instruction_file(filename, user_dir=user_dir)
        if not content:
            return ""
        return content.replace("{{agent_id}}", agent_id).replace("{{port}}", str(port))

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

        # File safety
        if self._is_file_safety_enabled() and self._instruction_file_exists(
            "file-safety.md"
        ):
            files.append("file-safety.md")

        # Learning mode (either flag enables learning.md injection)
        if self._is_any_learning_enabled() and self._instruction_file_exists(
            "learning.md"
        ):
            files.append("learning.md")

        # Shared memory
        if self._is_shared_memory_enabled() and self._instruction_file_exists(
            "shared-memory.md"
        ):
            files.append("shared-memory.md")

        # Proactive mode
        if self._is_proactive_mode_enabled() and self._instruction_file_exists(
            "proactive.md"
        ):
            files.append("proactive.md")

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
            List of display paths (e.g., [".synapse/default.md", "~/.synapse/gemini.md"])
        """
        paths: list[str] = []
        home = user_dir or Path.home()

        def is_md_filename(value: object) -> bool:
            """Check if value is a string ending with .md (filename only, no existence check)."""
            return isinstance(value, str) and value.endswith(".md")

        def add_if_exists(filename: str) -> None:
            """Add file to paths if it exists in project or user directory."""
            project_path = Path.cwd() / ".synapse" / filename
            user_path = home / ".synapse" / filename
            if not (project_path.exists() or user_path.exists()):
                return
            display_path = self._get_file_display_path(filename, user_dir)
            if display_path:
                paths.append(display_path)

        # Check agent-specific file
        agent_instruction = self.instructions.get(agent_type, "")
        if is_md_filename(agent_instruction):
            add_if_exists(agent_instruction)

        # Check default file (only if agent-specific is not set)
        if not agent_instruction:
            default_instruction = self.instructions.get("default", "")
            if is_md_filename(default_instruction):
                add_if_exists(default_instruction)

        # File safety
        if self._is_file_safety_enabled():
            add_if_exists("file-safety.md")

        # Learning mode (either flag enables learning.md injection)
        if self._is_any_learning_enabled():
            add_if_exists("learning.md")

        # Shared memory
        if self._is_shared_memory_enabled():
            add_if_exists("shared-memory.md")

        # Proactive mode
        if self._is_proactive_mode_enabled():
            add_if_exists("proactive.md")

        return paths

    def _get_file_display_path(
        self, filename: str, user_dir: Path | None = None
    ) -> str | None:
        """
        Get the display path for an instruction file.

        Checks if the file exists in project or user directory and returns
        the appropriate display path. Project directory takes precedence.

        Args:
            filename: The filename to check (e.g., "default.md")
            user_dir: Optional custom user directory for testing.

        Returns:
            Display path like ".synapse/default.md" or "~/.synapse/default.md",
            or None if file doesn't exist in either location.
        """
        home = user_dir or Path.home()
        locations = [
            (Path.cwd() / ".synapse" / filename, f".synapse/{filename}"),
            (home / ".synapse" / filename, f"~/.synapse/{filename}"),
        ]

        for path, display in locations:
            if path.exists():
                return display
        return None

    def _is_valid_md_file(self, instruction: object) -> bool:
        """Check if instruction is a valid .md filename that exists."""
        if not isinstance(instruction, str) or not instruction.endswith(".md"):
            return False
        return self._instruction_file_exists(instruction)

    def _is_env_flag_enabled(self, key: str) -> bool:
        """Check if an environment flag is enabled via env var or settings.

        Resolution order: os.environ > self.env > default (false).

        Args:
            key: The environment variable name (e.g., "SYNAPSE_FILE_SAFETY_ENABLED").

        Returns:
            True if the flag value is "true" or "1" (case-insensitive).
        """
        value = os.environ.get(key, "").lower()
        if not value:
            value = self.env.get(key, "false").lower()
        return value in ("true", "1")

    def _is_file_safety_enabled(self) -> bool:
        """Check if file safety is enabled via env var or settings."""
        return self._is_env_flag_enabled("SYNAPSE_FILE_SAFETY_ENABLED")

    def _is_learning_mode_enabled(self) -> bool:
        """Check if learning mode is enabled via env var or settings."""
        return self._is_env_flag_enabled("SYNAPSE_LEARNING_MODE_ENABLED")

    def _is_learning_translation_enabled(self) -> bool:
        """Check if learning translation is enabled via env var or settings."""
        return self._is_env_flag_enabled("SYNAPSE_LEARNING_MODE_TRANSLATION")

    def _is_shared_memory_enabled(self) -> bool:
        """Check if shared memory is enabled via env var or settings."""
        return self._is_env_flag_enabled("SYNAPSE_SHARED_MEMORY_ENABLED")

    def _is_proactive_mode_enabled(self) -> bool:
        """Check if proactive mode is enabled via env var or settings."""
        return self._is_env_flag_enabled("SYNAPSE_PROACTIVE_MODE_ENABLED")

    def _is_any_learning_enabled(self) -> bool:
        """Check if any learning feature (mode or translation) is enabled."""
        return (
            self._is_learning_mode_enabled() or self._is_learning_translation_enabled()
        )

    def _instruction_file_exists(self, filename: str) -> bool:
        """Check if an instruction file exists in .synapse directory."""
        project_path = Path.cwd() / ".synapse" / filename
        user_path = Path.home() / ".synapse" / filename

        return project_path.exists() or user_path.exists()

    def _append_optional_instructions(self, instruction: str) -> str:
        """
        Append optional instruction files based on environment variables or settings.

        Currently supports:
        - SYNAPSE_FILE_SAFETY_ENABLED=true: appends .synapse/file-safety.md
        - SYNAPSE_LEARNING_MODE_ENABLED or SYNAPSE_LEARNING_MODE_TRANSLATION=true: appends .synapse/learning.md

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

        if self._is_any_learning_enabled():
            learning_content = self._load_instruction_file("learning.md")
            if learning_content:
                instruction = instruction + "\n\n" + learning_content

        if self._is_shared_memory_enabled():
            memory_content = self._load_instruction_file("shared-memory.md")
            if memory_content:
                instruction = instruction + "\n\n" + memory_content

        if self._is_proactive_mode_enabled():
            proactive_content = self._load_instruction_file("proactive.md")
            if proactive_content:
                instruction = instruction + "\n\n" + proactive_content

        return instruction

    def _process_conditional_sections(
        self, text: str, variables: dict[str, str]
    ) -> str:
        """
        Process Mustache-style conditional sections.

        Supports:
        - {{#var}}content{{/var}}: include content if var is truthy
        - {{^var}}content{{/var}}: include content if var is falsy (inverse)

        Args:
            text: The template text to process.
            variables: Dict of variable names to their values.

        Returns:
            Processed text with conditional sections resolved.
        """
        keep = r"\1"
        remove = ""

        # Process known variables
        for var_name, value in variables.items():
            # Positive sections: {{#var}}...{{/var}} — keep if truthy
            pos_pattern = rf"\{{\{{#{var_name}\}}\}}(.*?)\{{\{{/{var_name}\}}\}}"
            text = re.sub(pos_pattern, keep if value else remove, text, flags=re.DOTALL)

            # Inverse sections: {{^var}}...{{/var}} — keep if falsy
            inv_pattern = rf"\{{\{{\^{var_name}\}}\}}(.*?)\{{\{{/{var_name}\}}\}}"
            text = re.sub(inv_pattern, remove if value else keep, text, flags=re.DOTALL)

        # Remove any remaining unprocessed conditional sections (undefined variables)
        # This prevents template syntax from appearing in final output
        remaining_pattern = r"\{\{[#^]\w+\}\}.*?\{\{/\w+\}\}"
        text = re.sub(remaining_pattern, "", text, flags=re.DOTALL)

        return text

    def _load_instruction_file(
        self, filename: str, *, user_dir: Path | None = None
    ) -> str:
        """
        Load instruction content from a file in .synapse directory.

        Search order:
        1. Project: .synapse/<filename>
        2. User: <user_dir>/.synapse/<filename> (or ~/.synapse/<filename>)

        Args:
            filename: The filename to load (e.g., "default.md")
            user_dir: Optional override for the user home directory.

        Returns:
            File content if found, empty string otherwise.
        """
        home = user_dir if user_dir is not None else Path.home()
        search_paths = [
            Path.cwd() / ".synapse" / filename,
            home / ".synapse" / filename,
        ]

        for path in search_paths:
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
        return flags if isinstance(flags, list) else []

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

        def matches_flag(arg: str, flag: str) -> bool:
            # Exact match (e.g., "--resume" matches "--resume")
            if arg == flag:
                return True
            # Value form match (e.g., "--resume=abc" matches "--resume")
            # Only for flags starting with "-" (not positional like "resume")
            return flag.startswith("-") and arg.startswith(flag + "=")

        return any(matches_flag(arg, flag) for arg in tool_args for flag in flags)

    def has_mcp_bootstrap_config(self, agent_type: str) -> bool:
        """Return True when Synapse MCP bootstrap is configured for *agent_type*."""
        normalized = agent_type.strip().lower()

        for path in self._mcp_config_paths(normalized):
            if path.suffix == ".toml":
                if self._has_synapse_mcp_toml(path):
                    return True
                continue
            if self._has_synapse_mcp_json(path, normalized):
                return True
        return False

    def _mcp_config_paths(self, agent_type: str) -> list[Path]:
        """Return candidate MCP configuration files for the given agent type."""
        home = Path.home()
        cwd = Path.cwd()
        if agent_type == "claude":
            return [cwd / ".mcp.json", home / ".claude.json"]
        if agent_type == "codex":
            return [
                home / ".codex" / "config.toml",
                home / ".config" / "codex" / "config.toml",
            ]
        if agent_type == "gemini":
            return [
                cwd / ".gemini" / "settings.json",
                home / ".gemini" / "settings.json",
            ]
        if agent_type == "opencode":
            return [
                cwd / "opencode.json",
                home / ".config" / "opencode" / "opencode.json",
            ]
        return []

    def _has_synapse_mcp_json(self, path: Path, agent_type: str) -> bool:
        """Check JSON config files used by Claude, Gemini, and OpenCode."""
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        if not isinstance(data, dict):
            return False

        if agent_type == "opencode":
            section = data.get("mcp", {})
        else:
            section = data.get("mcpServers", {})
        if not isinstance(section, dict):
            return False

        for name, entry in section.items():
            if not isinstance(entry, dict):
                continue
            if agent_type == "opencode" and entry.get("enabled") is not True:
                continue
            if self._looks_like_synapse_mcp_entry(name, entry):
                return True
        return False

    def _has_synapse_mcp_toml(self, path: Path) -> bool:
        """Check Codex TOML MCP config using a lightweight text scan."""
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return False

        section_match = re.search(
            r"(?ms)^\[mcp_servers\.synapse\]\s*(.*?)(?=^\[|\Z)",
            text,
        )
        if section_match:
            return self._looks_like_synapse_mcp_text(section_match.group(1))

        for candidate in re.finditer(
            r"(?ms)^\[mcp_servers\.(.*?)\]\s*(.*?)(?=^\[|\Z)",
            text,
        ):
            if candidate.group(1) != "synapse":
                continue
            if self._looks_like_synapse_mcp_text(candidate.group(2)):
                return True

        return False

    @staticmethod
    def _looks_like_synapse_mcp_entry(name: str, entry: dict[str, Any]) -> bool:
        """Return True when a structured MCP config entry points at Synapse."""
        if name == "synapse":
            return True

        command = entry.get("command")
        args = entry.get("args")
        command_text = (
            " ".join(command) if isinstance(command, list) else str(command or "")
        )
        args_text = (
            " ".join(str(arg) for arg in args)
            if isinstance(args, list)
            else str(args or "")
        )
        return SynapseSettings._looks_like_synapse_mcp_text(
            f"{command_text} {args_text}"
        )

    @staticmethod
    def _looks_like_synapse_mcp_text(text: str) -> bool:
        """Return True when text contains a Synapse MCP launcher signature."""
        normalized = text.lower()
        return "synapse.mcp" in normalized or "synapse mcp serve" in normalized

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

    def get_list_columns(self) -> list[str]:
        """
        Get the list of columns to display in synapse list command.

        Available columns:
        - ID: Agent ID (e.g., synapse-claude-8100)
        - NAME: Custom agent name
        - TYPE: Agent type (claude, gemini, codex, etc.)
        - ROLE: Agent role description
        - STATUS: Current status (READY, PROCESSING, etc.)
        - CURRENT: Current task preview
        - TRANSPORT: Transport status (UDS/TCP)
        - WORKING_DIR: Working directory
        - EDITING_FILE: File being edited (requires file-safety enabled)

        Returns:
            List of column names in display order.
        """
        columns = self.list_config.get("columns", [])
        if not columns:
            # Fall back to default
            columns = DEFAULT_SETTINGS["list"]["columns"]
        return list(columns)

    def get_shutdown_settings(self) -> dict[str, Any]:
        """Get shutdown configuration.

        Returns:
            Dict with timeout_seconds (int) and graceful_enabled (bool).
        """
        defaults = DEFAULT_SETTINGS["shutdown"]
        return {
            "timeout_seconds": self.shutdown_config.get(
                "timeout_seconds", defaults["timeout_seconds"]
            ),
            "graceful_enabled": self.shutdown_config.get(
                "graceful_enabled", defaults["graceful_enabled"]
            ),
        }

    def get_delegate_mode_config(self) -> dict[str, Any]:
        """Get delegate mode configuration.

        Returns:
            Dict with deny_file_locks (bool) and instruction_template (str).
        """
        defaults = DEFAULT_SETTINGS["delegate_mode"]
        return {
            "deny_file_locks": self.delegate_mode_config.get(
                "deny_file_locks", defaults["deny_file_locks"]
            ),
            "instruction_template": self.delegate_mode_config.get(
                "instruction_template", defaults["instruction_template"]
            ),
        }

    def get_hooks_config(self) -> dict[str, str]:
        """Get hooks configuration.

        Returns:
            Dict with hook names mapped to shell commands.
        """
        defaults = DEFAULT_SETTINGS["hooks"]
        return {
            "on_idle": self.hooks_config.get("on_idle", defaults["on_idle"]),
            "on_task_completed": self.hooks_config.get(
                "on_task_completed", defaults["on_task_completed"]
            ),
        }


def get_settings() -> SynapseSettings:
    """
    Get the current settings, loading from all scopes.

    This is a convenience function that creates a new SynapseSettings
    instance with the default paths.

    Returns:
        SynapseSettings instance with merged settings.
    """
    return SynapseSettings.load()
