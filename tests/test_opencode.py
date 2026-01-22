"""Tests for OpenCode agent support."""

import re
from pathlib import Path

import pytest
import yaml

from synapse.port_manager import PORT_RANGES, get_port_range


class TestOpenCodePortRange:
    """Tests for OpenCode port range configuration."""

    def test_opencode_in_port_ranges(self):
        """OpenCode should be defined in PORT_RANGES."""
        assert "opencode" in PORT_RANGES

    def test_opencode_port_range_values(self):
        """OpenCode should have port range 8130-8139."""
        assert PORT_RANGES["opencode"] == (8130, 8139)

    def test_get_port_range_opencode(self):
        """get_port_range should return correct range for opencode."""
        assert get_port_range("opencode") == (8130, 8139)

    def test_opencode_range_no_overlap(self):
        """OpenCode port range should not overlap with other agents."""
        opencode_start, opencode_end = PORT_RANGES["opencode"]
        for agent_type, (start, end) in PORT_RANGES.items():
            if agent_type != "opencode":
                assert opencode_end < start or end < opencode_start, (
                    f"OpenCode range overlaps with {agent_type}"
                )


class TestOpenCodeProfile:
    """Tests for OpenCode profile configuration."""

    @pytest.fixture
    def profile_path(self):
        """Get path to OpenCode profile."""
        return Path(__file__).parent.parent / "synapse" / "profiles" / "opencode.yaml"

    @pytest.fixture
    def profile(self, profile_path):
        """Load OpenCode profile."""
        with open(profile_path) as f:
            return yaml.safe_load(f)

    def test_profile_exists(self, profile_path):
        """OpenCode profile file should exist."""
        assert profile_path.exists()

    def test_profile_command(self, profile):
        """Profile should have correct command."""
        assert profile["command"] == "opencode"

    def test_profile_submit_sequence(self, profile):
        """Profile should have correct submit sequence."""
        assert profile["submit_sequence"] == "\r"

    def test_profile_env_term(self, profile):
        """Profile should set TERM environment variable."""
        assert profile["env"]["TERM"] == "xterm-256color"

    def test_profile_idle_detection_strategy(self, profile):
        """Profile should use timeout-based idle detection."""
        assert profile["idle_detection"]["strategy"] == "timeout"

    def test_profile_idle_detection_timeout(self, profile):
        """Profile should have reasonable idle timeout."""
        timeout = profile["idle_detection"]["timeout"]
        assert 0.5 <= timeout <= 5.0  # Reasonable range

    def test_profile_waiting_detection_exists(self, profile):
        """Profile should have waiting detection configuration."""
        assert "waiting_detection" in profile

    def test_profile_waiting_detection_regex_valid(self, profile):
        """Profile waiting detection regex should be valid."""
        regex = profile["waiting_detection"]["regex"]
        # Should compile without error
        compiled = re.compile(regex)
        assert compiled is not None

    def test_profile_waiting_detection_patterns(self, profile):
        """Profile waiting detection should match expected patterns."""
        regex = profile["waiting_detection"]["regex"]
        compiled = re.compile(regex, re.MULTILINE)

        # Should match numbered choices
        assert compiled.search("1. First option")
        assert compiled.search("  2. Second option")

        # Should match Yes/No prompts
        assert compiled.search("[y/N]")
        assert compiled.search("[Y/n]")


class TestOpenCodeTemplate:
    """Tests for OpenCode instruction template."""

    @pytest.fixture
    def template_path(self):
        """Get path to OpenCode template (uses default.md since opencode has no special requirements)."""
        return (
            Path(__file__).parent.parent
            / "synapse"
            / "templates"
            / ".synapse"
            / "default.md"
        )

    @pytest.fixture
    def template_content(self, template_path):
        """Load OpenCode template content."""
        with open(template_path) as f:
            return f.read()

    def test_template_exists(self, template_path):
        """OpenCode template file should exist."""
        assert template_path.exists()

    def test_template_has_placeholders(self, template_content):
        """Template should have agent_id and port placeholders."""
        assert "{{agent_id}}" in template_content
        assert "{{port}}" in template_content

    def test_template_has_agent_examples(self, template_content):
        """Template should have agent examples (default.md uses codex as example)."""
        # default.md uses codex as example, opencode uses the same template
        assert "--from" in template_content

    def test_template_lists_available_agents(self, template_content):
        """Template should list opencode in available agents."""
        assert "opencode" in template_content.lower()

    def test_template_has_a2a_protocol_section(self, template_content):
        """Template should have A2A communication protocol section."""
        assert "A2A COMMUNICATION PROTOCOL" in template_content

    def test_template_has_branch_management(self, template_content):
        """Template should have branch management section."""
        assert "BRANCH MANAGEMENT" in template_content


class TestOpenCodeIntegration:
    """Integration tests for OpenCode agent support."""

    def test_known_profiles_includes_opencode(self):
        """KNOWN_PROFILES in cli.py should include opencode."""
        from synapse.cli import KNOWN_PROFILES

        assert "opencode" in KNOWN_PROFILES

    def test_all_templates_list_opencode(self):
        """All agent templates should list opencode in available agents."""
        templates_dir = (
            Path(__file__).parent.parent / "synapse" / "templates" / ".synapse"
        )

        for template_file in templates_dir.glob("*.md"):
            with open(template_file) as f:
                content = f.read()
            # Check for AVAILABLE AGENTS line
            if "AVAILABLE AGENTS:" in content:
                assert "opencode" in content, (
                    f"{template_file.name} should list opencode"
                )
