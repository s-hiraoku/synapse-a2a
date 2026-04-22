"""Synapse Canvas — shared visual output surface for agents."""

from __future__ import annotations

import hashlib
from pathlib import Path

_CANVAS_DIR = Path(__file__).resolve().parent

CANVAS_CSS_FILES = (
    "canvas-base.css",
    "canvas-spotlight.css",
    "canvas-dashboard.css",
    "canvas-cards.css",
    "canvas-markdown.css",
    "canvas-templates.css",
    "canvas-views.css",
    "canvas-knowledge.css",
    "canvas-skills.css",
)

CANVAS_JS_FILES = (
    "canvas-core.js",
    "canvas-renderers.js",
    "canvas-system.js",
    "canvas-spotlight.js",
    "canvas-admin.js",
    "canvas-workflow.js",
    "canvas-multiagent.js",
    "canvas-database.js",
    "canvas-knowledge.js",
    "canvas-skills.js",
    "canvas-mcp.js",
    "canvas-init.js",
)

_ASSET_PATHS = (
    "templates/index.html",
    "static/palette.css",
    *(f"static/{f}" for f in CANVAS_CSS_FILES),
    *(f"static/{f}" for f in CANVAS_JS_FILES),
)


def compute_asset_hash() -> str:
    """SHA-256 of Canvas static assets, truncated to 12 hex chars.

    Used by both the server (to report its asset generation) and the CLI
    (to detect stale servers serving outdated HTML/JS/CSS).
    """
    h = hashlib.sha256()
    for rel in _ASSET_PATHS:
        p = _CANVAS_DIR / rel
        if not p.is_file():
            raise FileNotFoundError(f"Missing Canvas asset: {p}")
        h.update(p.read_bytes())
    return h.hexdigest()[:12]
