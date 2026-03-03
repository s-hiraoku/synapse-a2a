"""Workflow definitions for saved message sequences.

Stores reusable YAML-based workflows that send messages to agents
in sequential order. Each workflow is a named list of steps.

Storage:
- Project scope: ``.synapse/workflows/<name>.yaml``
- User scope: ``~/.synapse/workflows/<name>.yaml``
"""

from __future__ import annotations

import logging
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml

logger = logging.getLogger(__name__)

Scope = Literal["project", "user"]
_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")
_VALID_RESPONSE_MODES = {"wait", "notify", "silent"}


class WorkflowError(ValueError):
    """Raised for invalid workflow operations."""


@dataclass
class WorkflowStep:
    """A single step in a workflow sequence."""

    target: str
    message: str
    priority: int = 3
    response_mode: str = "notify"

    def __post_init__(self) -> None:
        if not isinstance(self.target, str) or not self.target:
            raise WorkflowError("Step target must be a non-empty string.")
        if not isinstance(self.message, str) or not self.message:
            raise WorkflowError("Step message must be a non-empty string.")
        if (
            isinstance(self.priority, bool)
            or not isinstance(self.priority, int)
            or not (1 <= self.priority <= 5)
        ):
            raise WorkflowError(f"Step priority must be 1-5, got {self.priority}.")
        if self.response_mode not in _VALID_RESPONSE_MODES:
            raise WorkflowError(
                f"Step response_mode must be one of {_VALID_RESPONSE_MODES}, "
                f"got '{self.response_mode}'."
            )


@dataclass
class Workflow:
    """A named sequence of message steps."""

    name: str
    steps: list[WorkflowStep]
    scope: Scope
    description: str = ""
    step_count: int = field(init=False)
    path: Path | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if not self.steps:
            raise WorkflowError("Workflow must have at least one step.")
        self.step_count = len(self.steps)


class WorkflowStore:
    """Persist and retrieve workflow definitions from project/user scopes."""

    def __init__(
        self,
        *,
        project_dir: Path | None = None,
        user_dir: Path | None = None,
    ) -> None:
        self.project_dir = project_dir or (Path.cwd() / ".synapse" / "workflows")
        self.user_dir = user_dir or (Path.home() / ".synapse" / "workflows")

    # ── public API ───────────────────────────────────────────

    def save(self, workflow: Workflow) -> Path:
        """Save a workflow to disk (upsert)."""
        self._validate_name(workflow.name)
        target_dir = self._scope_dir(workflow.scope)
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / f"{workflow.name}.yaml"

        data = {
            "name": workflow.name,
            "description": workflow.description,
            "steps": [
                {
                    "target": s.target,
                    "message": s.message,
                    "priority": s.priority,
                    "response_mode": s.response_mode,
                }
                for s in workflow.steps
            ],
        }
        # Atomic write: write to temp file then rename to avoid partial YAML.
        fd, tmp = tempfile.mkstemp(dir=str(target_path.parent), suffix=".tmp")
        try:
            with open(fd, "w", encoding="utf-8") as f:
                yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
            Path(tmp).replace(target_path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
        return target_path

    def load(
        self,
        name: str,
        scope: Scope | None = None,
    ) -> Workflow | None:
        """Load a workflow by name.

        When *scope* is None, searches project first then user.
        """
        self._validate_name(name)
        if scope is not None:
            return self._load_from_dir(name, self._scope_dir(scope), scope)

        # Project-first resolution
        result = self._load_from_dir(name, self.project_dir, "project")
        if result is not None:
            return result
        return self._load_from_dir(name, self.user_dir, "user")

    def exists(self, name: str, scope: Scope | None = None) -> bool:
        """Check whether a workflow file exists on disk (ignoring parse errors)."""
        self._validate_name(name)
        if scope is not None:
            return (self._scope_dir(scope) / f"{name}.yaml").is_file()
        return (self.project_dir / f"{name}.yaml").is_file() or (
            self.user_dir / f"{name}.yaml"
        ).is_file()

    def list_workflows(self, scope: Scope | None = None) -> list[Workflow]:
        """List workflows, optionally filtered by scope."""
        workflows: list[Workflow] = []
        dirs: list[tuple[Scope, Path]] = []

        if scope is None or scope == "project":
            dirs.append(("project", self.project_dir))
        if scope is None or scope == "user":
            dirs.append(("user", self.user_dir))

        for sc, dir_path in dirs:
            if not dir_path.is_dir():
                continue
            for file_path in sorted(dir_path.glob("*.yaml")):
                try:
                    wf = self._parse_file(file_path, sc)
                    workflows.append(wf)
                except (
                    yaml.YAMLError,
                    KeyError,
                    TypeError,
                    ValueError,
                    WorkflowError,
                ) as e:
                    logger.warning(
                        "Skipping invalid workflow file %s: %s", file_path, e
                    )
        return workflows

    def delete(self, name: str, scope: Scope | None = None) -> bool:
        """Delete a workflow by name. Returns True if deleted."""
        self._validate_name(name)
        if scope is not None:
            path = self._scope_dir(scope) / f"{name}.yaml"
            if path.is_file():
                path.unlink()
                return True
            return False

        # Try project first, then user
        for sc in ("project", "user"):
            path = self._scope_dir(sc) / f"{name}.yaml"
            if path.is_file():
                path.unlink()
                return True
        return False

    # ── validation ───────────────────────────────────────────

    @staticmethod
    def _validate_name(name: str) -> None:
        """Validate workflow name (same rules as session names)."""
        if not name or not _NAME_PATTERN.fullmatch(name):
            raise WorkflowError(
                f"Invalid workflow name '{name}'. "
                "Must start with alphanumeric and contain only "
                "alphanumeric, dots, hyphens, or underscores."
            )

    # ── internal ─────────────────────────────────────────────

    def _scope_dir(self, scope: Scope) -> Path:
        if scope == "project":
            return self.project_dir
        if scope == "user":
            return self.user_dir
        raise WorkflowError(f"unsupported scope: {scope}")

    def _load_from_dir(
        self, name: str, dir_path: Path, scope: Scope
    ) -> Workflow | None:
        file_path = dir_path / f"{name}.yaml"
        if not file_path.is_file():
            return None
        try:
            return self._parse_file(file_path, scope)
        except (yaml.YAMLError, KeyError, TypeError, ValueError, WorkflowError) as e:
            logger.warning("Failed to load workflow %s: %s", file_path, e)
            return None

    @staticmethod
    def _parse_file(file_path: Path, scope: Scope) -> Workflow:
        raw = yaml.safe_load(file_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(
                f"Invalid workflow YAML at {file_path}: expected a mapping"
            )
        if "steps" not in raw or not isinstance(raw["steps"], list) or not raw["steps"]:
            raise ValueError(
                f"Invalid workflow YAML at {file_path}: missing or empty 'steps' list"
            )
        raw_name = raw.get("name", file_path.stem)
        if raw_name != file_path.stem:
            logger.warning(
                "Workflow name '%s' does not match filename '%s'; using filename.",
                raw_name,
                file_path.stem,
            )
            raw_name = file_path.stem
        steps = [
            WorkflowStep(
                target=s["target"],
                message=s["message"],
                priority=s.get("priority", 3),
                response_mode=s.get("response_mode", "notify"),
            )
            for s in raw["steps"]
        ]
        wf = Workflow(
            name=raw_name,
            steps=steps,
            description=raw.get("description", ""),
            scope=scope,
        )
        wf.path = file_path
        return wf
