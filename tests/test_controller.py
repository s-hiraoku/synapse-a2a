"""Tests for TerminalController identity instruction functionality."""

import threading
import time
from unittest.mock import Mock, patch

import pytest

from synapse.config import WRITE_PROCESSING_DELAY
from synapse.controller import TerminalController
from synapse.registry import AgentRegistry
from tests.helpers import read_stored_instruction


def _wait_until(predicate, timeout: float = 1.0, interval: float = 0.01) -> bool:
    """Poll until predicate() is truthy or timeout expires."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return bool(predicate())


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

        assert _wait_until(send_called.is_set)

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
        assert _wait_until(lambda: call_count[0] == 1)
        assert controller._identity_sent is True
        assert call_count[0] == 1

        # Manually set back to BUSY to simulate activity
        controller.status = "BUSY"
        controller.output_buffer = b"more output $"

        # Second IDLE - should NOT call again
        controller._check_idle_state(b"$")
        assert _wait_until(lambda: controller.status == "READY")
        assert controller._identity_sent is True
        assert controller.status == "READY"
        assert call_count[0] == 1  # Still 1, not 2

    def _send_identity_and_capture(self, controller, monkeypatch, tmp_path=None):
        """Send identity instruction and return the raw PTY message written."""
        monkeypatch.setattr("synapse.controller.POST_WRITE_IDLE_DELAY", 0)
        controller.running = True
        controller.master_fd = 1

        written_data = []

        def mock_write(data, submit_seq=None):
            written_data.append(data)

        controller.write = mock_write

        # Reset singleton and use a fresh store with a reliable temp directory
        # to avoid test pollution from other tests' stale singletons.
        import synapse.long_message

        synapse.long_message._store_instance = None

        store_patch = {}
        if tmp_path is not None:
            msg_dir = tmp_path / "messages"
            store_patch["SYNAPSE_LONG_MESSAGE_DIR"] = str(msg_dir)

        with (
            patch("synapse.controller.get_settings") as mock_get_settings,
            patch.dict("os.environ", store_patch),
        ):
            mock_settings = Mock()
            mock_settings.get_instruction_file_paths.return_value = [
                ".synapse/default.md",
            ]
            mock_get_settings.return_value = mock_settings

            controller._send_identity_instruction()

        # Clean up singleton so it doesn't leak to other tests
        synapse.long_message._store_instance = None

        assert len(written_data) == 1
        return written_data[0]

    def test_identity_instruction_content(
        self, controller, mock_registry, monkeypatch, tmp_path
    ):
        """Identity instruction should use file storage and send short reference.

        The identity message body always exceeds the LongMessageStore threshold
        (200 chars), so it should be stored in a file and only a short reference
        sent to the PTY.  The full content is readable from the stored file.
        """
        pty_message = self._send_identity_and_capture(controller, monkeypatch, tmp_path)

        # PTY message should be a file reference wrapped in A2A prefix
        assert pty_message.startswith("A2A: ")
        assert "[LONG MESSAGE - FILE ATTACHED]" in pty_message
        assert "Please read this file" in pty_message

        # The stored file should contain the full identity message
        stored_content = read_stored_instruction(pty_message)
        assert "synapse-claude-8100" in stored_content
        assert "8100" in stored_content
        assert ".synapse/default.md" in stored_content
        assert "$SYNAPSE_AGENT_ID" in stored_content
        assert "--from" in stored_content

    def test_identity_pty_message_is_short(
        self, controller, mock_registry, monkeypatch, tmp_path
    ):
        """PTY message for identity should be short enough for TUI paste.

        The file reference message sent to the PTY must stay well under the
        200-char threshold that Ink TUI uses for its shortcut display.
        """
        pty_message = self._send_identity_and_capture(controller, monkeypatch, tmp_path)

        # The file reference (A2A prefix + path + instructions) is typically
        # ~200-250 chars depending on the temp directory path length.
        # This must stay well under the original identity message size (~500+).
        assert len(pty_message) < 300, (
            f"PTY message too long ({len(pty_message)} chars), "
            f"should use file storage for short reference"
        )

    def test_mcp_bootstrap_message_is_inline_and_minimal(
        self, mock_registry, monkeypatch
    ):
        """MCP bootstrap should send a short inline bootstrap message."""
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$",
            registry=mock_registry,
            agent_id="synapse-codex-8120",
            agent_type="codex",
            submit_seq="\r",
            mcp_bootstrap=True,
            port=8120,
        )
        ctrl.running = True
        ctrl.master_fd = 1

        written_data = []

        def mock_write(data, submit_seq=None):
            written_data.append((data, submit_seq))

        ctrl.write = mock_write
        monkeypatch.setattr("synapse.controller.POST_WRITE_IDLE_DELAY", 0)

        ctrl._send_identity_instruction()

        assert len(written_data) == 1
        pty_message, submit_seq = written_data[0]
        assert submit_seq == "\r"
        assert pty_message.startswith("A2A: [SYNAPSE MCP BOOTSTRAP]")
        assert "synapse-codex-8120" in pty_message
        assert "8120" in pty_message
        assert "synapse://instructions/default" in pty_message
        assert "bootstrap_agent()" in pty_message
        assert "[LONG MESSAGE - FILE ATTACHED]" not in pty_message

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

        assert _wait_until(lambda: ctrl.status == "READY")

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

    @pytest.fixture
    def mock_os_write(self):
        """Patch os.write in the controller module and collect written data.

        Yields a list of (fd, data) tuples captured from os.write calls.
        """
        written_data: list[tuple[int, bytes]] = []

        def _mock(fd, data):
            written_data.append((fd, data))
            return len(data)

        with patch("synapse.controller.os.write", side_effect=_mock):
            yield written_data

    def test_write_sends_data_with_submit_seq(self, mock_os_write):
        """Write should send data then submit_seq as separate writes."""
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

        with patch("synapse.controller.time.sleep"):
            ctrl.write("test message", submit_seq="\r")

        # Split write: data first, then submit_seq
        assert len(mock_os_write) == 2
        assert mock_os_write[0] == (1, b"test message")
        assert mock_os_write[1] == (1, b"\r")

    def test_write_with_bracketed_paste_mode_idle_regex(self, mock_os_write):
        """Write should send data then submit_seq separately with BRACKETED_PASTE_MODE."""
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

        with patch("synapse.controller.time.sleep"):
            ctrl.write("test message", submit_seq="\r")

        # Split write: data first, then submit_seq
        assert len(mock_os_write) == 2
        assert mock_os_write[0] == (1, b"test message")
        assert mock_os_write[1] == (1, b"\r")

    def test_write_in_non_interactive_mode(self, mock_os_write):
        """Write should send data then submit_seq separately in non-interactive mode."""
        ctrl = TerminalController(command="echo test", idle_regex=r"\$")
        ctrl.running = True
        ctrl.interactive = False
        ctrl.master_fd = 1

        with patch("synapse.controller.time.sleep"):
            ctrl.write("test message", submit_seq="\n")

        # Split write: data first, then submit_seq
        assert len(mock_os_write) == 2
        assert mock_os_write[0] == (1, b"test message")
        assert mock_os_write[1] == (1, b"\n")

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

        with (
            patch(
                "synapse.controller.os.write", side_effect=lambda fd, data: len(data)
            ),
            patch("synapse.controller.time.sleep"),
        ):
            ctrl.write("test", submit_seq="\n")
        assert ctrl.status == "PROCESSING"

    def test_write_without_submit_seq(self, mock_os_write):
        """Write should work without submit_seq."""
        ctrl = TerminalController(command="echo test", idle_regex=r"\$")
        ctrl.running = True
        ctrl.interactive = False
        ctrl.master_fd = 1

        ctrl.write("test message")  # No submit_seq
        assert len(mock_os_write) == 1
        assert mock_os_write[0] == (1, b"test message")

    # --- Partial write retry tests (Bug 3: os.write() short write handling) ---

    def test_write_retries_on_partial_write(self):
        """Write should retry when os.write returns fewer bytes than requested.

        PTY file descriptors can perform short writes (return less than
        the full buffer). The write loop must retry with the remaining
        bytes until everything is written.
        """
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$",
            agent_id="synapse-claude-8100",
            agent_type="claude",
            submit_seq="\r",
        )
        ctrl.running = True
        ctrl.master_fd = 1

        write_calls: list[tuple[int, bytes]] = []
        data_bytes = b"test message"
        half = len(data_bytes) // 2

        def mock_partial_write(fd, data):
            write_calls.append((fd, data))
            # First call: write only half of data, rest: write fully
            if len(write_calls) == 1:
                return half
            return len(data)

        with (
            patch("synapse.controller.os.write", side_effect=mock_partial_write),
            patch("synapse.controller.time.sleep"),
        ):
            result = ctrl.write("test message", submit_seq="\r")

        assert result is True
        # 3 calls: data-half, data-rest, submit_seq
        assert len(write_calls) == 3
        assert write_calls[0] == (1, data_bytes)
        assert write_calls[1] == (1, data_bytes[half:])
        assert write_calls[2] == (1, b"\r")

    def test_write_raises_on_zero_write(self):
        """Write should raise OSError if os.write returns 0 (master fd closed)."""
        ctrl = TerminalController(command="echo test", idle_regex=r"\$")
        ctrl.running = True
        ctrl.master_fd = 1

        with patch("synapse.controller.os.write", return_value=0):
            with pytest.raises(OSError, match="os.write returned 0"):
                ctrl.write("test message", submit_seq="\r")

    def test_write_complete_returns_true(self):
        """Write should return True when all bytes are written successfully."""
        ctrl = TerminalController(command="echo test", idle_regex=r"\$")
        ctrl.running = True
        ctrl.master_fd = 1

        with (
            patch(
                "synapse.controller.os.write", side_effect=lambda fd, data: len(data)
            ),
            patch("synapse.controller.time.sleep"),
        ):
            result = ctrl.write("hello", submit_seq="\n")
        assert result is True

    # --- Split write tests (Bug 4: bracketed paste mode requires separate writes) ---

    def test_write_split_data_then_submit_seq(self, mock_os_write):
        """Write with submit_seq should use two os.write calls (split).

        Bracketed paste mode wraps each write in paste boundaries.  If data
        and CR are in the same write, CR becomes a literal newline inside
        the paste boundary.  Splitting ensures CR arrives as a keypress.
        """
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$",
            agent_id="synapse-copilot-8140",
            agent_type="copilot",
            submit_seq="\r",
        )
        ctrl.running = True
        ctrl.interactive = True
        ctrl.master_fd = 1

        with patch("synapse.controller.time.sleep"):
            ctrl.write("test message", submit_seq="\r")

        # Must be exactly TWO write calls (split)
        assert len(mock_os_write) == 2
        assert mock_os_write[0] == (1, b"test message")
        assert mock_os_write[1] == (1, b"\r")

    def test_write_split_preserves_content(self, mock_os_write):
        """Split write should preserve the full data and submit_seq content."""
        ctrl = TerminalController(command="echo test", idle_regex=r"\$")
        ctrl.running = True
        ctrl.interactive = True
        ctrl.master_fd = 1

        with patch("synapse.controller.time.sleep"):
            ctrl.write("A2A: [REPLY EXPECTED] Review this code", submit_seq="\r")

        assert len(mock_os_write) == 2
        assert mock_os_write[0] == (
            1,
            b"A2A: [REPLY EXPECTED] Review this code",
        )
        assert mock_os_write[1] == (1, b"\r")

    # --- Delay and ordering tests (Bug 4: bracketed paste mode) ---

    def test_write_delay_between_data_and_submit_seq(self):
        """Write should call time.sleep(WRITE_PROCESSING_DELAY) between data and submit_seq.

        The delay lets the paste boundary close before the submit sequence
        arrives, so the terminal treats CR as a keypress, not a literal char.
        """
        ctrl = TerminalController(command="echo test", idle_regex=r"\$")
        ctrl.running = True
        ctrl.master_fd = 1

        with (
            patch(
                "synapse.controller.os.write", side_effect=lambda fd, data: len(data)
            ),
            patch("synapse.controller.time.sleep") as mock_sleep,
        ):
            ctrl.write("hello", submit_seq="\r")
            mock_sleep.assert_called_once_with(WRITE_PROCESSING_DELAY)

    def test_write_no_delay_without_submit_seq(self):
        """Write without submit_seq should not call time.sleep."""
        ctrl = TerminalController(command="echo test", idle_regex=r"\$")
        ctrl.running = True
        ctrl.master_fd = 1

        with (
            patch(
                "synapse.controller.os.write", side_effect=lambda fd, data: len(data)
            ),
            patch("synapse.controller.time.sleep") as mock_sleep,
        ):
            ctrl.write("hello")
            mock_sleep.assert_not_called()

    def test_write_split_order(self):
        """Data must be written before submit_seq (correct ordering)."""
        ctrl = TerminalController(command="echo test", idle_regex=r"\$")
        ctrl.running = True
        ctrl.master_fd = 1

        call_log: list[tuple[str, ...]] = []

        def mock_write(fd, data):
            call_log.append(("write", data))
            return len(data)

        with (
            patch("synapse.controller.os.write", side_effect=mock_write),
            patch("synapse.controller.time.sleep") as mock_sleep,
        ):
            mock_sleep.side_effect = lambda _: call_log.append(("sleep",))
            ctrl.write("data", submit_seq="\r")

        # Order: write data → sleep → write submit_seq
        assert call_log == [
            ("write", b"data"),
            ("sleep",),
            ("write", b"\r"),
        ]

    # --- Per-profile write_delay tests (Bug 5: configurable delay) ---

    def test_write_uses_custom_write_delay(self):
        """Write should use the custom write_delay when specified.

        Profiles like Claude Code may need 0.5s while others need different
        values.  The per-instance write_delay overrides the global constant.
        """
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$",
            write_delay=1.0,
        )
        ctrl.running = True
        ctrl.master_fd = 1

        with (
            patch(
                "synapse.controller.os.write", side_effect=lambda fd, data: len(data)
            ),
            patch("synapse.controller.time.sleep") as mock_sleep,
        ):
            ctrl.write("hello", submit_seq="\r")
            mock_sleep.assert_called_once_with(1.0)

    def test_write_skips_delay_when_zero(self):
        """Write should skip time.sleep entirely when write_delay is 0.

        Copilot CLI may work better with no delay between data and submit_seq
        because its Ink TUI closes paste boundaries faster.
        """
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$",
            write_delay=0,
        )
        ctrl.running = True
        ctrl.master_fd = 1

        with (
            patch(
                "synapse.controller.os.write", side_effect=lambda fd, data: len(data)
            ),
            patch("synapse.controller.time.sleep") as mock_sleep,
        ):
            ctrl.write("hello", submit_seq="\r")
            mock_sleep.assert_not_called()

    def test_write_default_delay(self):
        """Write should use WRITE_PROCESSING_DELAY when write_delay is not specified."""
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$",
            # write_delay not specified — should default to WRITE_PROCESSING_DELAY
        )
        ctrl.running = True
        ctrl.master_fd = 1

        with (
            patch(
                "synapse.controller.os.write", side_effect=lambda fd, data: len(data)
            ),
            patch("synapse.controller.time.sleep") as mock_sleep,
        ):
            ctrl.write("hello", submit_seq="\r")
            mock_sleep.assert_called_once_with(WRITE_PROCESSING_DELAY)

    def test_write_uses_small_delay(self):
        """Write should sleep for the configured small delay (e.g., 0.05s).

        Copilot CLI needs a small but non-zero delay so that the PTY paste
        boundary has time to close before the submit sequence (CR) is sent.
        """
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$",
            write_delay=0.05,
        )
        ctrl.running = True
        ctrl.master_fd = 1

        with (
            patch(
                "synapse.controller.os.write", side_effect=lambda fd, data: len(data)
            ),
            patch("synapse.controller.time.sleep") as mock_sleep,
        ):
            ctrl.write("hello", submit_seq="\r")
            mock_sleep.assert_called_once_with(0.05)

    def test_write_delay_string_coerced_to_float(self):
        """write_delay given as a string (e.g. YAML quoted value) should be
        coerced to float automatically."""
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$",
            write_delay="0.3",
        )
        assert ctrl._write_delay == 0.3

    def test_write_delay_negative_raises(self):
        """Negative write_delay should raise ValueError."""
        with pytest.raises(ValueError, match="write_delay must be.*non-negative"):
            TerminalController(
                command="echo test",
                idle_regex=r"\$",
                write_delay=-1,
            )

    def test_write_delay_negative_string_raises(self):
        """Negative write_delay as string should also raise ValueError."""
        with pytest.raises(ValueError, match="write_delay must be.*non-negative"):
            TerminalController(
                command="echo test",
                idle_regex=r"\$",
                write_delay="-0.5",
            )

    def test_write_delay_non_numeric_string_raises(self):
        """Non-numeric write_delay string should raise ValueError."""
        with pytest.raises(ValueError, match="write_delay must be"):
            TerminalController(
                command="echo test",
                idle_regex=r"\$",
                write_delay="fast",
            )

    def test_submit_retry_delay_sends_submit_twice(self):
        """submit_retry_delay should cause submit_seq to be sent twice.

        Copilot CLI v0.0.300+ needs two CRs: the first flushes the Ink
        async paste buffer and the second triggers the actual submit
        after React re-renders.
        """
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$",
            write_delay=0.5,
            submit_retry_delay=0.05,
        )
        ctrl.running = True
        ctrl.master_fd = 1

        writes: list[bytes] = []
        sleeps: list[float] = []
        with (
            patch(
                "synapse.controller.os.write",
                side_effect=lambda fd, data: (writes.append(data), len(data))[1],
            ),
            patch(
                "synapse.controller.time.sleep",
                side_effect=lambda t: sleeps.append(t),
            ),
        ):
            ctrl.write("hello", submit_seq="\r")

        # Should write: data, sleep(0.5), CR, sleep(0.05), CR
        assert writes == [b"hello", b"\r", b"\r"]
        assert sleeps == [0.5, 0.05]

    def test_submit_retry_delay_none_sends_once(self):
        """Without submit_retry_delay, submit_seq should be sent once."""
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$",
            write_delay=0.05,
        )
        ctrl.running = True
        ctrl.master_fd = 1

        writes: list[bytes] = []
        with (
            patch(
                "synapse.controller.os.write",
                side_effect=lambda fd, data: (writes.append(data), len(data))[1],
            ),
            patch("synapse.controller.time.sleep"),
        ):
            ctrl.write("hello", submit_seq="\r")

        assert writes == [b"hello", b"\r"]

    def test_submit_retry_delay_negative_raises(self):
        """Negative submit_retry_delay should raise ValueError."""
        with pytest.raises(
            ValueError, match="submit_retry_delay must be.*non-negative"
        ):
            TerminalController(
                command="echo test",
                idle_regex=r"\$",
                submit_retry_delay=-0.1,
            )

    def test_submit_retry_delay_non_numeric_raises(self):
        """Non-numeric submit_retry_delay should raise ValueError."""
        with pytest.raises(ValueError, match="submit_retry_delay must be numeric"):
            TerminalController(
                command="echo test",
                idle_regex=r"\$",
                submit_retry_delay="fast",
            )

    def test_submit_retry_delay_string_numeric_accepts(self):
        """Numeric string submit_retry_delay should be coerced to float."""
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$",
            submit_retry_delay="0.05",
        )
        assert ctrl._submit_retry_delay == 0.05

    def test_submit_confirmation_retries_for_copilot_when_text_remains(self):
        """Copilot should send extra CRs when injected text still appears unsubmitted."""
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$",
            agent_type="copilot",
            write_delay=0.5,
            submit_retry_delay=0.15,
            submit_confirm_timeout=0.2,
            submit_confirm_poll_interval=0.05,
            submit_confirm_retries=2,
        )
        ctrl.running = True
        ctrl.master_fd = 1
        ctrl.status = "READY"

        writes: list[bytes] = []
        sleeps: list[float] = []

        poll_state = {"count": 0}

        def fake_get_context() -> str:
            poll_state["count"] += 1
            if poll_state["count"] == 1:
                return ""
            return "A2A: hello"

        ctrl.get_context = fake_get_context  # type: ignore[method-assign]

        with (
            patch(
                "synapse.controller.os.write",
                side_effect=lambda fd, data: (writes.append(data), len(data))[1],
            ),
            patch(
                "synapse.controller.time.sleep",
                side_effect=lambda t: sleeps.append(t),
            ),
        ):
            result = ctrl.write("hello", submit_seq="\r")

        assert result is True
        assert writes == [b"hello", b"\r", b"\r", b"\r", b"\r"]
        assert sleeps[:1] == [0.5]
        # Filter out 0.1s sleeps that may leak from daemon threads in other
        # tests (master_fd wait loop).  Only the poll_interval sleeps matter.
        confirm_sleeps = [s for s in sleeps[1:] if s != 0.1]
        assert confirm_sleeps == [0.05] * 12

    def test_submit_confirmation_stops_when_copilot_status_advances(self):
        """Copilot should stop retrying once status leaves READY."""
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$",
            agent_type="copilot",
            write_delay=0.5,
            submit_retry_delay=0.15,
            submit_confirm_timeout=0.2,
            submit_confirm_poll_interval=0.05,
            submit_confirm_retries=2,
        )
        ctrl.running = True
        ctrl.master_fd = 1
        ctrl.status = "READY"

        writes: list[bytes] = []
        sleeps: list[float] = []
        poll_count = {"value": 0}

        def fake_get_context() -> str:
            poll_count["value"] += 1
            if poll_count["value"] == 1:
                return ""
            if poll_count["value"] >= 2:
                ctrl.status = "PROCESSING"
            return "Processing..."

        ctrl.get_context = fake_get_context  # type: ignore[method-assign]

        with (
            patch(
                "synapse.controller.os.write",
                side_effect=lambda fd, data: (writes.append(data), len(data))[1],
            ),
            patch(
                "synapse.controller.time.sleep",
                side_effect=lambda t: sleeps.append(t),
            ),
        ):
            result = ctrl.write("hello", submit_seq="\r")

        assert result is True
        assert writes == [b"hello", b"\r"]
        assert sleeps[:1] == [0.5]
        assert sleeps[1:] == [0.1]

    def test_submit_confirmation_retries_when_waiting_state_does_not_advance(self):
        """Copilot should not treat WAITING->WAITING as confirmation by itself."""
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$",
            agent_type="copilot",
            write_delay=0.5,
            submit_retry_delay=0.15,
            submit_confirm_timeout=0.2,
            submit_confirm_poll_interval=0.05,
            submit_confirm_retries=2,
        )
        ctrl.running = True
        ctrl.master_fd = 1
        ctrl.status = "WAITING"
        ctrl.get_context = lambda: "A2A: hello"  # type: ignore[method-assign]

        writes: list[bytes] = []
        sleeps: list[float] = []

        with (
            patch(
                "synapse.controller.os.write",
                side_effect=lambda fd, data: (writes.append(data), len(data))[1],
            ),
            patch(
                "synapse.controller.time.sleep",
                side_effect=lambda t: sleeps.append(t),
            ),
        ):
            result = ctrl.write("hello", submit_seq="\r")

        assert result is True
        assert writes == [b"hello", b"\r", b"\r", b"\r", b"\r"]
        assert sleeps[:1] == [0.5]

    def test_submit_confirmation_accepts_waiting_when_text_disappears(self):
        """Copilot WAITING->WAITING is confirmed when the prompt text is gone."""
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$",
            agent_type="copilot",
            write_delay=0.5,
            submit_retry_delay=0.15,
            submit_confirm_timeout=0.2,
            submit_confirm_poll_interval=0.05,
            submit_confirm_retries=2,
        )
        ctrl.running = True
        ctrl.master_fd = 1
        ctrl.status = "WAITING"
        ctrl.get_context = lambda: "Processing..."  # type: ignore[method-assign]

        writes: list[bytes] = []
        sleeps: list[float] = []

        with (
            patch(
                "synapse.controller.os.write",
                side_effect=lambda fd, data: (writes.append(data), len(data))[1],
            ),
            patch(
                "synapse.controller.time.sleep",
                side_effect=lambda t: sleeps.append(t),
            ),
        ):
            result = ctrl.write("hello", submit_seq="\r")

        assert result is True
        assert writes == [b"hello", b"\r"]

    def test_copilot_paste_echo_settle_delay_when_echo_detected(self):
        """Copilot should add settle delay after paste echo is detected."""
        from synapse.controller import _COPILOT_PASTE_ECHO_SETTLE

        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$",
            agent_type="copilot",
            write_delay=0.5,
            bracketed_paste=True,
        )

        # Simulate: first call returns pre-paste, second call returns changed
        contexts = iter(["pre-paste context", "post-paste context with echo"])
        sleeps: list[float] = []
        mono_time = [0.0]

        with (
            patch.object(
                ctrl,
                "get_context",
                side_effect=lambda: next(contexts, "post-paste context with echo"),
            ),
            patch(
                "synapse.controller.time.sleep",
                side_effect=lambda t: sleeps.append(t),
            ),
            patch(
                "synapse.controller.time.monotonic",
                side_effect=lambda: (
                    mono_time.__setitem__(0, mono_time[0] + 0.01) or mono_time[0]
                ),
            ),
        ):
            ctrl._wait_for_copilot_paste_echo("pre-paste context")

        # The settle delay should be the last sleep call
        assert _COPILOT_PASTE_ECHO_SETTLE in sleeps
        assert sleeps[-1] == _COPILOT_PASTE_ECHO_SETTLE

    def test_copilot_paste_echo_fallback_to_write_delay(self):
        """Copilot should fall back to write_delay when no echo is detected."""
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$",
            agent_type="copilot",
            write_delay=0.5,
            bracketed_paste=True,
        )

        # Simulate: context never changes (no echo)
        sleeps: list[float] = []
        mono_time = [0.0]

        def advance_time(t: float) -> None:
            mono_time[0] += t
            sleeps.append(t)

        with (
            patch.object(
                ctrl,
                "get_context",
                return_value="same context always",
            ),
            patch(
                "synapse.controller.time.sleep",
                side_effect=advance_time,
            ),
            patch(
                "synapse.controller.time.monotonic",
                side_effect=lambda: mono_time[0],
            ),
        ):
            ctrl._wait_for_copilot_paste_echo("same context always")

        # Should fall back to write_delay (0.5)
        assert 0.5 in sleeps
        assert sleeps[-1] == 0.5

    def test_submit_confirmation_disabled_for_non_copilot(self):
        """Non-Copilot profiles should keep existing write behavior."""
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$",
            agent_type="claude",
            write_delay=0.5,
            submit_retry_delay=0.15,
            submit_confirm_timeout=0.2,
            submit_confirm_poll_interval=0.05,
            submit_confirm_retries=2,
        )
        ctrl.running = True
        ctrl.master_fd = 1

        writes: list[bytes] = []
        sleeps: list[float] = []

        with (
            patch(
                "synapse.controller.os.write",
                side_effect=lambda fd, data: (writes.append(data), len(data))[1],
            ),
            patch(
                "synapse.controller.time.sleep",
                side_effect=lambda t: sleeps.append(t),
            ),
        ):
            result = ctrl.write("hello", submit_seq="\r")

        assert result is True
        assert writes == [b"hello", b"\r", b"\r"]
        assert sleeps == [0.5, 0.15]

    def test_submit_confirmation_warns_after_bounded_retries(self, caplog):
        """Copilot should log a warning when submit remains unconfirmed."""
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$",
            agent_id="synapse-copilot-8140",
            agent_type="copilot",
            write_delay=0.5,
            submit_retry_delay=0.15,
            submit_confirm_timeout=0.1,
            submit_confirm_poll_interval=0.05,
            submit_confirm_retries=1,
        )
        ctrl.running = True
        ctrl.master_fd = 1
        ctrl.status = "READY"
        ctrl.get_context = lambda: "A2A: hello"  # type: ignore[method-assign]

        with (
            patch(
                "synapse.controller.os.write",
                side_effect=lambda fd, data: len(data),
            ),
            patch("synapse.controller.time.sleep"),
            caplog.at_level("WARNING"),
        ):
            result = ctrl.write("hello", submit_seq="\r")

        assert result is True
        assert "submit confirmation failed" in caplog.text

    # --- Copilot submit confirmation tests ---

    @staticmethod
    def _copilot_echo_context(initial: str, after_paste: str):
        """Factory that returns (get_context, write_side_effect).

        get_context: callable returning `initial` before paste, `after_paste` after.
        write_side_effect: callable for os.write mock that tracks writes and
            flips the context when bracketed paste data (containing \\x1b[200~)
            is written.

        Usage in tests:
            get_ctx, write_se = self._copilot_echo_context("", "A2A: hello")
            ctrl.get_context = get_ctx
            with patch("synapse.controller.os.write", side_effect=write_se): ...
        """
        state = {"pasted": False}
        writes: list[bytes] = []

        def get_context() -> str:
            return after_paste if state["pasted"] else initial

        def write_side_effect(fd: int, data: bytes) -> int:
            writes.append(data)
            if b"\x1b[200~" in data:
                state["pasted"] = True
            return len(data)

        write_side_effect.writes = writes  # type: ignore[attr-defined]
        return get_context, write_side_effect

    @staticmethod
    def _make_copilot_ctrl(*, retries=2, long_retries=None):
        """Factory for a Copilot controller with submit-confirm defaults."""
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$",
            agent_id="synapse-copilot-8140",
            agent_type="copilot",
            write_delay=0.5,
            bracketed_paste=True,
            submit_confirm_timeout=0.1,
            submit_confirm_poll_interval=0.05,
            submit_confirm_retries=retries,
            long_submit_confirm_retries=long_retries,
        )
        ctrl.running = True
        ctrl.master_fd = 1
        ctrl.status = "READY"
        ctrl.get_context = lambda: "A2A: hello"  # type: ignore[method-assign]
        return ctrl

    def test_copilot_retries_enter_only_after_confirmation_timeout(self):
        """Copilot retries should resend Enter only after confirmation polls fail."""
        ctrl = self._make_copilot_ctrl(retries=2)
        get_ctx, write_se = self._copilot_echo_context("", "A2A: hello")
        ctrl.get_context = get_ctx  # type: ignore[method-assign]

        with (
            patch("synapse.controller.os.write", side_effect=write_se),
            patch("synapse.controller.time.sleep"),
        ):
            ctrl.write("hello", submit_seq="\r")

        assert write_se.writes == [
            b"\x1b[200~hello\x1b[201~",
            b"\r",
            b"\r",
            b"\r",
            b"\r",
        ]

    def test_copilot_short_single_line_message_uses_paste_not_typed(self):
        """Copilot single-line sends should use bracketed paste plus Enter."""
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$",
            agent_type="copilot",
            write_delay=0.5,
            bracketed_paste=True,
            submit_confirm_timeout=0.1,
            submit_confirm_poll_interval=0.05,
            submit_confirm_retries=1,
        )
        ctrl.running = True
        ctrl.master_fd = 1
        get_ctx, write_se = self._copilot_echo_context("", "echoed")
        ctrl.get_context = get_ctx  # type: ignore[method-assign]

        with (
            patch("synapse.controller.os.write", side_effect=write_se),
            patch("synapse.controller.time.sleep"),
        ):
            ctrl.write("hello", submit_seq="\r")

        assert write_se.writes == [b"\x1b[200~hello\x1b[201~", b"\r"]

    def test_copilot_sends_early_enter_nudge_when_prompt_stays_pending(self):
        """Copilot should resend Enter quickly when the pasted prompt still remains."""
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$",
            agent_type="copilot",
            write_delay=0.5,
            bracketed_paste=True,
            submit_confirm_timeout=0.1,
            submit_confirm_poll_interval=0.05,
            submit_confirm_retries=1,
        )
        ctrl.running = True
        ctrl.master_fd = 1
        ctrl.status = "READY"
        get_ctx, write_se = self._copilot_echo_context("", "A2A: hello")
        ctrl.get_context = get_ctx  # type: ignore[method-assign]

        with (
            patch("synapse.controller.os.write", side_effect=write_se),
            patch("synapse.controller.time.sleep"),
        ):
            ctrl.write("hello", submit_seq="\r")

        assert write_se.writes == [b"\x1b[200~hello\x1b[201~", b"\r", b"\r", b"\r"]

    def test_copilot_skips_early_enter_nudge_when_prompt_clears_immediately(self):
        """Copilot should avoid the early Enter nudge when the prompt clears quickly."""
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$",
            agent_type="copilot",
            write_delay=0.5,
            bracketed_paste=True,
            submit_confirm_timeout=0.1,
            submit_confirm_poll_interval=0.05,
            submit_confirm_retries=1,
        )
        ctrl.running = True
        ctrl.master_fd = 1
        ctrl.status = "READY"
        # After paste echo, status advances → confirmation clears immediately.
        state = {"pasted": False}
        writes: list[bytes] = []

        def write_se(fd: int, data: bytes) -> int:
            writes.append(data)
            if b"\x1b[200~" in data:
                state["pasted"] = True
            return len(data)

        def get_ctx() -> str:
            if not state["pasted"]:
                return ""
            ctrl.status = "PROCESSING"
            return "Processing..."

        ctrl.get_context = get_ctx  # type: ignore[method-assign]

        with (
            patch("synapse.controller.os.write", side_effect=write_se),
            patch("synapse.controller.time.sleep"),
        ):
            ctrl.write("hello", submit_seq="\r")

        assert writes == [b"\x1b[200~hello\x1b[201~", b"\r"]

    def test_copilot_does_not_use_ctrl_s_even_when_footer_mentions_it(self):
        """Copilot submit should stay on Enter even if the footer mentions Ctrl+S."""
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$",
            agent_type="copilot",
            write_delay=0.5,
            bracketed_paste=True,
            submit_confirm_timeout=0.1,
            submit_confirm_poll_interval=0.05,
            submit_confirm_retries=0,
        )
        ctrl.running = True
        ctrl.master_fd = 1
        ctrl.get_context = (
            lambda: "shift+tab switch mode · ctrl+s run command\nA2A: hello"
        )  # type: ignore[method-assign]

        writes: list[bytes] = []
        with (
            patch(
                "synapse.controller.os.write",
                side_effect=lambda fd, data: (writes.append(data), len(data))[1],
            ),
            patch("synapse.controller.time.sleep"),
        ):
            ctrl.write("hello", submit_seq="\r")

        assert writes == [b"\x1b[200~hello\x1b[201~", b"\r"]

    def test_copilot_multiline_message_keeps_paste_mode(self):
        """Multi-line Copilot messages should keep the existing paste behavior."""
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$",
            agent_type="copilot",
            write_delay=0.5,
            bracketed_paste=True,
            submit_confirm_timeout=0.1,
            submit_confirm_poll_interval=0.05,
            submit_confirm_retries=0,
        )
        ctrl.running = True
        ctrl.master_fd = 1
        get_ctx, write_se = self._copilot_echo_context("", "hello\nworld")
        ctrl.get_context = get_ctx  # type: ignore[method-assign]

        with (
            patch("synapse.controller.os.write", side_effect=write_se),
            patch("synapse.controller.time.sleep"),
        ):
            ctrl.write("hello\nworld", submit_seq="\r")

        assert write_se.writes == [b"\x1b[200~hello\nworld\x1b[201~", b"\r"]

    def test_copilot_long_message_reference_stays_pending_while_reference_remains(self):
        """Long-message reference text should keep Copilot confirmation pending."""
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$",
            agent_type="copilot",
            write_delay=0.5,
            bracketed_paste=True,
            submit_confirm_timeout=0.1,
            submit_confirm_poll_interval=0.05,
            submit_confirm_retries=1,
        )
        ctrl.running = True
        ctrl.master_fd = 1
        ctrl.status = "READY"
        ctrl.get_context = (  # type: ignore[method-assign]
            lambda: (
                "A2A: [LONG MESSAGE - FILE ATTACHED]\n"
                "The full message content is stored at: /tmp/msg.txt\n"
                "Please read this file to get the complete message.\n"
                "Processing..."
            )
        )

        writes: list[bytes] = []
        with (
            patch(
                "synapse.controller.os.write",
                side_effect=lambda fd, data: (writes.append(data), len(data))[1],
            ),
            patch("synapse.controller.time.sleep"),
        ):
            ctrl.write(
                "A2A: [LONG MESSAGE - FILE ATTACHED]\n"
                "The full message content is stored at: /tmp/msg.txt\n"
                "Please read this file to get the complete message.",
                submit_seq="\r",
            )

        assert writes == [
            b"\x1b[200~A2A: [LONG MESSAGE - FILE ATTACHED]\n"
            b"The full message content is stored at: /tmp/msg.txt\n"
            b"Please read this file to get the complete message.\x1b[201~",
            b"\r",
            b"\r",
            b"\r",
        ]

    def test_copilot_long_message_status_advance_needs_reference_to_clear(self):
        """Long Copilot sends should not confirm on PROCESSING while prompt text remains."""
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$",
            agent_type="copilot",
            write_delay=0.5,
            bracketed_paste=True,
            submit_confirm_timeout=0.1,
            submit_confirm_poll_interval=0.05,
            submit_confirm_retries=1,
        )
        ctrl.running = True
        ctrl.master_fd = 1
        ctrl.status = "READY"
        ctrl.get_context = (  # type: ignore[method-assign]
            lambda: (setattr(ctrl, "status", "PROCESSING") or "")
            + "[LONG MESSAGE - FILE ATTACHED]\n"
            + "Please read this file to get the complete message.\n"
            + "Processing..."
        )

        writes: list[bytes] = []
        with (
            patch(
                "synapse.controller.os.write",
                side_effect=lambda fd, data: (writes.append(data), len(data))[1],
            ),
            patch("synapse.controller.time.sleep"),
        ):
            ctrl.write(
                "[LONG MESSAGE - FILE ATTACHED]\n"
                "Please read this file to get the complete message.",
                submit_seq="\r",
            )

        assert writes == [
            b"\x1b[200~[LONG MESSAGE - FILE ATTACHED]\n"
            b"Please read this file to get the complete message.\x1b[201~",
            b"\r",
            b"\r",
            b"\r",
        ]

    def test_copilot_compact_paste_token_stays_pending_while_visible(self):
        """Compact paste placeholders should keep Copilot confirmation pending."""
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$",
            agent_type="copilot",
            write_delay=0.5,
            bracketed_paste=True,
            submit_confirm_timeout=0.1,
            submit_confirm_poll_interval=0.05,
            submit_confirm_retries=1,
        )
        ctrl.running = True
        ctrl.master_fd = 1
        ctrl.status = "READY"
        poll_state = {"count": 0}

        def fake_get_context() -> str:
            poll_state["count"] += 1
            if poll_state["count"] == 1:
                return ""
            return "[Paste #1 - 12 lines]\nProcessing..."

        ctrl.get_context = fake_get_context  # type: ignore[method-assign]

        message = "\n".join(f"line{i}" for i in range(1, 13))
        writes: list[bytes] = []
        with (
            patch(
                "synapse.controller.os.write",
                side_effect=lambda fd, data: (writes.append(data), len(data))[1],
            ),
            patch("synapse.controller.time.sleep"),
        ):
            ctrl.write(message, submit_seq="\r")

        assert writes == [f"\x1b[200~{message}\x1b[201~".encode(), b"\r", b"\r", b"\r"]

    def test_copilot_retries_when_same_compact_paste_token_was_already_visible(self):
        """Copilot should still retry when a repeated paste token stays on screen."""
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$",
            agent_type="copilot",
            write_delay=0.5,
            bracketed_paste=True,
            submit_confirm_timeout=0.1,
            submit_confirm_poll_interval=0.05,
            submit_confirm_retries=1,
        )
        ctrl.running = True
        ctrl.master_fd = 1
        ctrl.status = "READY"
        current_tail = "[Paste #1 - 12 lines]\nFollow-up still pending..."
        ctrl.get_context = lambda: current_tail  # type: ignore[method-assign]

        writes: list[bytes] = []
        with (
            patch(
                "synapse.controller.os.write",
                side_effect=lambda fd, data: (writes.append(data), len(data))[1],
            ),
            patch.object(
                ctrl,
                "_wait_for_copilot_paste_echo",
                side_effect=lambda pre: None,
            ),
            patch("synapse.controller.time.sleep"),
        ):
            ctrl.write("line1\nline2", submit_seq="\r")

        assert ctrl._has_copilot_pending_placeholder(current_tail)
        assert writes == [b"\x1b[200~line1\nline2\x1b[201~", b"\r", b"\r", b"\r"]

    def test_copilot_saved_paste_token_stays_pending_while_visible(self):
        """Saved-paste placeholders should keep Copilot confirmation pending."""
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$",
            agent_type="copilot",
            write_delay=0.5,
            bracketed_paste=True,
            submit_confirm_timeout=0.1,
            submit_confirm_poll_interval=0.05,
            submit_confirm_retries=1,
        )
        ctrl.running = True
        ctrl.master_fd = 1
        ctrl.status = "READY"
        poll_state = {"count": 0}

        def fake_get_context() -> str:
            poll_state["count"] += 1
            if poll_state["count"] == 1:
                return ""
            return "[Saved pasted content to workspace (14 KB) id=3]\nProcessing..."

        ctrl.get_context = fake_get_context  # type: ignore[method-assign]

        writes: list[bytes] = []
        with (
            patch(
                "synapse.controller.os.write",
                side_effect=lambda fd, data: (writes.append(data), len(data))[1],
            ),
            patch("synapse.controller.time.sleep"),
        ):
            ctrl.write("line1\nline2\nline3", submit_seq="\r")

        assert writes == [b"\x1b[200~line1\nline2\nline3\x1b[201~", b"\r", b"\r", b"\r"]

    def test_copilot_retries_when_same_saved_paste_token_was_already_visible(self):
        """Copilot should still retry when a repeated saved-paste token stays visible."""
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$",
            agent_type="copilot",
            write_delay=0.5,
            bracketed_paste=True,
            submit_confirm_timeout=0.1,
            submit_confirm_poll_interval=0.05,
            submit_confirm_retries=1,
        )
        ctrl.running = True
        ctrl.master_fd = 1
        ctrl.status = "READY"
        current_tail = "[Saved pasted content to workspace (14 KB) id=3]\nFollow-up still pending..."
        ctrl.get_context = lambda: current_tail  # type: ignore[method-assign]

        writes: list[bytes] = []
        with (
            patch(
                "synapse.controller.os.write",
                side_effect=lambda fd, data: (writes.append(data), len(data))[1],
            ),
            patch.object(
                ctrl,
                "_wait_for_copilot_paste_echo",
                side_effect=lambda pre: None,
            ),
            patch("synapse.controller.time.sleep"),
        ):
            ctrl.write("line1\nline2", submit_seq="\r")

        assert ctrl._has_copilot_pending_placeholder(current_tail)
        assert writes == [b"\x1b[200~line1\nline2\x1b[201~", b"\r", b"\r", b"\r"]

    def test_copilot_multiline_message_uses_long_submit_confirm_budget(self):
        """Multi-line Copilot sends should use the long-message confirm budget."""
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$",
            agent_type="copilot",
            write_delay=0.5,
            bracketed_paste=True,
            submit_confirm_timeout=0.1,
            submit_confirm_poll_interval=0.05,
            submit_confirm_retries=1,
            long_submit_confirm_timeout=0.2,
            long_submit_confirm_retries=2,
        )
        ctrl.running = True
        ctrl.master_fd = 1
        ctrl.status = "READY"
        get_ctx, write_se = self._copilot_echo_context("", "hello\nworld")
        ctrl.get_context = get_ctx  # type: ignore[method-assign]

        sleeps: list[float] = []
        with (
            patch("synapse.controller.os.write", side_effect=write_se),
            patch(
                "synapse.controller.time.sleep",
                side_effect=lambda t: sleeps.append(t),
            ),
        ):
            ctrl.write("hello\nworld", submit_seq="\r")

        assert write_se.writes == [
            b"\x1b[200~hello\nworld\x1b[201~",
            b"\r",
            b"\r",
            b"\r",
            b"\r",
        ]
        # Confirm polls use 0.05s intervals; nudge delays may also appear.
        poll_sleeps = [s for s in sleeps if s == 0.05]
        assert len(poll_sleeps) >= 12

    def test_copilot_long_message_uses_longer_early_enter_nudge(self):
        """Long Copilot sends should wait slightly longer before the early Enter nudge."""
        from synapse.controller import (
            _COPILOT_LONG_SUBMIT_NUDGE_DELAY,
            _COPILOT_SUBMIT_NUDGE_DELAY,
        )

        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$",
            agent_type="copilot",
            write_delay=0.5,
            bracketed_paste=True,
            submit_confirm_timeout=0.1,
            submit_confirm_poll_interval=0.05,
            submit_confirm_retries=1,
        )
        ctrl.running = True
        ctrl.master_fd = 1
        ctrl.status = "READY"
        get_ctx, write_se = self._copilot_echo_context("", "line1\nline2")
        ctrl.get_context = get_ctx  # type: ignore[method-assign]

        sleeps: list[float] = []
        with (
            patch("synapse.controller.os.write", side_effect=write_se),
            patch(
                "synapse.controller.time.sleep",
                side_effect=lambda t: sleeps.append(t),
            ),
        ):
            ctrl.write("line1\nline2", submit_seq="\r")

        assert write_se.writes == [
            b"\x1b[200~line1\nline2\x1b[201~",
            b"\r",
            b"\r",
            b"\r",
        ]
        assert _COPILOT_LONG_SUBMIT_NUDGE_DELAY in sleeps
        assert _COPILOT_SUBMIT_NUDGE_DELAY not in sleeps

    def test_copilot_single_line_message_keeps_default_submit_timing(self):
        """Single-line Copilot sends should use paste echo wait, not fixed delay."""
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$",
            agent_type="copilot",
            write_delay=0.5,
            bracketed_paste=True,
            submit_confirm_timeout=0.1,
            submit_confirm_poll_interval=0.05,
            submit_confirm_retries=0,
        )
        ctrl.running = True
        ctrl.master_fd = 1
        ctrl.status = "READY"
        get_ctx, write_se = self._copilot_echo_context("", "hello")
        ctrl.get_context = get_ctx  # type: ignore[method-assign]

        sleeps: list[float] = []
        with (
            patch("synapse.controller.os.write", side_effect=write_se),
            patch(
                "synapse.controller.time.sleep",
                side_effect=lambda t: sleeps.append(t),
            ),
        ):
            ctrl.write("hello", submit_seq="\r")

        # No 0.5s fixed write_delay — paste echo detection fires immediately.
        assert 0.5 not in sleeps

    # --- Bracketed paste mode tests ---

    def test_bracketed_paste_wraps_data(self):
        """bracketed_paste=True should wrap data in ESC[200~ ... ESC[201~."""
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$",
            write_delay=0.05,
            bracketed_paste=True,
        )
        ctrl.running = True
        ctrl.master_fd = 1

        writes: list[bytes] = []
        with (
            patch(
                "synapse.controller.os.write",
                side_effect=lambda fd, data: (writes.append(data), len(data))[1],
            ),
            patch("synapse.controller.time.sleep"),
        ):
            ctrl.write("hello", submit_seq="\r")

        # Data should be wrapped: ESC[200~ + data + ESC[201~, then CR
        assert writes == [b"\x1b[200~hello\x1b[201~", b"\r"]

    def test_bracketed_paste_false_no_wrapping(self):
        """bracketed_paste=False (default) should not wrap data."""
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$",
            write_delay=0.05,
            bracketed_paste=False,
        )
        ctrl.running = True
        ctrl.master_fd = 1

        writes: list[bytes] = []
        with (
            patch(
                "synapse.controller.os.write",
                side_effect=lambda fd, data: (writes.append(data), len(data))[1],
            ),
            patch("synapse.controller.time.sleep"),
        ):
            ctrl.write("hello", submit_seq="\r")

        assert writes == [b"hello", b"\r"]

    def test_bracketed_paste_default_is_false(self):
        """Default bracketed_paste should be False."""
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$",
        )
        assert ctrl._bracketed_paste is False

    def test_bracketed_paste_with_submit_retry(self):
        """bracketed_paste should work together with submit_retry_delay."""
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$",
            write_delay=0.5,
            submit_retry_delay=0.15,
            bracketed_paste=True,
        )
        ctrl.running = True
        ctrl.master_fd = 1

        writes: list[bytes] = []
        sleeps: list[float] = []
        with (
            patch(
                "synapse.controller.os.write",
                side_effect=lambda fd, data: (writes.append(data), len(data))[1],
            ),
            patch(
                "synapse.controller.time.sleep",
                side_effect=lambda t: sleeps.append(t),
            ),
        ):
            ctrl.write("hello", submit_seq="\r")

        # Should write: bracketed data, sleep(0.5), CR, sleep(0.15), CR
        assert writes == [b"\x1b[200~hello\x1b[201~", b"\r", b"\r"]
        assert sleeps == [0.5, 0.15]

    def test_bracketed_paste_no_submit_seq(self):
        """bracketed_paste without submit_seq should still wrap data."""
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$",
            bracketed_paste=True,
        )
        ctrl.running = True
        ctrl.master_fd = 1

        writes: list[bytes] = []
        with (
            patch(
                "synapse.controller.os.write",
                side_effect=lambda fd, data: (writes.append(data), len(data))[1],
            ),
            patch("synapse.controller.time.sleep"),
        ):
            ctrl.write("hello")

        # Data should be wrapped, no CR
        assert writes == [b"\x1b[200~hello\x1b[201~"]

    # --- Thread safety test (Bug 4: _write_lock prevents interleaving) ---

    def test_write_lock_prevents_interleaving(self):
        """Concurrent write() calls must not interleave data→sleep→submit_seq.

        Each call's sequence should appear as a contiguous block in the
        event log, proving _write_lock serializes the entire operation.
        """
        from concurrent.futures import ThreadPoolExecutor

        ctrl = TerminalController(command="echo test", idle_regex=r"\$")
        ctrl.running = True
        ctrl.master_fd = 1

        call_log: list[tuple[str, ...]] = []
        log_lock = threading.Lock()

        # Track the current thread IDs performing test writes so we
        # only record calls from the test's own ThreadPoolExecutor,
        # ignoring stray calls from daemon threads left by other tests.
        test_threads: set[int] = set()
        test_threads_lock = threading.Lock()

        def mock_write(fd, data):
            if threading.current_thread().ident in test_threads:
                with log_lock:
                    call_log.append(("write", data))
            return len(data)

        with (
            patch("synapse.controller.os.write", side_effect=mock_write),
            patch("synapse.controller.time.sleep") as mock_sleep,
        ):

            def sleep_side_effect(delay):
                if threading.current_thread().ident in test_threads:
                    with log_lock:
                        call_log.append(("sleep",))

            mock_sleep.side_effect = sleep_side_effect

            def call_write(label: str):
                with test_threads_lock:
                    test_threads.add(threading.current_thread().ident)
                ctrl.write(label, submit_seq="\r")

            with ThreadPoolExecutor(max_workers=2) as pool:
                f1 = pool.submit(call_write, "AAA")
                f2 = pool.submit(call_write, "BBB")
                f1.result()
                f2.result()

        # Each call produces 3 events: write(data), sleep, write(submit)
        assert len(call_log) == 6

        # Find each call's contiguous block
        first_a = next(i for i, e in enumerate(call_log) if e == ("write", b"AAA"))
        first_b = next(i for i, e in enumerate(call_log) if e == ("write", b"BBB"))

        # The block starting at first_a must be contiguous: data, sleep, submit
        block_a = call_log[first_a : first_a + 3]
        assert block_a == [("write", b"AAA"), ("sleep",), ("write", b"\r")]

        block_b = call_log[first_b : first_b + 3]
        assert block_b == [("write", b"BBB"), ("sleep",), ("write", b"\r")]

        # Blocks must not overlap (one starts after the other ends)
        assert abs(first_a - first_b) >= 3


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
