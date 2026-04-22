#!/usr/bin/env python3
"""Union-merge CHANGELOG.md conflict sides.

Usage:
    python scripts/merge_changelog.py <base> <ours> <theirs>

Prints the merged CHANGELOG to stdout.

Strategy: treat CHANGELOG.md as an append-only, version-sectioned document.
Each version section starts with a level-2 heading like "## [0.27.1] - YYYY-MM-DD"
or "## [Unreleased]". We keep the preamble from `ours`, then emit each unique
version section in descending-version order, preferring `ours` when both sides
have the same version.

Exits 2 if the structure can't be parsed from either side.
"""

import re
import sys
from pathlib import Path

HEADING_RE = re.compile(r"^## \[([^\]]+)\](?:\s*-\s*.*)?$", re.MULTILINE)


def split_sections(text: str) -> tuple[str, list[tuple[str, str]]]:
    """Split CHANGELOG into (preamble, [(version, section_text), ...])."""
    matches = list(HEADING_RE.finditer(text))
    if not matches:
        return text, []
    preamble = text[: matches[0].start()]
    sections: list[tuple[str, str]] = []
    for i, m in enumerate(matches):
        version = m.group(1)
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections.append((version, text[m.start() : end]))
    return preamble, sections


# Any numeric semver is a triple of small ints (major.minor.patch); this
# sentinel is larger than any plausible component so Unreleased sorts on top.
_UNRELEASED_RANK = 10**9


def version_key(v: str) -> tuple[int, ...]:
    """Sort key: numeric semver descending, 'Unreleased' on top."""
    if v.lower() == "unreleased":
        return (_UNRELEASED_RANK,)
    parts: list[int] = []
    for p in v.split("."):
        digits = re.match(r"\d+", p)
        parts.append(int(digits.group()) if digits else 0)
    return tuple(parts)


def union_merge(ours: str, theirs: str) -> str:
    ours_preamble, ours_sections = split_sections(ours)
    theirs_preamble, theirs_sections = split_sections(theirs)

    if not ours_sections and not theirs_sections:
        print(
            "ERROR: neither side has recognizable CHANGELOG sections", file=sys.stderr
        )
        sys.exit(2)

    preamble = ours_preamble or theirs_preamble
    seen: dict[str, str] = {}
    for version, body in ours_sections:
        seen[version] = body
    for version, body in theirs_sections:
        seen.setdefault(version, body)

    ordered = sorted(seen.items(), key=lambda kv: version_key(kv[0]), reverse=True)
    body = "".join(b for _, b in ordered)
    return preamble.rstrip() + "\n\n" + body.lstrip()


def main() -> None:
    if len(sys.argv) != 4:
        print("Usage: merge_changelog.py <base> <ours> <theirs>", file=sys.stderr)
        sys.exit(1)
    _, ours_path, theirs_path = sys.argv[1], sys.argv[2], sys.argv[3]
    ours = Path(ours_path).read_text(encoding="utf-8")
    theirs = Path(theirs_path).read_text(encoding="utf-8")
    sys.stdout.write(union_merge(ours, theirs))


if __name__ == "__main__":
    main()
