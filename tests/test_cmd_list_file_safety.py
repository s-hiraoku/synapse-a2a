"Tests for file safety integration in synapse list command."

from unittest.mock import MagicMock, patch

import pytest

from synapse.commands.list import ListCommand
from synapse.registry import AgentRegistry


@pytest.fixture
def mock_registry():
    """Create a mock registry with sample agents."""
    registry = MagicMock(spec=AgentRegistry)
    registry.list_agents.return_value = {
        "synapse-claude-8100": {
            "agent_type": "claude",
            "port": 8100,
            "status": "READY",
            "pid": 12345,
            "working_dir": "/tmp/work",
            "endpoint": "http://localhost:8100",
        },
        "synapse-gemini-8101": {
            "agent_type": "gemini",
            "port": 8101,
            "status": "PROCESSING",
            "pid": 12346,
            "working_dir": "/tmp/work",
            "endpoint": "http://localhost:8101",
        },
    }
    return registry


@pytest.fixture
def list_command():
    """Create a ListCommand instance with mocks."""
    return ListCommand(
        registry_factory=MagicMock(),
        is_process_alive=lambda pid: True,
        is_port_open=lambda host, port, timeout: True,
        clear_screen=MagicMock(),
        time_module=MagicMock(),
        print_func=MagicMock(),
    )


def test_render_table_file_safety_disabled(list_command, mock_registry):
    """Test table rendering when file safety is disabled."""
    with patch("synapse.commands.list.FileSafetyManager") as MockFSM:
        # Setup FSM to be disabled
        fsm_instance = MockFSM.from_env.return_value
        fsm_instance.enabled = False

        output = list_command._render_agent_table(mock_registry)

        # Verify header does NOT contain EDITING FILE column
        header_line = output.split("\n")[0]
        assert "EDITING FILE" not in header_line
        assert "TYPE" in header_line
        assert "PORT" in header_line


def test_render_table_file_safety_enabled_no_locks(list_command, mock_registry):
    """Test table rendering when enabled but no files are locked."""
    with patch("synapse.commands.list.FileSafetyManager") as MockFSM:
        # Setup FSM to be enabled but return no locks
        fsm_instance = MockFSM.from_env.return_value
        fsm_instance.enabled = True
        fsm_instance.list_locks.return_value = []
        fsm_instance.get_stale_locks.return_value = []

        output = list_command._render_agent_table(mock_registry)

        # Verify header DOES contain EDITING FILE column
        header_line = output.split("\n")[0]
        assert "EDITING FILE" in header_line

        # Verify columns alignment in header (simple check)
        assert output.find("EDITING FILE") > output.find("PID")

        # Verify content lines show placeholder for no locks
        lines = output.split("\n")[2:]  # Skip header and separator
        for line in lines:
            if "claude" in line:
                # Should show placeholder (e.g. "-")
                assert " -" in line or line.rstrip().endswith("-")


def test_render_table_file_safety_shows_locked_file(list_command, mock_registry):
    """Test table rendering shows locked file name."""
    with patch("synapse.commands.list.FileSafetyManager") as MockFSM:
        fsm_instance = MockFSM.from_env.return_value
        fsm_instance.enabled = True
        fsm_instance.get_stale_locks.return_value = []

        # Setup locks: claude locks a file
        def mock_list_locks(
            agent_name=None, *, pid=None, agent_type=None, include_stale=True
        ):
            if pid == 12345:
                return [{"file_path": "/path/to/important_file.py"}]
            return []

        fsm_instance.list_locks.side_effect = mock_list_locks

        output = list_command._render_agent_table(mock_registry)

        # Check output contains the file name (basename only)
        assert "important_file.py" in output
        # Ensure full path is NOT shown to keep table clean
        assert "/path/to/important_file.py" not in output

        # Verify specific line for claude has the file
        lines = output.split("\n")
        claude_line = next(line for line in lines if "claude" in line)
        assert "important_file.py" in claude_line


def test_render_table_shows_only_one_locked_file(list_command, mock_registry):
    """Test table shows only one file even if multiple are locked."""
    with patch("synapse.commands.list.FileSafetyManager") as MockFSM:
        fsm_instance = MockFSM.from_env.return_value
        fsm_instance.enabled = True
        fsm_instance.get_stale_locks.return_value = []

        # Setup locks: claude locks multiple files
        def mock_list_locks(
            agent_name=None, *, pid=None, agent_type=None, include_stale=True
        ):
            if pid == 12345:
                return [
                    {"file_path": "/path/to/file1.py"},
                    {"file_path": "/path/to/file2.py"},
                ]
            return []

        fsm_instance.list_locks.side_effect = mock_list_locks

        output = list_command._render_agent_table(mock_registry)

        lines = output.split("\n")
        claude_line = next(line for line in lines if "claude" in line)

        # Check that ONLY one file is displayed
        has_file1 = "file1.py" in claude_line
        has_file2 = "file2.py" in claude_line

        assert has_file1 or has_file2
        # Ensure both are NOT displayed (concatenated or listed)
        assert not (has_file1 and has_file2)
