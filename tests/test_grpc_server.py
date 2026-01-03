"""Tests for gRPC server module."""

from unittest.mock import MagicMock, patch

import pytest

from synapse.grpc_server import (
    GrpcServicer,
    check_grpc_available,
    create_grpc_server,
)


class TestCheckGrpcAvailable:
    """Tests for gRPC availability check."""

    def test_check_returns_boolean(self):
        result = check_grpc_available()
        assert isinstance(result, bool)


class TestGrpcServicer:
    """Tests for GrpcServicer class."""

    @pytest.fixture
    def mock_controller(self):
        """Create mock controller."""
        controller = MagicMock()
        controller.status = "IDLE"
        controller.get_context.return_value = "Test output"
        return controller

    @pytest.fixture
    def servicer(self, mock_controller):
        """Create servicer instance."""
        return GrpcServicer(
            controller=mock_controller,
            agent_type="claude",
            port=8100,
            submit_seq="\n",
            agent_id="test-agent",
        )

    def test_init(self, servicer):
        """Test servicer initialization."""
        assert servicer.agent_type == "claude"
        assert servicer.port == 8100
        assert servicer.agent_id == "test-agent"

    def test_get_agent_card(self, servicer):
        """Test agent card retrieval."""
        card = servicer.get_agent_card()

        assert "name" in card
        assert "description" in card
        assert "url" in card
        assert "capabilities" in card
        assert card["capabilities"]["streaming"] is True

    def test_create_task(self, servicer):
        """Test task creation."""
        task = servicer._create_task("Hello")

        assert "id" in task
        assert task["status"] == "submitted"
        assert task["message"]["text"] == "Hello"

    def test_send_message(self, servicer, mock_controller):
        """Test sending message."""
        task = servicer.send_message("Hello agent")

        assert task["status"] == "working"
        mock_controller.write.assert_called_once()

    def test_send_message_no_controller(self):
        """Test send message without controller."""
        servicer = GrpcServicer(
            controller=None,
            agent_type="claude",
            port=8100,
        )

        with pytest.raises(RuntimeError):
            servicer.send_message("Hello")

    def test_get_task_exists(self, servicer):
        """Test get existing task."""
        created = servicer._create_task("Test")
        task = servicer.get_task(created["id"])

        assert task is not None
        assert task["id"] == created["id"]

    def test_get_task_not_found(self, servicer):
        """Test get non-existent task."""
        task = servicer.get_task("nonexistent-id")
        assert task is None

    def test_get_task_updates_status(self, servicer, mock_controller):
        """Test that get_task updates status when IDLE."""
        task = servicer.send_message("Test")
        mock_controller.status = "IDLE"

        updated = servicer.get_task(task["id"])

        assert updated["status"] == "completed"

    def test_list_tasks(self, servicer):
        """Test listing tasks."""
        servicer._create_task("Task 1")
        servicer._create_task("Task 2")

        tasks = servicer.list_tasks()
        assert len(tasks) == 2

    def test_list_tasks_by_context(self, servicer):
        """Test listing tasks filtered by context."""
        servicer._create_task("Task 1", context_id="ctx-1")
        servicer._create_task("Task 2", context_id="ctx-2")

        tasks = servicer.list_tasks(context_id="ctx-1")
        assert len(tasks) == 1

    def test_cancel_task(self, servicer, mock_controller):
        """Test canceling task."""
        task = servicer.send_message("Test")
        result = servicer.cancel_task(task["id"])

        assert result["status"] == "canceled"
        mock_controller.interrupt.assert_called_once()

    def test_cancel_task_not_found(self, servicer):
        """Test cancel non-existent task."""
        with pytest.raises(ValueError):
            servicer.cancel_task("nonexistent-id")

    def test_cancel_completed_task(self, servicer, mock_controller):
        """Test cancel already completed task."""
        task = servicer.send_message("Test")
        servicer._update_task_status(task["id"], "completed")

        with pytest.raises(ValueError):
            servicer.cancel_task(task["id"])


class TestCreateGrpcServer:
    """Tests for create_grpc_server function."""

    def test_create_without_grpc(self):
        """Test creation when gRPC not available."""
        with patch("synapse.grpc_server.GRPC_AVAILABLE", False):
            server, servicer = create_grpc_server(
                controller=MagicMock(),
                agent_type="claude",
                port=8100,
            )

            assert server is None
            assert servicer is None

    @pytest.mark.skipif(not check_grpc_available(), reason="gRPC not installed")
    def test_create_with_grpc(self):
        """Test creation when gRPC is available."""
        server, servicer = create_grpc_server(
            controller=MagicMock(),
            agent_type="claude",
            port=8100,
            grpc_port=8101,
        )

        assert server is not None
        assert servicer is not None
        assert servicer.agent_type == "claude"

        # Clean up
        server.stop(0)


class TestSubscribe:
    """Tests for subscribe streaming."""

    @pytest.fixture
    def mock_controller(self):
        """Create mock controller with changing state."""
        controller = MagicMock()
        controller.status = "BUSY"
        controller.get_context.return_value = "Output"
        return controller

    def test_subscribe_task_not_found(self, mock_controller):
        """Test subscribe to non-existent task."""
        servicer = GrpcServicer(
            controller=mock_controller,
            agent_type="claude",
            port=8100,
        )

        with pytest.raises(ValueError):
            list(servicer.subscribe("nonexistent-id"))

    def test_subscribe_yields_events(self, mock_controller):
        """Test subscribe yields output events."""
        servicer = GrpcServicer(
            controller=mock_controller,
            agent_type="claude",
            port=8100,
        )

        task = servicer._create_task("Test")
        servicer._update_task_status(task["id"], "working")

        # Simulate output growing then task completing
        outputs = ["Hello", "Hello World"]
        call_count = [0]

        def side_effect():
            idx = min(call_count[0], len(outputs) - 1)
            call_count[0] += 1
            if call_count[0] > 2:
                servicer._update_task_status(task["id"], "completed")
            return outputs[idx]

        mock_controller.get_context.side_effect = side_effect

        events = list(servicer.subscribe(task["id"]))

        # Should have output and done events
        event_types = [e["event_type"] for e in events]
        assert "output" in event_types
        assert "done" in event_types
