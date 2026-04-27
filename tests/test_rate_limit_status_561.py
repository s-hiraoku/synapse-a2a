"""Tests for surfacing LLM provider rate limits as agent status (#561)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from synapse.a2a_compat import create_a2a_router
from synapse.a2a_models import Message, TextPart
from synapse.status import (
    DONE,
    PROCESSING,
    RATE_LIMITED,
    READY,
    SHUTTING_DOWN,
    WAITING_FOR_INPUT,
    get_status_style,
    is_valid_status,
)


@pytest.fixture
def mock_controller() -> MagicMock:
    controller = MagicMock()
    controller.status = PROCESSING
    controller.get_context.return_value = "Working..."
    controller.last_waiting_source = "none"
    return controller


class TestRateLimitStatus561:
    """Tests for task error detection propagating to registry status."""

    agent_id = "synapse-test-agent-8126"

    def setup_method(self) -> None:
        from synapse.a2a_compat import task_store

        with task_store._lock:
            task_store._tasks.clear()

    def _register_callback(self, mock_controller: MagicMock, mock_registry: MagicMock):
        create_a2a_router(
            mock_controller,
            "codex",
            8126,
            "\n",
            agent_id=self.agent_id,
            registry=mock_registry,
        )
        return mock_controller.on_status_change.call_args.args[0]

    def _create_working_task(self):
        from synapse.a2a_compat import task_store

        task = task_store.create(Message(parts=[TextPart(text="hello")]))
        task_store.update_status(task.id, "working")
        return task

    @pytest.mark.parametrize("current_status", [PROCESSING, READY, WAITING_FOR_INPUT])
    def test_rate_limit_output_sets_registry_status(
        self, mock_controller: MagicMock, current_status: str
    ) -> None:
        mock_controller.status = READY
        mock_controller.get_context.return_value = (
            "Provider error: rate limit exceeded, please retry later"
        )
        mock_registry = MagicMock()
        mock_registry.get_agent.return_value = {"status": current_status}
        status_callback = self._register_callback(mock_controller, mock_registry)
        self._create_working_task()

        status_callback(PROCESSING, READY)

        mock_registry.update_status.assert_any_call(self.agent_id, RATE_LIMITED)

    def test_non_rate_limit_error_does_not_demote(
        self, mock_controller: MagicMock
    ) -> None:
        mock_controller.status = READY
        mock_controller.get_context.return_value = "Operation timed out"
        mock_registry = MagicMock()
        mock_registry.get_agent.return_value = {"status": PROCESSING}
        status_callback = self._register_callback(mock_controller, mock_registry)
        self._create_working_task()

        status_callback(PROCESSING, READY)

        assert (self.agent_id, RATE_LIMITED) not in [
            call.args for call in mock_registry.update_status.call_args_list
        ]

    @pytest.mark.parametrize("current_status", [DONE, SHUTTING_DOWN])
    def test_rate_limited_does_not_overwrite_terminal_agent_status(
        self, mock_controller: MagicMock, current_status: str
    ) -> None:
        mock_controller.status = READY
        mock_controller.get_context.return_value = "too many requests"
        mock_registry = MagicMock()
        mock_registry.get_agent.return_value = {"status": current_status}
        status_callback = self._register_callback(mock_controller, mock_registry)
        self._create_working_task()

        status_callback(PROCESSING, READY)

        assert (self.agent_id, RATE_LIMITED) not in [
            call.args for call in mock_registry.update_status.call_args_list
        ]

    def test_status_constant_is_valid(self) -> None:
        assert is_valid_status(RATE_LIMITED) is True

    def test_rate_limited_style_defined(self) -> None:
        assert get_status_style(RATE_LIMITED) == "bold magenta"

    def test_clean_output_does_not_demote(self, mock_controller: MagicMock) -> None:
        mock_controller.status = READY
        mock_controller.get_context.return_value = "Task completed successfully"
        mock_registry = MagicMock()
        mock_registry.get_agent.return_value = {"status": WAITING_FOR_INPUT}
        status_callback = self._register_callback(mock_controller, mock_registry)
        self._create_working_task()

        status_callback(PROCESSING, READY)

        assert (self.agent_id, RATE_LIMITED) not in [
            call.args for call in mock_registry.update_status.call_args_list
        ]
