"""Tests for proactive mode settings and instruction injection."""

import tempfile
from pathlib import Path

import pytest

from synapse.settings import (
    DEFAULT_SETTINGS,
    SynapseSettings,
)

_ENV_KEYS = [
    "SYNAPSE_PROACTIVE_MODE_ENABLED",
    "SYNAPSE_LEARNING_MODE_ENABLED",
    "SYNAPSE_LEARNING_MODE_TRANSLATION",
    "SYNAPSE_FILE_SAFETY_ENABLED",
    "SYNAPSE_SHARED_MEMORY_ENABLED",
]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Remove proactive/learning-mode env vars so each test starts from a clean slate."""
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


class TestProactiveModeSettings:
    """Test default proactive mode settings."""

    def test_default_settings_has_proactive_mode_env_var(self):
        """DEFAULT_SETTINGS['env'] has proactive mode key."""
        assert "SYNAPSE_PROACTIVE_MODE_ENABLED" in DEFAULT_SETTINGS["env"]

    def test_default_proactive_mode_disabled(self):
        """Proactive mode is disabled by default."""
        assert DEFAULT_SETTINGS["env"]["SYNAPSE_PROACTIVE_MODE_ENABLED"] == "false"


class TestProactiveModeInstructionInjection:
    """Test optional proactive instruction loading."""

    def test_proactive_instruction_appended_when_enabled(self, monkeypatch):
        """SYNAPSE_PROACTIVE_MODE_ENABLED=true appends proactive.md content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            synapse_dir = Path(tmpdir) / ".synapse"
            synapse_dir.mkdir()
            (synapse_dir / "proactive.md").write_text(
                "PROACTIVE RULES\nAlways use task board"
            )

            settings = SynapseSettings(
                env={},
                instructions={"default": "Base instruction"},
            )

            monkeypatch.chdir(tmpdir)
            monkeypatch.setenv("SYNAPSE_PROACTIVE_MODE_ENABLED", "true")
            result = settings.get_instruction("claude", "agent", 8100)
            assert "Base instruction" in result
            assert "PROACTIVE RULES" in result
            assert "Always use task board" in result

    def test_proactive_instruction_not_appended_when_disabled(self, monkeypatch):
        """Proactive instructions are not appended when flag is disabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            synapse_dir = Path(tmpdir) / ".synapse"
            synapse_dir.mkdir()
            (synapse_dir / "proactive.md").write_text("PROACTIVE RULES")

            settings = SynapseSettings(
                env={},
                instructions={"default": "Base instruction"},
            )

            monkeypatch.chdir(tmpdir)
            result = settings.get_instruction("claude", "agent", 8100)
            assert result == "Base instruction"
            assert "PROACTIVE RULES" not in result

    def test_proactive_enabled_via_settings_env(self, monkeypatch):
        """Proactive mode can be enabled via settings env."""
        with tempfile.TemporaryDirectory() as tmpdir:
            synapse_dir = Path(tmpdir) / ".synapse"
            synapse_dir.mkdir()
            (synapse_dir / "proactive.md").write_text("PROACTIVE FROM SETTINGS")

            settings = SynapseSettings(
                env={"SYNAPSE_PROACTIVE_MODE_ENABLED": "true"},
                instructions={"default": "Base instruction"},
            )

            monkeypatch.chdir(tmpdir)
            result = settings.get_instruction("claude", "agent", 8100)
            assert "Base instruction" in result
            assert "PROACTIVE FROM SETTINGS" in result

    def test_env_var_takes_priority_over_settings(self, monkeypatch):
        """Environment variable takes priority over settings env."""
        with tempfile.TemporaryDirectory() as tmpdir:
            synapse_dir = Path(tmpdir) / ".synapse"
            synapse_dir.mkdir()
            (synapse_dir / "proactive.md").write_text("PROACTIVE CONTENT")

            settings = SynapseSettings(
                env={"SYNAPSE_PROACTIVE_MODE_ENABLED": "false"},
                instructions={"default": "Base instruction"},
            )

            monkeypatch.chdir(tmpdir)
            monkeypatch.setenv("SYNAPSE_PROACTIVE_MODE_ENABLED", "true")
            result = settings.get_instruction("claude", "agent", 8100)
            assert "Base instruction" in result
            assert "PROACTIVE CONTENT" in result


class TestProactiveModeFileList:
    """Test proactive.md appears in instruction file listings when enabled."""

    def test_proactive_md_in_instruction_files_when_enabled(self, monkeypatch):
        """get_instruction_files() includes proactive.md when proactive mode enabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            synapse_dir = Path(tmpdir) / ".synapse"
            synapse_dir.mkdir()
            (synapse_dir / "proactive.md").write_text("PROACTIVE")

            settings = SynapseSettings(
                env={},
                instructions={"default": "Base instruction"},
            )

            monkeypatch.chdir(tmpdir)
            monkeypatch.setenv("SYNAPSE_PROACTIVE_MODE_ENABLED", "true")
            files = settings.get_instruction_files("claude")
            assert "proactive.md" in files

    def test_proactive_md_not_in_instruction_files_when_disabled(self, monkeypatch):
        """get_instruction_files() does not include proactive.md when disabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            synapse_dir = Path(tmpdir) / ".synapse"
            synapse_dir.mkdir()
            (synapse_dir / "proactive.md").write_text("PROACTIVE")

            settings = SynapseSettings(
                env={},
                instructions={"default": "Base instruction"},
            )

            monkeypatch.chdir(tmpdir)
            files = settings.get_instruction_files("claude")
            assert "proactive.md" not in files

    def test_proactive_md_in_file_paths_when_enabled(self, monkeypatch):
        """get_instruction_file_paths() includes .synapse/proactive.md when enabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            synapse_dir = Path(tmpdir) / ".synapse"
            synapse_dir.mkdir()
            (synapse_dir / "proactive.md").write_text("PROACTIVE")

            settings = SynapseSettings(
                env={},
                instructions={"default": "Base instruction"},
            )

            monkeypatch.chdir(tmpdir)
            monkeypatch.setenv("SYNAPSE_PROACTIVE_MODE_ENABLED", "true")
            paths = settings.get_instruction_file_paths("claude")
            assert ".synapse/proactive.md" in paths


class TestProactiveModeTemplateExists:
    """Test proactive template structure."""

    def test_template_file_exists(self):
        """Template proactive.md exists in synapse/templates/.synapse/."""
        template = Path("synapse/templates/.synapse/proactive.md")
        assert template.exists(), "Template proactive.md must exist"

    def test_template_has_required_sections(self):
        """Template proactive.md contains required sections."""
        template = Path("synapse/templates/.synapse/proactive.md").read_text(
            encoding="utf-8"
        )
        assert "BEFORE" in template
        assert "DURING" in template
        assert "AFTER" in template
        assert "synapse tasks" in template
        assert "synapse memory" in template

    def test_project_proactive_md_is_synced_from_template(self):
        """Project .synapse/proactive.md should stay in sync with template."""
        template = Path("synapse/templates/.synapse/proactive.md").read_text(
            encoding="utf-8"
        )
        project_copy = Path(".synapse/proactive.md").read_text(encoding="utf-8")
        assert project_copy == template


class TestProactiveModeIndependence:
    """Test proactive mode is independent of learning mode."""

    def test_proactive_and_learning_can_coexist(self, monkeypatch):
        """Both proactive and learning mode can be enabled simultaneously."""
        with tempfile.TemporaryDirectory() as tmpdir:
            synapse_dir = Path(tmpdir) / ".synapse"
            synapse_dir.mkdir()
            (synapse_dir / "proactive.md").write_text("PROACTIVE CONTENT")
            (synapse_dir / "learning.md").write_text("LEARNING CONTENT")

            settings = SynapseSettings(
                env={},
                instructions={"default": "Base instruction"},
            )

            monkeypatch.chdir(tmpdir)
            monkeypatch.setenv("SYNAPSE_PROACTIVE_MODE_ENABLED", "true")
            monkeypatch.setenv("SYNAPSE_LEARNING_MODE_ENABLED", "true")
            result = settings.get_instruction("claude", "agent", 8100)
            assert "Base instruction" in result
            assert "PROACTIVE CONTENT" in result
            assert "LEARNING CONTENT" in result

    def test_proactive_without_learning(self, monkeypatch):
        """Proactive mode works independently without learning mode."""
        with tempfile.TemporaryDirectory() as tmpdir:
            synapse_dir = Path(tmpdir) / ".synapse"
            synapse_dir.mkdir()
            (synapse_dir / "proactive.md").write_text("PROACTIVE ONLY")
            (synapse_dir / "learning.md").write_text("LEARNING ONLY")

            settings = SynapseSettings(
                env={},
                instructions={"default": "Base instruction"},
            )

            monkeypatch.chdir(tmpdir)
            monkeypatch.setenv("SYNAPSE_PROACTIVE_MODE_ENABLED", "true")
            result = settings.get_instruction("claude", "agent", 8100)
            assert "PROACTIVE ONLY" in result
            assert "LEARNING ONLY" not in result

    def test_learning_without_proactive(self, monkeypatch):
        """Learning mode works independently without proactive mode."""
        with tempfile.TemporaryDirectory() as tmpdir:
            synapse_dir = Path(tmpdir) / ".synapse"
            synapse_dir.mkdir()
            (synapse_dir / "proactive.md").write_text("PROACTIVE ONLY")
            (synapse_dir / "learning.md").write_text("LEARNING ONLY")

            settings = SynapseSettings(
                env={},
                instructions={"default": "Base instruction"},
            )

            monkeypatch.chdir(tmpdir)
            monkeypatch.setenv("SYNAPSE_LEARNING_MODE_ENABLED", "true")
            result = settings.get_instruction("claude", "agent", 8100)
            assert "LEARNING ONLY" in result
            assert "PROACTIVE ONLY" not in result
