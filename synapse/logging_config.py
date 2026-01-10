"""Logging configuration for Synapse A2A.

This module provides centralized logging configuration with support for:
- Console output (stderr)
- File logging to ~/.synapse/logs/
- Debug mode via environment variable

Usage:
    from synapse.logging_config import setup_logging, get_logger

    # At application startup
    setup_logging()

    # In modules
    logger = get_logger(__name__)
    logger.info("Message")

Environment variables:
    SYNAPSE_LOG_LEVEL: Set log level (DEBUG, INFO, WARNING, ERROR)
    SYNAPSE_LOG_FILE: Enable file logging (true/false)
"""

import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# Default log directory
LOG_DIR = Path.home() / ".synapse" / "logs"

# Log format
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_FORMAT_DEBUG = "%(asctime)s [%(levelname)s] %(name)s:%(lineno)d: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def get_log_level() -> int:
    """Get log level from environment variable."""
    level_str = os.environ.get("SYNAPSE_LOG_LEVEL", "INFO").upper()
    levels = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
    }
    return levels.get(level_str, logging.INFO)


def is_file_logging_enabled() -> bool:
    """Check if file logging is enabled."""
    return os.environ.get("SYNAPSE_LOG_FILE", "false").lower() in ("true", "1")


def setup_logging(
    level: int | None = None,
    log_file: bool | None = None,
    agent_name: str | None = None,
) -> None:
    """Configure logging for Synapse.

    Args:
        level: Log level (uses SYNAPSE_LOG_LEVEL if not specified)
        log_file: Enable file logging (uses SYNAPSE_LOG_FILE if not specified)
        agent_name: Agent name for log file naming
    """
    if level is None:
        level = get_log_level()

    if log_file is None:
        log_file = is_file_logging_enabled()

    # Use debug format for DEBUG level
    log_format = LOG_FORMAT_DEBUG if level == logging.DEBUG else LOG_FORMAT

    # Configure root logger for synapse
    synapse_logger = logging.getLogger("synapse")
    synapse_logger.setLevel(level)

    # Remove existing handlers
    synapse_logger.handlers.clear()

    # Console handler (stderr)
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(level)
    console_handler.setFormatter(logging.Formatter(log_format, DATE_FORMAT))
    synapse_logger.addHandler(console_handler)

    # File handler (if enabled)
    if log_file:
        LOG_DIR.mkdir(parents=True, exist_ok=True)

        if agent_name:
            log_filename = f"{agent_name}.log"
        else:
            log_filename = f"synapse_{datetime.now().strftime('%Y%m%d')}.log"

        file_handler = logging.FileHandler(
            LOG_DIR / log_filename,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(logging.Formatter(log_format, DATE_FORMAT))
        synapse_logger.addHandler(file_handler)

    # Don't propagate to root logger
    synapse_logger.propagate = False


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the given name.

    Args:
        name: Logger name (usually __name__)

    Returns:
        Logger instance
    """
    # Ensure name is under synapse namespace
    if not name.startswith("synapse"):
        name = f"synapse.{name}"
    return logging.getLogger(name)


def set_debug_mode(enabled: bool = True) -> None:
    """Enable or disable debug mode.

    Args:
        enabled: Whether to enable debug mode
    """
    level = logging.DEBUG if enabled else logging.INFO
    logger = logging.getLogger("synapse")
    logger.setLevel(level)
    for handler in logger.handlers:
        handler.setLevel(level)
