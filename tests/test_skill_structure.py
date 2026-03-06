"""Tests for skill file structure best practices.

Verifies that plugin skills follow Progressive Disclosure patterns:
- Description length is optimal for triggering
- SKILL.md body stays within context budget
- Large skills have references/ for on-demand detail loading
- Descriptions include trigger contexts
- Scripts have executable permissions
"""

from __future__ import annotations

import stat
from pathlib import Path

import pytest

PLUGIN_SKILLS_DIR = Path(__file__).parent.parent / "plugins" / "synapse-a2a" / "skills"

# Skills that should be in plugins/ (user-distributable)
EXPECTED_PLUGIN_SKILLS = {"synapse-a2a", "synapse-manager", "synapse-reinst"}


def _parse_frontmatter(skill_md: Path) -> dict[str, str]:
    """Parse YAML frontmatter from SKILL.md."""
    text = skill_md.read_text()
    if not text.startswith("---"):
        return {}
    try:
        end = text.index("---", 3)
    except ValueError:
        return {}
    frontmatter = text[3:end].strip()
    result: dict[str, str] = {}
    current_key = ""
    current_val = ""
    for line in frontmatter.split("\n"):
        if line and not line[0].isspace() and ":" in line:
            if current_key:
                result[current_key] = current_val.strip()
            key, _, val = line.partition(":")
            current_key = key.strip()
            v = val.strip()
            if v.startswith(">-"):
                v = v[2:]
            elif v.startswith((">", "|")):
                v = v[1:]
            current_val = v.strip()
        elif current_key:
            current_val += " " + line.strip()
    if current_key:
        result[current_key] = current_val.strip()
    return result


def _body_lines(skill_md: Path) -> int:
    """Count lines in SKILL.md body (after frontmatter)."""
    text = skill_md.read_text()
    if not text.startswith("---"):
        return len(text.splitlines())
    try:
        end = text.index("---", 3) + 3
    except ValueError:
        return len(text.splitlines())
    body = text[end:].strip()
    return len(body.splitlines())


def _discover_plugin_skills() -> list[Path]:
    """Find all skill directories in plugins/synapse-a2a/skills/."""
    if not PLUGIN_SKILLS_DIR.exists():
        return []
    return [
        d
        for d in sorted(PLUGIN_SKILLS_DIR.iterdir())
        if d.is_dir() and (d / "SKILL.md").exists()
    ]


# Cache at module level to avoid repeated filesystem scans during parametrize
_PLUGIN_SKILLS = _discover_plugin_skills()

# Synapse-specific skills that must fully comply with Progressive Disclosure
_SYNAPSE_SKILLS = [d for d in _PLUGIN_SKILLS if d.name in EXPECTED_PLUGIN_SKILLS]


class TestSkillPresence:
    """Verify expected skills exist in plugins/."""

    def test_expected_skills_exist(self) -> None:
        actual = {d.name for d in _PLUGIN_SKILLS}
        for name in EXPECTED_PLUGIN_SKILLS:
            assert name in actual, f"Expected skill {name!r} in plugins/"

    def test_synapse_docs_not_in_plugins(self) -> None:
        """synapse-docs is a dev-only skill, not distributed via plugins."""
        docs_dir = PLUGIN_SKILLS_DIR / "synapse-docs"
        assert not docs_dir.exists(), (
            "synapse-docs should not be in plugins/ — "
            "it is project-specific and lives in .agents/skills/ only"
        )


class TestDescriptionLength:
    """Description should be 50-500 chars for optimal triggering."""

    @pytest.mark.parametrize("skill_dir", _PLUGIN_SKILLS, ids=lambda d: d.name)
    def test_skill_description_length(self, skill_dir: Path) -> None:
        fm = _parse_frontmatter(skill_dir / "SKILL.md")
        desc = fm.get("description", "")
        assert 50 <= len(desc) <= 500, (
            f"{skill_dir.name}: description is {len(desc)} chars "
            f"(expected 50-500). Current: {desc[:100]}..."
        )


class TestBodyLineCount:
    """SKILL.md body should be <=300 lines to protect context budget."""

    @pytest.mark.parametrize("skill_dir", _SYNAPSE_SKILLS, ids=lambda d: d.name)
    def test_skill_body_line_count(self, skill_dir: Path) -> None:
        lines = _body_lines(skill_dir / "SKILL.md")
        assert lines <= 300, (
            f"{skill_dir.name}: SKILL.md body has {lines} lines (max 300). "
            f"Move detail to references/ for progressive disclosure."
        )


class TestReferencesExist:
    """Skills with body >150 lines should have references/ directory."""

    @pytest.mark.parametrize("skill_dir", _SYNAPSE_SKILLS, ids=lambda d: d.name)
    def test_references_exist_for_large_skills(self, skill_dir: Path) -> None:
        lines = _body_lines(skill_dir / "SKILL.md")
        if lines > 150:
            refs = skill_dir / "references"
            assert refs.exists() and any(refs.iterdir()), (
                f"{skill_dir.name}: {lines} body lines but no references/. "
                f"Extract detail to references/ for progressive disclosure."
            )


class TestDescriptionTriggerContexts:
    """Description should include trigger contexts for reliable activation."""

    @pytest.mark.parametrize("skill_dir", _SYNAPSE_SKILLS, ids=lambda d: d.name)
    def test_description_has_trigger_contexts(self, skill_dir: Path) -> None:
        fm = _parse_frontmatter(skill_dir / "SKILL.md")
        desc = fm.get("description", "").lower()
        has_trigger = "use this skill when" in desc or "use when" in desc
        assert has_trigger, (
            f"{skill_dir.name}: description lacks trigger context. "
            f"Add 'Use this skill when ...' for reliable activation."
        )


class TestScriptsExecutable:
    """Scripts in scripts/ should have executable permissions."""

    @pytest.mark.parametrize("skill_dir", _PLUGIN_SKILLS, ids=lambda d: d.name)
    def test_scripts_are_executable(self, skill_dir: Path) -> None:
        scripts_dir = skill_dir / "scripts"
        if not scripts_dir.exists():
            pytest.skip(f"{skill_dir.name} has no scripts/")
        for script in scripts_dir.iterdir():
            if script.suffix in (".py", ".sh") and not script.name.startswith("__"):
                mode = script.stat().st_mode
                assert mode & stat.S_IXUSR, (
                    f"{script.relative_to(PLUGIN_SKILLS_DIR)} is not executable"
                )
