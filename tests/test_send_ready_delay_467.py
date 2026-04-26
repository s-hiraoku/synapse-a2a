"""Tests for delaying sends to READY targets in synapse send (#467)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def _make_args(
    *,
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


def _make_registry(target):
    reg = MagicMock()
    reg.list_agents.return_value = (
        {target["agent_id"]: target} if target is not None else {}
    )
    return reg


def _run_cmd_send(args, registries, *, monkeypatch, sleep_calls):
    from synapse.tools.a2a import cmd_send

    task = _make_task()

    def fake_sleep(seconds):
        sleep_calls.append(seconds)

    with (
        patch("synapse.tools.a2a.AgentRegistry", side_effect=registries),
        patch("synapse.tools.a2a.A2AClient") as mock_client_cls,
        patch("synapse.tools.a2a.is_process_running", return_value=True),
        patch("synapse.tools.a2a.is_port_open", return_value=True),
        patch("synapse.tools.a2a.build_sender_info", return_value={}),
        patch("synapse.tools.a2a._record_sent_message"),
        patch("synapse.tools.a2a.time.sleep", side_effect=fake_sleep),
        patch("os.getcwd", return_value="/tmp/project"),
    ):
        mock_client_cls.return_value.send_to_local.return_value = task
        cmd_send(args)


class TestSendReadyDelay467:
    """Tests for cmd_send delaying briefly before sending to READY targets."""

    def test_ready_status_triggers_delay(self, monkeypatch):
        """READY targets should sleep at least once before sending."""
        target = _make_target("READY")
        sleep_calls: list[float] = []
        registries = [
            _make_registry(target),
            *[_make_registry(target) for _ in range(8)],
        ]

        _run_cmd_send(
            _make_args(),
            registries,
            monkeypatch=monkeypatch,
            sleep_calls=sleep_calls,
        )

        assert sleep_calls
        assert sleep_calls == [0.25] * 8

    def test_processing_during_delay_breaks_immediately(self, monkeypatch):
        """READY delay should stop early when the target becomes PROCESSING."""
        ready = _make_target("READY")
        processing = _make_target("PROCESSING")
        sleep_calls: list[float] = []

        _run_cmd_send(
            _make_args(),
            [_make_registry(ready), _make_registry(processing)],
            monkeypatch=monkeypatch,
            sleep_calls=sleep_calls,
        )

        assert sleep_calls == [0.25]

    def test_ready_delay_zero_disables_feature(self, monkeypatch):
        """SYNAPSE_SEND_READY_DELAY=0 should send without sleeping."""
        target = _make_target("READY")
        sleep_calls: list[float] = []
        monkeypatch.setenv("SYNAPSE_SEND_READY_DELAY", "0")

        _run_cmd_send(
            _make_args(),
            [_make_registry(target)],
            monkeypatch=monkeypatch,
            sleep_calls=sleep_calls,
        )

        assert sleep_calls == []

    def test_silent_mode_skips_ready_delay(self, monkeypatch):
        """Silent sends should skip READY delay like PROCESSING wait."""
        target = _make_target("READY")
        sleep_calls: list[float] = []

        _run_cmd_send(
            _make_args(response_mode="silent"),
            [_make_registry(target)],
            monkeypatch=monkeypatch,
            sleep_calls=sleep_calls,
        )

        assert sleep_calls == []

    def test_force_flag_skips_ready_delay(self, monkeypatch):
        """--force should skip READY delay like PROCESSING wait."""
        target = _make_target("READY")
        sleep_calls: list[float] = []

        _run_cmd_send(
            _make_args(force=True),
            [_make_registry(target)],
            monkeypatch=monkeypatch,
            sleep_calls=sleep_calls,
        )

        assert sleep_calls == []

    def test_priority_5_skips_ready_delay(self, monkeypatch):
        """Emergency priority should skip READY delay."""
        target = _make_target("READY")
        sleep_calls: list[float] = []

        _run_cmd_send(
            _make_args(priority=5),
            [_make_registry(target)],
            monkeypatch=monkeypatch,
            sleep_calls=sleep_calls,
        )

        assert sleep_calls == []

    def test_target_disappearing_during_delay_continues_send(self, monkeypatch):
        """If refresh no longer finds the target, stop delaying and send."""
        ready = _make_target("READY")
        sleep_calls: list[float] = []

        _run_cmd_send(
            _make_args(),
            [_make_registry(ready), _make_registry(None)],
            monkeypatch=monkeypatch,
            sleep_calls=sleep_calls,
        )

        assert sleep_calls == [0.25]
