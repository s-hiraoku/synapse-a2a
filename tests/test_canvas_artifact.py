"""Tests for Canvas artifact support (HTML with interactive content)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from synapse.canvas.protocol import CanvasMessage, ContentBlock, validate_message


def test_html_with_cdn_script_validates() -> None:
    """HTML content with CDN script tags should pass validate_message."""
    html_body = (
        "<!doctype html><html><head>"
        '<script src="https://cdn.jsdelivr.net/npm/react@18/umd/react.production.min.js"></script>'
        '</head><body><div id="root"></div>'
        "<script>console.log('hello');</script>"
        "</body></html>"
    )
    msg = CanvasMessage(
        type="render",
        agent_id="test-agent",
        agent_name="TestAgent",
        title="CDN Test",
        content=[ContentBlock(format="html", body=html_body)],
    )
    errors = validate_message(msg)
    assert errors == [], f"Unexpected validation errors: {errors}"


def test_html_with_x_title_roundtrip() -> None:
    """ContentBlock with x_title should serialize and deserialize correctly."""
    block = ContentBlock(format="html", body="<p>Hello</p>", x_title="My Widget")
    serialized = block.to_dict()
    assert serialized["x_title"] == "My Widget"
    assert serialized["format"] == "html"
    assert serialized["body"] == "<p>Hello</p>"

    # Roundtrip via CanvasMessage
    msg = CanvasMessage(
        type="render",
        agent_id="test-agent",
        agent_name="TestAgent",
        title="X-Title Test",
        content=[block],
    )
    data = msg.to_dict()
    restored = CanvasMessage.from_dict(data)
    restored_block = restored.content[0]
    assert restored_block.x_title == "My Widget"
    assert restored_block.format == "html"
    assert restored_block.body == "<p>Hello</p>"


def test_artifact_tag_roundtrip() -> None:
    """CanvasMessage with tags=['artifact'] should roundtrip correctly."""
    msg = CanvasMessage(
        type="render",
        agent_id="test-agent",
        agent_name="TestAgent",
        title="Tagged Artifact",
        tags=["artifact"],
        content=[ContentBlock(format="html", body="<p>Art</p>")],
    )
    data = msg.to_dict()
    assert "artifact" in data["tags"]

    restored = CanvasMessage.from_dict(data)
    assert "artifact" in restored.tags
    assert restored.title == "Tagged Artifact"


def test_artifact_theme_sync_and_resize() -> None:
    """Frontend: formatCanvasHTMLDocument injects theme and resize scripts."""
    script = Path("tests/canvas_frontend_artifact_test.js")
    if shutil.which("node") is None:
        pytest.skip("node is required for tests/canvas_frontend_artifact_test.js")
    result = subprocess.run(
        ["node", str(script)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr or result.stdout
