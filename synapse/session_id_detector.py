"""Detect CLI tool session IDs from the filesystem.

Each CLI agent stores session data in tool-specific locations.  This module
provides ``detect_session_id()`` (most-recent single ID) and
``list_sessions()`` (all sessions with metadata) for Claude, Gemini, Codex,
and Copilot.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Callable types for dispatcher dicts — each _detect_* / _list_* has
# different kwargs, so we use a broad signature here.
_Detector = Callable[..., str | None]
_Lister = Callable[..., list[Any]]


# ── dataclass ────────────────────────────────────────────────────


@dataclass
class SessionInfo:
    """Metadata for a single CLI session file."""

    profile: str
    session_id: str
    path: Path
    modified_at: float  # mtime
    size_bytes: int


# ── public API ───────────────────────────────────────────────────


def detect_session_id(
    profile: str | None,
    working_dir: str,
    **home_overrides: Path,
) -> str | None:
    """Return the most-recent session ID for *profile*, or ``None``.

    Args:
        profile: Agent profile name (``"claude"``, ``"gemini"``, …).
        working_dir: Project working directory (needed for Claude/Gemini).
        **home_overrides: DI overrides such as ``claude_home=…``.
    """
    detectors: dict[str, _Detector] = {
        "claude": _detect_claude,
        "gemini": _detect_gemini,
        "codex": _detect_codex,
        "copilot": _detect_copilot,
    }
    fn = detectors.get(profile or "")
    if fn is None:
        return None

    try:
        return fn(working_dir, **home_overrides)
    except Exception:
        logger.debug("session_id detection failed for %s", profile, exc_info=True)
        return None


def list_sessions(
    profile: str | None,
    working_dir: str,
    *,
    limit: int = 20,
    **home_overrides: Path,
) -> list[SessionInfo]:
    """List CLI session files, newest first.

    Args:
        profile: Filter to a single profile, or ``None`` for all.
        working_dir: Project working directory.
        limit: Max number of results to return.
        **home_overrides: DI overrides.
    """
    if limit <= 0:
        return []

    listers: dict[str, _Lister] = {
        "claude": _list_claude_sessions,
        "gemini": _list_gemini_sessions,
        "codex": _list_codex_sessions,
        "copilot": _list_copilot_sessions,
    }

    if profile is not None:
        if profile not in listers:
            return []
        targets: dict[str, _Lister] = {profile: listers[profile]}
    else:
        targets = listers

    results: list[SessionInfo] = []
    for pname, fn in targets.items():
        try:
            results.extend(fn(working_dir, **home_overrides))
        except Exception:
            logger.debug("list_sessions failed for %s", pname, exc_info=True)

    results.sort(key=lambda s: s.modified_at, reverse=True)
    return results[:limit]


# ── shared helpers ───────────────────────────────────────────────


def _find_most_recent(directory: Path, glob_pattern: str) -> Path | None:
    """Return the file with the highest mtime matching *glob_pattern*."""
    if not directory.is_dir():
        return None
    best: Path | None = None
    best_mtime: float = -1
    for p in directory.glob(glob_pattern):
        if p.is_file():
            mt = p.stat().st_mtime
            if mt > best_mtime:
                best_mtime = mt
                best = p
    return best


def _collect_files(
    directory: Path, glob_pattern: str, profile: str
) -> list[SessionInfo]:
    """Collect all matching files as SessionInfo list."""
    if not directory.is_dir():
        return []
    results: list[SessionInfo] = []
    for p in directory.glob(glob_pattern):
        if p.is_file():
            st = p.stat()
            results.append(
                SessionInfo(
                    profile=profile,
                    session_id=p.stem,
                    path=p,
                    modified_at=st.st_mtime,
                    size_bytes=st.st_size,
                )
            )
    return results


# ── Claude ───────────────────────────────────────────────────────


def _claude_project_dir(working_dir: str, claude_home: Path | None = None) -> Path:
    """Resolve Claude's project directory for *working_dir*."""
    home = claude_home or Path.home() / ".claude"
    project_hash = working_dir.replace("/", "-")
    return home / "projects" / project_hash


def _detect_claude(
    working_dir: str, *, claude_home: Path | None = None, **_kw: object
) -> str | None:
    proj = _claude_project_dir(working_dir, claude_home)
    best = _find_most_recent(proj, "*.jsonl")
    return best.stem if best else None


def _list_claude_sessions(
    working_dir: str, *, claude_home: Path | None = None, **_kw: object
) -> list[SessionInfo]:
    proj = _claude_project_dir(working_dir, claude_home)
    return _collect_files(proj, "*.jsonl", "claude")


# ── Gemini ───────────────────────────────────────────────────────


def _gemini_chats_dir(working_dir: str, gemini_home: Path | None = None) -> Path | None:
    """Resolve Gemini's chats directory, checking named mapping first."""
    home = gemini_home or Path.home() / ".gemini"

    # Check projects.json for a named mapping
    projects_json = home / "projects.json"
    if projects_json.is_file():
        try:
            mapping = json.loads(projects_json.read_text())
            if isinstance(mapping, dict):
                ref: str | None = mapping.get(working_dir)
                if ref:
                    chats: Path = home / "tmp" / ref / "chats"
                    if chats.is_dir():
                        return chats
        except (json.JSONDecodeError, OSError):
            pass

    # Fallback: SHA256 hash
    proj_hash = hashlib.sha256(working_dir.encode()).hexdigest()
    chats = home / "tmp" / proj_hash / "chats"
    return chats if chats.is_dir() else None


def _detect_gemini(
    working_dir: str, *, gemini_home: Path | None = None, **_kw: object
) -> str | None:
    chats = _gemini_chats_dir(working_dir, gemini_home)
    if chats is None:
        return None
    best = _find_most_recent(chats, "*.json")
    return best.stem if best else None


def _list_gemini_sessions(
    working_dir: str, *, gemini_home: Path | None = None, **_kw: object
) -> list[SessionInfo]:
    chats = _gemini_chats_dir(working_dir, gemini_home)
    if chats is None:
        return []
    return _collect_files(chats, "*.json", "gemini")


# ── Codex ────────────────────────────────────────────────────────


def _codex_sessions_dir(codex_home: Path | None = None) -> Path:
    home = codex_home or Path.home() / ".codex"
    return home / "sessions"


def _detect_codex(
    _working_dir: str, *, codex_home: Path | None = None, **_kw: object
) -> str | None:
    sessions = _codex_sessions_dir(codex_home)
    # Codex stores in year/month/day subdirs — glob recursively
    best = _find_most_recent(sessions, "**/*.jsonl")
    return best.stem if best else None


def _list_codex_sessions(
    _working_dir: str, *, codex_home: Path | None = None, **_kw: object
) -> list[SessionInfo]:
    sessions = _codex_sessions_dir(codex_home)
    return _collect_files(sessions, "**/*.jsonl", "codex")


# ── Copilot ──────────────────────────────────────────────────────


def _copilot_state_dir(copilot_home: Path | None = None) -> Path:
    home = copilot_home or Path.home() / ".copilot"
    return home / "session-state"


def _detect_copilot(
    _working_dir: str, *, copilot_home: Path | None = None, **_kw: object
) -> str | None:
    state = _copilot_state_dir(copilot_home)
    best = _find_most_recent(state, "*.jsonl")
    return best.stem if best else None


def _list_copilot_sessions(
    _working_dir: str, *, copilot_home: Path | None = None, **_kw: object
) -> list[SessionInfo]:
    state = _copilot_state_dir(copilot_home)
    return _collect_files(state, "*.jsonl", "copilot")
