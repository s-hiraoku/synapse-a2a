"""Tests for synapse.settings module."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

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
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump({"env": {"TEST": "value"}}, f)
            f.flush()
            try:
                result = load_settings(Path(f.name))
                assert result == {"env": {"TEST": "value"}}
            finally:
                os.unlink(f.name)

    def test_load_invalid_json_returns_empty(self):
        """Loading invalid JSON file returns empty dict."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
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
            (project_dir / "settings.local.json").write_text(
                json.dumps(local_settings)
            )

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
            instructions={
                "default": "{{agent_id}} on {{port}}, again {{agent_id}}"
            },
        )
        result = settings.get_instruction("claude", "my-agent", 1234)
        assert result == "my-agent on 1234, again my-agent"
