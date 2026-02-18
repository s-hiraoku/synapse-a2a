#!/usr/bin/env python3
"""Extract a version's changelog section from CHANGELOG.md.

Usage:
    python scripts/extract_changelog.py <version>

Prints the matching section to stdout.
Exits with code 1 if the version is not found.
"""

import re
import sys
from pathlib import Path

CHANGELOG_PATH = Path(__file__).parent.parent / "CHANGELOG.md"


def extract_changelog(version: str) -> str:
    """Extract changelog section for the given version.

    Raises:
        ValueError: If the version is not found in CHANGELOG.md.
    """
    content = CHANGELOG_PATH.read_text(encoding="utf-8")
    escaped = re.escape(version)
    pattern = rf"## \[{escaped}\] - \d{{4}}-\d{{2}}-\d{{2}}\n(.*?)(?=\n## \[|\Z)"
    match = re.search(pattern, content, re.DOTALL)
    if not match:
        raise ValueError(f"Version {version} not found in CHANGELOG.md")
    return match.group(0).strip()


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: extract_changelog.py <version>", file=sys.stderr)
        sys.exit(1)
    try:
        print(extract_changelog(sys.argv[1]))
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
