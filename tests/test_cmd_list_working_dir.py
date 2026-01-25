"""Tests for synapse list command working_dir display."""

import json
import os
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from synapse.cli import cmd_list
from synapse.registry import AgentRegistry


@pytest.fixture
def temp_registry():
    """Create a test registry with temp directory."""
    reg = AgentRegistry()
    reg.registry_dir = Path("/tmp/a2a_test_list_working_dir")
    reg.registry_dir.mkdir(parents=True, exist_ok=True)
    yield reg
    shutil.rmtree(reg.registry_dir, ignore_errors=True)


class TestCmdListWorkingDir:
    """Tests for cmd_list command working_dir display."""

    def test_list_displays_working_dir(self, temp_registry):
        """synapse list should include working_dir in agent data."""
        from synapse.commands.list import ListCommand

        # Register an agent with working_dir
        test_working_dir = "/home/user/project"
        temp_registry.register("synapse-claude-8100", "claude", 8100)

        # Update the registry file to include working_dir
        file_path = temp_registry.registry_dir / "synapse-claude-8100.json"
        with open(file_path) as f:
            data = json.load(f)
        data["working_dir"] = test_working_dir
        with open(file_path, "w") as f:
            json.dump(data, f)

        list_cmd = ListCommand(
            registry_factory=lambda: temp_registry,
            is_process_alive=lambda pid: True,
            is_port_open=lambda host, port, timeout=0.5: True,
            clear_screen=lambda: None,
            time_module=MagicMock(),
            print_func=print,
        )

        agents, _, _ = list_cmd._get_agent_data(temp_registry)

        assert len(agents) == 1
        # working_dir should be the basename
        assert agents[0]["working_dir"] == "project"

    def test_list_displays_multiple_agents_with_working_dir(self, temp_registry):
        """synapse list should include working_dir for multiple agents."""
        from synapse.commands.list import ListCommand

        test_dirs = ["/home/user/project1", "/home/user/project2"]

        for i, test_dir in enumerate(test_dirs):
            agent_id = f"synapse-claude-810{i}"
            port = 8100 + i
            temp_registry.register(agent_id, "claude", port)

            file_path = temp_registry.registry_dir / f"{agent_id}.json"
            with open(file_path) as f:
                data = json.load(f)
            data["working_dir"] = test_dir
            with open(file_path, "w") as f:
                json.dump(data, f)

        list_cmd = ListCommand(
            registry_factory=lambda: temp_registry,
            is_process_alive=lambda pid: True,
            is_port_open=lambda host, port, timeout=0.5: True,
            clear_screen=lambda: None,
            time_module=MagicMock(),
            print_func=print,
        )

        agents, _, _ = list_cmd._get_agent_data(temp_registry)

        assert len(agents) == 2
        working_dirs = [a["working_dir"] for a in agents]
        assert "project1" in working_dirs
        assert "project2" in working_dirs

    def test_list_header_includes_working_dir(self, temp_registry, capsys):
        """synapse list header should be present (non-TTY mode)."""
        temp_registry.register("synapse-claude-8100", "claude", 8100)

        args = MagicMock()
        args.working_dir = None

        with (
            patch("synapse.cli.AgentRegistry", return_value=temp_registry),
            patch("synapse.cli.is_process_alive", return_value=True),
            patch("sys.stdout.isatty", return_value=False),
        ):
            cmd_list(args)

        captured = capsys.readouterr()
        # Non-TTY mode shows simple table
        assert "TYPE" in captured.out
        assert "PORT" in captured.out

    def test_list_empty_registry(self, temp_registry, capsys):
        """synapse list should handle empty registry gracefully."""
        args = MagicMock()
        args.working_dir = None

        with (
            patch("synapse.cli.AgentRegistry", return_value=temp_registry),
            patch("sys.stdout.isatty", return_value=False),
        ):
            cmd_list(args)

        captured = capsys.readouterr()
        assert "No agents running" in captured.out

    def test_list_agent_with_current_working_dir(self, temp_registry):
        """synapse list should show current directory name."""
        from synapse.commands.list import ListCommand

        current_dir = os.getcwd()
        current_dir_name = os.path.basename(current_dir)

        temp_registry.register("synapse-claude-8100", "claude", 8100)

        file_path = temp_registry.registry_dir / "synapse-claude-8100.json"
        with open(file_path) as f:
            data = json.load(f)
        data["working_dir"] = current_dir
        with open(file_path, "w") as f:
            json.dump(data, f)

        list_cmd = ListCommand(
            registry_factory=lambda: temp_registry,
            is_process_alive=lambda pid: True,
            is_port_open=lambda host, port, timeout=0.5: True,
            clear_screen=lambda: None,
            time_module=MagicMock(),
            print_func=print,
        )

        agents, _, _ = list_cmd._get_agent_data(temp_registry)

        assert len(agents) == 1
        assert agents[0]["working_dir"] == current_dir_name
