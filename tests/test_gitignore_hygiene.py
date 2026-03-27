"""Regression tests for repo-local generated file ignore rules."""

from __future__ import annotations

import subprocess


def _is_ignored(path: str) -> bool:
    result = subprocess.run(
        ["git", "check-ignore", "-q", path],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


class TestGitignoreHygiene:
    """Generated local-state files should stay out of git status noise."""

    def test_synapse_sqlite_artifacts_are_ignored(self) -> None:
        assert _is_ignored(".synapse/runtime-test.db")
        assert _is_ignored(".synapse/runtime-canvas.db")
        assert _is_ignored(".synapse/runtime-memory.db")
        assert _is_ignored(".synapse/runtime-test.db-wal")
        assert _is_ignored(".synapse/runtime-test.db-shm")

    def test_regular_project_files_are_not_blanket_ignored(self) -> None:
        assert not _is_ignored("tests/test_gitignore_hygiene.py")
        assert not _is_ignored("synapse/cli.py")
