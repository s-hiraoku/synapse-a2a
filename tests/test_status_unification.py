"""Tests for status unification (READY/PROCESSING system)."""

import argparse
import json
import shutil
import tempfile
import time
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from synapse.commands.list import ListCommand
from synapse.commands.status import StatusCommand
from synapse.registry import AgentRegistry


@pytest.fixture
def temp_registry():
    """Create a test registry with temp directory."""
    reg = AgentRegistry()
    reg.registry_dir = Path(tempfile.mkdtemp(prefix="a2a_test_status_unification_"))
    yield reg
    shutil.rmtree(reg.registry_dir, ignore_errors=True)


class TestStatusUnification:
    """Tests for unified READY/PROCESSING status system."""

    def test_initial_status_is_processing(self, temp_registry):
        """Agent should start with PROCESSING status (startup in progress)."""
        temp_registry.register("synapse-claude-8100", "claude", 8100)

        # CodeRabbit fix: Use registry method instead of direct file read to get consistent status
        agent_data = temp_registry.get_agent("synapse-claude-8100")

        # Initial status should be what's set in register()
        # which should be PROCESSING for startup
        assert agent_data.get("status") == "PROCESSING"

    def test_ready_status_when_idle(self, temp_registry):
        """Agent should have READY status when in IDLE state (waiting for input)."""
        temp_registry.register("synapse-claude-8100", "claude", 8100)

        # Simulate IDLE state transition
        temp_registry.update_status("synapse-claude-8100", "READY")

        # CodeRabbit fix: Use registry method instead of direct file read
        agent_data = temp_registry.get_agent("synapse-claude-8100")

        assert agent_data.get("status") == "READY"

    def test_processing_status_when_busy(self, temp_registry):
        """Agent should have PROCESSING status when handling requests."""
        temp_registry.register("synapse-claude-8100", "claude", 8100)

        # Simulate BUSY state
        temp_registry.update_status("synapse-claude-8100", "PROCESSING")

        # CodeRabbit fix: Use registry method instead of direct file read
        agent_data = temp_registry.get_agent("synapse-claude-8100")

        assert agent_data.get("status") == "PROCESSING"

    def test_status_transition_processing_to_ready(self, temp_registry):
        """Status should transition from PROCESSING to READY when idle."""
        agent_id = "synapse-claude-8100"
        temp_registry.register(agent_id, "claude", 8100)

        # CodeRabbit fix: Verify initial PROCESSING status
        initial_data = temp_registry.get_agent(agent_id)
        assert initial_data.get("status") == "PROCESSING"

        # Transition to READY (when agent becomes idle)
        temp_registry.update_status(agent_id, "READY")

        # CodeRabbit fix: Use registry method instead of direct file read
        updated_data = temp_registry.get_agent(agent_id)

        assert updated_data.get("status") == "READY"

    def test_status_transition_ready_to_processing(self, temp_registry):
        """Status should transition from READY to PROCESSING when handling work."""
        agent_id = "synapse-claude-8100"
        temp_registry.register(agent_id, "claude", 8100)
        temp_registry.update_status(agent_id, "READY")

        # Transition to PROCESSING (when handling a request)
        temp_registry.update_status(agent_id, "PROCESSING")

        # CodeRabbit fix: Use registry method instead of direct file read
        agent_data = temp_registry.get_agent(agent_id)

        assert agent_data.get("status") == "PROCESSING"

    def test_no_old_status_values(self, temp_registry):
        """Registry should only use READY/PROCESSING, not BUSY/IDLE."""
        agent_id = "synapse-claude-8100"
        temp_registry.register(agent_id, "claude", 8100)

        # CodeRabbit fix: Use registry method instead of direct file read
        agent_data = temp_registry.get_agent(agent_id)

        status = agent_data.get("status")
        # Should not contain old status values
        assert status not in ["BUSY", "IDLE", "STARTING"]
        # Should be one of the new values
        assert status in ["READY", "PROCESSING"]

    def test_multiple_agents_different_statuses(self, temp_registry):
        """Multiple agents can have different statuses simultaneously."""
        # Agent 1: READY
        temp_registry.register("synapse-claude-8100", "claude", 8100)
        temp_registry.update_status("synapse-claude-8100", "READY")

        # Agent 2: PROCESSING
        temp_registry.register("synapse-claude-8101", "claude", 8101)
        temp_registry.update_status("synapse-claude-8101", "PROCESSING")

        agents = temp_registry.list_agents()

        assert agents["synapse-claude-8100"]["status"] == "READY"
        assert agents["synapse-claude-8101"]["status"] == "PROCESSING"


class TestStatusListJsonViewUnification:
    """Regression tests for status/list JSON view divergence (#696)."""

    def _list_command(
        self, registry: AgentRegistry, time_module: object | None = None
    ) -> ListCommand:
        return ListCommand(
            registry_factory=lambda: registry,
            is_process_alive=lambda pid: True,
            is_port_open=lambda *args, **kwargs: True,
            clear_screen=lambda: None,
            time_module=time_module
            or MagicMock(time=time.time, sleep=lambda _seconds: None),
            print_func=MagicMock(),
        )

    def test_status_and_list_json_share_current_task_and_uptime_fields(
        self, temp_registry: AgentRegistry
    ) -> None:
        """The same agent should expose identical canonical JSON fields."""
        agent_id = "synapse-codex-8122"
        now = 1777619000.0
        temp_registry.register(
            agent_id,
            "codex",
            8122,
            status="PROCESSING",
            name="fix-696",
            role="fix status/list divergence",
            spawned_by="synapse-claude-8104",
        )

        info = temp_registry.get_agent(agent_id)
        assert info is not None
        info.update(
            {
                "registered_at": now - 45.0,
                "current_task_preview": "Investigate status/list JSON",
                "task_received_at": now - 12.0,
            }
        )
        (temp_registry.registry_dir / f"{agent_id}.json").write_text(json.dumps(info))

        status_out = StringIO()
        with patch("synapse.commands.status.time.time", return_value=now):
            StatusCommand(registry=temp_registry, output=status_out).run(
                agent_id, json_output=True
            )
        status_payload = json.loads(status_out.getvalue())

        list_cmd = self._list_command(
            temp_registry,
            time_module=MagicMock(time=lambda: now, sleep=lambda _seconds: None),
        )
        list_cmd.run_json(argparse.Namespace())
        list_payload = json.loads(list_cmd._print.call_args.args[0])[0]

        fields = (
            "agent_id",
            "status",
            "current_task_preview",
            "task_received_at",
            "uptime_seconds",
            "input_required_tasks",
        )
        assert {field: status_payload.get(field) for field in fields} == {
            field: list_payload.get(field) for field in fields
        }
        assert status_payload["current_task_preview"] == "Investigate status/list JSON"
        assert status_payload["uptime_seconds"] == pytest.approx(45.0)

    def test_status_json_resolves_from_same_live_agent_snapshot_as_list(
        self, temp_registry: AgentRegistry
    ) -> None:
        """Status JSON should not resolve through a different registry view."""
        agent_id = "synapse-codex-8122"
        old_now = time.time() - 3600
        new_now = time.time()
        temp_registry.register(agent_id, "codex", 8122, status="PROCESSING")

        old_info = temp_registry.get_agent(agent_id)
        assert old_info is not None
        old_info.update(
            {
                "registered_at": old_now,
                "current_task_preview": None,
                "task_received_at": None,
            }
        )
        fresh_info = dict(old_info)
        fresh_info.update(
            {
                "registered_at": new_now,
                "current_task_preview": "Fresh task preview",
                "task_received_at": new_now,
            }
        )

        class DivergentRegistry:
            def list_agents(self) -> dict[str, dict]:
                return {agent_id: fresh_info}

            def resolve_agent(self, target: str) -> dict | None:
                assert target == agent_id
                return old_info

            def get_orphans(self, agents: dict[str, dict] | None = None) -> dict:
                return {}

            def get_transport_display(self, agent_id: str) -> str | None:
                return None

        registry = DivergentRegistry()
        list_cmd = self._list_command(registry)  # type: ignore[arg-type]
        list_cmd.run_json(argparse.Namespace())
        list_payload = json.loads(list_cmd._print.call_args.args[0])[0]

        status_out = StringIO()
        StatusCommand(registry=registry, output=status_out).run(  # type: ignore[arg-type]
            agent_id,
            json_output=True,
        )
        status_payload = json.loads(status_out.getvalue())

        assert (
            status_payload["current_task_preview"]
            == list_payload["current_task_preview"]
        )
