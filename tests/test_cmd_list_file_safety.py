"Tests for file safety integration in synapse list command."

from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from synapse.commands.list import ListCommand
from synapse.registry import AgentRegistry

# Type alias for mock_list_locks function signature
MockListLocksType = Callable[..., list[dict[str, Any]]]


def create_mock_list_locks(
    pid_locks: dict[int, list[dict[str, Any]]] | None = None,
    agent_locks: dict[str, list[dict[str, Any]]] | None = None,
) -> MockListLocksType:
    """Create a mock list_locks function with configurable return values.

    Args:
        pid_locks: Dict mapping PID to list of lock dicts.
        agent_locks: Dict mapping agent_name to list of lock dicts.

    Returns:
        A function that returns locks based on pid or agent_name lookup.
    """
    pid_locks = pid_locks or {}
    agent_locks = agent_locks or {}

    def mock_list_locks(
        agent_name: str | None = None,
        *,
        pid: int | None = None,
        agent_type: str | None = None,
        include_stale: bool = True,
    ) -> list[dict[str, Any]]:
        if pid is not None and pid in pid_locks:
            return pid_locks[pid]
        if agent_name is not None and agent_name in agent_locks:
            return agent_locks[agent_name]
        return []

    return mock_list_locks


@pytest.fixture
def mock_registry() -> MagicMock:
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
def list_command() -> ListCommand:
    """Create a ListCommand instance with mocks."""
    return ListCommand(
        registry_factory=MagicMock(),
        is_process_alive=lambda pid: True,
        is_port_open=lambda host, port, timeout=0.5: True,
        clear_screen=MagicMock(),
        time_module=MagicMock(),
        print_func=MagicMock(),
    )


def test_get_agent_data_file_safety_disabled(
    list_command: ListCommand, mock_registry: MagicMock
) -> None:
    """Test that file safety column is not added when disabled."""
    with patch("synapse.commands.list.FileSafetyManager") as MockFSM:
        MockFSM.from_env.return_value.enabled = False

        agents, stale_locks, show_file_safety = list_command._get_agent_data(
            mock_registry
        )

        assert show_file_safety is False
        for agent in agents:
            assert "editing_file" not in agent


def test_get_agent_data_file_safety_enabled_no_locks(
    list_command: ListCommand, mock_registry: MagicMock
) -> None:
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
        for agent in agents:
            assert agent["editing_file"] == "-"


def test_get_agent_data_file_safety_shows_locked_file(
    list_command: ListCommand, mock_registry: MagicMock
) -> None:
    """Test that file safety shows locked file name."""
    with patch("synapse.commands.list.FileSafetyManager") as MockFSM:
        fsm_instance = MockFSM.from_env.return_value
        fsm_instance.enabled = True
        fsm_instance.get_stale_locks.return_value = []
        fsm_instance.list_locks.side_effect = create_mock_list_locks(
            pid_locks={12345: [{"file_path": "/path/to/important_file.py"}]}
        )

        agents, stale_locks, show_file_safety = list_command._get_agent_data(
            mock_registry
        )

        assert show_file_safety is True
        claude_agent = next(a for a in agents if a["agent_type"] == "claude")
        assert claude_agent["editing_file"] == "important_file.py"


def test_get_agent_data_file_safety_falls_back_to_agent_id(
    list_command: ListCommand, mock_registry: MagicMock
) -> None:
    """Test fallback to agent_id when PID lookup returns no locks."""
    with patch("synapse.commands.list.FileSafetyManager") as MockFSM:
        fsm_instance = MockFSM.from_env.return_value
        fsm_instance.enabled = True
        fsm_instance.get_stale_locks.return_value = []
        fsm_instance.list_locks.side_effect = create_mock_list_locks(
            pid_locks={12345: []},
            agent_locks={
                "synapse-claude-8100": [{"file_path": "/path/to/fallback_file.py"}]
            },
        )

        agents, _, show_file_safety = list_command._get_agent_data(mock_registry)

        assert show_file_safety is True
        claude_agent = next(a for a in agents if a["agent_type"] == "claude")
        assert claude_agent["editing_file"] == "fallback_file.py"


def test_get_agent_data_shows_only_one_locked_file(
    list_command: ListCommand, mock_registry: MagicMock
) -> None:
    """Test that only first locked file is shown when multiple locked."""
    with patch("synapse.commands.list.FileSafetyManager") as MockFSM:
        fsm_instance = MockFSM.from_env.return_value
        fsm_instance.enabled = True
        fsm_instance.get_stale_locks.return_value = []
        fsm_instance.list_locks.side_effect = create_mock_list_locks(
            pid_locks={
                12345: [
                    {"file_path": "/path/to/file1.py"},
                    {"file_path": "/path/to/file2.py"},
                ]
            }
        )

        agents, _, _ = list_command._get_agent_data(mock_registry)

        claude_agent = next(a for a in agents if a["agent_type"] == "claude")
        assert claude_agent["editing_file"] == "file1.py"
        assert "file2.py" not in claude_agent["editing_file"]


def test_non_tty_header_uses_editing_file_label(
    mock_registry: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    """Non-TTY list output should label the column as EDITING_FILE."""
    list_cmd = ListCommand(
        registry_factory=MagicMock(return_value=mock_registry),
        is_process_alive=lambda pid: True,
        is_port_open=lambda host, port, timeout=0.5: True,
        clear_screen=MagicMock(),
        time_module=MagicMock(),
        print_func=print,
    )
    args = MagicMock()

    with (
        patch("synapse.commands.list.FileSafetyManager") as MockFSM,
        patch("sys.stdout.isatty", return_value=False),
    ):
        fsm_instance = MockFSM.from_env.return_value
        fsm_instance.enabled = True
        fsm_instance.list_locks.return_value = []
        fsm_instance.get_stale_locks.return_value = []

        list_cmd.run(args)

    captured = capsys.readouterr()
    assert "EDITING_FILE" in captured.out
