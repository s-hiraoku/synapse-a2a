"""Additional tests for synapse list command to improve coverage."""

import contextlib
import sys
from itertools import count
from unittest.mock import MagicMock, patch

import pytest

from synapse.commands.list import ListCommand


class TestListCommandCoverage:
    """Tests for ListCommand methods to improve coverage."""

    @pytest.fixture
    def mock_dependencies(self):
        """Create mock dependencies for ListCommand."""
        return {
            "registry_factory": MagicMock(),
            "is_process_alive": MagicMock(return_value=True),
            "is_port_open": MagicMock(return_value=True),
            "clear_screen": MagicMock(),
            "time_module": MagicMock(),
            "print_func": MagicMock(),
        }

    @pytest.fixture
    def list_command(self, mock_dependencies):
        """Create ListCommand instance."""
        cmd = ListCommand(**mock_dependencies)
        # Mock _time.time() to return increasing values
        cmd._time.time.side_effect = count(start=100.0, step=0.1)
        return cmd

    def test_setup_nonblocking_input_success(self, list_command):
        """Test _setup_nonblocking_input success path."""
        with patch.dict("sys.modules", {"termios": MagicMock(), "tty": MagicMock()}):
            termios_mock = sys.modules["termios"]
            tty_mock = sys.modules["tty"]
            termios_mock.tcgetattr.return_value = ["old_settings"]

            # We need to mock sys.stdin.fileno() as well since it's called
            with patch("sys.stdin") as mock_stdin:
                mock_stdin.fileno.return_value = 1

                result = list_command._setup_nonblocking_input()

                assert result is not None
                assert result[0] == ["old_settings"]
                tty_mock.setcbreak.assert_called_with(1)

    def test_setup_nonblocking_input_failure(self, list_command):
        """Test _setup_nonblocking_input failure path."""
        with (
            patch.dict("sys.modules", {"termios": MagicMock(), "tty": MagicMock()}),
            patch("sys.stdin") as mock_stdin,
        ):
            mock_stdin.fileno.side_effect = Exception("error")

            result = list_command._setup_nonblocking_input()

            assert result is None

    def test_restore_terminal(self, list_command):
        """Test _restore_terminal."""
        with patch.dict("sys.modules", {"termios": MagicMock()}):
            termios_mock = sys.modules["termios"]

            # Success case
            list_command._restore_terminal((["old"], 1))
            termios_mock.tcsetattr.assert_called_with(
                1, termios_mock.TCSADRAIN, ["old"]
            )

            # None case
            list_command._restore_terminal(None)

            # Exception case
            termios_mock.tcsetattr.side_effect = Exception("error")
            list_command._restore_terminal((["old"], 1))  # Should not raise

    @patch("select.select")
    @patch("os.read")
    @patch("fcntl.fcntl")
    @patch("sys.stdin")
    def test_read_key_nonblocking_no_input(
        self, mock_stdin, mock_fcntl, mock_read, mock_select, list_command
    ):
        """Test _read_key_nonblocking with no input."""
        mock_stdin.fileno.return_value = 1
        mock_select.return_value = ([], [], [])  # No data

        result = list_command._read_key_nonblocking()

        assert result is None

    @patch("select.select")
    @patch("os.read")
    @patch("fcntl.fcntl")
    @patch("sys.stdin")
    def test_read_key_nonblocking_char(
        self, mock_stdin, mock_fcntl, mock_read, mock_select, list_command
    ):
        """Test _read_key_nonblocking with a character."""
        mock_stdin.fileno.return_value = 1
        mock_select.return_value = ([mock_stdin], [], [])
        mock_read.return_value = b"a"

        result = list_command._read_key_nonblocking()

        assert result == "a"

    @patch("select.select")
    @patch("os.read")
    @patch("fcntl.fcntl")
    @patch("sys.stdin")
    def test_read_key_nonblocking_escape_sequence(
        self, mock_stdin, mock_fcntl, mock_read, mock_select, list_command
    ):
        """Test _read_key_nonblocking with escape sequence."""
        mock_stdin.fileno.return_value = 1
        mock_select.return_value = ([mock_stdin], [], [])
        # First read returns ESC, loop reads [ then A
        mock_read.side_effect = [b"\x1b", b"[", b"A"]

        result = list_command._read_key_nonblocking()

        assert result == "UP"

    @patch("select.select")
    @patch("os.read")
    @patch("fcntl.fcntl")
    @patch("sys.stdin")
    def test_read_key_nonblocking_partial_escape(
        self, mock_stdin, mock_fcntl, mock_read, mock_select, list_command
    ):
        """Test _read_key_nonblocking with partial escape (timeout)."""
        mock_stdin.fileno.return_value = 1
        mock_select.side_effect = [
            ([mock_stdin], [], []),  # First check
            ([], [], []),  # Second check (timeout inside loop)
        ]
        mock_read.return_value = b"\x1b"

        result = list_command._read_key_nonblocking()

        assert result == "\x1b"

    @patch("select.select")
    @patch("os.read")
    @patch("fcntl.fcntl")
    @patch("sys.stdin")
    def test_read_key_nonblocking_unknown_sequence(
        self, mock_stdin, mock_fcntl, mock_read, mock_select, list_command
    ):
        """Test _read_key_nonblocking with unknown sequence."""
        mock_stdin.fileno.return_value = 1
        mock_select.return_value = ([mock_stdin], [], [])
        # Start with ESC, then something not in known sequences
        mock_read.side_effect = [b"\x1b", b"X"]

        result = list_command._read_key_nonblocking()

        assert result == "\x1b"

    @patch("select.select")
    @patch("os.read")
    @patch("fcntl.fcntl")
    @patch("sys.stdin")
    def test_read_key_nonblocking_exception(
        self, mock_stdin, mock_fcntl, mock_read, mock_select, list_command
    ):
        """Test _read_key_nonblocking handling exception."""
        mock_stdin.fileno.return_value = 1
        mock_select.side_effect = Exception("error")

        result = list_command._read_key_nonblocking()

        assert result is None

    def test_create_file_watcher_import_error(self, list_command):
        """Test _create_file_watcher when watchdog is missing."""
        with patch.dict("sys.modules", {"watchdog.events": None}):
            result = list_command._create_file_watcher(MagicMock(), MagicMock())
            assert result is None

    @patch("synapse.commands.renderers.rich_renderer.RichRenderer")
    @patch("rich.live.Live")
    def test_run_rich_tui_interactive_flow(
        self, mock_live, mock_renderer, list_command
    ):
        """Test _run_rich_tui interactive flow with various keys."""
        # Setup mocks
        console = MagicMock()
        registry = MagicMock()
        registry.list_agents.return_value = {
            "agent1": {
                "agent_type": "claude",
                "port": 8100,
                "status": "READY",
                "working_dir_full": "/tmp",
            }
        }

        # Mock _setup_nonblocking_input to return something (interactive mode)
        list_command._setup_nonblocking_input = MagicMock(return_value=("settings", 1))
        list_command._restore_terminal = MagicMock()
        list_command._create_file_watcher = MagicMock(return_value=MagicMock())

        # Sequence of keys to simulate:
        # 1. '/' -> Enter filter mode
        # 2. 'c' -> Type 'c'
        # 3. Enter -> Apply filter
        # 4. '1' -> Select row 1
        # 5. 'k' -> Kill confirm
        # 6. 'n' -> Cancel kill
        # 7. 'k' -> Kill confirm
        # 8. 'y' -> Confirm kill
        # 9. 'q' -> Quit
        keys = ["/", "c", "\r", "1", "k", "n", "k", "y", "q"]
        list_command._read_key_nonblocking = MagicMock(side_effect=keys)

        # Mock _kill_agent
        list_command._kill_agent = MagicMock()

        # Run
        with contextlib.suppress(SystemExit):
            list_command._run_rich_tui(registry, console, "1.0.0")

        # Verifications
        assert list_command._kill_agent.call_count == 1  # Once for 'y'
        assert list_command._read_key_nonblocking.call_count == len(keys)

    @patch("synapse.commands.renderers.rich_renderer.RichRenderer")
    @patch("rich.live.Live")
    def test_run_rich_tui_filter_logic(self, mock_live, mock_renderer, list_command):
        """Test _run_rich_tui filter logic specifically."""
        console = MagicMock()
        registry = MagicMock()
        registry.list_agents.return_value = {}

        list_command._setup_nonblocking_input = MagicMock(return_value=("settings", 1))
        list_command._restore_terminal = MagicMock()
        list_command._create_file_watcher = MagicMock(return_value=MagicMock())

        # Keys:
        # '/' (enter filter)
        # 'a' (type a)
        # ESC (cancel filter)
        # '/' (enter filter)
        # 'b' (type b)
        # Backspace (delete b)
        # ESC (cancel filter - needed to exit mode so 'q' works as quit)
        # 'q' (quit)
        keys = ["/", "a", "\x1b", "/", "b", "\x7f", "\x1b", "q"]
        list_command._read_key_nonblocking = MagicMock(side_effect=keys)

        with contextlib.suppress(SystemExit):
            list_command._run_rich_tui(registry, console, "1.0.0")

        assert list_command._read_key_nonblocking.call_count == len(keys)

    @patch("synapse.commands.renderers.rich_renderer.RichRenderer")
    @patch("rich.live.Live")
    def test_run_rich_tui_navigation(self, mock_live, mock_renderer, list_command):
        """Test _run_rich_tui navigation (UP/DOWN)."""
        console = MagicMock()
        registry = MagicMock()
        # 3 agents
        registry.list_agents.return_value = {
            "a1": {"pid": 1},
            "a2": {"pid": 2},
            "a3": {"pid": 3},
        }

        list_command._setup_nonblocking_input = MagicMock(return_value=("settings", 1))
        list_command._restore_terminal = MagicMock()
        list_command._create_file_watcher = MagicMock(return_value=MagicMock())

        # Keys: DOWN, DOWN, UP, q
        keys = ["DOWN", "DOWN", "UP", "q"]
        list_command._read_key_nonblocking = MagicMock(side_effect=keys)

        with contextlib.suppress(SystemExit):
            list_command._run_rich_tui(registry, console, "1.0.0")

        assert list_command._read_key_nonblocking.call_count == len(keys)

    @patch("synapse.commands.renderers.rich_renderer.RichRenderer")
    @patch("rich.live.Live")
    def test_run_rich_tui_jump(self, mock_live, mock_renderer, list_command):
        """Test _run_rich_tui jump functionality."""
        console = MagicMock()
        registry = MagicMock()
        registry.list_agents.return_value = {"a1": {"pid": 1}}

        list_command._setup_nonblocking_input = MagicMock(return_value=("settings", 1))
        list_command._restore_terminal = MagicMock()
        list_command._create_file_watcher = MagicMock(return_value=MagicMock())

        # Keys: 1 (select), j (jump), q
        keys = ["1", "j", "q"]
        list_command._read_key_nonblocking = MagicMock(side_effect=keys)

        with (
            patch("synapse.terminal_jump.can_jump", return_value=True),
            patch("synapse.terminal_jump.jump_to_terminal") as mock_jump,
            contextlib.suppress(SystemExit),
        ):
            list_command._run_rich_tui(registry, console, "1.0.0")

            mock_jump.assert_called_once()
