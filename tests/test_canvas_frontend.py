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


def test_render_spotlight_reuses_existing_shell_for_same_card_updates() -> None:
    """renderSpotlight should update the active card in place during periodic refreshes."""
    script = Path("tests/canvas_frontend_spotlight_test.js")
    if shutil.which("node") is None:
        pytest.skip("node is required for tests/canvas_frontend_spotlight_test.js")
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
        "dash-agents",
        "dash-tasks",
        "dash-file-locks",
        "dash-worktrees",
        "dash-memory",
        "dash-errors",
    ]:
        assert f'id="{widget_id}"' in html, f"Missing widget: {widget_id}"


def test_dashboard_widgets_render_in_vertical_flow() -> None:
    """Dashboard widgets should be stacked in one container from top to bottom."""
    html = Path("synapse/canvas/templates/index.html").read_text(encoding="utf-8")
    section_start = html.index('id="dashboard-view"')
    section_end = html.index("</section>", section_start)
    dashboard_section = html[section_start:section_end]

    assert dashboard_section.count('class="dash-grid"') == 1
    assert dashboard_section.count('class="dash-widget"') >= 6
    assert 'class="dash-widget dash-full-width"' not in dashboard_section


def test_dashboard_css_classes_exist() -> None:
    """canvas.css should define dashboard-specific CSS classes."""
    css = Path("synapse/canvas/static/canvas.css").read_text(encoding="utf-8")
    for cls in [".dash-strip", ".dash-grid", ".dash-widget"]:
        assert cls in css, f"Missing CSS class: {cls}"


def test_system_skills_name_cells_allow_wrapping() -> None:
    """System skills name cells should wrap instead of colliding with descriptions."""
    css = Path("synapse/canvas/static/canvas.css").read_text(encoding="utf-8")
    start = css.index(".agent-name-cell {")
    end = css.index("}", start)
    block = css[start:end]

    assert "white-space: normal;" in block
    assert "overflow-wrap: anywhere;" in block or "word-break: break-word;" in block
    assert "white-space: nowrap;" not in block


def test_dashboard_layout_is_single_column() -> None:
    """Dashboard should use a single-column vertical layout on desktop."""
    css = Path("synapse/canvas/static/canvas.css").read_text(encoding="utf-8")
    start = css.index(".dash-grid {")
    end = css.index("}", start)
    dash_grid_block = css[start:end]

    assert "grid-template-columns: 1fr;" in dash_grid_block
    assert "grid-template-columns: 1fr 1fr;" not in dash_grid_block


def test_dashboard_route_in_js() -> None:
    """canvas.js should handle the dashboard route."""
    js = Path("synapse/canvas/static/canvas.js").read_text(encoding="utf-8")
    assert '"dashboard"' in js
    assert "dashboardView" in js or "dashboard-view" in js
    assert "renderDashboard" in js


def test_admin_view_exists_in_html() -> None:
    """index.html should contain the admin view shell and controls."""
    html = Path("synapse/canvas/templates/index.html").read_text(encoding="utf-8")
    for fragment in [
        'id="admin-view"',
        'id="admin-container"',
        'id="admin-agents-widget"',
        'id="admin-feed"',
        'id="admin-target-badge"',
        'id="admin-message-input"',
        'id="admin-send-btn"',
    ]:
        assert fragment in html, f"Missing admin fragment: {fragment}"


def test_admin_nav_link_exists_and_follows_system() -> None:
    """Admin nav link should exist and appear after the system nav item."""
    html = Path("synapse/canvas/templates/index.html").read_text(encoding="utf-8")
    system_pos = html.index('data-route="system"')
    admin_pos = html.index('data-route="admin"')
    assert system_pos < admin_pos


def test_admin_route_in_js() -> None:
    """canvas.js should expose admin route handling and DOM bindings."""
    js = Path("synapse/canvas/static/canvas.js").read_text(encoding="utf-8")

    assert 'document.getElementById("admin-view")' in js
    assert 'document.getElementById("admin-feed")' in js
    assert 'document.getElementById("admin-target-badge")' in js
    assert 'document.getElementById("admin-agents-widget")' in js
    assert 'document.getElementById("admin-message-input")' in js
    assert 'document.getElementById("admin-send-btn")' in js
    assert 'admin: "Admin"' in js
    assert 'currentRoute === "admin"' in js
    assert "loadAdminAgents();" in js


def test_admin_command_center_functions_exist_in_js() -> None:
    """canvas.js should define the admin command-center helpers."""
    js = Path("synapse/canvas/static/canvas.js").read_text(encoding="utf-8")

    for name in [
        "async function loadAdminAgents()",
        "function renderAdminAgentsWidget(agents)",
        "function createAdminBubble(role, text, agentName)",
        "function addAdminBubble(role, text, agentName)",
        "function addAdminSpinner()",
        "function removeAdminSpinner()",
        "async function sendAdminCommand()",
        "function pollAdminTask(taskId, target, agentName)",
        "function escapeHtml(str)",
    ]:
        assert name in js, f"Missing admin helper: {name}"


def test_admin_init_event_listeners_exist_in_js() -> None:
    """canvas.js should wire the admin send button, Enter key, and IME handlers."""
    js = Path("synapse/canvas/static/canvas.js").read_text(encoding="utf-8")

    assert 'adminSendBtn.addEventListener("click", sendAdminCommand)' in js
    assert 'adminMessageInput.addEventListener("keydown", function (e)' in js
    assert 'if (e.key === "Enter" && e.metaKey && !_isComposing)' in js


def test_admin_reply_polling_endpoint_used_in_js() -> None:
    """Admin command center should poll the reply endpoint instead of SSE streaming."""
    js = Path("synapse/canvas/static/canvas.js").read_text(encoding="utf-8")

    assert "/api/admin/replies/" in js
    assert "streamAdminTask(" not in js
    assert "/api/admin/stream/" not in js


def test_admin_bubble_creation_split_exists_in_js() -> None:
    """addAdminBubble should delegate DOM construction to createAdminBubble."""
    js = Path("synapse/canvas/static/canvas.js").read_text(encoding="utf-8")

    assert "function createAdminBubble(role, text, agentName)" in js
    assert "var bubble = createAdminBubble(role, text, agentName);" in js


def test_admin_css_classes_exist() -> None:
    """canvas.css should define the admin view layout and bubble styles."""
    css = Path("synapse/canvas/static/canvas.css").read_text(encoding="utf-8")

    for selector in [
        "#admin-view",
        "#admin-container",
        "#admin-agents-widget",
        "#admin-feed",
        ".admin-bubble",
        ".admin-bubble-user",
        ".admin-bubble-agent",
        "#admin-input-bar",
        "#admin-target-badge",
        "#admin-message-input",
        "#admin-send-btn",
        ".admin-spinner",
        ".admin-spinner-dot",
    ]:
        assert selector in css, f"Missing admin CSS selector: {selector}"


def test_canvas_view_image_block_can_expand_to_available_height() -> None:
    """Canvas view image blocks should be allowed to fill the spotlight body."""
    css = Path("synapse/canvas/static/canvas.css").read_text(encoding="utf-8")
    start = css.index(".canvas-content > .content-block {")
    end = css.index("}", start)
    base_block = css[start:end]

    assert "display: flex;" in base_block
    assert "flex-direction: column;" in base_block

    start = css.index(".canvas-content > .content-block.format-image {")
    end = css.index("}", start)
    image_block = css[start:end]

    assert "flex: 1;" in image_block
    assert "min-height: 0;" in image_block


def test_canvas_view_images_use_contained_full_size_scaling() -> None:
    """Canvas view images should use the full content area without introducing scrollbars."""
    css = Path("synapse/canvas/static/canvas.css").read_text(encoding="utf-8")
    start = css.index(".canvas-content .format-image img {")
    end = css.index("}", start)
    image_rule = css[start:end]

    assert "width: 100%;" in image_rule
    assert "height: 100%;" in image_rule
    assert "max-width: 100%;" in image_rule
    assert "max-height: 100%;" in image_rule
    assert "object-fit: contain;" in image_rule


def test_canvas_view_html_block_can_expand_to_available_height() -> None:
    """Canvas view HTML blocks should be allowed to fill the spotlight body."""
    css = Path("synapse/canvas/static/canvas.css").read_text(encoding="utf-8")
    js = Path("synapse/canvas/static/canvas.js").read_text(encoding="utf-8")
    start = css.index(".canvas-content > .content-block.format-html {")
    end = css.index("}", start)
    html_block = css[start:end]

    assert "flex: 1;" in html_block
    assert "min-height: 0;" in html_block

    start = css.index(".canvas-content .format-html iframe {")
    end = css.index("}", start)
    iframe_rule = css[start:end]

    assert "width: 100%;" in iframe_rule
    assert "height: 100%;" in iframe_rule
    assert "min-height: 0;" in iframe_rule
    assert "min-height: 200px;" not in iframe_rule
    assert "formatCanvasHTMLDocument" in js
    assert "html, body { height: 100%;" in js
    assert "body { margin: 0;" in js
    assert "overflow: hidden;" in js
    assert "options && options.inCanvasView === true" in js
    assert 'el.closest(".canvas-content")' not in js


def test_canvas_view_chart_does_not_use_fixed_height_caps() -> None:
    """Canvas view charts should not be clamped to viewport or pixel max-heights."""
    css = Path("synapse/canvas/static/canvas.css").read_text(encoding="utf-8")
    js = Path("synapse/canvas/static/canvas.js").read_text(encoding="utf-8")

    start = css.index(".canvas-content .format-chart canvas {")
    end = css.index("}", start)
    chart_rule = css[start:end]

    assert "max-height: 60vh;" not in chart_rule
    assert "height: 100%;" in chart_rule
    assert 'canvas.style.maxHeight = "400px";' not in js


def test_dashboard_agent_widget_uses_agents_label() -> None:
    """Dashboard agent widget should use the simpler 'Agents' label."""
    js = Path("synapse/canvas/static/canvas.js").read_text(encoding="utf-8")

    assert '"ph-robot", "Agents (" + agents.length + ")"' in js
    assert '"ph-robot", "Agent Fleet (' not in js


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


def test_dashboard_task_board_renders_all_status_columns() -> None:
    """renderSystemTasks should include the failed status column for dashboard task boards."""
    js = Path("synapse/canvas/static/canvas.js").read_text(encoding="utf-8")
    start = js.index("function renderSystemTasks(tasks)")
    end = js.index("\n  function renderSystemFileLocks(", start)
    body = js[start:end]

    assert '["pending", "in_progress", "completed", "failed"]' in body


def test_dashboard_task_board_shows_summary_and_detail() -> None:
    """Dashboard task widget should show summary bar and expandable detail."""
    js = Path("synapse/canvas/static/canvas.js").read_text(encoding="utf-8")
    start = js.index("function buildTaskBars(tasks) {")
    end = js.index("\n  function buildMemoryList(", start)
    body = js[start:end]

    assert "dash-task-bar-row" in body
    assert "renderSystemTasks(tasks)" in body


def test_task_card_shows_detail_on_click() -> None:
    """Task cards should show description, priority, assignee on click."""
    js = Path("synapse/canvas/static/canvas.js").read_text(encoding="utf-8")
    start = js.index("function renderSystemTasks(tasks)")
    end = js.index("\n  function renderSystemFileLocks(", start)
    body = js[start:end]

    assert "task-item-detail" in body
    assert "item.description" in body
    assert "item.priority" in body
    assert "item.created_by" in body


def test_canvas_server_sends_task_detail_fields() -> None:
    """Canvas server should include description, priority, created_by in task data."""
    source = Path("synapse/canvas/server.py").read_text(encoding="utf-8")

    assert '"description": row.get("description"' in source
    assert '"priority": row.get("priority"' in source
    assert '"created_by": row.get("created_by"' in source


def test_system_panel_polling_remains_enabled_for_dashboard_freshness() -> None:
    """Canvas should continue polling system data so dashboard agent/task widgets stay fresh."""
    js = Path("synapse/canvas/static/canvas.js").read_text(encoding="utf-8")

    assert "window.setInterval(loadSystemPanel, 10000);" in js


def test_live_feed_harness_uses_vm_instead_of_eval() -> None:
    """The Node harness should execute extracted code in a vm sandbox."""
    source = Path("tests/canvas_frontend_live_feed_test.js").read_text(encoding="utf-8")

    assert 'require("node:vm")' in source
    assert "new vm.Script(" in source
    assert "runInNewContext(" in source or "runInContext(" in source
    assert "eval(script)" not in source


def test_spotlight_harness_uses_vm_instead_of_eval() -> None:
    """The spotlight harness should execute extracted code in a vm sandbox."""
    source = Path("tests/canvas_frontend_spotlight_test.js").read_text(encoding="utf-8")

    assert 'require("node:vm")' in source
    assert "new vm.Script(" in source
    assert "runInNewContext(" in source or "runInContext(" in source
    assert "eval(script)" not in source


def test_system_panel_harness_uses_vm_instead_of_eval() -> None:
    """The system panel harness should execute extracted code in a vm sandbox."""
    source = Path("tests/canvas_frontend_system_panel_test.js").read_text(
        encoding="utf-8"
    )

    assert 'require("node:vm")' in source
    assert "new vm.Script(" in source
    assert "runInNewContext(" in source or "runInContext(" in source
    assert "eval(script)" not in source


def test_spotlight_swap_delay_uses_named_constant() -> None:
    """Spotlight swap timing should use a named constant instead of a bare literal."""
    js = Path("synapse/canvas/static/canvas.js").read_text(encoding="utf-8")
    start = js.index("function markSpotlightSwap()")
    end = js.index(
        "\n\n  // ----------------------------------------------------------------",
        start,
    )
    body = js[start:end]

    assert "const SPOTLIGHT_SWAP_DELAY = 420;" in js
    assert "SPOTLIGHT_SWAP_DELAY" in body
    assert "}, 420);" not in body


def test_extract_function_documents_brace_counting_limitations() -> None:
    """The helper should document where the brace-counting extractor can fail."""
    source = Path("tests/canvas_test_helpers.js").read_text(encoding="utf-8")

    assert (
        "This simple brace-counting extractor assumes the target function body"
        in source
    )
    assert "braces inside strings, template literals, or comments" in source
    assert "A robust fix would require a real parser or tokenizer." in source


def test_render_live_feed_reuses_existing_items() -> None:
    """History live feed should preserve existing DOM nodes instead of rebuilding all rows."""
    js = Path("synapse/canvas/static/canvas.js").read_text(encoding="utf-8")
    start = js.index("function renderLiveFeed(recentCards)")
    end = js.index("\n  function createAgentPanel(", start)
    body = js[start:end]

    assert "existingItems" in body
    assert "dataset.cardId" in body
    assert "existingItem" in body


def test_history_rendering_uses_keyed_updates_instead_of_wholesale_clear() -> None:
    """History rendering should avoid clearing the entire grid on every update."""
    js = Path("synapse/canvas/static/canvas.js").read_text(encoding="utf-8")
    start = js.index("function renderAll()")
    end = js.index("\n  function renderLiveFeed(", start)
    body = js[start:end]
    update_body = js[
        js.index("function updateAgentPanel(") : js.index(
            "\n  // Format type", js.index("function updateAgentPanel(")
        )
    ]

    assert 'grid.innerHTML = "";' not in body
    assert "existingPanels" in body
    assert "existingCards" in update_body


def test_spotlight_rendering_avoids_wholesale_rebuild_for_same_card_updates() -> None:
    """Spotlight rendering should preserve the shell and update only card content when possible."""
    js = Path("synapse/canvas/static/canvas.js").read_text(encoding="utf-8")
    start = js.index("function renderSpotlight()")
    end = js.index(
        "\n  // ----------------------------------------------------------------\n  // Init",
        start,
    )
    body = js[start:end]

    assert "ensureSpotlightFrame()" in body
    assert "renderSpotlightContent(" in body
    assert "renderSpotlightInfo(" in body
    assert 'canvasSpotlight.innerHTML = "";' not in body


def test_history_css_limits_entry_animations_to_new_items() -> None:
    """History CSS should animate only explicitly marked new items."""
    css = Path("synapse/canvas/static/canvas.css").read_text(encoding="utf-8")
    live_feed_start = css.index(".live-feed-item {")
    live_feed_block = css[live_feed_start : css.index("}", live_feed_start)]
    agent_panel_start = css.index(".agent-panel {")
    agent_panel_block = css[agent_panel_start : css.index("}", agent_panel_start)]
    canvas_card_start = css.index(".canvas-card {")
    canvas_card_block = css[canvas_card_start : css.index("}", canvas_card_start)]

    assert ".live-feed-item.is-new" in css
    assert ".agent-panel.is-new" in css
    assert ".canvas-card.is-new" in css
    assert "animation:" not in live_feed_block
    assert "animation:" not in agent_panel_block
    assert "animation:" not in canvas_card_block


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


def test_dashboard_widgets_use_expandable_detail_pattern() -> None:
    """Each dashboard widget should use createDashWidget for summary+detail toggle."""
    js = Path("synapse/canvas/static/canvas.js").read_text(encoding="utf-8")

    assert "function createDashWidget(" in js
    assert "_dashExpandState" in js
    assert "dash-widget-chevron" in js

    # Each renderDash* function should call createDashWidget
    for fn in [
        "renderDashAgents",
        "renderDashTasks",
        "renderDashMemory",
        "renderDashFileLocks",
        "renderDashWorktrees",
        "renderDashErrors",
    ]:
        start = js.index(f"function {fn}(")
        end = js.index("\n  function ", start + 1)
        body = js[start:end]
        assert "createDashWidget(" in body, f"{fn} should use createDashWidget"


def test_dashboard_expand_state_persists_across_renders() -> None:
    """Expand state should be stored in a module-level object, not per-render."""
    js = Path("synapse/canvas/static/canvas.js").read_text(encoding="utf-8")

    assert "var _dashExpandState = {};" in js


def test_dashboard_detail_sections_reuse_system_renderers() -> None:
    """Expanded detail sections should reuse renderSystem* functions."""
    js = Path("synapse/canvas/static/canvas.js").read_text(encoding="utf-8")

    # Memory detail should use renderSystemMemories
    start = js.index("function renderDashMemory(")
    end = js.index("\n  function ", start + 1)
    body = js[start:end]
    assert "renderSystemMemories(" in body


def test_dashboard_css_has_expand_collapse_styles() -> None:
    """canvas.css should define styles for the expandable widget pattern."""
    css = Path("synapse/canvas/static/canvas.css").read_text(encoding="utf-8")

    assert ".dash-widget-chevron" in css
    assert ".dash-widget-detail" in css
    assert ".dash-widget-detail.expanded" in css


def test_phase6_renderers_exist_in_js() -> None:
    """canvas.js should define render functions for progress, terminal, dependency-graph, cost."""
    js = Path("synapse/canvas/static/canvas.js").read_text(encoding="utf-8")
    for fn in [
        "renderProgress",
        "renderTerminal",
        "renderDependencyGraph",
        "renderCost",
    ]:
        assert f"function {fn}(el, body)" in js, f"Missing renderer: {fn}"


def test_phase6_formats_in_render_block_switch() -> None:
    """renderBlock switch should dispatch to the 4 new renderers."""
    js = Path("synapse/canvas/static/canvas.js").read_text(encoding="utf-8")
    start = js.index("function renderBlock(block, options)")
    end = js.index("\n  // ------", start)
    body = js[start:end]

    for fmt in ["progress", "terminal", "dependency-graph", "cost"]:
        assert f'case "{fmt}":' in body, f"Missing case for '{fmt}' in renderBlock"


def test_phase6_filter_options_in_html() -> None:
    """index.html filter dropdown should include new card types."""
    html = Path("synapse/canvas/templates/index.html").read_text(encoding="utf-8")
    for fmt in ["progress", "terminal", "dependency-graph", "cost"]:
        assert f'value="{fmt}"' in html, f"Missing filter option: {fmt}"


def test_phase6_css_classes_exist() -> None:
    """canvas.css should define CSS classes for the 4 new card types."""
    css = Path("synapse/canvas/static/canvas.css").read_text(encoding="utf-8")
    for cls in [".progress-bar", ".terminal-output", ".dep-graph", ".cost-table"]:
        assert cls in css, f"Missing CSS class: {cls}"


def test_progress_renderer_has_bar_and_steps() -> None:
    """renderProgress should render a progress bar and step list."""
    js = Path("synapse/canvas/static/canvas.js").read_text(encoding="utf-8")
    start = js.index("function renderProgress(el, body)")
    end = js.index("\n  function ", start + 1)
    body = js[start:end]

    assert "progress-bar" in body
    assert "progress-fill" in body
    assert "current" in body
    assert "total" in body


def test_terminal_renderer_handles_ansi() -> None:
    """renderTerminal should process ANSI escape codes."""
    js = Path("synapse/canvas/static/canvas.js").read_text(encoding="utf-8")
    start = js.index("function renderTerminal(el, body)")
    end = js.index("\n  function ", start + 1)
    body = js[start:end]

    assert "terminal-output" in body
    # Should handle ANSI color codes
    assert "\\x1b" in body or "\\u001b" in body or "ansi" in body.lower()


def test_code_renderer_supports_inline_meta_row() -> None:
    """renderCode should support title/filename metadata via block-level x_title/x_filename."""
    js = Path("synapse/canvas/static/canvas.js").read_text(encoding="utf-8")
    css = Path("synapse/canvas/static/canvas.css").read_text(encoding="utf-8")
    start = js.index("function renderCode(el, body, lang, block)")
    end = js.index("\n  function renderImage(", start)
    body = js[start:end]

    assert 'buildMetaRow("code", block)' in body
    assert ".code-view-meta" in css
    assert ".code-title" in css
    assert ".code-filename" in css


def test_dependency_graph_renderer_has_nodes_and_edges() -> None:
    """renderDependencyGraph should render nodes and edges."""
    js = Path("synapse/canvas/static/canvas.js").read_text(encoding="utf-8")
    start = js.index("function renderDependencyGraph(el, body)")
    end = js.index("\n  function ", start + 1)
    body = js[start:end]

    assert "nodes" in body
    assert "edges" in body
    assert "dep-graph" in body


def test_cost_renderer_has_table_and_total() -> None:
    """renderCost should render agent cost table and total."""
    js = Path("synapse/canvas/static/canvas.js").read_text(encoding="utf-8")
    start = js.index("function renderCost(el, body)")
    end = js.index("\n  function ", start + 1)
    body = js[start:end]

    assert "cost-table" in body
    assert "total_cost" in body
    assert "agents" in body


def test_json_renderer_supports_optional_inner_title() -> None:
    """renderJSON should render a subtle single-line meta row via shared helpers."""
    js = Path("synapse/canvas/static/canvas.js").read_text(encoding="utf-8")
    css = Path("synapse/canvas/static/canvas.css").read_text(encoding="utf-8")
    start = js.index("function renderJSON(el, body, block)")
    end = js.index("\n  function buildDiffPane(", start)
    body = js[start:end]

    assert 'buildMetaRow("json", block)' in body
    assert ".json-view-meta" in css
    assert ".json-title" in css
    assert ".json-filename" in css
    meta_block = css.split(".json-view-meta", 1)[1].split("}", 1)[0]
    assert "display: flex;" in meta_block
    assert "justify-content: space-between;" in meta_block
    assert "flex-wrap: nowrap;" in meta_block
    assert "background:" not in meta_block
    title_block = css.split(".json-title", 1)[1].split("}", 1)[0]
    filename_block = css.split(".json-filename", 1)[1].split("}", 1)[0]
    assert "font-size: var(--text-xs);" in title_block
    assert "font-size: var(--text-xs);" in filename_block


def test_mermaid_theme_syncs_with_canvas_theme() -> None:
    """Mermaid should use custom theme variables that change with light/dark toggle."""
    source = Path("synapse/canvas/static/canvas.js").read_text(encoding="utf-8")

    # Theme config exists for both modes
    assert "MERMAID_THEMES" in source
    assert "dark:" in source or '"dark"' in source
    assert "light:" in source or '"light"' in source
    assert "initMermaidTheme" in source

    # Theme variables use Canvas brand color
    assert "4051b5" in source, "should use Canvas brand color in Mermaid theme"

    # Source preservation for re-rendering on theme switch
    assert "mermaidSource" in source, (
        "should store source for re-render on theme switch"
    )

    # Theme toggle triggers Mermaid re-render
    assert "initMermaidTheme(next)" in source


def test_mermaid_renderer_supports_inline_meta_row() -> None:
    """renderMermaid should support title/filename metadata via shared helpers."""
    js = Path("synapse/canvas/static/canvas.js").read_text(encoding="utf-8")
    css = Path("synapse/canvas/static/canvas.css").read_text(encoding="utf-8")
    start = js.index("function renderMermaid(el, body, block)")
    end = js.index(
        "\n  /** Run mermaid on pending diagrams and fix SVG heights afterward. */",
        start,
    )
    body = js[start:end]

    assert 'buildMetaRow("mermaid", block)' in body
    assert "mermaid-panel" in body
    assert ".mermaid-view-meta" in css
    assert ".mermaid-title" in css
    assert ".mermaid-filename" in css


def test_tip_renderer_supports_string_body_with_meta_row() -> None:
    """renderTip should keep string body semantics and render block-level metadata separately."""
    js = Path("synapse/canvas/static/canvas.js").read_text(encoding="utf-8")
    css = Path("synapse/canvas/static/canvas.css").read_text(encoding="utf-8")

    assert 'case "tip":' in js
    start = js.index('case "tip":')
    end = js.index('case "progress":', start)
    switch_body = js[start:end]
    assert "renderTip(wrap, block.body, block)" in switch_body

    start = js.index("function renderTip(el, body, block)")
    end = js.index("\n  function renderProgress(", start)
    body = js[start:end]

    assert 'buildMetaRow("tip", block)' in body
    assert 'typeof body === "string"' in body
    assert ".tip-view-meta" in css
    assert ".tip-title" in css
    assert ".tip-filename" in css


def test_log_renderer_parses_json_strings_and_supports_meta_row() -> None:
    """renderLog should preserve structured entries while accepting JSON-string bodies."""
    js = Path("synapse/canvas/static/canvas.js").read_text(encoding="utf-8")
    css = Path("synapse/canvas/static/canvas.css").read_text(encoding="utf-8")
    start = js.index("function renderLog(el, body, block)")
    end = js.index("\n  function renderStatus(", start)
    body = js[start:end]

    assert "parseBody(body)" in body
    assert 'buildMetaRow("log", block)' in body
    assert "Array.isArray(data)" in body
    assert ".log-view-meta" in css
    assert ".log-title" in css
    assert ".log-filename" in css


def test_checklist_renderer_parses_json_strings_and_supports_meta_row() -> None:
    """renderChecklist should keep list semantics while accepting JSON-string bodies."""
    js = Path("synapse/canvas/static/canvas.js").read_text(encoding="utf-8")
    css = Path("synapse/canvas/static/canvas.css").read_text(encoding="utf-8")
    start = js.index("function renderChecklist(el, body, block)")
    end = js.index("\n  function renderTimeline(", start)
    body = js[start:end]

    assert "parseBody(body)" in body
    assert 'buildMetaRow("checklist", block)' in body
    assert "Array.isArray(data)" in body
    assert ".checklist-view-meta" in css
    assert ".checklist-title" in css
    assert ".checklist-filename" in css


def test_trace_renderer_parses_json_strings_and_supports_meta_row() -> None:
    """renderTrace should keep list semantics while accepting JSON-string bodies."""
    js = Path("synapse/canvas/static/canvas.js").read_text(encoding="utf-8")
    css = Path("synapse/canvas/static/canvas.css").read_text(encoding="utf-8")
    start = js.index("function renderTrace(el, body, block)")
    end = js.index("\n  function renderTraceSpan(", start)
    body = js[start:end]

    assert "parseBody(body)" in body
    assert 'buildMetaRow("trace", block)' in body
    assert "Array.isArray(data)" in body
    assert ".trace-view-meta" in css
    assert ".trace-title" in css
    assert ".trace-filename" in css


def test_sidebar_collapse_toggle() -> None:
    """Sidebar should have a collapse/expand toggle with localStorage persistence."""
    source = Path("synapse/canvas/static/canvas.js").read_text(encoding="utf-8")
    css = Path("synapse/canvas/static/canvas.css").read_text(encoding="utf-8")
    html = Path("synapse/canvas/templates/index.html").read_text(encoding="utf-8")

    # HTML: collapse toggle button exists in sidebar header
    assert "sidebar-collapse" in html, "sidebar-collapse button should exist in HTML"

    # CSS: sidebar-collapsed class hides sidebar and adjusts main content
    assert "sidebar-collapsed" in css, "sidebar-collapsed CSS class should exist"

    # JS: toggle logic reads/writes localStorage for persistence
    assert "sidebar-collapsed" in source, "JS should toggle sidebar-collapsed class"
    assert "canvas-sidebar" in source, "JS should persist sidebar state to localStorage"


def test_sidebar_header_allows_title_to_wrap_inside_panel() -> None:
    """Sidebar header should wrap the title instead of overflowing the toggle button."""
    css = Path("synapse/canvas/static/canvas.css").read_text(encoding="utf-8")
    heading_block = css.split(".sidebar-header h1 {", 1)[1].split("}", 1)[0]

    assert ".sidebar-header {" in css
    assert "grid-template-columns: minmax(0, 1fr) auto;" in css
    assert "white-space: nowrap;" not in heading_block


def test_collapsed_sidebar_uses_compact_width() -> None:
    """Collapsed sidebar should return to a compact width when labels are hidden."""
    css = Path("synapse/canvas/static/canvas.css").read_text(encoding="utf-8")

    assert "body.sidebar-collapsed #sidebar {" in css
    assert "width: var(--sidebar-collapsed-width);" in css
    assert "--sidebar-collapsed-width: 56px;" in css


def test_collapsed_sidebar_header_hides_title_and_keeps_button_inside() -> None:
    """Collapsed sidebar should hide the title and keep the toggle inside the panel."""
    css = Path("synapse/canvas/static/canvas.css").read_text(encoding="utf-8")
    collapsed_heading_block = css.split(
        "body.sidebar-collapsed .sidebar-header h1 {", 1
    )[1].split("}", 1)[0]

    assert "body.sidebar-collapsed .sidebar-header h1 {" in css
    assert "font-size: 0;" in collapsed_heading_block
    assert "overflow: hidden;" in collapsed_heading_block
    assert "justify-content: center;" in collapsed_heading_block
    assert "body.sidebar-collapsed #sidebar-collapse {" in css
    collapsed_icon_block = css.split(
        "body.sidebar-collapsed .sidebar-header h1 .brand-icon {", 1
    )[1].split("}", 1)[0]
    assert "display: none;" in collapsed_icon_block


def test_collapsed_main_content_margin_matches_sidebar_width() -> None:
    """Collapsed layout should still shift the main content by the sidebar width."""
    css = Path("synapse/canvas/static/canvas.css").read_text(encoding="utf-8")

    assert "body.sidebar-collapsed #main-content {" in css


def test_canvas_js_does_not_render_or_prioritize_pinned_cards() -> None:
    """canvas.js should ignore legacy pin state in the frontend."""
    source = Path("synapse/canvas/static/canvas.js").read_text(encoding="utf-8")

    assert "if (a.pinned && !b.pinned)" not in source
    assert "if (!a.pinned && b.pinned)" not in source
    assert 'pin.className = "pin-icon"' not in source


def test_admin_ime_composition_listeners_exist() -> None:
    """canvas.js should register compositionstart/compositionend for IME support."""
    js = Path("synapse/canvas/static/canvas.js").read_text(encoding="utf-8")

    assert "compositionstart" in js
    assert "compositionend" in js
    assert "_isComposing" in js


def test_admin_target_badge_exists_in_html() -> None:
    """index.html should have a badge for showing selected agent."""
    html = Path("synapse/canvas/templates/index.html").read_text(encoding="utf-8")

    assert 'id="admin-target-badge"' in html


def test_admin_agents_widget_reuses_renderSystemAgents() -> None:
    """canvas.js should reuse renderSystemAgents with onRowClick for admin selection."""
    js = Path("synapse/canvas/static/canvas.js").read_text(encoding="utf-8")

    assert "renderAdminAgentsWidget" in js
    assert "_selectedAdminTarget" in js
    assert "admin-row-selected" in js
    # Admin widget delegates to shared renderSystemAgents with options
    assert "renderSystemAgents(agents, {" in js
    assert "onRowClick" in js
    # Shared row builder
    assert "function buildAgentRow(agent)" in js


def test_admin_no_console_log_debug() -> None:
    """canvas.js should not contain console.log debug lines for admin."""
    js = Path("synapse/canvas/static/canvas.js").read_text(encoding="utf-8")

    assert 'console.log("[Admin]' not in js


def test_admin_bubble_max_width_is_90_percent() -> None:
    """Admin bubbles should use 90% max-width for better readability."""
    css = Path("synapse/canvas/static/canvas.css").read_text(encoding="utf-8")
    start = css.index(".admin-bubble {")
    end = css.index("}", start)
    block = css[start:end]

    assert "max-width: 90%;" in block


def test_admin_badge_has_proper_styling() -> None:
    """Admin target badge should have consistent styling."""
    css = Path("synapse/canvas/static/canvas.css").read_text(encoding="utf-8")

    assert "#admin-target-badge {" in css
    assert ".admin-row-selected" in css
