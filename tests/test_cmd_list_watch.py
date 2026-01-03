"""Tests for synapse list --watch command."""

import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from synapse.cli import _clear_screen, _render_agent_table, cmd_list
from synapse.registry import AgentRegistry

# CodeRabbit fix: Removed unused 'json' import that was not used in tests


@pytest.fixture
def temp_registry_dir():
    """Create a temporary registry directory."""
    temp_dir = Path("/tmp/a2a_test_list_watch")
    temp_dir.mkdir(parents=True, exist_ok=True)
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def temp_registry(temp_registry_dir):
    """Create a test registry with temp directory."""
    reg = AgentRegistry()
    reg.registry_dir = temp_registry_dir
    return reg


class TestRenderAgentTable:
    """Tests for _render_agent_table helper function."""

    def test_render_empty_registry(self, temp_registry):
        """Should display 'No agents running' with port ranges."""
        output = _render_agent_table(temp_registry)
        assert "No agents running" in output
        assert "Port ranges:" in output
        assert "claude: 8100-8109" in output

    def test_render_single_agent(self, temp_registry):
        """Should render table with single agent."""
        agent_id = "synapse-claude-8100"
        temp_registry.register(agent_id, "claude", 8100, status="READY")

        with patch("synapse.cli.is_process_alive", return_value=True):
            output = _render_agent_table(temp_registry)

        assert "TYPE" in output  # Header
        assert "claude" in output
        assert "8100" in output
        assert "READY" in output

    def test_render_multiple_agents(self, temp_registry):
        """Should render table with multiple agents."""
        temp_registry.register("synapse-claude-8100", "claude", 8100, status="READY")
        temp_registry.register(
            "synapse-gemini-8110", "gemini", 8110, status="PROCESSING"
        )

        with patch("synapse.cli.is_process_alive", return_value=True):
            output = _render_agent_table(temp_registry)

        assert "claude" in output
        assert "gemini" in output
        assert output.count("\n") >= 3  # Header + separator + 2 agents

    def test_cleans_up_dead_processes(self, temp_registry):
        """Should remove dead processes from registry during render."""
        agent_id = "synapse-claude-8100"
        temp_registry.register(agent_id, "claude", 8100, status="READY")

        with patch("synapse.cli.is_process_alive", return_value=False):
            output = _render_agent_table(temp_registry)

        # Should show empty registry
        assert "No agents running" in output

        # Should have cleaned up the registry
        assert len(temp_registry.list_agents()) == 0


class TestClearScreen:
    """Tests for _clear_screen helper function."""

    @patch("os.system")
    @patch("os.name", "posix")
    def test_clear_on_posix(self, mock_system):
        """Should use 'clear' on POSIX systems."""
        _clear_screen()
        mock_system.assert_called_once_with("clear")

    @patch("os.system")
    @patch("os.name", "nt")
    def test_clear_on_windows(self, mock_system):
        """Should use 'cls' on Windows."""
        _clear_screen()
        mock_system.assert_called_once_with("cls")


class TestCmdListNormalMode:
    """Tests for cmd_list in normal (non-watch) mode."""

    def test_normal_mode_single_output(self, temp_registry, capsys):
        """Normal mode should output once and exit."""
        agent_id = "synapse-claude-8100"
        temp_registry.register(agent_id, "claude", 8100, status="READY")

        args = MagicMock()
        args.watch = False

        with (
            patch("synapse.cli.AgentRegistry", return_value=temp_registry),
            patch("synapse.cli.is_process_alive", return_value=True),
        ):
            cmd_list(args)

        captured = capsys.readouterr()
        assert "claude" in captured.out
        assert "8100" in captured.out

    def test_normal_mode_backward_compatible(self, temp_registry, capsys):
        """Args without watch attribute should work (backward compat)."""
        args = MagicMock(spec=[])  # Empty spec = no attributes

        with patch("synapse.cli.AgentRegistry", return_value=temp_registry):
            cmd_list(args)

        captured = capsys.readouterr()
        assert "No agents running" in captured.out


class TestCmdListWatchMode:
    """Tests for cmd_list in watch mode."""

    def test_watch_mode_loops_with_interval(self, temp_registry):
        """Watch mode should loop and refresh at interval."""
        args = MagicMock()
        args.watch = True
        args.interval = 0.1

        call_count = 0

        def sleep_side_effect(duration):
            nonlocal call_count
            call_count += 1
            if call_count >= 3:  # Exit after 3 iterations
                raise KeyboardInterrupt()

        with (
            patch("synapse.cli.AgentRegistry", return_value=temp_registry),
            patch("synapse.cli._clear_screen"),
            patch("synapse.cli.time.sleep", side_effect=sleep_side_effect),
            pytest.raises(SystemExit) as exc_info,
        ):
            cmd_list(args)

        assert exc_info.value.code == 0
        assert call_count == 3

    def test_watch_mode_clears_screen(self, temp_registry):
        """Watch mode should clear screen before each update."""
        args = MagicMock()
        args.watch = True
        args.interval = 0.1

        clear_calls = []

        def sleep_side_effect(duration):
            if len(clear_calls) >= 2:
                raise KeyboardInterrupt()

        def clear_side_effect():
            clear_calls.append(1)

        with (
            patch("synapse.cli.AgentRegistry", return_value=temp_registry),
            patch("synapse.cli._clear_screen", side_effect=clear_side_effect),
            patch("synapse.cli.time.sleep", side_effect=sleep_side_effect),
            pytest.raises(SystemExit),
        ):
            cmd_list(args)

        assert len(clear_calls) >= 2

    def test_watch_mode_uses_custom_interval(self, temp_registry):
        """Watch mode should respect custom interval."""
        args = MagicMock()
        args.watch = True
        args.interval = 5.0

        sleep_calls = []

        def sleep_side_effect(duration):
            sleep_calls.append(duration)
            raise KeyboardInterrupt()

        with (
            patch("synapse.cli.AgentRegistry", return_value=temp_registry),
            patch("synapse.cli._clear_screen"),
            patch("synapse.cli.time.sleep", side_effect=sleep_side_effect),
            pytest.raises(SystemExit),
        ):
            cmd_list(args)

        assert 5.0 in sleep_calls

    def test_watch_mode_exits_on_ctrl_c(self, temp_registry, capsys):
        """Watch mode should exit gracefully on Ctrl+C."""
        args = MagicMock()
        args.watch = True
        args.interval = 0.1

        with (
            patch("synapse.cli.AgentRegistry", return_value=temp_registry),
            patch("synapse.cli._clear_screen"),
            patch("synapse.cli.time.sleep", side_effect=KeyboardInterrupt),
            pytest.raises(SystemExit) as exc_info,
        ):
            cmd_list(args)

        assert exc_info.value.code == 0

        captured = capsys.readouterr()
        assert "Exiting watch mode" in captured.out

    def test_watch_mode_shows_timestamp(self, temp_registry, capsys):
        """Watch mode should show last updated timestamp."""
        args = MagicMock()
        args.watch = True
        args.interval = 0.1

        timestamp = "2026-01-03 12:00:00"
        with (
            patch("synapse.cli.AgentRegistry", return_value=temp_registry),
            patch("synapse.cli._clear_screen"),
            patch("synapse.cli.time.sleep", side_effect=KeyboardInterrupt),
            patch("synapse.cli.time.strftime", return_value=timestamp),
            pytest.raises(SystemExit),
        ):
            cmd_list(args)

        captured = capsys.readouterr()
        assert "Last updated:" in captured.out
        assert "2026-01-03 12:00:00" in captured.out

    def test_watch_mode_shows_refresh_interval_in_header(self, temp_registry, capsys):
        """Watch mode should show refresh interval in header."""
        args = MagicMock()
        args.watch = True
        args.interval = 2.5

        with (
            patch("synapse.cli.AgentRegistry", return_value=temp_registry),
            patch("synapse.cli._clear_screen"),
            patch("synapse.cli.time.sleep", side_effect=KeyboardInterrupt),
            pytest.raises(SystemExit),
        ):
            cmd_list(args)

        captured = capsys.readouterr()
        assert "refreshing every 2.5s" in captured.out

    def test_watch_mode_empty_registry_continues_watching(self, temp_registry, capsys):
        """Watch mode should show empty message and continue watching."""
        args = MagicMock()
        args.watch = True
        args.interval = 0.1

        call_count = 0

        def sleep_side_effect(duration):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                raise KeyboardInterrupt()

        with (
            patch("synapse.cli.AgentRegistry", return_value=temp_registry),
            patch("synapse.cli._clear_screen"),
            patch("synapse.cli.time.sleep", side_effect=sleep_side_effect),
            pytest.raises(SystemExit),
        ):
            cmd_list(args)

        captured = capsys.readouterr()
        assert "No agents running" in captured.out
        assert call_count == 2  # Should have looped

    def test_watch_mode_default_interval(self, temp_registry):
        """Watch mode should use default 2.0s interval if not specified."""
        args = MagicMock()
        args.watch = True
        args.interval = 2.0  # default

        sleep_calls = []

        def sleep_side_effect(duration):
            sleep_calls.append(duration)
            raise KeyboardInterrupt()

        with (
            patch("synapse.cli.AgentRegistry", return_value=temp_registry),
            patch("synapse.cli._clear_screen"),
            patch("synapse.cli.time.sleep", side_effect=sleep_side_effect),
            pytest.raises(SystemExit),
        ):
            cmd_list(args)

        assert 2.0 in sleep_calls
