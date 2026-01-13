"""Tests for CLI commands in synapse/cli.py."""

import argparse
import json
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from synapse.cli import (
    _stop_agent,
    _write_default_settings,
    cmd_auth_generate_key,
    cmd_auth_setup,
    cmd_external_add,
    cmd_external_info,
    cmd_external_list,
    cmd_external_remove,
    cmd_external_send,
    cmd_history_cleanup,
    cmd_history_export,
    cmd_history_list,
    cmd_history_search,
    cmd_history_show,
    cmd_history_stats,
    cmd_init,
    cmd_logs,
    cmd_reset,
    cmd_send,
    cmd_start,
    cmd_stop,
    install_skills,
)
from synapse.registry import AgentRegistry

# ==============================================================================
# Fixtures
# ==============================================================================


@pytest.fixture
def temp_registry_dir():
    """Create a temporary registry directory."""
    temp_dir = Path(tempfile.mkdtemp(prefix="test_cli_registry_"))
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def temp_registry(temp_registry_dir):
    """Create a test registry with temp directory."""
    reg = AgentRegistry()
    reg.registry_dir = temp_registry_dir
    return reg


@pytest.fixture
def mock_args():
    """Create a mock argparse.Namespace."""
    return argparse.Namespace()


@pytest.fixture
def temp_synapse_dir():
    """Create a temporary .synapse directory."""
    temp_dir = Path(tempfile.mkdtemp(prefix="test_synapse_"))
    synapse_dir = temp_dir / ".synapse"
    synapse_dir.mkdir(parents=True)
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def temp_empty_dir():
    """Create a temporary directory without .synapse subdirectory."""
    temp_dir = Path(tempfile.mkdtemp(prefix="test_synapse_empty_"))
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


# ==============================================================================
# Tests for cmd_start
# ==============================================================================


class TestCmdStart:
    """Tests for cmd_start command."""

    def test_ssl_validation_both_required(self, mock_args, capsys):
        """Should error when only ssl-cert provided without ssl-key."""
        mock_args.profile = "claude"
        mock_args.port = 8100
        mock_args.foreground = False
        mock_args.ssl_cert = "/path/to/cert.pem"
        mock_args.ssl_key = None
        mock_args.tool_args = []

        with pytest.raises(SystemExit) as exc_info:
            cmd_start(mock_args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Both --ssl-cert and --ssl-key must be provided" in captured.out

    def test_ssl_validation_key_without_cert(self, mock_args, capsys):
        """Should error when only ssl-key provided without ssl-cert."""
        mock_args.profile = "claude"
        mock_args.port = 8100
        mock_args.foreground = False
        mock_args.ssl_cert = None
        mock_args.ssl_key = "/path/to/key.pem"
        mock_args.tool_args = []

        with pytest.raises(SystemExit) as exc_info:
            cmd_start(mock_args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Both --ssl-cert and --ssl-key must be provided" in captured.out

    def test_tool_args_filter_separator(self, mock_args):
        """Should filter -- from tool_args start."""
        mock_args.profile = "claude"
        mock_args.port = 8100
        mock_args.foreground = True
        mock_args.ssl_cert = None
        mock_args.ssl_key = None
        mock_args.tool_args = ["--", "--model", "opus"]

        with (
            patch("synapse.commands.start.subprocess.run") as mock_run,
            patch("synapse.commands.start.PortManager"),
        ):
            cmd_start(mock_args)

        # Check that tool args were passed via environment
        call_args = mock_run.call_args
        env = call_args.kwargs.get("env", {})
        assert env.get("SYNAPSE_TOOL_ARGS") == "--model\x00opus"

    def test_auto_port_selection(self, mock_args, temp_registry):
        """Should auto-select port when not specified."""
        mock_args.profile = "claude"
        mock_args.port = None
        mock_args.foreground = True
        mock_args.ssl_cert = None
        mock_args.ssl_key = None
        mock_args.tool_args = []

        with (
            patch("synapse.commands.start.AgentRegistry", return_value=temp_registry),
            patch("synapse.commands.start.PortManager") as mock_pm_class,
            patch("synapse.commands.start.subprocess.run"),
        ):
            mock_pm = mock_pm_class.return_value
            mock_pm.get_available_port.return_value = 8100

            cmd_start(mock_args)

            mock_pm.get_available_port.assert_called_once_with("claude")

    def test_port_exhaustion_error(self, mock_args, temp_registry, capsys):
        """Should exit with error when ports exhausted."""
        mock_args.profile = "claude"
        mock_args.port = None
        mock_args.foreground = False
        mock_args.ssl_cert = None
        mock_args.ssl_key = None
        mock_args.tool_args = []

        with (
            patch("synapse.commands.start.AgentRegistry", return_value=temp_registry),
            patch("synapse.commands.start.PortManager") as mock_pm_class,
        ):
            mock_pm = mock_pm_class.return_value
            mock_pm.get_available_port.return_value = None
            mock_pm.format_exhaustion_error.return_value = "No ports available"

            with pytest.raises(SystemExit) as exc_info:
                cmd_start(mock_args)

            assert exc_info.value.code == 1
            captured = capsys.readouterr()
            assert "No ports available" in captured.out

    def test_background_mode_starts_subprocess(self, mock_args, capsys):
        """Should start subprocess in background mode."""
        mock_args.profile = "claude"
        mock_args.port = 8100
        mock_args.foreground = False
        mock_args.ssl_cert = None
        mock_args.ssl_key = None
        mock_args.tool_args = []

        with (
            patch("synapse.commands.start.subprocess.Popen") as mock_popen,
            patch("synapse.commands.start.time.sleep"),
            patch("synapse.commands.start.os.makedirs"),
            patch("builtins.open", MagicMock()),
        ):
            mock_process = MagicMock()
            mock_process.poll.return_value = None
            mock_process.pid = 12345
            mock_popen.return_value = mock_process

            cmd_start(mock_args)

        captured = capsys.readouterr()
        assert "Starting claude on port 8100" in captured.out
        assert "PID: 12345" in captured.out

    def test_foreground_mode_runs_directly(self, mock_args, capsys):
        """Should run directly in foreground mode."""
        mock_args.profile = "claude"
        mock_args.port = 8100
        mock_args.foreground = True
        mock_args.ssl_cert = None
        mock_args.ssl_key = None
        mock_args.tool_args = []

        with patch("synapse.commands.start.subprocess.run") as mock_run:
            cmd_start(mock_args)

        captured = capsys.readouterr()
        assert "foreground" in captured.out
        mock_run.assert_called_once()


# ==============================================================================
# Tests for cmd_stop
# ==============================================================================


class TestCmdStop:
    """Tests for cmd_stop command."""

    def test_no_running_agent(self, mock_args, temp_registry, capsys):
        """Should exit with error when no agent running."""
        mock_args.target = "claude"
        mock_args.all = False

        with (
            patch("synapse.cli.AgentRegistry", return_value=temp_registry),
            patch("synapse.cli.PortManager") as mock_pm_class,
        ):
            mock_pm = mock_pm_class.return_value
            mock_pm.get_running_instances.return_value = []

            with pytest.raises(SystemExit) as exc_info:
                cmd_stop(mock_args)

            assert exc_info.value.code == 1
            captured = capsys.readouterr()
            assert "No running agent found" in captured.out

    def test_stop_single_agent(self, mock_args, temp_registry, capsys):
        """Should stop single running agent."""
        mock_args.target = "claude"
        mock_args.all = False

        running_info = {
            "agent_id": "synapse-claude-8100",
            "pid": 12345,
        }

        with (
            patch("synapse.cli.AgentRegistry", return_value=temp_registry),
            patch("synapse.cli.PortManager") as mock_pm_class,
            patch("synapse.cli.os.kill") as mock_kill,
        ):
            mock_pm = mock_pm_class.return_value
            mock_pm.get_running_instances.return_value = [running_info]

            cmd_stop(mock_args)

            mock_kill.assert_called_once_with(12345, 15)  # SIGTERM = 15

        captured = capsys.readouterr()
        assert "Stopped synapse-claude-8100" in captured.out

    def test_stop_all_agents(self, mock_args, temp_registry, capsys):
        """Should stop all agents with --all flag."""
        mock_args.target = "claude"
        mock_args.all = True

        running_infos = [
            {"agent_id": "synapse-claude-8100", "pid": 12345},
            {"agent_id": "synapse-claude-8101", "pid": 12346},
        ]

        with (
            patch("synapse.cli.AgentRegistry", return_value=temp_registry),
            patch("synapse.cli.PortManager") as mock_pm_class,
            patch("synapse.cli.os.kill") as mock_kill,
        ):
            mock_pm = mock_pm_class.return_value
            mock_pm.get_running_instances.return_value = running_infos

            cmd_stop(mock_args)

            assert mock_kill.call_count == 2

    def test_stop_process_not_found(self, mock_args, temp_registry, capsys):
        """Should handle ProcessLookupError gracefully."""
        mock_args.target = "claude"
        mock_args.all = False

        running_info = {
            "agent_id": "synapse-claude-8100",
            "pid": 99999,
        }

        with (
            patch("synapse.cli.AgentRegistry", return_value=temp_registry),
            patch("synapse.cli.PortManager") as mock_pm_class,
            patch("synapse.cli.os.kill", side_effect=ProcessLookupError),
        ):
            mock_pm = mock_pm_class.return_value
            mock_pm.get_running_instances.return_value = [running_info]

            cmd_stop(mock_args)

        captured = capsys.readouterr()
        assert "Process 99999 not found" in captured.out

    def test_stop_by_agent_id(self, mock_args, temp_registry, capsys):
        """Should stop agent by specific agent ID."""
        mock_args.target = "synapse-claude-8100"
        mock_args.all = False

        agent_info = {
            "agent_id": "synapse-claude-8100",
            "pid": 12345,
        }

        with (
            patch("synapse.cli.AgentRegistry") as mock_registry_cls,
            patch("synapse.cli.os.kill") as mock_kill,
        ):
            mock_registry = mock_registry_cls.return_value
            mock_registry.get_agent.return_value = agent_info

            cmd_stop(mock_args)

            mock_registry.get_agent.assert_called_once_with("synapse-claude-8100")
            mock_kill.assert_called_once_with(12345, 15)

        captured = capsys.readouterr()
        assert "Stopped synapse-claude-8100" in captured.out

    def test_stop_by_agent_id_not_found(self, mock_args, capsys):
        """Should exit with error when agent ID not found."""
        mock_args.target = "synapse-claude-9999"
        mock_args.all = False

        with patch("synapse.cli.AgentRegistry") as mock_registry_cls:
            mock_registry = mock_registry_cls.return_value
            mock_registry.get_agent.return_value = None

            with pytest.raises(SystemExit) as exc_info:
                cmd_stop(mock_args)

            assert exc_info.value.code == 1

        captured = capsys.readouterr()
        assert "Agent not found" in captured.out


class TestStopAgent:
    """Tests for _stop_agent helper function."""

    def test_stop_agent_with_valid_pid(self, temp_registry, capsys):
        """Should stop agent with valid PID."""
        info = {"agent_id": "test-agent", "pid": 12345}

        with patch("synapse.cli.os.kill") as mock_kill:
            _stop_agent(temp_registry, info)

            mock_kill.assert_called_once_with(12345, 15)

        captured = capsys.readouterr()
        assert "Stopped test-agent" in captured.out

    def test_stop_agent_no_pid(self, temp_registry, capsys):
        """Should handle missing PID."""
        info = {"agent_id": "test-agent"}

        _stop_agent(temp_registry, info)

        captured = capsys.readouterr()
        assert "No PID found" in captured.out


# ==============================================================================
# Tests for cmd_logs
# ==============================================================================


class TestCmdLogs:
    """Tests for cmd_logs command."""

    def test_logs_file_not_found(self, mock_args, capsys):
        """Should exit with error when log file not found."""
        mock_args.profile = "nonexistent"
        mock_args.follow = False
        mock_args.lines = 50

        with patch("synapse.cli.os.path.exists", return_value=False):
            with pytest.raises(SystemExit) as exc_info:
                cmd_logs(mock_args)

            assert exc_info.value.code == 1

        captured = capsys.readouterr()
        assert "No logs found" in captured.out

    def test_logs_show_last_lines(self, mock_args):
        """Should show last N lines of log file."""
        mock_args.profile = "claude"
        mock_args.follow = False
        mock_args.lines = 100

        with (
            patch("synapse.cli.os.path.exists", return_value=True),
            patch("synapse.cli.subprocess.run") as mock_run,
        ):
            cmd_logs(mock_args)

            mock_run.assert_called_once()
            call_args = mock_run.call_args[0][0]
            assert "tail" in call_args
            assert "-n" in call_args
            assert "100" in call_args

    def test_logs_follow_mode(self, mock_args):
        """Should use tail -f in follow mode."""
        mock_args.profile = "claude"
        mock_args.follow = True
        mock_args.lines = 50

        with (
            patch("synapse.cli.os.path.exists", return_value=True),
            patch("synapse.cli.subprocess.run") as mock_run,
        ):
            cmd_logs(mock_args)

            call_args = mock_run.call_args[0][0]
            assert "tail" in call_args
            assert "-f" in call_args


# ==============================================================================
# Tests for cmd_send
# ==============================================================================


class TestCmdSend:
    """Tests for cmd_send command."""

    def test_send_message(self, mock_args, capsys):
        """Should send message to target agent."""
        mock_args.target = "gemini"
        mock_args.message = "Hello Gemini"
        mock_args.priority = 3
        mock_args.want_response = None

        with patch("synapse.cli.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="Task created", stderr="")
            cmd_send(mock_args)

            call_args = mock_run.call_args
            cmd = call_args[0][0]
            assert "send" in cmd
            assert "--target" in cmd
            assert "gemini" in cmd
            assert "--priority" in cmd
            assert "3" in cmd

        captured = capsys.readouterr()
        assert "Task created" in captured.out

    def test_send_with_response_flag(self, mock_args, capsys):
        """Should pass --response flag to a2a.py."""
        mock_args.target = "codex"
        mock_args.message = "Test"
        mock_args.priority = 1
        mock_args.want_response = True

        with patch("synapse.cli.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="Success", stderr="")
            cmd_send(mock_args)

            cmd = mock_run.call_args[0][0]
            assert "--response" in cmd

    def test_send_with_no_response_flag(self, mock_args, capsys):
        """Should pass --no-response flag to a2a.py."""
        mock_args.target = "codex"
        mock_args.message = "Test"
        mock_args.priority = 1
        mock_args.want_response = False

        with patch("synapse.cli.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="Success", stderr="")
            cmd_send(mock_args)

            cmd = mock_run.call_args[0][0]
            assert "--no-response" in cmd


# ==============================================================================
# Tests for history commands
# ==============================================================================


class TestCmdHistoryList:
    """Tests for cmd_history_list command."""

    def test_history_disabled(self, mock_args, capsys):
        """Should show message when history is disabled."""
        mock_args.limit = 50
        mock_args.agent = None

        with patch("synapse.history.HistoryManager") as mock_hm_class:
            mock_hm = MagicMock()
            mock_hm.enabled = False
            mock_hm_class.from_env.return_value = mock_hm

            cmd_history_list(mock_args)

        captured = capsys.readouterr()
        assert "History is disabled" in captured.out

    def test_history_empty(self, mock_args, capsys):
        """Should show message when no history."""
        mock_args.limit = 50
        mock_args.agent = None

        with patch("synapse.history.HistoryManager") as mock_hm_class:
            mock_hm = MagicMock()
            mock_hm.enabled = True
            mock_hm.list_observations.return_value = []
            mock_hm_class.from_env.return_value = mock_hm

            cmd_history_list(mock_args)

        captured = capsys.readouterr()
        assert "No task history found" in captured.out

    def test_history_list_with_entries(self, mock_args, capsys):
        """Should display history entries."""
        mock_args.limit = 50
        mock_args.agent = None

        observations = [
            {
                "task_id": "task-123",
                "agent_name": "claude",
                "status": "completed",
                "timestamp": "2024-01-01T12:00:00",
                "input": "Test input message",
            }
        ]

        with patch("synapse.history.HistoryManager") as mock_hm_class:
            mock_hm = MagicMock()
            mock_hm.enabled = True
            mock_hm.list_observations.return_value = observations
            mock_hm_class.from_env.return_value = mock_hm

            cmd_history_list(mock_args)

        captured = capsys.readouterr()
        assert "task-123" in captured.out
        assert "claude" in captured.out
        assert "completed" in captured.out


class TestCmdHistoryShow:
    """Tests for cmd_history_show command."""

    def test_history_show_not_found(self, mock_args, capsys):
        """Should exit when task not found."""
        mock_args.task_id = "nonexistent-task"

        with patch("synapse.history.HistoryManager") as mock_hm_class:
            mock_hm = MagicMock()
            mock_hm.enabled = True
            mock_hm.get_observation.return_value = None
            mock_hm_class.from_env.return_value = mock_hm

            with pytest.raises(SystemExit) as exc_info:
                cmd_history_show(mock_args)

            assert exc_info.value.code == 1

        captured = capsys.readouterr()
        assert "Task not found" in captured.out

    def test_history_show_displays_details(self, mock_args, capsys):
        """Should display task details."""
        mock_args.task_id = "task-123"

        observation = {
            "task_id": "task-123",
            "agent_name": "claude",
            "status": "completed",
            "session_id": "session-456",
            "timestamp": "2024-01-01T12:00:00",
            "input": "Test input",
            "output": "Test output",
            "metadata": None,
        }

        with patch("synapse.history.HistoryManager") as mock_hm_class:
            mock_hm = MagicMock()
            mock_hm.enabled = True
            mock_hm.get_observation.return_value = observation
            mock_hm_class.from_env.return_value = mock_hm

            cmd_history_show(mock_args)

        captured = capsys.readouterr()
        assert "task-123" in captured.out
        assert "claude" in captured.out
        assert "Test input" in captured.out
        assert "Test output" in captured.out


class TestCmdHistorySearch:
    """Tests for cmd_history_search command."""

    def test_history_search_no_matches(self, mock_args, capsys):
        """Should show message when no matches."""
        mock_args.keywords = ["nonexistent"]
        mock_args.logic = "OR"
        mock_args.case_sensitive = False
        mock_args.limit = 50
        mock_args.agent = None

        with patch("synapse.history.HistoryManager") as mock_hm_class:
            mock_hm = MagicMock()
            mock_hm.enabled = True
            mock_hm.search_observations.return_value = []
            mock_hm_class.from_env.return_value = mock_hm

            cmd_history_search(mock_args)

        captured = capsys.readouterr()
        assert "No matches found" in captured.out

    def test_history_search_with_results(self, mock_args, capsys):
        """Should display search results."""
        mock_args.keywords = ["test"]
        mock_args.logic = "OR"
        mock_args.case_sensitive = False
        mock_args.limit = 50
        mock_args.agent = None

        observations = [
            {
                "task_id": "task-123",
                "agent_name": "claude",
                "status": "completed",
                "timestamp": "2024-01-01T12:00:00",
                "input": "Test message",
            }
        ]

        with patch("synapse.history.HistoryManager") as mock_hm_class:
            mock_hm = MagicMock()
            mock_hm.enabled = True
            mock_hm.search_observations.return_value = observations
            mock_hm_class.from_env.return_value = mock_hm

            cmd_history_search(mock_args)

        captured = capsys.readouterr()
        assert "Found 1 matches" in captured.out


class TestCmdHistoryCleanup:
    """Tests for cmd_history_cleanup command."""

    def test_history_cleanup_requires_days_or_max_size(self, mock_args, capsys):
        """Should error when neither --days nor --max-size provided."""
        mock_args.days = None
        mock_args.max_size = None
        mock_args.dry_run = False
        mock_args.force = False
        mock_args.no_vacuum = False

        with patch("synapse.history.HistoryManager") as mock_hm_class:
            mock_hm = MagicMock()
            mock_hm.enabled = True
            mock_hm_class.from_env.return_value = mock_hm

            with pytest.raises(SystemExit) as exc_info:
                cmd_history_cleanup(mock_args)

            assert exc_info.value.code == 1

        captured = capsys.readouterr()
        assert "Specify --days or --max-size" in captured.out

    def test_history_cleanup_mutual_exclusive(self, mock_args, capsys):
        """Should error when both --days and --max-size provided."""
        mock_args.days = 30
        mock_args.max_size = 100
        mock_args.dry_run = False
        mock_args.force = False
        mock_args.no_vacuum = False

        with patch("synapse.history.HistoryManager") as mock_hm_class:
            mock_hm = MagicMock()
            mock_hm.enabled = True
            mock_hm_class.from_env.return_value = mock_hm

            with pytest.raises(SystemExit) as exc_info:
                cmd_history_cleanup(mock_args)

            assert exc_info.value.code == 1

        captured = capsys.readouterr()
        assert "only one of --days or --max-size" in captured.out


class TestCmdHistoryStats:
    """Tests for cmd_history_stats command."""

    def test_history_stats_empty(self, mock_args, capsys):
        """Should show message when no history."""
        mock_args.agent = None

        with patch("synapse.history.HistoryManager") as mock_hm_class:
            mock_hm = MagicMock()
            mock_hm.enabled = True
            mock_hm.get_statistics.return_value = {"total_tasks": 0}
            mock_hm_class.from_env.return_value = mock_hm

            cmd_history_stats(mock_args)

        captured = capsys.readouterr()
        assert "No task history found" in captured.out

    def test_history_stats_displays_stats(self, mock_args, capsys):
        """Should display statistics."""
        mock_args.agent = None

        stats = {
            "total_tasks": 100,
            "completed": 80,
            "failed": 15,
            "canceled": 5,
            "success_rate": 80.0,
            "db_size_mb": 1.5,
            "oldest_task": "2024-01-01",
            "newest_task": "2024-12-31",
            "date_range_days": 365,
            "by_agent": {
                "claude": {"total": 50, "completed": 45, "failed": 3, "canceled": 2},
                "gemini": {"total": 50, "completed": 35, "failed": 12, "canceled": 3},
            },
        }

        with patch("synapse.history.HistoryManager") as mock_hm_class:
            mock_hm = MagicMock()
            mock_hm.enabled = True
            mock_hm.get_statistics.return_value = stats
            mock_hm_class.from_env.return_value = mock_hm

            cmd_history_stats(mock_args)

        captured = capsys.readouterr()
        assert "Total Tasks:     100" in captured.out
        assert "Success Rate:    80.0%" in captured.out
        assert "claude" in captured.out


class TestCmdHistoryExport:
    """Tests for cmd_history_export command."""

    def test_history_export_invalid_format(self, mock_args, capsys):
        """Should error on invalid format."""
        mock_args.format = "xml"
        mock_args.agent = None
        mock_args.limit = None
        mock_args.output = None

        with patch("synapse.history.HistoryManager") as mock_hm_class:
            mock_hm = MagicMock()
            mock_hm.enabled = True
            mock_hm_class.from_env.return_value = mock_hm

            with pytest.raises(SystemExit) as exc_info:
                cmd_history_export(mock_args)

            assert exc_info.value.code == 1

        captured = capsys.readouterr()
        assert "Invalid format" in captured.out

    def test_history_export_to_stdout(self, mock_args, capsys):
        """Should export to stdout when no output file."""
        mock_args.format = "json"
        mock_args.agent = None
        mock_args.limit = None
        mock_args.output = None

        with patch("synapse.history.HistoryManager") as mock_hm_class:
            mock_hm = MagicMock()
            mock_hm.enabled = True
            mock_hm.export_observations.return_value = '{"data": []}'
            mock_hm_class.from_env.return_value = mock_hm

            cmd_history_export(mock_args)

        captured = capsys.readouterr()
        assert '{"data": []}' in captured.out

    def test_history_export_to_file(self, mock_args, capsys, temp_synapse_dir):
        """Should export to file when output specified."""
        output_file = temp_synapse_dir / "export.json"
        mock_args.format = "json"
        mock_args.agent = None
        mock_args.limit = None
        mock_args.output = str(output_file)

        with patch("synapse.history.HistoryManager") as mock_hm_class:
            mock_hm = MagicMock()
            mock_hm.enabled = True
            mock_hm.export_observations.return_value = '{"data": []}'
            mock_hm_class.from_env.return_value = mock_hm

            cmd_history_export(mock_args)

        assert output_file.exists()
        assert output_file.read_text() == '{"data": []}'


# ==============================================================================
# Tests for external agent commands
# ==============================================================================


class TestCmdExternalAdd:
    """Tests for cmd_external_add command."""

    def test_external_add_success(self, mock_args, capsys):
        """Should add external agent successfully."""
        mock_args.url = "https://agent.example.com"
        mock_args.alias = "example"

        mock_agent = MagicMock()
        mock_agent.name = "Example Agent"
        mock_agent.alias = "example"
        mock_agent.url = "https://agent.example.com"
        mock_agent.description = "An example agent"
        mock_agent.skills = []

        with patch("synapse.cli.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.discover.return_value = mock_agent
            mock_get_client.return_value = mock_client

            cmd_external_add(mock_args)

        captured = capsys.readouterr()
        assert "Added external agent: Example Agent" in captured.out

    def test_external_add_failure(self, mock_args, capsys):
        """Should exit with error when discovery fails."""
        mock_args.url = "https://invalid.example.com"
        mock_args.alias = None

        with patch("synapse.cli.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.discover.return_value = None
            mock_get_client.return_value = mock_client

            with pytest.raises(SystemExit) as exc_info:
                cmd_external_add(mock_args)

            assert exc_info.value.code == 1


class TestCmdExternalList:
    """Tests for cmd_external_list command."""

    def test_external_list_empty(self, mock_args, capsys):
        """Should show message when no external agents."""
        with patch("synapse.cli.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.list_agents.return_value = []
            mock_get_client.return_value = mock_client

            cmd_external_list(mock_args)

        captured = capsys.readouterr()
        assert "No external agents registered" in captured.out

    def test_external_list_with_agents(self, mock_args, capsys):
        """Should display external agents."""
        mock_agent = MagicMock()
        mock_agent.alias = "example"
        mock_agent.name = "Example Agent"
        mock_agent.url = "https://agent.example.com"
        mock_agent.last_seen = "2024-01-01T12:00:00"

        with patch("synapse.cli.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.list_agents.return_value = [mock_agent]
            mock_get_client.return_value = mock_client

            cmd_external_list(mock_args)

        captured = capsys.readouterr()
        assert "example" in captured.out
        assert "Example Agent" in captured.out


class TestCmdExternalRemove:
    """Tests for cmd_external_remove command."""

    def test_external_remove_success(self, mock_args, capsys):
        """Should remove external agent."""
        mock_args.alias = "example"

        with patch("synapse.cli.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.remove_agent.return_value = True
            mock_get_client.return_value = mock_client

            cmd_external_remove(mock_args)

        captured = capsys.readouterr()
        assert "Removed external agent: example" in captured.out

    def test_external_remove_not_found(self, mock_args, capsys):
        """Should exit with error when agent not found."""
        mock_args.alias = "nonexistent"

        with patch("synapse.cli.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.remove_agent.return_value = False
            mock_get_client.return_value = mock_client

            with pytest.raises(SystemExit) as exc_info:
                cmd_external_remove(mock_args)

            assert exc_info.value.code == 1


class TestCmdExternalSend:
    """Tests for cmd_external_send command."""

    def test_external_send_success(self, mock_args, capsys):
        """Should send message to external agent."""
        mock_args.alias = "example"
        mock_args.message = "Hello"
        mock_args.wait = False

        mock_task = MagicMock()
        mock_task.id = "task-123"
        mock_task.status = "working"
        mock_task.artifacts = []

        with patch("synapse.cli.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.send_message.return_value = mock_task
            mock_get_client.return_value = mock_client

            cmd_external_send(mock_args)

        captured = capsys.readouterr()
        assert "Task ID: task-123" in captured.out
        assert "Status: working" in captured.out


class TestCmdExternalInfo:
    """Tests for cmd_external_info command."""

    def test_external_info_not_found(self, mock_args, capsys):
        """Should exit when agent not found."""
        mock_args.alias = "nonexistent"

        with patch("synapse.cli.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.registry.get.return_value = None
            mock_get_client.return_value = mock_client

            with pytest.raises(SystemExit) as exc_info:
                cmd_external_info(mock_args)

            assert exc_info.value.code == 1

    def test_external_info_displays_details(self, mock_args, capsys):
        """Should display agent details."""
        mock_args.alias = "example"

        mock_agent = MagicMock()
        mock_agent.name = "Example Agent"
        mock_agent.alias = "example"
        mock_agent.url = "https://agent.example.com"
        mock_agent.description = "An example agent"
        mock_agent.added_at = "2024-01-01T00:00:00"
        mock_agent.last_seen = "2024-01-02T12:00:00"
        mock_agent.capabilities = {"streaming": True}
        mock_agent.skills = [{"name": "code", "description": "Code generation"}]

        with patch("synapse.cli.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.registry.get.return_value = mock_agent
            mock_get_client.return_value = mock_client

            cmd_external_info(mock_args)

        captured = capsys.readouterr()
        assert "Example Agent" in captured.out
        assert "example" in captured.out
        assert "streaming: True" in captured.out
        assert "code" in captured.out


# ==============================================================================
# Tests for auth commands
# ==============================================================================


class TestCmdAuthGenerateKey:
    """Tests for cmd_auth_generate_key command."""

    def test_generate_single_key(self, mock_args, capsys):
        """Should generate single API key."""
        mock_args.count = 1
        mock_args.export = False

        with patch("synapse.cli.generate_api_key", return_value="synapse_test123"):
            cmd_auth_generate_key(mock_args)

        captured = capsys.readouterr()
        assert "synapse_test123" in captured.out

    def test_generate_multiple_keys(self, mock_args, capsys):
        """Should generate multiple API keys."""
        mock_args.count = 3
        mock_args.export = False

        keys = ["key1", "key2", "key3"]
        with patch("synapse.cli.generate_api_key", side_effect=keys):
            cmd_auth_generate_key(mock_args)

        captured = capsys.readouterr()
        for key in keys:
            assert key in captured.out

    def test_generate_export_format(self, mock_args, capsys):
        """Should output in export format."""
        mock_args.count = 1
        mock_args.export = True

        with patch("synapse.cli.generate_api_key", return_value="synapse_test123"):
            cmd_auth_generate_key(mock_args)

        captured = capsys.readouterr()
        assert "export SYNAPSE_API_KEYS=synapse_test123" in captured.out

    def test_generate_export_format_multiple(self, mock_args, capsys):
        """Should output multiple keys in export format."""
        mock_args.count = 2
        mock_args.export = True

        keys = ["key1", "key2"]
        with patch("synapse.cli.generate_api_key", side_effect=keys):
            cmd_auth_generate_key(mock_args)

        captured = capsys.readouterr()
        assert "export SYNAPSE_API_KEYS=key1,key2" in captured.out


class TestCmdAuthSetup:
    """Tests for cmd_auth_setup command."""

    def test_auth_setup_displays_instructions(self, mock_args, capsys):
        """Should display setup instructions."""
        with patch(
            "synapse.cli.generate_api_key", side_effect=["api_key", "admin_key"]
        ):
            cmd_auth_setup(mock_args)

        captured = capsys.readouterr()
        assert "Authentication Setup" in captured.out
        assert "api_key" in captured.out
        assert "admin_key" in captured.out
        assert "SYNAPSE_AUTH_ENABLED=true" in captured.out


# ==============================================================================
# Tests for init/reset commands
# ==============================================================================


class TestWriteDefaultSettings:
    """Tests for _write_default_settings helper function."""

    def test_write_creates_settings_file(self, temp_synapse_dir):
        """Should create settings.json with defaults."""
        settings_path = temp_synapse_dir / ".synapse" / "settings.json"

        result = _write_default_settings(settings_path)

        assert result is True
        assert settings_path.exists()

        with open(settings_path) as f:
            data = json.load(f)
            assert "env" in data

    def test_write_creates_parent_dirs(self, temp_synapse_dir):
        """Should create parent directories if needed."""
        settings_path = temp_synapse_dir / "nested" / "path" / "settings.json"

        result = _write_default_settings(settings_path)

        assert result is True
        assert settings_path.exists()


class TestCmdInit:
    """Tests for cmd_init command."""

    def test_init_cancelled_when_no_scope(self, mock_args, capsys):
        """Should cancel when user doesn't select scope."""
        mock_args.scope = None

        with patch("synapse.cli._prompt_scope_selection", return_value=None):
            cmd_init(mock_args)

        captured = capsys.readouterr()
        assert "Cancelled" in captured.out

    def test_init_user_scope(self, mock_args, temp_empty_dir, capsys, monkeypatch):
        """Should create .synapse/ in user scope."""
        mock_args.scope = "user"

        monkeypatch.setattr(Path, "home", lambda: temp_empty_dir)

        cmd_init(mock_args)

        captured = capsys.readouterr()
        assert "Created" in captured.out
        assert (temp_empty_dir / ".synapse" / "settings.json").exists()

    def test_init_project_scope(self, mock_args, temp_empty_dir, capsys, monkeypatch):
        """Should create .synapse/ in project scope."""
        mock_args.scope = "project"

        monkeypatch.setattr(Path, "cwd", lambda: temp_empty_dir)

        cmd_init(mock_args)

        captured = capsys.readouterr()
        assert "Created" in captured.out
        assert (temp_empty_dir / ".synapse" / "settings.json").exists()

    def test_init_copies_template_files(
        self, mock_args, temp_empty_dir, capsys, monkeypatch
    ):
        """Should copy all template files from templates/.synapse/ to target."""
        mock_args.scope = "project"

        monkeypatch.setattr(Path, "cwd", lambda: temp_empty_dir)

        cmd_init(mock_args)

        # Check that template files were copied
        synapse_dir = temp_empty_dir / ".synapse"
        assert (synapse_dir / "settings.json").exists()
        assert (synapse_dir / "default.md").exists()
        assert (synapse_dir / "file-safety.md").exists()
        assert (synapse_dir / "delegate.md").exists()
        assert (synapse_dir / "gemini.md").exists()

    def test_init_asks_overwrite_for_existing_synapse_dir(
        self, mock_args, temp_empty_dir, capsys, monkeypatch
    ):
        """Should ask for confirmation when .synapse/ directory exists."""
        mock_args.scope = "project"

        monkeypatch.setattr(Path, "cwd", lambda: temp_empty_dir)

        # Create existing .synapse directory with custom content
        synapse_dir = temp_empty_dir / ".synapse"
        synapse_dir.mkdir(parents=True)
        custom_file = synapse_dir / "custom.md"
        custom_file.write_text("custom content")
        settings_file = synapse_dir / "settings.json"
        settings_file.write_text('{"custom": "value"}')

        # User says no to overwrite
        with patch("builtins.input", return_value="n"):
            cmd_init(mock_args)

        captured = capsys.readouterr()
        assert "Cancelled" in captured.out

        # Custom file should still exist
        assert custom_file.exists()
        assert custom_file.read_text() == "custom content"

    def test_init_overwrites_when_user_confirms(
        self, mock_args, temp_empty_dir, capsys, monkeypatch
    ):
        """Should overwrite .synapse/ when user confirms."""
        mock_args.scope = "project"

        monkeypatch.setattr(Path, "cwd", lambda: temp_empty_dir)

        # Create existing .synapse directory with old settings
        synapse_dir = temp_empty_dir / ".synapse"
        synapse_dir.mkdir(parents=True)
        settings_file = synapse_dir / "settings.json"
        settings_file.write_text('{"old": "value"}')

        # User says yes to overwrite
        with patch("builtins.input", return_value="y"):
            cmd_init(mock_args)

        captured = capsys.readouterr()
        assert "Created" in captured.out

        # Settings should have new default values
        with open(settings_file) as f:
            data = json.load(f)
            assert "env" in data
            assert "old" not in data


class TestCmdReset:
    """Tests for cmd_reset command."""

    def test_reset_cancelled_when_no_scope(self, mock_args, capsys):
        """Should cancel when user doesn't select scope."""
        mock_args.scope = None
        mock_args.force = False

        with patch("synapse.cli._prompt_reset_scope_selection", return_value=None):
            cmd_reset(mock_args)

        captured = capsys.readouterr()
        assert "Cancelled" in captured.out

    def test_reset_with_force_flag(
        self, mock_args, temp_synapse_dir, capsys, monkeypatch
    ):
        """Should reset without confirmation when --force."""
        mock_args.scope = "project"
        mock_args.force = True

        monkeypatch.setattr(Path, "cwd", lambda: temp_synapse_dir)

        # Create initial settings
        settings_path = temp_synapse_dir / ".synapse" / "settings.json"
        settings_path.write_text('{"custom": "value"}')

        cmd_reset(mock_args)

        captured = capsys.readouterr()
        assert "Reset" in captured.out

        # Should have default settings now
        with open(settings_path) as f:
            data = json.load(f)
            assert "env" in data


# ==============================================================================
# Tests for install_skills
# ==============================================================================


class TestInstallSkills:
    """Tests for install_skills function."""

    def test_install_skills_skips_existing(self, temp_synapse_dir, monkeypatch):
        """Should skip installation when skills already exist in both .claude and .codex."""
        # Create existing skill directories in both .claude and .codex
        claude_skill_dir = temp_synapse_dir / ".claude" / "skills" / "synapse-a2a"
        claude_skill_dir.mkdir(parents=True)
        codex_skill_dir = temp_synapse_dir / ".codex" / "skills" / "synapse-a2a"
        codex_skill_dir.mkdir(parents=True)

        monkeypatch.setattr(Path, "home", lambda: temp_synapse_dir)

        # Mock synapse package location
        import synapse

        with patch.object(
            synapse, "__file__", str(temp_synapse_dir / "synapse" / "__init__.py")
        ):
            # Should not raise, just skip silently
            install_skills()

    def test_install_skills_handles_errors(self, capsys):
        """Should silently ignore installation errors."""
        with patch("synapse.cli.Path.home", side_effect=Exception("Test error")):
            # Should not raise
            install_skills()

        # No error output expected
        captured = capsys.readouterr()
        assert "error" not in captured.out.lower()
