#!/usr/bin/env python3
"""Update Scoop manifest with the latest version and hash from PyPI."""

import hashlib
import json
import sys
import urllib.request
from pathlib import Path

MANIFEST_PATH = Path(__file__).parent.parent / "scoop" / "synapse-a2a.json"
PYPI_API_URL = "https://pypi.org/pypi/synapse-a2a/json"


def fetch_pypi_info(version: str | None = None) -> tuple[str, str, str]:
    """Fetch version, sdist URL, and SHA256 from PyPI.

    Returns:
        Tuple of (version, sdist_url, sha256_hex).
    """
    url = (
        f"https://pypi.org/pypi/synapse-a2a/{version}/json" if version else PYPI_API_URL
    )
    with urllib.request.urlopen(url) as resp:
        data = json.loads(resp.read())

    ver = data["info"]["version"]
    sdist = next(
        (u for u in data["urls"] if u["packagetype"] == "sdist"),
        None,
    )
    if sdist is None:
        print(f"ERROR: No sdist found for synapse-a2a=={ver}", file=sys.stderr)
        sys.exit(1)

    sdist_url: str = sdist["url"]

    # Use PyPI-provided digest when available
    sha256_hex: str = sdist["digests"].get("sha256", "")
    if not sha256_hex:
        # Fallback: download and hash
        with urllib.request.urlopen(sdist_url) as dl:
            sha256_hex = hashlib.sha256(dl.read()).hexdigest()

    return ver, sdist_url, sha256_hex


def update_manifest(version: str, sdist_url: str, sha256: str) -> None:
    """Patch the Scoop manifest JSON in-place."""
    manifest = json.loads(MANIFEST_PATH.read_text())
    manifest["version"] = version
    manifest["url"] = sdist_url
    manifest["hash"] = sha256
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=4) + "\n")
    print(f"Updated scoop/synapse-a2a.json to v{version}")


def main() -> None:
    version_arg = sys.argv[1] if len(sys.argv) > 1 else None
    ver, url, sha = fetch_pypi_info(version_arg)
    update_manifest(ver, url, sha)


if __name__ == "__main__":
    main()
