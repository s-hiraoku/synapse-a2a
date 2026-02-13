#!/usr/bin/env python3
"""Patch the Homebrew formula URL and SHA256 from PyPI.

Usage:
    python scripts/patch_homebrew_formula.py <version>
"""

import hashlib
import json
import re
import sys
import urllib.request
from pathlib import Path

FORMULA_PATH = Path(__file__).parent.parent / "homebrew" / "synapse-a2a.rb"


def fetch_pypi_sdist_info(version: str) -> tuple[str, str]:
    """Return (sdist_url, sha256) for a specific version from PyPI."""
    url = f"https://pypi.org/pypi/synapse-a2a/{version}/json"
    with urllib.request.urlopen(url) as resp:
        data = json.loads(resp.read())

    sdist = next(
        (u for u in data["urls"] if u["packagetype"] == "sdist"),
        None,
    )
    if sdist is None:
        print(f"ERROR: No sdist for synapse-a2a=={version}", file=sys.stderr)
        sys.exit(1)

    sha256_hex: str = sdist["digests"].get("sha256", "")
    if not sha256_hex:
        with urllib.request.urlopen(sdist["url"]) as dl:
            sha256_hex = hashlib.sha256(dl.read()).hexdigest()

    return sdist["url"], sha256_hex


def patch_formula(version: str, sdist_url: str, sha256: str) -> None:
    """Replace URL and SHA256 in the formula."""
    text = FORMULA_PATH.read_text()

    # Update url line
    text = re.sub(
        r'url "https://files\.pythonhosted\.org/.*?"',
        f'url "{sdist_url}"',
        text,
    )

    # Update sha256 line
    text = re.sub(
        r'sha256 ".*?"',
        f'sha256 "{sha256}"',
        text,
    )

    FORMULA_PATH.write_text(text)
    print(f"Patched homebrew/synapse-a2a.rb for v{version}")


def main() -> None:
    if len(sys.argv) < 2:
        print(
            "Usage: patch_homebrew_formula.py <version>",
            file=sys.stderr,
        )
        sys.exit(1)

    version = sys.argv[1]
    sdist_url, sha256 = fetch_pypi_sdist_info(version)
    patch_formula(version, sdist_url, sha256)


if __name__ == "__main__":
    main()
