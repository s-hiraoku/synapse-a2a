"""
Centralized path management for Synapse.

Provides functions to get standard paths for history DB, registry,
and external registry directories. All paths can be overridden via
environment variables.
"""

import os
from pathlib import Path


def _resolve_path(env_var: str, default: Path) -> str:
    """Resolve a path from an environment variable or fall back to a default.

    If the environment variable is set, its value is expanded
    (``~`` and ``$VAR`` substitution) and returned. Otherwise the
    *default* path is returned.

    Args:
        env_var: Name of the environment variable to check.
        default: Default path when the environment variable is unset.

    Returns:
        Resolved path string.
    """
    env_path = os.environ.get(env_var)
    if env_path:
        return str(Path(os.path.expanduser(os.path.expandvars(env_path))))
    return str(default)


def get_history_db_path() -> str:
    """Get the path to the history database.

    Override with SYNAPSE_HISTORY_DB_PATH environment variable.
    """
    return _resolve_path(
        "SYNAPSE_HISTORY_DB_PATH",
        Path.home() / ".synapse" / "history" / "history.db",
    )


def get_registry_dir() -> str:
    """Get the path to the agent registry directory.

    Override with SYNAPSE_REGISTRY_DIR environment variable.
    """
    return _resolve_path(
        "SYNAPSE_REGISTRY_DIR",
        Path.home() / ".a2a" / "registry",
    )


def get_external_registry_dir() -> str:
    """Get the path to the external agent registry directory.

    Override with SYNAPSE_EXTERNAL_REGISTRY_DIR environment variable.
    """
    return _resolve_path(
        "SYNAPSE_EXTERNAL_REGISTRY_DIR",
        Path.home() / ".a2a" / "external",
    )


def get_synapse_skills_dir() -> str:
    """Get the path to the central synapse skills directory.

    Override with SYNAPSE_SKILLS_DIR environment variable.
    """
    return _resolve_path(
        "SYNAPSE_SKILLS_DIR",
        Path.home() / ".synapse" / "skills",
    )
