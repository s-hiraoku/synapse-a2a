"""Tests for scripts/merge_version_line.py."""

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"

_scripts_path = str(SCRIPTS_DIR)
sys.path.insert(0, _scripts_path)
from merge_version_line import extract_version, merge, semver_key  # noqa: E402

sys.path.remove(_scripts_path)


class TestExtractVersion:
    def test_pyproject_toml_style(self):
        assert extract_version('version = "0.27.1"') == "0.27.1"
        assert extract_version("version = '1.0.0'") == "1.0.0"

    def test_plugin_json_style(self):
        assert extract_version('  "version": "0.27.1",') == "0.27.1"
        assert extract_version('"version": "1.2.3"') == "1.2.3"

    def test_non_version_line(self):
        assert extract_version("name = 'synapse-a2a'") is None
        assert extract_version("") is None


class TestSemverKey:
    def test_ordering(self):
        assert semver_key("0.27.1") < semver_key("0.27.2")
        assert semver_key("0.27.9") < semver_key("0.28.0")
        assert semver_key("1.0.0") > semver_key("0.99.99")


class TestMerge:
    def test_only_version_differs_picks_higher(self):
        ours = 'name = "x"\nversion = "0.27.1"\n'
        theirs = 'name = "x"\nversion = "0.27.2"\n'
        result = merge(ours, theirs)
        assert '"0.27.2"' in result
        assert '"0.27.1"' not in result

    def test_lower_side_ignored(self):
        ours = 'version = "0.28.0"\n'
        theirs = 'version = "0.27.9"\n'
        result = merge(ours, theirs)
        assert '"0.28.0"' in result
        assert '"0.27.9"' not in result

    def test_non_version_conflict_bails(self):
        ours = 'name = "x"\nversion = "0.27.1"\n'
        theirs = 'name = "y"\nversion = "0.27.2"\n'
        with pytest.raises(SystemExit) as exc:
            merge(ours, theirs)
        assert exc.value.code == 3

    def test_plugin_json_version_merge(self):
        ours = '{\n  "name": "p",\n  "version": "0.27.1"\n}\n'
        theirs = '{\n  "name": "p",\n  "version": "0.27.2"\n}\n'
        result = merge(ours, theirs)
        assert '"0.27.2"' in result

    def test_only_changed_version_line_is_replaced(self):
        # Two version-bearing lines; only one actually differs. The unchanged
        # one must stay untouched even though a naive cross-product loop
        # would match it against the higher semver on the other side.
        ours = 'version = "0.27.1"\nother = "x"\n# ref: version = "1.0.0"\n'
        theirs = 'version = "0.28.0"\nother = "x"\n# ref: version = "1.0.0"\n'
        result = merge(ours, theirs)
        assert 'version = "0.28.0"\n' in result
        assert '# ref: version = "1.0.0"\n' in result
        assert 'version = "0.27.1"' not in result.split("\n", 1)[0]


class TestMergeVersionLineCLI:
    SCRIPT = str(SCRIPTS_DIR / "merge_version_line.py")

    def _run(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, self.SCRIPT, *args],
            capture_output=True,
            text=True,
            timeout=10,
        )

    def test_cli_merges_version_only(self, tmp_path: Path):
        ours = tmp_path / "ours.toml"
        theirs = tmp_path / "theirs.toml"
        ours.write_text('version = "0.27.1"\n', encoding="utf-8")
        theirs.write_text('version = "0.27.2"\n', encoding="utf-8")

        result = self._run(str(ours), str(theirs))
        assert result.returncode == 0, result.stderr
        assert '"0.27.2"' in result.stdout

    def test_cli_bails_on_non_version(self, tmp_path: Path):
        ours = tmp_path / "ours.toml"
        theirs = tmp_path / "theirs.toml"
        ours.write_text('name = "a"\n', encoding="utf-8")
        theirs.write_text('name = "b"\n', encoding="utf-8")

        result = self._run(str(ours), str(theirs))
        assert result.returncode == 3

    def test_cli_wrong_arg_count(self):
        result = self._run("only-one")
        assert result.returncode == 1
        assert "Usage" in result.stderr
