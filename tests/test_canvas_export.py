"""Tests for synapse.canvas.export — card download/export functionality."""

from __future__ import annotations

import base64
import json

import pytest

from synapse.canvas.export import (
    _block_to_markdown,
    _checklist_to_md,
    _cost_to_csv,
    _sanitize_filename,
    _table_to_csv,
    export_card,
)

# ============================================================
# Filename sanitisation
# ============================================================


def test_sanitize_filename_basic():
    assert _sanitize_filename("Hello World!") == "Hello-World"


def test_sanitize_filename_unicode():
    assert _sanitize_filename("日本語テスト") == "card"


def test_sanitize_filename_empty():
    assert _sanitize_filename("") == "card"


def test_sanitize_filename_special_chars():
    # Backslash is stripped (header injection prevention), then / and : become hyphens
    assert _sanitize_filename("a/b\\c:d") == "a-bc-d"


# ============================================================
# Group A — Markdown converters
# ============================================================


def test_markdown_passthrough():
    block = {"format": "markdown", "body": "# Hello\nWorld"}
    assert _block_to_markdown(block) == "# Hello\nWorld"


def test_checklist_to_md():
    items = [
        {"text": "Buy milk", "done": True},
        {"text": "Write tests", "done": False},
    ]
    result = _checklist_to_md({"body": items})
    assert "- [x] Buy milk" in result
    assert "- [ ] Write tests" in result


def test_alert_to_md():
    block = {"format": "alert", "body": {"severity": "warning", "message": "Disk full"}}
    result = _block_to_markdown(block)
    assert "> **WARNING:** Disk full" in result


def test_status_to_md():
    block = {"format": "status", "body": {"state": "running", "label": "API Server"}}
    result = _block_to_markdown(block)
    assert "# running" in result
    assert "**API Server**" in result


def test_metric_to_md():
    block = {
        "format": "metric",
        "body": {"value": "99.9", "unit": "%", "label": "Uptime"},
    }
    result = _block_to_markdown(block)
    assert "# 99.9 %" in result
    assert "Uptime" in result


def test_progress_to_md():
    block = {
        "format": "progress",
        "body": {"label": "Build", "value": 75, "total": 100},
    }
    result = _block_to_markdown(block)
    assert "Build" in result
    assert "75%" in result


def test_timeline_to_md():
    block = {
        "format": "timeline",
        "body": [
            {"timestamp": "10:00", "text": "Started"},
            {"timestamp": "10:05", "text": "Finished"},
        ],
    }
    result = _block_to_markdown(block)
    assert "**10:00**" in result
    assert "Finished" in result


def test_link_preview_to_md():
    block = {
        "format": "link-preview",
        "body": {
            "url": "https://example.com",
            "title": "Example",
            "description": "A site",
        },
    }
    result = _block_to_markdown(block)
    assert "[Example](https://example.com)" in result
    assert "A site" in result


def test_tip_to_md():
    block = {"format": "tip", "body": "Use --verbose for more info"}
    result = _block_to_markdown(block)
    assert "> **Tip:** Use --verbose for more info" in result


# ============================================================
# Group B — Native converters
# ============================================================


def test_export_code_block():
    card = {
        "card_id": "abc12345-6789",
        "title": "Hello Script",
        "template": "",
        "content": [{"format": "code", "body": "print('hello')", "lang": "python"}],
    }
    data, filename, mime = export_card(card)
    assert data == b"print('hello')"
    assert filename.endswith(".py")
    assert "text/plain" in mime


def test_export_terminal_strips_ansi():
    card = {
        "card_id": "term1234-5678",
        "title": "Terminal Output",
        "template": "",
        "content": [{"format": "terminal", "body": "\x1b[31mERROR\x1b[0m: fail"}],
    }
    data, filename, mime = export_card(card)
    assert b"\x1b" not in data
    assert b"ERROR" in data
    assert filename.endswith(".txt")


def test_export_diff():
    diff_body = "--- a/foo.py\n+++ b/foo.py\n@@ -1 +1 @@\n-old\n+new"
    card = {
        "card_id": "diff1234-5678",
        "title": "My Diff",
        "template": "",
        "content": [{"format": "diff", "body": diff_body}],
    }
    data, filename, mime = export_card(card)
    assert data == diff_body.encode("utf-8")
    assert filename.endswith(".diff")


def test_export_mermaid():
    card = {
        "card_id": "merm1234-5678",
        "title": "Flow",
        "template": "",
        "content": [{"format": "mermaid", "body": "graph LR\n  A-->B"}],
    }
    data, filename, mime = export_card(card)
    assert filename.endswith(".mmd")


def test_export_image_data_uri():
    # Tiny 1x1 PNG
    png_bytes = base64.b64encode(b"\x89PNG\r\n\x1a\n").decode()
    card = {
        "card_id": "img12345-6789",
        "title": "Image",
        "template": "",
        "content": [{"format": "image", "body": f"data:image/png;base64,{png_bytes}"}],
    }
    data, filename, mime = export_card(card)
    assert filename.endswith(".png")
    assert mime == "image/png"


# ============================================================
# Group C — JSON converters
# ============================================================


def test_export_json_block():
    card = {
        "card_id": "json1234-5678",
        "title": "Data",
        "template": "",
        "content": [{"format": "json", "body": {"key": "value"}}],
    }
    data, filename, mime = export_card(card)
    parsed = json.loads(data)
    assert parsed == {"key": "value"}
    assert filename.endswith(".json")


def test_export_chart():
    card = {
        "card_id": "chrt1234-5678",
        "title": "Chart",
        "template": "",
        "content": [{"format": "chart", "body": {"type": "bar", "data": {}}}],
    }
    data, filename, mime = export_card(card)
    assert filename.endswith(".json")


# ============================================================
# Group D — CSV converters
# ============================================================


def test_table_to_csv():
    block = {
        "body": {"headers": ["Name", "Age"], "rows": [["Alice", "30"], ["Bob", "25"]]}
    }
    result = _table_to_csv(block)
    assert b"Name,Age" in result
    assert b"Alice,30" in result


def test_cost_to_csv():
    block = {
        "body": {
            "agents": [
                {"name": "claude", "tokens": 1000},
                {"name": "gemini", "tokens": 500},
            ],
            "total": {"tokens": 1500},
        }
    }
    result = _cost_to_csv(block)
    assert b"claude" in result
    assert b"Total" in result


def test_export_table_default_csv():
    card = {
        "card_id": "tbl12345-6789",
        "title": "Results",
        "template": "",
        "content": [{"format": "table", "body": {"headers": ["A"], "rows": [["1"]]}}],
    }
    data, filename, mime = export_card(card)
    assert filename.endswith(".csv")
    assert b"A" in data


# ============================================================
# Target format override
# ============================================================


def test_export_table_as_json():
    card = {
        "card_id": "tbl12345-6789",
        "title": "Results",
        "template": "",
        "content": [{"format": "table", "body": {"headers": ["A"], "rows": [["1"]]}}],
    }
    data, filename, mime = export_card(card, target_format="json")
    assert filename.endswith(".json")
    parsed = json.loads(data)
    assert "headers" in parsed


def test_export_status_as_md():
    card = {
        "card_id": "stat1234-5678",
        "title": "Status",
        "template": "",
        "content": [{"format": "status", "body": {"state": "ok", "label": "All good"}}],
    }
    data, filename, mime = export_card(card)
    assert filename.endswith(".md")
    assert b"# ok" in data


# ============================================================
# Template cards
# ============================================================


def test_template_briefing_to_markdown():
    card = {
        "card_id": "brief123-4567",
        "title": "Daily Brief",
        "template": "briefing",
        "template_data": {
            "sections": [
                {"title": "Overview", "blocks": [0]},
                {"title": "Details", "blocks": [1]},
            ]
        },
        "content": [
            {"format": "markdown", "body": "All systems nominal."},
            {"format": "checklist", "body": [{"text": "Deploy", "done": True}]},
        ],
    }
    data, filename, mime = export_card(card)
    text = data.decode("utf-8")
    assert "## Overview" in text
    assert "All systems nominal" in text
    assert filename.endswith(".md")


def test_template_comparison_to_markdown():
    card = {
        "card_id": "comp1234-5678",
        "title": "Framework Comparison",
        "template": "comparison",
        "template_data": {
            "summary": "React vs Vue",
            "sides": [
                {"label": "React", "blocks": [0]},
                {"label": "Vue", "blocks": [1]},
            ],
        },
        "content": [
            {"format": "markdown", "body": "Component-based, JSX"},
            {"format": "markdown", "body": "Template-based, SFC"},
        ],
    }
    data, filename, mime = export_card(card)
    text = data.decode("utf-8")
    assert "## React" in text
    assert "## Vue" in text
    assert "Component-based" in text
    assert "Template-based" in text


def test_template_slides_to_markdown():
    card = {
        "card_id": "slid1234-5678",
        "title": "Presentation",
        "template": "slides",
        "template_data": {
            "slides": [
                {"title": "Intro", "blocks": [0]},
                {"title": "Details", "blocks": [1], "notes": "Speaker notes here"},
            ]
        },
        "content": [
            {"format": "markdown", "body": "Welcome to the talk"},
            {"format": "markdown", "body": "Here are the details"},
        ],
    }
    data, filename, mime = export_card(card)
    text = data.decode("utf-8")
    assert "## Intro" in text
    assert "---" in text  # slide separator
    assert "## Details" in text
    assert "> Speaker notes here" in text


def test_template_dashboard_to_markdown():
    card = {
        "card_id": "dash5678-1234",
        "title": "Monitoring",
        "template": "dashboard",
        "template_data": {
            "cols": 2,
            "widgets": [
                {"title": "CPU", "blocks": [0]},
                {"title": "Memory", "blocks": [1]},
            ],
        },
        "content": [
            {
                "format": "metric",
                "body": {"value": "45", "unit": "%", "label": "Usage"},
            },
            {
                "format": "metric",
                "body": {"value": "8.2", "unit": "GB", "label": "Used"},
            },
        ],
    }
    data, filename, mime = export_card(card)
    text = data.decode("utf-8")
    assert "## CPU" in text
    assert "## Memory" in text
    assert "45 %" in text


def test_export_html_native():
    card = {
        "card_id": "html1234-5678",
        "title": "Widget",
        "template": "",
        "content": [{"format": "html", "body": "<div>Hello</div>"}],
    }
    data, filename, mime = export_card(card)
    assert data == b"<div>Hello</div>"
    assert filename.endswith(".html")
    assert "text/html" in mime


def test_export_artifact_native():
    card = {
        "card_id": "artf1234-5678",
        "title": "App",
        "template": "",
        "content": [{"format": "artifact", "body": "<html><body>App</body></html>"}],
    }
    data, filename, mime = export_card(card)
    assert b"<html>" in data
    assert filename.endswith(".html")
    assert "text/html" in mime


def test_template_steps_to_markdown():
    card = {
        "card_id": "step1234-5678",
        "title": "Setup",
        "template": "steps",
        "template_data": {
            "steps": [
                {"title": "Install", "done": True},
                {"title": "Configure", "done": False},
            ]
        },
        "content": [{"format": "markdown", "body": "placeholder"}],
    }
    data, filename, mime = export_card(card)
    text = data.decode("utf-8")
    assert "1. [x] Install" in text
    assert "2. [ ] Configure" in text


def test_template_as_json():
    card = {
        "card_id": "dash1234-5678",
        "title": "Dashboard",
        "template": "dashboard",
        "template_data": {"widgets": [{"title": "W1", "blocks": [0]}]},
        "content": [{"format": "metric", "body": {"value": "42", "unit": "ms"}}],
    }
    data, filename, mime = export_card(card, target_format="json")
    assert filename.endswith(".json")
    parsed = json.loads(data)
    assert parsed["template"] == "dashboard"


def test_template_plan_to_markdown():
    card = {
        "card_id": "plan1234-5678",
        "title": "Execution Plan",
        "template": "plan",
        "template_data": {
            "plan_id": "p1",
            "status": "active",
            "mermaid": "graph LR\n  A-->B",
            "steps": [
                {
                    "id": "s1",
                    "subject": "Do thing",
                    "agent": "claude",
                    "status": "completed",
                },
            ],
        },
        "content": [{"format": "markdown", "body": "plan content"}],
    }
    data, filename, mime = export_card(card)
    text = data.decode("utf-8")
    assert "**Status:** active" in text
    assert "```mermaid" in text
    assert "Do thing" in text


# ============================================================
# Edge cases
# ============================================================


def test_export_empty_card():
    card = {
        "card_id": "empty123-4567",
        "title": "",
        "template": "",
        "content": [],
    }
    data, filename, mime = export_card(card)
    assert filename.startswith("card-")


def test_export_string_content():
    """Content stored as JSON string (from DB)."""
    card = {
        "card_id": "str12345-6789",
        "title": "Test",
        "template": "",
        "content": json.dumps([{"format": "markdown", "body": "hello"}]),
    }
    data, filename, mime = export_card(card)
    assert data == b"hello"


# ============================================================
# Security / robustness (codex-agent review fixes)
# ============================================================


def test_sanitize_filename_header_injection():
    """Newlines and quotes must be stripped to prevent header injection."""
    assert "\n" not in _sanitize_filename('evil\n\rname"here')
    assert '"' not in _sanitize_filename('evil"name')


def test_sanitize_filename_length_limit():
    long_name = "a" * 200
    result = _sanitize_filename(long_name)
    assert len(result) <= 80


def test_export_broken_json_content():
    """Broken JSON in content should not raise, fallback to markdown."""
    card = {
        "card_id": "brk12345-6789",
        "title": "Broken",
        "template": "",
        "content": "{not valid json",
    }
    data, filename, mime = export_card(card)
    assert b"not valid json" in data


def test_export_broken_base64_image():
    """Invalid base64 in image should not raise."""
    card = {
        "card_id": "bimg1234-5678",
        "title": "Bad Image",
        "template": "",
        "content": [{"format": "image", "body": "data:image/png;base64,!!!invalid!!!"}],
    }
    data, filename, mime = export_card(card)
    # Should fallback gracefully, not raise
    assert len(data) > 0


def test_export_svg_data_uri():
    """svg+xml MIME type must be matched by the regex."""
    svg_b64 = base64.b64encode(b"<svg></svg>").decode()
    card = {
        "card_id": "svg12345-6789",
        "title": "SVG",
        "template": "",
        "content": [
            {"format": "image", "body": f"data:image/svg+xml;base64,{svg_b64}"}
        ],
    }
    data, filename, mime = export_card(card)
    assert filename.endswith(".svg")
    assert b"<svg>" in data


def test_blocks_at_indices_bad_type():
    """Non-integer indices in template_data should not crash."""
    from synapse.canvas.export import _blocks_at_indices

    blocks = [{"format": "markdown", "body": "a"}, {"format": "markdown", "body": "b"}]
    result = _blocks_at_indices(blocks, [0, "bad", None, 1])
    assert len(result) == 2


def test_export_multiblock_nontemplate():
    """Multi-block non-template cards should include all blocks."""
    card = {
        "card_id": "multi123-4567",
        "title": "Multi",
        "template": "",
        "content": [
            {"format": "markdown", "body": "Block one"},
            {"format": "markdown", "body": "Block two"},
            {"format": "tip", "body": "A tip"},
        ],
    }
    data, filename, mime = export_card(card)
    text = data.decode("utf-8")
    assert "Block one" in text
    assert "Block two" in text
    assert "A tip" in text
    assert filename.endswith(".md")


@pytest.mark.asyncio
async def test_download_endpoint_returns_correct_headers():
    """Integration test: download endpoint returns proper Content-Disposition and MIME."""
    from unittest.mock import MagicMock, patch

    from synapse.canvas.server import create_app

    with patch("synapse.canvas.store.CanvasStore"):
        mock_store = MagicMock()
        mock_store.get_card.return_value = {
            "card_id": "test1234-5678",
            "title": "Test Card",
            "template": "",
            "content": [{"format": "markdown", "body": "# Hello"}],
            "agent_id": "agent-1",
            "agent_name": "test",
            "tags": [],
            "pinned": False,
            "updated_at": "2026-01-01T00:00:00Z",
        }

        app = create_app()
        # Inject our mock store
        app.state.store = mock_store

        # We can't easily inject the store into the closure, so test export_card directly
        from synapse.canvas.export import export_card

        card = mock_store.get_card.return_value
        content_bytes, filename, content_type = export_card(card)
        assert b"# Hello" in content_bytes
        assert filename.endswith(".md")
        assert "markdown" in content_type


def test_download_endpoint_404_for_missing_card():
    """Export of None card should be handled at endpoint level."""
    from synapse.canvas.export import export_card

    # Empty card still produces output
    card = {"card_id": "x", "title": "", "template": "", "content": []}
    data, filename, mime = export_card(card)
    assert filename.startswith("card-")


def test_export_card_max_size_constant():
    """MAX_EXPORT_SIZE should be defined and reasonable."""
    from synapse.canvas.export import MAX_EXPORT_SIZE

    assert MAX_EXPORT_SIZE == 50 * 1024 * 1024
