"""Tests for TerminalController identity instruction functionality."""

import pytest
import threading
import time
from unittest.mock import Mock, patch, MagicMock
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
            submit_seq="\r"
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

        assert controller.status == "IDLE"

    def test_identity_sent_on_first_idle(self, controller):
        """Identity instruction should be sent on first IDLE detection."""
        controller.running = True
        controller.master_fd = 1  # Mock fd
        controller.output_buffer = b"prompt $"

        # Track if _send_identity_instruction was called
        send_called = threading.Event()
        original_send = controller._send_identity_instruction

        def mock_send():
            send_called.set()

        controller._send_identity_instruction = mock_send

        # Trigger idle detection
        controller._check_idle_state(b"$")

        # Wait for the thread to be spawned
        time.sleep(0.1)

        assert controller._identity_sent is True
        assert send_called.is_set()

    def test_identity_sent_only_once(self, controller):
        """Identity instruction should only be sent once."""
        controller.running = True
        controller.master_fd = 1
        controller.output_buffer = b"prompt $"

        call_count = 0

        def mock_send():
            nonlocal call_count
            call_count += 1

        controller._send_identity_instruction = mock_send

        # First IDLE
        controller._check_idle_state(b"$")
        time.sleep(0.1)

        # Second IDLE (should not send again)
        controller.status = "BUSY"
        controller.output_buffer = b"more output $"
        controller._check_idle_state(b"$")
        time.sleep(0.1)

        assert call_count == 1

    def test_identity_instruction_content(self, controller, mock_registry):
        """Identity instruction should contain correct bootstrap content."""
        controller.running = True
        controller.master_fd = 1

        written_data = []

        def mock_write(data, submit_seq=None):
            written_data.append(data)

        controller.write = mock_write

        # Call directly to test content
        controller._send_identity_instruction()

        assert len(written_data) == 1
        instruction = written_data[0]

        # Check key content - minimal bootstrap with commands
        assert "synapse-claude-8100" in instruction
        assert "SYNAPSE" in instruction
        assert "8100" in instruction
        assert "a2a.py send" in instruction
        assert "a2a.py list" in instruction

    def test_identity_not_sent_without_agent_id(self, mock_registry):
        """Identity should not be sent if agent_id is None."""
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$",
            registry=mock_registry,
            agent_id=None,
            agent_type="claude"
        )
        ctrl.running = True
        ctrl.master_fd = 1
        ctrl.output_buffer = b"prompt $"

        ctrl.write = Mock()
        ctrl._check_idle_state(b"$")

        time.sleep(0.2)

        # write should not have been called
        ctrl.write.assert_not_called()


class TestOutputIdleDetection:
    """Tests for output idle detection mechanism."""

    def test_last_output_time_initialized_none(self):
        """Last output time should be None initially."""
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$",
            agent_id="synapse-claude-8100",
            agent_type="claude"
        )
        assert ctrl._last_output_time is None

    def test_output_idle_threshold_default(self):
        """Default output idle threshold should be 1.5 seconds."""
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$"
        )
        assert ctrl._output_idle_threshold == 1.5

    def test_startup_delay_from_config(self):
        """Startup delay should be configurable."""
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$",
            startup_delay=8
        )
        assert ctrl._startup_delay == 8

    def test_startup_delay_default(self):
        """Default startup delay should be 3 seconds."""
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$"
        )
        assert ctrl._startup_delay == 3


class TestSubmitSequence:
    """Tests for submit sequence configuration."""

    def test_default_submit_seq(self):
        """Default submit sequence should be newline."""
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$"
        )
        assert ctrl._submit_seq == "\n"

    def test_custom_submit_seq(self):
        """Custom submit sequence should be stored."""
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$",
            submit_seq="\r"
        )
        assert ctrl._submit_seq == "\r"

    def test_submit_seq_used_in_identity(self):
        """Identity instruction should use configured submit_seq."""
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$",
            agent_id="synapse-claude-8100",
            agent_type="claude",
            submit_seq="\r"
        )
        ctrl.running = True
        ctrl.master_fd = 1

        captured_submit_seq = []

        def mock_write(data, submit_seq=None):
            captured_submit_seq.append(submit_seq)

        ctrl.write = mock_write
        ctrl._send_identity_instruction()

        assert len(captured_submit_seq) == 1
        assert captured_submit_seq[0] == "\r"


class TestInterAgentMessageWrite:
    """Tests for inter-agent message writing."""

    def test_write_in_interactive_mode_with_submit_seq(self):
        """Write should send data and submit_seq separately in interactive mode."""
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$",
            agent_id="synapse-claude-8100",
            agent_type="claude",
            submit_seq="\r"
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

            # Should have two writes: data and submit_seq
            assert len(written_data) == 2
            assert written_data[0] == (1, b"test message")
            assert written_data[1] == (1, b"\r")
        finally:
            os.write = original_write

    def test_write_in_non_interactive_mode_combines_data(self):
        """Write should combine data and submit_seq in non-interactive mode."""
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$"
        )
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

            # Should have one write with combined data
            assert len(written_data) == 1
            assert written_data[0] == (1, b"test message\n")
        finally:
            os.write = original_write

    def test_write_fails_when_not_running(self):
        """Write should do nothing when controller is not running."""
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$"
        )
        ctrl.running = False
        ctrl.master_fd = 1

        # Should not raise, just return
        ctrl.write("test", submit_seq="\n")

    def test_write_raises_when_master_fd_none(self):
        """Write should raise when master_fd is None."""
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$"
        )
        ctrl.running = True
        ctrl.master_fd = None

        with pytest.raises(ValueError) as excinfo:
            ctrl.write("test", submit_seq="\n")
        assert "master_fd is None" in str(excinfo.value)

    def test_write_sets_status_to_busy(self):
        """Write should set status to BUSY."""
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$"
        )
        ctrl.running = True
        ctrl.interactive = False
        ctrl.master_fd = 1
        ctrl.status = "IDLE"

        import os
        original_write = os.write
        os.write = lambda fd, data: len(data)

        try:
            ctrl.write("test", submit_seq="\n")
            assert ctrl.status == "BUSY"
        finally:
            os.write = original_write

    def test_write_without_submit_seq(self):
        """Write should work without submit_seq."""
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$"
        )
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
        """Controller should start with STARTING status."""
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$"
        )
        assert ctrl.status == "STARTING"

    def test_status_changes_to_idle_on_pattern_match(self):
        """Status should change to IDLE when idle_regex matches."""
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$"
        )
        ctrl.running = True
        ctrl.master_fd = 1
        ctrl.output_buffer = b"some output $"
        ctrl.write = Mock()

        ctrl._check_idle_state(b"$")
        assert ctrl.status == "IDLE"

    def test_status_changes_to_busy_on_no_match(self):
        """Status should change to BUSY when idle_regex doesn't match."""
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$$"  # Must end with $
        )
        ctrl.running = True
        ctrl.master_fd = 1
        ctrl.output_buffer = b"some output without prompt"
        ctrl.status = "IDLE"

        ctrl._check_idle_state(b"no prompt here")
        assert ctrl.status == "BUSY"


class TestControllerOutputBuffer:
    """Tests for output buffer management."""

    def test_output_buffer_initialized_empty(self):
        """Output buffer should be empty initially."""
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$"
        )
        assert ctrl.output_buffer == b""

    def test_get_context_returns_decoded_buffer(self):
        """get_context should return decoded output buffer."""
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$"
        )
        ctrl.output_buffer = b"Hello World"

        context = ctrl.get_context()
        assert context == "Hello World"

    def test_get_context_handles_unicode(self):
        """get_context should handle unicode properly."""
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$"
        )
        ctrl.output_buffer = "こんにちは".encode('utf-8')

        context = ctrl.get_context()
        assert context == "こんにちは"

    def test_get_context_handles_invalid_bytes(self):
        """get_context should handle invalid bytes gracefully."""
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$"
        )
        ctrl.output_buffer = b"valid \xff invalid"

        # Should not raise, uses errors='replace'
        context = ctrl.get_context()
        assert "valid" in context


class TestControllerInterrupt:
    """Tests for controller interrupt functionality."""

    def test_interrupt_does_nothing_when_not_running(self):
        """interrupt should do nothing when not running."""
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$"
        )
        ctrl.running = False

        # Should not raise
        ctrl.interrupt()

    def test_interrupt_does_nothing_when_no_process(self):
        """interrupt should do nothing when process is None."""
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$"
        )
        ctrl.running = True
        ctrl.process = None

        # Should not raise
        ctrl.interrupt()


class TestControllerInitialization:
    """Tests for controller initialization."""

    def test_default_env_uses_system_environ(self):
        """Default env should be a copy of os.environ."""
        import os
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$"
        )
        # env should be a dict (copy of os.environ)
        assert isinstance(ctrl.env, dict)

    def test_custom_env_is_used(self):
        """Custom env should be stored."""
        custom_env = {"FOO": "bar"}
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$",
            env=custom_env
        )
        assert ctrl.env == custom_env

    def test_idle_regex_compiled(self):
        """idle_regex should be compiled as bytes pattern."""
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$"
        )
        # Should be a compiled regex
        assert hasattr(ctrl.idle_regex, 'search')
