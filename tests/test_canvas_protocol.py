"""Tests for Canvas Message Protocol — validation and format registry.

Test-first development: these tests define the expected behavior
for the CanvasMessage protocol before implementation.
"""

from __future__ import annotations

# ============================================================
# TestContentBlock — Content block validation
# ============================================================


class TestContentBlock:
    """Tests for ContentBlock dataclass."""

    def test_create_mermaid_block(self):
        """Should create a content block with mermaid format."""
        from synapse.canvas.protocol import ContentBlock

        block = ContentBlock(format="mermaid", body="graph TD; A-->B")
        assert block.format == "mermaid"
        assert block.body == "graph TD; A-->B"
        assert block.lang is None

    def test_create_code_block_with_lang(self):
        """Should create a code block with language hint."""
        from synapse.canvas.protocol import ContentBlock

        block = ContentBlock(format="code", body="def foo(): pass", lang="python")
        assert block.format == "code"
        assert block.lang == "python"

    def test_create_table_block_with_dict_body(self):
        """Should accept dict body for table format."""
        from synapse.canvas.protocol import ContentBlock

        body = {"headers": ["name", "status"], "rows": [["auth", "pass"]]}
        block = ContentBlock(format="table", body=body)
        assert block.body == body


# ============================================================
# TestCanvasMessage — Message validation
# ============================================================


class TestCanvasMessage:
    """Tests for CanvasMessage dataclass and validation."""

    def _make_message(self, **overrides):
        from synapse.canvas.protocol import CanvasMessage, ContentBlock

        defaults = {
            "type": "render",
            "content": ContentBlock(format="mermaid", body="graph TD; A-->B"),
            "agent_id": "synapse-claude-8103",
            "agent_name": "Gojo",
            "title": "Test Card",
        }
        defaults.update(overrides)
        return CanvasMessage(**defaults)

    def test_create_render_message(self):
        """Should create a valid render message."""
        msg = self._make_message()
        assert msg.type == "render"
        assert msg.agent_id == "synapse-claude-8103"
        assert msg.title == "Test Card"
        assert msg.card_id == ""
        assert msg.pinned is False
        assert msg.tags == []

    def test_create_with_card_id(self):
        """Should accept user-specified card_id for upserts."""
        msg = self._make_message(card_id="auth-flow")
        assert msg.card_id == "auth-flow"

    def test_create_with_tags(self):
        """Should accept tags list."""
        msg = self._make_message(tags=["design", "auth"])
        assert msg.tags == ["design", "auth"]

    def test_create_with_pinned(self):
        """Pinned cards should be exempt from TTL."""
        msg = self._make_message(pinned=True)
        assert msg.pinned is True

    def test_composite_content(self):
        """Should accept list of content blocks (composite card)."""
        from synapse.canvas.protocol import ContentBlock

        blocks = [
            ContentBlock(format="markdown", body="## Overview"),
            ContentBlock(format="mermaid", body="graph TD; A-->B"),
        ]
        msg = self._make_message(content=blocks)
        assert isinstance(msg.content, list)
        assert len(msg.content) == 2


# ============================================================
# TestValidation — Protocol validation rules
# ============================================================


class TestValidation:
    """Tests for CanvasMessage validation."""

    def test_validate_valid_message(self):
        """Valid message should pass validation."""
        from synapse.canvas.protocol import (
            CanvasMessage,
            ContentBlock,
            validate_message,
        )

        msg = CanvasMessage(
            type="render",
            content=ContentBlock(format="mermaid", body="graph TD; A-->B"),
            agent_id="synapse-claude-8103",
        )
        errors = validate_message(msg)
        assert errors == []

    def test_validate_invalid_type(self):
        """Invalid message type should fail validation."""
        from synapse.canvas.protocol import (
            CanvasMessage,
            ContentBlock,
            validate_message,
        )

        msg = CanvasMessage(
            type="invalid_type",
            content=ContentBlock(format="mermaid", body="graph TD; A-->B"),
            agent_id="synapse-claude-8103",
        )
        errors = validate_message(msg)
        assert len(errors) > 0
        assert any("type" in e for e in errors)

    def test_validate_invalid_format(self):
        """Unregistered format should fail validation."""
        from synapse.canvas.protocol import (
            CanvasMessage,
            ContentBlock,
            validate_message,
        )

        msg = CanvasMessage(
            type="render",
            content=ContentBlock(format="unknown_format", body="..."),
            agent_id="synapse-claude-8103",
        )
        errors = validate_message(msg)
        assert len(errors) > 0
        assert any("format" in e for e in errors)

    def test_validate_body_too_large(self):
        """Body exceeding max size should fail validation."""
        from synapse.canvas.protocol import (
            CanvasMessage,
            ContentBlock,
            validate_message,
        )

        large_body = "x" * 600_000  # > 500KB
        msg = CanvasMessage(
            type="render",
            content=ContentBlock(format="markdown", body=large_body),
            agent_id="synapse-claude-8103",
        )
        errors = validate_message(msg)
        assert len(errors) > 0
        assert any("size" in e.lower() or "large" in e.lower() for e in errors)

    def test_validate_too_many_blocks(self):
        """Composite card with too many blocks should fail."""
        from synapse.canvas.protocol import (
            MAX_BLOCKS_PER_CARD,
            CanvasMessage,
            ContentBlock,
            validate_message,
        )

        blocks = [
            ContentBlock(format="markdown", body=f"Block {i}")
            for i in range(MAX_BLOCKS_PER_CARD + 1)
        ]
        msg = CanvasMessage(
            type="render",
            content=blocks,
            agent_id="synapse-claude-8103",
        )
        errors = validate_message(msg)
        assert len(errors) > 0
        assert any("block" in e.lower() for e in errors)

    def test_validate_empty_block_list(self):
        """Composite card with no blocks should fail."""
        from synapse.canvas.protocol import CanvasMessage, validate_message

        msg = CanvasMessage(
            type="render",
            content=[],
            agent_id="synapse-claude-8103",
        )
        errors = validate_message(msg)
        assert len(errors) > 0
        assert any("content" in e.lower() or "block" in e.lower() for e in errors)

    def test_validate_missing_agent_id(self):
        """Empty agent_id should fail validation."""
        from synapse.canvas.protocol import (
            CanvasMessage,
            ContentBlock,
            validate_message,
        )

        msg = CanvasMessage(
            type="render",
            content=ContentBlock(format="mermaid", body="graph TD; A-->B"),
            agent_id="",
        )
        errors = validate_message(msg)
        assert len(errors) > 0
        assert any("agent" in e.lower() for e in errors)

    def test_validate_clear_type_no_content_needed(self):
        """Clear type should not require content."""
        from synapse.canvas.protocol import (
            CanvasMessage,
            ContentBlock,
            validate_message,
        )

        msg = CanvasMessage(
            type="clear",
            content=ContentBlock(format="mermaid", body=""),
            agent_id="synapse-claude-8103",
        )
        errors = validate_message(msg)
        assert errors == []


# ============================================================
# TestFormatRegistry — Format registration
# ============================================================


class TestFormatRegistry:
    """Tests for the format registry."""

    def test_mermaid_registered(self):
        """Mermaid format should be registered."""
        from synapse.canvas.protocol import FORMAT_REGISTRY

        assert "mermaid" in FORMAT_REGISTRY

    def test_all_standard_formats_registered(self):
        """All standard formats should be in the registry."""
        from synapse.canvas.protocol import FORMAT_REGISTRY

        expected = {
            "mermaid",
            "markdown",
            "html",
            "table",
            "json",
            "diff",
            "chart",
            "image",
            "code",
        }
        assert expected.issubset(set(FORMAT_REGISTRY.keys()))

    def test_new_formats_registered(self):
        """Phase 5 formats should be in the registry."""
        from synapse.canvas.protocol import FORMAT_REGISTRY

        new_formats = {
            "log",
            "status",
            "metric",
            "checklist",
            "timeline",
            "alert",
            "file-preview",
            "trace",
            "task-board",
        }
        assert new_formats.issubset(set(FORMAT_REGISTRY.keys()))

    def test_format_spec_has_body_type(self):
        """Each format spec should declare a body_type."""
        from synapse.canvas.protocol import FORMAT_REGISTRY

        for name, spec in FORMAT_REGISTRY.items():
            assert hasattr(spec, "body_type"), f"{name} missing body_type"

    def test_html_format_is_sandboxed(self):
        """HTML format should be marked as sandboxed."""
        from synapse.canvas.protocol import FORMAT_REGISTRY

        assert FORMAT_REGISTRY["html"].sandboxed is True


# ============================================================
# TestMessageSerialization — JSON serialization
# ============================================================


class TestMessageSerialization:
    """Tests for converting messages to/from JSON."""

    def test_to_dict(self):
        """Message should serialize to dict."""
        from synapse.canvas.protocol import CanvasMessage, ContentBlock

        msg = CanvasMessage(
            type="render",
            content=ContentBlock(format="mermaid", body="graph TD; A-->B"),
            agent_id="synapse-claude-8103",
            agent_name="Gojo",
            title="Flow",
            card_id="auth",
        )
        d = msg.to_dict()
        assert d["type"] == "render"
        assert d["content"]["format"] == "mermaid"
        assert d["card_id"] == "auth"
        assert d["agent_name"] == "Gojo"

    def test_from_dict(self):
        """Message should deserialize from dict."""
        from synapse.canvas.protocol import CanvasMessage

        data = {
            "type": "render",
            "content": {"format": "mermaid", "body": "graph TD; A-->B"},
            "agent_id": "synapse-claude-8103",
            "title": "Flow",
        }
        msg = CanvasMessage.from_dict(data)
        assert msg.type == "render"
        assert msg.content.format == "mermaid"
        assert msg.content.body == "graph TD; A-->B"
        assert msg.title == "Flow"

    def test_from_dict_composite(self):
        """Should deserialize composite content (list of blocks)."""
        from synapse.canvas.protocol import CanvasMessage

        data = {
            "type": "render",
            "content": [
                {"format": "markdown", "body": "## Title"},
                {"format": "mermaid", "body": "graph TD; A-->B"},
            ],
            "agent_id": "synapse-claude-8103",
        }
        msg = CanvasMessage.from_dict(data)
        assert isinstance(msg.content, list)
        assert len(msg.content) == 2
        assert msg.content[0].format == "markdown"

    def test_from_dict_with_tags(self):
        """Should preserve tags on deserialization."""
        from synapse.canvas.protocol import CanvasMessage

        data = {
            "type": "render",
            "content": {"format": "mermaid", "body": "graph TD; A-->B"},
            "agent_id": "synapse-claude-8103",
            "tags": ["design", "auth"],
        }
        msg = CanvasMessage.from_dict(data)
        assert msg.tags == ["design", "auth"]
