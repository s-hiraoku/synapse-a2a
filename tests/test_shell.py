"""Tests for SynapseShell - Interactive shell with @Agent support."""

from unittest.mock import MagicMock, patch

from synapse.shell import SynapseShell

# ============================================================
# Shell Initialization Tests
# ============================================================


class TestShellInitialization:
    """Test SynapseShell initialization."""

    @patch("synapse.shell.AgentRegistry")
    def test_init_creates_registry(self, mock_registry_cls):
        """Should create AgentRegistry on initialization."""
        shell = SynapseShell()
        mock_registry_cls.assert_called_once()
        assert shell.registry is not None

    @patch("synapse.shell.AgentRegistry")
    def test_init_sets_prompt(self, mock_registry_cls):
        """Should set prompt to 'synapse> '."""
        shell = SynapseShell()
        assert shell.prompt == "synapse> "

    @patch("synapse.shell.AgentRegistry")
    def test_init_has_intro(self, mock_registry_cls):
        """Should have intro banner."""
        shell = SynapseShell()
        assert "Synapse Shell" in shell.intro
        assert "@Agent" in shell.intro

    @patch("synapse.shell.AgentRegistry")
    def test_init_compiles_agent_pattern(self, mock_registry_cls):
        """Should compile regex pattern for @Agent detection."""
        shell = SynapseShell()
        assert shell.agent_pattern is not None

        # Test pattern matches
        match = shell.agent_pattern.match("@claude hello world")
        assert match is not None
        assert match.group(1) == "claude"
        assert match.group(3) == "hello world"


# ============================================================
# Pattern Detection Tests
# ============================================================


class TestPatternDetection:
    """Test @Agent pattern detection in default handler."""

    @patch("synapse.shell.AgentRegistry")
    def test_agent_pattern_basic(self, mock_registry_cls):
        """Should detect basic @agent message pattern."""
        shell = SynapseShell()

        match = shell.agent_pattern.match("@claude hello")
        assert match is not None
        assert match.group(1) == "claude"
        assert match.group(2) is None  # No --response flag
        assert match.group(3) == "hello"

    @patch("synapse.shell.AgentRegistry")
    def test_agent_pattern_with_response_flag(self, mock_registry_cls):
        """Should detect --response flag in @agent pattern."""
        shell = SynapseShell()

        match = shell.agent_pattern.match("@gemini --response do this task")
        assert match is not None
        assert match.group(1) == "gemini"
        assert match.group(2) is not None  # Has --response flag
        assert match.group(3) == "do this task"

    @patch("synapse.shell.AgentRegistry")
    def test_agent_pattern_case_insensitive(self, mock_registry_cls):
        """Pattern should be case insensitive for agent names."""
        shell = SynapseShell()

        match1 = shell.agent_pattern.match("@Claude message")
        match2 = shell.agent_pattern.match("@CODEX message")

        assert match1 is not None
        assert match2 is not None

    @patch("synapse.shell.AgentRegistry")
    def test_no_match_without_at(self, mock_registry_cls):
        """Should not match input without @ prefix."""
        shell = SynapseShell()

        match = shell.agent_pattern.match("claude hello")
        assert match is None

    @patch("synapse.shell.AgentRegistry")
    def test_no_match_at_only(self, mock_registry_cls):
        """Should not match @ without agent name and message."""
        shell = SynapseShell()

        match = shell.agent_pattern.match("@")
        assert match is None


# ============================================================
# Default Handler Tests
# ============================================================


class TestDefaultHandler:
    """Test default() method for input handling."""

    @patch("synapse.shell.AgentRegistry")
    def test_default_calls_send_to_agent(self, mock_registry_cls):
        """Should call send_to_agent for @agent pattern."""
        shell = SynapseShell()
        shell.send_to_agent = MagicMock()

        shell.default("@claude hello world")

        shell.send_to_agent.assert_called_once_with("claude", "hello world", False)

    @patch("synapse.shell.AgentRegistry")
    def test_default_calls_send_to_agent_with_response(self, mock_registry_cls):
        """Should call send_to_agent with wait_response=True for --response."""
        shell = SynapseShell()
        shell.send_to_agent = MagicMock()

        shell.default("@gemini --response analyze this")

        shell.send_to_agent.assert_called_once_with("gemini", "analyze this", True)

    @patch("synapse.shell.AgentRegistry")
    @patch("os.system")
    def test_default_executes_shell_command(self, mock_system, mock_registry_cls):
        """Should execute non-@agent input as shell command."""
        shell = SynapseShell()

        shell.default("ls -la")

        mock_system.assert_called_once_with("ls -la")

    @patch("synapse.shell.AgentRegistry")
    @patch("os.system")
    def test_default_ignores_empty_lines(self, mock_system, mock_registry_cls):
        """Should not execute empty lines."""
        shell = SynapseShell()

        shell.default("")
        shell.default("   ")

        mock_system.assert_not_called()


# ============================================================
# Send To Agent Tests
# ============================================================


class TestSendToAgent:
    """Test send_to_agent() method."""

    @patch("synapse.shell.AgentRegistry")
    def test_agent_not_found(self, mock_registry_cls, capsys):
        """Should print error when agent not found."""
        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = {}
        mock_registry_cls.return_value = mock_registry

        shell = SynapseShell()
        shell.send_to_agent("nonexistent", "hello")

        captured = capsys.readouterr()
        assert "not found" in captured.out

    @patch("synapse.shell.AgentRegistry")
    def test_agent_found_shows_available(self, mock_registry_cls, capsys):
        """Should list available agents when target not found."""
        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = {
            "agent-1": {"agent_type": "claude"},
            "agent-2": {"agent_type": "gemini"},
        }
        mock_registry_cls.return_value = mock_registry

        shell = SynapseShell()
        shell.send_to_agent("codex", "hello")

        captured = capsys.readouterr()
        assert "claude" in captured.out
        assert "gemini" in captured.out

    @patch("synapse.shell.requests.post")
    @patch("synapse.shell.AgentRegistry")
    def test_send_message_success(self, mock_registry_cls, mock_post, capsys):
        """Should send message to agent endpoint."""
        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = {
            "agent-1": {
                "agent_type": "claude",
                "endpoint": "http://localhost:8100",
            }
        }
        mock_registry_cls.return_value = mock_registry
        mock_post.return_value.raise_for_status = MagicMock()

        shell = SynapseShell()
        shell.send_to_agent("claude", "hello")

        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[0][0] == "http://localhost:8100/message"
        assert call_args[1]["json"]["content"] == "hello"
        assert call_args[1]["json"]["priority"] == 1

        captured = capsys.readouterr()
        assert "Sending to claude" in captured.out
        assert "Message sent" in captured.out

    @patch("synapse.shell.requests.post")
    @patch("synapse.shell.AgentRegistry")
    def test_send_message_no_endpoint(self, mock_registry_cls, mock_post, capsys):
        """Should handle agent without endpoint."""
        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = {
            "agent-1": {"agent_type": "claude"}  # No endpoint
        }
        mock_registry_cls.return_value = mock_registry

        shell = SynapseShell()
        shell.send_to_agent("claude", "hello")

        mock_post.assert_not_called()
        captured = capsys.readouterr()
        assert "No endpoint" in captured.out

    @patch("synapse.shell.requests.post")
    @patch("synapse.shell.AgentRegistry")
    def test_send_message_request_error(self, mock_registry_cls, mock_post, capsys):
        """Should handle request errors gracefully."""
        import requests

        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = {
            "agent-1": {
                "agent_type": "claude",
                "endpoint": "http://localhost:8100",
            }
        }
        mock_registry_cls.return_value = mock_registry
        mock_post.side_effect = requests.exceptions.ConnectionError(
            "Connection refused"
        )

        shell = SynapseShell()
        shell.send_to_agent("claude", "hello")

        captured = capsys.readouterr()
        assert "Error" in captured.out


# ============================================================
# Wait For Response Tests
# ============================================================


class TestWaitForResponse:
    """Test wait_for_response() method."""

    @patch("synapse.shell.requests.get")
    @patch("synapse.shell.AgentRegistry")
    def test_wait_for_idle_and_get_context(self, mock_registry_cls, mock_get, capsys):
        """Should wait for IDLE status and extract context."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "IDLE",
            "context": "This is the response from claude",
        }
        mock_get.return_value = mock_response

        shell = SynapseShell()
        shell.wait_for_response("http://localhost:8100", "claude", timeout=5)

        captured = capsys.readouterr()
        assert "Waiting for claude" in captured.out
        assert "response from claude" in captured.out

    @patch("synapse.shell.time.sleep")
    @patch("synapse.shell.requests.get")
    @patch("synapse.shell.AgentRegistry")
    def test_wait_for_response_timeout(
        self, mock_registry_cls, mock_get, mock_sleep, capsys
    ):
        """Should timeout when agent doesn't become IDLE."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "BUSY",
            "context": "",
        }
        mock_get.return_value = mock_response

        shell = SynapseShell()
        shell.wait_for_response("http://localhost:8100", "claude", timeout=2)

        captured = capsys.readouterr()
        assert "Timeout" in captured.out

    @patch("synapse.shell.time.sleep")
    @patch("synapse.shell.requests.get")
    @patch("synapse.shell.AgentRegistry")
    def test_wait_for_response_handles_errors(
        self, mock_registry_cls, mock_get, mock_sleep, capsys
    ):
        """Should handle request errors during wait."""
        import requests

        mock_get.side_effect = requests.exceptions.ConnectionError()

        shell = SynapseShell()
        shell.wait_for_response("http://localhost:8100", "claude", timeout=2)

        captured = capsys.readouterr()
        assert "Timeout" in captured.out


# ============================================================
# List Command Tests
# ============================================================


class TestListCommand:
    """Test do_list() command."""

    @patch("synapse.shell.AgentRegistry")
    def test_list_no_agents(self, mock_registry_cls, capsys):
        """Should show message when no agents running."""
        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = {}
        mock_registry_cls.return_value = mock_registry

        shell = SynapseShell()
        shell.do_list("")

        captured = capsys.readouterr()
        assert "No agents running" in captured.out

    @patch("synapse.shell.AgentRegistry")
    def test_list_shows_agents(self, mock_registry_cls, capsys):
        """Should list running agents."""
        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = {
            "agent-1": {
                "agent_type": "claude",
                "port": 8100,
                "status": "IDLE",
                "endpoint": "http://localhost:8100",
            },
            "agent-2": {
                "agent_type": "gemini",
                "port": 8110,
                "status": "BUSY",
                "endpoint": "http://localhost:8110",
            },
        }
        mock_registry_cls.return_value = mock_registry

        shell = SynapseShell()
        shell.do_list("")

        captured = capsys.readouterr()
        assert "claude" in captured.out
        assert "8100" in captured.out
        assert "IDLE" in captured.out
        assert "gemini" in captured.out
        assert "8110" in captured.out
        assert "BUSY" in captured.out


# ============================================================
# Status Command Tests
# ============================================================


class TestStatusCommand:
    """Test do_status() command."""

    @patch("synapse.shell.AgentRegistry")
    def test_status_no_arg(self, mock_registry_cls, capsys):
        """Should show usage when no agent specified."""
        shell = SynapseShell()
        shell.do_status("")

        captured = capsys.readouterr()
        assert "Usage" in captured.out

    @patch("synapse.shell.AgentRegistry")
    def test_status_agent_not_found(self, mock_registry_cls, capsys):
        """Should show error when agent not found."""
        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = {}
        mock_registry_cls.return_value = mock_registry

        shell = SynapseShell()
        shell.do_status("nonexistent")

        captured = capsys.readouterr()
        assert "not found" in captured.out

    @patch("synapse.shell.requests.get")
    @patch("synapse.shell.AgentRegistry")
    def test_status_shows_agent_status(self, mock_registry_cls, mock_get, capsys):
        """Should show agent status and context."""
        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = {
            "agent-1": {
                "agent_type": "claude",
                "endpoint": "http://localhost:8100",
            }
        }
        mock_registry_cls.return_value = mock_registry

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "IDLE",
            "context": "Agent ready for input",
        }
        mock_get.return_value = mock_response

        shell = SynapseShell()
        shell.do_status("claude")

        captured = capsys.readouterr()
        assert "IDLE" in captured.out
        assert "ready for input" in captured.out

    @patch("synapse.shell.requests.get")
    @patch("synapse.shell.AgentRegistry")
    def test_status_handles_request_error(self, mock_registry_cls, mock_get, capsys):
        """Should handle request errors."""
        import requests

        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = {
            "agent-1": {
                "agent_type": "claude",
                "endpoint": "http://localhost:8100",
            }
        }
        mock_registry_cls.return_value = mock_registry
        mock_get.side_effect = requests.exceptions.ConnectionError("Connection refused")

        shell = SynapseShell()
        shell.do_status("claude")

        captured = capsys.readouterr()
        assert "Error" in captured.out


# ============================================================
# Exit/Quit Command Tests
# ============================================================


class TestExitCommands:
    """Test exit/quit commands."""

    @patch("synapse.shell.AgentRegistry")
    def test_do_exit_returns_true(self, mock_registry_cls, capsys):
        """do_exit should return True to exit cmdloop."""
        shell = SynapseShell()
        result = shell.do_exit("")

        assert result is True
        captured = capsys.readouterr()
        assert "Goodbye" in captured.out

    @patch("synapse.shell.AgentRegistry")
    def test_do_quit_returns_true(self, mock_registry_cls, capsys):
        """do_quit should return True to exit cmdloop."""
        shell = SynapseShell()
        result = shell.do_quit("")

        assert result is True

    @patch("synapse.shell.AgentRegistry")
    def test_do_eof_returns_true(self, mock_registry_cls, capsys):
        """do_EOF should return True (Ctrl+D handling)."""
        shell = SynapseShell()
        result = shell.do_EOF("")

        assert result is True


# ============================================================
# Empty Line Tests
# ============================================================


class TestEmptyLine:
    """Test emptyline() method."""

    @patch("synapse.shell.AgentRegistry")
    def test_emptyline_returns_false(self, mock_registry_cls):
        """emptyline should return False (do nothing)."""
        shell = SynapseShell()
        result = shell.emptyline()

        assert result is False


# ============================================================
# Main Function Tests
# ============================================================


class TestMainFunction:
    """Test main() function."""

    @patch("synapse.shell.SynapseShell")
    def test_main_creates_shell_and_runs(self, mock_shell_cls):
        """main() should create shell and run cmdloop."""
        from synapse.shell import main

        mock_shell = MagicMock()
        mock_shell_cls.return_value = mock_shell

        main()

        mock_shell.cmdloop.assert_called_once()

    @patch("synapse.shell.SynapseShell")
    def test_main_handles_keyboard_interrupt(self, mock_shell_cls, capsys):
        """main() should handle Ctrl+C gracefully."""
        from synapse.shell import main

        mock_shell = MagicMock()
        mock_shell.cmdloop.side_effect = KeyboardInterrupt()
        mock_shell_cls.return_value = mock_shell

        main()

        captured = capsys.readouterr()
        assert "Goodbye" in captured.out
