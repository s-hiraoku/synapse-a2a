"""Additional tests for synapse approval module to improve coverage."""

import sys
from unittest.mock import MagicMock, patch

from synapse.approval import prompt_for_approval


class TestPromptForApproval:
    """Tests for prompt_for_approval function."""

    @patch("builtins.input")
    @patch("builtins.print")
    @patch("sys.stdin")
    def test_prompt_approve(self, mock_stdin, mock_print, mock_input):
        """Test approval with 'y'."""
        mock_input.return_value = "y"
        mock_stdin.fileno.return_value = 1

        with patch.dict("sys.modules", {"termios": MagicMock()}):
            termios_mock = sys.modules["termios"]
            termios_mock.tcgetattr.return_value = ["settings"]

            result = prompt_for_approval("agent-id", 8000)

            assert result == "approve"
            termios_mock.tcgetattr.assert_called_with(1)
            termios_mock.tcsetattr.assert_called()
            termios_mock.tcflush.assert_called()

    @patch("builtins.input")
    @patch("builtins.print")
    @patch("sys.stdin")
    def test_prompt_abort(self, mock_stdin, mock_print, mock_input):
        """Test approval with 'n'."""
        mock_input.return_value = "n"
        mock_stdin.fileno.return_value = 1

        with patch.dict("sys.modules", {"termios": MagicMock()}):
            result = prompt_for_approval("agent-id", 8000)
            assert result == "abort"

    @patch("builtins.input")
    @patch("builtins.print")
    @patch("sys.stdin")
    def test_prompt_skip(self, mock_stdin, mock_print, mock_input):
        """Test approval with 's'."""
        mock_input.return_value = "s"
        mock_stdin.fileno.return_value = 1

        with patch.dict("sys.modules", {"termios": MagicMock()}):
            result = prompt_for_approval("agent-id", 8000)
            assert result == "skip"

    @patch("builtins.input")
    @patch("builtins.print")
    @patch("sys.stdin")
    def test_prompt_eof_error(self, mock_stdin, mock_print, mock_input):
        """Test EOFError handling."""
        mock_input.side_effect = EOFError()
        mock_stdin.fileno.return_value = 1

        with patch.dict("sys.modules", {"termios": MagicMock()}):
            result = prompt_for_approval("agent-id", 8000)
            assert result == "abort"

    @patch("builtins.input")
    @patch("builtins.print")
    @patch("sys.stdin")
    def test_prompt_keyboard_interrupt(self, mock_stdin, mock_print, mock_input):
        """Test KeyboardInterrupt handling."""
        mock_input.side_effect = KeyboardInterrupt()
        mock_stdin.fileno.return_value = 1

        with patch.dict("sys.modules", {"termios": MagicMock()}):
            result = prompt_for_approval("agent-id", 8000)
            assert result == "abort"

    @patch("builtins.input")
    @patch("builtins.print")
    @patch("sys.stdin")
    def test_prompt_termios_error_on_getattr(self, mock_stdin, mock_print, mock_input):
        """Test termios error during tcgetattr (not a TTY)."""
        mock_input.return_value = "y"
        mock_stdin.fileno.return_value = 1

        with patch.dict("sys.modules", {"termios": MagicMock()}):
            termios_mock = sys.modules["termios"]
            termios_mock.error = Exception
            termios_mock.tcgetattr.side_effect = termios_mock.error("Not a TTY")

            result = prompt_for_approval("agent-id", 8000)

            assert result == "approve"
            # verify tcsetattr was NOT called because settings were not saved
            termios_mock.tcsetattr.assert_not_called()
            # flush should still be called
            termios_mock.tcflush.assert_called()

    @patch("builtins.input")
    @patch("builtins.print")
    @patch("sys.stdin")
    def test_prompt_termios_error_on_flush(self, mock_stdin, mock_print, mock_input):
        """Test termios error during tcflush."""
        mock_input.return_value = "y"
        mock_stdin.fileno.return_value = 1

        with patch.dict("sys.modules", {"termios": MagicMock()}):
            termios_mock = sys.modules["termios"]
            termios_mock.error = Exception
            termios_mock.tcflush.side_effect = termios_mock.error("Flush failed")

            result = prompt_for_approval("agent-id", 8000)

            assert result == "approve"
            # Should not raise exception
