"""Tests for Shared Memory — CLI commands.

Test-first development: these tests define the expected CLI behavior
for `synapse memory` subcommands.
Pattern: follows test_cli_tasks.py conventions (direct handler import + mock).
"""

from __future__ import annotations

import argparse
from unittest.mock import patch

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
        assert "2" in out  # total count
