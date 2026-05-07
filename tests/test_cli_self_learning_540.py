"""CLI wiring tests for self-learning commands (issue #540)."""

import subprocess
import sys


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "synapse.cli", *args],
        capture_output=True,
        text=True,
    )


def test_learn_help_is_available() -> None:
    result = _run_cli("learn", "--help")

    assert result.returncode == 0
    assert "Analyze observations" in result.stdout
    assert "--observation-db-path" in result.stdout
    assert "--db-path" in result.stdout


def test_evolve_help_is_available() -> None:
    result = _run_cli("evolve", "--help")

    assert result.returncode == 0
    assert "Discover skill candidates" in result.stdout
    assert "--generate" in result.stdout
    assert "--output-dir" in result.stdout


def test_instinct_subcommands_are_available() -> None:
    status = _run_cli("instinct", "status", "--help")
    listing = _run_cli("instinct", "list", "--help")
    promote = _run_cli("instinct", "promote", "--help")

    assert status.returncode == 0
    assert "Show instincts ordered by confidence" in status.stdout
    assert "--min-confidence" in status.stdout

    assert listing.returncode == 0
    assert "List instincts" in listing.stdout
    assert "--scope" in listing.stdout

    assert promote.returncode == 0
    assert "Promote an instinct" in promote.stdout
    assert "instinct_id" in promote.stdout
