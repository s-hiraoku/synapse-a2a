#!/usr/bin/env python3
"""Merge two sides of a version-only conflict in pyproject.toml or plugin.json.

Usage:
    python scripts/merge_version_line.py <ours> <theirs>

Prints the merged file to stdout.

Strategy: treat the file as a line-by-line diff. If the ONLY differing lines
are version-bearing lines (`version = "..."` in pyproject.toml, or
`"version": "..."` in plugin.json), pick the higher semver. If any other
line differs, exit 3 (the workflow then falls back to needs-manual-rebase).
"""

import difflib
import re
import sys
from pathlib import Path

VERSION_PATTERNS = [
    re.compile(r'^(\s*)version\s*=\s*[\'"]([^\'"]+)[\'"](\s*)$'),  # pyproject.toml
    re.compile(r'^(\s*)"version"\s*:\s*"([^"]+)"(\s*,?\s*)$'),  # plugin.json
]


def extract_version(line: str) -> str | None:
    for pat in VERSION_PATTERNS:
        m = pat.match(line)
        if m:
            return m.group(2)
    return None


def semver_key(v: str) -> tuple[int, ...]:
    parts: list[int] = []
    for p in v.split("."):
        digits = re.match(r"\d+", p)
        parts.append(int(digits.group()) if digits else 0)
    return tuple(parts)


def merge(ours: str, theirs: str) -> str:
    ours_lines = ours.splitlines(keepends=True)
    theirs_lines = theirs.splitlines(keepends=True)

    diff = list(difflib.unified_diff(ours_lines, theirs_lines, n=0, lineterm=""))
    # Partition diff lines into (removed, added) pairs ignoring hunk headers.
    removed: list[str] = []
    added: list[str] = []
    for line in diff:
        if line.startswith("---") or line.startswith("+++") or line.startswith("@@"):
            continue
        if line.startswith("-"):
            removed.append(line[1:])
        elif line.startswith("+"):
            added.append(line[1:])

    if len(removed) != len(added):
        print("ERROR: asymmetric diff; non-version conflict detected", file=sys.stderr)
        sys.exit(3)

    for r, a in zip(removed, added, strict=True):
        rv = extract_version(r.rstrip("\n"))
        av = extract_version(a.rstrip("\n"))
        if rv is None or av is None:
            print(
                f"ERROR: non-version line differs; bailing out.\n  ours:   {r!r}\n  theirs: {a!r}",
                file=sys.stderr,
            )
            sys.exit(3)

    # All differing lines are version-lines; build per-removed-line replacement
    # queues from the paired (removed, added) diff — NOT a full cross product.
    # Without this pairing, a file with multiple version lines (e.g. one at
    # line 2 and another at line 6, only line 2 actually differing) would see
    # the unchanged line 6 overwritten by line 2's higher semver match.
    replacements: dict[str, list[str]] = {}
    for r, a in zip(removed, added, strict=True):
        rv = extract_version(r.rstrip("\n"))
        av = extract_version(a.rstrip("\n"))
        if rv is not None and av is not None and semver_key(av) > semver_key(rv):
            replacements.setdefault(r, []).append(a)

    merged = list(ours_lines)
    for idx, line in enumerate(merged):
        queue = replacements.get(line)
        if queue:
            merged[idx] = queue.pop(0)
    return "".join(merged)


def main() -> None:
    if len(sys.argv) != 3:
        print("Usage: merge_version_line.py <ours> <theirs>", file=sys.stderr)
        sys.exit(1)
    ours = Path(sys.argv[1]).read_text(encoding="utf-8")
    theirs = Path(sys.argv[2]).read_text(encoding="utf-8")
    sys.stdout.write(merge(ours, theirs))


if __name__ == "__main__":
    main()
