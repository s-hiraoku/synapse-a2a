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


def test_dashboard_view_exists_in_html() -> None:
    """index.html should contain a dashboard-view section."""
    html = Path("synapse/canvas/templates/index.html").read_text(encoding="utf-8")
    assert 'id="dashboard-view"' in html


def test_dashboard_nav_link_exists() -> None:
    """index.html should have a nav link with data-route='dashboard'."""
    html = Path("synapse/canvas/templates/index.html").read_text(encoding="utf-8")
    assert 'data-route="dashboard"' in html


def test_dashboard_nav_order() -> None:
    """Dashboard nav link should appear between Canvas and History."""
    html = Path("synapse/canvas/templates/index.html").read_text(encoding="utf-8")
    canvas_pos = html.index('data-route="canvas"')
    dashboard_pos = html.index('data-route="dashboard"')
    history_pos = html.index('data-route="history"')
    assert canvas_pos < dashboard_pos < history_pos


def test_dashboard_widget_ids_in_html() -> None:
    """Dashboard section should contain expected widget IDs."""
    html = Path("synapse/canvas/templates/index.html").read_text(encoding="utf-8")
    for widget_id in [
        "dash-status-strip",
        "dash-agents",
        "dash-attention",
        "dash-tasks",
        "dash-activity",
        "dash-file-locks",
        "dash-worktrees",
        "dash-memory",
        "dash-errors",
    ]:
        assert f'id="{widget_id}"' in html, f"Missing widget: {widget_id}"


def test_dashboard_css_classes_exist() -> None:
    """canvas.css should define dashboard-specific CSS classes."""
    css = Path("synapse/canvas/static/canvas.css").read_text(encoding="utf-8")
    for cls in [".dash-strip", ".dash-grid", ".dash-widget"]:
        assert cls in css, f"Missing CSS class: {cls}"


def test_dashboard_route_in_js() -> None:
    """canvas.js should handle the dashboard route."""
    js = Path("synapse/canvas/static/canvas.js").read_text(encoding="utf-8")
    assert '"dashboard"' in js
    assert "dashboardView" in js or "dashboard-view" in js
    assert "renderDashboard" in js


def test_load_system_panel_fetches_before_route_specific_rendering() -> None:
    """loadSystemPanel should cache fetched data even when system views are hidden."""
    js = Path("synapse/canvas/static/canvas.js").read_text(encoding="utf-8")
    start = js.index("async function loadSystemPanel()")
    end = js.index("\n  function renderSystemPanel(", start)
    body = js[start:end]

    assert (
        'if (currentRoute !== "system" && currentRoute !== "history") return;'
        not in body
    )
    assert (
        'if (currentRoute !== "system" && currentRoute !== "history" && currentRoute !== "dashboard") return;'
        not in body
    )
    assert "_lastSystemData = data;" in body
    assert 'if (currentRoute === "system") {' in body
    assert 'if (currentRoute === "history") {' in body


def test_card_count_visibility_is_controlled_in_js_not_inline_html() -> None:
    """card-count should not be hard-hidden in HTML and should be shown by JS."""
    html = Path("synapse/canvas/templates/index.html").read_text(encoding="utf-8")
    js = Path("synapse/canvas/static/canvas.js").read_text(encoding="utf-8")

    assert 'id="card-count" style=' not in html
    assert "cardCount.textContent = countText;" in js
    assert "cardCount.style.display" in js or "cardCount.classList" in js


def test_status_color_prioritizes_agent_specific_states() -> None:
    """statusColor should define explicit mappings for agent lifecycle states."""
    js = Path("synapse/canvas/static/canvas.js").read_text(encoding="utf-8")
    start = js.index("function statusColor(status)")
    end = js.index(
        "\n\n  // ----------------------------------------------------------------\n  // Router",
        start,
    )
    body = js[start:end]

    assert 'case "ready":' in body
    assert 'case "waiting":' in body
    assert 'case "processing":' in body
    assert 'case "done":' in body
    assert 'case "shutting_down":' in body
    assert 'return "var(--color-success)"' in body
    assert 'return "var(--color-accent)"' in body
    assert 'return "var(--color-warning)"' in body
    assert 'return "var(--color-signal)"' in body
    assert 'return "var(--color-danger)"' in body


def test_live_feed_harness_uses_vm_instead_of_eval() -> None:
    """The Node harness should execute extracted code in a vm sandbox."""
    source = Path("tests/canvas_frontend_live_feed_test.js").read_text(encoding="utf-8")

    assert 'require("node:vm")' in source
    assert "new vm.Script(" in source
    assert "runInNewContext(" in source or "runInContext(" in source
    assert "eval(script)" not in source


def test_system_panel_does_not_render_dashboard_sections() -> None:
    """System view should NOT render agents, tasks, file-locks, history, memory, worktrees."""
    js = Path("synapse/canvas/static/canvas.js").read_text(encoding="utf-8")
    # Find the renderSystemPanel function body
    start = js.index("function renderSystemPanel(")
    # Find the next top-level function definition
    end = js.index("\n  function ", start + 1)
    system_body = js[start:end]
    # These section keys should NOT appear as createSystemSection calls
    for section_key in ["agents", "file-locks", "history", "memories", "worktrees"]:
        # Check that createSystemSection is not called with this key
        call_pattern = f'createSystemSection(\n          "{section_key}"'
        assert call_pattern not in system_body, (
            f"renderSystemPanel should not render '{section_key}' (moved to Dashboard)"
        )


def test_canvas_js_does_not_render_or_prioritize_pinned_cards() -> None:
    """canvas.js should ignore legacy pin state in the frontend."""
    source = Path("synapse/canvas/static/canvas.js").read_text(encoding="utf-8")

    assert "if (a.pinned && !b.pinned)" not in source
    assert "if (!a.pinned && b.pinned)" not in source
    assert 'pin.className = "pin-icon"' not in source
