"""Tests for Readiness Gate — blocks task send until agent initialization is complete."""

import threading
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from synapse.a2a_compat import create_a2a_router

# Standard payload for sending a task message
SEND_PAYLOAD = {
    "message": {"role": "user", "parts": [{"type": "text", "text": "Hello"}]}
}


# ============================================================
# Fixtures
# ============================================================


def _make_controller(*, agent_ready: bool = True) -> MagicMock:
    """Create a mock controller with readiness gate attributes."""
    ctrl = MagicMock()
    ctrl.status = "READY"
    ctrl.get_context.return_value = "output"
    ctrl._agent_ready = agent_ready
    ctrl._agent_ready_event = threading.Event()
    if agent_ready:
        ctrl._agent_ready_event.set()
    return ctrl


def _make_client(controller: MagicMock) -> TestClient:
    """Create a FastAPI test client wired to the given controller."""
    app = FastAPI()
    router = create_a2a_router(controller, "test", 8000, "\n")
    app.include_router(router)
    return TestClient(app)


# ============================================================
# Test: agent_ready=True → normal message delivery
# ============================================================


class TestReadyAgentAcceptsMessages:
    """When agent is ready, messages should be delivered normally."""

    def test_send_succeeds_when_ready(self):
        ctrl = _make_controller(agent_ready=True)
        client = _make_client(ctrl)

        resp = client.post("/tasks/send", json=SEND_PAYLOAD)

        assert resp.status_code == 200
        data = resp.json()
        assert "task" in data
        assert data["task"]["status"] == "working"
        ctrl.write.assert_called_once()

    def test_send_priority_succeeds_when_ready(self):
        ctrl = _make_controller(agent_ready=True)
        client = _make_client(ctrl)

        resp = client.post("/tasks/send-priority?priority=3", json=SEND_PAYLOAD)

        assert resp.status_code == 200
        ctrl.write.assert_called_once()


# ============================================================
# Test: agent_ready=False → HTTP 503 with Retry-After
# ============================================================


class TestNotReadyAgentRejects:
    """When agent is NOT ready and gate times out, return 503."""

    @patch("synapse.a2a_compat.AGENT_READY_TIMEOUT", 0.1)
    def test_send_returns_503_when_not_ready(self):
        ctrl = _make_controller(agent_ready=False)
        client = _make_client(ctrl)

        resp = client.post("/tasks/send", json=SEND_PAYLOAD)

        assert resp.status_code == 503
        assert "not ready" in resp.json()["detail"].lower()
        assert resp.headers.get("Retry-After") == "5"
        ctrl.write.assert_not_called()

    @patch("synapse.a2a_compat.AGENT_READY_TIMEOUT", 0.1)
    def test_send_priority_returns_503_when_not_ready(self):
        ctrl = _make_controller(agent_ready=False)
        client = _make_client(ctrl)

        resp = client.post("/tasks/send-priority?priority=3", json=SEND_PAYLOAD)

        assert resp.status_code == 503
        ctrl.write.assert_not_called()


# ============================================================
# Test: Priority 5 bypasses the readiness gate
# ============================================================


class TestPriority5BypassesGate:
    """Priority 5 (emergency interrupt) must bypass the readiness gate."""

    def test_priority5_delivers_even_when_not_ready(self):
        ctrl = _make_controller(agent_ready=False)
        client = _make_client(ctrl)

        resp = client.post("/tasks/send-priority?priority=5", json=SEND_PAYLOAD)

        assert resp.status_code == 200
        ctrl.interrupt.assert_called_once()
        ctrl.write.assert_called_once()


# ============================================================
# Test: Event blocks then unblocks (concurrent gate open)
# ============================================================


class TestEventBlockThenUnblock:
    """_agent_ready_event.wait() should block, then proceed when set."""

    def test_gate_opens_mid_wait(self):
        ctrl = _make_controller(agent_ready=False)
        client = _make_client(ctrl)

        # Simulate agent becoming ready after 0.2s
        def _set_ready():
            ctrl._agent_ready = True
            ctrl._agent_ready_event.set()

        timer = threading.Timer(0.2, _set_ready)
        timer.start()

        try:
            resp = client.post("/tasks/send", json=SEND_PAYLOAD)
            assert resp.status_code == 200
            ctrl.write.assert_called_once()
        finally:
            timer.cancel()


# ============================================================
# Test: Reply messages bypass readiness gate
# ============================================================


class TestReplyBypassesGate:
    """Reply messages (in_reply_to) should bypass the readiness gate.

    Replies write to PTY directly and don't need initialization to be
    complete — they're responses to tasks the agent already created.
    """

    @patch("synapse.a2a_compat.AGENT_READY_TIMEOUT", 0.1)
    def test_reply_succeeds_when_not_ready(self):
        ctrl = _make_controller(agent_ready=False)
        app = FastAPI()
        router = create_a2a_router(ctrl, "test", 8000, "\n")
        app.include_router(router)
        client = TestClient(app)

        # First, create a task while agent is ready (setup)
        ctrl._agent_ready = True
        ctrl._agent_ready_event.set()
        resp1 = client.post("/tasks/send", json=SEND_PAYLOAD)
        assert resp1.status_code == 200
        task_id = resp1.json()["task"]["id"]

        # Now make agent not-ready and send a reply
        ctrl._agent_ready = False
        ctrl._agent_ready_event.clear()

        reply_payload = {
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": "Reply content"}],
            },
            "metadata": {"in_reply_to": task_id},
        }

        resp2 = client.post("/tasks/send", json=reply_payload)
        # Reply should succeed — it bypasses the gate
        assert resp2.status_code == 200
