import argparse
from unittest.mock import MagicMock, patch

import pytest

from synapse.cli import (
    cmd_history_cleanup,
    cmd_history_export,
    cmd_history_list,
    cmd_history_search,
    cmd_history_show,
    cmd_history_stats,
)


class TestCliHistoryCommands:
    """Tests for history-related CLI commands."""

    @pytest.fixture
    def mock_args(self):
        """Create a mock args object."""
        args = MagicMock(spec=argparse.Namespace)
        args.limit = 50
        args.agent = None
        args.task_id = None
        args.keywords = []
        args.logic = "OR"
        args.case_sensitive = False
        args.days = None
        args.max_size = None
        args.dry_run = False
        args.force = False
        args.no_vacuum = False
        args.format = "json"
        args.output = None
        return args

    @patch("synapse.cli._get_history_manager")
    @patch("builtins.print")
    def test_cmd_history_list(self, mock_print, mock_get_hm, mock_args):
        """cmd_history_list should call list_observations and print results."""
        mock_hm_inst = mock_get_hm.return_value
        mock_hm_inst.enabled = True
        mock_hm_inst.list_observations.return_value = [
            {
                "task_id": "t1",
                "agent_name": "claude",
                "status": "completed",
                "timestamp": "2026-01-09 10:00:00",
                "input": "hi",
            }
        ]

        cmd_history_list(mock_args)

        mock_hm_inst.list_observations.assert_called_once_with(
            limit=50, agent_name=None
        )
        # Verify print was called
        printed_output = "\n".join(
            call.args[0] for call in mock_print.call_args_list if call.args
        )
        assert "t1" in printed_output
        assert "claude" in printed_output

    @patch("synapse.cli._get_history_manager")
    @patch("builtins.print")
    def test_cmd_history_show(self, mock_print, mock_get_hm, mock_args):
        """cmd_history_show should call get_observation and print details."""
        mock_args.task_id = "t1"
        mock_hm_inst = mock_get_hm.return_value
        mock_hm_inst.enabled = True
        mock_hm_inst.get_observation.return_value = {
            "task_id": "t1",
            "agent_name": "claude",
            "status": "completed",
            "session_id": "s1",
            "timestamp": "2026-01-09 10:00:00",
            "input": "hi",
            "output": "hello",
            "metadata": {},
        }

        cmd_history_show(mock_args)

        mock_hm_inst.get_observation.assert_called_once_with("t1")
        # Verify details were printed
        printed_output = "\n".join(
            call.args[0] for call in mock_print.call_args_list if call.args
        )
        assert "t1" in printed_output
        assert "claude" in printed_output
        assert "s1" in printed_output

    @patch("synapse.cli._get_history_manager")
    @patch("builtins.print")
    def test_cmd_history_search(self, mock_print, mock_get_hm, mock_args):
        """cmd_history_search should call search_observations."""
        mock_args.keywords = ["python"]
        mock_hm_inst = mock_get_hm.return_value
        mock_hm_inst.enabled = True
        mock_hm_inst.search_observations.return_value = [
            {
                "task_id": "t1",
                "agent_name": "claude",
                "status": "completed",
                "timestamp": "2026-01-09 10:00:00",
                "input": "hi python",
            }
        ]

        cmd_history_search(mock_args)

        mock_hm_inst.search_observations.assert_called_once_with(
            keywords=["python"],
            logic="OR",
            agent_name=None,
            case_sensitive=False,
            limit=50,
        )
        printed_output = "\n".join(
            call.args[0] for call in mock_print.call_args_list if call.args
        )
        assert "t1" in printed_output

    @patch("synapse.cli._get_history_manager")
    @patch("builtins.print")
    def test_cmd_history_cleanup_days(self, mock_print, mock_get_hm, mock_args):
        """cmd_history_cleanup --days should call cleanup_old_observations."""
        mock_args.days = 7
        mock_args.force = True
        mock_hm_inst = mock_get_hm.return_value
        mock_hm_inst.enabled = True
        mock_hm_inst.cleanup_old_observations.return_value = {
            "deleted_count": 5,
            "vacuum_reclaimed_mb": 0.5,
        }

        cmd_history_cleanup(mock_args)

        mock_hm_inst.cleanup_old_observations.assert_called_once_with(
            days=7, vacuum=True
        )

    @patch("synapse.cli._get_history_manager")
    @patch("builtins.print")
    def test_cmd_history_cleanup_size(self, mock_print, mock_get_hm, mock_args):
        """cmd_history_cleanup --max-size should call cleanup_by_size."""
        mock_args.max_size = 100
        mock_args.force = True
        mock_hm_inst = mock_get_hm.return_value
        mock_hm_inst.enabled = True
        mock_hm_inst.cleanup_by_size.return_value = {
            "deleted_count": 10,
            "vacuum_reclaimed_mb": 1.2,
        }

        cmd_history_cleanup(mock_args)

        mock_hm_inst.cleanup_by_size.assert_called_once_with(
            max_size_mb=100, vacuum=True
        )

    @patch("synapse.cli._get_history_manager")
    @patch("sqlite3.connect")
    @patch("builtins.print")
    def test_cmd_history_cleanup_dry_run(
        self, mock_print, mock_connect, mock_get_hm, mock_args
    ):
        """cmd_history_cleanup --dry-run should not call cleanup methods."""
        mock_args.days = 7
        mock_args.dry_run = True
        mock_hm_inst = mock_get_hm.return_value
        mock_hm_inst.enabled = True
        mock_hm_inst.db_path = "/tmp/test.db"

        mock_cursor = mock_connect.return_value.cursor.return_value
        mock_cursor.fetchone.return_value = [5]

        cmd_history_cleanup(mock_args)

        mock_hm_inst.cleanup_old_observations.assert_not_called()
        printed_output = "\n".join(
            call.args[0] for call in mock_print.call_args_list if call.args
        )
        assert "Would delete 5 observations" in printed_output

    @patch("synapse.cli._get_history_manager")
    @patch("builtins.print")
    def test_cmd_history_stats(self, mock_print, mock_get_hm, mock_args):
        """cmd_history_stats should call get_statistics."""
        mock_hm_inst = mock_get_hm.return_value
        mock_hm_inst.enabled = True
        mock_hm_inst.get_statistics.return_value = {
            "total_tasks": 10,
            "completed": 8,
            "failed": 1,
            "canceled": 1,
            "success_rate": 80.0,
            "db_size_mb": 0.5,
            "by_agent": {},
            "oldest_task": "2026-01-01",
            "newest_task": "2026-01-09",
            "date_range_days": 8,
        }

        cmd_history_stats(mock_args)

        mock_hm_inst.get_statistics.assert_called_once_with(agent_name=None)

    @patch("synapse.cli._get_history_manager")
    @patch("builtins.print")
    def test_cmd_history_export(self, mock_print, mock_get_hm, mock_args):
        """cmd_history_export should call export_observations."""
        mock_args.format = "json"
        mock_hm_inst = mock_get_hm.return_value
        mock_hm_inst.enabled = True
        mock_hm_inst.export_observations.return_value = "[]"

        cmd_history_export(mock_args)

        mock_hm_inst.export_observations.assert_called_once_with(
            format="json", agent_name=None, limit=50
        )

    @patch("synapse.cli._get_history_manager")
    @patch("builtins.open", new_callable=MagicMock)
    @patch("builtins.print")
    def test_cmd_history_export_to_file(
        self, mock_print, mock_open, mock_get_hm, mock_args
    ):
        """cmd_history_export --output file should write to file."""
        mock_args.output = "test.json"
        mock_hm_inst = mock_get_hm.return_value
        mock_hm_inst.enabled = True
        mock_hm_inst.export_observations.return_value = '{"data": "test"}'

        cmd_history_export(mock_args)

        mock_open.assert_called_once_with("test.json", "w")
        mock_open.return_value.__enter__.return_value.write.assert_called_once_with(
            '{"data": "test"}'
        )
