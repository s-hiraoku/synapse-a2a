"""Tests for synapse send working_dir mismatch warning."""

import os
from unittest.mock import MagicMock, patch

import pytest

from synapse.tools.a2a import _normalize_working_dir, _warn_working_dir_mismatch


@pytest.fixture
def agents_registry():
    """Create a mock agents dict."""
    return {
        "synapse-claude-8100": {
            "agent_id": "synapse-claude-8100",
            "agent_type": "claude",
            "port": 8100,
            "status": "READY",
            "working_dir": "/project-a",
            "name": None,
            "endpoint": "http://localhost:8100",
        },
        "synapse-gemini-8110": {
            "agent_id": "synapse-gemini-8110",
            "agent_type": "gemini",
            "port": 8110,
            "status": "READY",
            "working_dir": "/project-a",
            "name": None,
            "endpoint": "http://localhost:8110",
        },
        "synapse-codex-8120": {
            "agent_id": "synapse-codex-8120",
            "agent_type": "codex",
            "port": 8120,
            "status": "READY",
            "working_dir": "/project-b",
            "name": "フリーレン",
            "endpoint": "http://localhost:8120",
        },
    }


class TestWarnWorkingDirMismatch:
    """Tests for _warn_working_dir_mismatch()."""

    def test_same_directory_no_warning(self, agents_registry, capsys):
        """Same working_dir: no warning, returns False."""
        target = agents_registry["synapse-gemini-8110"]
        with patch("os.getcwd", return_value="/project-a"):
            result = _warn_working_dir_mismatch(target, agents_registry)

        assert result is False
        captured = capsys.readouterr()
        assert captured.err == ""

    def test_different_directory_warning(self, agents_registry, capsys):
        """Different working_dir: warning, returns True."""
        target = agents_registry["synapse-codex-8120"]
        with patch("os.getcwd", return_value="/project-a"):
            result = _warn_working_dir_mismatch(target, agents_registry)

        assert result is True
        captured = capsys.readouterr()
        assert "Warning:" in captured.err
        assert "/project-a" in captured.err
        assert "/project-b" in captured.err

    def test_different_directory_shows_target_display_name(
        self, agents_registry, capsys
    ):
        """Warning message should show target's custom name if set."""
        target = agents_registry["synapse-codex-8120"]
        with patch("os.getcwd", return_value="/project-a"):
            _warn_working_dir_mismatch(target, agents_registry)

        captured = capsys.readouterr()
        assert "フリーレン" in captured.err

    def test_different_directory_shows_agent_id_when_no_name(
        self, agents_registry, capsys
    ):
        """Warning shows agent_id when no custom name is set."""
        target = agents_registry["synapse-codex-8120"].copy()
        target["name"] = None
        with patch("os.getcwd", return_value="/project-a"):
            _warn_working_dir_mismatch(target, agents_registry)

        captured = capsys.readouterr()
        assert "synapse-codex-8120" in captured.err

    def test_target_no_working_dir_no_warning(self, agents_registry, capsys):
        """Target without working_dir: no warning for backward compatibility."""
        target = agents_registry["synapse-claude-8100"].copy()
        target.pop("working_dir", None)
        with patch("os.getcwd", return_value="/project-a"):
            result = _warn_working_dir_mismatch(target, agents_registry)

        assert result is False
        captured = capsys.readouterr()
        assert captured.err == ""

    def test_same_dir_agents_suggested(self, agents_registry, capsys):
        """When same-dir agents exist, they should be suggested."""
        target = agents_registry["synapse-codex-8120"]
        with patch("os.getcwd", return_value="/project-a"):
            _warn_working_dir_mismatch(target, agents_registry)

        captured = capsys.readouterr()
        assert "Agents in current directory:" in captured.err
        assert "synapse-gemini-8110" in captured.err or "gemini" in captured.err
        assert "synapse-claude-8100" in captured.err or "claude" in captured.err

    def test_no_same_dir_agents_spawn_suggested(self, capsys):
        """When no same-dir agents exist, suggest synapse spawn."""
        agents = {
            "synapse-codex-8120": {
                "agent_id": "synapse-codex-8120",
                "agent_type": "codex",
                "port": 8120,
                "status": "READY",
                "working_dir": "/project-b",
                "name": None,
                "endpoint": "http://localhost:8120",
            },
        }
        target = agents["synapse-codex-8120"]
        with patch("os.getcwd", return_value="/project-a"):
            _warn_working_dir_mismatch(target, agents)

        captured = capsys.readouterr()
        assert "No agents in current directory" in captured.err
        assert "synapse spawn" in captured.err

    def test_spawn_suggests_different_model(self, capsys):
        """Spawn suggestion should prefer a different model than sender."""
        agents = {
            "synapse-codex-8120": {
                "agent_id": "synapse-codex-8120",
                "agent_type": "codex",
                "port": 8120,
                "status": "READY",
                "working_dir": "/project-b",
                "name": None,
                "endpoint": "http://localhost:8120",
            },
        }
        target = agents["synapse-codex-8120"]
        # Sender is claude, so spawn suggestion should prefer non-claude
        with (
            patch("os.getcwd", return_value="/project-a"),
            patch.dict(os.environ, {"SYNAPSE_AGENT_ID": "synapse-claude-8100"}),
        ):
            _warn_working_dir_mismatch(target, agents)

        captured = capsys.readouterr()
        # Should suggest a model different from claude (sender)
        assert "synapse spawn" in captured.err
        # The suggestion should NOT be claude since sender is claude
        spawn_line = [
            line for line in captured.err.split("\n") if "synapse spawn" in line
        ][0]
        assert "claude" not in spawn_line.lower()

    def test_spawn_suggests_target_model_when_no_sender_id(self, capsys):
        """When no sender ID, suggest target's model type."""
        agents = {
            "synapse-codex-8120": {
                "agent_id": "synapse-codex-8120",
                "agent_type": "codex",
                "port": 8120,
                "status": "READY",
                "working_dir": "/project-b",
                "name": None,
                "endpoint": "http://localhost:8120",
            },
        }
        target = agents["synapse-codex-8120"]
        with (
            patch("os.getcwd", return_value="/project-a"),
            patch.dict(os.environ, {}, clear=True),
        ):
            _warn_working_dir_mismatch(target, agents)

        captured = capsys.readouterr()
        assert "synapse spawn" in captured.err

    def test_force_hint_in_warning(self, capsys):
        """Warning should mention --force flag."""
        agents = {
            "synapse-codex-8120": {
                "agent_id": "synapse-codex-8120",
                "agent_type": "codex",
                "port": 8120,
                "status": "READY",
                "working_dir": "/project-b",
                "name": None,
                "endpoint": "http://localhost:8120",
            },
        }
        target = agents["synapse-codex-8120"]
        with patch("os.getcwd", return_value="/project-a"):
            _warn_working_dir_mismatch(target, agents)

        captured = capsys.readouterr()
        assert "--force" in captured.err


class TestCmdSendWithForce:
    """Integration-style tests for cmd_send with --force flag."""

    def test_send_same_dir_succeeds(self, agents_registry):
        """Send to same-dir agent should succeed without force."""
        from synapse.tools.a2a import cmd_send

        args = MagicMock()
        args.target = "gemini"
        args.message = "hello"
        args.message_file = None
        args.stdin = False
        args.attach = None
        args.priority = 3
        args.sender = None
        args.want_response = False
        args.force = False

        mock_task = MagicMock()
        mock_task.id = "test-task-id"
        mock_task.status = "completed"
        mock_task.artifacts = []

        with (
            patch("synapse.tools.a2a.AgentRegistry") as MockRegistry,
            patch("synapse.tools.a2a.A2AClient") as MockClient,
            patch("synapse.tools.a2a.is_process_running", return_value=True),
            patch("synapse.tools.a2a.is_port_open", return_value=True),
            patch("synapse.tools.a2a.build_sender_info", return_value={}),
            patch("synapse.tools.a2a._record_sent_message"),
            patch("os.getcwd", return_value="/project-a"),
        ):
            MockRegistry.return_value.list_agents.return_value = agents_registry
            MockClient.return_value.send_to_local.return_value = mock_task
            # Should not raise or exit
            cmd_send(args)

    def test_send_different_dir_exits_without_force(self, agents_registry):
        """Send to different-dir agent should exit(1) without --force."""
        from synapse.tools.a2a import cmd_send

        args = MagicMock()
        args.target = "codex"
        args.message = "hello"
        args.message_file = None
        args.stdin = False
        args.attach = None
        args.priority = 3
        args.sender = None
        args.want_response = False
        args.force = False

        with (
            patch("synapse.tools.a2a.AgentRegistry") as MockRegistry,
            patch("synapse.tools.a2a.is_process_running", return_value=True),
            patch("synapse.tools.a2a.is_port_open", return_value=True),
            patch("os.getcwd", return_value="/project-a"),
            pytest.raises(SystemExit) as exc_info,
        ):
            MockRegistry.return_value.list_agents.return_value = agents_registry
            cmd_send(args)

        assert exc_info.value.code == 1

    def test_send_different_dir_succeeds_with_force(self, agents_registry):
        """Send to different-dir agent should succeed with --force."""
        from synapse.tools.a2a import cmd_send

        args = MagicMock()
        args.target = "codex"
        args.message = "hello"
        args.message_file = None
        args.stdin = False
        args.attach = None
        args.priority = 3
        args.sender = None
        args.want_response = False
        args.force = True

        mock_task = MagicMock()
        mock_task.id = "test-task-id"
        mock_task.status = "completed"
        mock_task.artifacts = []

        with (
            patch("synapse.tools.a2a.AgentRegistry") as MockRegistry,
            patch("synapse.tools.a2a.A2AClient") as MockClient,
            patch("synapse.tools.a2a.is_process_running", return_value=True),
            patch("synapse.tools.a2a.is_port_open", return_value=True),
            patch("synapse.tools.a2a.build_sender_info", return_value={}),
            patch("synapse.tools.a2a._record_sent_message"),
            patch("os.getcwd", return_value="/project-a"),
        ):
            MockRegistry.return_value.list_agents.return_value = agents_registry
            MockClient.return_value.send_to_local.return_value = mock_task
            # Should succeed with --force
            cmd_send(args)


class TestNormalizeWorkingDir:
    """Tests for _normalize_working_dir helper."""

    def test_none_returns_none(self):
        assert _normalize_working_dir(None) is None

    def test_empty_returns_none(self):
        assert _normalize_working_dir("") is None

    def test_normalizes_path(self):
        result = _normalize_working_dir("/tmp/../tmp")
        assert result == "/tmp" or result.endswith("/tmp")

    def test_resolves_symlinks(self, tmp_path):
        real_dir = tmp_path / "real"
        real_dir.mkdir()
        link = tmp_path / "link"
        link.symlink_to(real_dir)

        assert _normalize_working_dir(str(link)) == _normalize_working_dir(
            str(real_dir)
        )
