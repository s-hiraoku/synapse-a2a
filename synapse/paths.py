"""
Centralized path management for Synapse.

Provides functions to get standard paths for history DB, registry,
and external registry directories. All paths can be overridden via
environment variables.
"""

import os
from pathlib import Path


def get_history_db_path() -> str:
    """Get the path to the history database.

    Override with SYNAPSE_HISTORY_DB_PATH environment variable.

    Returns:
        Path string to the history database file.
    """
    env_path = os.environ.get("SYNAPSE_HISTORY_DB_PATH")
    if env_path:
        expanded = os.path.expanduser(os.path.expandvars(env_path))
        return str(Path(expanded))
    return str(Path.home() / ".synapse" / "history" / "history.db")


def get_registry_dir() -> str:
    """Get the path to the agent registry directory.

    Override with SYNAPSE_REGISTRY_DIR environment variable.

    Returns:
        Path string to the registry directory.
    """
    env_path = os.environ.get("SYNAPSE_REGISTRY_DIR")
    if env_path:
        expanded = os.path.expanduser(os.path.expandvars(env_path))
        return str(Path(expanded))
    return str(Path.home() / ".a2a" / "registry")


def get_external_registry_dir() -> str:
    """Get the path to the external agent registry directory.

    Override with SYNAPSE_EXTERNAL_REGISTRY_DIR environment variable.

    Returns:
        Path string to the external registry directory.
    """
    env_path = os.environ.get("SYNAPSE_EXTERNAL_REGISTRY_DIR")
    if env_path:
        expanded = os.path.expanduser(os.path.expandvars(env_path))
        return str(Path(expanded))
    return str(Path.home() / ".a2a" / "external")
