import sys
from unittest.mock import patch

from synapse.cli import main


class TestCliMain:
    """Tests for synapse.cli.main() function."""

    @patch("synapse.cli.cmd_run_interactive")
    @patch("synapse.cli.PortManager")
    @patch("synapse.cli.AgentRegistry")
    @patch("synapse.cli.install_skills")
    def test_main_shortcut_claude(
        self, mock_install, mock_registry, mock_pm, mock_run_interactive
    ):
        """synapse claude should trigger interactive mode."""
        mock_pm_inst = mock_pm.return_value
        mock_pm_inst.get_available_port.return_value = 8100

        with patch.object(sys, "argv", ["synapse", "claude"]):
            main()

        mock_install.assert_called_once()
        mock_run_interactive.assert_called_once_with(
            "claude", 8100, [], name=None, role=None, no_setup=False
        )

    @patch("synapse.cli.cmd_run_interactive")
    @patch("synapse.cli.PortManager")
    @patch("synapse.cli.AgentRegistry")
    @patch("synapse.cli.install_skills")
    def test_main_shortcut_with_port(
        self, mock_install, mock_registry, mock_pm, mock_run_interactive
    ):
        """synapse claude --port 8105 should use specified port."""
        with patch.object(sys, "argv", ["synapse", "claude", "--port", "8105"]):
            main()

        mock_run_interactive.assert_called_once_with(
            "claude", 8105, [], name=None, role=None, no_setup=False
        )

    @patch("synapse.cli.cmd_run_interactive")
    @patch("synapse.cli.PortManager")
    @patch("synapse.cli.AgentRegistry")
    @patch("synapse.cli.install_skills")
    def test_main_shortcut_with_tool_args(
        self, mock_install, mock_registry, mock_pm, mock_run_interactive
    ):
        """synapse claude -- --model opus should pass tool args."""
        mock_pm_inst = mock_pm.return_value
        mock_pm_inst.get_available_port.return_value = 8100

        with patch.object(sys, "argv", ["synapse", "claude", "--", "--model", "opus"]):
            main()

        mock_run_interactive.assert_called_once_with(
            "claude", 8100, ["--model", "opus"], name=None, role=None, no_setup=False
        )

    @patch("synapse.cli.cmd_start")
    @patch("synapse.cli.install_skills")
    def test_main_command_start(self, mock_install, mock_cmd_start):
        """synapse start claude should call cmd_start."""
        with patch.object(sys, "argv", ["synapse", "start", "claude"]):
            main()

        mock_cmd_start.assert_called_once()
        args = mock_cmd_start.call_args[0][0]
        assert args.command == "start"
        assert args.profile == "claude"

    @patch("synapse.cli.cmd_list")
    @patch("synapse.cli.install_skills")
    def test_main_command_list(self, mock_install, mock_cmd_list):
        """synapse list should call cmd_list."""
        with patch.object(sys, "argv", ["synapse", "list"]):
            main()

        mock_cmd_list.assert_called_once()
        args = mock_cmd_list.call_args[0][0]
        assert args.command == "list"

    @patch("synapse.cli.cmd_history_list")
    @patch("synapse.cli.install_skills")
    def test_main_command_history_list(self, mock_install, mock_cmd_history_list):
        """synapse history list should call cmd_history_list."""
        with patch.object(sys, "argv", ["synapse", "history", "list"]):
            main()

        mock_cmd_history_list.assert_called_once()
        args = mock_cmd_history_list.call_args[0][0]
        assert args.command == "history"
        assert args.history_command == "list"

    @patch("synapse.cli.cmd_history_search")
    @patch("synapse.cli.install_skills")
    def test_main_command_history_search(self, mock_install, mock_cmd_history_search):
        """synapse history search keyword should call cmd_history_search."""
        with patch.object(sys, "argv", ["synapse", "history", "search", "python"]):
            main()

        mock_cmd_history_search.assert_called_once()
        args = mock_cmd_history_search.call_args[0][0]
        assert args.history_command == "search"
        assert args.keywords == ["python"]

    @patch("synapse.cli.cmd_history_cleanup")
    @patch("synapse.cli.install_skills")
    def test_main_command_history_cleanup(self, mock_install, mock_cmd_history_cleanup):
        """synapse history cleanup --days 7 should call cmd_history_cleanup."""
        with patch.object(
            sys, "argv", ["synapse", "history", "cleanup", "--days", "7"]
        ):
            main()

        mock_cmd_history_cleanup.assert_called_once()
        args = mock_cmd_history_cleanup.call_args[0][0]
        assert args.history_command == "cleanup"
        assert args.days == 7

    @patch("synapse.cli.cmd_stop")
    @patch("synapse.cli.install_skills")
    def test_main_command_stop(self, mock_install, mock_cmd_stop):
        """synapse stop claude should call cmd_stop."""
        with patch.object(sys, "argv", ["synapse", "stop", "claude"]):
            main()

        mock_cmd_stop.assert_called_once()
        args = mock_cmd_stop.call_args[0][0]
        assert args.target == "claude"

    @patch("synapse.cli.cmd_logs")
    @patch("synapse.cli.install_skills")
    def test_main_command_logs(self, mock_install, mock_cmd_logs):
        """synapse logs claude should call cmd_logs."""
        with patch.object(sys, "argv", ["synapse", "logs", "claude"]):
            main()

        mock_cmd_logs.assert_called_once()
        args = mock_cmd_logs.call_args[0][0]
        assert args.profile == "claude"

    @patch("synapse.cli.cmd_send")
    @patch("synapse.cli.install_skills")
    def test_main_command_send(self, mock_install, mock_cmd_send):
        """synapse send claude 'hello' should call cmd_send."""
        with patch.object(sys, "argv", ["synapse", "send", "claude", "hello"]):
            main()

        mock_cmd_send.assert_called_once()
        args = mock_cmd_send.call_args[0][0]
        assert args.target == "claude"
        assert args.message == "hello"

    @patch("synapse.cli.cmd_history_show")
    @patch("synapse.cli.install_skills")
    def test_main_command_history_show(self, mock_install, mock_cmd_history_show):
        """synapse history show task-123 should call cmd_history_show."""
        with patch.object(sys, "argv", ["synapse", "history", "show", "task-123"]):
            main()

        mock_cmd_history_show.assert_called_once()
        args = mock_cmd_history_show.call_args[0][0]
        assert args.task_id == "task-123"

    @patch("synapse.cli.cmd_history_stats")
    @patch("synapse.cli.install_skills")
    def test_main_command_history_stats(self, mock_install, mock_cmd_history_stats):
        """synapse history stats should call cmd_history_stats."""
        with patch.object(sys, "argv", ["synapse", "history", "stats"]):
            main()

        mock_cmd_history_stats.assert_called_once()
        args = mock_cmd_history_stats.call_args[0][0]
        assert args.history_command == "stats"

    @patch("synapse.cli.cmd_history_export")
    @patch("synapse.cli.install_skills")
    def test_main_command_history_export(self, mock_install, mock_cmd_history_export):
        """synapse history export --format json should call cmd_history_export."""
        with patch.object(
            sys, "argv", ["synapse", "history", "export", "--format", "json"]
        ):
            main()

        mock_cmd_history_export.assert_called_once()
        args = mock_cmd_history_export.call_args[0][0]
        assert args.history_command == "export"
        assert args.format == "json"

    @patch("synapse.cli.cmd_file_safety_status")
    @patch("synapse.cli.install_skills")
    def test_main_command_file_safety_status(self, mock_install, mock_cmd_fs_status):
        """synapse file-safety status should call cmd_file_safety_status."""
        with patch.object(sys, "argv", ["synapse", "file-safety", "status"]):
            main()

        mock_cmd_fs_status.assert_called_once()
        args = mock_cmd_fs_status.call_args[0][0]
        assert args.file_safety_command == "status"

    @patch("synapse.cli.cmd_file_safety_lock")
    @patch("synapse.cli.install_skills")
    def test_main_command_file_safety_lock(self, mock_install, mock_cmd_fs_lock):
        """synapse file-safety lock file.py agent should call cmd_file_safety_lock."""
        with patch.object(
            sys, "argv", ["synapse", "file-safety", "lock", "file.py", "claude"]
        ):
            main()

        mock_cmd_fs_lock.assert_called_once()
        args = mock_cmd_fs_lock.call_args[0][0]
        assert args.file_safety_command == "lock"
        assert args.file == "file.py"
        assert args.agent == "claude"

    @patch("synapse.cli.cmd_run_interactive")
    @patch("synapse.cli.PortManager")
    @patch("synapse.cli.AgentRegistry")
    @patch("synapse.cli.install_skills")
    def test_main_shortcut_with_name_and_role(
        self, mock_install, mock_registry, mock_pm, mock_run_interactive
    ):
        """synapse claude --name my-claude --role reviewer should pass name/role."""
        mock_pm_inst = mock_pm.return_value
        mock_pm_inst.get_available_port.return_value = 8100

        with patch.object(
            sys,
            "argv",
            ["synapse", "claude", "--name", "my-claude", "--role", "reviewer"],
        ):
            main()

        mock_run_interactive.assert_called_once_with(
            "claude", 8100, [], name="my-claude", role="reviewer", no_setup=False
        )

    @patch("synapse.cli.cmd_run_interactive")
    @patch("synapse.cli.PortManager")
    @patch("synapse.cli.AgentRegistry")
    @patch("synapse.cli.install_skills")
    def test_main_shortcut_with_no_setup(
        self, mock_install, mock_registry, mock_pm, mock_run_interactive
    ):
        """synapse claude --no-setup should skip interactive setup."""
        mock_pm_inst = mock_pm.return_value
        mock_pm_inst.get_available_port.return_value = 8100

        with patch.object(sys, "argv", ["synapse", "claude", "--no-setup"]):
            main()

        mock_run_interactive.assert_called_once_with(
            "claude", 8100, [], name=None, role=None, no_setup=True
        )

    @patch("synapse.cli.cmd_kill")
    @patch("synapse.cli.install_skills")
    def test_main_command_kill(self, mock_install, mock_cmd_kill):
        """synapse kill claude should call cmd_kill."""
        with patch.object(sys, "argv", ["synapse", "kill", "claude"]):
            main()

        mock_cmd_kill.assert_called_once()
        args = mock_cmd_kill.call_args[0][0]
        assert args.target == "claude"

    @patch("synapse.cli.cmd_jump")
    @patch("synapse.cli.install_skills")
    def test_main_command_jump(self, mock_install, mock_cmd_jump):
        """synapse jump claude should call cmd_jump."""
        with patch.object(sys, "argv", ["synapse", "jump", "claude"]):
            main()

        mock_cmd_jump.assert_called_once()
        args = mock_cmd_jump.call_args[0][0]
        assert args.target == "claude"

    @patch("synapse.cli.cmd_rename")
    @patch("synapse.cli.install_skills")
    def test_main_command_rename(self, mock_install, mock_cmd_rename):
        """synapse rename claude --name my-claude should call cmd_rename."""
        with patch.object(
            sys, "argv", ["synapse", "rename", "claude", "--name", "my-claude"]
        ):
            main()

        mock_cmd_rename.assert_called_once()
        args = mock_cmd_rename.call_args[0][0]
        assert args.target == "claude"
        assert args.name == "my-claude"
