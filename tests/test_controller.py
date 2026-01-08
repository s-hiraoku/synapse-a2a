"""Tests for TerminalController identity instruction functionality."""

import threading
import time
from unittest.mock import Mock, patch

import pytest

from synapse.controller import TerminalController
from synapse.registry import AgentRegistry


class TestIdentityInstruction:
    """Tests for identity instruction sending on first IDLE."""

    @pytest.fixture
    def mock_registry(self):
        """Create a mock registry."""
        registry = Mock(spec=AgentRegistry)
        registry.list_agents.return_value = {
            "synapse-gemini-8101": {"agent_type": "gemini", "port": 8101}
        }
        # get_live_agents is used by get_other_agents_from_registry
        registry.get_live_agents.return_value = {
            "synapse-gemini-8101": {
                "agent_id": "synapse-gemini-8101",
                "agent_type": "gemini",
                "endpoint": "http://localhost:8101",
                "status": "READY",
            }
        }
        return registry

    @pytest.fixture
    def controller(self, mock_registry):
        """Create a controller with agent_id and agent_type."""
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$",
            registry=mock_registry,
            agent_id="synapse-claude-8100",
            agent_type="claude",
            submit_seq="\r",
        )
        return ctrl

    def test_controller_has_agent_identity(self, controller):
        """Controller should store agent_id and agent_type."""
        assert controller.agent_id == "synapse-claude-8100"
        assert controller.agent_type == "claude"
        assert controller._submit_seq == "\r"
        assert controller._identity_sent is False

    def test_identity_not_sent_initially(self, controller):
        """Identity should not be sent before first IDLE."""
        assert controller._identity_sent is False

    def test_check_idle_state_detects_idle(self, controller):
        """_check_idle_state should detect IDLE when regex matches."""
        controller.running = True
        controller.master_fd = 1  # Mock fd

        # Add data that matches idle_regex
        controller.output_buffer = b"some output $"

        # Mock write to prevent actual writing
        controller.write = Mock()

        controller._check_idle_state(b"$")

        assert controller.status == "READY"

    def test_identity_sent_on_first_idle(self, controller):
        """Identity instruction should be sent on first IDLE detection."""
        controller.running = True
        controller.master_fd = 1  # Mock fd
        controller.output_buffer = b"prompt $"

        # Track if _send_identity_instruction was called
        send_called = threading.Event()
        original_send = controller._send_identity_instruction  # noqa: F841

        def mock_send():
            controller._identity_sent = True
            controller._identity_sending = False
            send_called.set()

        controller._send_identity_instruction = mock_send

        # Verify flag is not set initially
        assert controller._identity_sent is False

        # Trigger idle detection
        controller._check_idle_state(b"$")

        # Wait for thread
        time.sleep(0.1)

        # Flag should be set and _send_identity_instruction should be called
        assert controller._identity_sent is True
        assert controller.status == "READY"
        assert send_called.is_set()

    def test_identity_sent_only_once(self, controller):
        """Identity instruction should only be sent once, not on subsequent IDLE transitions."""
        controller.running = True
        controller.master_fd = 1
        controller.output_buffer = b"prompt $"

        # Track call count
        call_count = [0]

        def mock_send():
            controller._identity_sent = True
            controller._identity_sending = False
            call_count[0] += 1

        controller._send_identity_instruction = mock_send

        # First IDLE - should call _send_identity_instruction
        controller._check_idle_state(b"$")
        time.sleep(0.1)
        assert controller._identity_sent is True
        assert call_count[0] == 1

        # Manually set back to BUSY to simulate activity
        controller.status = "BUSY"
        controller.output_buffer = b"more output $"

        # Second IDLE - should NOT call again
        controller._check_idle_state(b"$")
        time.sleep(0.1)
        assert controller._identity_sent is True
        assert controller.status == "READY"
        assert call_count[0] == 1  # Still 1, not 2

        def test_identity_instruction_content(self, controller, mock_registry):
            """Identity instruction should contain correct full instructions with A2A format."""
            controller.running = True
            controller.master_fd = 1

            written_data = []

            def mock_write(data, submit_seq=None):
                written_data.append(data)

            controller.write = mock_write

            # Patch get_settings to return deterministic instructions
            with patch("synapse.controller.get_settings") as mock_get_settings:
                mock_settings = Mock()
                mock_settings.get_instruction.return_value = (
                    "[SYNAPSE INSTRUCTIONS - DO NOT EXECUTE]\n"
                    "Agent: {{agent_id}} | Port: {{port}}\n"
                    "HOW TO RECEIVE A2A MESSAGES\n"
                    "HOW TO SEND MESSAGES TO OTHER AGENTS\n"
                    "AVAILABLE AGENTS: claude, gemini, codex\n"
                    "LIST COMMAND: a2a.py list\n"
                    "SKILL: synapse-a2a skill\n"
                    "TASK HISTORY:\n"
                    "  synapse history list\n"
                    "  synapse history cleanup\n"
                )
                mock_get_settings.return_value = mock_settings

                # Call directly to test content
                controller._send_identity_instruction()

            assert len(written_data) == 1
            instruction = written_data[0]

            # Check A2A Task format prefix
            assert instruction.startswith("[A2A:")
            assert ":synapse-system]" in instruction

            # Check key content - bootstrap message format
            assert "synapse-claude-8100" in instruction
            assert "SYNAPSE INSTRUCTIONS" in instruction
            assert "8100" in instruction
            assert "a2a.py list" in instruction
            # Check for A2A message handling instructions
            assert "RECEIVE A2A MESSAGES" in instruction
            assert "SEND" in instruction and "AGENTS" in instruction
            # Check for do not execute marker
            assert "DO NOT EXECUTE" in instruction

    def test_identity_not_sent_without_agent_id(self, mock_registry):
        """Identity should not be sent if agent_id is None."""
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$",
            registry=mock_registry,
            agent_id=None,
            agent_type="claude",
        )
        ctrl.running = True
        ctrl.master_fd = 1
        ctrl.output_buffer = b"prompt $"

        ctrl.write = Mock()  # type: ignore[method-assign]
        ctrl._check_idle_state(b"$")

        time.sleep(0.2)

        # write should not have been called
        ctrl.write.assert_not_called()

    def test_identity_not_marked_sent_on_master_fd_timeout(
        self, controller, monkeypatch
    ):
        """Identity should retry if master_fd isn't ready in time."""
        controller.running = True
        controller.master_fd = None
        controller.write = Mock()

        monkeypatch.setattr("synapse.controller.IDENTITY_WAIT_TIMEOUT", 0)

        controller._send_identity_instruction()

        assert controller._identity_sent is False
        assert controller._identity_sending is False
        controller.write.assert_not_called()

    def test_identity_sent_on_success_marks_sent(self, controller, monkeypatch):
        """Successful send should mark identity as sent."""
        controller.running = True
        controller.master_fd = 1
        controller.write = Mock()

        monkeypatch.setattr("synapse.controller.POST_WRITE_IDLE_DELAY", 0)

        controller._send_identity_instruction()

        assert controller._identity_sent is True
        assert controller._identity_sending is False
        assert controller.write.called

    def test_idle_check_skips_when_identity_sending(self, controller):
        """Idle checks should not spawn duplicate identity send threads."""
        controller.running = True
        controller.master_fd = 1
        controller.output_buffer = b"prompt $"
        controller._identity_sending = True

        controller._send_identity_instruction = Mock()

        controller._check_idle_state(b"$")

        controller._send_identity_instruction.assert_not_called()


class TestOutputIdleDetection:
    """Tests for output idle detection mechanism."""

    def test_last_output_time_initialized_none(self):
        """Last output time should be None initially."""
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$",
            agent_id="synapse-claude-8100",
            agent_type="claude",
        )
        assert ctrl._last_output_time is None

    def test_output_idle_threshold_default(self):
        """Default output idle threshold should be 1.5 seconds."""
        ctrl = TerminalController(command="echo test", idle_regex=r"\$")
        assert ctrl._output_idle_threshold == 1.5

    def test_startup_delay_from_config(self):
        """Startup delay should be configurable."""
        ctrl = TerminalController(
            command="echo test", idle_regex=r"\$", startup_delay=8
        )
        assert ctrl._startup_delay == 8

    def test_startup_delay_default(self):
        """Default startup delay should be 3 seconds."""
        ctrl = TerminalController(command="echo test", idle_regex=r"\$")
        assert ctrl._startup_delay == 3


class TestSubmitSequence:
    """Tests for submit sequence configuration."""

    def test_default_submit_seq(self):
        """Default submit sequence should be newline."""
        ctrl = TerminalController(command="echo test", idle_regex=r"\$")
        assert ctrl._submit_seq == "\n"

    def test_custom_submit_seq(self):
        """Custom submit sequence should be stored."""
        ctrl = TerminalController(
            command="echo test", idle_regex=r"\$", submit_seq="\r"
        )
        assert ctrl._submit_seq == "\r"

    def test_submit_seq_used_in_identity(self):
        """Identity instruction should use configured submit_seq."""
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$",
            agent_id="synapse-claude-8100",
            agent_type="claude",
            submit_seq="\r",
        )
        ctrl.running = True
        ctrl.master_fd = 1

        captured_submit_seq = []

        def mock_write(data, submit_seq=None):
            captured_submit_seq.append(submit_seq)

        ctrl.write = mock_write  # type: ignore[method-assign]
        ctrl._send_identity_instruction()

        assert len(captured_submit_seq) == 1
        assert captured_submit_seq[0] == "\r"


class TestInterAgentMessageWrite:
    """Tests for inter-agent message writing."""

    def test_write_sends_data_then_submit_seq(self):
        """Write should send data first, then submit_seq after delay."""
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$",
            agent_id="synapse-claude-8100",
            agent_type="claude",
            submit_seq="\r",
        )
        ctrl.running = True
        ctrl.interactive = True
        ctrl.master_fd = 1  # Mock fd

        written_data = []

        # Mock os.write to capture what's being written
        import os

        original_write = os.write

        def mock_os_write(fd, data):
            written_data.append((fd, data))
            return len(data)

        os.write = mock_os_write

        try:
            ctrl.write("test message", submit_seq="\r")

            # Should have two writes: data, then submit_seq
            assert len(written_data) == 2
            assert written_data[0] == (1, b"test message")
            assert written_data[1] == (1, b"\r")
        finally:
            os.write = original_write

    def test_write_with_bracketed_paste_mode_idle_regex(self):
        """Write should send data then submit_seq with BRACKETED_PASTE_MODE idle_regex."""
        ctrl = TerminalController(
            command="claude",
            idle_regex="BRACKETED_PASTE_MODE",  # For IDLE detection only, not for writing
            agent_id="synapse-claude-8100",
            agent_type="claude",
            submit_seq="\r",
        )
        ctrl.running = True
        ctrl.interactive = True
        ctrl.master_fd = 1  # Mock fd

        written_data = []

        import os

        original_write = os.write

        def mock_os_write(fd, data):
            written_data.append((fd, data))
            return len(data)

        os.write = mock_os_write

        try:
            ctrl.write("test message", submit_seq="\r")

            # Should have two writes: data, then submit_seq
            assert len(written_data) == 2
            assert written_data[0] == (1, b"test message")
            assert written_data[1] == (1, b"\r")
        finally:
            os.write = original_write

    def test_write_in_non_interactive_mode(self):
        """Write should send data then submit_seq in non-interactive mode."""
        ctrl = TerminalController(command="echo test", idle_regex=r"\$")
        ctrl.running = True
        ctrl.interactive = False
        ctrl.master_fd = 1

        written_data = []

        import os

        original_write = os.write

        def mock_os_write(fd, data):
            written_data.append((fd, data))
            return len(data)

        os.write = mock_os_write

        try:
            ctrl.write("test message", submit_seq="\n")

            # Should have two writes: data, then submit_seq
            assert len(written_data) == 2
            assert written_data[0] == (1, b"test message")
            assert written_data[1] == (1, b"\n")
        finally:
            os.write = original_write

    def test_write_fails_when_not_running(self):
        """Write should do nothing when controller is not running."""
        ctrl = TerminalController(command="echo test", idle_regex=r"\$")
        ctrl.running = False
        ctrl.master_fd = 1

        # Should not raise, just return
        ctrl.write("test", submit_seq="\n")

    def test_write_raises_when_master_fd_none(self):
        """Write should raise when master_fd is None."""
        ctrl = TerminalController(command="echo test", idle_regex=r"\$")
        ctrl.running = True
        ctrl.master_fd = None

        with pytest.raises(ValueError) as excinfo:
            ctrl.write("test", submit_seq="\n")
        assert "master_fd is None" in str(excinfo.value)

    def test_write_sets_status_to_busy(self):
        """Write should set status to PROCESSING."""
        ctrl = TerminalController(command="echo test", idle_regex=r"\$")
        ctrl.running = True
        ctrl.interactive = False
        ctrl.master_fd = 1
        ctrl.status = "READY"

        import os

        original_write = os.write
        os.write = lambda fd, data: len(data) if isinstance(data, bytes | str) else 0  # type: ignore[assignment, unused-ignore]

        try:
            ctrl.write("test", submit_seq="\n")
            assert ctrl.status == "PROCESSING"
        finally:
            os.write = original_write

    def test_write_without_submit_seq(self):
        """Write should work without submit_seq."""
        ctrl = TerminalController(command="echo test", idle_regex=r"\$")
        ctrl.running = True
        ctrl.interactive = False
        ctrl.master_fd = 1

        written_data = []

        import os

        original_write = os.write

        def mock_os_write(fd, data):
            written_data.append((fd, data))
            return len(data)

        os.write = mock_os_write

        try:
            ctrl.write("test message")  # No submit_seq
            assert len(written_data) == 1
            assert written_data[0] == (1, b"test message")
        finally:
            os.write = original_write


class TestControllerStatusTransitions:
    """Tests for controller status transitions."""

    def test_initial_status_is_starting(self):
        """Controller should start with PROCESSING status."""
        ctrl = TerminalController(command="echo test", idle_regex=r"\$")
        assert ctrl.status == "PROCESSING"

    def test_status_changes_to_idle_on_pattern_match(self):
        """Status should change to READY when idle_regex matches."""
        ctrl = TerminalController(command="echo test", idle_regex=r"\$")
        ctrl.running = True
        ctrl.master_fd = 1
        ctrl.output_buffer = b"some output $"
        ctrl.write = Mock()  # type: ignore[method-assign]

        ctrl._check_idle_state(b"$")
        assert ctrl.status == "READY"

    def test_status_changes_to_busy_on_no_match(self):
        """Status should change to PROCESSING when idle_regex doesn't match."""
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$$",  # Must end with $
        )
        ctrl.running = True
        ctrl.master_fd = 1
        ctrl.output_buffer = b"some output without prompt"
        ctrl.status = "READY"

        ctrl._check_idle_state(b"no prompt here")
        assert ctrl.status == "PROCESSING"


class TestControllerOutputBuffer:
    """Tests for output buffer management."""

    def test_output_buffer_initialized_empty(self):
        """Output buffer should be empty initially."""
        ctrl = TerminalController(command="echo test", idle_regex=r"\$")
        assert ctrl.output_buffer == b""

    def test_get_context_returns_decoded_buffer(self):
        """get_context should return render buffer content."""
        ctrl = TerminalController(command="echo test", idle_regex=r"\$")
        ctrl._render_buffer = list("Hello World")

        context = ctrl.get_context()
        assert context == "Hello World"

    def test_get_context_handles_unicode(self):
        """get_context should handle unicode properly."""
        ctrl = TerminalController(command="echo test", idle_regex=r"\$")
        ctrl._render_buffer = list("こんにちは")

        context = ctrl.get_context()
        assert context == "こんにちは"

    def test_get_context_returns_empty_for_empty_buffer(self):
        """get_context should return empty string for empty buffer."""
        ctrl = TerminalController(command="echo test", idle_regex=r"\$")
        ctrl._render_buffer = []

        context = ctrl.get_context()
        assert context == ""


class TestControllerInterrupt:
    """Tests for controller interrupt functionality."""

    def test_interrupt_does_nothing_when_not_running(self):
        """interrupt should do nothing when not running."""
        ctrl = TerminalController(command="echo test", idle_regex=r"\$")
        ctrl.running = False

        # Should not raise
        ctrl.interrupt()

    def test_interrupt_does_nothing_when_no_process(self):
        """interrupt should do nothing when process is None."""
        ctrl = TerminalController(command="echo test", idle_regex=r"\$")
        ctrl.running = True
        ctrl.process = None

        # Should not raise
        ctrl.interrupt()


class TestControllerInitialization:
    """Tests for controller initialization."""

    def test_default_env_uses_system_environ(self):
        """Default env should be a copy of os.environ."""
        ctrl = TerminalController(command="echo test", idle_regex=r"\$")
        # env should be a dict (copy of os.environ)
        assert isinstance(ctrl.env, dict)

    def test_custom_env_is_used(self):
        """Custom env should be stored."""
        custom_env = {"FOO": "bar"}
        ctrl = TerminalController(command="echo test", idle_regex=r"\$", env=custom_env)
        assert ctrl.env == custom_env

    def test_idle_regex_compiled(self):
        """idle_regex should be compiled as bytes pattern."""
        ctrl = TerminalController(command="echo test", idle_regex=r"\$")
        # Should be a compiled regex
        assert hasattr(ctrl.idle_regex, "search")


class TestInvalidRegexHandling:
    """Tests for handling invalid regex patterns in idle detection."""

    def test_invalid_regex_pattern_fallback_to_timeout(self):
        """Invalid regex pattern should fall back to timeout without crashing."""
        # Use an invalid regex pattern (unclosed bracket)
        ctrl = TerminalController(
            command="echo test",
            idle_detection={
                "strategy": "pattern",
                "pattern": "[invalid(regex",
                "timeout": 1.5,
            },
        )
        # Should not raise, idle_regex should be None
        assert ctrl.idle_regex is None
        # Should fall back to timeout-based detection
        assert ctrl._output_idle_threshold == 1.5

    def test_hybrid_mode_with_invalid_regex_fallback(self):
        """Hybrid mode with invalid regex should fall back to timeout."""
        ctrl = TerminalController(
            command="echo test",
            idle_detection={
                "strategy": "hybrid",
                "pattern": "[invalid(",
                "timeout": 2.0,
            },
        )
        # Should not raise
        assert ctrl.idle_regex is None
        assert ctrl._pattern_detected is False
        # Should use timeout as fallback
        assert ctrl._output_idle_threshold == 2.0

    def test_pattern_detected_flag_reset_on_error(self):
        """_pattern_detected flag should be reset to False on regex error."""
        # First, create a valid pattern to set the flag
        ctrl = TerminalController(
            command="echo test",
            idle_detection={
                "strategy": "hybrid",
                "pattern": r"\$",
                "timeout": 1.5,
            },
        )
        # Verify pattern was compiled
        assert ctrl.idle_regex is not None
        assert ctrl._pattern_detected is False

    def test_invalid_regex_in_hybrid_strategy(self):
        """Invalid regex in hybrid strategy should safely fall back to timeout."""
        ctrl = TerminalController(
            command="echo test",
            idle_detection={
                "strategy": "hybrid",
                "pattern": "(?P<invalid",  # Invalid named group
                "timeout": 1.5,
            },
        )
        # Should not crash
        assert ctrl.idle_regex is None
        assert ctrl._pattern_detected is False
        assert ctrl._output_idle_threshold == 1.5

    def test_special_pattern_bracketed_paste_mode_valid(self):
        """BRACKETED_PASTE_MODE special pattern should compile successfully."""
        ctrl = TerminalController(
            command="claude",
            idle_detection={
                "strategy": "pattern",
                "pattern": "BRACKETED_PASTE_MODE",
                "timeout": 0.5,
            },
        )
        # Should compile without error
        assert ctrl.idle_regex is not None
        # Should match the BRACKETED_PASTE_MODE escape sequence
        assert ctrl.idle_regex.search(b"\x1b[?2004h") is not None

    def test_timeout_default_on_pattern_error(self):
        """Should use default timeout when pattern compilation fails."""
        ctrl = TerminalController(
            command="echo test",
            idle_detection={
                "strategy": "pattern",
                "pattern": "*invalid",  # * without preceding character
            },
        )
        # Should have default timeout
        assert ctrl._output_idle_threshold == 1.5  # Default
        assert ctrl.idle_regex is None
