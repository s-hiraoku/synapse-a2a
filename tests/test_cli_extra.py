"""Extra tests for CLI commands to improve coverage."""

import argparse
from unittest.mock import MagicMock, patch

import pytest

from synapse.cli import cmd_stop
from synapse.commands.list import ListCommand


class TestCliExtra:
    """Test cases for missing logic in cli.py."""

    @pytest.fixture
    def mock_args(self):
        return argparse.Namespace()

    def test_cmd_stop_all(self, mock_args):
        """Test stopping all agents with --all flag."""
        mock_args.target = "claude"
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


class TestListCommand:
    """Test cases for ListCommand class."""

    def test_get_agent_data_cleans_up_dead_agents(self):
        """Test that _get_agent_data cleans up dead agents."""
        mock_registry_factory = MagicMock()
        mock_registry = MagicMock()
        mock_registry_factory.return_value = mock_registry
        mock_registry.list_agents.return_value = {
            "dead-agent": {
                "agent_id": "dead-agent",
                "agent_type": "claude",
                "pid": 99999,
                "port": 8100,
                "status": "READY",
            }
        }

        list_cmd = ListCommand(
            registry_factory=mock_registry_factory,
            is_process_alive=lambda pid: False,  # Always dead
            is_port_open=lambda host, port, timeout=0.5: True,
            clear_screen=lambda: None,
            time_module=MagicMock(),
            print_func=print,
        )

        with patch("synapse.commands.list.FileSafetyManager") as mock_fs:
            mock_fs.from_env.return_value.enabled = False
            list_cmd._get_agent_data(mock_registry)

        mock_registry.unregister.assert_called_with("dead-agent")

    def test_get_agent_data_cleans_up_closed_ports(self):
        """Test that _get_agent_data cleans up agents with closed ports."""
        mock_registry_factory = MagicMock()
        mock_registry = MagicMock()
        mock_registry_factory.return_value = mock_registry
        mock_registry.list_agents.return_value = {
            "closed-port-agent": {
                "agent_id": "closed-port-agent",
                "agent_type": "claude",
                "pid": 123,
                "port": 8100,
                "status": "READY",
            }
        }

        list_cmd = ListCommand(
            registry_factory=mock_registry_factory,
            is_process_alive=lambda pid: True,
            is_port_open=lambda host, port, timeout=0.5: False,  # Port closed
            clear_screen=lambda: None,
            time_module=MagicMock(),
            print_func=print,
        )

        with patch("synapse.commands.list.FileSafetyManager") as mock_fs:
            mock_fs.from_env.return_value.enabled = False
            list_cmd._get_agent_data(mock_registry)

        mock_registry.unregister.assert_called_with("closed-port-agent")
