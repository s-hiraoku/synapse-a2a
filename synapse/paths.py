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


def get_reply_target_dir() -> str:
    """Get the path to the reply target persistence directory.

    Override with SYNAPSE_REPLY_TARGET_DIR environment variable.
    """
    return _resolve_path(
        "SYNAPSE_REPLY_TARGET_DIR",
        Path.home() / ".a2a" / "reply",
    )


def get_external_registry_dir() -> str:
    """Get the path to the external agent registry directory.

    Override with SYNAPSE_EXTERNAL_REGISTRY_DIR environment variable.
    """
    return _resolve_path(
        "SYNAPSE_EXTERNAL_REGISTRY_DIR",
        Path.home() / ".a2a" / "external",
    )


def get_shared_memory_db_path() -> str:
    """Get the path to the shared memory database.

    Default: ~/.synapse/memory.db (user-global, shared across projects).
    Override with SYNAPSE_SHARED_MEMORY_DB_PATH environment variable.
    """
    return _resolve_path(
        "SYNAPSE_SHARED_MEMORY_DB_PATH",
        Path.home() / ".synapse" / "memory.db",
    )


def get_canvas_db_path() -> str:
    """Get the path to the canvas database.

    Default: ~/.synapse/canvas.db (user-global, shared across projects).
    Override with SYNAPSE_CANVAS_DB_PATH environment variable.
    """
    return _resolve_path(
        "SYNAPSE_CANVAS_DB_PATH",
        Path.home() / ".synapse" / "canvas.db",
    )


def get_workflow_runs_db_path() -> str:
    """Get the path to the workflow runs database.

    Default: .synapse/workflow_runs.db (project-local).
    Override with SYNAPSE_WORKFLOW_RUNS_DB_PATH environment variable.
    """
    return _resolve_path(
        "SYNAPSE_WORKFLOW_RUNS_DB_PATH",
        Path(".synapse") / "workflow_runs.db",
    )


def get_file_safety_db_path() -> str:
    """Get the path to the file safety database.

    Default: .synapse/file_safety.db (project-local).
    Override with SYNAPSE_FILE_SAFETY_DB_PATH environment variable.
    """
    return _resolve_path(
        "SYNAPSE_FILE_SAFETY_DB_PATH",
        Path(".synapse") / "file_safety.db",
    )


def get_observation_db_path() -> str:
    """Get the path to the observations database.

    Default: .synapse/observations.db (project-local).
    Override with SYNAPSE_OBSERVATION_DB_PATH environment variable.
    """
    return _resolve_path(
        "SYNAPSE_OBSERVATION_DB_PATH",
        Path(".synapse") / "observations.db",
    )


def get_instinct_db_path() -> str:
    """Get the path to the instincts database.

    Default: .synapse/instincts.db (project-local).
    Override with SYNAPSE_INSTINCT_DB_PATH environment variable.
    """
    return _resolve_path(
        "SYNAPSE_INSTINCT_DB_PATH",
        Path(".synapse") / "instincts.db",
    )


def get_synapse_skills_dir() -> str:
    """Get the path to the central synapse skills directory.

    Override with SYNAPSE_SKILLS_DIR environment variable.
    """
    return _resolve_path(
        "SYNAPSE_SKILLS_DIR",
        Path.home() / ".synapse" / "skills",
    )


def get_waiting_debug_path() -> str:
    """Get the path to the WAITING debug JSONL file.

    Default: ~/.synapse/waiting_debug.jsonl (user-global, resolved lazily
    so tests that override ``HOME`` take effect).
    Override with SYNAPSE_WAITING_DEBUG_PATH environment variable.
    """
    return _resolve_path(
        "SYNAPSE_WAITING_DEBUG_PATH",
        Path.home() / ".synapse" / "waiting_debug.jsonl",
    )
