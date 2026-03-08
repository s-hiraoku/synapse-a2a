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

REPO_ROOT = Path(__file__).parent.parent
PLUGIN_SKILLS_DIR = Path(__file__).parent.parent / "plugins" / "synapse-a2a" / "skills"
AGENTS_SKILLS_DIR = REPO_ROOT / ".agents" / "skills"
CLAUDE_SKILLS_DIR = REPO_ROOT / ".claude" / "skills"

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


def _iter_skill_files(skill_dir: Path) -> list[Path]:
    """Return all files within a skill directory, relative to the skill root."""
    return sorted(
        path.relative_to(skill_dir)
        for path in skill_dir.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
    )


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

    @pytest.mark.parametrize("target_root", [AGENTS_SKILLS_DIR, CLAUDE_SKILLS_DIR])
    def test_plugin_skills_exist_in_sync_targets(self, target_root: Path) -> None:
        """Plugin skills should be synced into both project agent directories."""
        missing = [
            skill_dir.name
            for skill_dir in _PLUGIN_SKILLS
            if not (target_root / skill_dir.name / "SKILL.md").exists()
        ]
        assert not missing, f"Missing synced skills in {target_root}: {missing}"


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
            if script.suffix not in (".py", ".sh") or script.name.startswith("__"):
                continue

            plugin_mode = script.stat().st_mode
            assert plugin_mode & stat.S_IXUSR, (
                f"{script.relative_to(PLUGIN_SKILLS_DIR)} is not executable"
            )

            rel_path = script.relative_to(skill_dir)
            for target_root in (AGENTS_SKILLS_DIR, CLAUDE_SKILLS_DIR):
                synced_script = target_root / skill_dir.name / rel_path
                assert synced_script.exists(), f"Missing synced script: {synced_script}"
                synced_mode = synced_script.stat().st_mode
                assert synced_mode & stat.S_IXUSR, (
                    f"{synced_script.relative_to(REPO_ROOT)} is not executable"
                )


class TestSyncedSkillParity:
    """Synced skill copies must match the plugin source of truth."""

    @pytest.mark.parametrize("skill_dir", _PLUGIN_SKILLS, ids=lambda d: d.name)
    @pytest.mark.parametrize("target_root", [AGENTS_SKILLS_DIR, CLAUDE_SKILLS_DIR])
    def test_synced_skill_files_match_plugin(
        self, skill_dir: Path, target_root: Path
    ) -> None:
        target_dir = target_root / skill_dir.name
        assert target_dir.exists(), f"Missing synced directory: {target_dir}"

        plugin_files = _iter_skill_files(skill_dir)
        target_files = _iter_skill_files(target_dir)
        assert target_files == plugin_files, (
            f"{target_dir} differs from plugin source. Run skill sync from plugins/."
        )

        for rel_path in plugin_files:
            plugin_bytes = (skill_dir / rel_path).read_bytes()
            target_bytes = (target_dir / rel_path).read_bytes()
            assert target_bytes == plugin_bytes, (
                f"{target_dir / rel_path} is out of sync with {skill_dir / rel_path}"
            )


class TestGeneratedArtifactsIgnored:
    """Generated Python cache files should not affect skill parity scans."""

    def test_iter_skill_files_ignores_python_cache_artifacts(
        self, tmp_path: Path
    ) -> None:
        skill_dir = tmp_path / "example-skill"
        scripts_dir = skill_dir / "scripts"
        pycache_dir = scripts_dir / "__pycache__"
        pycache_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# Skill\n", encoding="utf-8")
        (scripts_dir / "tool.py").write_text("print('ok')\n", encoding="utf-8")
        (pycache_dir / "tool.cpython-314.pyc").write_bytes(b"pyc")

        files = _iter_skill_files(skill_dir)

        assert files == [Path("SKILL.md"), Path("scripts/tool.py")]

    def test_iter_skill_files_ignores_standalone_pyc(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "example-skill"
        scripts_dir = skill_dir / "scripts"
        scripts_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# Skill\n", encoding="utf-8")
        (scripts_dir / "tool.py").write_text("print('ok')\n", encoding="utf-8")
        (scripts_dir / "standalone.pyc").write_bytes(b"pyc")

        files = _iter_skill_files(skill_dir)

        assert files == [Path("SKILL.md"), Path("scripts/tool.py")]
