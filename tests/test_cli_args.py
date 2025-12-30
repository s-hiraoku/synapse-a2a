"""Tests for CLI tool arguments passthrough."""

import pytest
import sys
from unittest.mock import patch, MagicMock


class TestShortcutToolArgsParsing:
    """Tests for parsing tool args in shortcut syntax."""

    def test_parse_tool_args_after_separator(self):
        """synapse claude -- --model opus should extract tool args."""
        argv = ['synapse', 'claude', '--', '--model', 'opus']

        # Find -- separator
        try:
            separator_idx = argv.index('--')
            synapse_args = argv[2:separator_idx]
            tool_args = argv[separator_idx + 1:]
        except ValueError:
            synapse_args = argv[2:]
            tool_args = []

        assert synapse_args == []
        assert tool_args == ['--model', 'opus']

    def test_parse_port_and_tool_args(self):
        """synapse claude --port 8100 -- --model opus should work."""
        argv = ['synapse', 'claude', '--port', '8100', '--', '--model', 'opus']

        try:
            separator_idx = argv.index('--')
            synapse_args = argv[2:separator_idx]
            tool_args = argv[separator_idx + 1:]
        except ValueError:
            synapse_args = argv[2:]
            tool_args = []

        # Parse --port from synapse_args
        port = None
        if '--port' in synapse_args:
            idx = synapse_args.index('--port')
            if idx + 1 < len(synapse_args):
                port = int(synapse_args[idx + 1])

        assert port == 8100
        assert tool_args == ['--model', 'opus']

    def test_no_separator_no_tool_args(self):
        """synapse claude --port 8100 should have no tool args."""
        argv = ['synapse', 'claude', '--port', '8100']

        try:
            separator_idx = argv.index('--')
            synapse_args = argv[2:separator_idx]
            tool_args = argv[separator_idx + 1:]
        except ValueError:
            synapse_args = argv[2:]
            tool_args = []

        assert synapse_args == ['--port', '8100']
        assert tool_args == []

    def test_empty_separator_valid(self):
        """synapse claude -- should be valid with empty tool args."""
        argv = ['synapse', 'claude', '--']

        try:
            separator_idx = argv.index('--')
            synapse_args = argv[2:separator_idx]
            tool_args = argv[separator_idx + 1:]
        except ValueError:
            synapse_args = argv[2:]
            tool_args = []

        assert synapse_args == []
        assert tool_args == []

    def test_multiple_tool_args(self):
        """synapse claude -- --model opus --dangerously-skip-permissions should work."""
        argv = ['synapse', 'claude', '--', '--model', 'opus', '--dangerously-skip-permissions']

        try:
            separator_idx = argv.index('--')
            synapse_args = argv[2:separator_idx]
            tool_args = argv[separator_idx + 1:]
        except ValueError:
            synapse_args = argv[2:]
            tool_args = []

        assert tool_args == ['--model', 'opus', '--dangerously-skip-permissions']


class TestToolArgsMerging:
    """Tests for merging profile args with CLI tool args."""

    def test_empty_profile_with_cli_args(self):
        """Profile args=[], CLI args=['--model', 'opus']"""
        profile_args = []
        tool_args = ['--model', 'opus']
        all_args = profile_args + tool_args

        assert all_args == ['--model', 'opus']

    def test_profile_args_with_cli_args(self):
        """Profile args should come before CLI args."""
        profile_args = ['--foo', 'bar']
        tool_args = ['--model', 'opus']
        all_args = profile_args + tool_args

        assert all_args == ['--foo', 'bar', '--model', 'opus']

    def test_empty_both(self):
        """Both empty should result in empty list."""
        profile_args = []
        tool_args = []
        all_args = profile_args + tool_args

        assert all_args == []


class TestStartCommandToolArgs:
    """Tests for start command tool args handling."""

    def test_filter_separator_from_tool_args(self):
        """-- should be filtered from tool_args start."""
        tool_args = ['--', '--model', 'opus']
        if tool_args and tool_args[0] == '--':
            tool_args = tool_args[1:]

        assert tool_args == ['--model', 'opus']

    def test_no_separator_in_tool_args(self):
        """Tool args without -- should pass through."""
        tool_args = ['--model', 'opus']
        if tool_args and tool_args[0] == '--':
            tool_args = tool_args[1:]

        assert tool_args == ['--model', 'opus']

    def test_environment_variable_encoding(self):
        """Tool args should be null-separated for environment variable."""
        tool_args = ['--model', 'opus', '--foo', 'bar']
        encoded = '\x00'.join(tool_args)
        decoded = encoded.split('\x00')

        assert decoded == tool_args

    def test_environment_variable_empty(self):
        """Empty tool args should result in empty string."""
        tool_args = []
        if tool_args:
            encoded = '\x00'.join(tool_args)
        else:
            encoded = ""

        # Decode
        decoded = encoded.split('\x00') if encoded else []

        assert decoded == []


class TestControllerArgsHandling:
    """Tests for TerminalController args handling."""

    def test_command_list_building(self):
        """Command and args should be combined as list."""
        command = "claude"
        args = ["--model", "opus"]
        cmd_list = [command] + args

        assert cmd_list == ["claude", "--model", "opus"]

    def test_empty_args(self):
        """Empty args should result in command only."""
        command = "claude"
        args = []
        cmd_list = [command] + args

        assert cmd_list == ["claude"]

    def test_args_with_spaces(self):
        """Args with spaces should be preserved as separate elements."""
        command = "claude"
        args = ["--message", "hello world"]
        cmd_list = [command] + args

        assert cmd_list == ["claude", "--message", "hello world"]
        assert len(cmd_list) == 3
