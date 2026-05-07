"""Skill installation helpers used by the CLI."""

from __future__ import annotations

import shutil
from pathlib import Path

DEFAULT_SKILLS = ("synapse-a2a", "synapse-reinst")


def install_skills() -> None:
    """Install Synapse A2A skills to ~/.claude/skills/ and ~/.agents/skills/."""
    try:
        import synapse

        package_dir = Path(synapse.__file__).parent

        for skill_name in DEFAULT_SKILLS:
            claude_target = Path.home() / ".claude" / "skills" / skill_name

            if claude_target.exists():
                _copy_skill_to_agents(claude_target, skill_name)
                continue

            source_dir = package_dir / "skills" / skill_name
            if source_dir.exists():
                claude_target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(source_dir, claude_target)
                msg = f"Installed {skill_name} skill to {claude_target}"
                print(f"\x1b[32m[Synapse]\x1b[0m {msg}")
                _copy_skill_to_agents(claude_target, skill_name)
    except Exception:  # broad catch: best-effort skill install must never block startup
        pass


def _copy_skill_to_agents(
    source_dir: Path,
    skill_name: str,
    *,
    base_dir: Path | None = None,
    force: bool = False,
    quiet: bool = False,
) -> str | None:
    """Copy a skill to .agents/skills/ for Codex/OpenCode/Gemini/Copilot."""
    try:
        target_base = base_dir or Path.home()
        agents_target = target_base / ".agents" / "skills" / skill_name
        if agents_target.exists() and not force:
            return None
        if agents_target.exists() and force:
            shutil.rmtree(agents_target)
        agents_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source_dir, agents_target)
        if not quiet:
            print(
                f"\x1b[32m[Synapse]\x1b[0m Copied {skill_name} skill to {agents_target}"
            )
        return str(agents_target)
    except OSError:
        return None


def _copy_claude_skills_to_agents(base_dir: Path, force: bool = False) -> list[str]:
    """Copy Synapse skills from .claude/skills/ to .agents/skills/."""
    installed: list[str] = []

    for skill_name in DEFAULT_SKILLS:
        source = base_dir / ".claude" / "skills" / skill_name
        if not source.exists():
            continue
        result = _copy_skill_to_agents(
            source, skill_name, base_dir=base_dir, force=force, quiet=True
        )
        if result:
            installed.append(result)

    return installed
