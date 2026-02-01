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

    def setup_method(self):
        """Clear environment variables that affect instruction generation."""
        # Remove file safety env var to avoid it affecting tests
        if "SYNAPSE_FILE_SAFETY_ENABLED" in os.environ:
            del os.environ["SYNAPSE_FILE_SAFETY_ENABLED"]

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

    def test_get_instruction_array_format(self):
        """Get instruction supports array format for easier multiline."""
        settings = SynapseSettings(
            env={},
            instructions={
                "default": ["line 1", "line 2", "line 3"],
            },
        )
        result = settings.get_instruction("claude", "agent-id", 8100)
        assert result == "line 1\nline 2\nline 3"

    def test_get_instruction_array_with_placeholders(self):
        """Get instruction replaces placeholders in array format."""
        settings = SynapseSettings(
            env={},
            instructions={
                "default": ["Agent: {{agent_id}}", "Port: {{port}}"],
            },
        )
        result = settings.get_instruction("claude", "test-agent", 9000)
        assert result == "Agent: test-agent\nPort: 9000"

    def test_get_instruction_file_reference(self):
        """Get instruction loads content from .md file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create .synapse directory with instruction file
            synapse_dir = Path(tmpdir) / ".synapse"
            synapse_dir.mkdir()
            instruction_file = synapse_dir / "test.md"
            instruction_file.write_text("Hello {{agent_id}} on port {{port}}")

            settings = SynapseSettings(
                env={},
                instructions={"default": "test.md"},
            )

            # Change to temp directory so .synapse/test.md is found
            import os

            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                result = settings.get_instruction("claude", "my-agent", 8100)
                assert result == "Hello my-agent on port 8100"
            finally:
                os.chdir(original_cwd)

    def test_get_instruction_file_not_found_returns_none(self):
        """Get instruction returns None when file not found."""
        settings = SynapseSettings(
            env={},
            instructions={"default": "nonexistent.md"},
        )
        result = settings.get_instruction("claude", "agent", 8100)
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

    def test_get_instruction_with_name_and_role(self):
        """Get instruction replaces name and role placeholders."""
        settings = SynapseSettings(
            env={},
            instructions={
                "default": "Name: {{agent_name}} Role: {{agent_role}} ID: {{agent_id}}",
            },
        )
        result = settings.get_instruction(
            "claude",
            "synapse-claude-8100",
            8100,
            name="my-claude",
            role="code reviewer",
        )
        assert result == "Name: my-claude Role: code reviewer ID: synapse-claude-8100"

    def test_get_instruction_with_name_only(self):
        """Get instruction uses agent_id when name not provided."""
        settings = SynapseSettings(
            env={},
            instructions={
                "default": "Display: {{agent_name}} Internal: {{agent_id}}",
            },
        )
        result = settings.get_instruction(
            "claude", "synapse-claude-8100", 8100, name=None
        )
        # When name is None, agent_name should default to agent_id
        assert result == "Display: synapse-claude-8100 Internal: synapse-claude-8100"

    def test_get_instruction_with_role_only(self):
        """Get instruction handles role without name."""
        settings = SynapseSettings(
            env={},
            instructions={
                "default": "Name: {{agent_name}} Role: {{agent_role}}",
            },
        )
        result = settings.get_instruction(
            "claude", "synapse-claude-8100", 8100, role="reviewer"
        )
        # Name defaults to agent_id, role is set
        assert result == "Name: synapse-claude-8100 Role: reviewer"

    def test_get_instruction_role_defaults_to_empty(self):
        """Get instruction uses empty string for role when not provided."""
        settings = SynapseSettings(
            env={},
            instructions={
                "default": "Role: [{{agent_role}}]",
            },
        )
        result = settings.get_instruction("claude", "synapse-claude-8100", 8100)
        # Role should be empty string when not provided
        assert result == "Role: []"

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

    def setup_method(self):
        """Clear environment variables that affect instruction generation."""
        if "SYNAPSE_FILE_SAFETY_ENABLED" in os.environ:
            del os.environ["SYNAPSE_FILE_SAFETY_ENABLED"]

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


class TestOptionalInstructions:
    """Test optional instruction file loading based on environment."""

    def test_file_safety_instruction_appended_when_enabled(self):
        """File safety instructions are appended when SYNAPSE_FILE_SAFETY_ENABLED=true."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create .synapse directory with file-safety.md
            synapse_dir = Path(tmpdir) / ".synapse"
            synapse_dir.mkdir()
            file_safety = synapse_dir / "file-safety.md"
            file_safety.write_text("FILE SAFETY RULES\nLock before editing")

            settings = SynapseSettings(
                env={},
                instructions={"default": "Base instruction"},
            )

            original_cwd = os.getcwd()
            original_env = os.environ.get("SYNAPSE_FILE_SAFETY_ENABLED")
            try:
                os.chdir(tmpdir)
                os.environ["SYNAPSE_FILE_SAFETY_ENABLED"] = "true"
                result = settings.get_instruction("claude", "agent", 8100)
                assert "Base instruction" in result
                assert "FILE SAFETY RULES" in result
                assert "Lock before editing" in result
            finally:
                os.chdir(original_cwd)
                if original_env is None:
                    os.environ.pop("SYNAPSE_FILE_SAFETY_ENABLED", None)
                else:
                    os.environ["SYNAPSE_FILE_SAFETY_ENABLED"] = original_env

    def test_file_safety_instruction_not_appended_when_disabled(self):
        """File safety instructions are NOT appended when disabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create .synapse directory with file-safety.md
            synapse_dir = Path(tmpdir) / ".synapse"
            synapse_dir.mkdir()
            file_safety = synapse_dir / "file-safety.md"
            file_safety.write_text("FILE SAFETY RULES")

            settings = SynapseSettings(
                env={},
                instructions={"default": "Base instruction"},
            )

            original_cwd = os.getcwd()
            original_env = os.environ.get("SYNAPSE_FILE_SAFETY_ENABLED")
            try:
                os.chdir(tmpdir)
                os.environ.pop("SYNAPSE_FILE_SAFETY_ENABLED", None)
                result = settings.get_instruction("claude", "agent", 8100)
                assert result == "Base instruction"
                assert "FILE SAFETY RULES" not in result
            finally:
                os.chdir(original_cwd)
                if original_env is not None:
                    os.environ["SYNAPSE_FILE_SAFETY_ENABLED"] = original_env

    def test_file_safety_placeholders_replaced(self):
        """Placeholders in file-safety.md are replaced."""
        with tempfile.TemporaryDirectory() as tmpdir:
            synapse_dir = Path(tmpdir) / ".synapse"
            synapse_dir.mkdir()
            file_safety = synapse_dir / "file-safety.md"
            file_safety.write_text("Agent {{agent_id}} should lock files")

            settings = SynapseSettings(
                env={},
                instructions={"default": "Base"},
            )

            original_cwd = os.getcwd()
            original_env = os.environ.get("SYNAPSE_FILE_SAFETY_ENABLED")
            try:
                os.chdir(tmpdir)
                os.environ["SYNAPSE_FILE_SAFETY_ENABLED"] = "true"
                result = settings.get_instruction("claude", "synapse-claude-8100", 8100)
                assert "Agent synapse-claude-8100 should lock files" in result
            finally:
                os.chdir(original_cwd)
                if original_env is None:
                    os.environ.pop("SYNAPSE_FILE_SAFETY_ENABLED", None)
                else:
                    os.environ["SYNAPSE_FILE_SAFETY_ENABLED"] = original_env

    def test_file_safety_enabled_via_settings_env(self):
        """File safety can be enabled via settings.json env section."""
        with tempfile.TemporaryDirectory() as tmpdir:
            synapse_dir = Path(tmpdir) / ".synapse"
            synapse_dir.mkdir()
            file_safety = synapse_dir / "file-safety.md"
            file_safety.write_text("FILE SAFETY FROM SETTINGS")

            # Enable via settings env, not environment variable
            settings = SynapseSettings(
                env={"SYNAPSE_FILE_SAFETY_ENABLED": "true"},
                instructions={"default": "Base instruction"},
            )

            original_cwd = os.getcwd()
            original_env = os.environ.get("SYNAPSE_FILE_SAFETY_ENABLED")
            try:
                os.chdir(tmpdir)
                # Make sure env var is NOT set
                os.environ.pop("SYNAPSE_FILE_SAFETY_ENABLED", None)
                result = settings.get_instruction("claude", "agent", 8100)
                assert "Base instruction" in result
                assert "FILE SAFETY FROM SETTINGS" in result
            finally:
                os.chdir(original_cwd)
                if original_env is not None:
                    os.environ["SYNAPSE_FILE_SAFETY_ENABLED"] = original_env

    def test_env_var_takes_priority_over_settings(self):
        """Environment variable takes priority over settings.json."""
        with tempfile.TemporaryDirectory() as tmpdir:
            synapse_dir = Path(tmpdir) / ".synapse"
            synapse_dir.mkdir()
            file_safety = synapse_dir / "file-safety.md"
            file_safety.write_text("FILE SAFETY CONTENT")

            # Settings says disabled
            settings = SynapseSettings(
                env={"SYNAPSE_FILE_SAFETY_ENABLED": "false"},
                instructions={"default": "Base"},
            )

            original_cwd = os.getcwd()
            original_env = os.environ.get("SYNAPSE_FILE_SAFETY_ENABLED")
            try:
                os.chdir(tmpdir)
                # But env var says enabled - should win
                os.environ["SYNAPSE_FILE_SAFETY_ENABLED"] = "true"
                result = settings.get_instruction("claude", "agent", 8100)
                assert "FILE SAFETY CONTENT" in result
            finally:
                os.chdir(original_cwd)
                if original_env is None:
                    os.environ.pop("SYNAPSE_FILE_SAFETY_ENABLED", None)
                else:
                    os.environ["SYNAPSE_FILE_SAFETY_ENABLED"] = original_env


class TestSkillInstallation:
    """Test skill installation functionality.

    Skills are distributed via Claude Code plugin marketplace for Claude.
    Codex does not support plugins, so skills are copied from .claude to .codex.
    """

    def test_install_skills_returns_empty_when_no_source(self):
        """Test _copy_claude_skills_to_codex returns empty when .claude/skills doesn't exist."""
        from synapse.cli import _copy_claude_skills_to_codex

        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)

            # No .claude/skills/synapse-a2a exists
            installed = _copy_claude_skills_to_codex(base_dir, force=False)

            assert len(installed) == 0

    def test_install_skills_copies_to_codex(self):
        """Test _copy_claude_skills_to_codex copies skills from .claude to .codex."""
        from synapse.cli import _copy_claude_skills_to_codex

        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)

            # Create source .claude/skills/synapse-a2a
            claude_skills = base_dir / ".claude" / "skills" / "synapse-a2a"
            claude_skills.mkdir(parents=True)
            (claude_skills / "SKILL.md").write_text("# Test Skill")
            (claude_skills / "references").mkdir()
            (claude_skills / "references" / "api.md").write_text("# API")

            # Install skills
            installed = _copy_claude_skills_to_codex(base_dir, force=False)

            # Should copy to .codex
            assert len(installed) == 1
            codex_skills = base_dir / ".codex" / "skills" / "synapse-a2a"
            assert codex_skills.exists()
            assert (codex_skills / "SKILL.md").read_text() == "# Test Skill"
            assert (codex_skills / "references" / "api.md").read_text() == "# API"

    def test_install_skills_skips_existing_codex(self):
        """Test _copy_claude_skills_to_codex skips if .codex/skills already exists."""
        from synapse.cli import _copy_claude_skills_to_codex

        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)

            # Create source
            claude_skills = base_dir / ".claude" / "skills" / "synapse-a2a"
            claude_skills.mkdir(parents=True)
            (claude_skills / "SKILL.md").write_text("# New Skill")

            # Create existing destination
            codex_skills = base_dir / ".codex" / "skills" / "synapse-a2a"
            codex_skills.mkdir(parents=True)
            (codex_skills / "SKILL.md").write_text("# Old Skill")

            # Install without force
            installed = _copy_claude_skills_to_codex(base_dir, force=False)

            # Should not overwrite
            assert len(installed) == 0
            assert (codex_skills / "SKILL.md").read_text() == "# Old Skill"

    def test_install_skills_overwrites_with_force(self):
        """Test _copy_claude_skills_to_codex overwrites .codex/skills with force=True."""
        from synapse.cli import _copy_claude_skills_to_codex

        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)

            # Create source
            claude_skills = base_dir / ".claude" / "skills" / "synapse-a2a"
            claude_skills.mkdir(parents=True)
            (claude_skills / "SKILL.md").write_text("# New Skill")

            # Create existing destination
            codex_skills = base_dir / ".codex" / "skills" / "synapse-a2a"
            codex_skills.mkdir(parents=True)
            (codex_skills / "SKILL.md").write_text("# Old Skill")

            # Install with force
            installed = _copy_claude_skills_to_codex(base_dir, force=True)

            # Should overwrite
            assert len(installed) == 1
            assert (codex_skills / "SKILL.md").read_text() == "# New Skill"

    def test_install_skills_no_directories_without_source(self):
        """Test _copy_claude_skills_to_codex does not create directories without source."""
        from synapse.cli import _copy_claude_skills_to_codex

        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)

            _copy_claude_skills_to_codex(base_dir, force=False)

            # No directories should be created when source doesn't exist
            codex_dir = base_dir / ".codex"
            assert not codex_dir.exists()


class TestResumeFlags:
    """Test resume flags functionality."""

    def test_default_settings_has_resume_flags(self):
        """Default settings should have resume_flags section."""
        assert "resume_flags" in DEFAULT_SETTINGS
        assert isinstance(DEFAULT_SETTINGS["resume_flags"], dict)

    def test_default_resume_flags_for_claude(self):
        """Claude should have default resume flags."""
        flags = DEFAULT_SETTINGS["resume_flags"]["claude"]
        assert "--continue" in flags
        assert "--resume" in flags
        assert "-c" in flags

    def test_default_resume_flags_for_codex(self):
        """Codex should have resume flag."""
        flags = DEFAULT_SETTINGS["resume_flags"]["codex"]
        assert "resume" in flags

    def test_default_resume_flags_for_gemini(self):
        """Gemini should have --resume and -r flags."""
        flags = DEFAULT_SETTINGS["resume_flags"]["gemini"]
        assert "--resume" in flags
        assert "-r" in flags

    def test_get_resume_flags_returns_list(self):
        """get_resume_flags should return a list."""
        settings = SynapseSettings.from_defaults()
        flags = settings.get_resume_flags("claude")
        assert isinstance(flags, list)
        assert "--continue" in flags

    def test_get_resume_flags_unknown_agent(self):
        """get_resume_flags should return empty list for unknown agent."""
        settings = SynapseSettings.from_defaults()
        flags = settings.get_resume_flags("unknown")
        assert flags == []

    def test_is_resume_mode_with_continue_flag(self):
        """is_resume_mode should return True when --continue is in args."""
        settings = SynapseSettings.from_defaults()
        assert settings.is_resume_mode("claude", ["--continue"]) is True
        assert settings.is_resume_mode("claude", ["-c"]) is True
        assert settings.is_resume_mode("claude", ["--resume"]) is True

    def test_is_resume_mode_without_flags(self):
        """is_resume_mode should return False when no resume flags."""
        settings = SynapseSettings.from_defaults()
        assert settings.is_resume_mode("claude", []) is False
        assert settings.is_resume_mode("claude", ["--help"]) is False

    def test_is_resume_mode_with_other_args(self):
        """is_resume_mode should work with mixed arguments."""
        settings = SynapseSettings.from_defaults()
        assert settings.is_resume_mode("claude", ["--continue", "--verbose"]) is True
        assert settings.is_resume_mode("claude", ["-p", "prompt", "-c"]) is True

    def test_is_resume_mode_codex_gemini(self):
        """is_resume_mode should work for codex and gemini."""
        settings = SynapseSettings.from_defaults()
        # Codex uses "resume" subcommand
        assert settings.is_resume_mode("codex", ["resume", "--last"]) is True
        assert settings.is_resume_mode("codex", ["--help"]) is False
        # Gemini uses "--resume" or "-r" flag
        assert settings.is_resume_mode("gemini", ["--resume"]) is True
        assert settings.is_resume_mode("gemini", ["-r"]) is True
        assert settings.is_resume_mode("gemini", ["--continue"]) is False

    def test_resume_flags_custom_settings(self):
        """Custom settings should override default resume flags."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / ".synapse"
            project_dir.mkdir(parents=True)

            # Custom settings with different flags
            custom_settings = {
                "resume_flags": {
                    "claude": ["--custom-resume"],
                    "codex": ["--resume", "-r"],
                }
            }
            (project_dir / "settings.json").write_text(json.dumps(custom_settings))

            settings = SynapseSettings.load(
                project_path=project_dir / "settings.json",
            )

            # Claude should use custom flags
            assert settings.is_resume_mode("claude", ["--custom-resume"]) is True
            assert settings.is_resume_mode("claude", ["--continue"]) is False

            # Codex should now have resume flags
            assert settings.is_resume_mode("codex", ["--resume"]) is True
            assert settings.is_resume_mode("codex", ["-r"]) is True

    def test_from_defaults_includes_resume_flags(self):
        """from_defaults should include resume_flags."""
        settings = SynapseSettings.from_defaults()
        assert settings.resume_flags is not None
        assert "claude" in settings.resume_flags

    def test_is_resume_mode_with_flag_equals_value(self):
        """is_resume_mode should match --flag=value forms."""
        settings = SynapseSettings.from_defaults()

        # Claude: --resume=<session_id>
        assert settings.is_resume_mode("claude", ["--resume=abc123"]) is True
        assert settings.is_resume_mode("claude", ["--continue=session"]) is True
        assert settings.is_resume_mode("claude", ["-c=xyz"]) is True
        assert settings.is_resume_mode("claude", ["-r=123"]) is True

        # Gemini: --resume=<index|UUID>
        assert settings.is_resume_mode("gemini", ["--resume=5"]) is True
        assert settings.is_resume_mode("gemini", ["--resume=abc-def-123"]) is True
        assert settings.is_resume_mode("gemini", ["-r=2"]) is True

        # Mixed with other args
        assert settings.is_resume_mode("claude", ["--verbose", "--resume=abc"]) is True
        assert settings.is_resume_mode("gemini", ["-r=1", "--model", "gemini"]) is True

    def test_is_resume_mode_positional_no_equals(self):
        """Positional flags (like 'resume') should not match 'resume=value'."""
        settings = SynapseSettings.from_defaults()

        # Codex uses positional "resume" subcommand - should NOT match "resume=xxx"
        # because "resume" doesn't start with "-"
        assert settings.is_resume_mode("codex", ["resume"]) is True
        assert settings.is_resume_mode("codex", ["resume=xxx"]) is False
        assert settings.is_resume_mode("codex", ["resume", "--last"]) is True

    def test_is_resume_mode_partial_match_rejected(self):
        """is_resume_mode should not match partial flag names."""
        settings = SynapseSettings.from_defaults()

        # "--resumeXXX" should not match "--resume"
        assert settings.is_resume_mode("claude", ["--resumeXXX"]) is False
        assert settings.is_resume_mode("gemini", ["--resume-all"]) is False

        # But "--resume=XXX" should match "--resume"
        assert settings.is_resume_mode("claude", ["--resume=XXX"]) is True


class TestInstructionFilePaths:
    """Test get_instruction_file_paths returns correct paths for project and user directories."""

    def setup_method(self):
        """Clear environment variables that affect instruction generation."""
        if "SYNAPSE_FILE_SAFETY_ENABLED" in os.environ:
            del os.environ["SYNAPSE_FILE_SAFETY_ENABLED"]

    def test_file_in_project_directory_only(self):
        """When file exists only in project dir, return .synapse/ path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create project .synapse directory with instruction file
            project_synapse = Path(tmpdir) / ".synapse"
            project_synapse.mkdir()
            (project_synapse / "default.md").write_text("Project instruction")

            settings = SynapseSettings(
                env={},
                instructions={"default": "default.md"},
            )

            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                paths = settings.get_instruction_file_paths("claude")
                assert len(paths) == 1
                assert paths[0] == ".synapse/default.md"
            finally:
                os.chdir(original_cwd)

    def test_file_in_user_directory_only(self):
        """When file exists only in user dir, return ~/.synapse/ path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create fake user home with .synapse directory
            fake_home = Path(tmpdir) / "fake_home"
            user_synapse = fake_home / ".synapse"
            user_synapse.mkdir(parents=True)
            (user_synapse / "default.md").write_text("User instruction")

            # Create project directory without instruction file
            project_dir = Path(tmpdir) / "project"
            project_dir.mkdir()

            settings = SynapseSettings(
                env={},
                instructions={"default": "default.md"},
            )

            original_cwd = os.getcwd()
            try:
                os.chdir(project_dir)
                # Use custom home directory for testing
                paths = settings.get_instruction_file_paths(
                    "claude", user_dir=fake_home
                )
                assert len(paths) == 1
                assert paths[0] == "~/.synapse/default.md"
            finally:
                os.chdir(original_cwd)

    def test_file_in_both_directories_prefers_project(self):
        """When file exists in both dirs, prefer project dir."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create fake user home
            fake_home = Path(tmpdir) / "fake_home"
            user_synapse = fake_home / ".synapse"
            user_synapse.mkdir(parents=True)
            (user_synapse / "default.md").write_text("User instruction")

            # Create project directory with instruction file
            project_dir = Path(tmpdir) / "project"
            project_synapse = project_dir / ".synapse"
            project_synapse.mkdir(parents=True)
            (project_synapse / "default.md").write_text("Project instruction")

            settings = SynapseSettings(
                env={},
                instructions={"default": "default.md"},
            )

            original_cwd = os.getcwd()
            try:
                os.chdir(project_dir)
                paths = settings.get_instruction_file_paths(
                    "claude", user_dir=fake_home
                )
                assert len(paths) == 1
                # Project dir takes precedence
                assert paths[0] == ".synapse/default.md"
            finally:
                os.chdir(original_cwd)

    def test_multiple_files_different_locations(self):
        """Test multiple files from different locations."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create fake user home with delegate.md
            fake_home = Path(tmpdir) / "fake_home"
            user_synapse = fake_home / ".synapse"
            user_synapse.mkdir(parents=True)
            (user_synapse / "delegate.md").write_text("User delegate")

            # Create project directory with default.md
            project_dir = Path(tmpdir) / "project"
            project_synapse = project_dir / ".synapse"
            project_synapse.mkdir(parents=True)
            (project_synapse / "default.md").write_text("Project default")

            settings = SynapseSettings(
                env={},
                instructions={"default": "default.md"},
                delegation={"enabled": True},
            )

            original_cwd = os.getcwd()
            try:
                os.chdir(project_dir)
                paths = settings.get_instruction_file_paths(
                    "claude", user_dir=fake_home
                )
                # Should have default.md from project and delegate.md from user
                assert ".synapse/default.md" in paths
                assert "~/.synapse/delegate.md" in paths
            finally:
                os.chdir(original_cwd)

    def test_file_not_found_in_either_location(self):
        """When file doesn't exist anywhere, return empty list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = SynapseSettings(
                env={},
                instructions={"default": "nonexistent.md"},
            )

            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                paths = settings.get_instruction_file_paths("claude")
                assert len(paths) == 0
            finally:
                os.chdir(original_cwd)
