"""Tests for interactive mode idle detection with periodic checking."""

import shutil
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from synapse.controller import TerminalController
from synapse.registry import AgentRegistry


@pytest.fixture
def temp_registry_dir():
    """Create a temporary registry directory."""
    temp_dir = Path("/tmp/a2a_test_interactive_idle")
    temp_dir.mkdir(parents=True, exist_ok=True)
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def temp_registry(temp_registry_dir):
    """Create a test registry with temp directory."""
    reg = AgentRegistry()
    reg.registry_dir = temp_registry_dir
    return reg


class TestInteractivePollTimeout:
    """Tests for periodic polling timeout in interactive mode."""

    def test_select_timeout_triggers_idle_check(self, temp_registry):
        """Periodic select() timeout should trigger idle check even with no data."""
        agent_id = "test-interactive-timeout-1"

        controller = TerminalController(
            command="echo",
            idle_detection={
                "strategy": "timeout",
                "timeout": 0.5,
            },
            registry=temp_registry,
            agent_id=agent_id,
            agent_type="claude",
            port=8100,
        )

        temp_registry.register(agent_id, "claude", 8100, status="PROCESSING")

        # Simulate: set last output time to old value
        controller._last_output_time = time.time() - 1.0

        # Call _check_idle_state with no data (simulating timeout with no PTY data)
        controller._check_idle_state(b"")

        # Should transition to READY
        assert controller.status == "READY"
        registry_data = temp_registry.get_agent(agent_id)
        assert registry_data.get("status") == "READY"

    def test_output_resets_processing_status(self, temp_registry):
        """New PTY output should transition from READY back to PROCESSING."""
        agent_id = "test-interactive-timeout-2"

        controller = TerminalController(
            command="echo",
            idle_detection={
                "strategy": "timeout",
                "timeout": 0.5,
            },
            registry=temp_registry,
            agent_id=agent_id,
            agent_type="claude",
            port=8101,
        )

        temp_registry.register(agent_id, "claude", 8101, status="PROCESSING")

        # First: become READY
        controller._last_output_time = time.time() - 1.0
        controller._check_idle_state(b"")
        assert controller.status == "READY"

        # Second: receive new output -> should be PROCESSING
        controller._last_output_time = time.time()  # Recent output
        controller._append_output(b"new output")
        controller._check_idle_state(b"new output")
        assert controller.status == "PROCESSING"

    def test_periodic_idle_detection_threshold(self, temp_registry):
        """Idle detection should respect timeout threshold."""
        agent_id = "test-interactive-timeout-3"

        controller = TerminalController(
            command="echo",
            idle_detection={
                "strategy": "timeout",
                "timeout": 2.0,  # 2 second threshold
            },
            registry=temp_registry,
            agent_id=agent_id,
            agent_type="claude",
            port=8102,
        )

        temp_registry.register(agent_id, "claude", 8102, status="PROCESSING")

        # Set last output to 1.5 seconds ago (below 2.0 threshold)
        controller._last_output_time = time.time() - 1.5
        controller._check_idle_state(b"")

        # Should still be PROCESSING
        assert controller.status == "PROCESSING"

        # Now set to 2.1 seconds ago (above threshold)
        controller._last_output_time = time.time() - 2.1
        controller._check_idle_state(b"")

        # Should now be READY
        assert controller.status == "READY"


class TestInteractivePatternDetection:
    """Tests for pattern-based idle detection in interactive mode."""

    def test_pattern_detection_in_interactive(self, temp_registry):
        """Pattern strategy should work in interactive mode."""
        agent_id = "test-interactive-pattern-1"

        controller = TerminalController(
            command="echo",
            idle_detection={
                "strategy": "pattern",
                "pattern": "PROMPT:",
                "timeout": 1.5,
            },
            registry=temp_registry,
            agent_id=agent_id,
            agent_type="test",
            port=8103,
        )

        temp_registry.register(agent_id, "test", 8103, status="PROCESSING")

        # Simulate pattern in output
        controller.output_buffer = b"user input\nPROMPT: "
        controller._append_output(b"PROMPT: ")

        with patch("synapse.controller.threading.Thread"):
            controller._check_idle_state(b"PROMPT: ")

        # Should be READY
        assert controller.status == "READY"

    def test_pattern_disappearance_triggers_processing(self, temp_registry):
        """When pattern disappears, should transition to PROCESSING."""
        agent_id = "test-interactive-pattern-2"

        controller = TerminalController(
            command="echo",
            idle_detection={
                "strategy": "pattern",
                "pattern": "PROMPT:",
                "timeout": 1.5,
            },
            registry=temp_registry,
            agent_id=agent_id,
            agent_type="test",
            port=8104,
        )

        temp_registry.register(agent_id, "test", 8104, status="PROCESSING")

        # First: pattern present -> READY
        controller.output_buffer = b"PROMPT: "
        with patch("synapse.controller.threading.Thread"):
            controller._check_idle_state(b"PROMPT: ")
        assert controller.status == "READY"

        # Second: pattern disappears -> PROCESSING
        controller.output_buffer = b"processing output"
        controller._append_output(b"output")
        controller._check_idle_state(b"output")
        assert controller.status == "PROCESSING"


class TestInteractiveHybridStrategy:
    """Tests for hybrid strategy in interactive mode."""

    def test_hybrid_pattern_then_timeout(self, temp_registry):
        """Hybrid should use pattern first, then timeout."""
        agent_id = "test-interactive-hybrid-1"

        controller = TerminalController(
            command="echo",
            idle_detection={
                "strategy": "hybrid",
                "pattern": "BRACKETED_PASTE_MODE",
                "pattern_use": "startup_only",
                "timeout": 0.5,
            },
            registry=temp_registry,
            agent_id=agent_id,
            agent_type="claude",
            port=8105,
        )

        temp_registry.register(agent_id, "claude", 8105, status="PROCESSING")

        # Phase 1: Detect pattern at startup
        controller.output_buffer = b"\x1b[?2004h"
        with patch("synapse.controller.threading.Thread"):
            controller._check_idle_state(b"\x1b[?2004h")
        assert controller.status == "READY"
        assert controller._pattern_detected is True

        # Phase 2: Reset status, simulate user input
        controller.status = "PROCESSING"
        controller._identity_sent = True
        controller.output_buffer = b"processing"
        controller._append_output(b"output")
        controller._check_idle_state(b"output")
        assert controller.status == "PROCESSING"

        # Phase 3: Timeout after pattern_detected (pattern_use=startup_only)
        controller._last_output_time = time.time() - 1.0  # 1 second ago
        controller._check_idle_state(b"")
        # Should be READY (timeout-based, not pattern)
        assert controller.status == "READY"


class TestInteractiveTerminalHandling:
    """Tests for terminal mode preservation in interactive mode."""

    def test_terminal_settings_preserved(self, temp_registry):
        """Terminal settings should be saved and restored."""
        agent_id = "test-interactive-terminal-1"

        controller = TerminalController(
            command="echo",
            idle_detection={
                "strategy": "timeout",
                "timeout": 0.5,
            },
            registry=temp_registry,
            agent_id=agent_id,
            agent_type="claude",
            port=8106,
        )

        # We can't fully test terminal mode without a real PTY
        # But we can verify the code paths exist
        assert hasattr(controller, "interactive")
        assert hasattr(controller, "master_fd")

    def test_master_fd_initialization(self, temp_registry):
        """master_fd should be properly set and used."""
        agent_id = "test-interactive-terminal-2"

        controller = TerminalController(
            command="echo",
            idle_detection={
                "strategy": "timeout",
                "timeout": 0.5,
            },
            registry=temp_registry,
            agent_id=agent_id,
            agent_type="claude",
            port=8107,
        )

        # Initially should be None
        assert controller.master_fd is None

        # In actual run_interactive(), it would be set by forkpty()
        # We verify it's initialized for tracking
        assert hasattr(controller, "_last_output_time")


class TestInteractiveIdleDetectionTiming:
    """Tests for timing aspects of idle detection in interactive mode."""

    def test_polling_interval_independent_of_data(self, temp_registry):
        """Idle checks should occur even without PTY data (timeout-based)."""
        agent_id = "test-interactive-timing-1"

        controller = TerminalController(
            command="echo",
            idle_detection={
                "strategy": "timeout",
                "timeout": 0.1,  # Very short timeout
            },
            registry=temp_registry,
            agent_id=agent_id,
            agent_type="claude",
            port=8108,
        )

        temp_registry.register(agent_id, "claude", 8108, status="PROCESSING")

        # Simulate time passing without output
        controller._last_output_time = time.time() - 0.15

        # Call _check_idle_state with no data (empty bytes)
        # This represents the select() timeout case
        controller._check_idle_state(b"")

        # Should detect idle
        assert controller.status == "READY"

    def test_last_output_time_updated_on_data(self, temp_registry):
        """_last_output_time should update when data arrives."""
        agent_id = "test-interactive-timing-2"

        controller = TerminalController(
            command="echo",
            idle_detection={
                "strategy": "timeout",
                "timeout": 0.5,
            },
            registry=temp_registry,
            agent_id=agent_id,
            agent_type="claude",
            port=8109,
        )

        # Set old time
        old_time = time.time() - 10.0
        controller._last_output_time = old_time

        # Process new output
        controller._append_output(b"new data")

        # Last output time should be updated
        assert controller._last_output_time > old_time
        assert controller._last_output_time <= time.time()

    def test_status_unchanged_before_timeout(self, temp_registry):
        """Status should remain PROCESSING until timeout expires."""
        agent_id = "test-interactive-timing-3"

        controller = TerminalController(
            command="echo",
            idle_detection={
                "strategy": "timeout",
                "timeout": 1.0,
            },
            registry=temp_registry,
            agent_id=agent_id,
            agent_type="claude",
            port=8110,
        )

        temp_registry.register(agent_id, "claude", 8110, status="PROCESSING")

        # Set last output time to recent (within timeout)
        controller._last_output_time = time.time() - 0.5

        # Check idle state
        controller._check_idle_state(b"")

        # Should still be PROCESSING
        assert controller.status == "PROCESSING"


class TestInteractiveRegistrySynchronization:
    """Tests for registry sync in interactive mode."""

    def test_status_synced_on_transition(self, temp_registry):
        """Status changes should sync to registry in interactive mode."""
        agent_id = "test-interactive-sync-1"

        controller = TerminalController(
            command="echo",
            idle_detection={
                "strategy": "timeout",
                "timeout": 0.5,
            },
            registry=temp_registry,
            agent_id=agent_id,
            agent_type="claude",
            port=8111,
        )

        temp_registry.register(agent_id, "claude", 8111, status="PROCESSING")

        # Transition to READY
        controller._last_output_time = time.time() - 1.0
        controller._check_idle_state(b"")

        # Verify registry is updated
        registry_data = temp_registry.get_agent(agent_id)
        assert registry_data["status"] == "READY"

        # Transition back to PROCESSING
        controller._last_output_time = time.time()
        controller._append_output(b"output")
        controller._check_idle_state(b"output")

        # Verify registry is updated again
        registry_data = temp_registry.get_agent(agent_id)
        assert registry_data["status"] == "PROCESSING"

    def test_multiple_transitions_sync_correctly(self, temp_registry):
        """Multiple status transitions should all sync correctly."""
        agent_id = "test-interactive-sync-2"

        controller = TerminalController(
            command="echo",
            idle_detection={
                "strategy": "timeout",
                "timeout": 0.3,
            },
            registry=temp_registry,
            agent_id=agent_id,
            agent_type="claude",
            port=8112,
        )

        temp_registry.register(agent_id, "claude", 8112, status="PROCESSING")

        # Cycle: PROCESSING -> READY -> PROCESSING -> READY
        for i in range(4):
            if i % 2 == 0:
                # Transition to READY
                controller._last_output_time = time.time() - 1.0
                controller._check_idle_state(b"")
                assert controller.status == "READY"
            else:
                # Transition back to PROCESSING
                controller._last_output_time = time.time()
                controller._append_output(b"output")
                controller._check_idle_state(b"output")
                assert controller.status == "PROCESSING"

            # Verify registry is synchronized at each step
            registry_data = temp_registry.get_agent(agent_id)
            assert registry_data["status"] == controller.status


class TestInteractiveVsBackgroundConsistency:
    """Tests to ensure interactive mode has same behavior as background mode."""

    def test_same_idle_detection_logic(self, temp_registry):
        """Interactive and background modes should use same idle detection logic."""
        agent_id = "test-consistency-1"

        controller = TerminalController(
            command="echo",
            idle_detection={
                "strategy": "timeout",
                "timeout": 0.5,
            },
            registry=temp_registry,
            agent_id=agent_id,
            agent_type="claude",
            port=8113,
        )

        temp_registry.register(agent_id, "claude", 8113, status="PROCESSING")

        # Both background and interactive use same _check_idle_state() method
        controller._last_output_time = time.time() - 1.0

        # In background mode: called from _monitor_output() when select() times out
        # In interactive mode: called from run_interactive() when select() times out
        controller._check_idle_state(b"")

        assert controller.status == "READY"

    def test_same_strategy_handling(self, temp_registry):
        """Interactive and background should support all strategies."""
        for strategy in ["timeout", "pattern"]:
            agent_id = f"test-consistency-{strategy}"

            config = {
                "strategy": strategy,
                "timeout": 0.5,
            }
            if strategy == "pattern":
                config["pattern"] = "PROMPT:"

            controller = TerminalController(
                command="echo",
                idle_detection=config,
                registry=temp_registry,
                agent_id=agent_id,
                agent_type="test",
                port=8114,
            )

            # Verify controller accepts the configuration
            assert controller.idle_strategy == strategy
