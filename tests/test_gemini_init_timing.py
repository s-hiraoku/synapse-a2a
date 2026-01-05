"""Test Gemini initial instruction timing fix.

This test suite verifies the fix for the Gemini initial instruction delivery bug
where instructions were not being sent due to a race condition between timeout-based
idle detection and master_fd initialization.

Root cause: _last_output_time was initialized at Time 0 (before any actual output),
causing timeout detection to trigger at Time 1.5s, but master_fd wasn't available
until Time 8s (when Gemini produced first output).

Fix: Initialize _last_output_time to None until first actual output occurs.
"""

import shutil
import time
from pathlib import Path
from unittest.mock import Mock

import pytest

from synapse.controller import TerminalController
from synapse.registry import AgentRegistry


@pytest.fixture
def temp_registry_dir():
    """Create a temporary registry directory."""
    temp_dir = Path("/tmp/a2a_test_gemini_init")
    temp_dir.mkdir(parents=True, exist_ok=True)
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def temp_registry(temp_registry_dir):
    """Create a test registry with temp directory."""
    reg = AgentRegistry()
    reg.registry_dir = temp_registry_dir
    return reg


class TestGeminiInitInstructionTiming:
    """Tests for Gemini initial instruction delivery timing fix."""

    def test_last_output_time_none_until_first_output(self, temp_registry):
        """_last_output_time should be None in interactive mode until first output."""
        agent_id = "test-gemini-init-timing-1"

        controller = TerminalController(
            command="gemini",
            idle_detection={"strategy": "timeout", "timeout": 1.5},
            registry=temp_registry,
            agent_id=agent_id,
            agent_type="gemini",
            port=8110,
        )

        # Simulate run_interactive initialization (the fix)
        controller.interactive = True
        controller.running = True
        with controller.lock:
            controller._last_output_time = None  # Fixed behavior

        # Before any output, _last_output_time should be None
        assert controller._last_output_time is None

        # Simulate periodic idle check before any output
        controller._check_idle_state(b"")

        # Should NOT transition to READY (no output yet, so timeout detection doesn't trigger)
        assert controller.status == "PROCESSING"

    def test_timeout_detection_after_first_output(self, temp_registry):
        """Timeout detection should work correctly after first output."""
        agent_id = "test-gemini-init-timing-2"

        controller = TerminalController(
            command="gemini",
            idle_detection={"strategy": "timeout", "timeout": 0.2},
            registry=temp_registry,
            agent_id=agent_id,
            agent_type="gemini",
            port=8111,
        )

        temp_registry.register(agent_id, "gemini", 8111, status="PROCESSING")

        # Initialize as if in interactive mode
        controller.interactive = True
        controller.running = True
        with controller.lock:
            controller._last_output_time = None

        # Verify no idle detection yet
        assert controller._last_output_time is None
        controller._check_idle_state(b"")
        assert controller.status == "PROCESSING"

        # Simulate first output (as if from read_callback)
        with controller.lock:
            controller._last_output_time = time.time()

        # Immediately after output, should still be PROCESSING
        controller._check_idle_state(b"some output")
        assert controller.status == "PROCESSING"

        # After 0.2s of no output, should transition to READY
        time.sleep(0.25)
        controller._check_idle_state(b"")

        # Should now be READY (and identity sent flag should be set)
        assert controller.status == "READY"

    def test_slow_startup_doesnt_trigger_premature_ready(self, temp_registry):
        """Slow startup agent (like Gemini) shouldn't transition to READY before first output."""
        agent_id = "test-gemini-init-timing-slow"

        controller = TerminalController(
            command="gemini",
            idle_detection={"strategy": "timeout", "timeout": 1.0},
            registry=temp_registry,
            agent_id=agent_id,
            agent_type="gemini",
            port=8112,
        )

        temp_registry.register(agent_id, "gemini", 8112, status="PROCESSING")

        # Initialize as if in interactive mode
        controller.interactive = True
        controller.running = True
        with controller.lock:
            controller._last_output_time = None

        # Simulate periodic idle checker running every 100ms for 1.5 seconds
        # (simulating first 1.5s of Gemini startup)
        for _ in range(15):
            controller._check_idle_state(b"")
            time.sleep(0.1)

        # Should still be PROCESSING because no actual output has occurred
        assert controller.status == "PROCESSING"
        assert controller._last_output_time is None

        # Now simulate first output at time ~1.5s
        with controller.lock:
            controller._last_output_time = time.time()

        # Immediately after first output, still PROCESSING
        controller._check_idle_state(b"first output from gemini")
        assert controller.status == "PROCESSING"

        # After 1.0s of idle (timeout threshold), should transition to READY
        time.sleep(1.1)
        controller._check_idle_state(b"")
        assert controller.status == "READY"

    def test_identity_instruction_sent_on_ready(self, temp_registry):
        """Initial identity instruction should be sent when READY is reached."""
        agent_id = "test-gemini-init-timing-identity"

        controller = TerminalController(
            command="gemini",
            idle_detection={"strategy": "timeout", "timeout": 0.1},
            registry=temp_registry,
            agent_id=agent_id,
            agent_type="gemini",
            port=8113,
        )

        temp_registry.register(agent_id, "gemini", 8113, status="PROCESSING")

        # Initialize as if in interactive mode
        controller.interactive = True
        controller.running = True
        with controller.lock:
            controller._last_output_time = None

        # Mock the master_fd and write method
        controller.master_fd = 5
        controller.write = Mock()

        # Simulate first output
        with controller.lock:
            controller._last_output_time = time.time()

        # Wait for timeout
        time.sleep(0.15)

        # Trigger idle check (simulating periodic checker)
        controller._check_idle_state(b"")

        # Should be READY
        assert controller.status == "READY"
        assert controller._identity_sending is True

        # wait for the identity instruction thread to complete
        time.sleep(2.2)  # POST_WRITE_IDLE_DELAY + send time

        # write should have been called with the initial instructions
        assert controller.write.called
        assert controller._identity_sent is True

    def test_multiple_agents_independent_timing(self, temp_registry):
        """Multiple agents should have independent idle detection timing."""
        # Create multiple controllers with different timeouts
        agents = [
            ("claude-test", "claude", 0.5, 8100),
            ("gemini-test", "gemini", 1.5, 8110),
            ("codex-test", "codex", 1.5, 8120),
        ]

        controllers = []
        for agent_id, agent_type, timeout, port in agents:
            controller = TerminalController(
                command=agent_type,
                idle_detection={"strategy": "timeout", "timeout": timeout},
                registry=temp_registry,
                agent_id=agent_id,
                agent_type=agent_type,
                port=port,
            )
            temp_registry.register(agent_id, agent_type, port, status="PROCESSING")

            # Initialize as if in interactive mode
            controller.interactive = True
            controller.running = True
            with controller.lock:
                controller._last_output_time = None

            controllers.append((controller, timeout))

        # All should start with PROCESSING and _last_output_time=None
        for controller, _ in controllers:
            assert controller.status == "PROCESSING"
            assert controller._last_output_time is None

        # Simulate output for each agent at different times
        for _i, (controller, _timeout) in enumerate(controllers):
            time.sleep(0.3)
            with controller.lock:
                controller._last_output_time = time.time()

            # After output, should still be PROCESSING
            controller._check_idle_state(b"output")
            assert controller.status == "PROCESSING"

        # Wait for all to reach their timeout
        time.sleep(2.0)

        # Trigger idle check for each
        for controller, _timeout in controllers:
            controller._check_idle_state(b"")

        # All should now be READY
        for controller, _ in controllers:
            assert controller.status == "READY"

    def test_output_resets_idle_detection(self, temp_registry):
        """New output should reset idle detection timer."""
        agent_id = "test-gemini-init-timing-reset"

        controller = TerminalController(
            command="gemini",
            idle_detection={"strategy": "timeout", "timeout": 0.2},
            registry=temp_registry,
            agent_id=agent_id,
            agent_type="gemini",
            port=8114,
        )

        temp_registry.register(agent_id, "gemini", 8114, status="PROCESSING")

        # Initialize as if in interactive mode
        controller.interactive = True
        controller.running = True
        with controller.lock:
            controller._last_output_time = None

        # Simulate first output
        with controller.lock:
            controller._last_output_time = time.time()

        # Wait 0.15s (less than timeout)
        time.sleep(0.15)

        # More output should reset the timer
        with controller.lock:
            controller._last_output_time = time.time()

        # Immediately check - should still be PROCESSING
        controller._check_idle_state(b"more output")
        assert controller.status == "PROCESSING"

        # Wait another 0.15s (still less than timeout from the second output)
        time.sleep(0.15)
        controller._check_idle_state(b"")
        assert controller.status == "PROCESSING"

        # Finally wait for timeout to expire
        time.sleep(0.1)
        controller._check_idle_state(b"")
        assert controller.status == "READY"
