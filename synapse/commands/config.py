"""Config command implementation for Synapse CLI."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import questionary
from questionary import Choice, Separator

from synapse.settings import (
    DEFAULT_SETTINGS,
    SynapseSettings,
    get_settings,
    load_settings,
)

# Sentinel value for "Back to main menu" choice
# Note: questionary.Choice(title, value=None) uses title as value, not None
_BACK_SENTINEL = "__BACK__"

# Setting category definitions with display names and descriptions
SETTING_CATEGORIES = {
    "env": {
        "name": "Environment Variables",
        "description": "Configure SYNAPSE_* environment variables",
    },
    "instructions": {
        "name": "Instructions",
        "description": "Configure agent-specific instruction files",
    },
    "a2a": {
        "name": "A2A Protocol",
        "description": "Configure inter-agent communication settings",
    },
    "delegation": {
        "name": "Delegation",
        "description": "Configure task delegation settings",
    },
    "resume_flags": {
        "name": "Resume Flags",
        "description": "Configure CLI flags that indicate resume mode",
    },
}

# Boolean environment variables (will show as toggle)
BOOLEAN_ENV_VARS = {
    "SYNAPSE_HISTORY_ENABLED",
    "SYNAPSE_FILE_SAFETY_ENABLED",
    "SYNAPSE_AUTH_ENABLED",
    "SYNAPSE_ALLOW_LOCALHOST",
    "SYNAPSE_USE_HTTPS",
}


class ConfigCommand:
    """Interactive TUI for managing Synapse settings."""

    def __init__(
        self,
        settings_factory: Callable[[], SynapseSettings] | None = None,
        print_func: Callable[[str], None] = print,
        questionary_module: Any | None = None,
    ) -> None:
        """Initialize ConfigCommand.

        Args:
            settings_factory: Factory to create SynapseSettings instance.
            print_func: Function to use for output (for testing).
            questionary_module: Questionary module for TUI (injectable for testing).
        """
        self._settings_factory = settings_factory or get_settings
        self._print = print_func
        self._questionary = questionary_module or questionary

    def _get_settings_path(self, scope: str) -> Path:
        """Get settings file path for the given scope."""
        if scope == "user":
            return Path.home() / ".synapse" / "settings.json"
        else:  # project
            return Path.cwd() / ".synapse" / "settings.json"

    def _load_current_settings(self, path: Path) -> dict[str, Any]:
        """Load settings from a specific file (not merged)."""
        return load_settings(path)

    def _save_settings(self, path: Path, settings: dict[str, Any]) -> bool:
        """Save settings to a JSON file."""
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(settings, f, indent=2, ensure_ascii=False)
            return True
        except OSError as e:
            self._print(f"Error saving settings: {e}")
            return False

    def _prompt_scope(self) -> str | None:
        """Prompt user to select scope (user or project)."""
        result: str | None = self._questionary.select(
            "Which settings file do you want to edit?",
            choices=[
                Choice("User settings (~/.synapse/settings.json)", value="user"),
                Choice("Project settings (./.synapse/settings.json)", value="project"),
                Separator(),
                Choice("Cancel", value=_BACK_SENTINEL),
            ],
        ).ask()
        return None if result == _BACK_SENTINEL else result

    def _prompt_main_menu(self) -> str | None:
        """Show main menu with setting categories."""
        choices = []
        for key, info in SETTING_CATEGORIES.items():
            choices.append(Choice(f"{info['name']} - {info['description']}", value=key))
        choices.extend(
            [
                Separator(),
                Choice("Save and exit", value="save"),
                Choice("Exit without saving", value="cancel"),
            ]
        )

        result: str | None = self._questionary.select(
            "Select a category to configure:",
            choices=choices,
        ).ask()
        return result

    def _prompt_env_setting(
        self, current_settings: dict[str, Any]
    ) -> tuple[str | None, str | None]:
        """Prompt user to select and edit an environment variable."""
        env_settings = current_settings.get("env", {})
        default_env = DEFAULT_SETTINGS.get("env", {})

        # Build choices with current values
        choices = []
        for key in default_env:
            current_value = env_settings.get(key, default_env.get(key, ""))
            display_value = current_value if current_value else "(not set)"
            choices.append(Choice(f"{key}: {display_value}", value=key))

        choices.extend(
            [
                Separator(),
                Choice("Back to main menu", value=_BACK_SENTINEL),
            ]
        )

        selected_key = self._questionary.select(
            "Select environment variable to edit:",
            choices=choices,
        ).ask()

        if selected_key is None or selected_key == _BACK_SENTINEL:
            return (None, None)

        # Get new value based on type
        current_value = env_settings.get(
            selected_key, default_env.get(selected_key, "")
        )

        if selected_key in BOOLEAN_ENV_VARS:
            # Boolean toggle
            new_value = self._questionary.select(
                f"Set {selected_key}:",
                choices=[
                    Choice("true", value="true"),
                    Choice("false", value="false"),
                    Choice("(not set)", value=""),
                ],
                default="true" if str(current_value).lower() == "true" else "false",
            ).ask()
        else:
            # Text input
            new_value = self._questionary.text(
                f"Enter value for {selected_key}:",
                default=str(current_value),
            ).ask()

        return (selected_key, new_value)

    def _prompt_instructions_setting(
        self, current_settings: dict[str, Any]
    ) -> tuple[str | None, str | None]:
        """Prompt user to select and edit an instruction setting."""
        instructions = current_settings.get("instructions", {})

        # Available agent types
        agent_types = ["default", "claude", "gemini", "codex"]

        choices = []
        for agent_type in agent_types:
            current_value = instructions.get(agent_type, "")
            if current_value:
                # Truncate long values for display
                display_value = (
                    current_value[:40] + "..."
                    if len(str(current_value)) > 40
                    else current_value
                )
            else:
                display_value = "(default)"
            choices.append(Choice(f"{agent_type}: {display_value}", value=agent_type))

        choices.extend(
            [
                Separator(),
                Choice("Back to main menu", value=_BACK_SENTINEL),
            ]
        )

        selected_key = self._questionary.select(
            "Select instruction to edit:",
            choices=choices,
        ).ask()

        if selected_key is None or selected_key == _BACK_SENTINEL:
            return (None, None)

        current_value = instructions.get(selected_key, "")
        new_value = self._questionary.text(
            f"Enter instruction file for {selected_key} (e.g., 'default.md'):",
            default=str(current_value) if current_value else "",
        ).ask()

        return (selected_key, new_value)

    def _prompt_a2a_setting(
        self, current_settings: dict[str, Any]
    ) -> tuple[str | None, str | None]:
        """Prompt user to edit A2A settings."""
        a2a = current_settings.get("a2a", {})
        current_flow = a2a.get("flow", "auto")

        choices = [
            Choice(
                f"flow - Communication flow mode (current: {current_flow})",
                value="flow",
            ),
            Separator(),
            Choice("Back to main menu", value=_BACK_SENTINEL),
        ]

        selected_key = self._questionary.select(
            "Select A2A setting to edit:",
            choices=choices,
        ).ask()

        if selected_key is None or selected_key == _BACK_SENTINEL:
            return (None, None)

        if selected_key == "flow":
            new_value = self._questionary.select(
                "Select A2A flow mode:",
                choices=[
                    Choice("auto - Automatically determine flow", value="auto"),
                    Choice("roundtrip - Always wait for response", value="roundtrip"),
                    Choice("oneway - Fire and forget", value="oneway"),
                ],
                default=current_flow,
            ).ask()
            return ("flow", new_value)

        return (None, None)

    def _prompt_delegation_setting(
        self, current_settings: dict[str, Any]
    ) -> tuple[str | None, Any]:
        """Prompt user to edit delegation settings."""
        delegation = current_settings.get("delegation", {})
        current_enabled = delegation.get("enabled", False)

        choices = [
            Choice(
                f"enabled - Task delegation enabled: {current_enabled}",
                value="enabled",
            ),
            Separator(),
            Choice("Back to main menu", value=_BACK_SENTINEL),
        ]

        selected_key = self._questionary.select(
            "Select delegation setting to edit:",
            choices=choices,
        ).ask()

        if selected_key is None or selected_key == _BACK_SENTINEL:
            return (None, None)

        if selected_key == "enabled":
            new_value = self._questionary.confirm(
                "Enable task delegation?",
                default=current_enabled,
            ).ask()
            return ("enabled", new_value)

        return (None, None)

    def _prompt_resume_flags_setting(
        self, current_settings: dict[str, Any]
    ) -> tuple[str | None, list[str] | None]:
        """Prompt user to edit resume flags settings."""
        resume_flags = current_settings.get("resume_flags", {})
        default_flags = DEFAULT_SETTINGS.get("resume_flags", {})

        agent_types = ["claude", "codex", "gemini"]

        choices = []
        for agent_type in agent_types:
            current_value = resume_flags.get(
                agent_type, default_flags.get(agent_type, [])
            )
            display_value = ", ".join(current_value) if current_value else "(none)"
            choices.append(Choice(f"{agent_type}: {display_value}", value=agent_type))

        choices.extend(
            [
                Separator(),
                Choice("Back to main menu", value=_BACK_SENTINEL),
            ]
        )

        selected_key = self._questionary.select(
            "Select agent to edit resume flags:",
            choices=choices,
        ).ask()

        if selected_key is None or selected_key == _BACK_SENTINEL:
            return (None, None)

        current_value = resume_flags.get(
            selected_key, default_flags.get(selected_key, [])
        )
        current_str = ", ".join(current_value) if current_value else ""

        new_value_str = self._questionary.text(
            f"Enter resume flags for {selected_key} (comma-separated):",
            default=current_str,
        ).ask()

        if new_value_str is None:
            return (None, None)

        # Parse comma-separated values
        new_value = [flag.strip() for flag in new_value_str.split(",") if flag.strip()]

        return (selected_key, new_value)

    def _update_settings(
        self,
        settings: dict[str, Any],
        category: str,
        key: str | None,
        value: Any,
    ) -> dict[str, Any]:
        """Update settings dict with new value."""
        if key is None:
            return settings

        if category not in settings:
            settings[category] = {}

        settings[category][key] = value
        return settings

    def run(self, scope: str | None = None) -> bool:
        """Run the interactive config TUI.

        Args:
            scope: Optional scope ("user" or "project"). If None, prompt user.

        Returns:
            True if settings were saved, False otherwise.
        """
        # Select scope
        if scope is None:
            scope = self._prompt_scope()

        if scope is None:
            self._print("Cancelled.")
            return False

        # Load current settings for the selected scope
        settings_path = self._get_settings_path(scope)
        current_settings = self._load_current_settings(settings_path)

        self._print(f"\nEditing: {settings_path}")
        if not settings_path.exists():
            self._print("(File does not exist, will be created on save)")
        self._print("")

        modified = False

        # Main loop
        while True:
            category = self._prompt_main_menu()

            if category is None:
                # Handle Ctrl+C or unexpected None return
                if modified:
                    confirm = self._questionary.confirm(
                        "You have unsaved changes. Exit anyway?",
                        default=False,
                    ).ask()
                    if confirm:
                        self._print("\nExited without saving.")
                        return False
                else:
                    self._print("\nExited.")
                    return False

            elif category == "save":
                if modified:
                    if self._save_settings(settings_path, current_settings):
                        self._print(f"\nSettings saved to {settings_path}")
                        return True
                    else:
                        return False
                else:
                    self._print("\nNo changes to save.")
                    return True

            elif category == "cancel":
                if modified:
                    confirm = self._questionary.confirm(
                        "You have unsaved changes. Exit anyway?",
                        default=False,
                    ).ask()
                    if confirm:
                        self._print("\nExited without saving.")
                        return False
                else:
                    self._print("\nExited.")
                    return False

            elif category == "env":
                key, value = self._prompt_env_setting(current_settings)
                if key is not None:
                    current_settings = self._update_settings(
                        current_settings, "env", key, value
                    )
                    modified = True

            elif category == "instructions":
                key, value = self._prompt_instructions_setting(current_settings)
                if key is not None:
                    current_settings = self._update_settings(
                        current_settings, "instructions", key, value
                    )
                    modified = True

            elif category == "a2a":
                key, value = self._prompt_a2a_setting(current_settings)
                if key is not None:
                    current_settings = self._update_settings(
                        current_settings, "a2a", key, value
                    )
                    modified = True

            elif category == "delegation":
                key, value = self._prompt_delegation_setting(current_settings)
                if key is not None:
                    current_settings = self._update_settings(
                        current_settings, "delegation", key, value
                    )
                    modified = True

            elif category == "resume_flags":
                rf_key, rf_value = self._prompt_resume_flags_setting(current_settings)
                if rf_key is not None:
                    current_settings = self._update_settings(
                        current_settings, "resume_flags", rf_key, rf_value
                    )
                    modified = True

    def show(self, scope: str | None = None) -> None:
        """Show current settings (non-interactive).

        Args:
            scope: Optional scope ("user", "project", or "merged").
        """
        if scope == "merged" or scope is None:
            # Show merged settings from all scopes
            settings = self._settings_factory()
            self._print("Current settings (merged from all scopes):")
            self._print("-" * 60)
            self._print(
                json.dumps(
                    {
                        "env": settings.env,
                        "instructions": {
                            k: (v[:50] + "..." if len(str(v)) > 50 else v)
                            for k, v in settings.instructions.items()
                        },
                        "a2a": settings.a2a,
                        "delegation": settings.delegation,
                        "resume_flags": settings.resume_flags,
                    },
                    indent=2,
                )
            )
        else:
            # Show settings from specific scope
            path = self._get_settings_path(scope)
            if path.exists():
                settings_dict = self._load_current_settings(path)
                self._print(f"Settings from {path}:")
                self._print("-" * 60)
                self._print(json.dumps(settings_dict, indent=2))
            else:
                self._print(f"No settings file found at {path}")
