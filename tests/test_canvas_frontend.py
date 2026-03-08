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
