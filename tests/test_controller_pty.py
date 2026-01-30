"""Tests for TerminalController PTY management and interactive mode."""

import signal
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from synapse.controller import TerminalController


class TestControllerPTY:
    """Tests for PTY management in TerminalController."""

    @pytest.fixture
    def mock_pty(self):
        with patch("synapse.controller.pty") as mock:
            mock.openpty.return_value = (10, 11)  # master, slave
            yield mock

    @pytest.fixture
    def mock_subprocess(self):
        with patch("synapse.controller.subprocess") as mock:
            process = MagicMock()
            process.poll.return_value = None
            process.pid = 12345
            mock.Popen.return_value = process
            yield mock

    @pytest.fixture
    def mock_os(self):
        with patch("synapse.controller.os") as mock:
            mock.environ.copy.return_value = {"PATH": "/bin"}
            mock.read.return_value = b"output"
            mock.setsid = MagicMock()
            mock.close = MagicMock()
            mock.write = MagicMock()
            mock.killpg = MagicMock()
            mock.getpgid.return_value = 12345
            yield mock

    @pytest.fixture
    def mock_select(self):
        with patch("synapse.controller.select") as mock:
            mock.select.return_value = ([10], [], [])
            yield mock

    @pytest.fixture
    def controller(self):
        return TerminalController(command="bash", args=["-c", "echo hello"])

    def test_start_launches_process(
        self, controller, mock_pty, mock_subprocess, mock_os
    ):
        """Test that start() launches the subprocess with PTY."""
        controller.start()

        mock_pty.openpty.assert_called_once()
        mock_subprocess.Popen.assert_called_once()

        args, kwargs = mock_subprocess.Popen.call_args
        assert args[0] == ["bash", "-c", "echo hello"]
        assert kwargs["stdin"] == 11
        assert kwargs["stdout"] == 11
        assert kwargs["stderr"] == 11
        assert kwargs["preexec_fn"] == mock_os.setsid

        mock_os.close.assert_called_once_with(11)  # Slave closed in parent
        assert controller.running is True
        assert controller.master_fd == 10

        # Cleanup
        controller.stop()

    def test_monitor_output_reads_from_pty(
        self, controller, mock_pty, mock_subprocess, mock_os, mock_select
    ):
        """Test that _monitor_output reads data from master_fd."""
        controller.start()

        # Allow thread to run briefly
        time.sleep(0.1)

        # Stop controller to exit loop
        controller.running = False
        controller.thread.join(timeout=1.0)

        # Verify select called
        mock_select.select.assert_called()
        # Verify read called
        mock_os.read.assert_called_with(10, 1024)
        # Verify output buffer updated
        assert b"output" in controller.output_buffer

    def test_monitor_output_handles_os_error(
        self, controller, mock_pty, mock_subprocess, mock_os, mock_select
    ):
        """Test that _monitor_output handles OSError gracefully."""
        mock_os.read.side_effect = OSError("Read error")

        controller.start()
        time.sleep(0.1)
        controller.running = False
        controller.thread.join(timeout=1.0)

        # Should have exited loop without crashing
        assert not controller.thread.is_alive()

    def test_monitor_output_handles_empty_read(
        self, controller, mock_pty, mock_subprocess, mock_os, mock_select
    ):
        """Test that _monitor_output exits on empty read (EOF)."""
        mock_os.read.return_value = b""

        controller.start()
        time.sleep(0.1)
        controller.thread.join(timeout=1.0)

        assert not controller.thread.is_alive()

    def test_write_to_pty(self, controller, mock_pty, mock_subprocess, mock_os):
        """Test writing to PTY."""
        controller.start()

        controller.write("ls", submit_seq="\n")

        # Check writes
        # 1. Command
        mock_os.write.assert_any_call(10, b"ls")
        # 2. Submit sequence
        mock_os.write.assert_any_call(10, b"\n")

        controller.stop()

    def test_interrupt_sends_signal(
        self, controller, mock_pty, mock_subprocess, mock_os
    ):
        """Test sending interrupt signal."""
        controller.start()

        controller.interrupt()

        mock_os.getpgid.assert_called_with(12345)
        mock_os.killpg.assert_called_with(12345, signal.SIGINT)

        controller.stop()

    def test_run_interactive_uses_pty_spawn(self, controller, mock_pty, mock_os):
        """Test run_interactive uses pty.spawn."""
        with (
            patch("synapse.controller.pty.spawn") as mock_spawn,
            patch("synapse.controller.signal.signal"),
        ):
            # Run in a thread since it blocks
            t = threading.Thread(target=controller.run_interactive)
            t.start()

            time.sleep(0.1)
            controller.running = False  # Signal to stop

            mock_spawn.assert_called()
            args, _ = mock_spawn.call_args
            assert args[0] == ["bash", "-c", "echo hello"]

            # Wait for thread (mock spawn should return immediately if not mocked side_effect)
            t.join(timeout=1.0)


class TestInteractiveCallbacks:
    """Tests for interactive mode callbacks."""

    def test_read_callback(self):
        """Test read_callback handles data and updates state."""
        controller = TerminalController(command="bash")
        controller.agent_id = "test-agent"

        # Access the internal function via run_interactive scope is hard,
        # but we can test logic if we extract it or inspect pty.spawn args.
        # Instead, we'll rely on the fact that we can mock pty.spawn and call the callback passed to it.

        with (
            patch("synapse.controller.pty.spawn") as mock_spawn,
            patch("synapse.controller.os.read", return_value=b"data"),
            patch("synapse.controller.fcntl.ioctl"),
            patch("synapse.controller.signal.signal"),
        ):
            t = threading.Thread(target=controller.run_interactive)
            t.start()
            time.sleep(0.1)

            # Get the read_callback passed to spawn
            args, _ = mock_spawn.call_args
            read_callback = args[1]

            # Call it
            data = read_callback(10)

            assert data == b"data"
            assert controller.master_fd == 10
            assert controller._last_output_time is not None

            controller.running = False
            t.join()

    def test_input_callback(self):
        """Test input_callback passes data through."""
        controller = TerminalController(command="bash")

        with (
            patch("synapse.controller.pty.spawn") as mock_spawn,
            patch("synapse.controller.os.read", return_value=b"input"),
            patch("synapse.controller.signal.signal"),
        ):
            t = threading.Thread(target=controller.run_interactive)
            t.start()
            time.sleep(0.1)

            # Get input_callback (3rd arg if present)
            args, _ = mock_spawn.call_args
            if len(args) > 2:
                input_callback = args[2]
                data = input_callback(0)
                assert data == b"input"

            controller.running = False
            t.join()
