"""Tests for synapse config command."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from synapse.commands.config import HAS_QUESTIONARY, RichConfigCommand

# ConfigCommand requires questionary - conditionally import
if HAS_QUESTIONARY:
    from synapse.commands.config import ConfigCommand
else:
    ConfigCommand = None  # type: ignore[assignment,misc]

# Skip decorator for tests requiring questionary
requires_questionary = pytest.mark.skipif(
    not HAS_QUESTIONARY, reason="questionary not installed"
)


class MockQuestionary:
    """Mock questionary module for testing."""

    def __init__(self, responses: list[Any]) -> None:
        self._responses = iter(responses)
        self._call_log: list[tuple[str, str]] = []

    def _next_response(self) -> Any:
        return next(self._responses)

    def select(self, message: str, choices: Any = None, **kwargs: Any) -> MagicMock:
        self._call_log.append(("select", message))
        mock = MagicMock()
        mock.ask.return_value = self._next_response()
        return mock

    def text(self, message: str, default: str = "", **kwargs: Any) -> MagicMock:
        self._call_log.append(("text", message))
        mock = MagicMock()
        mock.ask.return_value = self._next_response()
        return mock

    def confirm(self, message: str, default: bool = False, **kwargs: Any) -> MagicMock:
        self._call_log.append(("confirm", message))
        mock = MagicMock()
        mock.ask.return_value = self._next_response()
        return mock


@pytest.fixture
def temp_synapse_dir(tmp_path: Path) -> Path:
    """Create a temporary .synapse directory."""
    synapse_dir = tmp_path / ".synapse"
    synapse_dir.mkdir(parents=True, exist_ok=True)
    return synapse_dir


@requires_questionary
class TestConfigShow:
    """Tests for 'synapse config show' command."""

    def test_show_merged_settings(self) -> None:
        """Should show merged settings from all scopes."""
        output_lines: list[str] = []

        cmd = ConfigCommand(
            print_func=lambda s: output_lines.append(s),
        )
        cmd.show(scope="merged")

        output = "\n".join(output_lines)
        assert "merged" in output.lower()

    def test_show_user_settings_not_found(self, tmp_path: Path) -> None:
        """Should show message when user settings not found."""
        output_lines: list[str] = []

        cmd = ConfigCommand(
            print_func=lambda s: output_lines.append(s),
        )

        with patch.object(cmd, "_get_settings_path") as mock_path:
            mock_path.return_value = tmp_path / "nonexistent" / "settings.json"
            cmd.show(scope="user")

        output = "\n".join(output_lines)
        assert "no settings file" in output.lower()

    def test_show_project_settings_exists(self, temp_synapse_dir: Path) -> None:
        """Should show project settings when file exists."""
        settings = {"env": {"SYNAPSE_HISTORY_ENABLED": "true"}}
        (temp_synapse_dir / "settings.json").write_text(json.dumps(settings))

        output_lines: list[str] = []
        cmd = ConfigCommand(
            print_func=lambda s: output_lines.append(s),
        )

        with patch.object(cmd, "_get_settings_path") as mock_path:
            mock_path.return_value = temp_synapse_dir / "settings.json"
            cmd.show(scope="project")

        output = "\n".join(output_lines)
        assert "SYNAPSE_HISTORY_ENABLED" in output
        assert "true" in output


@requires_questionary
class TestConfigRun:
    """Tests for interactive config command."""

    def test_cancel_scope_selection(self) -> None:
        """Should exit gracefully when scope selection is cancelled."""
        output_lines: list[str] = []
        mock_q = MockQuestionary([None])  # Cancel scope selection

        cmd = ConfigCommand(
            print_func=lambda s: output_lines.append(s),
            questionary_module=mock_q,
        )
        result = cmd.run()

        assert result is False
        output = "\n".join(output_lines)
        assert "cancelled" in output.lower()

    def test_exit_without_changes(self, temp_synapse_dir: Path) -> None:
        """Should exit without saving when no changes made."""
        output_lines: list[str] = []
        mock_q = MockQuestionary(
            [
                "user",  # scope selection
                "cancel",  # main menu - exit
            ]
        )

        cmd = ConfigCommand(
            print_func=lambda s: output_lines.append(s),
            questionary_module=mock_q,
        )

        with patch.object(cmd, "_get_settings_path") as mock_path:
            mock_path.return_value = temp_synapse_dir / "settings.json"
            result = cmd.run()

        assert result is False
        output = "\n".join(output_lines)
        assert "exited" in output.lower()

    def test_edit_and_save_env_setting(self, temp_synapse_dir: Path) -> None:
        """Should save changes when env setting is modified."""
        settings_path = temp_synapse_dir / "settings.json"

        output_lines: list[str] = []
        mock_q = MockQuestionary(
            [
                "user",  # scope selection
                "env",  # main menu - env category
                "SYNAPSE_HISTORY_ENABLED",  # env setting selection
                "true",  # new value
                "save",  # main menu - save
            ]
        )

        cmd = ConfigCommand(
            print_func=lambda s: output_lines.append(s),
            questionary_module=mock_q,
        )

        with patch.object(cmd, "_get_settings_path") as mock_path:
            mock_path.return_value = settings_path
            result = cmd.run()

        assert result is True

        # Verify settings were saved
        assert settings_path.exists()
        saved = json.loads(settings_path.read_text())
        assert saved["env"]["SYNAPSE_HISTORY_ENABLED"] == "true"

    def test_edit_a2a_flow_setting(self, temp_synapse_dir: Path) -> None:
        """Should save A2A flow setting correctly."""
        settings_path = temp_synapse_dir / "settings.json"

        output_lines: list[str] = []
        mock_q = MockQuestionary(
            [
                "project",  # scope selection
                "a2a",  # main menu - a2a category
                "flow",  # a2a setting selection
                "roundtrip",  # new value
                "save",  # main menu - save
            ]
        )

        cmd = ConfigCommand(
            print_func=lambda s: output_lines.append(s),
            questionary_module=mock_q,
        )

        with patch.object(cmd, "_get_settings_path") as mock_path:
            mock_path.return_value = settings_path
            result = cmd.run()

        assert result is True

        saved = json.loads(settings_path.read_text())
        assert saved["a2a"]["flow"] == "roundtrip"

    def test_edit_delegation_enabled(self, temp_synapse_dir: Path) -> None:
        """Should save delegation enabled setting correctly."""
        settings_path = temp_synapse_dir / "settings.json"

        output_lines: list[str] = []
        mock_q = MockQuestionary(
            [
                "user",  # scope selection
                "delegation",  # main menu - delegation category
                "enabled",  # delegation setting selection
                True,  # new value (confirm)
                "save",  # main menu - save
            ]
        )

        cmd = ConfigCommand(
            print_func=lambda s: output_lines.append(s),
            questionary_module=mock_q,
        )

        with patch.object(cmd, "_get_settings_path") as mock_path:
            mock_path.return_value = settings_path
            result = cmd.run()

        assert result is True

        saved = json.loads(settings_path.read_text())
        assert saved["delegation"]["enabled"] is True

    def test_edit_instructions_setting(self, temp_synapse_dir: Path) -> None:
        """Should save instructions setting correctly."""
        settings_path = temp_synapse_dir / "settings.json"

        output_lines: list[str] = []
        mock_q = MockQuestionary(
            [
                "user",  # scope selection
                "instructions",  # main menu - instructions category
                "claude",  # instructions setting selection
                "claude.md",  # new value
                "save",  # main menu - save
            ]
        )

        cmd = ConfigCommand(
            print_func=lambda s: output_lines.append(s),
            questionary_module=mock_q,
        )

        with patch.object(cmd, "_get_settings_path") as mock_path:
            mock_path.return_value = settings_path
            result = cmd.run()

        assert result is True

        saved = json.loads(settings_path.read_text())
        assert saved["instructions"]["claude"] == "claude.md"

    def test_edit_resume_flags_setting(self, temp_synapse_dir: Path) -> None:
        """Should save resume flags setting correctly."""
        settings_path = temp_synapse_dir / "settings.json"

        output_lines: list[str] = []
        mock_q = MockQuestionary(
            [
                "user",  # scope selection
                "resume_flags",  # main menu - resume_flags category
                "claude",  # resume_flags setting selection
                "--continue, --resume",  # new value (comma-separated)
                "save",  # main menu - save
            ]
        )

        cmd = ConfigCommand(
            print_func=lambda s: output_lines.append(s),
            questionary_module=mock_q,
        )

        with patch.object(cmd, "_get_settings_path") as mock_path:
            mock_path.return_value = settings_path
            result = cmd.run()

        assert result is True

        saved = json.loads(settings_path.read_text())
        assert saved["resume_flags"]["claude"] == ["--continue", "--resume"]

    def test_unsaved_changes_warning(self, temp_synapse_dir: Path) -> None:
        """Should warn about unsaved changes on exit."""
        output_lines: list[str] = []
        mock_q = MockQuestionary(
            [
                "user",  # scope selection
                "env",  # main menu - env category
                "SYNAPSE_HISTORY_ENABLED",  # env setting selection
                "true",  # new value
                "cancel",  # main menu - cancel
                True,  # confirm exit
            ]
        )

        cmd = ConfigCommand(
            print_func=lambda s: output_lines.append(s),
            questionary_module=mock_q,
        )

        with patch.object(cmd, "_get_settings_path") as mock_path:
            mock_path.return_value = temp_synapse_dir / "settings.json"
            result = cmd.run()

        assert result is False
        # Verify confirm was called
        assert ("confirm", "You have unsaved changes. Exit anyway?") in mock_q._call_log

    def test_no_changes_to_save(self, temp_synapse_dir: Path) -> None:
        """Should show message when saving with no changes."""
        output_lines: list[str] = []
        mock_q = MockQuestionary(
            [
                "user",  # scope selection
                "save",  # main menu - save (no changes made)
            ]
        )

        cmd = ConfigCommand(
            print_func=lambda s: output_lines.append(s),
            questionary_module=mock_q,
        )

        with patch.object(cmd, "_get_settings_path") as mock_path:
            mock_path.return_value = temp_synapse_dir / "settings.json"
            result = cmd.run()

        assert result is True
        output = "\n".join(output_lines)
        assert "no changes" in output.lower()

    def test_back_to_main_menu_from_env(self, temp_synapse_dir: Path) -> None:
        """Should return to main menu when selecting 'Back' from env settings."""
        output_lines: list[str] = []
        mock_q = MockQuestionary(
            [
                "user",  # scope selection
                "env",  # main menu - env category
                None,  # Back to main menu
                "cancel",  # main menu - exit
            ]
        )

        cmd = ConfigCommand(
            print_func=lambda s: output_lines.append(s),
            questionary_module=mock_q,
        )

        with patch.object(cmd, "_get_settings_path") as mock_path:
            mock_path.return_value = temp_synapse_dir / "settings.json"
            result = cmd.run()

        assert result is False


@requires_questionary
class TestConfigHelpers:
    """Tests for helper methods."""

    def test_get_settings_path_user(self) -> None:
        """Should return user settings path."""
        cmd = ConfigCommand()
        path = cmd._get_settings_path("user")
        assert ".synapse" in str(path)
        assert "settings.json" in str(path)

    def test_get_settings_path_project(self, tmp_path: Path) -> None:
        """Should return project settings path."""
        cmd = ConfigCommand()
        with patch("pathlib.Path.cwd", return_value=tmp_path):
            path = cmd._get_settings_path("project")
        assert "settings.json" in str(path)

    def test_update_settings_creates_category(self) -> None:
        """Should create category if it doesn't exist."""
        cmd = ConfigCommand()
        settings: dict[str, Any] = {}
        result = cmd._update_settings(settings, "env", "TEST_VAR", "value")
        assert result["env"]["TEST_VAR"] == "value"

    def test_update_settings_preserves_existing(self) -> None:
        """Should preserve existing settings."""
        cmd = ConfigCommand()
        settings: dict[str, Any] = {"env": {"EXISTING": "value"}}
        result = cmd._update_settings(settings, "env", "NEW_VAR", "new_value")
        assert result["env"]["EXISTING"] == "value"
        assert result["env"]["NEW_VAR"] == "new_value"

    def test_update_settings_with_none_key(self) -> None:
        """Should return settings unchanged when key is None."""
        cmd = ConfigCommand()
        settings: dict[str, Any] = {"env": {"EXISTING": "value"}}
        result = cmd._update_settings(settings, "env", None, "value")
        assert result == settings

    def test_save_settings_creates_directory(self, tmp_path: Path) -> None:
        """Should create parent directory if it doesn't exist."""
        cmd = ConfigCommand()
        settings_path = tmp_path / "new_dir" / ".synapse" / "settings.json"
        settings = {"env": {"TEST": "value"}}

        result = cmd._save_settings(settings_path, settings)

        assert result is True
        assert settings_path.exists()
        saved = json.loads(settings_path.read_text())
        assert saved["env"]["TEST"] == "value"

    def test_load_current_settings_nonexistent_file(self, tmp_path: Path) -> None:
        """Should return empty dict for nonexistent file."""
        cmd = ConfigCommand()
        path = tmp_path / "nonexistent.json"

        result = cmd._load_current_settings(path)

        assert result == {}


@requires_questionary
class TestConfigCLIIntegration:
    """Tests for CLI integration."""

    def test_cmd_config_calls_run(self) -> None:
        """cmd_config should call ConfigCommand.run()."""
        from synapse.cli import cmd_config

        with patch("synapse.commands.config.ConfigCommand") as mock_cmd_class:
            mock_cmd = MagicMock()
            mock_cmd_class.return_value = mock_cmd

            args = MagicMock()
            args.scope = "user"

            cmd_config(args)

            mock_cmd.run.assert_called_once_with(scope="user")

    def test_cmd_config_show_calls_show(self) -> None:
        """cmd_config_show should call ConfigCommand.show()."""
        from synapse.cli import cmd_config_show

        with patch("synapse.commands.config.ConfigCommand") as mock_cmd_class:
            mock_cmd = MagicMock()
            mock_cmd_class.return_value = mock_cmd

            args = MagicMock()
            args.scope = "merged"

            cmd_config_show(args)

            mock_cmd.show.assert_called_once_with(scope="merged")


class TestRichConfigCommand:
    """Tests for Rich TUI config command."""

    def test_init_default(self) -> None:
        """Should initialize with default values."""
        cmd = RichConfigCommand()
        assert cmd._scope == "user"
        assert cmd._modified is False

    def test_init_with_scope(self) -> None:
        """Should accept scope parameter."""
        cmd = RichConfigCommand(scope="project")
        assert cmd._scope == "project"

    def test_get_category_keys(self) -> None:
        """Should return list of category keys."""
        cmd = RichConfigCommand()
        keys = cmd._get_category_keys()
        assert "env" in keys
        assert "instructions" in keys
        assert "a2a" in keys
        assert "delegation" in keys
        assert "resume_flags" in keys

    def test_get_setting_keys(self) -> None:
        """Should return list of setting keys for a category."""
        cmd = RichConfigCommand()
        keys = cmd._get_setting_keys("env")
        assert "SYNAPSE_HISTORY_ENABLED" in keys

    def test_update_setting_env(self) -> None:
        """Should update env setting correctly."""
        cmd = RichConfigCommand()
        cmd._current_settings = {}

        cmd._update_setting("env", "SYNAPSE_HISTORY_ENABLED", "true")

        assert cmd._current_settings["env"]["SYNAPSE_HISTORY_ENABLED"] == "true"
        assert cmd._modified is True

    def test_update_setting_delegation(self) -> None:
        """Should update delegation setting correctly (boolean)."""
        cmd = RichConfigCommand()
        cmd._current_settings = {}

        cmd._update_setting("delegation", "enabled", True)

        assert cmd._current_settings["delegation"]["enabled"] is True
        assert cmd._modified is True

    def test_update_setting_resume_flags(self) -> None:
        """Should update resume_flags setting correctly (list)."""
        cmd = RichConfigCommand()
        cmd._current_settings = {}

        cmd._update_setting("resume_flags", "claude", ["--continue", "--resume"])

        assert cmd._current_settings["resume_flags"]["claude"] == [
            "--continue",
            "--resume",
        ]
        assert cmd._modified is True

    def test_get_settings_path_user(self) -> None:
        """Should return user settings path."""
        cmd = RichConfigCommand()
        path = cmd._get_settings_path("user")
        assert ".synapse/settings.json" in str(path)

    def test_get_settings_path_project(self) -> None:
        """Should return project settings path."""
        cmd = RichConfigCommand()
        path = cmd._get_settings_path("project")
        assert ".synapse/settings.json" in str(path)

    def test_select_menu_returns_none_on_escape(self) -> None:
        """_select_menu should return None when ESC is pressed."""
        import sys
        from unittest.mock import MagicMock, patch

        # Create a mock module
        mock_module = MagicMock()
        mock_menu = MagicMock()
        mock_menu.show.return_value = None
        mock_module.TerminalMenu.return_value = mock_menu

        # Patch the import
        with patch.dict(sys.modules, {"simple_term_menu": mock_module}):
            cmd = RichConfigCommand()
            result = cmd._select_menu("Test Title", ["Item 1", "Item 2"])

            assert result is None
            mock_module.TerminalMenu.assert_called_once()

    def test_select_menu_returns_selected_index(self) -> None:
        """_select_menu should return selected index."""
        import sys
        from unittest.mock import MagicMock, patch

        # Create a mock module
        mock_module = MagicMock()
        mock_menu = MagicMock()
        mock_menu.show.return_value = 1  # Second item selected
        mock_module.TerminalMenu.return_value = mock_menu

        with patch.dict(sys.modules, {"simple_term_menu": mock_module}):
            cmd = RichConfigCommand()
            result = cmd._select_menu("Test Title", ["Item 1", "Item 2"])

            assert result == 1

    def test_run_saves_settings(self, tmp_path: Path) -> None:
        """run() should save settings when user selects save."""
        from unittest.mock import patch

        settings_path = tmp_path / ".synapse" / "settings.json"
        initial_settings = {"env": {"SYNAPSE_HISTORY_ENABLED": "true"}}

        cmd = RichConfigCommand(scope="user")

        # Mock _select_menu to return "Save and exit" option (index 6 for 5 categories + separator)
        # Categories: env, instructions, a2a, delegation, resume_flags (5)
        # Separator at index 5, Save at index 6, Quit at index 7
        def mock_select_menu(
            title: str, items: list[str], cursor_index: int = 0
        ) -> int:
            # Set modified flag and settings before returning save
            cmd._modified = True
            cmd._current_settings = initial_settings
            return 6

        with (
            patch.object(cmd, "_select_menu", side_effect=mock_select_menu),
            patch.object(cmd, "_get_settings_path", return_value=settings_path),
            patch(
                "synapse.commands.config.load_settings", return_value=initial_settings
            ),
        ):
            result = cmd.run()

        assert result is True
        assert settings_path.exists()
        saved = json.loads(settings_path.read_text())
        assert saved["env"]["SYNAPSE_HISTORY_ENABLED"] == "true"

    def test_run_exits_without_saving(self) -> None:
        """run() should exit without saving when user cancels."""
        from unittest.mock import patch

        cmd = RichConfigCommand(scope="user")
        cmd._modified = False

        # Mock _select_menu to return "Exit without saving" option (index 7)
        with (
            patch.object(cmd, "_select_menu", return_value=7),
            patch("synapse.commands.config.load_settings", return_value={}),
        ):
            result = cmd.run()

        assert result is False

    def test_run_exits_on_escape(self) -> None:
        """run() should exit when ESC is pressed."""
        from unittest.mock import patch

        cmd = RichConfigCommand(scope="user")
        cmd._modified = False

        # Mock _select_menu to return None (ESC pressed)
        with (
            patch.object(cmd, "_select_menu", return_value=None),
            patch("synapse.commands.config.load_settings", return_value={}),
        ):
            result = cmd.run()

        assert result is False

    def test_edit_category_back_on_escape(self) -> None:
        """_edit_category should return when ESC is pressed."""
        from unittest.mock import patch

        cmd = RichConfigCommand()
        cmd._current_settings = {}

        # Mock _select_menu to return None (ESC)
        with patch.object(cmd, "_select_menu", return_value=None):
            # Should return without error
            cmd._edit_category("env")

    def test_edit_value_boolean_true(self) -> None:
        """_edit_value should set boolean to true when first option selected."""
        from unittest.mock import patch

        cmd = RichConfigCommand()
        cmd._current_settings = {"env": {}}

        # Mock _select_menu to return 0 (true option)
        with patch.object(cmd, "_select_menu", return_value=0):
            cmd._edit_value("env", "SYNAPSE_HISTORY_ENABLED")

        assert cmd._current_settings["env"]["SYNAPSE_HISTORY_ENABLED"] == "true"
        assert cmd._modified is True

    def test_edit_value_boolean_false(self) -> None:
        """_edit_value should set boolean to false when second option selected."""
        from unittest.mock import patch

        cmd = RichConfigCommand()
        cmd._current_settings = {"env": {}}

        # Mock _select_menu to return 1 (false option)
        with patch.object(cmd, "_select_menu", return_value=1):
            cmd._edit_value("env", "SYNAPSE_HISTORY_ENABLED")

        assert cmd._current_settings["env"]["SYNAPSE_HISTORY_ENABLED"] == "false"

    def test_edit_value_flow_setting(self) -> None:
        """_edit_value should set flow setting correctly."""
        from unittest.mock import patch

        cmd = RichConfigCommand()
        cmd._current_settings = {"a2a": {}}

        # Mock _select_menu to return 1 (roundtrip option)
        with patch.object(cmd, "_select_menu", return_value=1):
            cmd._edit_value("a2a", "flow")

        assert cmd._current_settings["a2a"]["flow"] == "roundtrip"

    def test_edit_value_enabled_setting(self) -> None:
        """_edit_value should set enabled setting correctly."""
        from unittest.mock import patch

        cmd = RichConfigCommand()
        cmd._current_settings = {"delegation": {}}

        # Mock _select_menu to return 0 (true option)
        with patch.object(cmd, "_select_menu", return_value=0):
            cmd._edit_value("delegation", "enabled")

        assert cmd._current_settings["delegation"]["enabled"] is True
