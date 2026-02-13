#!/usr/bin/env python3
"""Patch the Homebrew formula with resource stanzas from homebrew-pypi-poet.

Usage:
    # Generate poet output first:
    python3 -m venv /tmp/poet-env
    /tmp/poet-env/bin/pip install synapse-a2a homebrew-pypi-poet
    /tmp/poet-env/bin/poet -f synapse-a2a > /tmp/poet-output.rb

    # Then patch the formula:
    python scripts/patch_homebrew_formula.py <version> /tmp/poet-output.rb
"""

import hashlib
import json
import re
import sys
import urllib.request
from pathlib import Path

FORMULA_PATH = Path(__file__).parent.parent / "homebrew" / "synapse-a2a.rb"

# Markers in the formula template
STANZA_START = "  # RESOURCE_STANZAS_START"
STANZA_END = "  # RESOURCE_STANZAS_END"


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


def extract_resource_stanzas(poet_output: str) -> str:
    """Extract resource stanzas from poet -f output.

    Poet generates a full formula class. We only need the `resource "..." do`
    blocks that sit between `depends_on` and `def install`.
    """
    lines = poet_output.splitlines()
    stanzas: list[str] = []
    inside_resource = False

    for line in lines:
        if line.strip().startswith('resource "'):
            inside_resource = True
        if inside_resource:
            stanzas.append(line)
            if line.strip() == "end":
                inside_resource = False
                stanzas.append("")

    return "\n".join(stanzas).rstrip()


def patch_formula(version: str, sdist_url: str, sha256: str, stanzas: str) -> None:
    """Replace version, URL, SHA, and resource stanzas in the formula."""
    text = FORMULA_PATH.read_text()

    # Update url line
    text = re.sub(
        r'url "https://files\.pythonhosted\.org/.*?"',
        f'url "{sdist_url}"',
        text,
    )

    # Update sha256 line (only the first one, which is the formula's own sha256)
    text = re.sub(
        r'sha256 ".*?"',
        f'sha256 "{sha256}"',
        text,
        count=1,
    )

    # Replace resource stanzas between markers
    start_idx = text.find(STANZA_START)
    end_idx = text.find(STANZA_END)
    if start_idx == -1 or end_idx == -1:
        print(
            "ERROR: RESOURCE_STANZAS markers not found in formula. "
            "Cannot patch resource stanzas.",
            file=sys.stderr,
        )
        sys.exit(1)
    end_idx += len(STANZA_END)
    text = (
        text[:start_idx]
        + STANZA_START
        + "\n"
        + stanzas
        + "\n"
        + STANZA_END
        + text[end_idx:]
    )

    FORMULA_PATH.write_text(text)
    print(f"Patched homebrew/synapse-a2a.rb for v{version}")


def main() -> None:
    if len(sys.argv) < 3:
        print(
            "Usage: patch_homebrew_formula.py <version> <poet-output-file>",
            file=sys.stderr,
        )
        sys.exit(1)

    version = sys.argv[1]
    poet_file = Path(sys.argv[2])

    if not poet_file.exists():
        print(f"ERROR: {poet_file} not found", file=sys.stderr)
        sys.exit(1)

    sdist_url, sha256 = fetch_pypi_sdist_info(version)
    stanzas = extract_resource_stanzas(poet_file.read_text())

    if not stanzas.strip():
        print("WARNING: No resource stanzas found in poet output", file=sys.stderr)

    patch_formula(version, sdist_url, sha256, stanzas)


if __name__ == "__main__":
    main()
