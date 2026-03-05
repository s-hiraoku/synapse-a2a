"""Tests for synapse status command (#311)."""

import json
import time
from io import StringIO
from typing import Any
from unittest.mock import MagicMock

from synapse.commands.status import StatusCommand


def _make_agent_info(**overrides: Any) -> dict[str, Any]:
    """Create a minimal agent info dict for testing."""
    base = {
        "agent_id": "synapse-claude-8100",
        "agent_type": "claude",
        "name": "my-claude",
        "role": "code reviewer",
        "port": 8100,
        "status": "READY",
        "status_updated_at": time.time(),
        "pid": 12345,
        "working_dir": "/tmp/test",
        "endpoint": "http://localhost:8100",
        "registered_at": time.time() - 3600,
        "current_task_preview": None,
        "task_received_at": None,
    }
    base.update(overrides)
    return base


def _make_command(
    agent_info: dict | None = None,
    history_items: list | None = None,
    file_locks: list | None = None,
    task_board_tasks: list | None = None,
) -> tuple[StatusCommand, StringIO]:
    """Create a StatusCommand with mocked dependencies."""
    output = StringIO()

    mock_registry = MagicMock()
    if agent_info:
        mock_registry.resolve_agent.return_value = agent_info
    else:
        mock_registry.resolve_agent.return_value = None

    mock_history = MagicMock()
    mock_history.list_observations.return_value = history_items or []

    mock_file_safety = MagicMock()
    mock_file_safety.list_locks.return_value = file_locks or []
    mock_file_safety.enabled = bool(file_locks)

    mock_task_board = MagicMock()
    mock_task_board.list_tasks.return_value = task_board_tasks or []

    cmd = StatusCommand(
        registry=mock_registry,
        history_manager=mock_history,
        file_safety_manager=mock_file_safety,
        task_board=mock_task_board,
        output=output,
    )
    return cmd, output


class TestStatusTargetResolution:
    """Tests for target resolution."""

    def test_resolves_agent_by_name(self):
        """Should resolve agent by custom name."""
        info = _make_agent_info()
        cmd, output = _make_command(agent_info=info)
        cmd.run("my-claude")

        text = output.getvalue()
        assert "synapse-claude-8100" in text

    def test_not_found_prints_error(self):
        """Should print error when agent not found."""
        cmd, output = _make_command(agent_info=None)
        cmd.run("nonexistent")

        text = output.getvalue()
        assert "not found" in text.lower()


class TestStatusMetadata:
    """Tests for metadata display."""

    def test_displays_basic_info(self):
        """Should display agent ID, type, name, role, status."""
        info = _make_agent_info()
        cmd, output = _make_command(agent_info=info)
        cmd.run("my-claude")

        text = output.getvalue()
        assert "synapse-claude-8100" in text
        assert "claude" in text
        assert "my-claude" in text
        assert "code reviewer" in text
        assert "READY" in text

    def test_displays_uptime(self):
        """Should display uptime from registered_at."""
        info = _make_agent_info(registered_at=time.time() - 7200)  # 2 hours ago
        cmd, output = _make_command(agent_info=info)
        cmd.run("my-claude")

        text = output.getvalue()
        assert "2h" in text


class TestStatusCurrentTask:
    """Tests for current task with elapsed time."""

    def test_shows_current_task_with_elapsed(self):
        """Should show current task preview and elapsed time."""
        info = _make_agent_info(
            status="PROCESSING",
            current_task_preview="Review code",
            task_received_at=time.time() - 135,  # 2m 15s ago
        )
        cmd, output = _make_command(agent_info=info)
        cmd.run("my-claude")

        text = output.getvalue()
        assert "Review code" in text
        assert "2m" in text

    def test_no_current_task(self):
        """Should show 'None' when no current task."""
        info = _make_agent_info()
        cmd, output = _make_command(agent_info=info)
        cmd.run("my-claude")

        text = output.getvalue()
        # Should not crash, output should be valid
        assert "synapse-claude-8100" in text


class TestStatusHistory:
    """Tests for recent message history."""

    def test_shows_recent_messages(self):
        """Should show recent messages from history."""
        info = _make_agent_info()
        history = [
            {
                "task_id": "abc123",
                "direction": "incoming",
                "sender": "gemini",
                "preview": "Please review auth.py",
                "timestamp": "2026-01-15T10:00:00",
            }
        ]
        cmd, output = _make_command(agent_info=info, history_items=history)
        cmd.run("my-claude")

        text = output.getvalue()
        assert "abc123" in text or "review auth" in text.lower()


class TestStatusFileLocks:
    """Tests for file lock display."""

    def test_shows_file_locks(self):
        """Should show file locks when present."""
        info = _make_agent_info()
        locks = [
            {"file_path": "/tmp/test/src/main.py", "agent_name": "synapse-claude-8100"}
        ]
        cmd, output = _make_command(agent_info=info, file_locks=locks)
        cmd.run("my-claude")

        text = output.getvalue()
        assert "main.py" in text


class TestStatusTaskBoard:
    """Tests for task board integration."""

    def test_shows_assigned_tasks(self):
        """Should show tasks assigned to this agent."""
        info = _make_agent_info()
        tasks = [
            MagicMock(
                id="task-1",
                subject="Fix auth bug",
                status="pending",
                priority=3,
            )
        ]
        cmd, output = _make_command(agent_info=info, task_board_tasks=tasks)
        cmd.run("my-claude")

        text = output.getvalue()
        assert "Fix auth bug" in text or "task-1" in text


class TestStatusJsonOutput:
    """Tests for JSON output format."""

    def test_json_output(self):
        """Should output valid JSON when json=True."""
        info = _make_agent_info()
        cmd, output = _make_command(agent_info=info)
        cmd.run("my-claude", json_output=True)

        text = output.getvalue()
        data = json.loads(text)
        assert data["agent_id"] == "synapse-claude-8100"
        assert data["status"] == "READY"

    def test_json_not_found(self):
        """Should output error JSON when agent not found."""
        cmd, output = _make_command(agent_info=None)
        cmd.run("nonexistent", json_output=True)

        text = output.getvalue()
        data = json.loads(text)
        assert "error" in data


class TestStatusErrorHandling:
    """Tests for error handling."""

    def test_history_error_graceful(self):
        """Should handle history manager errors gracefully."""
        info = _make_agent_info()
        cmd, output = _make_command(agent_info=info)
        cmd._history_manager.list_observations.side_effect = Exception("DB error")

        # Should not raise
        cmd.run("my-claude")
        text = output.getvalue()
        assert "synapse-claude-8100" in text
