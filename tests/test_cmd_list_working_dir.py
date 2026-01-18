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

    def test_list_displays_working_dir(self, temp_registry, capsys):
        """synapse list should display working_dir for registered agents."""
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

        # Mock the arguments object with explicit attributes
        args = MagicMock()
        args.watch = False
        args.interval = 2.0

        # Run the command with patched registry
        with (
            patch("synapse.cli.AgentRegistry", return_value=temp_registry),
            patch("synapse.cli.is_process_alive", return_value=True),
        ):
            cmd_list(args)

        # Check output - now displays only directory name, not full path
        captured = capsys.readouterr()
        assert "project" in captured.out  # Directory name only
        assert "WORKING_DIR" in captured.out  # Header should include WORKING_DIR

    def test_list_displays_multiple_agents_with_working_dir(
        self, temp_registry, capsys
    ):
        """synapse list should display working_dir for multiple agents."""
        # Register multiple agents with different working_dirs
        test_dirs = ["/home/user/project1", "/home/user/project2"]

        for i, test_dir in enumerate(test_dirs):
            agent_id = f"synapse-claude-810{i}"
            port = 8100 + i
            temp_registry.register(agent_id, "claude", port)

            # Update the registry file
            file_path = temp_registry.registry_dir / f"{agent_id}.json"
            with open(file_path) as f:
                data = json.load(f)
            data["working_dir"] = test_dir
            with open(file_path, "w") as f:
                json.dump(data, f)

        # Mock the arguments object with explicit attributes
        args = MagicMock()
        args.watch = False
        args.interval = 2.0

        # Run the command with patched registry
        with (
            patch("synapse.cli.AgentRegistry", return_value=temp_registry),
            patch("synapse.cli.is_process_alive", return_value=True),
        ):
            cmd_list(args)

        # Check output - now displays only directory names, not full paths
        captured = capsys.readouterr()
        assert "project1" in captured.out
        assert "project2" in captured.out

    def test_list_header_includes_working_dir(self, temp_registry, capsys):
        """synapse list header should include WORKING_DIR column."""
        # Register an agent
        temp_registry.register("synapse-claude-8100", "claude", 8100)

        # Mock the arguments object with explicit attributes
        args = MagicMock()
        args.watch = False
        args.interval = 2.0

        # Run the command with patched registry
        with (
            patch("synapse.cli.AgentRegistry", return_value=temp_registry),
            patch("synapse.cli.is_process_alive", return_value=True),
        ):
            cmd_list(args)

        # Check output
        captured = capsys.readouterr()
        # The output should have a header line with column names
        lines = captured.out.strip().split("\n")
        header = lines[0]
        assert "WORKING_DIR" in header

    def test_list_empty_registry(self, temp_registry, capsys):
        """synapse list should handle empty registry gracefully."""
        # Mock the arguments object with explicit attributes
        args = MagicMock()
        args.watch = False
        args.interval = 2.0

        # Run the command with patched registry
        with patch("synapse.cli.AgentRegistry", return_value=temp_registry):
            cmd_list(args)

        # Check output
        captured = capsys.readouterr()
        assert "No agents running" in captured.out

    def test_list_agent_with_current_working_dir(self, temp_registry, capsys):
        """synapse list should display agent registered from current directory."""
        # Get the current working directory
        current_dir = os.getcwd()
        current_dir_name = os.path.basename(current_dir)

        # Register an agent with current working directory
        temp_registry.register("synapse-claude-8100", "claude", 8100)

        # Update to use current directory (as done in register())
        file_path = temp_registry.registry_dir / "synapse-claude-8100.json"
        with open(file_path) as f:
            data = json.load(f)
        data["working_dir"] = current_dir
        with open(file_path, "w") as f:
            json.dump(data, f)

        # Mock the arguments object with explicit attributes
        args = MagicMock()
        args.watch = False
        args.interval = 2.0

        # Run the command with patched registry
        with (
            patch("synapse.cli.AgentRegistry", return_value=temp_registry),
            patch("synapse.cli.is_process_alive", return_value=True),
        ):
            cmd_list(args)

        # Check output - now displays only directory name, not full path
        captured = capsys.readouterr()
        assert current_dir_name in captured.out
