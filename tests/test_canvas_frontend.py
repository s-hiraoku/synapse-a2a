"""Frontend regression tests for canvas.js system panel rendering."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


def test_render_system_panel_registry_errors_states() -> None:
    """renderSystemPanel should omit or show registry errors UI based on errorCount."""
    script = Path("tests/canvas_frontend_system_panel_test.js")
    if shutil.which("node") is None:
        pytest.skip("node is required for tests/canvas_frontend_system_panel_test.js")
    result = subprocess.run(
        ["node", str(script)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr or result.stdout


def test_render_live_feed_shows_latest_three_posts() -> None:
    """renderAll should populate the dashboard live feed with the newest three cards."""
    script = Path("tests/canvas_frontend_live_feed_test.js")
    if shutil.which("node") is None:
        pytest.skip("node is required for tests/canvas_frontend_live_feed_test.js")
    result = subprocess.run(
        ["node", str(script)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr or result.stdout


def test_canvas_css_uses_signal_room_design_tokens() -> None:
    """canvas.css + palette.css should define design tokens and glass surfaces."""
    css = Path("synapse/canvas/static/canvas.css").read_text(encoding="utf-8")
    palette = Path("synapse/canvas/static/palette.css").read_text(encoding="utf-8")
    source = css + palette

    assert "Inter" in source
    assert "--color-signal" in source
    assert "--glass-bg" in source
    assert "--brand" in source
    assert ".live-feed-band" in source
    assert ".message-tools" in source
    assert ".theme-toggle-icon" in source
    assert "backdrop-filter: blur(" in source


def test_canvas_js_does_not_render_or_prioritize_pinned_cards() -> None:
    """canvas.js should ignore legacy pin state in the frontend."""
    source = Path("synapse/canvas/static/canvas.js").read_text(encoding="utf-8")

    assert "if (a.pinned && !b.pinned)" not in source
    assert "if (!a.pinned && b.pinned)" not in source
    assert 'pin.className = "pin-icon"' not in source
