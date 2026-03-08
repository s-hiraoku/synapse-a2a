"""Checks for static site-docs assets."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def test_card_gallery_lists_all_card_types_and_templates() -> None:
    text = _read("site-docs/assets/card-gallery.html")

    for card_type in (
        "mermaid",
        "markdown",
        "html",
        "table",
        "json",
        "diff",
        "chart",
        "image",
        "code",
        "log",
        "status",
        "metric",
        "checklist",
        "timeline",
        "alert",
        "file-preview",
        "trace",
        "task-board",
    ):
        assert card_type in text

    for template_name in ("briefing", "comparison", "dashboard", "steps", "slides"):
        assert template_name in text


def test_card_gallery_loads_required_cdns_and_supports_dark_theme() -> None:
    text = _read("site-docs/assets/card-gallery.html")

    assert "cdn.jsdelivr.net/npm/mermaid" in text
    assert "cdn.jsdelivr.net/npm/marked" in text
    assert "cdn.jsdelivr.net/npm/chart.js" in text
    assert "cdnjs.cloudflare.com/ajax/libs/highlight.js" in text
    assert "cdn.jsdelivr.net/npm/diff2html" in text
    assert "prefers-color-scheme: dark" in text
    assert "backdrop-filter: blur(" in text


def test_canvas_guide_links_to_card_gallery() -> None:
    text = _read("site-docs/guide/canvas.md")

    assert "../assets/card-gallery.html" in text
    assert "Card Gallery" in text
