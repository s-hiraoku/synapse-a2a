"""Tests for plugin skill files shipped in plugins/synapse-a2a/skills/.

We keep these lightweight: they assert that expected SKILL.md files exist and
have required frontmatter keys (name/description).
"""

from __future__ import annotations

from pathlib import Path

import pytest


def _read_frontmatter(md: str) -> dict[str, str]:
    """Parse a minimal YAML-like frontmatter block (--- ... ---)."""
    lines = md.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    out: dict[str, str] = {}
    i = 1
    while i < len(lines):
        line = lines[i]
        if line.strip() == "---":
            break
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
        i += 1
    return out


@pytest.mark.parametrize(
    "skill_name",
    [
        "synapse-a2a",
        "synapse-reinst",
        "system-design",
        "api-design",
        "code-review",
        "security-audit",
        "test-first",
        "refactoring",
        "code-simplifier",
        "task-planner",
        "project-docs",
        "react-performance",
        "frontend-design",
        "react-composition",
        "react-native",
        "web-accessibility",
    ],
)
def test_plugin_skill_has_required_frontmatter(skill_name: str) -> None:
    skill_md = Path("plugins") / "synapse-a2a" / "skills" / skill_name / "SKILL.md"
    assert skill_md.exists(), f"Missing skill file: {skill_md}"
    content = skill_md.read_text(encoding="utf-8")
    fm = _read_frontmatter(content)
    assert fm.get("name") == skill_name
    assert "description" in fm
