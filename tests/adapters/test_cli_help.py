"""Tests for top-level synapse --help output."""

import subprocess
import sys

import pytest

pytestmark = pytest.mark.adapters


class TestTopLevelHelp:
    """Verify discoverability of key help sections."""

    def test_help_includes_profile_shortcuts_section(self):
        """Top-level help should explicitly document profile shortcuts."""
        result = subprocess.run(
            [sys.executable, "-m", "synapse.cli", "--help"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "Profile Shortcuts:" in result.stdout
        assert "synapse claude" in result.stdout
        assert "synapse codex" in result.stdout
        assert "synapse gemini" in result.stdout
        assert "synapse opencode" in result.stdout
        assert "synapse copilot" in result.stdout

    def test_help_includes_command_help_hint(self):
        """Top-level help should explain how to drill down into subcommand help."""
        result = subprocess.run(
            [sys.executable, "-m", "synapse.cli", "--help"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "Run 'synapse <command> --help' for detailed usage" in result.stdout


class TestTeamHelp:
    """Verify discoverability for `synapse team --help`."""

    def test_team_help_includes_quick_start_examples(self):
        """Team help should show concrete quick-start examples."""
        result = subprocess.run(
            [sys.executable, "-m", "synapse.cli", "team", "--help"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "Quick Start:" in result.stdout
        assert "synapse team start claude gemini" in result.stdout
        assert "synapse team start claude gemini codex --worktree" in result.stdout

    def test_team_help_includes_subcommand_help_hint(self):
        """Team help should explain how to inspect subcommand-specific help."""
        result = subprocess.run(
            [sys.executable, "-m", "synapse.cli", "team", "--help"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert (
            "Run 'synapse team <subcommand> --help' for detailed usage" in result.stdout
        )


class TestSessionHelp:
    """Verify discoverability for `synapse session --help`."""

    def test_session_help_includes_quick_start_examples(self):
        """Session help should show save/list/show/restore flow examples."""
        result = subprocess.run(
            [sys.executable, "-m", "synapse.cli", "session", "--help"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "Quick Start:" in result.stdout
        assert "synapse session save review-team" in result.stdout
        assert "synapse session list" in result.stdout
        assert "synapse session show review-team" in result.stdout
        assert "synapse session restore review-team" in result.stdout

    def test_session_help_includes_subcommand_help_hint(self):
        """Session help should explain how to inspect subcommand-specific help."""
        result = subprocess.run(
            [sys.executable, "-m", "synapse.cli", "session", "--help"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert (
            "Run 'synapse session <subcommand> --help' for detailed usage"
            in result.stdout
        )


class TestListHelp:
    """Verify `synapse list --help` matches current interactive bindings."""

    def test_list_help_uses_enter_and_uppercase_k_bindings(self):
        """List help should document the current jump and kill keys."""
        result = subprocess.run(
            [sys.executable, "-m", "synapse.cli", "list", "--help"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "hjkl" in result.stdout
        assert "Enter       Jump to terminal" in result.stdout
        assert "K           Kill agent" in result.stdout

    def test_list_help_does_not_advertise_removed_bindings(self):
        """List help should not mention stale j/k action bindings."""
        result = subprocess.run(
            [sys.executable, "-m", "synapse.cli", "list", "--help"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "Enter/j" not in result.stdout
        assert "k           Kill agent" not in result.stdout
