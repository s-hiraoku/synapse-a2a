"""Tests for synapse interrupt CLI command (#4 Soft Interrupt)."""

import argparse
import subprocess
import sys
from unittest.mock import patch


class TestInterruptCommand:
    """Tests for cmd_interrupt() — ergonomic shorthand for priority-4 send."""

    @patch("synapse.commands.messaging._run_a2a_command")
    @patch("synapse.commands.messaging._build_a2a_cmd")
    def test_interrupt_builds_priority_4_command(self, mock_build, mock_run):
        """interrupt should delegate to _build_a2a_cmd with priority=4, no-response."""
        from synapse.cli import cmd_interrupt

        mock_build.return_value = ["dummy"]

        args = argparse.Namespace(
            target="gemini",
            message="Stop and review",
            sender=None,
        )
        cmd_interrupt(args)

        mock_build.assert_called_once_with(
            "send",
            "Stop and review",
            target="gemini",
            priority=4,
            sender=None,
            response_mode="silent",
            force=False,
        )
        mock_run.assert_called_once_with(["dummy"], exit_on_error=True)

    @patch("synapse.commands.messaging._run_a2a_command")
    @patch("synapse.commands.messaging._build_a2a_cmd")
    def test_interrupt_with_sender(self, mock_build, mock_run):
        """--from sender should be forwarded to _build_a2a_cmd."""
        from synapse.cli import cmd_interrupt

        mock_build.return_value = ["dummy"]

        args = argparse.Namespace(
            target="codex",
            message="Urgent task",
            sender="synapse-claude-8100",
        )
        cmd_interrupt(args)

        mock_build.assert_called_once_with(
            "send",
            "Urgent task",
            target="codex",
            priority=4,
            sender="synapse-claude-8100",
            response_mode="silent",
            force=False,
        )

    def test_interrupt_requires_target_and_message(self):
        """interrupt should require both target and message positional args."""
        # Verify via subprocess that missing args cause an error exit
        result = subprocess.run(
            [sys.executable, "-m", "synapse.cli", "interrupt"],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0

    def test_interrupt_help_shows_description(self):
        """synapse interrupt --help should show the command description."""
        result = subprocess.run(
            [sys.executable, "-m", "synapse.cli", "interrupt", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert (
            "interrupt" in result.stdout.lower() or "priority" in result.stdout.lower()
        )
