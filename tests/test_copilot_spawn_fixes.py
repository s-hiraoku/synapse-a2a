"""Regression tests for copilot spawn parsing and send target resolution fixes.

Covers:
  Fix 2: Parser guardrails — detect known Synapse flags accidentally in tool_args.
  Fix 3: Spawn readiness contract — cmd_spawn warns when agent not yet registered.
  Fix 4: Send target resolution UX — concrete command examples in ambiguity error.

Reference: [Actionable] synapse start/spawn option parsing and send target resolution issues
"""

from __future__ import annotations

import argparse
from unittest.mock import MagicMock, patch

import pytest


# ============================================================
# Fix 2: Parser guardrails
# ============================================================


class TestToolArgsGuardrails:
    """Detect known Synapse flags that accidentally end up in tool_args."""

    def test_known_flag_in_tool_args_warns(self, capsys) -> None:
        """If --port appears after '--', warn the user with guidance.

        Example: synapse spawn claude -- --port 8100
        The user probably intended: synapse spawn claude --port 8100
        """
        from synapse.cli import _warn_synapse_flags_in_tool_args

        warned = _warn_synapse_flags_in_tool_args(["--port", "8100"])
        assert warned is True

        captured = capsys.readouterr()
        assert "--port" in captured.err
        assert "before" in captured.err.lower() or "--" in captured.err

    def test_known_flag_name_in_tool_args_warns(self, capsys) -> None:
        """If --name appears after '--', it's likely misplaced."""
        from synapse.cli import _warn_synapse_flags_in_tool_args

        warned = _warn_synapse_flags_in_tool_args(["--name", "test"])
        assert warned is True

    def test_known_flag_role_in_tool_args_warns(self, capsys) -> None:
        """If --role appears after '--', it's likely misplaced."""
        from synapse.cli import _warn_synapse_flags_in_tool_args

        warned = _warn_synapse_flags_in_tool_args(["--role", "reviewer"])
        assert warned is True

    def test_unknown_flag_no_warning(self, capsys) -> None:
        """Unknown flags like --dangerously-skip-permissions should not warn."""
        from synapse.cli import _warn_synapse_flags_in_tool_args

        warned = _warn_synapse_flags_in_tool_args(
            ["--dangerously-skip-permissions"]
        )
        assert warned is False

    def test_empty_tool_args_no_warning(self) -> None:
        """Empty tool_args should not warn."""
        from synapse.cli import _warn_synapse_flags_in_tool_args

        warned = _warn_synapse_flags_in_tool_args([])
        assert warned is False

    def test_resume_flag_no_warning(self) -> None:
        """--resume is a valid tool_arg, not a Synapse flag."""
        from synapse.cli import _warn_synapse_flags_in_tool_args

        warned = _warn_synapse_flags_in_tool_args(["--resume"])
        assert warned is False

    def test_skill_set_flag_warns(self, capsys) -> None:
        """--skill-set is a Synapse flag that should warn."""
        from synapse.cli import _warn_synapse_flags_in_tool_args

        warned = _warn_synapse_flags_in_tool_args(["--skill-set", "dev"])
        assert warned is True

    def test_short_flag_n_warns(self, capsys) -> None:
        """Short form -n (--name) should also warn."""
        from synapse.cli import _warn_synapse_flags_in_tool_args

        warned = _warn_synapse_flags_in_tool_args(["-n", "test"])
        assert warned is True

    def test_short_flag_r_warns(self, capsys) -> None:
        """Short form -r (--role) should also warn."""
        from synapse.cli import _warn_synapse_flags_in_tool_args

        warned = _warn_synapse_flags_in_tool_args(["-r", "code reviewer"])
        assert warned is True

    def test_foreground_flag_warns(self, capsys) -> None:
        """--foreground / -f is a start-specific Synapse flag."""
        from synapse.cli import _warn_synapse_flags_in_tool_args

        warned = _warn_synapse_flags_in_tool_args(["--foreground"])
        assert warned is True

    def test_terminal_flag_warns(self, capsys) -> None:
        """--terminal is a spawn-specific Synapse flag."""
        from synapse.cli import _warn_synapse_flags_in_tool_args

        warned = _warn_synapse_flags_in_tool_args(["--terminal", "tmux"])
        assert warned is True


# ============================================================
# Fix 3: Spawn readiness contract
# ============================================================


class TestSpawnReadinessWarning:
    """cmd_spawn should warn when agent is not yet routable after spawn."""

    def test_cmd_spawn_warns_when_not_registered(self, capsys) -> None:
        """After spawn, if agent doesn't register quickly, warn the user."""
        from synapse.cli import cmd_spawn
        from synapse.spawn import SpawnResult

        mock_result = SpawnResult(
            agent_id="synapse-copilot-8140",
            port=8140,
            terminal_used="tmux",
            status="submitted",
        )

        args = argparse.Namespace(
            profile="copilot",
            port=None,
            name=None,
            role=None,
            skill_set=None,
            terminal=None,
            tool_args=[],
        )

        with (
            patch("synapse.spawn.spawn_agent", return_value=mock_result),
            patch("synapse.spawn.wait_for_agent", return_value=None),
        ):
            cmd_spawn(args)

        captured = capsys.readouterr()
        # Should print agent_id and port
        assert "synapse-copilot-8140 8140" in captured.out
        # Should warn about not yet registered
        assert "not yet registered" in captured.err.lower() or \
               "not yet registered" in captured.out.lower()

    def test_cmd_spawn_no_warning_when_registered(self, capsys) -> None:
        """If agent registers quickly, no warning should be shown."""
        from synapse.cli import cmd_spawn
        from synapse.spawn import SpawnResult

        mock_result = SpawnResult(
            agent_id="synapse-copilot-8140",
            port=8140,
            terminal_used="tmux",
            status="submitted",
        )
        agent_info = {
            "agent_id": "synapse-copilot-8140",
            "pid": 12345,
            "port": 8140,
        }

        args = argparse.Namespace(
            profile="copilot",
            port=None,
            name=None,
            role=None,
            skill_set=None,
            terminal=None,
            tool_args=[],
        )

        with (
            patch("synapse.spawn.spawn_agent", return_value=mock_result),
            patch("synapse.spawn.wait_for_agent", return_value=agent_info),
        ):
            cmd_spawn(args)

        captured = capsys.readouterr()
        assert "synapse-copilot-8140 8140" in captured.out
        # Should NOT warn
        assert "not yet registered" not in captured.err.lower()
        assert "not yet registered" not in captured.out.lower()


# ============================================================
# Fix 4: Send target resolution UX
# ============================================================


class TestAmbiguousTargetUX:
    """Ambiguity error should include concrete synapse send command examples."""

    def test_ambiguous_error_includes_send_commands(self) -> None:
        """When multiple agents match, error should show exact send commands."""
        from synapse.tools.a2a import _format_ambiguous_target_error

        matches = [
            {"agent_id": "synapse-copilot-8140", "agent_type": "copilot", "port": 8140},
            {"agent_id": "synapse-copilot-8141", "agent_type": "copilot", "port": 8141},
        ]

        error = _format_ambiguous_target_error("copilot", matches)

        # Should include concrete command examples
        assert "synapse send synapse-copilot-8140" in error or \
               "synapse-copilot-8140" in error
        assert "synapse send synapse-copilot-8141" in error or \
               "synapse-copilot-8141" in error

    def test_ambiguous_error_includes_named_agents(self) -> None:
        """Named agents should show name-based targeting."""
        from synapse.tools.a2a import _format_ambiguous_target_error

        matches = [
            {
                "agent_id": "synapse-copilot-8140",
                "agent_type": "copilot",
                "port": 8140,
                "name": "reviewer",
            },
            {
                "agent_id": "synapse-copilot-8141",
                "agent_type": "copilot",
                "port": 8141,
                "name": "tester",
            },
        ]

        error = _format_ambiguous_target_error("copilot", matches)

        # Should mention using names
        assert "reviewer" in error
        assert "tester" in error

    def test_ambiguous_error_shows_synapse_send_examples(self) -> None:
        """The error message should show runnable 'synapse send' examples."""
        from synapse.tools.a2a import _format_ambiguous_target_error

        matches = [
            {"agent_id": "synapse-opencode-8130", "agent_type": "opencode", "port": 8130},
            {"agent_id": "synapse-opencode-8131", "agent_type": "opencode", "port": 8131},
        ]

        error = _format_ambiguous_target_error("opencode", matches)

        # Should include "synapse send" example commands
        assert "synapse send" in error


# ============================================================
# Regression: CLI parse ordering
# ============================================================


class TestCLIParseOrdering:
    """Synapse options should parse correctly regardless of position."""

    def test_start_port_after_profile(self) -> None:
        """synapse start dummy --port 8199 should parse --port correctly.

        Regression: was treated as tool_args with REMAINDER parser.
        """
        from synapse.cli import _extract_tool_args

        argv = ["start", "dummy", "--port", "8199"]
        cli_argv, tool_args = _extract_tool_args(argv)

        # No '--' separator → all args stay in cli_argv
        assert cli_argv == ["start", "dummy", "--port", "8199"]
        assert tool_args == []

    def test_start_with_separator_passes_tool_args(self) -> None:
        """synapse start dummy -- --resume should pass --resume as tool_arg."""
        from synapse.cli import _extract_tool_args

        argv = ["start", "dummy", "--", "--resume"]
        cli_argv, tool_args = _extract_tool_args(argv)

        assert cli_argv == ["start", "dummy"]
        assert tool_args == ["--resume"]

    def test_spawn_port_after_profile(self) -> None:
        """synapse spawn copilot --port 8140 should parse correctly."""
        from synapse.cli import _extract_tool_args

        argv = ["spawn", "copilot", "--port", "8140"]
        cli_argv, tool_args = _extract_tool_args(argv)

        assert cli_argv == ["spawn", "copilot", "--port", "8140"]
        assert tool_args == []

    def test_spawn_all_options_after_profile(self) -> None:
        """All synapse options after profile should parse correctly."""
        from synapse.cli import _extract_tool_args

        argv = [
            "spawn", "copilot",
            "--port", "8140",
            "--name", "tester",
            "--role", "test writer",
            "--skill-set", "dev",
            "--terminal", "tmux",
        ]
        cli_argv, tool_args = _extract_tool_args(argv)

        assert cli_argv == argv
        assert tool_args == []


# ============================================================
# Regression: Env encoding roundtrip
# ============================================================


class TestEnvEncodingRoundtrip:
    """Tool args with special characters should roundtrip via JSON env."""

    def test_tool_args_with_spaces(self) -> None:
        """Tool args containing spaces should survive JSON encoding."""
        import json

        tool_args = ["--message", "hello world"]
        encoded = json.dumps(tool_args)
        decoded = json.loads(encoded)
        assert decoded == tool_args

    def test_tool_args_with_unicode(self) -> None:
        """Tool args with unicode should survive JSON encoding."""
        import json

        tool_args = ["--message", "こんにちは"]
        encoded = json.dumps(tool_args, ensure_ascii=False)
        decoded = json.loads(encoded)
        assert decoded == tool_args

    def test_tool_args_with_special_symbols(self) -> None:
        """Tool args with shell metacharacters should survive JSON encoding."""
        import json

        tool_args = ["--filter", "name=foo&bar|baz"]
        encoded = json.dumps(tool_args)
        decoded = json.loads(encoded)
        assert decoded == tool_args

    def test_no_null_bytes_in_json_encoding(self) -> None:
        """JSON encoding must never produce NUL bytes in the value."""
        import json

        tool_args = ["--resume", "--dangerously-skip-permissions"]
        encoded = json.dumps(tool_args)
        assert "\x00" not in encoded
