"""Tests for synapse init preserving user data (agents, databases, etc.)."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from synapse.cli import _copy_synapse_templates, cmd_init


@pytest.fixture
def temp_dir(tmp_path):
    """Provide a temporary directory."""
    return tmp_path


@pytest.fixture
def mock_args():
    """Create mock args for cmd_init."""
    from unittest.mock import MagicMock

    args = MagicMock()
    args.scope = "project"
    return args


@pytest.fixture
def synapse_dir_with_user_data(temp_dir):
    """Create a .synapse/ directory with user-generated data."""
    synapse_dir = temp_dir / ".synapse"
    synapse_dir.mkdir(parents=True)

    # Template files (should be overwritten)
    (synapse_dir / "settings.json").write_text('{"old": "settings"}')
    (synapse_dir / "default.md").write_text("old default instructions")

    # User data: saved agent definitions
    agents_dir = synapse_dir / "agents"
    agents_dir.mkdir()
    (agents_dir / "calm-lead.agent").write_text(
        json.dumps({"id": "calm-lead", "name": "Calm Lead", "profile": "claude"})
    )
    (agents_dir / "steady-builder.agent").write_text(
        json.dumps(
            {"id": "steady-builder", "name": "Steady Builder", "profile": "gemini"}
        )
    )

    # User data: databases
    (synapse_dir / "file_safety.db").write_bytes(b"SQLite format 3\x00" + b"\x00" * 100)
    (synapse_dir / "memory.db").write_bytes(b"SQLite format 3\x00" + b"\x00" * 100)

    # User data: sessions
    sessions_dir = synapse_dir / "sessions"
    sessions_dir.mkdir()
    (sessions_dir / "my-session.json").write_text('{"name": "my-session"}')

    # User data: workflows
    workflows_dir = synapse_dir / "workflows"
    workflows_dir.mkdir()
    (workflows_dir / "deploy.yaml").write_text("steps:\n  - name: deploy")

    # User data: worktrees
    worktrees_dir = synapse_dir / "worktrees"
    worktrees_dir.mkdir()
    (worktrees_dir / "feature-auth").mkdir()

    return synapse_dir


class TestCopySynapseTemplatesPreservesUserData:
    """_copy_synapse_templates must preserve user-generated data."""

    def test_preserves_agent_definitions(self, synapse_dir_with_user_data):
        """Saved agent definitions (.agent files) must survive init."""
        synapse_dir = synapse_dir_with_user_data

        result = _copy_synapse_templates(synapse_dir)
        assert result is True

        agents_dir = synapse_dir / "agents"
        assert agents_dir.exists(), "agents/ directory was deleted"
        assert (agents_dir / "calm-lead.agent").exists(), "calm-lead.agent was deleted"
        assert (agents_dir / "steady-builder.agent").exists(), (
            "steady-builder.agent was deleted"
        )

        # Verify content is intact
        data = json.loads((agents_dir / "calm-lead.agent").read_text())
        assert data["name"] == "Calm Lead"

    def test_preserves_databases(self, synapse_dir_with_user_data):
        """SQLite databases must survive init."""
        synapse_dir = synapse_dir_with_user_data

        result = _copy_synapse_templates(synapse_dir)
        assert result is True

        assert (synapse_dir / "file_safety.db").exists(), "file_safety.db was deleted"
        assert (synapse_dir / "memory.db").exists(), "memory.db was deleted"

    def test_preserves_sessions(self, synapse_dir_with_user_data):
        """Session configurations must survive init."""
        synapse_dir = synapse_dir_with_user_data

        result = _copy_synapse_templates(synapse_dir)
        assert result is True

        sessions_dir = synapse_dir / "sessions"
        assert sessions_dir.exists(), "sessions/ directory was deleted"
        assert (sessions_dir / "my-session.json").exists(), "session file was deleted"

    def test_preserves_workflows(self, synapse_dir_with_user_data):
        """Workflow definitions must survive init."""
        synapse_dir = synapse_dir_with_user_data

        result = _copy_synapse_templates(synapse_dir)
        assert result is True

        workflows_dir = synapse_dir / "workflows"
        assert workflows_dir.exists(), "workflows/ directory was deleted"
        assert (workflows_dir / "deploy.yaml").exists(), "workflow file was deleted"

    def test_preserves_worktrees(self, synapse_dir_with_user_data):
        """Worktree directories must survive init."""
        synapse_dir = synapse_dir_with_user_data

        result = _copy_synapse_templates(synapse_dir)
        assert result is True

        worktrees_dir = synapse_dir / "worktrees"
        assert worktrees_dir.exists(), "worktrees/ directory was deleted"
        assert (worktrees_dir / "feature-auth").exists(), "worktree was deleted"

    def test_updates_template_files(self, synapse_dir_with_user_data):
        """Template files (settings.json, *.md) must be updated."""
        synapse_dir = synapse_dir_with_user_data

        result = _copy_synapse_templates(synapse_dir)
        assert result is True

        # settings.json should have new default values, not old ones
        settings = json.loads((synapse_dir / "settings.json").read_text())
        assert "old" not in settings, "settings.json was not updated"
        assert "env" in settings, "settings.json doesn't have default content"

        # default.md should be updated
        content = (synapse_dir / "default.md").read_text()
        assert content != "old default instructions", "default.md was not updated"

    def test_fresh_init_works(self, temp_dir):
        """Init on a directory without existing .synapse/ should work."""
        synapse_dir = temp_dir / ".synapse"

        result = _copy_synapse_templates(synapse_dir)

        assert result is True
        assert (synapse_dir / "settings.json").exists()
        assert (synapse_dir / "default.md").exists()

    def test_skips_symlink_in_destination(self, temp_dir):
        """Symlinks in destination path must be rejected."""
        synapse_dir = temp_dir / ".synapse"
        synapse_dir.mkdir(parents=True)

        # Create a symlink pointing outside .synapse/
        outside_dir = temp_dir / "outside"
        outside_dir.mkdir()
        escape_link = synapse_dir / "escape"
        escape_link.symlink_to(outside_dir)

        result = _copy_synapse_templates(synapse_dir)
        assert result is True

        # The symlink target should not have any files written to it
        assert not list(outside_dir.iterdir()), "Files written through symlink"


class TestCmdInitPreservesUserData:
    """cmd_init integration test: user data preserved through full flow."""

    def test_init_overwrite_preserves_agents(
        self, mock_args, synapse_dir_with_user_data, monkeypatch
    ):
        """synapse init --scope project with overwrite must preserve agents."""
        temp_dir = synapse_dir_with_user_data.parent
        monkeypatch.setattr(Path, "cwd", lambda: temp_dir)

        with patch("builtins.input", return_value="y"):
            cmd_init(mock_args)

        agents_dir = temp_dir / ".synapse" / "agents"
        assert agents_dir.exists(), "agents/ directory was deleted by cmd_init"
        assert (agents_dir / "calm-lead.agent").exists()
        assert (agents_dir / "steady-builder.agent").exists()

    def test_init_overwrite_preserves_databases(
        self, mock_args, synapse_dir_with_user_data, monkeypatch
    ):
        """synapse init --scope project with overwrite must preserve databases."""
        temp_dir = synapse_dir_with_user_data.parent
        monkeypatch.setattr(Path, "cwd", lambda: temp_dir)

        with patch("builtins.input", return_value="y"):
            cmd_init(mock_args)

        synapse_dir = temp_dir / ".synapse"
        assert (synapse_dir / "file_safety.db").exists()
        assert (synapse_dir / "memory.db").exists()
