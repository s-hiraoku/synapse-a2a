"""Tests for task elapsed time display in CURRENT column (#297)."""

import json
import time

from synapse.commands.renderers.rich_renderer import RichRenderer, format_elapsed
from synapse.registry import AgentRegistry


class TestFormatElapsed:
    """Tests for format_elapsed helper function."""

    def test_format_elapsed_seconds(self):
        """Should format seconds-only values."""
        assert format_elapsed(0) == "0s"
        assert format_elapsed(5) == "5s"
        assert format_elapsed(59) == "59s"

    def test_format_elapsed_minutes(self):
        """Should format minutes + seconds."""
        assert format_elapsed(60) == "1m 0s"
        assert format_elapsed(135) == "2m 15s"
        assert format_elapsed(3599) == "59m 59s"

    def test_format_elapsed_hours(self):
        """Should format hours + minutes."""
        assert format_elapsed(3600) == "1h 0m"
        assert format_elapsed(7380) == "2h 3m"

    def test_format_elapsed_fractional(self):
        """Fractional seconds should be truncated."""
        assert format_elapsed(5.7) == "5s"
        assert format_elapsed(135.9) == "2m 15s"


class TestTaskReceivedAt:
    """Tests for task_received_at timestamp in registry."""

    def test_task_received_at_stored(self, tmp_path):
        """update_current_task should store task_received_at timestamp."""
        registry = AgentRegistry()
        registry.registry_dir = tmp_path

        # Register agent
        agent_id = "synapse-test-8100"
        registry.register(agent_id, "test", 8100)

        # Update current task
        before = time.time()
        registry.update_current_task(agent_id, "Review code")
        after = time.time()

        # Read registry file
        data = json.loads((tmp_path / f"{agent_id}.json").read_text())
        assert data["current_task_preview"] == "Review code"
        assert "task_received_at" in data
        assert before <= data["task_received_at"] <= after

    def test_task_received_at_cleared(self, tmp_path):
        """update_current_task(None) should clear task_received_at."""
        registry = AgentRegistry()
        registry.registry_dir = tmp_path

        agent_id = "synapse-test-8100"
        registry.register(agent_id, "test", 8100)

        # Set then clear
        registry.update_current_task(agent_id, "Review code")
        registry.update_current_task(agent_id, None)

        data = json.loads((tmp_path / f"{agent_id}.json").read_text())
        assert "current_task_preview" not in data
        assert "task_received_at" not in data


class TestCurrentColumnElapsed:
    """Tests for CURRENT column including elapsed time."""

    def test_current_column_includes_elapsed(self):
        """CURRENT column should show 'Review code (2m 15s)' format."""
        renderer = RichRenderer()
        agents = [
            {
                "agent_id": "synapse-test-8100",
                "agent_type": "test",
                "name": None,
                "status": "PROCESSING",
                "port": 8100,
                "pid": 1234,
                "working_dir": "test-dir",
                "endpoint": "http://localhost:8100",
                "current_task_preview": "Review code",
                "task_received_at": time.time() - 135,  # 2m 15s ago
                "transport": "-",
            }
        ]

        table = renderer.build_table(agents, columns=["CURRENT"])
        # Extract text from the Rich Table
        from io import StringIO

        from rich.console import Console

        console = Console(file=StringIO(), width=100)
        console.print(table)
        output = console.file.getvalue()

        # Should contain elapsed time
        assert "Review code" in output
        assert "2m" in output
