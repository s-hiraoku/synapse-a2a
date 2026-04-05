"""LLM wiki helpers and CLI commands."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

WIKI_PAGE_TYPES = {
    "entity",
    "concept",
    "decision",
    "comparison",
    "synthesis",
    "learning",
}
WIKILINK_PATTERN = re.compile(r"\[\[([^\]]+)\]\]")
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def get_wiki_dir(scope: str = "project") -> Path:
    """Get wiki directory path for given scope."""
    if scope == "global":
        return Path.home() / ".synapse" / "wiki"
    synapse_dir = os.environ.get("SYNAPSE_DIR", str(Path.cwd() / ".synapse"))
    return Path(synapse_dir) / "wiki"


def _read_template(relative_path: str) -> str:
    template_path = Path(__file__).parent / "templates" / relative_path
    return template_path.read_text(encoding="utf-8")


def ensure_wiki_dir(scope: str = "project") -> Path:
    """Create wiki directory structure if it doesn't exist."""
    wiki_dir = get_wiki_dir(scope)
    wiki_dir.mkdir(parents=True, exist_ok=True)
    (wiki_dir / "sources").mkdir(exist_ok=True)
    (wiki_dir / "pages").mkdir(exist_ok=True)

    schema_path = wiki_dir / "schema.md"
    if not schema_path.exists():
        schema_path.write_text(_read_template("wiki-schema.md"), encoding="utf-8")

    index_path = wiki_dir / "index.md"
    if not index_path.exists():
        index_path.write_text("# Wiki Index\n", encoding="utf-8")

    log_path = wiki_dir / "log.md"
    if not log_path.exists():
        log_path.write_text("# Wiki Log\n", encoding="utf-8")

    return wiki_dir


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")


def parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """Parse YAML frontmatter from markdown content.

    Returns (frontmatter_dict, body_content).
    """
    match = _FRONTMATTER_RE.match(content)
    if not match:
        return {}, content
    try:
        fm = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        fm = {}
    if not isinstance(fm, dict):
        return {}, content[match.end() :]
    return fm, content[match.end() :]


def _parse_frontmatter_from_path(path: Path) -> tuple[dict[str, Any], str]:
    return parse_frontmatter(path.read_text(encoding="utf-8"))


def _iter_page_paths(wiki_dir: Path) -> list[Path]:
    return sorted((wiki_dir / "pages").glob("*.md"))


def _page_slug(path: Path) -> str:
    return path.stem


def _git_head_short(cwd: Path | None = None) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            cwd=str(cwd) if cwd else None,
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except (OSError, FileNotFoundError):
        return None


def detect_stale_pages(wiki_dir: Path) -> list[tuple[Path, list[str]]]:
    """Detect wiki pages whose tracked source files have changed since source_commit."""
    results: list[tuple[Path, list[str]]] = []
    for path in _iter_page_paths(wiki_dir):
        fm, _ = _parse_frontmatter_from_path(path)
        source_files = fm.get("source_files")
        source_commit = fm.get("source_commit")
        if not isinstance(source_files, list) or not isinstance(source_commit, str):
            continue
        if not source_files or not source_commit:
            continue
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", f"{source_commit}..HEAD", "--"]
                + source_files,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                continue
        except (OSError, FileNotFoundError):
            continue
        if result.stdout.strip():
            results.append((path, result.stdout.strip().splitlines()))
    return results


def _update_frontmatter_field(path: Path, field: str, value: Any) -> None:
    """Update a single field in a page's YAML frontmatter."""
    content = path.read_text(encoding="utf-8")
    fm, body = parse_frontmatter(content)
    fm[field] = value
    path.write_text(
        f"---\n{yaml.dump(fm, default_flow_style=False)}---\n{body}", encoding="utf-8"
    )


def _collect_status(wiki_dir: Path) -> tuple[int, int, str | None, int, int]:
    page_paths = _iter_page_paths(wiki_dir)
    source_paths = [path for path in (wiki_dir / "sources").glob("*") if path.is_file()]
    lint_penalties = 0
    latest_updated: str | None = None
    page_slugs = {_page_slug(path) for path in page_paths}

    for path in page_paths:
        frontmatter, body = _parse_frontmatter_from_path(path)
        if any(
            not frontmatter.get(field)
            for field in ("type", "title", "created", "updated")
        ):
            lint_penalties += 1
        page_type = frontmatter.get("type")
        if page_type and page_type not in WIKI_PAGE_TYPES:
            lint_penalties += 1
        for target in WIKILINK_PATTERN.findall(body):
            if target not in page_slugs:
                lint_penalties += 1
        updated = frontmatter.get("updated")
        if updated is not None:
            updated_text = str(updated)
            if latest_updated is None or updated_text > latest_updated:
                latest_updated = updated_text

    health_score = max(0, 100 - (lint_penalties * 10))
    try:
        stale_count = len(detect_stale_pages(wiki_dir))
    except (OSError, subprocess.SubprocessError):
        stale_count = 0
    return len(page_paths), len(source_paths), latest_updated, health_score, stale_count


def cmd_wiki_ingest(args: argparse.Namespace) -> None:
    """Copy source file to wiki/sources/, append to log.md."""
    wiki_dir = ensure_wiki_dir(args.scope)
    source_path = Path(args.source).expanduser().resolve()
    if not source_path.exists():
        raise FileNotFoundError(f"Source file not found: {source_path}")

    destination = wiki_dir / "sources" / source_path.name
    shutil.copy2(source_path, destination)

    with (wiki_dir / "log.md").open("a", encoding="utf-8") as handle:
        handle.write(f"## [{_timestamp()}] ingest | {source_path.name}\n")

    print(f"Ingested {source_path} -> {destination}")


def cmd_wiki_query(args: argparse.Namespace) -> None:
    """Parse index.md and return relevant page candidates."""
    wiki_dir = ensure_wiki_dir(args.scope)
    index_text = (wiki_dir / "index.md").read_text(encoding="utf-8")
    terms = [term for term in re.findall(r"\w+", args.question.lower()) if term]
    line_pattern = re.compile(
        r"- \[(?P<title>[^\]]+)\]\((?P<path>[^)]+)\):\s*(?P<summary>.*)"
    )
    matches: list[tuple[str, str, str]] = []

    for line in index_text.splitlines():
        match = line_pattern.match(line.strip())
        if not match:
            continue
        title = match.group("title")
        page_path = match.group("path")
        summary = match.group("summary")
        haystack = f"{title} {summary}".lower()
        score = sum(1 for term in terms if term in haystack)
        if score > 0:
            matches.append((title, page_path, summary))

    if not matches:
        print("No matching wiki pages found.")
        return

    for title, page_path, summary in matches:
        print(f"- {title} ({page_path}): {summary}")


def cmd_wiki_lint(args: argparse.Namespace) -> None:
    """Validate frontmatter, detect broken links, find orphan pages."""
    wiki_dir = ensure_wiki_dir(args.scope)
    page_paths = _iter_page_paths(wiki_dir)
    known_pages = {_page_slug(path) for path in page_paths}
    inbound_links = {slug: 0 for slug in known_pages}
    required_fields = {"type", "title", "created", "updated"}
    issues: list[str] = []

    for path in page_paths:
        frontmatter, body = _parse_frontmatter_from_path(path)
        missing_fields = sorted(
            field for field in required_fields if not frontmatter.get(field)
        )
        if missing_fields:
            issues.append(
                f"{path.name}: missing required fields: {', '.join(missing_fields)}"
            )

        page_type = frontmatter.get("type")
        if page_type and page_type not in WIKI_PAGE_TYPES:
            issues.append(f"{path.name}: invalid type: {page_type}")

        for target in WIKILINK_PATTERN.findall(body):
            if target not in known_pages:
                issues.append(f"{path.name}: broken wikilink -> {target}")
            else:
                inbound_links[target] += 1

    orphan_pages = sorted(
        path.name for path in page_paths if inbound_links.get(_page_slug(path), 0) == 0
    )

    try:
        stale = detect_stale_pages(wiki_dir)
    except (OSError, subprocess.SubprocessError):
        stale = []
    for page_path, changed_files in stale:
        print(
            f"{page_path.name}: stale - source files changed: {', '.join(changed_files)}"
        )

    if not issues and not orphan_pages:
        print("Wiki lint passed.")
        return

    for issue in issues:
        print(issue)
    if orphan_pages:
        print("Orphan pages:")
        for path_name in orphan_pages:
            print(f"- {path_name}")


def cmd_wiki_status(args: argparse.Namespace) -> None:
    """Show wiki stats: page count, source count, last updated, health score."""
    wiki_dir = ensure_wiki_dir(args.scope)
    page_count, source_count, latest_updated, health_score, stale_count = (
        _collect_status(wiki_dir)
    )
    print(f"Pages: {page_count}")
    print(f"Sources: {source_count}")
    print(f"Last updated: {latest_updated or 'N/A'}")
    print(f"Health score: {health_score}")
    print(f"Stale pages: {stale_count}")


def cmd_wiki_refresh(args: argparse.Namespace) -> None:
    """Detect and refresh stale wiki pages."""
    wiki_dir = ensure_wiki_dir(args.scope)
    stale = detect_stale_pages(wiki_dir)
    if not stale:
        print("All pages are up to date.")
        return
    for page_path, changed_files in stale:
        print(f"STALE: {page_path.name}")
        print(f"  Changed: {', '.join(changed_files)}")
    if args.apply:
        head = _git_head_short()
        for page_path, _ in stale:
            _update_frontmatter_field(page_path, "source_commit", head)
        print(f"Updated source_commit to {head}")


_INIT_SKELETONS = [
    {
        "filename": "synthesis-architecture.md",
        "type": "synthesis",
        "title": "Architecture Overview",
    },
    {
        "filename": "synthesis-patterns.md",
        "type": "synthesis",
        "title": "Key Patterns",
    },
]


def cmd_wiki_init(args: argparse.Namespace) -> None:
    """Initialize wiki with skeleton pages."""
    wiki_dir = ensure_wiki_dir(args.scope)
    pages_dir = wiki_dir / "pages"
    index_path = wiki_dir / "index.md"
    ts = _timestamp()

    index_text = index_path.read_text(encoding="utf-8")

    for skeleton in _INIT_SKELETONS:
        filename = skeleton["filename"]
        page_path = pages_dir / filename
        if page_path.exists():
            print(f"Skipped {filename} (already exists)")
            continue

        slug = page_path.stem
        fm = {
            "type": skeleton["type"],
            "title": skeleton["title"],
            "created": ts,
            "updated": ts,
            "sources": [],
            "links": [],
            "confidence": "low",
            "author": "synapse",
        }
        body = f"# {skeleton['title']}\n\nTODO: fill in.\n"
        content = f"---\n{yaml.dump(fm, default_flow_style=False)}---\n{body}"
        page_path.write_text(content, encoding="utf-8")

        if slug not in index_text:
            with index_path.open("a", encoding="utf-8") as f:
                f.write(f"- [{slug}](pages/{filename}): {skeleton['title']}\n")
            index_text += slug

        print(f"Created {filename}")
