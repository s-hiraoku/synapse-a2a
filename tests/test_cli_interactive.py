"""Tests for CLI interactive mode and agent table rendering."""

from unittest.mock import MagicMock, patch

import pytest

from synapse.cli import cmd_run_interactive
from synapse.commands.list import ListCommand
from synapse.registry import AgentRegistry

# ============================================================
# cmd_run_interactive Tests
# ============================================================


class TestCmdRunInteractive:
    """Tests for cmd_run_interactive function."""

    @pytest.fixture
    def mock_dependencies(self):
        """Mock all dependencies."""
        with (
            patch("synapse.cli.TerminalController") as mock_ctrl_cls,
            patch("synapse.cli.AgentRegistry") as mock_reg_cls,
            patch("synapse.server.create_app"),
            patch("uvicorn.run"),
            patch("uvicorn.Config"),
            patch("uvicorn.Server"),
            patch("synapse.registry.resolve_uds_path") as mock_uds_path,
            patch("threading.Thread") as mock_thread,
            patch("synapse.cli.yaml.safe_load") as mock_yaml,
            patch("synapse.cli.os.path.exists", return_value=True),
            patch("builtins.open", MagicMock()),
            patch("synapse.settings.get_settings") as mock_settings,
        ):
            # Mock UDS path to return a mock Path object
            mock_path = MagicMock()
            mock_path.exists.return_value = False
            mock_uds_path.return_value = mock_path
            # Setup mocks
            mock_yaml.return_value = {
                "command": "bash",
                "submit_sequence": "\n",
                "idle_regex": r"\$",
                "args": ["-c"],
            }

            mock_ctrl = mock_ctrl_cls.return_value
            mock_reg = mock_reg_cls.return_value
            mock_reg.get_agent_id.return_value = "agent-123"

            yield {
                "controller": mock_ctrl,
                "registry": mock_reg,
                "thread": mock_thread,
                "yaml": mock_yaml,
                "settings": mock_settings,
                "ctrl_cls": mock_ctrl_cls,
            }

    def test_run_interactive_startup(self, mock_dependencies):
        """Should initialize and start components."""
        with patch("synapse.cli.time.sleep"):  # Skip sleep
            cmd_run_interactive("test_profile", 8100, ["--extra"])

        # Check Controller init
        mock_dependencies["ctrl_cls"].assert_called_once()
        kwargs = mock_dependencies["ctrl_cls"].call_args.kwargs
        assert kwargs["command"] == "bash"
        assert kwargs["port"] == 8100
        assert kwargs["agent_id"] == "agent-123"
        # Check args merging
        assert "-c" in kwargs["args"]
        assert "--extra" in kwargs["args"]

        # Check Registration
        mock_dependencies["registry"].register.assert_called_once()

        # Check Server Threads (UDS and TCP)
        assert mock_dependencies["thread"].call_count == 2
        assert mock_dependencies["thread"].return_value.start.call_count == 2

        # Check Interactive Run
        mock_dependencies["controller"].run_interactive.assert_called_once()

    def test_run_interactive_cleanup_on_exit(self, mock_dependencies):
        """Should clean up resources on normal exit."""
        with patch("synapse.cli.time.sleep"):
            cmd_run_interactive("test_profile", 8100)

        mock_dependencies["registry"].unregister.assert_called_with("agent-123")
        mock_dependencies["controller"].stop.assert_called_once()

    def test_run_interactive_keyboard_interrupt(self, mock_dependencies):
        """Should handle KeyboardInterrupt gracefully."""
        mock_dependencies["controller"].run_interactive.side_effect = KeyboardInterrupt

        with patch("synapse.cli.time.sleep"):
            cmd_run_interactive("test_profile", 8100)

        # Should still clean up
        mock_dependencies["registry"].unregister.assert_called()
        mock_dependencies["controller"].stop.assert_called()


# ============================================================
# ListCommand._render_agent_table Tests
# ============================================================


class TestRenderAgentTable:
    """Tests for ListCommand._render_agent_table method."""

    def _create_list_command(
        self,
        is_process_alive=lambda p: True,
        is_port_open=lambda host, port, timeout=0.5: True,
    ):
        """Create a ListCommand with mock dependencies."""
        return ListCommand(
            registry_factory=lambda: MagicMock(spec=AgentRegistry),
            is_process_alive=is_process_alive,
            is_port_open=is_port_open,
            clear_screen=lambda: None,
            time_module=MagicMock(),
            print_func=print,
        )

    def test_render_empty_registry(self):
        """Should return message when no agents running."""
        registry = MagicMock(spec=AgentRegistry)
        registry.list_agents.return_value = {}

        list_cmd = self._create_list_command()
        output = list_cmd._render_agent_table(registry)

        assert "No agents running" in output
        assert "Port ranges:" in output

    def test_render_active_agents(self):
        """Should render table with active agents."""
        registry = MagicMock(spec=AgentRegistry)
        registry.list_agents.return_value = {
            "agent-1": {
                "agent_type": "claude",
                "port": 8100,
                "status": "IDLE",
                "pid": 12345,
                "endpoint": "http://localhost:8100",
            }
        }

        list_cmd = self._create_list_command()
        output = list_cmd._render_agent_table(registry)

        assert "claude" in output
        assert "8100" in output
        assert "IDLE" in output
        assert "12345" in output

    def test_cleanup_dead_processes(self):
        """Should unregister agents with dead processes."""
        registry = MagicMock(spec=AgentRegistry)
        registry.list_agents.return_value = {
            "agent-1": {"agent_type": "claude", "pid": 12345}
        }

        list_cmd = self._create_list_command(is_process_alive=lambda p: False)
        output = list_cmd._render_agent_table(registry)

        registry.unregister.assert_called_with("agent-1")
        assert "No agents running" in output

    def test_cleanup_closed_ports(self):
        """Should unregister agents with closed ports (if not PROCESSING)."""
        registry = MagicMock(spec=AgentRegistry)
        registry.list_agents.return_value = {
            "agent-1": {
                "agent_type": "claude",
                "port": 8100,
                "status": "IDLE",
                "pid": 12345,
            }
        }

        list_cmd = self._create_list_command(
            is_process_alive=lambda p: True,
            is_port_open=lambda host, port, timeout=0.5: False,
        )
        output = list_cmd._render_agent_table(registry)

        registry.unregister.assert_called_with("agent-1")
        assert "No agents running" in output

    def test_skip_port_check_for_processing(self):
        """Should skip port check for agents in PROCESSING state."""
        registry = MagicMock(spec=AgentRegistry)
        registry.list_agents.return_value = {
            "agent-1": {
                "agent_type": "claude",
                "port": 8100,
                "status": "PROCESSING",
                "pid": 12345,
            }
        }

        port_check_called = []

        def track_port_check(h, p, t):
            port_check_called.append(True)
            return True

        list_cmd = self._create_list_command(
            is_process_alive=lambda p: True,
            is_port_open=track_port_check,
        )
        output = list_cmd._render_agent_table(registry)

        assert len(port_check_called) == 0
        assert "PROCESSING" in output
