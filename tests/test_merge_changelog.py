"""Tests for scripts/merge_changelog.py."""

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"

_scripts_path = str(SCRIPTS_DIR)
sys.path.insert(0, _scripts_path)
from merge_changelog import split_sections, union_merge, version_key  # noqa: E402

sys.path.remove(_scripts_path)


class TestVersionKey:
    def test_numeric_ascending(self):
        assert version_key("0.5.2") < version_key("0.6.0")
        assert version_key("1.0.0") > version_key("0.99.99")

    def test_unreleased_is_highest(self):
        assert version_key("Unreleased") > version_key("99.99.99")
        assert version_key("unreleased") > version_key("1.2.3")

    def test_non_numeric_components(self):
        # Non-numeric parts fall back to 0 without raising
        version_key("0.5.2rc1")


class TestSplitSections:
    def test_preamble_and_sections(self):
        text = (
            "# Changelog\n\nHeader text.\n\n"
            "## [0.6.0] - 2026-04-01\n- feature\n\n"
            "## [0.5.0] - 2026-03-01\n- fix\n"
        )
        preamble, sections = split_sections(text)
        assert "# Changelog" in preamble
        assert len(sections) == 2
        assert sections[0][0] == "0.6.0"
        assert sections[1][0] == "0.5.0"
        assert "- feature" in sections[0][1]

    def test_no_sections(self):
        preamble, sections = split_sections("Just prose.")
        assert preamble == "Just prose."
        assert sections == []


class TestUnionMerge:
    def test_disjoint_versions_kept_in_descending_order(self):
        ours = "# Changelog\n\n## [0.6.0] - 2026-04-01\n- ours-only\n"
        theirs = "# Changelog\n\n## [0.5.0] - 2026-03-01\n- theirs-only\n"
        merged = union_merge(ours, theirs)
        assert merged.index("[0.6.0]") < merged.index("[0.5.0]")
        assert "ours-only" in merged
        assert "theirs-only" in merged

    def test_overlapping_version_prefers_ours(self):
        ours = "# CL\n\n## [0.6.0] - 2026-04-01\n- ours-body\n"
        theirs = "# CL\n\n## [0.6.0] - 2026-04-01\n- theirs-body\n"
        merged = union_merge(ours, theirs)
        assert "ours-body" in merged
        assert "theirs-body" not in merged

    def test_unreleased_comes_first(self):
        ours = "# CL\n\n## [Unreleased]\n- pending\n"
        theirs = "# CL\n\n## [0.6.0] - 2026-04-01\n- released\n"
        merged = union_merge(ours, theirs)
        assert merged.index("[Unreleased]") < merged.index("[0.6.0]")

    def test_raises_when_no_sections_on_either_side(self):
        with pytest.raises(SystemExit) as exc:
            union_merge("prose", "more prose")
        assert exc.value.code == 2


class TestMergeChangelogCLI:
    SCRIPT = str(SCRIPTS_DIR / "merge_changelog.py")

    def _run(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, self.SCRIPT, *args],
            capture_output=True,
            text=True,
            timeout=10,
        )

    def test_cli_merges_two_sides(self, tmp_path: Path):
        base = tmp_path / "base.md"
        ours = tmp_path / "ours.md"
        theirs = tmp_path / "theirs.md"
        base.write_text("# CL\n", encoding="utf-8")
        ours.write_text("# CL\n\n## [0.6.0] - 2026-04-01\n- feat\n", encoding="utf-8")
        theirs.write_text("# CL\n\n## [0.5.0] - 2026-03-01\n- fix\n", encoding="utf-8")

        result = self._run(str(base), str(ours), str(theirs))
        assert result.returncode == 0, result.stderr
        assert "[0.6.0]" in result.stdout
        assert "[0.5.0]" in result.stdout

    def test_cli_wrong_arg_count(self):
        result = self._run("only-one")
        assert result.returncode == 1
        assert "Usage" in result.stderr
