import logging
from unittest.mock import MagicMock, patch

from synapse.tools.a2a import _find_sender_by_pid, build_sender_info


class TestSenderDetection:
    @patch("synapse.tools.a2a.os.getpid")
    @patch("synapse.tools.a2a.AgentRegistry")
    @patch("synapse.tools.a2a.is_descendant_of")
    def test_find_sender_by_pid_success(
        self, mock_is_descendant, mock_registry_cls, mock_getpid
    ):
        # Setup
        mock_getpid.return_value = 1000

        agent_info = {
            "agent_id": "synapse-claude-8100",
            "agent_type": "claude",
            "pid": 500,
            "endpoint": "http://localhost:8100",
        }

        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = {"synapse-claude-8100": agent_info}
        mock_registry_cls.return_value = mock_registry

        # Mock descendant check: 1000 is descendant of 500
        mock_is_descendant.side_effect = (
            lambda child, ancestor: child == 1000 and ancestor == 500
        )

        # Execute
        result = _find_sender_by_pid()

        # Verify
        assert result["sender_id"] == "synapse-claude-8100"
        assert result["sender_type"] == "claude"
        assert result["sender_endpoint"] == "http://localhost:8100"

    @patch("synapse.tools.a2a.os.getpid")
    @patch("synapse.tools.a2a.AgentRegistry")
    @patch("synapse.tools.a2a.is_descendant_of")
    def test_find_sender_by_pid_no_match(
        self, mock_is_descendant, mock_registry_cls, mock_getpid
    ):
        # Setup
        mock_getpid.return_value = 1000
        mock_is_descendant.return_value = False

        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = {"synapse-claude-8100": {"pid": 500}}
        mock_registry_cls.return_value = mock_registry

        # Execute
        result = _find_sender_by_pid()

        # Verify
        assert result == {}

    @patch("synapse.tools.a2a.os.getpid")
    @patch("synapse.tools.a2a.AgentRegistry")
    @patch("synapse.tools.a2a.is_descendant_of")
    @patch("synapse.tools.a2a.os.ttyname")
    @patch("synapse.tools.a2a.sys.stdin")
    def test_find_sender_by_tty_fallback(
        self,
        mock_stdin,
        mock_ttyname,
        mock_is_descendant,
        mock_registry_cls,
        mock_getpid,
    ):
        # Setup
        mock_getpid.return_value = 1000
        mock_is_descendant.return_value = False  # PID match fails

        mock_stdin.fileno.return_value = 0
        mock_ttyname.return_value = "/dev/ttys001"

        agent_info = {
            "agent_id": "synapse-claude-8100",
            "agent_type": "claude",
            "tty_device": "/dev/ttys001",
        }

        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = {"synapse-claude-8100": agent_info}
        mock_registry_cls.return_value = mock_registry

        # Execute
        result = _find_sender_by_pid()

        # Verify
        assert result["sender_id"] == "synapse-claude-8100"

    @patch("synapse.tools.a2a.os.getpid")
    @patch("synapse.tools.a2a.AgentRegistry")
    def test_find_sender_by_pid_exception_logged(
        self, mock_registry_cls, mock_getpid, caplog
    ):
        # Setup: Registry throws exception
        mock_registry_cls.side_effect = Exception("Registry error")

        # Enable propagation temporarily so caplog can capture log messages
        # (synapse logger has propagate=False when logging_config is loaded)
        loggers_to_fix = [
            logging.getLogger("synapse"),
            logging.getLogger("synapse.tools"),
            logging.getLogger("synapse.tools.a2a"),
        ]
        orig_propagate = {lg.name: lg.propagate for lg in loggers_to_fix}
        for lg in loggers_to_fix:
            lg.propagate = True
        try:
            with caplog.at_level(logging.ERROR, logger="synapse.tools.a2a"):
                result = _find_sender_by_pid()
        finally:
            for lg in loggers_to_fix:
                lg.propagate = orig_propagate[lg.name]

        # Verify
        assert result == {}
        assert "Error in _find_sender_by_pid" in caplog.text
        assert "Registry error" in caplog.text

    @patch("synapse.tools.a2a.os.environ.get")
    @patch("synapse.tools.a2a.AgentRegistry")
    @patch("synapse.tools.a2a._find_sender_by_pid")
    def test_build_sender_info_priority(
        self, mock_find_pid, mock_registry_cls, mock_env_get
    ):
        # 1. Test explicit sender (highest priority)
        # Already tested in test_a2a_tool.py mostly, but good to have here

        # 2. Test SYNAPSE_AGENT_ID priority
        mock_env_get.side_effect = (
            lambda k, d=None: "synapse-claude-8100" if k == "SYNAPSE_AGENT_ID" else d
        )

        agent_info = {"agent_id": "synapse-claude-8100", "agent_type": "claude"}
        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = {"synapse-claude-8100": agent_info}
        mock_registry_cls.return_value = mock_registry

        result = build_sender_info(None)
        assert result["sender_id"] == "synapse-claude-8100"
        mock_find_pid.assert_not_called()

        # 3. SYNAPSE_AGENT_ID takes priority even if NOT in registry
        mock_registry.list_agents.return_value = {}
        mock_find_pid.return_value = {"sender_id": "pid-detected"}

        result = build_sender_info(None)
        assert result["sender_id"] == "synapse-claude-8100"
        mock_find_pid.assert_not_called()
