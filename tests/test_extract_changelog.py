"""Tests for scripts/extract_changelog.py."""

import re
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"

# Import extract_changelog from scripts/ directory without permanently
# modifying sys.path (avoids import side effects across the test suite).
_scripts_path = str(SCRIPTS_DIR)
sys.path.insert(0, _scripts_path)
from extract_changelog import CHANGELOG_PATH, extract_changelog  # noqa: E402

sys.path.remove(_scripts_path)


class TestExtractChangelog:
    """Unit tests for the extract_changelog function."""

    def test_extract_existing_version(self):
        """Extracting an existing version returns non-empty text starting with the heading."""
        result = extract_changelog("0.5.2")
        assert result.startswith("## [0.5.2] - 2026-02-15")

    def test_extract_includes_subsections(self):
        """Extracted section includes Added/Changed/Documentation subsections."""
        result = extract_changelog("0.5.2")
        assert "### Added" in result
        assert "### Changed" in result
        assert "### Documentation" in result

    def test_extract_stops_at_next_version(self):
        """Extracted section does NOT bleed into the next version."""
        result = extract_changelog("0.5.2")
        # 0.5.1 is the next older version — must not be included
        assert "## [0.5.1]" not in result

    def test_extract_nonexistent_version(self):
        """Nonexistent version raises ValueError."""
        with pytest.raises(ValueError, match="99.99.99"):
            extract_changelog("99.99.99")

    def test_extract_latest_version(self):
        """The first (latest) version in the file can be extracted."""
        content = CHANGELOG_PATH.read_text(encoding="utf-8")
        match = re.search(r"## \[(\d+\.\d+\.\d+)\]", content)
        assert match, "No version found in CHANGELOG.md"
        latest = match.group(1)
        result = extract_changelog(latest)
        assert result.startswith(f"## [{latest}]")

    def test_extract_oldest_version(self):
        """The last (oldest) version in the file can be extracted (no trailing ## [)."""
        result = extract_changelog("0.1.0")
        assert result.startswith("## [0.1.0] - 2024-12-28")

    def test_extract_version_with_dots_not_regex_wildcard(self):
        """Dots in version are literal, not regex wildcards."""
        # "0.6.0" should not match a hypothetical "0X6Y0"
        with pytest.raises(ValueError):
            extract_changelog("0X6Y0")


class TestExtractChangelogCLI:
    """Integration tests for the CLI entry point."""

    SCRIPT = str(SCRIPTS_DIR / "extract_changelog.py")

    def _run(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, self.SCRIPT, *args],
            capture_output=True,
            text=True,
            timeout=10,
        )

    def test_cli_success(self):
        """CLI prints the changelog section to stdout."""
        result = self._run("0.5.2")
        assert result.returncode == 0
        assert "## [0.5.2]" in result.stdout

    def test_cli_missing_version(self):
        """CLI exits with code 1 for a missing version."""
        result = self._run("99.99.99")
        assert result.returncode == 1
        assert "ERROR" in result.stderr

    def test_cli_no_args(self):
        """CLI exits with code 1 when no arguments are given."""
        result = self._run()
        assert result.returncode == 1
        assert "Usage" in result.stderr
