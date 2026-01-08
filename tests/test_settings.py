"""Tests for synapse.settings module."""

import json
import os
import tempfile
from pathlib import Path

from synapse.settings import (
    DEFAULT_SETTINGS,
    SynapseSettings,
    get_default_instructions,
    get_gemini_instructions,
    load_settings,
    merge_settings,
)


class TestDefaultSettings:
    """Test default settings structure."""

    def test_default_settings_has_env(self):
        """Default settings should have env section."""
        assert "env" in DEFAULT_SETTINGS
        assert isinstance(DEFAULT_SETTINGS["env"], dict)

    def test_default_settings_has_instructions(self):
        """Default settings should have instructions section."""
        assert "instructions" in DEFAULT_SETTINGS
        assert isinstance(DEFAULT_SETTINGS["instructions"], dict)

    def test_default_env_has_required_keys(self):
        """Default env should have all required keys."""
        required_keys = [
            "SYNAPSE_HISTORY_ENABLED",
            "SYNAPSE_AUTH_ENABLED",
            "SYNAPSE_API_KEYS",
            "SYNAPSE_ADMIN_KEY",
            "SYNAPSE_ALLOW_LOCALHOST",
            "SYNAPSE_USE_HTTPS",
            "SYNAPSE_WEBHOOK_SECRET",
            "SYNAPSE_WEBHOOK_TIMEOUT",
            "SYNAPSE_WEBHOOK_MAX_RETRIES",
        ]
        for key in required_keys:
            assert key in DEFAULT_SETTINGS["env"]

    def test_default_instructions_has_agent_keys(self):
        """Default instructions should have default and agent-specific keys."""
        assert "default" in DEFAULT_SETTINGS["instructions"]
        assert "claude" in DEFAULT_SETTINGS["instructions"]
        assert "gemini" in DEFAULT_SETTINGS["instructions"]
        assert "codex" in DEFAULT_SETTINGS["instructions"]

    def test_gemini_instructions_no_skill(self):
        """Gemini instructions should not contain SKILL line."""
        gemini_instructions = get_gemini_instructions()
        assert "SKILL:" not in gemini_instructions
        assert "synapse-a2a skill" not in gemini_instructions

    def test_default_instructions_has_skill(self):
        """Default instructions should contain SKILL line."""
        default_instructions = get_default_instructions()
        assert "SKILL:" in default_instructions
        assert "synapse-a2a skill" in default_instructions


class TestMergeSettings:
    """Test settings merge logic."""

    def test_merge_empty_with_defaults(self):
        """Merging empty settings with defaults returns defaults."""
        result = merge_settings({}, DEFAULT_SETTINGS)
        assert result == DEFAULT_SETTINGS

    def test_merge_overwrites_env(self):
        """Higher priority settings overwrite env values."""
        base = {"env": {"KEY1": "base", "KEY2": "base"}}
        override = {"env": {"KEY1": "override"}}
        result = merge_settings(base, override)
        assert result["env"]["KEY1"] == "override"
        assert result["env"]["KEY2"] == "base"

    def test_merge_overwrites_instructions(self):
        """Higher priority settings overwrite instruction values."""
        base = {"instructions": {"default": "base", "claude": "base"}}
        override = {"instructions": {"claude": "override"}}
        result = merge_settings(base, override)
        assert result["instructions"]["default"] == "base"
        assert result["instructions"]["claude"] == "override"

    def test_merge_preserves_unset_keys(self):
        """Merge preserves keys not in override."""
        base = {"env": {"KEY1": "value"}, "instructions": {"default": "text"}}
        override = {"env": {"KEY2": "new"}}
        result = merge_settings(base, override)
        assert result["env"]["KEY1"] == "value"
        assert result["env"]["KEY2"] == "new"
        assert result["instructions"]["default"] == "text"


class TestLoadSettings:
    """Test settings loading from files."""

    def test_load_nonexistent_returns_empty(self):
        """Loading nonexistent file returns empty dict."""
        result = load_settings(Path("/nonexistent/path/settings.json"))
        assert result == {}

    def test_load_valid_json(self):
        """Loading valid JSON file returns parsed content."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"env": {"TEST": "value"}}, f)
            f.flush()
            try:
                result = load_settings(Path(f.name))
                assert result == {"env": {"TEST": "value"}}
            finally:
                os.unlink(f.name)

    def test_load_invalid_json_returns_empty(self):
        """Loading invalid JSON file returns empty dict."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("not valid json {{{")
            f.flush()
            try:
                result = load_settings(Path(f.name))
                assert result == {}
            finally:
                os.unlink(f.name)


class TestSynapseSettings:
    """Test SynapseSettings class."""

    def test_from_defaults(self):
        """Create settings from defaults."""
        settings = SynapseSettings.from_defaults()
        assert settings.env["SYNAPSE_HISTORY_ENABLED"] == "false"
        assert "default" in settings.instructions

    def test_get_instruction_for_agent_specific(self):
        """Get instruction returns agent-specific when set."""
        settings = SynapseSettings(
            env={},
            instructions={
                "default": "default text",
                "claude": "claude text",
            },
        )
        result = settings.get_instruction("claude", "agent-id", 8100)
        assert result == "claude text"

    def test_get_instruction_falls_back_to_default(self):
        """Get instruction falls back to default when agent-specific empty."""
        settings = SynapseSettings(
            env={},
            instructions={
                "default": "default text",
                "claude": "",
            },
        )
        result = settings.get_instruction("claude", "agent-id", 8100)
        assert result == "default text"

    def test_get_instruction_returns_none_when_all_empty(self):
        """Get instruction returns None when both empty."""
        settings = SynapseSettings(
            env={},
            instructions={
                "default": "",
                "claude": "",
            },
        )
        result = settings.get_instruction("claude", "agent-id", 8100)
        assert result is None

    def test_get_instruction_replaces_placeholders(self):
        """Get instruction replaces placeholders."""
        settings = SynapseSettings(
            env={},
            instructions={
                "default": "Agent: {{agent_id}} Port: {{port}}",
            },
        )
        result = settings.get_instruction("claude", "synapse-claude-8100", 8100)
        assert result == "Agent: synapse-claude-8100 Port: 8100"

    def test_load_with_scope_merging(self):
        """Test loading settings with scope merging."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create user settings
            user_dir = Path(tmpdir) / "user" / ".synapse"
            user_dir.mkdir(parents=True)
            user_settings = {"env": {"SYNAPSE_HISTORY_ENABLED": "true"}}
            (user_dir / "settings.json").write_text(json.dumps(user_settings))

            # Create project settings
            project_dir = Path(tmpdir) / "project" / ".synapse"
            project_dir.mkdir(parents=True)
            project_settings = {"env": {"SYNAPSE_AUTH_ENABLED": "true"}}
            (project_dir / "settings.json").write_text(json.dumps(project_settings))

            # Load with custom paths
            settings = SynapseSettings.load(
                user_path=user_dir / "settings.json",
                project_path=project_dir / "settings.json",
            )

            # Both should be merged
            assert settings.env.get("SYNAPSE_HISTORY_ENABLED") == "true"
            assert settings.env.get("SYNAPSE_AUTH_ENABLED") == "true"

    def test_local_overrides_project(self):
        """Test that local settings override project settings."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / ".synapse"
            project_dir.mkdir(parents=True)

            # Project says history disabled
            project_settings = {"env": {"SYNAPSE_HISTORY_ENABLED": "false"}}
            (project_dir / "settings.json").write_text(json.dumps(project_settings))

            # Local says history enabled
            local_settings = {"env": {"SYNAPSE_HISTORY_ENABLED": "true"}}
            (project_dir / "settings.local.json").write_text(json.dumps(local_settings))

            settings = SynapseSettings.load(
                project_path=project_dir / "settings.json",
                local_path=project_dir / "settings.local.json",
            )

            # Local should win
            assert settings.env.get("SYNAPSE_HISTORY_ENABLED") == "true"


class TestInstructionPlaceholders:
    """Test instruction placeholder replacement."""

    def test_agent_id_placeholder(self):
        """{{agent_id}} is replaced with actual agent ID."""
        settings = SynapseSettings(
            env={},
            instructions={"default": "ID: {{agent_id}}"},
        )
        result = settings.get_instruction("claude", "synapse-claude-8100", 8100)
        assert result == "ID: synapse-claude-8100"

    def test_port_placeholder(self):
        """{{port}} is replaced with actual port."""
        settings = SynapseSettings(
            env={},
            instructions={"default": "Port: {{port}}"},
        )
        result = settings.get_instruction("claude", "test-agent", 9999)
        assert result == "Port: 9999"

    def test_multiple_placeholders(self):
        """Multiple placeholders are all replaced."""
        settings = SynapseSettings(
            env={},
            instructions={"default": "{{agent_id}} on {{port}}, again {{agent_id}}"},
        )
        result = settings.get_instruction("claude", "my-agent", 1234)
        assert result == "my-agent on 1234, again my-agent"


class TestSkillInstallation:
    """Test skill installation functionality."""

    def test_install_skills_to_dir(self):
        """Test _install_skills_to_dir creates skills in .claude and .codex."""
        from synapse.cli import _install_skills_to_dir

        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)

            # Install skills
            installed = _install_skills_to_dir(base_dir, force=False)

            # Should install synapse-a2a and delegation to both .claude and .codex (4 total)
            assert len(installed) == 4

            # Check .claude skills exist
            claude_a2a = base_dir / ".claude" / "skills" / "synapse-a2a"
            assert claude_a2a.exists()
            assert (claude_a2a / "SKILL.md").exists()

            claude_delegation = base_dir / ".claude" / "skills" / "delegation"
            assert claude_delegation.exists()

            # Check .codex skills exist
            codex_a2a = base_dir / ".codex" / "skills" / "synapse-a2a"
            assert codex_a2a.exists()
            assert (codex_a2a / "SKILL.md").exists()

            codex_delegation = base_dir / ".codex" / "skills" / "delegation"
            assert codex_delegation.exists()

    def test_install_skills_skips_existing(self):
        """Test _install_skills_to_dir skips existing without force."""
        from synapse.cli import _install_skills_to_dir

        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)

            # Create existing skill directory
            existing = base_dir / ".claude" / "skills" / "synapse-a2a"
            existing.mkdir(parents=True)
            (existing / "custom.txt").write_text("custom content")

            # Install without force
            installed = _install_skills_to_dir(base_dir, force=False)

            # Should skip existing .claude/synapse-a2a, but install:
            # - .claude/delegation
            # - .codex/synapse-a2a
            # - .codex/delegation
            assert len(installed) == 3

            # Custom file should still exist
            assert (existing / "custom.txt").exists()

    def test_install_skills_force_overwrites(self):
        """Test _install_skills_to_dir overwrites with force=True."""
        from synapse.cli import _install_skills_to_dir

        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)

            # Create existing skill directory with custom file
            existing = base_dir / ".claude" / "skills" / "synapse-a2a"
            existing.mkdir(parents=True)
            (existing / "custom.txt").write_text("custom content")

            # Install with force
            installed = _install_skills_to_dir(base_dir, force=True)

            # Should install all 4 skills (synapse-a2a + delegation for .claude and .codex)
            assert len(installed) == 4

            # Custom file should be gone, replaced with SKILL.md
            assert not (existing / "custom.txt").exists()
            assert (existing / "SKILL.md").exists()

    def test_install_skills_no_gemini(self):
        """Test that skills are not installed to .gemini (unsupported)."""
        from synapse.cli import _install_skills_to_dir

        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)

            installed = _install_skills_to_dir(base_dir, force=False)

            # Check no .gemini directory was created
            gemini_skill = base_dir / ".gemini" / "skills" / "synapse-a2a"
            assert not gemini_skill.exists()

            # Only .claude and .codex (paths are like .../base/.claude/skills/synapse-a2a)
            # Extract the agent dir name (e.g., ".claude", ".codex")
            installed_agent_dirs = []
            for p in installed:
                parts = Path(p).parts
                # Find the part that starts with "."
                for part in parts:
                    if part.startswith(".") and part in [
                        ".claude",
                        ".codex",
                        ".gemini",
                    ]:
                        installed_agent_dirs.append(part)
                        break
            assert ".claude" in installed_agent_dirs
            assert ".codex" in installed_agent_dirs
            assert ".gemini" not in installed_agent_dirs
