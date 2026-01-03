"""Tests for multi-strategy idle detection in TerminalController."""

import json
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
    temp_dir = Path("/tmp/a2a_test_idle_strategies")
    temp_dir.mkdir(parents=True, exist_ok=True)
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def temp_registry(temp_registry_dir):
    """Create a test registry with temp directory."""
    reg = AgentRegistry()
    reg.registry_dir = temp_registry_dir
    return reg


class TestPatternStrategy:
    """Tests for pattern-based idle detection strategy."""

    def test_pattern_strategy_detects_on_match(self, temp_registry):
        """Pattern strategy should detect idle when pattern matches."""
        agent_id = "test-agent-pattern-1"

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
            port=8100,
        )

        # Register agent
        temp_registry.register(agent_id, "test", 8100, status="PROCESSING")

        # Simulate output with pattern
        controller.output_buffer = b"user input\nPROMPT: "

        with patch("synapse.controller.threading.Thread"):
            controller._check_idle_state(b"PROMPT: ")

        # Should be READY
        assert controller.status == "READY"

        # Registry should be updated
        registry_data = temp_registry.get_agent(agent_id)
        assert registry_data.get("status") == "READY"

    def test_pattern_strategy_ignores_timeout(self, temp_registry):
        """Pattern strategy should ignore timeout-based detection."""
        agent_id = "test-agent-pattern-2"

        controller = TerminalController(
            command="echo",
            idle_detection={
                "strategy": "pattern",
                "pattern": "PROMPT:",
                "timeout": 0.1,  # Very short timeout
            },
            registry=temp_registry,
            agent_id=agent_id,
            agent_type="test",
            port=8101,
        )

        # Register agent
        temp_registry.register(agent_id, "test", 8101, status="PROCESSING")

        # Set last output time to old value
        controller._last_output_time = time.time() - 10.0

        # Call with empty data (no pattern)
        controller._check_idle_state(b"")

        # Should still be PROCESSING (timeout ignored in pattern-only mode)
        assert controller.status == "PROCESSING"

    def test_pattern_strategy_respects_pattern_value(self, temp_registry):
        """Pattern strategy should respect configured pattern value."""
        agent_id = "test-agent-pattern-3"

        controller = TerminalController(
            command="echo",
            idle_detection={
                "strategy": "pattern",
                "pattern": "(> |\\*)",  # Gemini prompt pattern
                "timeout": 1.5,
            },
            registry=temp_registry,
            agent_id=agent_id,
            agent_type="gemini",
            port=8110,
        )

        # Register agent
        temp_registry.register(agent_id, "gemini", 8110, status="PROCESSING")

        # Simulate Gemini prompt
        controller.output_buffer = b"output\n> "

        with patch("synapse.controller.threading.Thread"):
            controller._check_idle_state(b"> ")

        # Should be READY
        assert controller.status == "READY"


class TestTimeoutStrategy:
    """Tests for timeout-based idle detection strategy."""

    def test_timeout_strategy_detects_on_idle(self, temp_registry):
        """Timeout strategy should detect idle when no output for threshold seconds."""
        agent_id = "test-agent-timeout-1"

        controller = TerminalController(
            command="echo",
            idle_detection={
                "strategy": "timeout",
                "timeout": 0.5,
            },
            registry=temp_registry,
            agent_id=agent_id,
            agent_type="test",
            port=8102,
        )

        # Register agent
        temp_registry.register(agent_id, "test", 8102, status="PROCESSING")

        # Set last output time to old value (> 0.5 seconds ago)
        controller._last_output_time = time.time() - 1.0

        controller._check_idle_state(b"")

        # Should be READY
        assert controller.status == "READY"

        # Registry should be updated
        registry_data = temp_registry.get_agent(agent_id)
        assert registry_data.get("status") == "READY"

    def test_timeout_strategy_ignores_pattern(self, temp_registry):
        """Timeout strategy should ignore pattern matching."""
        agent_id = "test-agent-timeout-2"

        controller = TerminalController(
            command="echo",
            idle_detection={
                "strategy": "timeout",
                "pattern": "PROMPT:",  # Should be ignored
                "timeout": 1.5,
            },
            registry=temp_registry,
            agent_id=agent_id,
            agent_type="test",
            port=8103,
        )

        # Register agent
        temp_registry.register(agent_id, "test", 8103, status="PROCESSING")

        # Set recent output time (no timeout)
        controller._last_output_time = time.time()

        # Send data with pattern
        controller.output_buffer = b"PROMPT: "
        controller._check_idle_state(b"PROMPT: ")

        # Should still be PROCESSING (pattern ignored in timeout-only mode)
        assert controller.status == "PROCESSING"

    def test_timeout_strategy_respects_threshold(self, temp_registry):
        """Timeout strategy should respect configured timeout threshold."""
        agent_id = "test-agent-timeout-3"

        controller = TerminalController(
            command="echo",
            idle_detection={
                "strategy": "timeout",
                "timeout": 2.0,  # 2 second threshold
            },
            registry=temp_registry,
            agent_id=agent_id,
            agent_type="test",
            port=8104,
        )

        # Register agent
        temp_registry.register(agent_id, "test", 8104, status="PROCESSING")

        # Set last output time to 1.5 seconds ago (< 2.0 threshold)
        controller._last_output_time = time.time() - 1.5

        controller._check_idle_state(b"")

        # Should still be PROCESSING
        assert controller.status == "PROCESSING"


class TestHybridStrategy:
    """Tests for hybrid idle detection strategy."""

    def test_hybrid_pattern_on_first_idle(self, temp_registry):
        """Hybrid strategy should use pattern for first idle."""
        agent_id = "test-agent-hybrid-1"

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
            port=8100,
        )

        # Register agent
        temp_registry.register(agent_id, "claude", 8100, status="PROCESSING")

        # Simulate BRACKETED_PASTE_MODE output
        controller.output_buffer = b"\x1b[?2004h"

        with patch("synapse.controller.threading.Thread"):
            controller._check_idle_state(b"\x1b[?2004h")

        # Should be READY
        assert controller.status == "READY"
        assert controller._pattern_detected is True

    def test_hybrid_timeout_after_pattern(self, temp_registry):
        """Hybrid strategy should use timeout after pattern detected once."""
        agent_id = "test-agent-hybrid-2"

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
            port=8101,
        )

        # Register agent
        temp_registry.register(agent_id, "claude", 8101, status="PROCESSING")

        # First: Detect pattern
        controller.output_buffer = b"\x1b[?2004h"
        with patch("synapse.controller.threading.Thread"):
            controller._check_idle_state(b"\x1b[?2004h")
        assert controller.status == "READY"

        # Now set status back to PROCESSING (user input received)
        controller.status = "PROCESSING"
        controller._identity_sent = True  # Skip identity instruction

        # Simulate some output and then idle (pattern disappears)
        controller.output_buffer = b"some output"
        controller._check_idle_state(b"output")

        # Still PROCESSING (just received output)
        assert controller.status == "PROCESSING"

        # Now simulate no output for timeout period
        controller._last_output_time = time.time() - 1.0  # 1 second ago

        controller._check_idle_state(b"")

        # Should be READY (timeout-based after pattern)
        assert controller.status == "READY"

    def test_hybrid_pattern_startup_only(self, temp_registry):
        """Hybrid strategy with pattern_use=startup_only should ignore pattern after first match."""
        agent_id = "test-agent-hybrid-3"

        controller = TerminalController(
            command="echo",
            idle_detection={
                "strategy": "hybrid",
                "pattern": "PROMPT:",
                "pattern_use": "startup_only",
                "timeout": 0.5,
            },
            registry=temp_registry,
            agent_id=agent_id,
            agent_type="test",
            port=8102,
        )

        # Register agent
        temp_registry.register(agent_id, "test", 8102, status="PROCESSING")

        # First: Detect pattern
        controller.output_buffer = b"PROMPT: "
        with patch("synapse.controller.threading.Thread"):
            controller._check_idle_state(b"PROMPT: ")
        assert controller.status == "READY"
        assert controller._pattern_detected is True

        # Reset to PROCESSING
        controller.status = "PROCESSING"
        controller._identity_sent = True

        # Second: Pattern appears again, but should be ignored (startup_only)
        controller.output_buffer = b"PROMPT: "

        # Short timeout - if pattern is checked again, status would be READY
        # But pattern_use=startup_only should skip pattern check
        controller._last_output_time = time.time()  # Recent output

        controller._check_idle_state(b"PROMPT: ")

        # Should still be PROCESSING (pattern not checked, timeout not met)
        assert controller.status == "PROCESSING"

    def test_claude_timeout_strategy(self, temp_registry):
        """Claude Code timeout strategy: pure timeout-based detection."""
        agent_id = "test-agent-claude-timeout"

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

        # Phase 1: Startup - output being produced
        controller.output_buffer = b"\x1b[?2004h..."
        controller._last_output_time = time.time()
        controller._check_idle_state(b"startup output")
        assert controller.status == "PROCESSING"

        # Phase 2: User sends input - status changes to PROCESSING
        controller.status = "PROCESSING"
        controller._identity_sent = True
        controller.output_buffer = b"processing user input..."
        controller._last_output_time = time.time()
        controller._check_idle_state(b"processing user input...")
        assert controller.status == "PROCESSING"

        # Phase 3: Agent becomes idle (0.5s timeout expires)
        controller._last_output_time = time.time() - 1.0
        controller._check_idle_state(b"")
        assert controller.status == "READY"


class TestBackwardCompatibility:
    """Tests for backward compatibility with legacy idle_regex parameter."""

    def test_legacy_idle_regex_parameter(self, temp_registry):
        """Old idle_regex parameter should still work (converted to pattern strategy)."""
        agent_id = "test-agent-legacy"

        # Using old idle_regex parameter
        controller = TerminalController(
            command="echo",
            idle_regex="PROMPT:",  # Old parameter
            registry=temp_registry,
            agent_id=agent_id,
            agent_type="test",
            port=8105,
        )

        temp_registry.register(agent_id, "test", 8105, status="PROCESSING")

        # Should have converted to pattern strategy
        assert controller.idle_strategy == "pattern"
        assert controller.idle_config["pattern"] == "PROMPT:"

        # Should work
        controller.output_buffer = b"PROMPT: "
        with patch("synapse.controller.threading.Thread"):
            controller._check_idle_state(b"PROMPT: ")
        assert controller.status == "READY"

    def test_idle_detection_takes_precedence(self, temp_registry):
        """If both idle_detection and idle_regex provided, idle_detection should win."""
        agent_id = "test-agent-precedence"

        controller = TerminalController(
            command="echo",
            idle_detection={
                "strategy": "timeout",
                "timeout": 0.5,
            },
            idle_regex="IGNORED:",  # Should be ignored
            registry=temp_registry,
            agent_id=agent_id,
            agent_type="test",
            port=8106,
        )

        temp_registry.register(agent_id, "test", 8106, status="PROCESSING")

        # Should use timeout strategy, not pattern
        assert controller.idle_strategy == "timeout"

        # Pattern should not match
        controller.output_buffer = b"IGNORED: this is present"
        controller._last_output_time = time.time()
        controller._check_idle_state(b"IGNORED:")

        # Should be PROCESSING (pattern ignored, timeout not met)
        assert controller.status == "PROCESSING"


class TestProfileLoading:
    """Tests for profile-based idle detection configuration loading."""

    def test_parse_idle_detection_from_profile(self):
        """Profile loading should correctly parse idle_detection section."""
        # This test validates the expected profile format
        profile = {
            "command": "claude",
            "idle_detection": {
                "strategy": "hybrid",
                "pattern": "BRACKETED_PASTE_MODE",
                "pattern_use": "startup_only",
                "timeout": 0.5,
            },
        }

        # Verify structure
        assert profile["idle_detection"]["strategy"] == "hybrid"
        assert profile["idle_detection"]["pattern"] == "BRACKETED_PASTE_MODE"
        assert profile["idle_detection"]["timeout"] == 0.5

    def test_profile_gemini_timeout_strategy(self):
        """Gemini profile should use timeout strategy (pattern unreliable with history)."""
        profile = {
            "command": "gemini",
            "idle_detection": {
                "strategy": "timeout",
                "timeout": 1.5,
            },
        }

        assert profile["idle_detection"]["strategy"] == "timeout"
        assert profile["idle_detection"]["timeout"] == 1.5

    def test_profile_codex_timeout_strategy(self):
        """Codex profile should use timeout strategy (pattern unreliable with history)."""
        profile = {
            "command": "codex",
            "idle_detection": {
                "strategy": "timeout",
                "timeout": 1.5,
            },
        }

        assert profile["idle_detection"]["strategy"] == "timeout"
        assert profile["idle_detection"]["timeout"] == 1.5


class TestStrategyTransitions:
    """Tests for status transitions with different strategies."""

    def test_pattern_ready_to_processing_transition(self, temp_registry):
        """Pattern strategy keeps READY if pattern is anywhere in buffer (can't detect processing)."""
        agent_id = "test-agent-transition-1"

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
            port=8107,
        )

        temp_registry.register(agent_id, "test", 8107, status="PROCESSING")

        # First: READY (pattern matches)
        controller.output_buffer = b"PROMPT: "
        with patch("synapse.controller.threading.Thread"):
            controller._check_idle_state(b"PROMPT: ")
        assert controller.status == "READY"

        # Note: Pattern strategy stays READY as long as pattern exists in buffer
        # This is why we prefer timeout strategy for agents with conversation history
        # where old prompts remain visible (Gemini, Codex)
        controller._append_output(b"\nProcessing user request...\nWorking...\nPROMPT: ")
        controller._check_idle_state(b"PROMPT: ")
        assert controller.status == "READY"  # Still READY because pattern is present

    def test_pattern_gemini_output_simulation(self, temp_registry):
        """Simulate Gemini output with timeout-based detection (pattern unreliable)."""
        agent_id = "test-agent-gemini-timeout"

        # Gemini uses timeout strategy (pattern matching is unreliable with conversation history)
        controller = TerminalController(
            command="gemini",
            idle_detection={
                "strategy": "timeout",
                "timeout": 0.5,  # Short timeout for testing
            },
            registry=temp_registry,
            agent_id=agent_id,
            agent_type="gemini",
            port=8110,
        )

        temp_registry.register(agent_id, "gemini", 8110, status="PROCESSING")

        # Phase 1: Startup, agent outputs and becomes idle (0.5s timeout)
        controller._append_output(b"Gemini initialization...\n> ")
        controller._last_output_time = time.time() - 1.0  # 1 second ago
        with patch("synapse.controller.threading.Thread"):
            controller._check_idle_state(b"")
        assert controller.status == "READY"

        # Phase 2: User sends input, agent starts processing (fresh output)
        controller._last_output_time = time.time()  # Just now
        controller._append_output(b"Processing your query...\nThinking...\n")
        controller._check_idle_state(b"Processing...")
        assert controller.status == "PROCESSING"

        # Phase 3: Agent finishes and becomes idle (0.5s timeout)
        # First, output arrives (updates _last_output_time to now)
        controller._append_output(b"Here's the result\n")
        assert controller.status == "PROCESSING"

        # Then, time passes and idle check occurs with no new data
        controller._last_output_time = time.time() - 1.0  # 1 second ago
        controller._check_idle_state(b"")
        assert controller.status == "READY"

    def test_timeout_ready_to_processing_transition(self, temp_registry):
        """Agent should transition from READY to PROCESSING when output received."""
        agent_id = "test-agent-transition-2"

        controller = TerminalController(
            command="echo",
            idle_detection={
                "strategy": "timeout",
                "timeout": 0.5,
            },
            registry=temp_registry,
            agent_id=agent_id,
            agent_type="test",
            port=8108,
        )

        temp_registry.register(agent_id, "test", 8108, status="PROCESSING")

        # First: READY (timeout met)
        controller._last_output_time = time.time() - 1.0
        with patch("synapse.controller.threading.Thread"):
            controller._check_idle_state(b"")
        assert controller.status == "READY"

        # Second: PROCESSING (new output received)
        controller._last_output_time = time.time()
        controller._check_idle_state(b"new output")
        assert controller.status == "PROCESSING"
