"""Tests for learning mode settings and instruction injection."""

import tempfile
from pathlib import Path

import pytest

from synapse.settings import (
    DEFAULT_SETTINGS,
    SynapseSettings,
)

_ENV_KEYS = [
    "SYNAPSE_FILE_SAFETY_ENABLED",
    "SYNAPSE_LEARNING_MODE_ENABLED",
    "SYNAPSE_LEARNING_MODE_TRANSLATION",
]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Remove learning-mode env vars so each test starts from a clean slate."""
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


class TestLearningModeSettings:
    """Test default learning mode settings."""

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

    def test_learning_instruction_appended_when_enabled(self, monkeypatch):
        """SYNAPSE_LEARNING_MODE_ENABLED=true appends learning.md content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            synapse_dir = Path(tmpdir) / ".synapse"
            synapse_dir.mkdir()
            (synapse_dir / "learning.md").write_text(
                "LEARNING RULES\nAlways explain changes"
            )

            settings = SynapseSettings(
                env={},
                instructions={"default": "Base instruction"},
            )

            monkeypatch.chdir(tmpdir)
            monkeypatch.setenv("SYNAPSE_LEARNING_MODE_ENABLED", "true")
            result = settings.get_instruction("claude", "agent", 8100)
            assert "Base instruction" in result
            assert "LEARNING RULES" in result
            assert "Always explain changes" in result

    def test_learning_instruction_appended_when_translation_only(self, monkeypatch):
        """SYNAPSE_LEARNING_MODE_TRANSLATION=true alone appends learning.md."""
        with tempfile.TemporaryDirectory() as tmpdir:
            synapse_dir = Path(tmpdir) / ".synapse"
            synapse_dir.mkdir()
            (synapse_dir / "learning.md").write_text(
                "LEARNING RULES\nTranslation support"
            )

            settings = SynapseSettings(
                env={},
                instructions={"default": "Base instruction"},
            )

            monkeypatch.chdir(tmpdir)
            monkeypatch.setenv("SYNAPSE_LEARNING_MODE_TRANSLATION", "true")
            result = settings.get_instruction("claude", "agent", 8100)
            assert "Base instruction" in result
            assert "LEARNING RULES" in result

    def test_learning_instruction_not_appended_when_disabled(self, monkeypatch):
        """Learning instructions are not appended when both flags disabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            synapse_dir = Path(tmpdir) / ".synapse"
            synapse_dir.mkdir()
            (synapse_dir / "learning.md").write_text("LEARNING RULES")

            settings = SynapseSettings(
                env={},
                instructions={"default": "Base instruction"},
            )

            monkeypatch.chdir(tmpdir)
            result = settings.get_instruction("claude", "agent", 8100)
            assert result == "Base instruction"
            assert "LEARNING RULES" not in result

    def test_learning_enabled_via_settings_env(self, monkeypatch):
        """Learning mode can be enabled via settings env."""
        with tempfile.TemporaryDirectory() as tmpdir:
            synapse_dir = Path(tmpdir) / ".synapse"
            synapse_dir.mkdir()
            (synapse_dir / "learning.md").write_text("LEARNING FROM SETTINGS")

            settings = SynapseSettings(
                env={"SYNAPSE_LEARNING_MODE_ENABLED": "true"},
                instructions={"default": "Base instruction"},
            )

            monkeypatch.chdir(tmpdir)
            result = settings.get_instruction("claude", "agent", 8100)
            assert "Base instruction" in result
            assert "LEARNING FROM SETTINGS" in result

    def test_env_var_takes_priority_over_settings(self, monkeypatch):
        """Environment variable takes priority over settings env."""
        with tempfile.TemporaryDirectory() as tmpdir:
            synapse_dir = Path(tmpdir) / ".synapse"
            synapse_dir.mkdir()
            (synapse_dir / "learning.md").write_text("LEARNING CONTENT")

            settings = SynapseSettings(
                env={"SYNAPSE_LEARNING_MODE_ENABLED": "false"},
                instructions={"default": "Base instruction"},
            )

            monkeypatch.chdir(tmpdir)
            monkeypatch.setenv("SYNAPSE_LEARNING_MODE_ENABLED", "true")
            result = settings.get_instruction("claude", "agent", 8100)
            assert "Base instruction" in result
            assert "LEARNING CONTENT" in result


class TestLearningModeTranslation:
    """Test conditional translation section handling."""

    def test_translation_section_included_when_both_enabled(self, monkeypatch):
        """Translation section is included when both flags are enabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            synapse_dir = Path(tmpdir) / ".synapse"
            synapse_dir.mkdir()
            (synapse_dir / "learning.md").write_text(
                "BASE\n{{#learning_translation}}TRANSLATION CONTENT{{/learning_translation}}"
            )

            settings = SynapseSettings(
                env={},
                instructions={"default": "Base instruction"},
            )

            monkeypatch.chdir(tmpdir)
            monkeypatch.setenv("SYNAPSE_LEARNING_MODE_ENABLED", "true")
            monkeypatch.setenv("SYNAPSE_LEARNING_MODE_TRANSLATION", "true")
            result = settings.get_instruction("claude", "agent", 8100)
            assert "TRANSLATION CONTENT" in result

    def test_translation_section_included_when_translation_only(self, monkeypatch):
        """Translation section is included when only translation is enabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            synapse_dir = Path(tmpdir) / ".synapse"
            synapse_dir.mkdir()
            (synapse_dir / "learning.md").write_text(
                "BASE\n{{#learning_translation}}TRANSLATION CONTENT{{/learning_translation}}"
            )

            settings = SynapseSettings(
                env={},
                instructions={"default": "Base instruction"},
            )

            monkeypatch.chdir(tmpdir)
            monkeypatch.setenv("SYNAPSE_LEARNING_MODE_TRANSLATION", "true")
            result = settings.get_instruction("claude", "agent", 8100)
            assert "TRANSLATION CONTENT" in result

    def test_translation_section_excluded_when_only_learning_mode(self, monkeypatch):
        """Translation section is excluded when only learning mode is enabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            synapse_dir = Path(tmpdir) / ".synapse"
            synapse_dir.mkdir()
            (synapse_dir / "learning.md").write_text(
                "BASE\n{{#learning_translation}}TRANSLATION CONTENT{{/learning_translation}}"
            )

            settings = SynapseSettings(
                env={},
                instructions={"default": "Base instruction"},
            )

            monkeypatch.chdir(tmpdir)
            monkeypatch.setenv("SYNAPSE_LEARNING_MODE_ENABLED", "true")
            result = settings.get_instruction("claude", "agent", 8100)
            assert "TRANSLATION CONTENT" not in result

    def test_translation_works_independently_without_learning_mode(self, monkeypatch):
        """Translation alone injects learning.md with translation sections."""
        with tempfile.TemporaryDirectory() as tmpdir:
            synapse_dir = Path(tmpdir) / ".synapse"
            synapse_dir.mkdir()
            (synapse_dir / "learning.md").write_text(
                "BASE\n{{#learning_translation}}TRANSLATION CONTENT{{/learning_translation}}"
                "\n{{#learning_mode}}PROMPT IMPROVEMENT{{/learning_mode}}"
            )

            settings = SynapseSettings(
                env={},
                instructions={"default": "Base instruction"},
            )

            monkeypatch.chdir(tmpdir)
            monkeypatch.setenv("SYNAPSE_LEARNING_MODE_TRANSLATION", "true")
            result = settings.get_instruction("claude", "agent", 8100)
            assert "Base instruction" in result
            assert "TRANSLATION CONTENT" in result
            assert "PROMPT IMPROVEMENT" not in result

    def test_learning_mode_without_translation(self, monkeypatch):
        """Learning mode alone includes prompt improvement but not translation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            synapse_dir = Path(tmpdir) / ".synapse"
            synapse_dir.mkdir()
            (synapse_dir / "learning.md").write_text(
                "BASE\n{{#learning_translation}}TRANSLATION CONTENT{{/learning_translation}}"
                "\n{{#learning_mode}}PROMPT IMPROVEMENT{{/learning_mode}}"
            )

            settings = SynapseSettings(
                env={},
                instructions={"default": "Base instruction"},
            )

            monkeypatch.chdir(tmpdir)
            monkeypatch.setenv("SYNAPSE_LEARNING_MODE_ENABLED", "true")
            result = settings.get_instruction("claude", "agent", 8100)
            assert "Base instruction" in result
            assert "PROMPT IMPROVEMENT" in result
            assert "TRANSLATION CONTENT" not in result


class TestLearningModeFilePaths:
    """Test learning.md appears in instruction file listings when enabled."""

    def test_learning_md_in_instruction_files_when_learning_enabled(self, monkeypatch):
        """get_instruction_files() includes learning.md when learning mode enabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            synapse_dir = Path(tmpdir) / ".synapse"
            synapse_dir.mkdir()
            (synapse_dir / "learning.md").write_text("LEARNING")

            settings = SynapseSettings(
                env={},
                instructions={"default": "Base instruction"},
            )

            monkeypatch.chdir(tmpdir)
            monkeypatch.setenv("SYNAPSE_LEARNING_MODE_ENABLED", "true")
            files = settings.get_instruction_files("claude")
            assert "learning.md" in files

    def test_learning_md_in_instruction_files_when_translation_only(self, monkeypatch):
        """get_instruction_files() includes learning.md when only translation enabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            synapse_dir = Path(tmpdir) / ".synapse"
            synapse_dir.mkdir()
            (synapse_dir / "learning.md").write_text("LEARNING")

            settings = SynapseSettings(
                env={},
                instructions={"default": "Base instruction"},
            )

            monkeypatch.chdir(tmpdir)
            monkeypatch.setenv("SYNAPSE_LEARNING_MODE_TRANSLATION", "true")
            files = settings.get_instruction_files("claude")
            assert "learning.md" in files

    def test_learning_md_not_in_instruction_files_when_disabled(self, monkeypatch):
        """get_instruction_files() does not include learning.md when disabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            synapse_dir = Path(tmpdir) / ".synapse"
            synapse_dir.mkdir()
            (synapse_dir / "learning.md").write_text("LEARNING")

            settings = SynapseSettings(
                env={},
                instructions={"default": "Base instruction"},
            )

            monkeypatch.chdir(tmpdir)
            files = settings.get_instruction_files("claude")
            assert "learning.md" not in files

    def test_learning_md_in_file_paths_when_learning_enabled(self, monkeypatch):
        """get_instruction_file_paths() includes .synapse/learning.md when learning enabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            synapse_dir = Path(tmpdir) / ".synapse"
            synapse_dir.mkdir()
            (synapse_dir / "learning.md").write_text("LEARNING")

            settings = SynapseSettings(
                env={},
                instructions={"default": "Base instruction"},
            )

            monkeypatch.chdir(tmpdir)
            monkeypatch.setenv("SYNAPSE_LEARNING_MODE_ENABLED", "true")
            paths = settings.get_instruction_file_paths("claude")
            assert ".synapse/learning.md" in paths

    def test_learning_md_in_file_paths_when_translation_only(self, monkeypatch):
        """get_instruction_file_paths() includes .synapse/learning.md when translation only."""
        with tempfile.TemporaryDirectory() as tmpdir:
            synapse_dir = Path(tmpdir) / ".synapse"
            synapse_dir.mkdir()
            (synapse_dir / "learning.md").write_text("LEARNING")

            settings = SynapseSettings(
                env={},
                instructions={"default": "Base instruction"},
            )

            monkeypatch.chdir(tmpdir)
            monkeypatch.setenv("SYNAPSE_LEARNING_MODE_TRANSLATION", "true")
            paths = settings.get_instruction_file_paths("claude")
            assert ".synapse/learning.md" in paths


class TestLearningModeConfigTUI:
    """Test Config TUI learning mode environment variables."""

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
