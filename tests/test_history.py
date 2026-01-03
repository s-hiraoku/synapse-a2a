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
            metadata={"sender_id": "test-sender"}
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
            "context_id": "ctx-123"
        }

        history_manager.save_observation(
            task_id="task-456",
            agent_name="claude",
            session_id="session-xyz",
            input_text="Input",
            output_text="Output",
            status="completed",
            metadata=metadata
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
                status="completed"
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
                status="completed"
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
            status="completed"
        )
        history_manager.save_observation(
            task_id="task-2",
            agent_name="gemini",
            session_id="session-1",
            input_text="Input 2",
            output_text="Output 2",
            status="completed"
        )
        history_manager.save_observation(
            task_id="task-3",
            agent_name="claude",
            session_id="session-1",
            input_text="Input 3",
            output_text="Output 3",
            status="completed"
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
                status="completed"
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
            status="completed"
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
            "error": {
                "code": "COMMAND_NOT_FOUND",
                "message": "Command 'xyz' not found"
            }
        }

        history_manager.save_observation(
            task_id="task-failed",
            agent_name="claude",
            session_id="session-1",
            input_text="Run xyz command",
            output_text="Error: command not found",
            status="failed",
            metadata=metadata
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
            status="canceled"
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
            status="completed"
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
                status="completed"
            )

        threads = [threading.Thread(target=save_observation, args=(i,)) for i in range(10)]
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
                role="user",
                parts=[TextPart(text="Write a hello world function")]
            ),
            artifacts=[
                Artifact(type="code", data={"language": "python", "code": "def hello(): print('hello')"})
            ],
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
            context_id="ctx-abc",
            metadata={
                "sender": {
                    "sender_id": "synapse-gemini-8110",
                    "sender_type": "gemini"
                }
            }
        )

        # Extract input
        input_text = task.message.parts[0].text if task.message else ""

        # Extract output from artifacts
        output_parts = []
        for artifact in task.artifacts:
            if artifact.type == "code":
                output_parts.append(f"[Code: {artifact.data.get('language', 'text')}]\n{artifact.data.get('code', '')}")
            elif artifact.type == "text":
                output_parts.append(artifact.data)
        output_text = "\n".join(output_parts)

        # Save to history
        manager.save_observation(
            task_id=task.id,
            agent_name="claude",  # Receiver agent
            session_id=task.context_id or "default",
            input_text=input_text,
            output_text=output_text,
            status=task.status,
            metadata=task.metadata
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
