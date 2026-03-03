"""Session save/restore for team configurations.

Saves running agent configurations as named JSON snapshots
and restores them later via ``spawn_agent()``.

Storage:
- Project scope: ``.synapse/sessions/<name>.json``
- User scope: ``~/.synapse/sessions/<name>.json``
"""

from __future__ import annotations

import json
import logging
import re
from argparse import Namespace
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

Scope = Literal["project", "user"]
_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")


class SessionError(ValueError):
    """Raised for invalid session operations."""


@dataclass
class SessionAgent:
    """Agent entry within a saved session."""

    profile: str
    name: str | None = None
    role: str | None = None
    skill_set: str | None = None
    worktree: bool = False


@dataclass
class Session:
    """A named snapshot of a team configuration."""

    session_name: str
    agents: list[SessionAgent]
    working_dir: str
    created_at: float
    scope: Scope
    agent_count: int = field(init=False)
    path: Path | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        self.agent_count = len(self.agents)


class SessionStore:
    """Persist and retrieve session snapshots from project/user scopes."""

    def __init__(
        self,
        *,
        project_dir: Path | None = None,
        user_dir: Path | None = None,
    ) -> None:
        self.project_dir = project_dir or (Path.cwd() / ".synapse" / "sessions")
        self.user_dir = user_dir or (Path.home() / ".synapse" / "sessions")

    # ── public API ───────────────────────────────────────────

    def save(self, session: Session) -> Path:
        """Save a session to disk (upsert)."""
        self._validate_session_name(session.session_name)
        target_dir = self._scope_dir(session.scope)
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / f"{session.session_name}.json"

        data = {
            "session_name": session.session_name,
            "agents": [
                {
                    "profile": a.profile,
                    "name": a.name,
                    "role": a.role,
                    "skill_set": a.skill_set,
                    "worktree": a.worktree,
                }
                for a in session.agents
            ],
            "working_dir": session.working_dir,
            "created_at": session.created_at,
            "scope": session.scope,
            "agent_count": session.agent_count,
        }
        target_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return target_path

    def load(
        self,
        name: str,
        scope: Scope | None = None,
    ) -> Session | None:
        """Load a session by name.

        When *scope* is None, searches project first then user.
        """
        self._validate_session_name(name)
        if scope is not None:
            return self._load_from_dir(name, self._scope_dir(scope), scope)

        # Project-first resolution
        result = self._load_from_dir(name, self.project_dir, "project")
        if result is not None:
            return result
        return self._load_from_dir(name, self.user_dir, "user")

    def list_sessions(self, scope: Scope | None = None) -> list[Session]:
        """List sessions, optionally filtered by scope."""
        sessions: list[Session] = []
        dirs: list[tuple[Scope, Path]] = []

        if scope is None or scope == "project":
            dirs.append(("project", self.project_dir))
        if scope is None or scope == "user":
            dirs.append(("user", self.user_dir))

        for sc, dir_path in dirs:
            if not dir_path.is_dir():
                continue
            for file_path in sorted(dir_path.glob("*.json")):
                try:
                    session = self._parse_file(file_path, sc)
                    sessions.append(session)
                except (json.JSONDecodeError, KeyError, TypeError) as e:
                    logger.warning("Skipping invalid session file %s: %s", file_path, e)
        return sessions

    def delete(self, name: str, scope: Scope | None = None) -> bool:
        """Delete a session by name. Returns True if deleted."""
        self._validate_session_name(name)
        if scope is not None:
            path = self._scope_dir(scope) / f"{name}.json"
            if path.is_file():
                path.unlink()
                return True
            return False

        # Try project first, then user
        for sc in ("project", "user"):
            path = self._scope_dir(sc) / f"{name}.json"
            if path.is_file():
                path.unlink()
                return True
        return False

    # ── validation ───────────────────────────────────────────

    @staticmethod
    def _validate_session_name(name: str) -> None:
        """Validate session name (same rules as worktree names)."""
        if not name or not _NAME_PATTERN.fullmatch(name):
            raise SessionError(
                f"Invalid session name '{name}'. "
                "Must start with alphanumeric and contain only "
                "alphanumeric, dots, hyphens, or underscores."
            )

    # ── internal ─────────────────────────────────────────────

    def _scope_dir(self, scope: Scope) -> Path:
        if scope == "project":
            return self.project_dir
        if scope == "user":
            return self.user_dir
        raise SessionError(f"unsupported scope: {scope}")

    def _load_from_dir(self, name: str, dir_path: Path, scope: Scope) -> Session | None:
        file_path = dir_path / f"{name}.json"
        if not file_path.is_file():
            return None
        try:
            return self._parse_file(file_path, scope)
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning("Failed to load session %s: %s", file_path, e)
            return None

    @staticmethod
    def _parse_file(file_path: Path, scope: Scope) -> Session:
        raw = json.loads(file_path.read_text(encoding="utf-8"))
        agents = [
            SessionAgent(
                profile=a["profile"],
                name=a.get("name"),
                role=a.get("role"),
                skill_set=a.get("skill_set"),
                worktree=a.get("worktree", False),
            )
            for a in raw["agents"]
        ]
        session = Session(
            session_name=raw["session_name"],
            agents=agents,
            working_dir=raw["working_dir"],
            created_at=raw["created_at"],
            scope=scope,
        )
        session.path = file_path
        return session


def resolve_scope_filter(args: Namespace) -> tuple[Scope | None, str | None]:
    """Extract (scope, working_dir_filter) from parsed CLI args.

    Returns:
        (scope, working_dir_filter) where scope is 'project', 'user',
        or None (both), and working_dir_filter is an optional directory
        path to match against agent working_dir.
    """
    if getattr(args, "user", False):
        return "user", None
    if getattr(args, "workdir", None):
        return None, args.workdir
    # Default: project scope, filter by CWD
    return "project", None
