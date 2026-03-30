"""Tests for JSON output in synapse list command."""

import json
from unittest.mock import MagicMock, patch

from synapse.cli import cmd_list
from synapse.commands.list import ListCommand
from synapse.registry import AgentRegistry


def create_list_command() -> ListCommand:
    """Create a ListCommand with mock dependencies."""
    return ListCommand(
        registry_factory=lambda: MagicMock(spec=AgentRegistry),
        is_process_alive=lambda pid: True,
        is_port_open=lambda host, port, timeout=0.5: True,
        clear_screen=lambda: None,
        time_module=MagicMock(),
        print_func=MagicMock(),
    )


def make_agent(
    *,
    agent_id: str,
    agent_type: str,
    name: str | None = None,
    role: str | None = None,
    skill_set: str | None = None,
    port: int,
    status: str,
    pid: int,
    working_dir: str,
    endpoint: str,
    transport: str,
    current_task_preview: str | None = None,
    task_received_at: float | None = None,
    editing_file: str | None = None,
) -> dict[str, object]:
    """Build agent data in the shape returned by _get_agent_data()."""
    agent = {
        "agent_id": agent_id,
        "agent_type": agent_type,
        "name": name,
        "role": role,
        "skill_set": skill_set,
        "port": port,
        "status": status,
        "pid": pid,
        "working_dir": working_dir,
        "working_dir_full": f"/tmp/{working_dir}",
        "endpoint": endpoint,
        "tty_device": None,
        "zellij_pane_id": None,
        "current_task_preview": current_task_preview,
        "task_received_at": task_received_at,
        "summary": None,
        "transport": transport,
    }
    if editing_file is not None:
        agent["editing_file"] = editing_file
    return agent


class TestListJson:
    """Tests for ListCommand.run_json."""

    def test_list_json_no_agents(self) -> None:
        """Should output [] when no agents are registered."""
        list_cmd = create_list_command()
        args = MagicMock()

        with patch.object(
            list_cmd,
            "_get_agent_data",
            return_value=([], [], False),
        ) as mock_get_agent_data:
            list_cmd.run_json(args)

        mock_get_agent_data.assert_called_once()
        list_cmd._print.assert_called_once_with("[]")

    def test_list_json_single_agent(self) -> None:
        """Should output one agent as a JSON array."""
        list_cmd = create_list_command()
        args = MagicMock()
        agent = make_agent(
            agent_id="synapse-claude-8100",
            agent_type="claude",
            name="Claud",
            role="reviewer",
            skill_set="code-review",
            port=8100,
            status="READY",
            pid=12345,
            working_dir="repo-a",
            endpoint="http://localhost:8100",
            transport="UDS→",
            current_task_preview="Review issue #380",
            task_received_at=1710000000.0,
        )

        with patch.object(
            list_cmd,
            "_get_agent_data",
            return_value=([agent], [], False),
        ):
            list_cmd.run_json(args)

        output = list_cmd._print.call_args.args[0]
        payload = json.loads(output)

        assert payload == [
            {
                "agent_id": "synapse-claude-8100",
                "agent_type": "claude",
                "name": "Claud",
                "role": "reviewer",
                "skill_set": "code-review",
                "port": 8100,
                "status": "READY",
                "pid": 12345,
                "working_dir": "/tmp/repo-a",
                "endpoint": "http://localhost:8100",
                "transport": "UDS→",
                "current_task_preview": "Review issue #380",
                "task_received_at": 1710000000.0,
                "summary": None,
            }
        ]

    def test_list_json_multiple_agents(self) -> None:
        """Should output multiple agents as a JSON array."""
        list_cmd = create_list_command()
        args = MagicMock()
        agents = [
            make_agent(
                agent_id="synapse-claude-8100",
                agent_type="claude",
                port=8100,
                status="READY",
                pid=12345,
                working_dir="repo-a",
                endpoint="http://localhost:8100",
                transport="UDS→",
            ),
            make_agent(
                agent_id="synapse-gemini-8110",
                agent_type="gemini",
                name="Gem",
                role="tester",
                skill_set="test-first",
                port=8110,
                status="PROCESSING",
                pid=22345,
                working_dir="repo-b",
                endpoint="http://localhost:8110",
                transport="TCP→",
                current_task_preview="Write list JSON tests",
                task_received_at=1710000100.0,
            ),
        ]

        with patch.object(
            list_cmd,
            "_get_agent_data",
            return_value=(agents, [], False),
        ):
            list_cmd.run_json(args)

        output = list_cmd._print.call_args.args[0]
        payload = json.loads(output)

        assert len(payload) == 2
        assert [item["agent_id"] for item in payload] == [
            "synapse-claude-8100",
            "synapse-gemini-8110",
        ]
        assert payload[0]["transport"] == "UDS→"
        assert payload[1]["current_task_preview"] == "Write list JSON tests"
        assert "editing_file" not in payload[0]

    def test_list_json_with_file_safety(self) -> None:
        """Should include editing_file when file safety is enabled."""
        list_cmd = create_list_command()
        args = MagicMock()
        agent = make_agent(
            agent_id="synapse-codex-8120",
            agent_type="codex",
            port=8120,
            status="READY",
            pid=32345,
            working_dir="repo-c",
            endpoint="http://localhost:8120",
            transport="-",
            editing_file="tests/test_cmd_list_json.py",
        )

        with patch.object(
            list_cmd,
            "_get_agent_data",
            return_value=([agent], [], True),
        ):
            list_cmd.run_json(args)

        output = list_cmd._print.call_args.args[0]
        payload = json.loads(output)

        assert payload == [
            {
                "agent_id": "synapse-codex-8120",
                "agent_type": "codex",
                "name": None,
                "role": None,
                "skill_set": None,
                "port": 8120,
                "status": "READY",
                "pid": 32345,
                "working_dir": "/tmp/repo-c",
                "endpoint": "http://localhost:8120",
                "transport": "-",
                "current_task_preview": None,
                "task_received_at": None,
                "summary": None,
                "editing_file": "tests/test_cmd_list_json.py",
            }
        ]


def test_list_json_bypasses_tui() -> None:
    """--json should use JSON mode instead of launching the TUI."""
    args = MagicMock()
    args.json_output = True

    with patch("synapse.cli.ListCommand") as MockListCommand:
        list_command = MockListCommand.return_value

        cmd_list(args)

    list_command.run_json.assert_called_once_with(args)
    list_command.run.assert_not_called()
