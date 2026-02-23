"""Tests for learning mode settings and instruction injection."""

import os
import tempfile
from pathlib import Path

from synapse.settings import (
    DEFAULT_SETTINGS,
    SynapseSettings,
)


class TestLearningModeSettings:
    """Test default learning mode settings."""

    def setup_method(self):
        """Clear environment variables that affect learning mode tests."""
        for key in [
            "SYNAPSE_FILE_SAFETY_ENABLED",
            "SYNAPSE_LEARNING_MODE_ENABLED",
            "SYNAPSE_LEARNING_MODE_TRANSLATION",
        ]:
            os.environ.pop(key, None)

    def test_default_settings_has_learning_mode_env_vars(self):
        """DEFAULT_SETTINGS['env'] has learning mode keys."""
        assert "SYNAPSE_LEARNING_MODE_ENABLED" in DEFAULT_SETTINGS["env"]
        assert "SYNAPSE_LEARNING_MODE_TRANSLATION" in DEFAULT_SETTINGS["env"]

    def test_default_learning_mode_disabled(self):
        """Learning mode is disabled by default."""
        assert DEFAULT_SETTINGS["env"]["SYNAPSE_LEARNING_MODE_ENABLED"] == "false"

    def test_default_learning_translation_disabled(self):
        """Learning mode translation is disabled by default."""
        assert DEFAULT_SETTINGS["env"]["SYNAPSE_LEARNING_MODE_TRANSLATION"] == "false"


class TestLearningModeInstructionInjection:
    """Test optional learning instruction loading."""

    def setup_method(self):
        """Clear environment variables that affect instruction generation."""
        for key in [
            "SYNAPSE_FILE_SAFETY_ENABLED",
            "SYNAPSE_LEARNING_MODE_ENABLED",
            "SYNAPSE_LEARNING_MODE_TRANSLATION",
        ]:
            os.environ.pop(key, None)

    def test_learning_instruction_appended_when_enabled(self):
        """SYNAPSE_LEARNING_MODE_ENABLED=true appends learning.md content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            synapse_dir = Path(tmpdir) / ".synapse"
            synapse_dir.mkdir()
            learning_file = synapse_dir / "learning.md"
            learning_file.write_text("LEARNING RULES\nAlways explain changes")

            settings = SynapseSettings(
                env={},
                instructions={"default": "Base instruction"},
            )

            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                os.environ["SYNAPSE_LEARNING_MODE_ENABLED"] = "true"
                result = settings.get_instruction("claude", "agent", 8100)
                assert "Base instruction" in result
                assert "LEARNING RULES" in result
                assert "Always explain changes" in result
            finally:
                os.chdir(original_cwd)

    def test_learning_instruction_appended_when_translation_only(self):
        """SYNAPSE_LEARNING_MODE_TRANSLATION=true alone appends learning.md."""
        with tempfile.TemporaryDirectory() as tmpdir:
            synapse_dir = Path(tmpdir) / ".synapse"
            synapse_dir.mkdir()
            learning_file = synapse_dir / "learning.md"
            learning_file.write_text("LEARNING RULES\nTranslation support")

            settings = SynapseSettings(
                env={},
                instructions={"default": "Base instruction"},
            )

            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                os.environ["SYNAPSE_LEARNING_MODE_TRANSLATION"] = "true"
                result = settings.get_instruction("claude", "agent", 8100)
                assert "Base instruction" in result
                assert "LEARNING RULES" in result
            finally:
                os.chdir(original_cwd)

    def test_learning_instruction_not_appended_when_disabled(self):
        """Learning instructions are not appended when both flags disabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            synapse_dir = Path(tmpdir) / ".synapse"
            synapse_dir.mkdir()
            learning_file = synapse_dir / "learning.md"
            learning_file.write_text("LEARNING RULES")

            settings = SynapseSettings(
                env={},
                instructions={"default": "Base instruction"},
            )

            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                result = settings.get_instruction("claude", "agent", 8100)
                assert result == "Base instruction"
                assert "LEARNING RULES" not in result
            finally:
                os.chdir(original_cwd)

    def test_learning_enabled_via_settings_env(self):
        """Learning mode can be enabled via settings env."""
        with tempfile.TemporaryDirectory() as tmpdir:
            synapse_dir = Path(tmpdir) / ".synapse"
            synapse_dir.mkdir()
            learning_file = synapse_dir / "learning.md"
            learning_file.write_text("LEARNING FROM SETTINGS")

            settings = SynapseSettings(
                env={"SYNAPSE_LEARNING_MODE_ENABLED": "true"},
                instructions={"default": "Base instruction"},
            )

            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                result = settings.get_instruction("claude", "agent", 8100)
                assert "Base instruction" in result
                assert "LEARNING FROM SETTINGS" in result
            finally:
                os.chdir(original_cwd)

    def test_env_var_takes_priority_over_settings(self):
        """Environment variable takes priority over settings env."""
        with tempfile.TemporaryDirectory() as tmpdir:
            synapse_dir = Path(tmpdir) / ".synapse"
            synapse_dir.mkdir()
            learning_file = synapse_dir / "learning.md"
            learning_file.write_text("LEARNING CONTENT")

            settings = SynapseSettings(
                env={"SYNAPSE_LEARNING_MODE_ENABLED": "false"},
                instructions={"default": "Base instruction"},
            )

            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                os.environ["SYNAPSE_LEARNING_MODE_ENABLED"] = "true"
                result = settings.get_instruction("claude", "agent", 8100)
                assert "Base instruction" in result
                assert "LEARNING CONTENT" in result
            finally:
                os.chdir(original_cwd)


class TestLearningModeTranslation:
    """Test conditional translation section handling."""

    def setup_method(self):
        """Clear environment variables that affect instruction generation."""
        for key in [
            "SYNAPSE_FILE_SAFETY_ENABLED",
            "SYNAPSE_LEARNING_MODE_ENABLED",
            "SYNAPSE_LEARNING_MODE_TRANSLATION",
        ]:
            os.environ.pop(key, None)

    def test_translation_section_included_when_both_enabled(self):
        """Translation section is included when both flags are enabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            synapse_dir = Path(tmpdir) / ".synapse"
            synapse_dir.mkdir()
            learning_file = synapse_dir / "learning.md"
            learning_file.write_text(
                "BASE\n{{#learning_translation}}TRANSLATION CONTENT{{/learning_translation}}"
            )

            settings = SynapseSettings(
                env={},
                instructions={"default": "Base instruction"},
            )

            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                os.environ["SYNAPSE_LEARNING_MODE_ENABLED"] = "true"
                os.environ["SYNAPSE_LEARNING_MODE_TRANSLATION"] = "true"
                result = settings.get_instruction("claude", "agent", 8100)
                assert "TRANSLATION CONTENT" in result
            finally:
                os.chdir(original_cwd)

    def test_translation_section_included_when_translation_only(self):
        """Translation section is included when only translation is enabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            synapse_dir = Path(tmpdir) / ".synapse"
            synapse_dir.mkdir()
            learning_file = synapse_dir / "learning.md"
            learning_file.write_text(
                "BASE\n{{#learning_translation}}TRANSLATION CONTENT{{/learning_translation}}"
            )

            settings = SynapseSettings(
                env={},
                instructions={"default": "Base instruction"},
            )

            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                os.environ["SYNAPSE_LEARNING_MODE_TRANSLATION"] = "true"
                result = settings.get_instruction("claude", "agent", 8100)
                assert "TRANSLATION CONTENT" in result
            finally:
                os.chdir(original_cwd)

    def test_translation_section_excluded_when_only_learning_mode(self):
        """Translation section is excluded when only learning mode is enabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            synapse_dir = Path(tmpdir) / ".synapse"
            synapse_dir.mkdir()
            learning_file = synapse_dir / "learning.md"
            learning_file.write_text(
                "BASE\n{{#learning_translation}}TRANSLATION CONTENT{{/learning_translation}}"
            )

            settings = SynapseSettings(
                env={},
                instructions={"default": "Base instruction"},
            )

            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                os.environ["SYNAPSE_LEARNING_MODE_ENABLED"] = "true"
                result = settings.get_instruction("claude", "agent", 8100)
                assert "TRANSLATION CONTENT" not in result
            finally:
                os.chdir(original_cwd)

    def test_translation_works_independently_without_learning_mode(self):
        """Translation alone injects learning.md with translation sections."""
        with tempfile.TemporaryDirectory() as tmpdir:
            synapse_dir = Path(tmpdir) / ".synapse"
            synapse_dir.mkdir()
            learning_file = synapse_dir / "learning.md"
            learning_file.write_text(
                "BASE\n{{#learning_translation}}TRANSLATION CONTENT{{/learning_translation}}"
                "\n{{#learning_mode}}PROMPT IMPROVEMENT{{/learning_mode}}"
            )

            settings = SynapseSettings(
                env={},
                instructions={"default": "Base instruction"},
            )

            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                os.environ["SYNAPSE_LEARNING_MODE_TRANSLATION"] = "true"
                result = settings.get_instruction("claude", "agent", 8100)
                assert "Base instruction" in result
                assert "TRANSLATION CONTENT" in result
                assert "PROMPT IMPROVEMENT" not in result
            finally:
                os.chdir(original_cwd)

    def test_learning_mode_without_translation(self):
        """Learning mode alone includes prompt improvement but not translation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            synapse_dir = Path(tmpdir) / ".synapse"
            synapse_dir.mkdir()
            learning_file = synapse_dir / "learning.md"
            learning_file.write_text(
                "BASE\n{{#learning_translation}}TRANSLATION CONTENT{{/learning_translation}}"
                "\n{{#learning_mode}}PROMPT IMPROVEMENT{{/learning_mode}}"
            )

            settings = SynapseSettings(
                env={},
                instructions={"default": "Base instruction"},
            )

            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                os.environ["SYNAPSE_LEARNING_MODE_ENABLED"] = "true"
                result = settings.get_instruction("claude", "agent", 8100)
                assert "Base instruction" in result
                assert "PROMPT IMPROVEMENT" in result
                assert "TRANSLATION CONTENT" not in result
            finally:
                os.chdir(original_cwd)


class TestLearningModeFilePaths:
    """Test learning.md appears in instruction file listings when enabled."""

    def setup_method(self):
        """Clear environment variables that affect instruction generation."""
        for key in [
            "SYNAPSE_FILE_SAFETY_ENABLED",
            "SYNAPSE_LEARNING_MODE_ENABLED",
            "SYNAPSE_LEARNING_MODE_TRANSLATION",
        ]:
            os.environ.pop(key, None)

    def test_learning_md_in_instruction_files_when_learning_enabled(self):
        """get_instruction_files() includes learning.md when learning mode enabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            synapse_dir = Path(tmpdir) / ".synapse"
            synapse_dir.mkdir()
            learning_file = synapse_dir / "learning.md"
            learning_file.write_text("LEARNING")

            settings = SynapseSettings(
                env={},
                instructions={"default": "Base instruction"},
            )

            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                os.environ["SYNAPSE_LEARNING_MODE_ENABLED"] = "true"
                files = settings.get_instruction_files("claude")
                assert "learning.md" in files
            finally:
                os.chdir(original_cwd)

    def test_learning_md_in_instruction_files_when_translation_only(self):
        """get_instruction_files() includes learning.md when only translation enabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            synapse_dir = Path(tmpdir) / ".synapse"
            synapse_dir.mkdir()
            learning_file = synapse_dir / "learning.md"
            learning_file.write_text("LEARNING")

            settings = SynapseSettings(
                env={},
                instructions={"default": "Base instruction"},
            )

            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                os.environ["SYNAPSE_LEARNING_MODE_TRANSLATION"] = "true"
                files = settings.get_instruction_files("claude")
                assert "learning.md" in files
            finally:
                os.chdir(original_cwd)

    def test_learning_md_not_in_instruction_files_when_disabled(self):
        """get_instruction_files() does not include learning.md when disabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            synapse_dir = Path(tmpdir) / ".synapse"
            synapse_dir.mkdir()
            learning_file = synapse_dir / "learning.md"
            learning_file.write_text("LEARNING")

            settings = SynapseSettings(
                env={},
                instructions={"default": "Base instruction"},
            )

            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                files = settings.get_instruction_files("claude")
                assert "learning.md" not in files
            finally:
                os.chdir(original_cwd)

    def test_learning_md_in_file_paths_when_learning_enabled(self):
        """get_instruction_file_paths() includes .synapse/learning.md when learning enabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            synapse_dir = Path(tmpdir) / ".synapse"
            synapse_dir.mkdir()
            learning_file = synapse_dir / "learning.md"
            learning_file.write_text("LEARNING")

            settings = SynapseSettings(
                env={},
                instructions={"default": "Base instruction"},
            )

            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                os.environ["SYNAPSE_LEARNING_MODE_ENABLED"] = "true"
                paths = settings.get_instruction_file_paths("claude")
                assert ".synapse/learning.md" in paths
            finally:
                os.chdir(original_cwd)

    def test_learning_md_in_file_paths_when_translation_only(self):
        """get_instruction_file_paths() includes .synapse/learning.md when translation only."""
        with tempfile.TemporaryDirectory() as tmpdir:
            synapse_dir = Path(tmpdir) / ".synapse"
            synapse_dir.mkdir()
            learning_file = synapse_dir / "learning.md"
            learning_file.write_text("LEARNING")

            settings = SynapseSettings(
                env={},
                instructions={"default": "Base instruction"},
            )

            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                os.environ["SYNAPSE_LEARNING_MODE_TRANSLATION"] = "true"
                paths = settings.get_instruction_file_paths("claude")
                assert ".synapse/learning.md" in paths
            finally:
                os.chdir(original_cwd)


class TestLearningModeConfigTUI:
    """Test Config TUI learning mode environment variables."""

    def setup_method(self):
        """Clear environment variables that affect instruction generation."""
        for key in [
            "SYNAPSE_FILE_SAFETY_ENABLED",
            "SYNAPSE_LEARNING_MODE_ENABLED",
            "SYNAPSE_LEARNING_MODE_TRANSLATION",
        ]:
            os.environ.pop(key, None)

    def test_boolean_env_vars_includes_learning_mode(self):
        """BOOLEAN_ENV_VARS includes learning mode settings."""
        from synapse.commands.config import BOOLEAN_ENV_VARS

        assert "SYNAPSE_LEARNING_MODE_ENABLED" in BOOLEAN_ENV_VARS
        assert "SYNAPSE_LEARNING_MODE_TRANSLATION" in BOOLEAN_ENV_VARS


class TestLearningTemplateStructure:
    """Test learning template structure and sync expectations."""

    def test_response_section_is_not_numbered_in_template(self):
        """Main response section should not be numbered like learning feedback."""
        template = Path("synapse/templates/.synapse/learning.md").read_text(
            encoding="utf-8"
        )
        assert "[1] 💬 RESPONSE" not in template
        assert "💬 RESPONSE" in template

    def test_project_learning_md_is_synced_from_template(self):
        """Project .synapse/learning.md should stay in sync with template."""
        template = Path("synapse/templates/.synapse/learning.md").read_text(
            encoding="utf-8"
        )
        project_copy = Path(".synapse/learning.md").read_text(encoding="utf-8")
        assert project_copy == template
