"""Synapse Canvas — shared visual output surface for agents."""

from __future__ import annotations

import hashlib
from pathlib import Path

_CANVAS_DIR = Path(__file__).resolve().parent

_ASSET_PATHS = (
    "templates/index.html",
    "static/canvas.js",
    "static/palette.css",
    "static/canvas-base.css",
    "static/canvas-spotlight.css",
    "static/canvas-dashboard.css",
    "static/canvas-cards.css",
    "static/canvas-markdown.css",
    "static/canvas-templates.css",
    "static/canvas-views.css",
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
