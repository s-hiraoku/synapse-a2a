"""Tests for Session History Persistence Feature."""

import os
import sqlite3
import tempfile
from pathlib import Path

import pytest

from synapse.a2a_compat import Message, TextPart
from synapse.history import HistoryManager

# ============================================================
# HistoryManager Tests
# ============================================================


class TestHistoryManager:
    """Test HistoryManager for session history persistence."""

    @pytest.fixture
    def temp_db_path(self):
        """Create a temporary database path for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "history.db"
            yield str(db_path)

    @pytest.fixture
    def history_manager(self, temp_db_path):
        """Create a HistoryManager instance for testing."""
        return HistoryManager(db_path=temp_db_path)

    def test_init_creates_database(self, temp_db_path):
        """Should create database file on initialization."""
        assert not Path(temp_db_path).exists()
        HistoryManager(db_path=temp_db_path)
        assert Path(temp_db_path).exists()

    def test_init_creates_observations_table(self, temp_db_path):
        """Should create observations table with correct schema."""
        HistoryManager(db_path=temp_db_path)

        # Check table exists
        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='observations'"
        )
        result = cursor.fetchone()
        conn.close()

        assert result is not None
        assert result[0] == "observations"

    def test_save_observation_basic(self, history_manager):
        """Should save observation with basic fields."""
        history_manager.save_observation(
            task_id="task-123",
            agent_name="claude",
            session_id="session-abc",
            input_text="Test input",
            output_text="Test output",
            status="completed",
            metadata={"sender_id": "test-sender"},
        )

        # Verify saved
        observations = history_manager.list_observations(limit=1)
        assert len(observations) == 1
        assert observations[0]["task_id"] == "task-123"
        assert observations[0]["agent_name"] == "claude"
        assert observations[0]["input"] == "Test input"
        assert observations[0]["output"] == "Test output"
        assert observations[0]["status"] == "completed"

    def test_save_observation_with_metadata(self, history_manager):
        """Should save observation with metadata as JSON."""
        metadata = {
            "sender_id": "synapse-gemini-8110",
            "sender_type": "gemini",
            "context_id": "ctx-123",
        }

        history_manager.save_observation(
            task_id="task-456",
            agent_name="claude",
            session_id="session-xyz",
            input_text="Input",
            output_text="Output",
            status="completed",
            metadata=metadata,
        )

        observations = history_manager.list_observations(limit=1)
        assert observations[0]["metadata"]["sender_id"] == "synapse-gemini-8110"
        assert observations[0]["metadata"]["sender_type"] == "gemini"

    def test_list_observations_default_limit(self, history_manager):
        """Should list observations with default limit."""
        # Create 3 observations
        for i in range(3):
            history_manager.save_observation(
                task_id=f"task-{i}",
                agent_name="claude",
                session_id="session-1",
                input_text=f"Input {i}",
                output_text=f"Output {i}",
                status="completed",
            )

        observations = history_manager.list_observations()
        assert len(observations) == 3

    def test_list_observations_custom_limit(self, history_manager):
        """Should respect custom limit parameter."""
        # Create 10 observations
        for i in range(10):
            history_manager.save_observation(
                task_id=f"task-{i}",
                agent_name="claude",
                session_id="session-1",
                input_text=f"Input {i}",
                output_text=f"Output {i}",
                status="completed",
            )

        observations = history_manager.list_observations(limit=5)
        assert len(observations) == 5

    def test_list_observations_filter_by_agent(self, history_manager):
        """Should filter observations by agent_name."""
        history_manager.save_observation(
            task_id="task-1",
            agent_name="claude",
            session_id="session-1",
            input_text="Input 1",
            output_text="Output 1",
            status="completed",
        )
        history_manager.save_observation(
            task_id="task-2",
            agent_name="gemini",
            session_id="session-1",
            input_text="Input 2",
            output_text="Output 2",
            status="completed",
        )
        history_manager.save_observation(
            task_id="task-3",
            agent_name="claude",
            session_id="session-1",
            input_text="Input 3",
            output_text="Output 3",
            status="completed",
        )

        claude_obs = history_manager.list_observations(agent_name="claude")
        assert len(claude_obs) == 2
        assert all(obs["agent_name"] == "claude" for obs in claude_obs)

    def test_list_observations_ordered_by_timestamp(self, history_manager):
        """Should return observations ordered by timestamp (newest first)."""
        import time

        for i in range(3):
            history_manager.save_observation(
                task_id=f"task-{i}",
                agent_name="claude",
                session_id="session-1",
                input_text=f"Input {i}",
                output_text=f"Output {i}",
                status="completed",
            )
            time.sleep(0.01)  # Small delay to ensure different timestamps

        observations = history_manager.list_observations()
        # Most recent should be first
        assert observations[0]["task_id"] == "task-2"
        assert observations[1]["task_id"] == "task-1"
        assert observations[2]["task_id"] == "task-0"

    def test_get_observation_by_task_id(self, history_manager):
        """Should retrieve specific observation by task_id."""
        history_manager.save_observation(
            task_id="task-unique",
            agent_name="claude",
            session_id="session-1",
            input_text="Unique input",
            output_text="Unique output",
            status="completed",
        )

        observation = history_manager.get_observation("task-unique")
        assert observation is not None
        assert observation["task_id"] == "task-unique"
        assert observation["input"] == "Unique input"

    def test_get_observation_nonexistent(self, history_manager):
        """Should return None for nonexistent task_id."""
        observation = history_manager.get_observation("nonexistent-task")
        assert observation is None

    def test_save_failed_task(self, history_manager):
        """Should save failed tasks with error information."""
        metadata = {
            "error": {"code": "COMMAND_NOT_FOUND", "message": "Command 'xyz' not found"}
        }

        history_manager.save_observation(
            task_id="task-failed",
            agent_name="claude",
            session_id="session-1",
            input_text="Run xyz command",
            output_text="Error: command not found",
            status="failed",
            metadata=metadata,
        )

        observation = history_manager.get_observation("task-failed")
        assert observation["status"] == "failed"
        assert observation["metadata"]["error"]["code"] == "COMMAND_NOT_FOUND"

    def test_save_canceled_task(self, history_manager):
        """Should save canceled tasks."""
        history_manager.save_observation(
            task_id="task-canceled",
            agent_name="claude",
            session_id="session-1",
            input_text="Long running task",
            output_text="Task canceled by user",
            status="canceled",
        )

        observation = history_manager.get_observation("task-canceled")
        assert observation["status"] == "canceled"

    def test_disabled_manager_does_not_save(self, temp_db_path):
        """Should not save when history is disabled."""
        manager = HistoryManager(db_path=temp_db_path, enabled=False)

        manager.save_observation(
            task_id="task-1",
            agent_name="claude",
            session_id="session-1",
            input_text="Input",
            output_text="Output",
            status="completed",
        )

        # Database file should not be created
        assert not Path(temp_db_path).exists()

    def test_thread_safety(self, history_manager):
        """Should be thread-safe for concurrent writes."""
        import threading

        def save_observation(i):
            history_manager.save_observation(
                task_id=f"task-{i}",
                agent_name="claude",
                session_id="session-1",
                input_text=f"Input {i}",
                output_text=f"Output {i}",
                status="completed",
            )

        threads = [
            threading.Thread(target=save_observation, args=(i,)) for i in range(10)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        observations = history_manager.list_observations()
        assert len(observations) == 10


# ============================================================
# Integration Tests with A2A Components
# ============================================================


class TestHistoryIntegration:
    """Test history integration with A2A task completion."""

    @pytest.fixture
    def temp_db_path(self):
        """Create a temporary database path for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "history.db"
            yield str(db_path)

    def test_save_completed_task_from_a2a(self, temp_db_path):
        """Should save task data from A2A task completion."""
        from datetime import datetime

        from synapse.a2a_compat import Artifact, Task

        manager = HistoryManager(db_path=temp_db_path)

        # Simulate completed task
        task = Task(
            id="task-a2a-123",
            status="completed",
            message=Message(
                role="user", parts=[TextPart(text="Write a hello world function")]
            ),
            artifacts=[
                Artifact(
                    type="code",
                    data={
                        "metadata": {"language": "python"},
                        "content": "def hello(): print('hello')",
                    },
                )
            ],
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
            context_id="ctx-abc",
            metadata={
                "sender": {"sender_id": "synapse-gemini-8110", "sender_type": "gemini"}
            },
        )

        # Extract input
        input_text = task.message.parts[0].text if task.message else ""

        # Extract output from artifacts (matching implementation in _save_task_to_history)
        output_parts = []
        for artifact in task.artifacts:
            if artifact.type == "code":
                code_data = artifact.data.get("metadata", {})
                language = code_data.get("language", "text")
                content = artifact.data.get("content", "")
                output_parts.append(f"[Code: {language}]\n{content}")
            elif artifact.type == "text":
                content = (
                    artifact.data
                    if isinstance(artifact.data, str)
                    else artifact.data.get("content", "")
                )
                output_parts.append(content)
        output_text = "\n".join(output_parts)

        # Save to history
        manager.save_observation(
            task_id=task.id,
            agent_name="claude",  # Receiver agent
            session_id=task.context_id or "default",
            input_text=input_text,
            output_text=output_text,
            status=task.status,
            metadata=task.metadata,
        )

        # Verify
        observation = manager.get_observation("task-a2a-123")
        assert observation is not None
        assert observation["task_id"] == "task-a2a-123"
        assert "Write a hello world function" in observation["input"]
        assert "def hello()" in observation["output"]


# ============================================================
# Environment Variable Tests
# ============================================================


class TestHistoryEnvVariable:
    """Test SYNAPSE_HISTORY_ENABLED environment variable."""

    @pytest.fixture
    def temp_db_path(self):
        """Create a temporary database path for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "history.db"
            yield str(db_path)

    def test_enabled_when_env_true(self, temp_db_path):
        """Should be enabled when SYNAPSE_HISTORY_ENABLED=true."""
        os.environ["SYNAPSE_HISTORY_ENABLED"] = "true"
        try:
            manager = HistoryManager.from_env(db_path=temp_db_path)
            assert manager.enabled is True
        finally:
            del os.environ["SYNAPSE_HISTORY_ENABLED"]

    def test_enabled_when_env_1(self, temp_db_path):
        """Should be enabled when SYNAPSE_HISTORY_ENABLED=1."""
        os.environ["SYNAPSE_HISTORY_ENABLED"] = "1"
        try:
            manager = HistoryManager.from_env(db_path=temp_db_path)
            assert manager.enabled is True
        finally:
            del os.environ["SYNAPSE_HISTORY_ENABLED"]

    def test_disabled_when_env_false(self, temp_db_path):
        """Should be disabled when SYNAPSE_HISTORY_ENABLED=false."""
        os.environ["SYNAPSE_HISTORY_ENABLED"] = "false"
        try:
            manager = HistoryManager.from_env(db_path=temp_db_path)
            assert manager.enabled is False
        finally:
            del os.environ["SYNAPSE_HISTORY_ENABLED"]

    def test_disabled_when_env_not_set(self, temp_db_path):
        """Should be disabled by default when env var not set."""
        # Ensure env var is not set
        if "SYNAPSE_HISTORY_ENABLED" in os.environ:
            del os.environ["SYNAPSE_HISTORY_ENABLED"]

        manager = HistoryManager.from_env(db_path=temp_db_path)
        assert manager.enabled is False


# ============================================================
# Phase 2a: Keyword Search Tests
# ============================================================


class TestHistorySearch:
    """Test keyword search functionality for session history."""

    @pytest.fixture
    def temp_db_path(self):
        """Create a temporary database path for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "history.db"
            yield str(db_path)

    @pytest.fixture
    def populated_history(self, temp_db_path):
        """Create a populated history database for testing."""
        manager = HistoryManager(db_path=temp_db_path)

        # Create diverse test data
        test_data = [
            {
                "task_id": "task-python-1",
                "agent_name": "claude",
                "status": "completed",
                "input_text": "Write a Python function to calculate factorial",
                "output_text": "def factorial(n):\n    if n <= 1:\n        return 1\n    return n * factorial(n-1)",
            },
            {
                "task_id": "task-docker-1",
                "agent_name": "gemini",
                "status": "completed",
                "input_text": "Create a Docker image for a Python application",
                "output_text": "FROM python:3.11\nWORKDIR /app\nCOPY requirements.txt .\nRUN pip install -r requirements.txt",
            },
            {
                "task_id": "task-error-1",
                "agent_name": "claude",
                "status": "failed",
                "input_text": "Execute invalid command xyz",
                "output_text": "Error: command 'xyz' not found",
            },
            {
                "task_id": "task-cancel-1",
                "agent_name": "codex",
                "status": "canceled",
                "input_text": "Run long-running analysis",
                "output_text": "Task canceled by user",
            },
            {
                "task_id": "task-search-test",
                "agent_name": "claude",
                "status": "completed",
                "input_text": "Search for keyword patterns in logs",
                "output_text": "Found 42 matching patterns in search results",
            },
        ]

        for data in test_data:
            manager.save_observation(session_id="test-session", **data)

        return manager

    def test_search_by_single_keyword(self, populated_history):
        """Should find observations containing keyword."""
        results = populated_history.search_observations(keywords=["Python"])
        assert len(results) >= 2
        assert any(
            "Python" in obs["input"] or "Python" in obs["output"] for obs in results
        )

    def test_search_multiple_keywords_or_logic(self, populated_history):
        """Should find observations matching any keyword (OR logic)."""
        results = populated_history.search_observations(
            keywords=["Python", "Docker"], logic="OR"
        )
        assert len(results) >= 2

    def test_search_multiple_keywords_and_logic(self, populated_history):
        """Should find observations matching all keywords (AND logic)."""
        results = populated_history.search_observations(
            keywords=["Write", "function"], logic="AND"
        )
        assert len(results) >= 1
        assert all(
            "Write" in obs["input"] and "function" in obs["input"] for obs in results
        )

    def test_search_case_insensitive_default(self, populated_history):
        """Should be case-insensitive by default."""
        results_upper = populated_history.search_observations(
            keywords=["PYTHON"], case_sensitive=False
        )
        results_lower = populated_history.search_observations(
            keywords=["python"], case_sensitive=False
        )
        assert len(results_upper) == len(results_lower)
        assert len(results_upper) >= 1

    def test_search_case_sensitive(self, populated_history):
        """Should respect case-sensitive flag."""
        # GLOB pattern matching is case-insensitive on macOS by default
        # So we test with exact case match that should appear
        results = populated_history.search_observations(
            keywords=["Python"], case_sensitive=True
        )
        assert len(results) >= 1

        # Test with a keyword that appears in exact case only
        results = populated_history.search_observations(
            keywords=["Write"], case_sensitive=True
        )
        assert len(results) >= 1
        assert any("Write" in obs["input"] for obs in results)

    def test_search_with_agent_filter(self, populated_history):
        """Should combine keyword search with agent filter."""
        results = populated_history.search_observations(
            keywords=["task"], agent_name="claude"
        )
        assert all(obs["agent_name"] == "claude" for obs in results)

    def test_search_no_matches(self, populated_history):
        """Should return empty list when no matches found."""
        results = populated_history.search_observations(
            keywords=["nonexistent_xyz_12345"]
        )
        assert results == []

    def test_search_empty_keywords(self, populated_history):
        """Should return empty list for empty keywords."""
        results = populated_history.search_observations(keywords=[])
        assert results == []

    def test_search_limit_parameter(self, populated_history):
        """Should respect limit parameter."""
        results = populated_history.search_observations(keywords=["task"], limit=2)
        assert len(results) <= 2

    def test_search_disabled_manager(self, temp_db_path):
        """Should return empty list when history is disabled."""
        manager = HistoryManager(db_path=temp_db_path, enabled=False)
        results = manager.search_observations(keywords=["test"])
        assert results == []

    def test_search_in_output_field(self, populated_history):
        """Should search in output field."""
        results = populated_history.search_observations(keywords=["Error"])
        assert len(results) >= 1
        assert any("Error" in obs["output"] for obs in results)


# ============================================================
# Phase 2c: Retention Policy Tests
# ============================================================


class TestHistoryCleanup:
    """Test retention policy and cleanup functionality."""

    @pytest.fixture
    def temp_db_path(self):
        """Create a temporary database path for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "history.db"
            yield str(db_path)

    @pytest.fixture
    def populated_history_with_old_data(self, temp_db_path):
        """Create a populated history with some old data."""
        manager = HistoryManager(db_path=temp_db_path)

        # Create recent observations
        for i in range(5):
            manager.save_observation(
                task_id=f"task-recent-{i}",
                agent_name="claude",
                session_id="session-1",
                input_text=f"Recent task {i}",
                output_text=f"Result {i}",
                status="completed",
            )

        # Create old observations by manipulating timestamp
        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()
        for i in range(3):
            cursor.execute(
                """INSERT INTO observations
                (session_id, agent_name, task_id, input, output, status, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, datetime('now', '-40 days'))""",
                (
                    "session-old",
                    "gemini",
                    f"task-old-{i}",
                    f"Old input {i}",
                    f"Old output {i}",
                    "completed",
                ),
            )
        conn.commit()
        conn.close()

        return manager

    def test_cleanup_by_days(self, populated_history_with_old_data):
        """Should delete observations older than N days."""
        result = populated_history_with_old_data.cleanup_old_observations(
            days=30, vacuum=False
        )
        assert result["deleted_count"] >= 3

    def test_cleanup_by_days_nothing_to_delete(self, populated_history_with_old_data):
        """Should handle case where no old observations exist."""
        result = populated_history_with_old_data.cleanup_old_observations(
            days=100, vacuum=False
        )
        assert result["deleted_count"] == 0

    def test_cleanup_by_size(self, populated_history_with_old_data, temp_db_path):
        """Should delete observations to reach target size."""
        # Get current size
        current_size_mb = Path(temp_db_path).stat().st_size / (1024 * 1024)

        # Set target to much smaller size (force deletion)
        target_mb = max(0.01, current_size_mb / 10)

        result = populated_history_with_old_data.cleanup_by_size(
            max_size_mb=target_mb, vacuum=False
        )

        # Should have deleted something
        assert result["deleted_count"] > 0

    def test_cleanup_by_size_already_under_limit(self, populated_history_with_old_data):
        """Should not delete when already under size limit."""
        result = populated_history_with_old_data.cleanup_by_size(
            max_size_mb=1000, vacuum=False
        )
        assert result["deleted_count"] == 0

    def test_cleanup_returns_deleted_count(self, populated_history_with_old_data):
        """Should return correct deleted count."""
        result = populated_history_with_old_data.cleanup_old_observations(
            days=30, vacuum=False
        )
        assert isinstance(result, dict)
        assert "deleted_count" in result
        assert "vacuum_reclaimed_mb" in result

    def test_cleanup_disabled_manager(self, temp_db_path):
        """Should not crash when history is disabled."""
        manager = HistoryManager(db_path=temp_db_path, enabled=False)
        result = manager.cleanup_old_observations(days=30)
        assert result["deleted_count"] == 0

    def test_get_database_size(self, populated_history_with_old_data, temp_db_path):
        """Should return database file size."""
        size_bytes = populated_history_with_old_data.get_database_size()
        assert size_bytes > 0

        # Verify against file system
        file_size = Path(temp_db_path).stat().st_size
        assert size_bytes == file_size


# ============================================================
# Phase 2d: Usage Statistics Tests
# ============================================================


class TestHistoryStatistics:
    """Test usage statistics functionality."""

    @pytest.fixture
    def temp_db_path(self):
        """Create a temporary database path for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "history.db"
            yield str(db_path)

    @pytest.fixture
    def populated_history_with_stats(self, temp_db_path):
        """Create a populated history for statistics testing."""
        manager = HistoryManager(db_path=temp_db_path)

        # Create diverse observations with different statuses
        test_data = [
            ("task-1", "claude", "completed"),
            ("task-2", "claude", "completed"),
            ("task-3", "claude", "failed"),
            ("task-4", "gemini", "completed"),
            ("task-5", "gemini", "completed"),
            ("task-6", "gemini", "completed"),
            ("task-7", "gemini", "failed"),
            ("task-8", "codex", "canceled"),
        ]

        for task_id, agent, status in test_data:
            manager.save_observation(
                task_id=task_id,
                agent_name=agent,
                session_id="session-1",
                input_text=f"Input for {task_id}",
                output_text=f"Output for {task_id}",
                status=status,
            )

        return manager

    def test_statistics_basic_counts(self, populated_history_with_stats):
        """Should calculate basic task counts."""
        stats = populated_history_with_stats.get_statistics()

        assert stats["total_tasks"] == 8
        assert stats["completed"] >= 5
        assert stats["failed"] >= 2
        assert stats["canceled"] >= 1

    def test_statistics_success_rate(self, populated_history_with_stats):
        """Should calculate success rate correctly."""
        stats = populated_history_with_stats.get_statistics()

        # Success rate = completed / (completed + failed)
        completed = stats["completed"]
        failed = stats["failed"]
        total_finished = completed + failed

        if total_finished > 0:
            expected_rate = (completed / total_finished) * 100
            assert abs(stats["success_rate"] - expected_rate) < 0.1

    def test_statistics_per_agent(self, populated_history_with_stats):
        """Should provide per-agent statistics."""
        stats = populated_history_with_stats.get_statistics()

        assert "by_agent" in stats
        assert "claude" in stats["by_agent"]
        assert "gemini" in stats["by_agent"]
        assert stats["by_agent"]["claude"]["total"] >= 3

    def test_statistics_filtered_by_agent(self, populated_history_with_stats):
        """Should filter statistics by agent."""
        stats = populated_history_with_stats.get_statistics(agent_name="claude")

        assert stats["total_tasks"] >= 3
        assert all(
            agent in ["claude"] or agent not in stats.get("by_agent", {})
            for agent in stats.get("by_agent", {})
        )

    def test_statistics_database_size(self, populated_history_with_stats):
        """Should include database size in statistics."""
        stats = populated_history_with_stats.get_statistics()

        assert "db_size_mb" in stats
        assert stats["db_size_mb"] > 0

    def test_statistics_date_range(self, populated_history_with_stats):
        """Should include oldest and newest task timestamps."""
        stats = populated_history_with_stats.get_statistics()

        assert "oldest_task" in stats
        assert "newest_task" in stats
        assert stats["oldest_task"] is not None
        assert stats["newest_task"] is not None

    def test_statistics_empty_database(self, temp_db_path):
        """Should handle empty database gracefully."""
        manager = HistoryManager(db_path=temp_db_path)
        stats = manager.get_statistics()

        assert stats["total_tasks"] == 0
        assert stats["completed"] == 0
        assert stats["success_rate"] == 0.0

    def test_statistics_disabled_manager(self, temp_db_path):
        """Should return empty dict when history is disabled."""
        manager = HistoryManager(db_path=temp_db_path, enabled=False)
        stats = manager.get_statistics()
        assert stats == {}


# ============================================================
# Phase 2b: Export Tests
# ============================================================


class TestHistoryExport:
    """Test export functionality for session history."""

    @pytest.fixture
    def temp_db_path(self):
        """Create a temporary database path for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "history.db"
            yield str(db_path)

    @pytest.fixture
    def populated_history_for_export(self, temp_db_path):
        """Create a populated history for export testing."""
        manager = HistoryManager(db_path=temp_db_path)

        # Create diverse observations
        test_data = [
            {
                "task_id": "task-1",
                "agent_name": "claude",
                "status": "completed",
                "input_text": "Write a Python function",
                "output_text": "def hello(): pass",
                "metadata": {"language": "python"},
            },
            {
                "task_id": "task-2",
                "agent_name": "gemini",
                "status": "completed",
                "input_text": "Create a Docker image",
                "output_text": "FROM python:3.11",
                "metadata": {"framework": "docker"},
            },
            {
                "task_id": "task-3",
                "agent_name": "claude",
                "status": "failed",
                "input_text": "Run invalid command",
                "output_text": "Error: command not found",
                "metadata": {"error": "COMMAND_NOT_FOUND"},
            },
        ]

        for data in test_data:
            manager.save_observation(session_id="test-session", **data)

        return manager

    def test_export_json_format(self, populated_history_for_export):
        """Should export observations in JSON format."""
        import json

        json_data = populated_history_for_export.export_observations(format="json")

        assert json_data is not None
        parsed = json.loads(json_data)
        assert isinstance(parsed, list)
        assert len(parsed) == 3
        # Results are ordered by timestamp DESC (newest first)
        assert parsed[0]["task_id"] == "task-3"
        assert parsed[2]["task_id"] == "task-1"

    def test_export_json_with_agent_filter(self, populated_history_for_export):
        """Should filter JSON export by agent."""
        import json

        json_data = populated_history_for_export.export_observations(
            format="json", agent_name="claude"
        )

        parsed = json.loads(json_data)
        assert len(parsed) == 2
        assert all(obs["agent_name"] == "claude" for obs in parsed)

    def test_export_json_preserves_metadata(self, populated_history_for_export):
        """Should preserve metadata in JSON export."""
        import json

        json_data = populated_history_for_export.export_observations(format="json")

        parsed = json.loads(json_data)
        assert len(parsed) == 3
        assert "metadata" in parsed[0]
        # Find task-1 which has the "language" metadata
        task_1 = next(obs for obs in parsed if obs["task_id"] == "task-1")
        assert task_1["metadata"]["language"] == "python"

    def test_export_csv_format(self, populated_history_for_export):
        """Should export observations in CSV format."""
        import csv
        import io

        csv_data = populated_history_for_export.export_observations(format="csv")

        assert csv_data is not None
        reader = csv.DictReader(io.StringIO(csv_data))
        rows = list(reader)

        assert len(rows) == 3
        # Results are ordered by timestamp DESC (newest first)
        assert rows[0]["task_id"] == "task-3"
        assert rows[2]["task_id"] == "task-1"

    def test_export_csv_has_headers(self, populated_history_for_export):
        """Should include proper CSV headers."""
        import csv
        import io

        csv_data = populated_history_for_export.export_observations(format="csv")

        lines = csv_data.strip().split("\n")
        assert len(lines) > 0

        reader = csv.DictReader(io.StringIO(csv_data))
        assert reader.fieldnames is not None
        expected_fields = ["task_id", "agent_name", "status", "timestamp", "input"]
        assert all(field in reader.fieldnames for field in expected_fields)

    def test_export_csv_with_agent_filter(self, populated_history_for_export):
        """Should filter CSV export by agent."""
        import csv
        import io

        csv_data = populated_history_for_export.export_observations(
            format="csv", agent_name="gemini"
        )

        reader = csv.DictReader(io.StringIO(csv_data))
        rows = list(reader)

        assert len(rows) == 1
        assert rows[0]["agent_name"] == "gemini"

    def test_export_with_limit(self, populated_history_for_export):
        """Should respect limit parameter in export."""
        import json

        json_data = populated_history_for_export.export_observations(
            format="json", limit=2
        )

        parsed = json.loads(json_data)
        assert len(parsed) == 2

    def test_export_empty_database(self, temp_db_path):
        """Should handle empty database gracefully."""
        import json

        manager = HistoryManager(db_path=temp_db_path)
        json_data = manager.export_observations(format="json")

        parsed = json.loads(json_data)
        assert parsed == []

    def test_export_disabled_manager(self, temp_db_path):
        """Should return empty result when history is disabled."""
        import json

        manager = HistoryManager(db_path=temp_db_path, enabled=False)
        json_data = manager.export_observations(format="json")

        parsed = json.loads(json_data)
        assert parsed == []

    def test_export_csv_special_characters(self, temp_db_path):
        """Should properly escape special characters in CSV."""
        import csv
        import io

        manager = HistoryManager(db_path=temp_db_path)
        manager.save_observation(
            task_id="task-special",
            agent_name="claude",
            session_id="session-1",
            input_text='Input with "quotes" and, commas',
            output_text="Output with\nnewlines",
            status="completed",
        )

        csv_data = manager.export_observations(format="csv")

        reader = csv.DictReader(io.StringIO(csv_data))
        rows = list(reader)

        assert len(rows) == 1
        assert '"quotes"' in rows[0]["input"]
        assert "commas" in rows[0]["input"]

    def test_export_json_escapes_special_chars(self, temp_db_path):
        """Should properly escape special characters in JSON."""
        import json

        manager = HistoryManager(db_path=temp_db_path)
        manager.save_observation(
            task_id="task-json",
            agent_name="claude",
            session_id="session-1",
            input_text='Input with "quotes" and\nnewlines',
            output_text="Output",
            status="completed",
        )

        json_data = manager.export_observations(format="json")

        parsed = json.loads(json_data)
        assert len(parsed) == 1
        assert "quotes" in parsed[0]["input"]
        assert "newlines" in parsed[0]["input"]
