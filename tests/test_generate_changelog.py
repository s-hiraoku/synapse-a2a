"""Tests for scripts/generate_changelog.py."""

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"

# Import the module under test with guaranteed sys.path cleanup
_scripts_path = str(SCRIPTS_DIR)
try:
    sys.path.insert(0, _scripts_path)
    from generate_changelog import (  # noqa: E402
        find_git_cliff,
        run_git_cliff,
        update_changelog,
    )
finally:
    if _scripts_path in sys.path:
        sys.path.remove(_scripts_path)


class TestFindGitCliff:
    """Tests for git-cliff binary detection."""

    def test_finds_git_cliff_in_path(self):
        """Returns ['git-cliff'] when binary is available."""
        with patch("shutil.which", return_value="/usr/local/bin/git-cliff"):
            result = find_git_cliff()
        assert result == ["git-cliff"]

    def test_falls_back_to_pipx(self):
        """Falls back to ['pipx', 'run', 'git-cliff'] when binary not found."""
        with patch(
            "shutil.which",
            side_effect=lambda x: {
                "git-cliff": None,
                "pipx": "/usr/local/bin/pipx",
            }.get(x),
        ):
            result = find_git_cliff()
        assert result == ["pipx", "run", "git-cliff"]

    def test_raises_when_nothing_available(self):
        """Raises RuntimeError when neither git-cliff nor pipx is found."""
        with patch("shutil.which", return_value=None):
            with pytest.raises(RuntimeError, match="git-cliff"):
                find_git_cliff()


class TestRunGitCliff:
    """Tests for the git-cliff invocation wrapper."""

    def _mock_run(self, stdout: str = "", returncode: int = 0):
        return MagicMock(
            stdout=stdout,
            stderr="",
            returncode=returncode,
        )

    def test_unreleased_mode_passes_correct_flags(self):
        """--unreleased mode passes --unreleased and --tag flags."""
        with (
            patch("shutil.which", return_value="/usr/bin/git-cliff"),
            patch("subprocess.run", return_value=self._mock_run("# changelog")) as mock,
        ):
            run_git_cliff(unreleased=True, tag="v0.7.0")
        args = mock.call_args[0][0]
        assert "--unreleased" in args
        assert "--tag" in args
        assert "v0.7.0" in args

    def test_full_mode_no_unreleased_flag(self):
        """Full mode does not pass --unreleased flag."""
        with (
            patch("shutil.which", return_value="/usr/bin/git-cliff"),
            patch("subprocess.run", return_value=self._mock_run("# changelog")) as mock,
        ):
            run_git_cliff(unreleased=False)
        args = mock.call_args[0][0]
        assert "--unreleased" not in args

    def test_returns_stdout(self):
        """Returns the stdout from git-cliff."""
        with (
            patch("shutil.which", return_value="/usr/bin/git-cliff"),
            patch(
                "subprocess.run",
                return_value=self._mock_run("## [0.7.0]\n\n### Added\n- feat"),
            ),
        ):
            result = run_git_cliff(unreleased=True, tag="v0.7.0")
        assert "## [0.7.0]" in result

    def test_raises_on_nonzero_exit(self):
        """Raises RuntimeError on git-cliff failure."""
        failed = MagicMock(stdout="", stderr="error occurred", returncode=1)
        with (
            patch("shutil.which", return_value="/usr/bin/git-cliff"),
            patch("subprocess.run", return_value=failed),
        ):
            with pytest.raises(RuntimeError, match="git-cliff failed"):
                run_git_cliff(unreleased=True, tag="v0.7.0")

    def test_raises_on_timeout(self):
        """Raises RuntimeError when git-cliff times out."""
        with (
            patch("shutil.which", return_value="/usr/bin/git-cliff"),
            patch(
                "subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd="git-cliff", timeout=60),
            ),
        ):
            with pytest.raises(RuntimeError, match="timed out"):
                run_git_cliff(unreleased=True, tag="v0.7.0")


class TestUpdateChangelog:
    """Tests for CHANGELOG.md update logic."""

    def test_prepends_unreleased_to_existing(self, tmp_path):
        """Unreleased content is inserted after the header."""
        changelog = tmp_path / "CHANGELOG.md"
        changelog.write_text(
            "# Changelog\n\n"
            "All notable changes...\n\n"
            "## [0.6.0] - 2026-02-17\n\n"
            "### Added\n- Old feature\n"
        )
        new_section = "## [0.7.0] - 2026-02-20\n\n### Added\n- New feature\n"
        update_changelog(new_section, changelog_path=changelog, mode="unreleased")
        content = changelog.read_text()
        # New section appears before old section
        assert content.index("## [0.7.0]") < content.index("## [0.6.0]")
        # Header preserved
        assert content.startswith("# Changelog")

    def test_full_mode_replaces_content(self, tmp_path):
        """Full mode replaces the entire changelog."""
        changelog = tmp_path / "CHANGELOG.md"
        changelog.write_text("# Old content\n")
        new_content = "# Changelog\n\n## [0.7.0]\n\n### Added\n- Everything\n"
        update_changelog(new_content, changelog_path=changelog, mode="full")
        assert changelog.read_text() == new_content

    def test_unreleased_mode_creates_file_if_missing(self, tmp_path):
        """Creates CHANGELOG.md with header if it doesn't exist."""
        changelog = tmp_path / "CHANGELOG.md"
        new_section = "## [0.1.0] - 2026-01-01\n\n### Added\n- Initial\n"
        update_changelog(new_section, changelog_path=changelog, mode="unreleased")
        content = changelog.read_text()
        assert "# Changelog" in content
        assert "## [0.1.0]" in content

    def test_skips_duplicate_version(self, tmp_path):
        """Does not insert if the same version already exists."""
        changelog = tmp_path / "CHANGELOG.md"
        changelog.write_text(
            "# Changelog\n\n## [0.7.0] - 2026-02-20\n\n### Added\n- Existing\n"
        )
        original = changelog.read_text()
        new_section = "## [0.7.0] - 2026-02-20\n\n### Added\n- Duplicate\n"
        update_changelog(new_section, changelog_path=changelog, mode="unreleased")
        assert changelog.read_text() == original

    def test_invalid_mode_raises(self, tmp_path):
        """Invalid mode raises ValueError."""
        with pytest.raises(ValueError, match="Invalid mode"):
            update_changelog(
                "content", changelog_path=tmp_path / "C.md", mode="preview"
            )  # type: ignore[arg-type]


class TestGenerateChangelogCLI:
    """Integration tests for the CLI entry point."""

    SCRIPT = str(SCRIPTS_DIR / "generate_changelog.py")

    def _run(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, self.SCRIPT, *args],
            capture_output=True,
            text=True,
            timeout=10,
        )

    def test_cli_help(self):
        """CLI shows help text."""
        result = self._run("--help")
        assert result.returncode == 0
        assert "unreleased" in result.stdout.lower() or "full" in result.stdout.lower()

    def test_cli_requires_mode(self):
        """CLI exits with error when no mode is given."""
        result = self._run()
        assert result.returncode != 0

    def test_cli_unreleased_requires_tag(self):
        """--unreleased mode requires --tag argument."""
        result = self._run("--unreleased")
        assert result.returncode != 0
        assert "tag" in result.stderr.lower() or "required" in result.stderr.lower()

    def test_cli_dry_run_does_not_modify_file(self, tmp_path):
        """--dry-run prints to stdout without modifying CHANGELOG.md."""
        changelog = tmp_path / "CHANGELOG.md"
        changelog.write_text("# Original\n")
        original = changelog.read_text()

        # Write a helper script to mock run_git_cliff in a subprocess
        helper = tmp_path / "helper.py"
        helper.write_text(
            "import sys\n"
            f"sys.path.insert(0, {str(SCRIPTS_DIR)!r})\n"
            "from unittest.mock import patch\n"
            "from generate_changelog import main\n"
            "sys.argv = ['gen', '--unreleased', '--tag', 'v99.99.99', '--dry-run']\n"
            "with patch('generate_changelog.run_git_cliff',\n"
            "           return_value='## [99.99.99]\\n### Added\\n- test\\n'):\n"
            "    main()\n"
        )
        result = subprocess.run(
            [sys.executable, str(helper)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "## [99.99.99]" in result.stdout
        # File must not be modified
        assert changelog.read_text() == original
