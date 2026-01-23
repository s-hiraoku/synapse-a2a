"""Tests for GitHub Copilot CLI agent support."""

import re
from pathlib import Path

import pytest
import yaml

from synapse.port_manager import PORT_RANGES, get_port_range


class TestCopilotPortRange:
    """Tests for Copilot port range configuration."""

    def test_copilot_in_port_ranges(self):
        """Copilot should be defined in PORT_RANGES."""
        assert "copilot" in PORT_RANGES

    def test_copilot_port_range_values(self):
        """Copilot should have port range 8140-8149."""
        assert PORT_RANGES["copilot"] == (8140, 8149)

    def test_get_port_range_copilot(self):
        """get_port_range should return correct range for copilot."""
        assert get_port_range("copilot") == (8140, 8149)

    def test_copilot_range_no_overlap(self):
        """Copilot port range should not overlap with other agents."""
        copilot_start, copilot_end = PORT_RANGES["copilot"]
        for agent_type, (start, end) in PORT_RANGES.items():
            if agent_type != "copilot":
                assert copilot_end < start or end < copilot_start, (
                    f"Copilot range overlaps with {agent_type}"
                )


class TestCopilotProfile:
    """Tests for Copilot profile configuration."""

    @pytest.fixture
    def profile_path(self):
        """Get path to Copilot profile."""
        return Path(__file__).parent.parent / "synapse" / "profiles" / "copilot.yaml"

    @pytest.fixture
    def profile(self, profile_path):
        """Load Copilot profile."""
        with open(profile_path) as f:
            return yaml.safe_load(f)

    def test_profile_exists(self, profile_path):
        """Copilot profile file should exist."""
        assert profile_path.exists()

    def test_profile_command(self, profile):
        """Profile should have correct command."""
        assert profile["command"] == "copilot"

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
        assert 0.1 <= timeout <= 5.0  # Reasonable range

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
        assert compiled.search("(y/n)")
        assert compiled.search("(Y/N)")


class TestCopilotTemplate:
    """Tests for Copilot instruction template."""

    @pytest.fixture
    def template_path(self):
        """Get path to default template (copilot uses default.md)."""
        return (
            Path(__file__).parent.parent
            / "synapse"
            / "templates"
            / ".synapse"
            / "default.md"
        )

    @pytest.fixture
    def template_content(self, template_path):
        """Load template content."""
        with open(template_path) as f:
            return f.read()

    def test_template_exists(self, template_path):
        """Template file should exist."""
        assert template_path.exists()

    def test_template_has_placeholders(self, template_content):
        """Template should have agent_id and port placeholders."""
        assert "{{agent_id}}" in template_content
        assert "{{port}}" in template_content

    def test_template_has_agent_examples(self, template_content):
        """Template should have agent examples."""
        assert "--from" in template_content

    def test_template_has_a2a_protocol_section(self, template_content):
        """Template should have A2A communication protocol section."""
        assert "A2A COMMUNICATION PROTOCOL" in template_content

    def test_template_has_branch_management(self, template_content):
        """Template should have branch management section."""
        assert "BRANCH MANAGEMENT" in template_content


class TestCopilotIntegration:
    """Integration tests for Copilot agent support."""

    def test_known_profiles_includes_copilot(self):
        """KNOWN_PROFILES in cli.py should include copilot."""
        from synapse.cli import KNOWN_PROFILES

        assert "copilot" in KNOWN_PROFILES
