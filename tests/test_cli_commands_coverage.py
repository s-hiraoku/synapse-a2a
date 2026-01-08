"""Coverage tests for synapse/cli.py."""

import argparse
from unittest.mock import MagicMock, patch

import pytest

from synapse.cli import cmd_list, cmd_start, install_skills


class TestCliCoverage:
    """Tests for missing coverage in cli.py."""

    def test_install_skills_existing_dir(self, tmp_path):
        """Test skipping skill installation if directory exists (Lines 47-49)."""
        home = tmp_path / "home"
        home.mkdir()
        # Create all skill directories to avoid any copy calls
        for skill in ["synapse-a2a", "delegation"]:
            skill_dir = home / ".claude" / "skills" / skill
            skill_dir.mkdir(parents=True)

        with (
            patch("synapse.cli.Path.home", return_value=home),
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

    def test_cmd_start_auto_port_failure(self):
        """Test error when no ports available (Line 124)."""
        args = argparse.Namespace(
            profile="claude",
            port=None,
            foreground=False,
            ssl_cert=None,
            ssl_key=None,
            tool_args=[],
        )
        with patch("synapse.cli.PortManager") as mock_pm_cls:
            mock_pm = mock_pm_cls.return_value
            mock_pm.get_available_port.return_value = None
            mock_pm.format_exhaustion_error.return_value = "Out of ports"

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
