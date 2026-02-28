"""Tests for Shared Memory — CLI commands.

Test-first development: these tests define the expected CLI behavior
for `synapse memory` subcommands.
Pattern: follows test_cli_tasks.py conventions (direct handler import + mock).
"""

from __future__ import annotations

import argparse
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def memory_instance(tmp_path):
    """Create a SharedMemory instance for testing."""
    from synapse.shared_memory import SharedMemory

    return SharedMemory(db_path=str(tmp_path / "memory.db"))


class TestCLIMemorySave:
    """Tests for cmd_memory_save."""

    def test_memory_save(self, memory_instance, capsys, monkeypatch):
        """save should create a new memory entry."""
        monkeypatch.setenv("SYNAPSE_AGENT_ID", "synapse-claude-8100")

        with patch(
            "synapse.shared_memory.SharedMemory.from_env",
            return_value=memory_instance,
        ):
            from synapse.cli import cmd_memory_save

            args = argparse.Namespace(
                key="auth-pattern",
                content="Use OAuth2 with PKCE flow",
                tags=None,
                notify=False,
            )
            cmd_memory_save(args)

        out = capsys.readouterr().out
        assert "auth-pattern" in out

    def test_memory_save_with_tags(self, memory_instance, capsys, monkeypatch):
        """save --tags should store tags."""
        monkeypatch.setenv("SYNAPSE_AGENT_ID", "synapse-claude-8100")

        with patch(
            "synapse.shared_memory.SharedMemory.from_env",
            return_value=memory_instance,
        ):
            from synapse.cli import cmd_memory_save

            args = argparse.Namespace(
                key="db-choice",
                content="PostgreSQL",
                tags="arch,database",
                notify=False,
            )
            cmd_memory_save(args)

        out = capsys.readouterr().out
        assert "db-choice" in out


class TestCLIMemoryList:
    """Tests for cmd_memory_list."""

    def test_memory_list(self, memory_instance, capsys):
        """list should show saved memories."""
        memory_instance.save("key-1", "Content 1", "claude")
        memory_instance.save("key-2", "Content 2", "claude")

        with patch(
            "synapse.shared_memory.SharedMemory.from_env",
            return_value=memory_instance,
        ):
            from synapse.cli import cmd_memory_list

            args = argparse.Namespace(author=None, tags=None, limit=50)
            cmd_memory_list(args)

        out = capsys.readouterr().out
        assert "key-1" in out
        assert "key-2" in out

    def test_memory_list_empty(self, memory_instance, capsys):
        """list should show message when no memories exist."""
        with patch(
            "synapse.shared_memory.SharedMemory.from_env",
            return_value=memory_instance,
        ):
            from synapse.cli import cmd_memory_list

            args = argparse.Namespace(author=None, tags=None, limit=50)
            cmd_memory_list(args)

        out = capsys.readouterr().out
        assert "no memories" in out.lower()

    def test_memory_list_filter_author(self, memory_instance, capsys):
        """list --author should filter by author."""
        memory_instance.save("key-1", "Content 1", "synapse-claude-8100")
        memory_instance.save("key-2", "Content 2", "synapse-gemini-8110")

        with patch(
            "synapse.shared_memory.SharedMemory.from_env",
            return_value=memory_instance,
        ):
            from synapse.cli import cmd_memory_list

            args = argparse.Namespace(author="synapse-gemini-8110", tags=None, limit=50)
            cmd_memory_list(args)

        out = capsys.readouterr().out
        assert "key-2" in out
        # key-1 should NOT be in the output since it's by claude
        assert "key-1" not in out


class TestCLIMemoryShow:
    """Tests for cmd_memory_show."""

    def test_memory_show_by_key(self, memory_instance, capsys):
        """show should display memory details by key."""
        memory_instance.save("test-key", "Detailed content here", "claude")

        with patch(
            "synapse.shared_memory.SharedMemory.from_env",
            return_value=memory_instance,
        ):
            from synapse.cli import cmd_memory_show

            args = argparse.Namespace(id_or_key="test-key")
            cmd_memory_show(args)

        out = capsys.readouterr().out
        assert "test-key" in out
        assert "Detailed content here" in out

    def test_memory_show_not_found(self, memory_instance):
        """show should exit with error when memory not found."""
        with patch(
            "synapse.shared_memory.SharedMemory.from_env",
            return_value=memory_instance,
        ):
            from synapse.cli import cmd_memory_show

            args = argparse.Namespace(id_or_key="nonexistent")
            with pytest.raises(SystemExit):
                cmd_memory_show(args)


class TestCLIMemorySearch:
    """Tests for cmd_memory_search."""

    def test_memory_search(self, memory_instance, capsys):
        """search should find matching memories."""
        memory_instance.save("auth-pattern", "OAuth2 PKCE flow", "claude")
        memory_instance.save("db-schema", "PostgreSQL UUID", "claude")

        with patch(
            "synapse.shared_memory.SharedMemory.from_env",
            return_value=memory_instance,
        ):
            from synapse.cli import cmd_memory_search

            args = argparse.Namespace(query="OAuth2")
            cmd_memory_search(args)

        out = capsys.readouterr().out
        assert "auth-pattern" in out


class TestCLIMemoryDelete:
    """Tests for cmd_memory_delete."""

    def test_memory_delete_force(self, memory_instance, capsys):
        """delete --force should remove without confirmation."""
        memory_instance.save("to-delete", "Will be deleted", "claude")

        with patch(
            "synapse.shared_memory.SharedMemory.from_env",
            return_value=memory_instance,
        ):
            from synapse.cli import cmd_memory_delete

            args = argparse.Namespace(id_or_key="to-delete", force=True)
            cmd_memory_delete(args)

        out = capsys.readouterr().out
        assert "deleted" in out.lower()

    def test_memory_delete_not_found(self, memory_instance):
        """delete should exit with error when memory not found."""
        with patch(
            "synapse.shared_memory.SharedMemory.from_env",
            return_value=memory_instance,
        ):
            from synapse.cli import cmd_memory_delete

            args = argparse.Namespace(id_or_key="nonexistent", force=True)
            with pytest.raises(SystemExit):
                cmd_memory_delete(args)


class TestCLIMemoryStats:
    """Tests for cmd_memory_stats."""

    def test_memory_stats(self, memory_instance, capsys):
        """stats should show summary."""
        memory_instance.save("key-1", "Content 1", "claude", tags=["arch"])
        memory_instance.save("key-2", "Content 2", "claude", tags=["test"])

        with patch(
            "synapse.shared_memory.SharedMemory.from_env",
            return_value=memory_instance,
        ):
            from synapse.cli import cmd_memory_stats

            args = argparse.Namespace()
            cmd_memory_stats(args)

        out = capsys.readouterr().out
        assert "Total memories: 2" in out


# --------------------------------------------------------
# #289: CLI tags split(",") produces empty/whitespace tags
# --------------------------------------------------------


class TestCLITagsParsing:
    """Tests for tags parsing in cmd_memory_save and cmd_memory_list (#289)."""

    def test_save_tags_whitespace_trimmed(self, memory_instance, capsys, monkeypatch):
        """save --tags 'arch, security' should trim whitespace."""
        monkeypatch.setenv("SYNAPSE_AGENT_ID", "synapse-claude-8100")

        with patch(
            "synapse.shared_memory.SharedMemory.from_env",
            return_value=memory_instance,
        ):
            from synapse.cli import cmd_memory_save

            args = argparse.Namespace(
                key="test-key",
                content="value",
                tags="arch, security",
                notify=False,
            )
            cmd_memory_save(args)

        # Verify tags were trimmed
        item = memory_instance.get("test-key")
        assert item["tags"] == ["arch", "security"]

    def test_save_tags_trailing_comma_filtered(
        self, memory_instance, capsys, monkeypatch
    ):
        """save --tags 'arch,security,' should filter empty strings."""
        monkeypatch.setenv("SYNAPSE_AGENT_ID", "synapse-claude-8100")

        with patch(
            "synapse.shared_memory.SharedMemory.from_env",
            return_value=memory_instance,
        ):
            from synapse.cli import cmd_memory_save

            args = argparse.Namespace(
                key="test-key2",
                content="value2",
                tags="arch,security,",
                notify=False,
            )
            cmd_memory_save(args)

        item = memory_instance.get("test-key2")
        assert "" not in item["tags"]
        assert item["tags"] == ["arch", "security"]

    def test_list_tags_whitespace_trimmed(self, memory_instance, capsys):
        """list --tags 'arch, security' should trim whitespace for filtering."""
        memory_instance.save("k1", "v1", "claude", tags=["arch"])
        memory_instance.save("k2", "v2", "claude", tags=["test"])

        with patch(
            "synapse.shared_memory.SharedMemory.from_env",
            return_value=memory_instance,
        ):
            from synapse.cli import cmd_memory_list

            args = argparse.Namespace(author=None, tags=" arch , ", limit=50)
            cmd_memory_list(args)

        out = capsys.readouterr().out
        assert "k1" in out
        assert "k2" not in out


# --------------------------------------------------------
# #290: synapse memory without subcommand crashes
# --------------------------------------------------------


class TestMemorySubcommandParsers:
    """Test that 'memory' is in subcommand_parsers (#290)."""

    def test_memory_in_subcommand_parsers(self):
        """'memory' should be in the subcommand_parsers dict."""
        # Import cli module and check main() parses "memory" correctly
        # The fix is to add "memory" to subcommand_parsers dict
        # We test by checking that "synapse memory" without subcommand
        # prints help and exits cleanly (not AttributeError)
        import subprocess
        import sys

        result = subprocess.run(
            [sys.executable, "-m", "synapse.cli", "memory"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        # Should exit with code 1 (help) not crash with unhandled exception
        assert result.returncode == 1
        # Should show help text, not a traceback
        assert "Traceback" not in result.stderr
        assert "AttributeError" not in result.stderr


# --------------------------------------------------------
# #291: _memory_broadcast_notify actually sends messages
# --------------------------------------------------------


class TestMemoryBroadcastNotify:
    """Tests for _memory_broadcast_notify actually sending (#291)."""

    def test_broadcast_sends_to_other_agents(self, monkeypatch):
        """_memory_broadcast_notify should send messages to other agents."""
        monkeypatch.setenv("SYNAPSE_AGENT_ID", "synapse-claude-8100")

        mock_agents = {
            "synapse-claude-8100": {
                "name": "my-claude",
                "endpoint": "http://localhost:8100",
            },
            "synapse-gemini-8110": {
                "name": "my-gemini",
                "endpoint": "http://localhost:8110",
            },
        }

        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = mock_agents

        with (
            patch("synapse.cli.AgentRegistry", return_value=mock_registry),
            patch("synapse.cli.A2AClient") as mock_client_cls,
        ):
            mock_client = MagicMock()
            mock_task = MagicMock()
            mock_client.send_to_local.return_value = mock_task
            mock_client_cls.return_value = mock_client

            from synapse.cli import _memory_broadcast_notify

            _memory_broadcast_notify("auth-pattern")

            # Should have sent to gemini but NOT to self (claude)
            mock_client.send_to_local.assert_called_once()
            call_kwargs = mock_client.send_to_local.call_args
            assert "auth-pattern" in str(call_kwargs)

    def test_broadcast_skips_self(self, monkeypatch):
        """_memory_broadcast_notify should skip the current agent."""
        monkeypatch.setenv("SYNAPSE_AGENT_ID", "synapse-claude-8100")

        mock_agents = {
            "synapse-claude-8100": {
                "name": "self",
                "endpoint": "http://localhost:8100",
            },
        }

        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = mock_agents

        with (
            patch("synapse.cli.AgentRegistry", return_value=mock_registry),
            patch("synapse.cli.A2AClient") as mock_client_cls,
        ):
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client

            from synapse.cli import _memory_broadcast_notify

            _memory_broadcast_notify("test-key")

            # Should NOT send to self
            mock_client.send_to_local.assert_not_called()

    def test_broadcast_handles_send_failure(self, monkeypatch, capsys):
        """_memory_broadcast_notify should handle send failures gracefully."""
        monkeypatch.setenv("SYNAPSE_AGENT_ID", "synapse-claude-8100")

        mock_agents = {
            "synapse-gemini-8110": {
                "name": "gemini",
                "endpoint": "http://localhost:8110",
            },
        }

        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = mock_agents

        with (
            patch("synapse.cli.AgentRegistry", return_value=mock_registry),
            patch("synapse.cli.A2AClient") as mock_client_cls,
        ):
            mock_client = MagicMock()
            mock_client.send_to_local.side_effect = Exception("connection refused")
            mock_client_cls.return_value = mock_client

            from synapse.cli import _memory_broadcast_notify

            # Should not raise, just print failure
            _memory_broadcast_notify("test-key")

        out = capsys.readouterr().out
        assert "Failed:" in out
        assert "connection refused" in out
