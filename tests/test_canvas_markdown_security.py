"""Security regression tests for canvas.js markdown rendering."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest


def _render_simple_markdown(text: str) -> str:
    if shutil.which("node") is None:
        pytest.skip("node is required for canvas markdown security tests")
    source = Path("synapse/canvas/static/canvas.js").read_text(encoding="utf-8")
    match = re.search(
        r"function escapeHtml\(text\) \{.*?\n  \}\n\n  function simpleMarkdown\(text\) \{.*?\n  \}",
        source,
        re.DOTALL,
    )
    assert match, "escapeHtml()/simpleMarkdown() block not found in canvas.js"

    script = f"""
{match.group(0)}
process.stdout.write(simpleMarkdown({json.dumps(text)}));
"""
    result = subprocess.run(
        ["node", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


class TestCanvasMarkdownSecurity:
    """Tests for sanitization behavior in simpleMarkdown()."""

    def test_simple_markdown_escapes_raw_html(self):
        """Raw HTML should not survive markdown rendering."""
        rendered = _render_simple_markdown('<img src=x onerror="alert(1)"> **safe**')

        assert "<img" not in rendered
        assert "&lt;img" in rendered
        assert "<strong>safe</strong>" in rendered

    def test_simple_markdown_rejects_javascript_links(self):
        """javascript: links should not render as clickable anchors."""
        rendered = _render_simple_markdown("[click](javascript:alert(1))")

        assert "<a " not in rendered
        assert "javascript:alert(1)" not in rendered
