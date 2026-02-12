"""Synapse Skill Management - Core module for skill discovery, sets, and management.

Provides:
- Skill discovery across synapse/user/project/plugin scopes
- SKILL.md frontmatter parsing
- Skill deletion and cross-scope movement
- Skill deploy/import/create operations
- Skill set load/save/apply/CRUD
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Agent type → skill directory relative path
AGENT_SKILL_DIRS: dict[str, str] = {
    "claude": ".claude/skills",
    "codex": ".agents/skills",
    "opencode": ".agents/skills",
    "gemini": ".gemini/skills",
    "copilot": ".agents/skills",
}

# Directories to scan for skills (relative to base)
_SCAN_DIRS = [".claude", ".agents", ".gemini"]


class SkillScope(Enum):
    SYNAPSE = "synapse"  # ~/.synapse/skills/ (central store)
    USER = "user"
    PROJECT = "project"
    PLUGIN = "plugin"


_SCOPE_ORDER = {
    SkillScope.SYNAPSE: 0,
    SkillScope.USER: 1,
    SkillScope.PROJECT: 2,
    SkillScope.PLUGIN: 3,
}


@dataclass
class SkillInfo:
    """Metadata for a discovered skill."""

    name: str
    description: str
    scope: SkillScope
    path: Path  # Skill directory (absolute)
    source_file: Path  # SKILL.md path (absolute)
    agent_dirs: list[str]  # e.g. [".claude", ".agents"]


@dataclass
class SkillSetDefinition:
    """A named group of skills."""

    name: str
    description: str
    skills: list[str]


@dataclass
class ApplyResult:
    """Result of applying a skill set."""

    copied: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    not_found: list[str] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)


@dataclass
class DeployResult:
    """Result of deploying a skill to agent directories."""

    copied: list[tuple[str, str]] = field(default_factory=list)  # [(agent_type, path)]
    skipped: list[tuple[str, str]] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)


@dataclass
class ImportResult:
    """Result of importing a skill to the central store."""

    imported: bool
    source_path: Path | None = None
    target_path: Path | None = None
    message: str = ""


@dataclass
class AddResult:
    """Result of adding a skill from a repository via npx."""

    npx_success: bool
    imported: list[str] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)


# ──────────────────────────────────────────────────────────
# Frontmatter Parsing
# ──────────────────────────────────────────────────────────

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)


def parse_skill_frontmatter(path: Path) -> dict[str, str] | None:
    """Parse YAML frontmatter from a SKILL.md file.

    Uses simple regex parsing (no PyYAML dependency for frontmatter).

    Returns:
        Dict with at least 'name' key, or None if invalid/missing.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, FileNotFoundError):
        return None

    match = _FRONTMATTER_RE.match(text)
    if not match:
        return None

    result: dict[str, str] = {}
    for line in match.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue

        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        result[key] = value

    if "name" not in result:
        return None

    return result


# ──────────────────────────────────────────────────────────
# Skill Discovery
# ──────────────────────────────────────────────────────────


def _scan_skills_in_dir(
    base_dir: Path,
    agent_dir: str,
    scope: SkillScope,
) -> list[SkillInfo]:
    """Scan a single agent directory for skills."""
    skills_dir = base_dir / agent_dir / "skills"
    if not skills_dir.is_dir():
        return []

    found: list[SkillInfo] = []
    for skill_dir in sorted(skills_dir.iterdir()):
        if not skill_dir.is_dir():
            continue

        skill_md = skill_dir / "SKILL.md"
        if not skill_md.is_file():
            continue

        frontmatter = parse_skill_frontmatter(skill_md)
        if frontmatter is None:
            continue

        found.append(
            SkillInfo(
                name=frontmatter["name"],
                description=frontmatter.get("description", ""),
                scope=scope,
                path=skill_dir.resolve(),
                source_file=skill_md.resolve(),
                agent_dirs=[agent_dir],
            )
        )
    return found


def _scan_synapse_skills(synapse_dir: Path) -> list[SkillInfo]:
    """Scan ~/.synapse/skills/ for centrally stored skills (flat structure)."""
    skills_dir = synapse_dir / "skills"
    if not skills_dir.is_dir():
        return []

    found: list[SkillInfo] = []
    for skill_dir in sorted(skills_dir.iterdir()):
        if not skill_dir.is_dir():
            continue

        skill_md = skill_dir / "SKILL.md"
        if not skill_md.is_file():
            continue

        frontmatter = parse_skill_frontmatter(skill_md)
        if frontmatter is None:
            continue

        found.append(
            SkillInfo(
                name=frontmatter["name"],
                description=frontmatter.get("description", ""),
                scope=SkillScope.SYNAPSE,
                path=skill_dir.resolve(),
                source_file=skill_md.resolve(),
                agent_dirs=["synapse"],
            )
        )
    return found


def discover_skills(
    project_dir: Path | None = None,
    user_dir: Path | None = None,
    synapse_dir: Path | None = None,
) -> list[SkillInfo]:
    """Discover all skills across synapse, user, project, and plugin scopes.

    Within the same scope, skills with the same name in different agent dirs
    (e.g. .claude and .agents) are merged into a single entry with combined
    agent_dirs. Skills with the same name in different scopes are kept separate.

    Returns:
        List of SkillInfo sorted by (scope priority, name).
    """
    all_skills: list[SkillInfo] = []

    def _scan_scope(base: Path, scope: SkillScope) -> None:
        # Group by name within scope for dedup
        by_name: dict[str, SkillInfo] = {}
        for agent_dir in _SCAN_DIRS:
            for skill in _scan_skills_in_dir(base, agent_dir, scope):
                if skill.name in by_name:
                    existing = by_name[skill.name]
                    for d in skill.agent_dirs:
                        if d not in existing.agent_dirs:
                            existing.agent_dirs.append(d)
                else:
                    by_name[skill.name] = skill
        all_skills.extend(by_name.values())

    # Synapse scope (central store)
    if synapse_dir is not None:
        all_skills.extend(_scan_synapse_skills(synapse_dir))

    # User scope
    if user_dir is not None:
        _scan_scope(user_dir, SkillScope.USER)

    # Project scope
    if project_dir is not None:
        _scan_scope(project_dir, SkillScope.PROJECT)

        # Plugin scope: plugins/*/skills/
        plugins_dir = project_dir / "plugins"
        if plugins_dir.is_dir():
            for plugin in sorted(plugins_dir.iterdir()):
                if not plugin.is_dir():
                    continue

                skills_dir = plugin / "skills"
                if not skills_dir.is_dir():
                    continue

                for skill_dir in sorted(skills_dir.iterdir()):
                    if not skill_dir.is_dir():
                        continue

                    skill_md = skill_dir / "SKILL.md"
                    if not skill_md.is_file():
                        continue

                    frontmatter = parse_skill_frontmatter(skill_md)
                    if frontmatter is None:
                        continue

                    all_skills.append(
                        SkillInfo(
                            name=frontmatter["name"],
                            description=frontmatter.get("description", ""),
                            scope=SkillScope.PLUGIN,
                            path=skill_dir.resolve(),
                            source_file=skill_md.resolve(),
                            agent_dirs=[f"plugins/{plugin.name}"],
                        )
                    )

    # Sort: scope priority → name
    all_skills.sort(key=lambda s: (_SCOPE_ORDER[s.scope], s.name))
    return all_skills


# ──────────────────────────────────────────────────────────
# Delete / Move
# ──────────────────────────────────────────────────────────


def delete_skill(skill: SkillInfo, base_dir: Path) -> list[Path]:
    """Delete a skill from all its agent directories.

    Args:
        skill: The SkillInfo to delete.
        base_dir: Base directory (user home or project root).

    Returns:
        List of deleted directory paths.
    """
    deleted: list[Path] = []
    if skill.scope == SkillScope.SYNAPSE:
        target = base_dir / "skills" / skill.name
        if target.exists():
            shutil.rmtree(target)
            deleted.append(target)
            logger.info(f"Deleted skill '{skill.name}' from {target}")
    else:
        for agent_dir in skill.agent_dirs:
            target = base_dir / agent_dir / "skills" / skill.name
            if target.exists():
                shutil.rmtree(target)
                deleted.append(target)
                logger.info(f"Deleted skill '{skill.name}' from {target}")
    return deleted


def move_skill(
    skill: SkillInfo,
    target_scope: SkillScope,
    user_dir: Path,
    project_dir: Path,
) -> tuple[list[Path], list[Path]]:
    """Move a skill from its current scope to a target scope.

    Copies to all agent dirs in target scope, then deletes from source.

    Args:
        skill: The SkillInfo to move.
        target_scope: Target scope (USER or PROJECT).
        user_dir: User home directory.
        project_dir: Project root directory.

    Returns:
        Tuple of (copied_paths, deleted_paths).

    Raises:
        ValueError: If source and target scope are the same, or source is PLUGIN.
    """
    if skill.scope == SkillScope.PLUGIN:
        raise ValueError("Cannot move plugin skills (read-only)")

    if skill.scope == SkillScope.SYNAPSE:
        raise ValueError("Cannot move synapse skills (read-only)")

    if skill.scope == target_scope:
        raise ValueError("Cannot move skill to the same scope")

    source_base = user_dir if skill.scope == SkillScope.USER else project_dir
    target_base = user_dir if target_scope == SkillScope.USER else project_dir

    copied: list[Path] = []
    for agent_dir in skill.agent_dirs:
        target_dir = target_base / agent_dir / "skills" / skill.name
        if target_dir.exists():
            continue

        target_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(skill.path, target_dir)
        copied.append(target_dir)

    deleted = delete_skill(skill, source_base)
    return copied, deleted


# ──────────────────────────────────────────────────────────
# Deploy / Import / Create / Add
# ──────────────────────────────────────────────────────────


def deploy_skill(
    skill: SkillInfo,
    agent_types: list[str],
    deploy_scope: str,
    user_dir: Path | None = None,
    project_dir: Path | None = None,
) -> DeployResult:
    """Deploy a skill to specified agent directories.

    Args:
        skill: The SkillInfo to deploy (typically from SYNAPSE scope).
        agent_types: List of agent types (e.g. ["claude", "codex"]).
        deploy_scope: "user" or "project".
        user_dir: User home directory.
        project_dir: Project root directory.

    Returns:
        DeployResult with copied/skipped lists.
    """
    result = DeployResult()
    base_dir = user_dir if deploy_scope == "user" else project_dir

    if base_dir is None:
        result.messages.append(f"No {deploy_scope} directory specified")
        return result

    for agent_type in agent_types:
        rel_dir = get_agent_skill_dir(agent_type)
        target_dir = base_dir / rel_dir / skill.name

        if target_dir.exists():
            result.skipped.append((agent_type, str(target_dir)))
            result.messages.append(
                f"Skill '{skill.name}' already exists in {rel_dir}, skipping"
            )
            continue

        target_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(skill.path, target_dir)
        result.copied.append((agent_type, str(target_dir)))
        result.messages.append(f"Deployed '{skill.name}' to {target_dir}")

    return result


def import_skill(
    skill: SkillInfo,
    synapse_dir: Path,
) -> ImportResult:
    """Import a skill to ~/.synapse/skills/ (central store).

    Args:
        skill: The SkillInfo to import.
        synapse_dir: Path to ~/.synapse directory.

    Returns:
        ImportResult indicating success/failure.
    """
    target_dir = synapse_dir / "skills" / skill.name
    if target_dir.exists():
        return ImportResult(
            imported=False,
            source_path=skill.path,
            target_path=target_dir,
            message=f"Skill '{skill.name}' already exists in central store",
        )

    target_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(skill.path, target_dir)
    return ImportResult(
        imported=True,
        source_path=skill.path,
        target_path=target_dir,
        message=f"Imported '{skill.name}' to {target_dir}",
    )


def create_skill(
    name: str,
    synapse_dir: Path,
) -> Path | None:
    """Create a new skill template in ~/.synapse/skills/<name>/.

    Generates a basic SKILL.md template. If skill-creator's init_skill
    is available, delegates to it for richer template generation.

    Args:
        name: Skill name.
        synapse_dir: Path to ~/.synapse directory.

    Returns:
        Path to the created skill directory, or None if already exists.
    """
    skill_dir = synapse_dir / "skills" / name
    if skill_dir.exists():
        return None

    skill_dir.mkdir(parents=True, exist_ok=True)

    # Try to use skill-creator's init_skill if available
    if _try_skill_creator_init(name, skill_dir, synapse_dir):
        return skill_dir

    # Fallback: create basic SKILL.md template
    _create_basic_skill_template(name, skill_dir)
    return skill_dir


def _try_skill_creator_init(name: str, skill_dir: Path, synapse_dir: Path) -> bool:
    """Attempt to use skill-creator's init_skill for template generation.

    Returns:
        True if skill-creator was successfully used, False otherwise.
    """
    try:
        import importlib.util

        search_paths = [
            Path.home() / ".claude" / "skills",
            synapse_dir / "skills",
        ]

        for base in search_paths:
            init_path = base / "skill-creator" / "scripts" / "init_skill.py"
            if not init_path.exists():
                continue

            spec = importlib.util.spec_from_file_location("init_skill", init_path)
            if not spec or not spec.loader:
                continue

            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            if hasattr(mod, "init_skill"):
                mod.init_skill(name, skill_dir)
                return True
    except Exception:
        pass

    return False


def _create_basic_skill_template(name: str, skill_dir: Path) -> None:
    """Create a basic SKILL.md template."""
    content = f"""---
name: {name}
description: ""
---

# {name}

## Overview

Describe what this skill does.

## Instructions

Provide instructions for the agent.
"""
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")


def add_skill_from_repo(
    repo: str,
    synapse_dir: Path,
    user_dir: Path | None = None,
) -> AddResult:
    """Add a skill from a repository via npx skills CLI.

    Flow:
    1. Record existing skills in ~/.claude/skills/
    2. Run npx skills add <repo> -g -a claude-code -y
    3. Detect newly added skills (diff)
    4. Import new skills to ~/.synapse/skills/
    5. Remove imported skills from ~/.claude/skills/

    Args:
        repo: Repository URL or identifier.
        synapse_dir: Path to ~/.synapse directory.
        user_dir: User home directory.

    Returns:
        AddResult with npx status and imported skill names.
    """
    user_dir = user_dir or Path.home()
    claude_skills_dir = user_dir / ".claude" / "skills"

    before = _get_skill_names(claude_skills_dir)

    npx_result = _run_npx_skills_add(repo)
    if not npx_result["success"]:
        return AddResult(npx_success=False, messages=[npx_result["message"]])

    after = _get_skill_names(claude_skills_dir)
    new_skills = after - before

    if not new_skills:
        return AddResult(
            npx_success=True,
            messages=["npx succeeded but no new skills were detected"],
        )

    return _import_and_cleanup_skills(new_skills, claude_skills_dir, synapse_dir)


def _get_skill_names(skills_dir: Path) -> set[str]:
    """Get set of skill names from a skills directory."""
    if not skills_dir.is_dir():
        return set()

    return {
        d.name
        for d in skills_dir.iterdir()
        if d.is_dir() and (d / "SKILL.md").is_file()
    }


def _run_npx_skills_add(repo: str) -> dict[str, Any]:
    """Run npx skills add command.

    Returns:
        Dict with 'success' (bool) and 'message' (str) keys.
    """
    try:
        proc = subprocess.run(
            ["npx", "skills", "add", repo, "-g", "-a", "claude-code", "-y"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if proc.returncode != 0:
            return {
                "success": False,
                "message": f"npx skills add failed: {proc.stderr or proc.stdout}",
            }
        return {"success": True, "message": ""}
    except FileNotFoundError:
        return {
            "success": False,
            "message": "npx is not installed. Install Node.js to use 'skills add'.",
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "message": "npx skills add timed out after 120 seconds",
        }


def _import_and_cleanup_skills(
    skill_names: set[str],
    source_dir: Path,
    synapse_dir: Path,
) -> AddResult:
    """Import skills to synapse store and remove from source."""
    result = AddResult(npx_success=True)

    for skill_name in sorted(skill_names):
        source = source_dir / skill_name
        target = synapse_dir / "skills" / skill_name

        if target.exists():
            result.messages.append(
                f"Skill '{skill_name}' already in central store, skipping import"
            )
            continue

        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, target)
        result.imported.append(skill_name)
        result.messages.append(f"Imported '{skill_name}' to {target}")

        shutil.rmtree(source)
        result.messages.append(f"Removed '{skill_name}' from {source}")

    return result


# ──────────────────────────────────────────────────────────
# Skill Sets (load / save / apply / CRUD)
# ──────────────────────────────────────────────────────────


def _default_skill_sets_path() -> Path:
    """Default path for skill_sets.json."""
    return Path.cwd() / ".synapse" / "skill_sets.json"


def _bundled_skill_sets_path() -> Path:
    """Path to the bundled default skill_sets.json shipped with the package."""
    return Path(__file__).parent / "templates" / ".synapse" / "skill_sets.json"


def load_skill_sets(path: Path | None = None) -> dict[str, SkillSetDefinition]:
    """Load skill set definitions from JSON.

    When ``path`` is not provided, tries the project-local
    ``.synapse/skill_sets.json`` first; if that does not exist, falls back
    to the bundled defaults shipped with the synapse package.

    When ``path`` is explicitly provided, only that file is consulted
    (no fallback).

    Args:
        path: Path to skill_sets.json.  Defaults to .synapse/skill_sets.json
              with automatic fallback to bundled defaults.

    Returns:
        Dict mapping set name → SkillSetDefinition.
    """
    if path is not None:
        # Explicit path — no fallback
        if not path.exists():
            return {}
    else:
        path = _default_skill_sets_path()
        if not path.exists():
            # Fallback to bundled defaults
            path = _bundled_skill_sets_path()
            if not path.exists():
                return {}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Failed to load skill sets from {path}: {e}")
        return {}

    if not isinstance(data, dict):
        return {}

    result: dict[str, SkillSetDefinition] = {}
    for key, value in data.items():
        if not isinstance(value, dict):
            continue

        raw_skills = value.get("skills", [])
        if isinstance(raw_skills, list):
            skills = [s for s in raw_skills if isinstance(s, str)]
        else:
            logger.warning(f"Skill set '{key}' has invalid skills field, using []")
            skills = []

        result[key] = SkillSetDefinition(
            name=str(value.get("name", key)),
            description=str(value.get("description", "")),
            skills=skills,
        )

    return result


def save_skill_sets(
    sets: dict[str, SkillSetDefinition],
    path: Path | None = None,
) -> None:
    """Save skill set definitions to JSON.

    Args:
        sets: Dict mapping set name → SkillSetDefinition.
        path: Target path. Defaults to .synapse/skill_sets.json.
    """
    path = path or _default_skill_sets_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    data: dict[str, Any] = {}
    for key, ssd in sets.items():
        data[key] = {
            "name": ssd.name,
            "description": ssd.description,
            "skills": ssd.skills,
        }

    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def get_agent_skill_dir(agent_type: str) -> str:
    """Get the skill directory path for an agent type.

    Args:
        agent_type: Agent type (claude, codex, gemini, opencode, copilot).

    Returns:
        Relative path like ".claude/skills".
    """
    return AGENT_SKILL_DIRS.get(agent_type, ".agents/skills")


def apply_skill_set(
    set_name: str,
    agent_type: str,
    user_dir: Path | None = None,
    project_dir: Path | None = None,
    skill_sets_path: Path | None = None,
    synapse_dir: Path | None = None,
) -> ApplyResult:
    """Apply a skill set by copying skills to the agent's skill directory.

    Skills are copied into the project-level agent skill directory.

    Args:
        set_name: Name of the skill set to apply.
        agent_type: Agent type (determines target dir).
        user_dir: User home for skill discovery. Defaults to Path.home().
        project_dir: Project root for skill discovery and target. Defaults to cwd.
        skill_sets_path: Path to skill_sets.json.
        synapse_dir: Synapse config dir for SYNAPSE scope discovery.

    Returns:
        ApplyResult with copied/skipped/not_found lists.
    """
    user_dir = user_dir or Path.home()
    project_dir = project_dir or Path.cwd()

    sets = load_skill_sets(skill_sets_path)
    if set_name not in sets:
        return ApplyResult(
            not_found=[set_name],
            messages=[f"Skill set '{set_name}' not found"],
        )

    skill_set = sets[set_name]
    all_skills = discover_skills(
        project_dir=project_dir, user_dir=user_dir, synapse_dir=synapse_dir
    )
    skill_map = {s.name: s for s in all_skills}

    target_rel = get_agent_skill_dir(agent_type)
    target_base = project_dir / target_rel

    result = ApplyResult()

    for skill_name in skill_set.skills:
        if skill_name not in skill_map:
            result.not_found.append(skill_name)
            result.messages.append(f"Skill '{skill_name}' not found, skipping")
            continue

        skill = skill_map[skill_name]
        dest = target_base / skill_name

        if dest.exists():
            result.skipped.append(skill_name)
            result.messages.append(f"Skill '{skill_name}' already exists, skipping")
            continue

        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(skill.path, dest)
        result.copied.append(skill_name)
        result.messages.append(f"Copied skill '{skill_name}' to {dest}")

    return result


# ──────────────────────────────────────────────────────────
# Skill Set CRUD (migrated from skill_sets.py)
# ──────────────────────────────────────────────────────────


def create_skill_set(
    name: str,
    description: str,
    skills: list[str],
    sets_path: Path | None = None,
) -> None:
    """Create a new skill set.

    Args:
        name: Skill set name.
        description: Description.
        skills: List of skill names.
        sets_path: Path to skill_sets.json.
    """
    path = sets_path or _default_skill_sets_path()
    sets = load_skill_sets(path)
    sets[name] = SkillSetDefinition(name=name, description=description, skills=skills)
    save_skill_sets(sets, path)


def delete_skill_set(name: str, sets_path: Path | None = None) -> bool:
    """Delete a skill set.

    Returns:
        True if deleted, False if not found.
    """
    path = sets_path or _default_skill_sets_path()
    sets = load_skill_sets(path)
    if name not in sets:
        return False
    del sets[name]
    save_skill_sets(sets, path)
    return True


def edit_skill_set(
    name: str,
    description: str | None = None,
    skills: list[str] | None = None,
    sets_path: Path | None = None,
) -> bool:
    """Edit an existing skill set.

    Args:
        name: Skill set name to edit.
        description: New description (None to keep current).
        skills: New skills list (None to keep current).
        sets_path: Path to skill_sets.json.

    Returns:
        True if edited, False if not found.
    """
    path = sets_path or _default_skill_sets_path()
    sets = load_skill_sets(path)

    if name not in sets:
        return False

    skill_set = sets[name]
    if description is not None:
        skill_set.description = description
    if skills is not None:
        skill_set.skills = skills

    save_skill_sets(sets, path)
    return True


def ensure_core_skills(agent_type: str) -> list[str]:
    """Ensure core skills (synapse-a2a) are deployed to the agent's directory.

    Returns list of messages about what was done.
    """
    import shutil

    messages = []
    core_skills = ["synapse-a2a"]

    # Source: plugins/synapse-a2a/skills/<name>
    # Note: Path resolution depends on environment.
    # From git root: synapse/skills.py -> ../plugins/synapse-a2a/skills/
    base_source_dir = (
        Path(__file__).parent.parent / "plugins" / "synapse-a2a" / "skills"
    )

    target_base = Path.cwd() / get_agent_skill_dir(agent_type)

    for skill_name in core_skills:
        source_dir = base_source_dir / skill_name
        target_dir = target_base / skill_name

        if not source_dir.exists():
            # Fallback if plugins/ is not in the same level as synapse/
            continue

        if not target_dir.exists():
            try:
                target_dir.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(source_dir, target_dir)
                messages.append(
                    f"Auto-deployed core skill '{skill_name}' to {agent_type}"
                )
            except Exception as e:
                messages.append(f"Failed to auto-deploy '{skill_name}': {e}")

    return messages
