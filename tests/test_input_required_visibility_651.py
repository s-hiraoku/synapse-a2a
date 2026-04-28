"""Tests for #651 input_required task visibility in synapse list / status."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from synapse.a2a_models import Message, TextPart
from synapse.registry import AgentRegistry


def _msg(text: str = "hi") -> Message:
    return Message(role="user", parts=[TextPart(type="text", text=text)])


@pytest.fixture
def tmp_registry() -> AgentRegistry:
    """Provide an AgentRegistry with an isolated temp directory."""
    tmp = tempfile.mkdtemp(prefix="synapse-test-651-")
    registry = AgentRegistry()
    registry.registry_dir = Path(tmp)
    registry.registry_dir.mkdir(parents=True, exist_ok=True)
    registry.register("synapse-codex-8121", "codex", 8121)
    try:
        yield registry
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


class TestRegistryInputRequiredTasks:
    def test_update_input_required_tasks_writes_field(
        self, tmp_registry: AgentRegistry
    ) -> None:
        tasks = [
            {
                "task_id": "abc12345",
                "approve_url": "http://localhost:8121/tasks/abc12345/permission/approve",
            }
        ]
        assert (
            tmp_registry.update_input_required_tasks("synapse-codex-8121", tasks)
            is True
        )
        info = tmp_registry.get_agent("synapse-codex-8121")
        assert info is not None
        assert info.get("input_required_tasks") == tasks

    def test_update_input_required_tasks_clears_with_empty_list(
        self, tmp_registry: AgentRegistry
    ) -> None:
        tmp_registry.update_input_required_tasks(
            "synapse-codex-8121",
            [{"task_id": "x", "approve_url": "http://x"}],
        )
        tmp_registry.update_input_required_tasks("synapse-codex-8121", [])
        info = tmp_registry.get_agent("synapse-codex-8121")
        assert info is not None
        assert info.get("input_required_tasks") == []

    def test_update_input_required_tasks_unknown_agent_returns_false(
        self, tmp_registry: AgentRegistry
    ) -> None:
        assert (
            tmp_registry.update_input_required_tasks("nonexistent", [{"task_id": "x"}])
            is False
        )

    def test_list_agents_includes_input_required_tasks(
        self, tmp_registry: AgentRegistry
    ) -> None:
        tmp_registry.update_input_required_tasks(
            "synapse-codex-8121",
            [{"task_id": "abc", "approve_url": "http://x"}],
        )
        agents = tmp_registry.list_agents()
        info = agents["synapse-codex-8121"]
        assert info.get("input_required_tasks") == [
            {"task_id": "abc", "approve_url": "http://x"}
        ]


class TestListCommandSurfacesInputRequired:
    def test_get_agent_data_includes_input_required_tasks_field(
        self, tmp_registry: AgentRegistry
    ) -> None:
        tmp_registry.update_input_required_tasks(
            "synapse-codex-8121",
            [
                {
                    "task_id": "abc12345",
                    "approve_url": "http://localhost:8121/.../approve",
                }
            ],
        )
        from synapse.commands.list import ListCommand

        list_cmd = ListCommand(
            registry_factory=lambda: tmp_registry,
            is_process_alive=lambda pid: True,
            is_port_open=lambda *args, **kwargs: True,
            clear_screen=lambda: None,
            time_module=MagicMock(),
            print_func=lambda s: None,
        )
        agents_list, _, _ = list_cmd._get_agent_data(tmp_registry)
        assert len(agents_list) == 1
        agent = agents_list[0]
        assert agent.get("input_required_tasks") == [
            {"task_id": "abc12345", "approve_url": "http://localhost:8121/.../approve"}
        ]

    def test_get_agent_data_empty_input_required_tasks_when_unset(
        self, tmp_registry: AgentRegistry
    ) -> None:
        from synapse.commands.list import ListCommand

        list_cmd = ListCommand(
            registry_factory=lambda: tmp_registry,
            is_process_alive=lambda pid: True,
            is_port_open=lambda *args, **kwargs: True,
            clear_screen=lambda: None,
            time_module=MagicMock(),
            print_func=lambda s: None,
        )
        agents_list, _, _ = list_cmd._get_agent_data(tmp_registry)
        assert len(agents_list) == 1
        assert agents_list[0].get("input_required_tasks", []) == []

    def test_run_json_exposes_input_required_tasks(
        self, tmp_registry: AgentRegistry
    ) -> None:
        """synapse list --json must include input_required_tasks for programmatic consumers."""
        import argparse
        import json

        from synapse.commands.list import ListCommand

        tmp_registry.update_input_required_tasks(
            "synapse-codex-8121",
            [
                {
                    "task_id": "abc12345",
                    "approve_url": "http://localhost:8121/.../approve",
                }
            ],
        )

        captured: list[str] = []
        list_cmd = ListCommand(
            registry_factory=lambda: tmp_registry,
            is_process_alive=lambda pid: True,
            is_port_open=lambda *args, **kwargs: True,
            clear_screen=lambda: None,
            time_module=MagicMock(),
            print_func=captured.append,
        )

        list_cmd.run_json(argparse.Namespace())

        assert len(captured) == 1
        payload = json.loads(captured[0])
        assert len(payload) == 1
        assert payload[0].get("input_required_tasks") == [
            {"task_id": "abc12345", "approve_url": "http://localhost:8121/.../approve"}
        ]

    def test_run_json_empty_input_required_tasks_when_unset(
        self, tmp_registry: AgentRegistry
    ) -> None:
        """synapse list --json should emit empty list when no input_required tasks."""
        import argparse
        import json

        from synapse.commands.list import ListCommand

        captured: list[str] = []
        list_cmd = ListCommand(
            registry_factory=lambda: tmp_registry,
            is_process_alive=lambda pid: True,
            is_port_open=lambda *args, **kwargs: True,
            clear_screen=lambda: None,
            time_module=MagicMock(),
            print_func=captured.append,
        )

        list_cmd.run_json(argparse.Namespace())

        payload = json.loads(captured[0])
        assert payload[0].get("input_required_tasks", []) == []

    def test_status_json_exposes_input_required_tasks(
        self, tmp_registry: AgentRegistry
    ) -> None:
        """synapse status <agent> --json must include input_required_tasks (docs/code parity)."""
        import json
        from io import StringIO

        from synapse.commands.status import StatusCommand

        tmp_registry.update_input_required_tasks(
            "synapse-codex-8121",
            [
                {
                    "task_id": "abc12345",
                    "approve_url": "http://localhost:8121/.../approve",
                }
            ],
        )

        out = StringIO()
        status_cmd = StatusCommand(registry=tmp_registry, output=out)
        status_cmd.run("synapse-codex-8121", json_output=True)

        payload = json.loads(out.getvalue())
        assert payload.get("input_required_tasks") == [
            {"task_id": "abc12345", "approve_url": "http://localhost:8121/.../approve"}
        ]

    def test_status_json_empty_input_required_tasks_when_unset(
        self, tmp_registry: AgentRegistry
    ) -> None:
        """synapse status --json should emit empty list when agent has no input_required tasks."""
        import json
        from io import StringIO

        from synapse.commands.status import StatusCommand

        out = StringIO()
        status_cmd = StatusCommand(registry=tmp_registry, output=out)
        status_cmd.run("synapse-codex-8121", json_output=True)

        payload = json.loads(out.getvalue())
        assert payload.get("input_required_tasks", []) == []


class TestSyncInputRequiredTasksHelper:
    """Test the helper that pushes input_required state from task_store to registry."""

    def test_sync_pushes_task_id_and_approve_url(
        self, tmp_registry: AgentRegistry
    ) -> None:
        from synapse.a2a_compat import _sync_registry_input_required_tasks
        from synapse.task_store import TaskStore

        store = TaskStore()
        task_a = store.create(_msg(), None)
        store.update_status(task_a.id, "input_required")
        task_b = store.create(_msg(), None)
        store.update_status(task_b.id, "completed")

        _sync_registry_input_required_tasks(
            registry=tmp_registry,
            agent_id="synapse-codex-8121",
            task_store=store,
            port=8121,
        )
        info = tmp_registry.get_agent("synapse-codex-8121")
        assert info is not None
        tasks = info.get("input_required_tasks") or []
        assert len(tasks) == 1
        assert tasks[0]["task_id"] == task_a.id
        assert "approve" in tasks[0]["approve_url"]
        assert str(task_a.id) in tasks[0]["approve_url"]

    def test_sync_clears_when_no_input_required_tasks(
        self, tmp_registry: AgentRegistry
    ) -> None:
        from synapse.a2a_compat import _sync_registry_input_required_tasks
        from synapse.task_store import TaskStore

        tmp_registry.update_input_required_tasks(
            "synapse-codex-8121",
            [{"task_id": "stale", "approve_url": "http://stale"}],
        )
        store = TaskStore()
        store.create(_msg(), None)

        _sync_registry_input_required_tasks(
            registry=tmp_registry,
            agent_id="synapse-codex-8121",
            task_store=store,
            port=8121,
        )
        info = tmp_registry.get_agent("synapse-codex-8121")
        assert info is not None
        assert info.get("input_required_tasks") == []

    def test_sync_skips_when_registry_or_agent_id_missing(
        self, tmp_registry: AgentRegistry
    ) -> None:
        from synapse.a2a_compat import _sync_registry_input_required_tasks
        from synapse.task_store import TaskStore

        store = TaskStore()
        task = store.create(_msg(), None)
        store.update_status(task.id, "input_required")

        _sync_registry_input_required_tasks(
            registry=None, agent_id="x", task_store=store, port=8121
        )
        _sync_registry_input_required_tasks(
            registry=tmp_registry, agent_id=None, task_store=store, port=8121
        )
        info = tmp_registry.get_agent("synapse-codex-8121")
        assert info is not None
        assert info.get("input_required_tasks") in (None, [])
