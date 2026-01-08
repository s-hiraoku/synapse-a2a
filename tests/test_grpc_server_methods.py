"""Tests for gRPC server methods and service implementation."""

import asyncio
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# Mock grpc and proto before importing synapse.grpc_server if they don't exist
try:
    import grpc

    import synapse.proto.a2a_pb2 as pb2
    import synapse.proto.a2a_pb2_grpc as pb2_grpc
except ImportError:
    grpc = MagicMock()
    pb2 = MagicMock()
    pb2_grpc = MagicMock()

    # Define a dummy class instead of MagicMock for base class to avoid MRO/iteration issues
    class DummyServicer:
        pass

    pb2_grpc.A2AServiceServicer = DummyServicer

    sys.modules["grpc"] = grpc
    sys.modules["synapse.proto.a2a_pb2"] = pb2
    sys.modules["synapse.proto.a2a_pb2_grpc"] = pb2_grpc

from synapse.grpc_server import GrpcServicer, serve_grpc


class TestGrpcServiceMethods:
    """Tests for the PascalCase gRPC service methods."""

    @pytest.fixture
    def mock_controller(self):
        controller = MagicMock()
        controller.status = "IDLE"
        controller.get_context.return_value = "Output"
        return controller

    @pytest.fixture
    def servicer(self, mock_controller):
        return GrpcServicer(
            controller=mock_controller,
            agent_type="claude",
            port=8100,
            submit_seq="\n",
            agent_id="test-agent",
        )

    def test_GetAgentCard(self, servicer):
        """Test GetAgentCard gRPC method."""
        request = MagicMock()
        context = MagicMock()

        # Ensure HTTPS is disabled for this test
        with patch.dict(os.environ, {}, clear=True):
            # servicer.GetAgentCard calls servicer.get_agent_card()
            # verify the return value structure
            card = servicer.GetAgentCard(request, context)

        assert card["name"] == "Synapse Claude Agent"
        assert card["url"] == "http://localhost:8100"

    def test_SendMessage_text(self, servicer, mock_controller):
        """Test SendMessage with text content."""
        request = MagicMock()
        # Mock request.message.parts[0].text_part.text
        part = MagicMock()
        part.HasField.return_value = True
        part.text_part.text = "Hello"
        request.message.parts = [part]
        request.context_id = "ctx-1"
        request.HasField.return_value = False  # No metadata

        context = MagicMock()

        response = servicer.SendMessage(request, context)

        assert response["task"]["message"]["text"] == "Hello"
        assert response["task"]["context_id"] == "ctx-1"
        mock_controller.write.assert_called()

    def test_SendMessage_with_metadata(self, servicer, mock_controller):
        """Test SendMessage with metadata."""
        request = MagicMock()
        part = MagicMock()
        part.HasField.return_value = True
        part.text_part.text = "Hello"
        request.message.parts = [part]

        request.HasField.return_value = True
        request.metadata.fields = {"key": "value"}.items()

        response = servicer.SendMessage(request, MagicMock())

        assert response["task"]["metadata"]["key"] == "value"

    def test_GetTask(self, servicer):
        """Test GetTask gRPC method."""
        # Create task first
        task = servicer._create_task("test")

        request = MagicMock()
        request.task_id = task["id"]

        response = servicer.GetTask(request, MagicMock())

        assert response["task"]["id"] == task["id"]

    def test_ListTasks(self, servicer):
        """Test ListTasks gRPC method."""
        servicer._create_task("test")

        request = MagicMock()
        request.context_id = ""

        response = servicer.ListTasks(request, MagicMock())

        assert len(response["tasks"]) > 0

    def test_CancelTask(self, servicer):
        """Test CancelTask gRPC method."""
        task = servicer.send_message("test")

        request = MagicMock()
        request.task_id = task["id"]

        response = servicer.CancelTask(request, MagicMock())

        assert response["status"] == "canceled"

    def test_Subscribe(self, servicer):
        """Test Subscribe gRPC method."""
        task = servicer.send_message("test")
        servicer._update_task_status(task["id"], "completed")

        request = MagicMock()
        request.task_id = task["id"]

        events = list(servicer.Subscribe(request, MagicMock()))

        assert len(events) > 0
        assert events[-1]["event_type"] == "done"

    def test_SendPriorityMessage(self, servicer, mock_controller):
        """Test SendPriorityMessage gRPC method."""
        request = MagicMock()
        part = MagicMock()
        part.HasField.return_value = True
        part.text_part.text = "Urgent"
        request.message.parts = [part]
        request.priority = 5
        request.HasField.return_value = False

        response = servicer.SendPriorityMessage(request, MagicMock())

        assert response["task"]["metadata"]["priority"] == 5
        assert response["task"]["message"]["text"] == "Urgent"


class TestGrpcServerAsync:
    """Tests for async server functions."""

    @pytest.mark.asyncio
    async def test_serve_grpc_starts_server(self):
        """Test serve_grpc starts server and waits."""
        mock_server = MagicMock()
        mock_servicer = MagicMock()

        with (
            patch(
                "synapse.grpc_server.create_grpc_server",
                return_value=(mock_server, mock_servicer),
            ),
            patch("synapse.grpc_server.asyncio.Event") as mock_event,
        ):
            # Make event.wait() return immediately or raise CancelledError
            mock_event_inst = mock_event.return_value
            mock_event_inst.wait.side_effect = asyncio.CancelledError

            await serve_grpc(MagicMock(), "claude", 8100)

            mock_server.start.assert_called_once()
            mock_server.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_serve_grpc_returns_if_no_server(self):
        """Test serve_grpc returns if create_grpc_server returns None."""
        with patch("synapse.grpc_server.create_grpc_server", return_value=(None, None)):
            await serve_grpc(MagicMock(), "claude", 8100)
            # Should just return
