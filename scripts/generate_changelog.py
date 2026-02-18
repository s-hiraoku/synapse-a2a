#!/usr/bin/env python3
"""Generate CHANGELOG.md from Conventional Commits using git-cliff.

Usage:
    python scripts/generate_changelog.py --unreleased --tag v0.7.0
    python scripts/generate_changelog.py --full
    python scripts/generate_changelog.py --unreleased --tag v0.7.0 --dry-run

Requires git-cliff to be installed, or falls back to `pipx run git-cliff`.
"""

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

CHANGELOG_PATH = Path(__file__).parent.parent / "CHANGELOG.md"
CLIFF_TOML = Path(__file__).parent.parent / "cliff.toml"

CHANGELOG_HEADER = """\
# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

"""


def find_git_cliff() -> list[str]:
    """Find the git-cliff command, falling back to pipx.

    Returns:
        Command list to invoke git-cliff (e.g., ["git-cliff"] or ["pipx", "run", "git-cliff"]).

    Raises:
        RuntimeError: If neither git-cliff nor pipx is available.
    """
    if shutil.which("git-cliff"):
        return ["git-cliff"]
    if shutil.which("pipx"):
        return ["pipx", "run", "git-cliff"]
    raise RuntimeError(
        "git-cliff is not installed. Install it with:\n"
        "  pipx install git-cliff\n"
        "  # or: brew install git-cliff"
    )


def run_git_cliff(
    *,
    unreleased: bool = False,
    tag: str | None = None,
) -> str:
    """Run git-cliff and return the generated changelog text.

    Args:
        unreleased: If True, generate only unreleased changes.
        tag: Version tag for the unreleased section (e.g., "v0.7.0").

    Returns:
        Generated changelog text.

    Raises:
        RuntimeError: If git-cliff exits with non-zero code.
    """
    cmd = find_git_cliff()
    cmd.extend(["--config", str(CLIFF_TOML)])

    if unreleased:
        cmd.append("--unreleased")
        if tag:
            cmd.extend(["--tag", tag])
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("git-cliff timed out after 60 seconds") from None
    if result.returncode != 0:
        raise RuntimeError(
            f"git-cliff failed (exit {result.returncode}):\n{result.stderr}"
        )
    return result.stdout


def update_changelog(
    content: str,
    *,
    changelog_path: Path = CHANGELOG_PATH,
    mode: str = "unreleased",
) -> None:
    """Write generated content to CHANGELOG.md.

    Args:
        content: The generated changelog text.
        changelog_path: Path to the CHANGELOG.md file.
        mode: "unreleased" inserts after header; "full" replaces entire file.
    """
    if mode == "full":
        changelog_path.write_text(content, encoding="utf-8")
        return

    # Unreleased mode: insert new section after header
    if changelog_path.exists():
        existing = changelog_path.read_text(encoding="utf-8")
        # Find the first version heading to insert before it
        match = re.search(r"^## \[", existing, re.MULTILINE)
        if match:
            before = existing[: match.start()]
            after = existing[match.start() :]
            new_content = before.rstrip() + "\n\n" + content.strip() + "\n\n" + after
        else:
            # No existing version sections, append after all content
            new_content = existing.rstrip() + "\n\n" + content.strip() + "\n"
    else:
        new_content = CHANGELOG_HEADER + content.strip() + "\n"

    changelog_path.write_text(new_content, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate CHANGELOG.md from Conventional Commits using git-cliff."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--unreleased",
        action="store_true",
        help="Generate only unreleased changes (for PR preview).",
    )
    group.add_argument(
        "--full",
        action="store_true",
        help="Regenerate full changelog from all history.",
    )
    parser.add_argument(
        "--tag",
        help="Version tag for unreleased section (e.g., v0.7.0). Required with --unreleased.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print generated changelog to stdout without writing to file.",
    )

    args = parser.parse_args()

    if args.unreleased and not args.tag:
        parser.error("--tag is required when using --unreleased")

    try:
        content = run_git_cliff(unreleased=args.unreleased, tag=args.tag)
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        print(content)
        return

    mode = "unreleased" if args.unreleased else "full"
    update_changelog(content, mode=mode)
    print(f"Updated {CHANGELOG_PATH} (mode: {mode})")


if __name__ == "__main__":
    main()
