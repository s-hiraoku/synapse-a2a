"""Persistent agent definition store for `synapse agents` commands."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


class AgentProfileError(ValueError):
    """Raised for invalid input or ambiguous profile lookup."""


Scope = Literal["project", "user"]
PETNAME_PATTERN = re.compile(r"^[a-z]+-[a-z]+$")
logger = logging.getLogger(__name__)


@dataclass
class AgentProfile:
    """Saved agent definition."""

    profile_id: str
    name: str
    profile: str
    role: str | None = None
    skill_set: str | None = None
    scope: Scope = "project"
    path: Path | None = None


class AgentProfileStore:
    """Store and resolve saved agent definitions from user/project scopes."""

    def __init__(
        self,
        *,
        project_root: Path | None = None,
        home_dir: Path | None = None,
    ) -> None:
        self.project_root = project_root or Path.cwd()
        self.home_dir = home_dir or Path.home()
        self.project_dir = self.project_root / ".synapse" / "agents"
        self.user_dir = self.home_dir / ".synapse" / "agents"

    def add(
        self,
        *,
        profile_id: str,
        name: str,
        profile: str,
        role: str | None,
        skill_set: str | None,
        scope: Scope,
    ) -> AgentProfile:
        self._validate_profile_id(profile_id)
        self._validate_required(name, "name")
        self._validate_required(profile, "profile")

        existing = self.list_all()
        for item in existing:
            if item.profile_id != profile_id and item.name == name:
                raise AgentProfileError(
                    f"name '{name}' is already used by '{item.profile_id}'"
                )

        target_dir = self._scope_dir(scope)
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / f"{profile_id}.agent"
        content_lines = [
            f"id={profile_id}",
            f"name={name}",
            f"profile={profile}",
        ]
        if role:
            content_lines.append(f"role={role}")
        if skill_set:
            content_lines.append(f"skill_set={skill_set}")
        target_path.write_text("\n".join(content_lines) + "\n", encoding="utf-8")

        return AgentProfile(
            profile_id=profile_id,
            name=name,
            profile=profile,
            role=role,
            skill_set=skill_set,
            scope=scope,
            path=target_path,
        )

    def delete(self, query: str) -> bool:
        found = self.resolve(query)
        if found is None or found.path is None:
            return False
        found.path.unlink(missing_ok=True)
        return True

    def resolve(self, query: str) -> AgentProfile | None:
        """Resolve a query to a single profile, matching by id then name."""
        all_items = self.list_all()

        match = self._find_unique(all_items, "profile_id", query, "id")
        if match is not None:
            return match
        return self._find_unique(all_items, "name", query, "name")

    @staticmethod
    def _find_unique(
        items: list[AgentProfile],
        attr: str,
        value: str,
        label: str,
    ) -> AgentProfile | None:
        """Return the single item whose *attr* equals *value*, or None.

        Raises AgentProfileError when multiple items match.
        """
        matches = [item for item in items if getattr(item, attr) == value]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise AgentProfileError(f"ambiguous {label} '{value}'")
        return None

    def list_all(self) -> list[AgentProfile]:
        # Load user first, then project so project entries take precedence by id.
        merged: dict[str, AgentProfile] = {}
        scopes: tuple[tuple[Scope, Path], tuple[Scope, Path]] = (
            ("user", self.user_dir),
            ("project", self.project_dir),
        )
        for scope, root in scopes:
            for file_path in sorted(root.glob("*.agent")):
                try:
                    parsed = self._read_file(file_path, scope=scope)
                except AgentProfileError as e:
                    logger.warning(
                        "Skipping invalid agent profile %s: %s", file_path, e
                    )
                    continue
                merged[parsed.profile_id] = parsed
        return sorted(merged.values(), key=lambda item: item.profile_id)

    def _read_file(self, path: Path, *, scope: Scope) -> AgentProfile:
        data: dict[str, str] = {}
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            data[key.strip()] = value.strip()

        profile_id = data.get("id", "")
        name = data.get("name", "")
        profile = data.get("profile", "")
        role = data.get("role")
        skill_set = data.get("skill_set")
        self._validate_profile_id(profile_id)
        self._validate_required(name, "name")
        self._validate_required(profile, "profile")
        return AgentProfile(
            profile_id=profile_id,
            name=name,
            profile=profile,
            role=role,
            skill_set=skill_set,
            scope=scope,
            path=path,
        )

    def _scope_dir(self, scope: Scope) -> Path:
        if scope == "project":
            return self.project_dir
        if scope == "user":
            return self.user_dir
        raise AgentProfileError(f"unsupported scope: {scope}")

    @staticmethod
    def _validate_profile_id(profile_id: str) -> None:
        if not PETNAME_PATTERN.fullmatch(profile_id):
            raise AgentProfileError(
                f"id '{profile_id}' must follow petname format (e.g. silent-snake)"
            )

    @staticmethod
    def _validate_required(value: str, field_name: str) -> None:
        if not value.strip():
            raise AgentProfileError(f"{field_name} is required")


def suggest_petname_ids(*values: str | None, limit: int = 3) -> list[str]:
    """Suggest a few valid petname-style IDs from user-facing labels."""
    tokens: list[str] = []
    seen: set[str] = set()

    for value in values:
        if not value:
            continue
        for token in re.findall(r"[a-z]+", value.lower()):
            if token in seen:
                continue
            seen.add(token)
            tokens.append(token)

    candidates: list[str] = []
    used: set[str] = set()

    for i, left in enumerate(tokens):
        for right in tokens[i + 1 :]:
            if left == right:
                continue
            candidate = f"{left}-{right}"
            if candidate in used:
                continue
            used.add(candidate)
            candidates.append(candidate)
            if len(candidates) >= limit:
                return candidates

    fallbacks = ["agent", "helper", "worker", "guide"]
    for left in tokens:
        for right in fallbacks:
            if left == right:
                continue
            candidate = f"{left}-{right}"
            if candidate in used:
                continue
            used.add(candidate)
            candidates.append(candidate)
            if len(candidates) >= limit:
                return candidates

    generic = ["silent-snake", "calm-lead", "steady-builder"]
    for candidate in generic:
        if candidate in used:
            continue
        candidates.append(candidate)
        if len(candidates) >= limit:
            break

    return candidates
