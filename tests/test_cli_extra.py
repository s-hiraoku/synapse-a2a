"""Extra tests for CLI commands to improve coverage."""

import argparse
from unittest.mock import MagicMock, patch

import pytest

from synapse.cli import _render_agent_table, cmd_stop


class TestCliExtra:
    """Test cases for missing logic in cli.py."""

    @pytest.fixture
    def mock_args(self):
        return argparse.Namespace()

    def test_cmd_stop_all(self, mock_args):
        """Test stopping all agents with --all flag."""
        mock_args.profile = "claude"
        mock_args.all = True

        running_infos = [
            {"agent_id": "c1", "pid": 101},
            {"agent_id": "c2", "pid": 102},
        ]

        with (
            patch("synapse.cli.PortManager") as mock_pm_cls,
            patch("synapse.cli._stop_agent") as mock_stop,
        ):
            mock_pm = mock_pm_cls.return_value
            mock_pm.get_running_instances.return_value = running_infos

            cmd_stop(mock_args)

            assert mock_stop.call_count == 2

    def test_render_table_with_dead_agents(self):
        """Test that _render_agent_table cleans up dead agents."""
        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = {
            "dead-agent": {
                "agent_id": "dead-agent",
                "agent_type": "claude",
                "pid": 99999,
                "port": 8100,
                "status": "READY",
            }
        }

        # Mock is_process_alive False to trigger unregister
        with patch("synapse.cli.is_process_alive", return_value=False):
            _render_agent_table(mock_registry)
            mock_registry.unregister.assert_called_with("dead-agent")

    def test_render_table_with_closed_port(self):
        """Test that _render_agent_table cleans up agents with closed ports."""
        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = {
            "closed-port-agent": {
                "agent_id": "closed-port-agent",
                "agent_type": "claude",
                "pid": 123,
                "port": 8100,
                "status": "READY",
            }
        }

        with (
            patch("synapse.cli.is_process_alive", return_value=True),
            patch("synapse.cli.is_port_open", return_value=False),
        ):
            _render_agent_table(mock_registry)
            mock_registry.unregister.assert_called_with("closed-port-agent")
