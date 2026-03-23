"""Core manifest, lockfile, and installer support for harness packages."""

from __future__ import annotations

import json
import shutil
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

ALL_AGENTS = ["claude", "codex", "gemini", "opencode", "copilot"]
DEFAULT_LOCK_PATH = ".synapse/harness-lock.json"


@dataclass
class HarnessManifest:
    """Parsed representation of harness.yaml."""

    name: str
    version: str
    description: str
    author: str
    license: str
    agents: list[str]
    layer_hint: str
    compatible_with: list[str]
    conflicts_with: list[str]
    contents: dict[str, Any]
    dependencies: list[str]

    @classmethod
    def from_yaml(cls, path: str | Path) -> HarnessManifest:
        """Load and parse a harness.yaml file."""
        with Path(path).open(encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        if not isinstance(data, dict):
            raise ValueError("harness manifest must be a mapping")
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HarnessManifest:
        """Parse a manifest from a dictionary."""
        return cls(
            name=str(data["name"]),
            version=str(data["version"]),
            description=str(data.get("description", "")),
            author=str(data.get("author", "")),
            license=str(data.get("license", "")),
            agents=list(data.get("agents") or ALL_AGENTS),
            layer_hint=str(data.get("layer_hint", "overlay")),
            compatible_with=list(data.get("compatible_with") or []),
            conflicts_with=list(data.get("conflicts_with") or []),
            contents=dict(data.get("contents") or {}),
            dependencies=list(data.get("dependencies") or []),
        )


class HarnessLock:
    """Read and write harness-lock.json."""

    def __init__(self, lock_path: str | Path | None = None) -> None:
        resolved = Path(lock_path or DEFAULT_LOCK_PATH)
        self.lock_path = resolved
        self._lock = threading.RLock()

    def load(self) -> dict[str, Any]:
        """Load the current lockfile content."""
        if not self.lock_path.exists():
            return {"harnesses": {}}
        with self._lock:
            data = json.loads(self.lock_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return {"harnesses": {}}
            return data

    def save(self, data: dict[str, Any]) -> None:
        """Persist lockfile content."""
        with self._lock:
            self.lock_path.parent.mkdir(parents=True, exist_ok=True)
            self.lock_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

    def add_harness(
        self,
        name: str,
        source: str,
        version: str,
        commit: str,
        files: list[str],
        layer: int,
        enabled: bool,
    ) -> None:
        """Add or update one harness record."""
        data = self.load()
        data.setdefault("harnesses", {})
        data["harnesses"][name] = {
            "name": name,
            "source": source,
            "version": version,
            "commit": commit,
            "files": files,
            "layer": layer,
            "enabled": enabled,
        }
        self.save(data)

    def remove_harness(self, name: str) -> bool:
        """Remove a harness from the lockfile."""
        data = self.load()
        harnesses = data.setdefault("harnesses", {})
        if name not in harnesses:
            return False
        del harnesses[name]
        self.save(data)
        return True

    def get_active_layers(self) -> list[dict[str, Any]]:
        """Return enabled harnesses sorted by layer number."""
        harnesses = self.load().get("harnesses", {})
        active = [item for item in harnesses.values() if item.get("enabled")]
        return sorted(active, key=lambda item: int(item.get("layer", 0)))

    def set_enabled(self, name: str, enabled: bool) -> bool:
        """Toggle enabled state for a harness."""
        data = self.load()
        harnesses = data.setdefault("harnesses", {})
        if name not in harnesses:
            return False
        harnesses[name]["enabled"] = enabled
        self.save(data)
        return True

    def get_harness(self, name: str) -> dict[str, Any] | None:
        """Return one harness record by name."""
        harness = self.load().get("harnesses", {}).get(name)
        return harness if isinstance(harness, dict) else None


class HarnessInstaller:
    """Install and remove harness-managed files."""

    def __init__(self, project_root: str | Path | None = None) -> None:
        self.project_root = Path(project_root or Path.cwd())

    def install_files(
        self, manifest: HarnessManifest, source_dir: str | Path
    ) -> list[str]:
        """Place files described by a manifest into the project."""
        base = Path(source_dir)
        installed: list[str] = []
        contents = manifest.contents

        for item in contents.get("skills", []):
            source = base / str(item["src"])
            target_rel = Path(str(item.get("target", item["src"])))
            claude_target = self.project_root / ".claude" / target_rel
            agents_target = self.project_root / ".agents" / target_rel
            installed.extend(self._copy_path(source, claude_target))
            installed.extend(self._copy_path(source, agents_target))

        for item in contents.get("rules", []):
            source = base / str(item["src"])
            target = self.project_root / ".claude" / "rules" / source.name
            installed.extend(self._copy_path(source, target))

        for item in contents.get("workflows", []):
            source = base / str(item["src"])
            target_root = self.project_root / ".synapse" / "workflows"
            target = target_root / source.name
            installed.extend(self._copy_path(source, target))

        for item in contents.get("instructions", []):
            source = base / str(item["src"])
            target = self.project_root / str(item["target"])
            installed.extend(self._copy_path(source, target))

        return installed

    def remove_files(self, file_list: list[str]) -> int:
        """Remove previously installed files."""
        removed = 0
        for path_str in file_list:
            path = Path(path_str)
            if path.is_file():
                path.unlink()
                removed += 1
        return removed

    def _copy_path(self, source: Path, target: Path) -> list[str]:
        if source.is_dir():
            copied: list[str] = []
            for item in sorted(source.rglob("*")):
                if item.is_file():
                    relative = item.relative_to(source)
                    copied.extend(self._copy_file(item, target / relative))
            return copied
        return self._copy_file(source, target)

    def _copy_file(self, source: Path, target: Path) -> list[str]:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        return [str(target)]
