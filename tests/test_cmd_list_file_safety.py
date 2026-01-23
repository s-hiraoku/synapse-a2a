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
    registry.get_transport_display.return_value = "-"
    return registry


@pytest.fixture
def list_command():
    """Create a ListCommand instance with mocks."""
    return ListCommand(
        registry_factory=MagicMock(),
        is_process_alive=lambda pid: True,
        is_port_open=lambda host, port, timeout=0.5: True,
        clear_screen=MagicMock(),
        time_module=MagicMock(),
        print_func=MagicMock(),
    )


def test_get_agent_data_file_safety_disabled(list_command, mock_registry):
    """Test that file safety column is not added when disabled."""
    with patch("synapse.commands.list.FileSafetyManager") as MockFSM:
        fsm_instance = MockFSM.from_env.return_value
        fsm_instance.enabled = False

        agents, stale_locks, show_file_safety = list_command._get_agent_data(
            mock_registry
        )

        assert show_file_safety is False
        # Check no editing_file key added
        for agent in agents:
            assert "editing_file" not in agent


def test_get_agent_data_file_safety_enabled_no_locks(list_command, mock_registry):
    """Test that file safety is shown with placeholder when no locks."""
    with patch("synapse.commands.list.FileSafetyManager") as MockFSM:
        fsm_instance = MockFSM.from_env.return_value
        fsm_instance.enabled = True
        fsm_instance.list_locks.return_value = []
        fsm_instance.get_stale_locks.return_value = []

        agents, stale_locks, show_file_safety = list_command._get_agent_data(
            mock_registry
        )

        assert show_file_safety is True
        # Check editing_file key added with placeholder
        for agent in agents:
            assert "editing_file" in agent
            assert agent["editing_file"] == "-"


def test_get_agent_data_file_safety_shows_locked_file(list_command, mock_registry):
    """Test that file safety shows locked file name."""
    with patch("synapse.commands.list.FileSafetyManager") as MockFSM:
        fsm_instance = MockFSM.from_env.return_value
        fsm_instance.enabled = True
        fsm_instance.get_stale_locks.return_value = []

        def mock_list_locks(
            agent_name=None, *, pid=None, agent_type=None, include_stale=True
        ):
            if pid == 12345:
                return [{"file_path": "/path/to/important_file.py"}]
            return []

        fsm_instance.list_locks.side_effect = mock_list_locks

        agents, stale_locks, show_file_safety = list_command._get_agent_data(
            mock_registry
        )

        assert show_file_safety is True
        claude_agent = next(a for a in agents if a["agent_type"] == "claude")
        # Should show basename only
        assert claude_agent["editing_file"] == "important_file.py"


def test_get_agent_data_shows_only_one_locked_file(list_command, mock_registry):
    """Test that only first locked file is shown when multiple locked."""
    with patch("synapse.commands.list.FileSafetyManager") as MockFSM:
        fsm_instance = MockFSM.from_env.return_value
        fsm_instance.enabled = True
        fsm_instance.get_stale_locks.return_value = []

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

        agents, _, _ = list_command._get_agent_data(mock_registry)

        claude_agent = next(a for a in agents if a["agent_type"] == "claude")
        # Should show only first file
        assert claude_agent["editing_file"] == "file1.py"
        assert "file2.py" not in claude_agent["editing_file"]
