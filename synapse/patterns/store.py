"""Pattern definition storage.

Stores reusable YAML-based pattern configurations.

Storage:
- Project scope: ``.synapse/patterns/<name>.yaml``
- User scope: ``~/.synapse/patterns/<name>.yaml``
"""

from __future__ import annotations

import logging
import re
import tempfile
from pathlib import Path
from typing import Literal

import yaml

logger = logging.getLogger(__name__)

Scope = Literal["project", "user"]
_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")


class PatternStore:
    """Persist YAML pattern definitions in project or user scope."""

    def __init__(
        self,
        *,
        project_dir: Path | None = None,
        user_dir: Path | None = None,
    ) -> None:
        self.project_dir = project_dir or (Path.cwd() / ".synapse" / "patterns")
        self.user_dir = user_dir or (Path.home() / ".synapse" / "patterns")

    def save(self, config: dict, scope: Scope = "project") -> Path:
        """Save a pattern config dict to YAML via atomic temp-file replace."""
        name = self._extract_name(config)
        self._validate_name(name)
        target_dir = self._scope_dir(scope)
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / f"{name}.yaml"

        fd, tmp = tempfile.mkstemp(dir=str(target_dir), suffix=".tmp")
        try:
            with open(fd, "w", encoding="utf-8") as handle:
                yaml.dump(config, handle, default_flow_style=False, allow_unicode=True)
            Path(tmp).replace(target_path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
        return target_path

    def load(self, name: str, scope: Scope | None = None) -> dict | None:
        """Load a pattern by name, preferring project scope when omitted."""
        self._validate_name(name)
        if scope is not None:
            return self._load_from_dir(name, self._scope_dir(scope))

        loaded = self._load_from_dir(name, self.project_dir)
        if loaded is not None:
            return loaded
        return self._load_from_dir(name, self.user_dir)

    def list_patterns(self, scope: Scope | None = None) -> list[dict]:
        """List all pattern configs in the requested scope(s), sorted by name."""
        dirs: list[Path] = []
        if scope is None or scope == "project":
            dirs.append(self.project_dir)
        if scope is None or scope == "user":
            dirs.append(self.user_dir)

        patterns: list[dict] = []
        for dir_path in dirs:
            if not dir_path.is_dir():
                continue
            for file_path in sorted(dir_path.glob("*.yaml")):
                try:
                    loaded = self._parse_file(file_path)
                    patterns.append(loaded)
                except (yaml.YAMLError, TypeError, ValueError) as exc:
                    logger.warning(
                        "Skipping invalid pattern file %s: %s", file_path, exc
                    )

        patterns.sort(key=lambda item: str(item.get("name", "")))
        return patterns

    def delete(self, name: str, scope: Scope | None = None) -> bool:
        """Delete a pattern YAML file by name."""
        self._validate_name(name)
        if scope is not None:
            path = self._scope_dir(scope) / f"{name}.yaml"
            if path.is_file():
                path.unlink()
                return True
            return False

        for dir_path in (self.project_dir, self.user_dir):
            path = dir_path / f"{name}.yaml"
            if path.is_file():
                path.unlink()
                return True
        return False

    def exists(self, name: str, scope: Scope | None = None) -> bool:
        """Check whether a pattern exists in the requested scope(s)."""
        self._validate_name(name)
        if scope is not None:
            return (self._scope_dir(scope) / f"{name}.yaml").is_file()
        return (self.project_dir / f"{name}.yaml").is_file() or (
            self.user_dir / f"{name}.yaml"
        ).is_file()

    @staticmethod
    def _extract_name(config: dict) -> str:
        name = config.get("name")
        if not isinstance(name, str):
            raise ValueError("Pattern config must include string field 'name'")
        return name

    @staticmethod
    def _validate_name(name: str) -> None:
        if not name or not _NAME_PATTERN.fullmatch(name):
            raise ValueError(
                f"Invalid pattern name '{name}'. Must start with alphanumeric and "
                "contain only alphanumeric, dots, hyphens, or underscores."
            )

    def _scope_dir(self, scope: Scope) -> Path:
        if scope == "project":
            return self.project_dir
        if scope == "user":
            return self.user_dir
        raise ValueError(f"unsupported scope: {scope}")

    def _load_from_dir(self, name: str, dir_path: Path) -> dict | None:
        file_path = dir_path / f"{name}.yaml"
        if not file_path.is_file():
            return None
        try:
            return self._parse_file(file_path)
        except (yaml.YAMLError, TypeError, ValueError) as exc:
            logger.warning("Failed to load pattern %s: %s", file_path, exc)
            return None

    @staticmethod
    def _parse_file(file_path: Path) -> dict:
        loaded = yaml.safe_load(file_path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError(f"Invalid pattern YAML at {file_path}: expected a mapping")
        name = loaded.get("name", file_path.stem)
        if not isinstance(name, str):
            raise ValueError(
                f"Invalid pattern YAML at {file_path}: 'name' must be text"
            )
        if name != file_path.stem:
            logger.warning(
                "Pattern name '%s' does not match filename '%s'; using filename.",
                name,
                file_path.stem,
            )
            loaded = dict(loaded)
            loaded["name"] = file_path.stem
        return loaded
