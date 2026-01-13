"""Tests for Synapse logging configuration."""

import logging
import os
import sys
from unittest.mock import MagicMock, patch

from synapse.logging_config import (
    get_log_level,
    get_logger,
    is_file_logging_enabled,
    set_debug_mode,
    setup_logging,
)


class TestLoggingConfig:
    """Test logging configuration."""

    def setup_method(self):
        """Reset logging before each test."""
        # Reset root logger handlers
        logging.getLogger().handlers = []
        # Reset synapse logger
        logger = logging.getLogger("synapse")
        logger.handlers = []
        logger.setLevel(logging.NOTSET)
        logger.propagate = True

    def test_get_log_level_default(self):
        """Test get_log_level returns INFO by default."""
        with patch.dict(os.environ, {}, clear=True):
            assert get_log_level() == logging.INFO

    def test_get_log_level_env(self):
        """Test get_log_level respects environment variable."""
        with patch.dict(os.environ, {"SYNAPSE_LOG_LEVEL": "DEBUG"}):
            assert get_log_level() == logging.DEBUG
        with patch.dict(os.environ, {"SYNAPSE_LOG_LEVEL": "WARNING"}):
            assert get_log_level() == logging.WARNING
        with patch.dict(os.environ, {"SYNAPSE_LOG_LEVEL": "ERROR"}):
            assert get_log_level() == logging.ERROR
        with patch.dict(os.environ, {"SYNAPSE_LOG_LEVEL": "INVALID"}):
            assert get_log_level() == logging.INFO

    def test_is_file_logging_enabled(self):
        """Test is_file_logging_enabled."""
        with patch.dict(os.environ, {}, clear=True):
            assert not is_file_logging_enabled()
        with patch.dict(os.environ, {"SYNAPSE_LOG_FILE": "true"}):
            assert is_file_logging_enabled()
        with patch.dict(os.environ, {"SYNAPSE_LOG_FILE": "1"}):
            assert is_file_logging_enabled()
        with patch.dict(os.environ, {"SYNAPSE_LOG_FILE": "false"}):
            assert not is_file_logging_enabled()

    def test_get_logger(self):
        """Test get_logger ensures namespace."""
        logger = get_logger("my_module")
        assert logger.name == "synapse.my_module"

        logger = get_logger("synapse.core")
        assert logger.name == "synapse.core"

    @patch("synapse.logging_config.logging.StreamHandler")
    def test_setup_logging_console(self, mock_stream_handler):
        """Test setup_logging configures console logging."""
        mock_handler_instance = MagicMock()
        mock_stream_handler.return_value = mock_handler_instance

        setup_logging(level=logging.INFO, log_file=False)

        logger = logging.getLogger("synapse")
        assert logger.level == logging.INFO
        assert not logger.propagate
        assert len(logger.handlers) == 1
        assert logger.handlers[0] == mock_handler_instance
        mock_stream_handler.assert_called_with(sys.stderr)

    @patch("synapse.logging_config.logging.FileHandler")
    @patch("synapse.logging_config.Path.mkdir")
    def test_setup_logging_file(self, mock_mkdir, mock_file_handler):
        """Test setup_logging configures file logging."""
        mock_handler_instance = MagicMock()
        mock_file_handler.return_value = mock_handler_instance

        with patch.dict(os.environ, {"SYNAPSE_LOG_FILE": "true"}):
            setup_logging(level=logging.INFO)

        logger = logging.getLogger("synapse")
        assert len(logger.handlers) == 2  # Console + File
        mock_mkdir.assert_called()
        mock_file_handler.assert_called()

    @patch("synapse.logging_config.logging.FileHandler")
    @patch("synapse.logging_config.Path.mkdir")
    def test_setup_logging_file_with_agent_name(self, mock_mkdir, mock_file_handler):
        """Test setup_logging with agent name."""
        mock_handler_instance = MagicMock()
        mock_file_handler.return_value = mock_handler_instance

        setup_logging(level=logging.INFO, log_file=True, agent_name="test-agent")

        # Verify filename contains agent name
        args, _ = mock_file_handler.call_args
        assert "test-agent.log" in str(args[0])

    def test_set_debug_mode(self):
        """Test set_debug_mode toggles log level."""
        setup_logging(level=logging.INFO, log_file=False)
        logger = logging.getLogger("synapse")

        set_debug_mode(True)
        assert logger.level == logging.DEBUG
        for handler in logger.handlers:
            assert handler.level == logging.DEBUG

        set_debug_mode(False)
        assert logger.level == logging.INFO
        for handler in logger.handlers:
            assert handler.level == logging.INFO
