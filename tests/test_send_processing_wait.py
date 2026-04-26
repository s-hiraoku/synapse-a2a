"""Tests for waiting on PROCESSING targets in synapse send."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def _make_args(
    force: bool = False,
    priority: int = 3,
    response_mode: str = "notify",
):
    args = MagicMock()
    args.target = "claude"
    args.message = "hello"
    args.message_file = None
    args.task_file = None
    args.stdin = False
    args.attach = None
    args.priority = priority
    args.sender = None
    args.response_mode = response_mode
    args.force = force
    return args


def _make_target(status: str = "READY"):
    return {
        "agent_id": "synapse-claude-8104",
        "agent_type": "claude",
        "name": "claude-helper",
        "pid": 1234,
        "port": 8104,
        "endpoint": "http://localhost:8104",
        "working_dir": "/tmp/project",
        "status": status,
    }


def _make_task():
    task = MagicMock()
    task.id = "task-id"
    task.status = "completed"
    task.artifacts = []
    return task


class TestSendProcessingWait:
    """Tests for cmd_send waiting on PROCESSING targets."""

    def test_ready_target_sends_immediately_when_ready_delay_disabled(
        self, capsys, monkeypatch
    ):
        """READY targets should not trigger PROCESSING wait output."""
        from synapse.tools.a2a import cmd_send

        args = _make_args()
        target = _make_target("READY")
        reg = MagicMock()
        reg.list_agents.return_value = {target["agent_id"]: target}
        task = _make_task()
        monkeypatch.setenv("SYNAPSE_SEND_READY_DELAY", "0")

        with (
            patch("synapse.tools.a2a.AgentRegistry", return_value=reg),
            patch("synapse.tools.a2a.A2AClient") as mock_client_cls,
            patch("synapse.tools.a2a.is_process_running", return_value=True),
            patch("synapse.tools.a2a.is_port_open", return_value=True),
            patch("synapse.tools.a2a.build_sender_info", return_value={}),
            patch("synapse.tools.a2a._record_sent_message"),
            patch("synapse.tools.a2a.time.sleep") as mock_sleep,
            patch("os.getcwd", return_value="/tmp/project"),
        ):
            mock_client_cls.return_value.send_to_local.return_value = task
            cmd_send(args)

        mock_sleep.assert_not_called()
        captured = capsys.readouterr()
        assert "Waiting for" not in captured.err

    def test_processing_target_waits_until_ready_then_sends(self, capsys, monkeypatch):
        """PROCESSING targets should poll until READY before sending."""
        from synapse.tools.a2a import cmd_send

        args = _make_args()
        processing = _make_target("PROCESSING")
        ready = _make_target("READY")
        reg_initial = MagicMock()
        reg_initial.list_agents.return_value = {processing["agent_id"]: processing}
        reg_poll_1 = MagicMock()
        reg_poll_1.list_agents.return_value = {processing["agent_id"]: processing}
        reg_poll_2 = MagicMock()
        reg_poll_2.list_agents.return_value = {ready["agent_id"]: ready}
        task = _make_task()

        monkeypatch.setenv("SYNAPSE_SEND_WAIT_TIMEOUT", "5")
        monkeypatch.setenv("SYNAPSE_SEND_READY_DELAY", "0")

        with (
            patch(
                "synapse.tools.a2a.AgentRegistry",
                side_effect=[reg_initial, reg_poll_1, reg_poll_2],
            ),
            patch("synapse.tools.a2a.A2AClient") as mock_client_cls,
            patch("synapse.tools.a2a.is_process_running", return_value=True),
            patch("synapse.tools.a2a.is_port_open", return_value=True),
            patch("synapse.tools.a2a.build_sender_info", return_value={}),
            patch("synapse.tools.a2a._record_sent_message"),
            patch("synapse.tools.a2a.time.sleep") as mock_sleep,
            patch("os.getcwd", return_value="/tmp/project"),
        ):
            mock_client_cls.return_value.send_to_local.return_value = task
            cmd_send(args)

        assert mock_sleep.call_count == 2
        mock_sleep.assert_called_with(1)
        captured = capsys.readouterr()
        assert "Waiting for claude-helper to become READY... (0s)" in captured.err
        assert "Waiting for claude-helper to become READY... (1s)" in captured.err

    def test_processing_timeout_warns_and_continues(self, capsys, monkeypatch):
        """Timeout should warn and continue sending without blocking."""
        from synapse.tools.a2a import cmd_send

        args = _make_args()
        processing = _make_target("PROCESSING")
        registries = []
        for _ in range(4):
            reg = MagicMock()
            reg.list_agents.return_value = {processing["agent_id"]: processing}
            registries.append(reg)
        task = _make_task()

        monkeypatch.setenv("SYNAPSE_SEND_WAIT_TIMEOUT", "2")

        with (
            patch("synapse.tools.a2a.AgentRegistry", side_effect=registries),
            patch("synapse.tools.a2a.A2AClient") as mock_client_cls,
            patch("synapse.tools.a2a.is_process_running", return_value=True),
            patch("synapse.tools.a2a.is_port_open", return_value=True),
            patch("synapse.tools.a2a.build_sender_info", return_value={}),
            patch("synapse.tools.a2a._record_sent_message"),
            patch("synapse.tools.a2a.time.sleep"),
            patch("os.getcwd", return_value="/tmp/project"),
        ):
            mock_client_cls.return_value.send_to_local.return_value = task
            cmd_send(args)

        captured = capsys.readouterr()
        assert (
            "Warning: Timed out waiting for claude-helper to become READY"
            in captured.err
        )

    def test_force_skips_wait(self, capsys):
        """--force should skip PROCESSING wait logic."""
        from synapse.tools.a2a import cmd_send

        args = _make_args(force=True)
        processing = _make_target("PROCESSING")
        reg = MagicMock()
        reg.list_agents.return_value = {processing["agent_id"]: processing}
        task = _make_task()

        with (
            patch("synapse.tools.a2a.AgentRegistry", return_value=reg),
            patch("synapse.tools.a2a.A2AClient") as mock_client_cls,
            patch("synapse.tools.a2a.is_process_running", return_value=True),
            patch("synapse.tools.a2a.is_port_open", return_value=True),
            patch("synapse.tools.a2a.build_sender_info", return_value={}),
            patch("synapse.tools.a2a._record_sent_message"),
            patch("synapse.tools.a2a.time.sleep") as mock_sleep,
            patch("os.getcwd", return_value="/tmp/project"),
        ):
            mock_client_cls.return_value.send_to_local.return_value = task
            cmd_send(args)

        mock_sleep.assert_not_called()
        captured = capsys.readouterr()
        assert "Waiting for" not in captured.err

    def test_priority_five_skips_wait(self, capsys):
        """Emergency priority should skip PROCESSING wait logic."""
        from synapse.tools.a2a import cmd_send

        args = _make_args(priority=5)
        processing = _make_target("PROCESSING")
        reg = MagicMock()
        reg.list_agents.return_value = {processing["agent_id"]: processing}
        task = _make_task()

        with (
            patch("synapse.tools.a2a.AgentRegistry", return_value=reg),
            patch("synapse.tools.a2a.A2AClient") as mock_client_cls,
            patch("synapse.tools.a2a.is_process_running", return_value=True),
            patch("synapse.tools.a2a.is_port_open", return_value=True),
            patch("synapse.tools.a2a.build_sender_info", return_value={}),
            patch("synapse.tools.a2a._record_sent_message"),
            patch("synapse.tools.a2a.time.sleep") as mock_sleep,
            patch("os.getcwd", return_value="/tmp/project"),
        ):
            mock_client_cls.return_value.send_to_local.return_value = task
            cmd_send(args)

        mock_sleep.assert_not_called()
        captured = capsys.readouterr()
        assert "Waiting for" not in captured.err

    def test_silent_mode_skips_wait(self, capsys):
        """Silent sends should skip PROCESSING wait logic to avoid reply deadlocks."""
        from synapse.tools.a2a import cmd_send

        args = _make_args(response_mode="silent")
        processing = _make_target("PROCESSING")
        reg = MagicMock()
        reg.list_agents.return_value = {processing["agent_id"]: processing}
        task = _make_task()

        with (
            patch("synapse.tools.a2a.AgentRegistry", return_value=reg),
            patch("synapse.tools.a2a.A2AClient") as mock_client_cls,
            patch("synapse.tools.a2a.is_process_running", return_value=True),
            patch("synapse.tools.a2a.is_port_open", return_value=True),
            patch("synapse.tools.a2a.build_sender_info", return_value={}),
            patch("synapse.tools.a2a._record_sent_message"),
            patch("synapse.tools.a2a.time.sleep") as mock_sleep,
            patch("os.getcwd", return_value="/tmp/project"),
        ):
            mock_client_cls.return_value.send_to_local.return_value = task
            cmd_send(args)

        mock_sleep.assert_not_called()
        captured = capsys.readouterr()
        assert "Waiting for" not in captured.err
