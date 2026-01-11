"""Coverage tests for synapse/cli.py."""

import argparse
from unittest.mock import MagicMock, patch

import pytest

from synapse.cli import cmd_list, cmd_start, install_skills


class TestCliCoverage:
    """Tests for missing coverage in cli.py."""

    def test_install_skills_existing_dir(self, tmp_path):
        """Test skipping skill installation if directory exists."""
        home = tmp_path / "home"
        home.mkdir()
        # Create all skill directories in both .claude and .codex to avoid any copy calls
        for skill in ["synapse-a2a", "delegation"]:
            claude_skill_dir = home / ".claude" / "skills" / skill
            claude_skill_dir.mkdir(parents=True)
            codex_skill_dir = home / ".codex" / "skills" / skill
            codex_skill_dir.mkdir(parents=True)

        with (
            patch("pathlib.Path.home", return_value=home),
            patch("synapse.cli.shutil.copytree") as mock_copy,
        ):
            install_skills()
            mock_copy.assert_not_called()

    def test_cmd_start_ssl_cert_only_error(self):
        """Test error when only SSL cert is provided (Line 98)."""
        args = argparse.Namespace(
            profile="claude",
            port=8100,
            foreground=False,
            ssl_cert="cert.pem",
            ssl_key=None,
            tool_args=[],
        )
        with pytest.raises(SystemExit) as exc:
            cmd_start(args)
        assert exc.value.code == 1

    def test_cmd_start_ssl_key_only_error(self):
        """Test error when only SSL key is provided (Line 98)."""
        args = argparse.Namespace(
            profile="claude",
            port=8100,
            foreground=False,
            ssl_cert=None,
            ssl_key="key.pem",
            tool_args=[],
        )
        with pytest.raises(SystemExit) as exc:
            cmd_start(args)
        assert exc.value.code == 1

    def test_cmd_list_dead_agent_cleanup(self):
        """Test cleaning up dead agents from list (Lines 268, 291)."""
        mock_reg = MagicMock()
        mock_reg.list_agents.return_value = {
            "dead": {"agent_id": "dead", "pid": 999, "status": "READY"}
        }

        args = argparse.Namespace(watch=False)
        with (
            patch("synapse.cli.AgentRegistry", return_value=mock_reg),
            patch("synapse.cli.is_process_alive", return_value=False),
            patch("builtins.print"),
        ):
            cmd_list(args)
            mock_reg.unregister.assert_called_with("dead")
