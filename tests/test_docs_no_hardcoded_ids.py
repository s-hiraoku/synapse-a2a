"""Lint test: ensure agent-facing files don't contain hardcoded --from IDs.

LLM agents read skill files, instruction templates, and CLAUDE.md.
If these files contain concrete ``--from synapse-<type>-<port>`` examples,
agents tend to copy them verbatim instead of using ``$SYNAPSE_AGENT_ID``.

This test scans all agent-facing files and fails if any hardcoded
``--from synapse-*-*`` patterns are found.
"""

import re
from pathlib import Path

import pytest

# Root of the repository
ROOT = Path(__file__).resolve().parent.parent

# Pattern that should NOT appear in agent-facing files
HARDCODED_FROM_PATTERN = re.compile(r"--from\s+synapse-\w+-\d+")

# Directories / files that agents read at runtime
AGENT_FACING_PATHS = [
    ROOT / ".claude" / "skills",
    ROOT / ".agents" / "skills",
    ROOT / ".gemini" / "skills",
    ROOT / ".synapse",
    ROOT / "synapse" / "templates" / ".synapse",
    ROOT / "CLAUDE.md",
]


def _collect_files() -> list[Path]:
    """Collect all text files from agent-facing paths."""
    files: list[Path] = []
    for path in AGENT_FACING_PATHS:
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            for ext in ("*.md", "*.txt", "*.yaml", "*.yml", "*.json"):
                files.extend(path.rglob(ext))
    return sorted(set(files))


def _find_violations() -> list[tuple[Path, int, str]]:
    """Return (file, line_number, line_text) for every violation."""
    violations = []
    for filepath in _collect_files():
        try:
            text = filepath.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if HARDCODED_FROM_PATTERN.search(line):
                violations.append((filepath, lineno, line.strip()))
    return violations


class TestNoHardcodedFromIds:
    """Agent-facing files must use $SYNAPSE_AGENT_ID, not hardcoded IDs."""

    def test_no_hardcoded_from_in_agent_files(self):
        violations = _find_violations()
        if violations:
            report = "\n".join(
                f"  {v[0].relative_to(ROOT)}:{v[1]}: {v[2]}" for v in violations
            )
            pytest.fail(
                f"Found {len(violations)} hardcoded '--from synapse-*-*' "
                f"in agent-facing files. Use $SYNAPSE_AGENT_ID instead:\n{report}"
            )
