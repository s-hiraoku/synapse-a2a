from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, HTTPException

from synapse.settings import load_settings, merge_settings

wiki_router = APIRouter()


def _get_wiki_dir(scope: str) -> Path:
    """Get wiki directory for the given scope."""
    if scope == "global":
        return Path.home() / ".synapse" / "wiki"

    synapse_dir = os.environ.get("SYNAPSE_DIR", os.path.join(os.getcwd(), ".synapse"))
    return Path(synapse_dir) / "wiki"


def _parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """Parse YAML frontmatter from markdown content."""
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if not match:
        return {}, content

    try:
        frontmatter = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        frontmatter = {}

    return frontmatter, content[match.end() :]


def _scan_wiki_pages(wiki_dir: Path) -> list[dict[str, Any]]:
    """Scan all pages in wiki/pages/ and parse their frontmatter."""
    pages_dir = wiki_dir / "pages"
    if not pages_dir.is_dir():
        return []

    pages: list[dict[str, Any]] = []
    for md_file in sorted(pages_dir.glob("*.md")):
        content = md_file.read_text(encoding="utf-8")
        frontmatter, body = _parse_frontmatter(content)

        summary = ""
        for line in body.strip().split("\n"):
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                summary = stripped[:200]
                break

        sources = frontmatter.get("sources", [])
        pages.append(
            {
                "filename": md_file.name,
                "slug": md_file.stem,
                **frontmatter,
                "summary": summary,
                "link_count": len(re.findall(r"\[\[([^\]]+)\]\]", body)),
                "source_count": len(sources) if isinstance(sources, list) else 0,
            }
        )

    return pages


def is_wiki_enabled() -> bool:
    """Return whether the wiki feature is enabled in merged raw settings."""
    user_settings = load_settings(
        Path(os.path.expanduser("~")) / ".synapse" / "settings.json"
    )
    project_root = Path(
        os.environ.get("SYNAPSE_DIR", os.path.join(os.getcwd(), ".synapse"))
    )
    project_settings = load_settings(project_root / "settings.json")
    local_settings = load_settings(project_root / "settings.local.json")
    merged = merge_settings(
        merge_settings(user_settings, project_settings), local_settings
    )

    wiki_settings = merged.get("wiki", {})
    if isinstance(wiki_settings, dict):
        return bool(wiki_settings.get("enabled", True))
    return True


@wiki_router.get("/api/wiki")
async def list_wiki_pages(scope: str = "project") -> dict[str, Any]:
    """List all wiki pages with parsed frontmatter."""
    if scope not in {"project", "global"}:
        raise HTTPException(
            status_code=400, detail="scope must be 'project' or 'global'"
        )

    wiki_dir = _get_wiki_dir(scope)
    if not wiki_dir.exists():
        return {"scope": scope, "pages": [], "exists": False}

    return {"scope": scope, "pages": _scan_wiki_pages(wiki_dir), "exists": True}


@wiki_router.get("/api/wiki/enabled")
async def wiki_enabled() -> dict[str, bool]:
    """Check if the wiki feature is enabled."""
    return {"enabled": is_wiki_enabled()}


@wiki_router.get("/api/wiki/{scope}/pages/{page:path}")
async def get_wiki_page(scope: str, page: str) -> dict[str, Any]:
    """Get a single wiki page content with parsed frontmatter."""
    if scope not in {"project", "global"}:
        raise HTTPException(
            status_code=400, detail="scope must be 'project' or 'global'"
        )

    wiki_dir = _get_wiki_dir(scope)
    safe_page = Path(page).name
    if not safe_page.endswith(".md"):
        safe_page = f"{safe_page}.md"

    page_path = wiki_dir / "pages" / safe_page
    if not page_path.is_file():
        raise HTTPException(status_code=404, detail=f"Page not found: {page}")

    content = page_path.read_text(encoding="utf-8")
    frontmatter, body = _parse_frontmatter(content)
    return {
        "slug": page_path.stem,
        "filename": page_path.name,
        **frontmatter,
        "body": body,
        "links": re.findall(r"\[\[([^\]]+)\]\]", body),
    }


@wiki_router.get("/api/wiki/stats")
async def wiki_stats(scope: str = "project") -> dict[str, Any]:
    """Get wiki statistics."""
    if scope not in {"project", "global"}:
        raise HTTPException(
            status_code=400, detail="scope must be 'project' or 'global'"
        )

    wiki_dir = _get_wiki_dir(scope)
    if not wiki_dir.exists():
        return {
            "scope": scope,
            "exists": False,
            "page_count": 0,
            "source_count": 0,
            "last_updated": None,
            "recent_activity": [],
        }

    pages_dir = wiki_dir / "pages"
    sources_dir = wiki_dir / "sources"
    page_files = sorted(pages_dir.glob("*.md")) if pages_dir.is_dir() else []
    source_count = (
        len([path for path in sources_dir.iterdir() if path.is_file()])
        if sources_dir.is_dir()
        else 0
    )

    last_updated = None
    for md_file in page_files:
        mtime = md_file.stat().st_mtime
        if last_updated is None or mtime > last_updated:
            last_updated = mtime

    recent_activity: list[dict[str, str]] = []
    log_path = wiki_dir / "log.md"
    if log_path.is_file():
        log_content = log_path.read_text(encoding="utf-8")
        for match in re.finditer(
            r"^## \[(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})\]\s+(\w+)\s*\|\s*(.+)$",
            log_content,
            re.MULTILINE,
        ):
            recent_activity.append(
                {
                    "timestamp": match.group(1),
                    "operation": match.group(2),
                    "detail": match.group(3).strip(),
                }
            )
        recent_activity = list(reversed(recent_activity[-10:]))

    return {
        "scope": scope,
        "exists": True,
        "page_count": len(page_files),
        "source_count": source_count,
        "last_updated": datetime.fromtimestamp(last_updated).isoformat()
        if last_updated
        else None,
        "recent_activity": recent_activity,
    }
