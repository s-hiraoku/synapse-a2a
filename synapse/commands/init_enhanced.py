"""Enhanced init helpers for project-aware Synapse setup."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _detect_framework_from_pyproject(content: str) -> str | None:
    lowered = content.lower()
    if "fastapi" in lowered:
        return "fastapi"
    if "django" in lowered:
        return "django"
    if "flask" in lowered:
        return "flask"
    return None


def _detect_framework_from_package(data: dict[str, Any]) -> str | None:
    dependencies = {
        **data.get("dependencies", {}),
        **data.get("devDependencies", {}),
    }
    if "next" in dependencies:
        return "nextjs"
    if "react" in dependencies:
        return "react"
    if "vue" in dependencies:
        return "vue"
    return None


def detect_project_context() -> dict[str, str]:
    """Detect project language and framework from common manifest files."""
    cwd = Path.cwd()

    pyproject = cwd / "pyproject.toml"
    if pyproject.exists():
        content = pyproject.read_text(encoding="utf-8")
        return {
            "language": "python",
            "framework": _detect_framework_from_pyproject(content) or "python",
            "detected_from": "pyproject.toml",
        }

    requirements = cwd / "requirements.txt"
    if requirements.exists():
        return {
            "language": "python",
            "framework": "python",
            "detected_from": "requirements.txt",
        }

    package_json = cwd / "package.json"
    if package_json.exists():
        data = json.loads(package_json.read_text(encoding="utf-8"))
        return {
            "language": "javascript",
            "framework": _detect_framework_from_package(data) or "javascript",
            "detected_from": "package.json",
        }

    markers = {
        "go.mod": {"language": "go", "framework": "go"},
        "Cargo.toml": {"language": "rust", "framework": "rust"},
        "build.gradle": {"language": "java", "framework": "gradle"},
        "pom.xml": {"language": "java", "framework": "maven"},
        "Gemfile": {"language": "ruby", "framework": "ruby"},
    }
    for filename, info in markers.items():
        if (cwd / filename).exists():
            return {**info, "detected_from": filename}

    return {}


def show_init_plan(scope: str, context: dict[str, str]) -> None:
    """Print the planned init actions for the detected project context."""
    print("Synapse Init Plan")
    print(f"Scope: {scope}")
    if context:
        print(
            f"Detected: {context.get('language', 'unknown')} / "
            f"{context.get('framework', 'unknown')} "
            f"from {context.get('detected_from', 'unknown')}"
        )
    else:
        print("Detected: no project context")
    print("Actions: create settings, install skills, save project context")


def save_project_context(synapse_dir: Path, context: dict[str, str]) -> None:
    """Persist detected project context into .synapse/settings.json."""
    synapse_dir.mkdir(parents=True, exist_ok=True)
    settings_path = synapse_dir / "settings.json"
    settings: dict[str, Any] = {}
    if settings_path.exists():
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    settings["project_context"] = context
    settings_path.write_text(
        json.dumps(settings, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
