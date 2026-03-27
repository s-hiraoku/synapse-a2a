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

        large_body = "x" * 2_100_000  # > 2MB
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
        }
        assert new_formats.issubset(set(FORMAT_REGISTRY.keys()))

    def test_phase6_formats_registered(self):
        """Phase 6 formats (progress, terminal, dependency-graph, cost) should be in the registry."""
        from synapse.canvas.protocol import FORMAT_REGISTRY

        phase6 = {"progress", "terminal", "dependency-graph", "cost"}
        assert phase6.issubset(set(FORMAT_REGISTRY.keys()))

    def test_progress_format_spec(self):
        """Progress format should accept object body."""
        from synapse.canvas.protocol import FORMAT_REGISTRY

        spec = FORMAT_REGISTRY["progress"]
        assert spec.body_type == "object"

    def test_terminal_format_spec(self):
        """Terminal format should accept string body."""
        from synapse.canvas.protocol import FORMAT_REGISTRY

        spec = FORMAT_REGISTRY["terminal"]
        assert spec.body_type == "string"

    def test_dependency_graph_format_spec(self):
        """Dependency-graph format should accept object body."""
        from synapse.canvas.protocol import FORMAT_REGISTRY

        spec = FORMAT_REGISTRY["dependency-graph"]
        assert spec.body_type == "object"

    def test_cost_format_spec(self):
        """Cost format should accept object body."""
        from synapse.canvas.protocol import FORMAT_REGISTRY

        spec = FORMAT_REGISTRY["cost"]
        assert spec.body_type == "object"

    def test_format_spec_has_body_type(self):
        """Each format spec should declare a body_type."""
        from synapse.canvas.protocol import FORMAT_REGISTRY

        for name, spec in FORMAT_REGISTRY.items():
            assert hasattr(spec, "body_type"), f"{name} missing body_type"

    def test_html_format_is_sandboxed(self):
        """HTML format should be marked as sandboxed."""
        from synapse.canvas.protocol import FORMAT_REGISTRY

        assert FORMAT_REGISTRY["html"].sandboxed is True

    def test_link_preview_format_registered(self):
        """link-preview format should be in the registry with object body_type."""
        from synapse.canvas.protocol import FORMAT_REGISTRY

        assert "link-preview" in FORMAT_REGISTRY
        spec = FORMAT_REGISTRY["link-preview"]
        assert spec.body_type == "object"


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


# ============================================================
# TestTemplateField — Template field on CanvasMessage
# ============================================================


class TestTemplateField:
    """Tests for the template and template_data fields on CanvasMessage."""

    def test_template_field_default_empty(self):
        """Default template should be empty string."""
        from synapse.canvas.protocol import CanvasMessage, ContentBlock

        msg = CanvasMessage(
            type="render",
            content=ContentBlock(format="markdown", body="hello"),
            agent_id="synapse-claude-8103",
        )
        assert msg.template == ""
        assert msg.template_data == {}

    def test_template_field_serialization(self):
        """to_dict/from_dict should round-trip template and template_data."""
        from synapse.canvas.protocol import CanvasMessage, ContentBlock

        msg = CanvasMessage(
            type="render",
            content=[
                ContentBlock(format="markdown", body="## Overview"),
                ContentBlock(format="table", body={"headers": ["a"], "rows": [["1"]]}),
            ],
            agent_id="synapse-claude-8103",
            template="briefing",
            template_data={
                "summary": "Test summary",
                "sections": [{"title": "Results", "blocks": [0, 1]}],
            },
        )
        d = msg.to_dict()
        assert d["template"] == "briefing"
        assert d["template_data"]["summary"] == "Test summary"

        restored = CanvasMessage.from_dict(d)
        assert restored.template == "briefing"
        assert restored.template_data["sections"][0]["title"] == "Results"

    def test_invalid_template_name(self):
        """Unknown template name should fail validation."""
        from synapse.canvas.protocol import (
            CanvasMessage,
            ContentBlock,
            validate_message,
        )

        msg = CanvasMessage(
            type="render",
            content=[ContentBlock(format="markdown", body="hello")],
            agent_id="synapse-claude-8103",
            template="unknown_template",
            template_data={"sections": [{"title": "A"}]},
        )
        errors = validate_message(msg)
        assert len(errors) > 0
        assert any("template" in e.lower() for e in errors)

    def test_template_without_data(self):
        """template set but template_data empty should fail validation."""
        from synapse.canvas.protocol import (
            CanvasMessage,
            ContentBlock,
            validate_message,
        )

        msg = CanvasMessage(
            type="render",
            content=[ContentBlock(format="markdown", body="hello")],
            agent_id="synapse-claude-8103",
            template="briefing",
            template_data={},
        )
        errors = validate_message(msg)
        assert len(errors) > 0


# ============================================================
# TestBriefingValidation — Briefing template validation
# ============================================================


class TestBriefingValidation:
    """Tests for briefing template validation rules."""

    def _make_briefing(self, **overrides):
        from synapse.canvas.protocol import CanvasMessage, ContentBlock

        defaults = {
            "type": "render",
            "content": [
                ContentBlock(format="markdown", body="## Overview"),
                ContentBlock(format="table", body={"headers": ["a"], "rows": [["1"]]}),
            ],
            "agent_id": "synapse-claude-8103",
            "template": "briefing",
            "template_data": {
                "sections": [{"title": "Results", "blocks": [0, 1]}],
            },
        }
        defaults.update(overrides)
        return CanvasMessage(**defaults)

    def test_briefing_valid(self):
        """Valid briefing should pass validation."""
        from synapse.canvas.protocol import validate_message

        msg = self._make_briefing()
        errors = validate_message(msg)
        assert errors == []

    def test_briefing_missing_sections(self):
        """Briefing without sections key should fail."""
        from synapse.canvas.protocol import validate_message

        msg = self._make_briefing(template_data={"summary": "no sections"})
        errors = validate_message(msg)
        assert len(errors) > 0
        assert any("sections" in e.lower() for e in errors)

    def test_briefing_sections_not_list(self):
        """sections must be a list."""
        from synapse.canvas.protocol import validate_message

        msg = self._make_briefing(template_data={"sections": "not a list"})
        errors = validate_message(msg)
        assert len(errors) > 0

    def test_briefing_empty_sections(self):
        """Empty sections list should fail."""
        from synapse.canvas.protocol import validate_message

        msg = self._make_briefing(template_data={"sections": []})
        errors = validate_message(msg)
        assert len(errors) > 0

    def test_briefing_section_missing_title(self):
        """Section without title should fail."""
        from synapse.canvas.protocol import validate_message

        msg = self._make_briefing(template_data={"sections": [{"blocks": [0]}]})
        errors = validate_message(msg)
        assert len(errors) > 0
        assert any("title" in e.lower() for e in errors)

    def test_briefing_blocks_out_of_range(self):
        """Block index out of content range should fail."""
        from synapse.canvas.protocol import validate_message

        msg = self._make_briefing(
            template_data={"sections": [{"title": "Bad", "blocks": [0, 5]}]}
        )
        errors = validate_message(msg)
        assert len(errors) > 0
        assert any("range" in e.lower() or "index" in e.lower() for e in errors)

    def test_briefing_content_must_be_list(self):
        """Briefing requires composite content (list), not single block."""
        from synapse.canvas.protocol import ContentBlock, validate_message

        msg = self._make_briefing(
            content=ContentBlock(format="markdown", body="single"),
            template_data={"sections": [{"title": "A", "blocks": [0]}]},
        )
        errors = validate_message(msg)
        assert len(errors) > 0
        assert any("composite" in e.lower() or "list" in e.lower() for e in errors)

    def test_briefing_too_many_sections(self):
        """Exceeding MAX_SECTIONS should fail."""
        from synapse.canvas.protocol import MAX_SECTIONS, validate_message

        sections = [{"title": f"Section {i}"} for i in range(MAX_SECTIONS + 1)]
        msg = self._make_briefing(template_data={"sections": sections})
        errors = validate_message(msg)
        assert len(errors) > 0
        assert any("section" in e.lower() for e in errors)

    def test_briefing_with_summary(self):
        """Briefing with summary field should pass."""
        from synapse.canvas.protocol import validate_message

        msg = self._make_briefing(
            template_data={
                "summary": "Executive summary here",
                "sections": [{"title": "Details", "blocks": [0]}],
            }
        )
        errors = validate_message(msg)
        assert errors == []

    def test_briefing_section_without_blocks(self):
        """Section without blocks (title-only divider) should pass."""
        from synapse.canvas.protocol import validate_message

        msg = self._make_briefing(
            template_data={
                "sections": [
                    {"title": "Divider Section"},
                    {"title": "Content", "blocks": [0]},
                ],
            }
        )
        errors = validate_message(msg)
        assert errors == []

    def test_briefing_negative_block_index(self):
        """Negative block index should fail validation."""
        from synapse.canvas.protocol import validate_message

        msg = self._make_briefing(
            template_data={"sections": [{"title": "Bad", "blocks": [-1]}]}
        )
        errors = validate_message(msg)
        assert len(errors) > 0
        assert any("range" in e.lower() or "index" in e.lower() for e in errors)

    def test_briefing_non_integer_block_index(self):
        """String block index should fail validation."""
        from synapse.canvas.protocol import validate_message

        msg = self._make_briefing(
            template_data={"sections": [{"title": "Bad", "blocks": ["zero"]}]}
        )
        errors = validate_message(msg)
        assert len(errors) > 0

    def test_briefing_float_block_index(self):
        """Float block index should fail validation."""
        from synapse.canvas.protocol import validate_message

        msg = self._make_briefing(
            template_data={"sections": [{"title": "Bad", "blocks": [0.5]}]}
        )
        errors = validate_message(msg)
        assert len(errors) > 0

    def test_briefing_bool_block_index(self):
        """Bool values should be rejected as block indices even though bool is int subclass."""
        from synapse.canvas.protocol import validate_message

        msg = self._make_briefing(
            template_data={"sections": [{"title": "Bad", "blocks": [True]}]}
        )
        errors = validate_message(msg)
        assert len(errors) > 0

    def test_briefing_duplicate_block_indices(self):
        """Same block index repeated in a section is allowed."""
        from synapse.canvas.protocol import validate_message

        msg = self._make_briefing(
            template_data={"sections": [{"title": "Dup", "blocks": [0, 0]}]}
        )
        errors = validate_message(msg)
        assert errors == []

    def test_briefing_block_in_multiple_sections(self):
        """Same block referenced from multiple sections is allowed."""
        from synapse.canvas.protocol import validate_message

        msg = self._make_briefing(
            template_data={
                "sections": [
                    {"title": "A", "blocks": [0]},
                    {"title": "B", "blocks": [0, 1]},
                ],
            }
        )
        errors = validate_message(msg)
        assert errors == []

    def test_briefing_from_dict_round_trip(self):
        """CanvasMessage round-trip should preserve all briefing fields."""
        from synapse.canvas.protocol import CanvasMessage

        original = self._make_briefing(
            title="Round Trip",
            template_data={
                "summary": "Executive summary",
                "sections": [
                    {"title": "Overview", "blocks": [0], "summary": "Section summary"},
                    {"title": "Details", "blocks": [1]},
                ],
            },
        )
        d = original.to_dict()
        restored = CanvasMessage.from_dict(d)

        assert restored.template == "briefing"
        assert restored.title == "Round Trip"
        assert restored.template_data["summary"] == "Executive summary"
        sections = restored.template_data["sections"]
        assert len(sections) == 2
        assert sections[0]["title"] == "Overview"
        assert sections[0]["blocks"] == [0]
        assert sections[0]["summary"] == "Section summary"
        assert sections[1]["title"] == "Details"
        assert sections[1]["blocks"] == [1]


# ============================================================
# TestComparisonValidation — Comparison template validation
# ============================================================


class TestComparisonValidation:
    """Tests for comparison template validation rules."""

    def _make_comparison(self, **overrides):
        from synapse.canvas.protocol import CanvasMessage, ContentBlock

        defaults = {
            "type": "render",
            "content": [
                ContentBlock(format="markdown", body="## Before"),
                ContentBlock(format="markdown", body="## After"),
            ],
            "agent_id": "synapse-claude-8103",
            "template": "comparison",
            "template_data": {
                "sides": [
                    {"label": "Before", "blocks": [0]},
                    {"label": "After", "blocks": [1]},
                ],
            },
        }
        defaults.update(overrides)
        return CanvasMessage(**defaults)

    def test_comparison_valid(self):
        from synapse.canvas.protocol import validate_message

        errors = validate_message(self._make_comparison())
        assert errors == []

    def test_comparison_missing_sides(self):
        from synapse.canvas.protocol import validate_message

        msg = self._make_comparison(template_data={})
        errors = validate_message(msg)
        assert any("sides" in e.lower() for e in errors)

    def test_comparison_too_few_sides(self):
        from synapse.canvas.protocol import validate_message

        msg = self._make_comparison(
            template_data={"sides": [{"label": "Only", "blocks": [0]}]}
        )
        errors = validate_message(msg)
        assert any("2" in e for e in errors)

    def test_comparison_too_many_sides(self):
        from synapse.canvas.protocol import MAX_SIDES, validate_message

        sides = [{"label": f"S{i}", "blocks": [0]} for i in range(MAX_SIDES + 1)]
        msg = self._make_comparison(template_data={"sides": sides})
        errors = validate_message(msg)
        assert any("side" in e.lower() for e in errors)

    def test_comparison_side_missing_label(self):
        from synapse.canvas.protocol import validate_message

        msg = self._make_comparison(
            template_data={"sides": [{"blocks": [0]}, {"label": "B", "blocks": [1]}]}
        )
        errors = validate_message(msg)
        assert any("label" in e.lower() for e in errors)

    def test_comparison_side_missing_blocks(self):
        from synapse.canvas.protocol import validate_message

        msg = self._make_comparison(
            template_data={"sides": [{"label": "A"}, {"label": "B", "blocks": [1]}]}
        )
        errors = validate_message(msg)
        assert any("blocks" in e.lower() for e in errors)

    def test_comparison_blocks_out_of_range(self):
        from synapse.canvas.protocol import validate_message

        msg = self._make_comparison(
            template_data={
                "sides": [
                    {"label": "A", "blocks": [0]},
                    {"label": "B", "blocks": [99]},
                ]
            }
        )
        errors = validate_message(msg)
        assert any("range" in e.lower() or "index" in e.lower() for e in errors)

    def test_comparison_invalid_layout(self):
        from synapse.canvas.protocol import validate_message

        msg = self._make_comparison(
            template_data={
                "sides": [
                    {"label": "A", "blocks": [0]},
                    {"label": "B", "blocks": [1]},
                ],
                "layout": "diagonal",
            }
        )
        errors = validate_message(msg)
        assert any("layout" in e.lower() for e in errors)

    def test_comparison_valid_stacked_layout(self):
        from synapse.canvas.protocol import validate_message

        msg = self._make_comparison(
            template_data={
                "sides": [
                    {"label": "A", "blocks": [0]},
                    {"label": "B", "blocks": [1]},
                ],
                "layout": "stacked",
            }
        )
        errors = validate_message(msg)
        assert errors == []

    def test_comparison_content_must_be_list(self):
        from synapse.canvas.protocol import ContentBlock, validate_message

        msg = self._make_comparison(
            content=ContentBlock(format="markdown", body="single"),
        )
        errors = validate_message(msg)
        assert any("composite" in e.lower() or "list" in e.lower() for e in errors)


# ============================================================
# TestDashboardValidation — Dashboard template validation
# ============================================================


class TestDashboardValidation:
    """Tests for dashboard template validation rules."""

    def _make_dashboard(self, **overrides):
        from synapse.canvas.protocol import CanvasMessage, ContentBlock

        defaults = {
            "type": "render",
            "content": [
                ContentBlock(format="metric", body={"value": 42, "label": "Users"}),
                ContentBlock(format="metric", body={"value": 99, "label": "Uptime"}),
            ],
            "agent_id": "synapse-claude-8103",
            "template": "dashboard",
            "template_data": {
                "cols": 2,
                "widgets": [
                    {"title": "Users", "blocks": [0]},
                    {"title": "Uptime", "blocks": [1]},
                ],
            },
        }
        defaults.update(overrides)
        return CanvasMessage(**defaults)

    def test_dashboard_valid(self):
        from synapse.canvas.protocol import validate_message

        errors = validate_message(self._make_dashboard())
        assert errors == []

    def test_dashboard_missing_widgets(self):
        from synapse.canvas.protocol import validate_message

        msg = self._make_dashboard(template_data={"cols": 2})
        errors = validate_message(msg)
        assert any("widgets" in e.lower() for e in errors)

    def test_dashboard_empty_widgets(self):
        from synapse.canvas.protocol import validate_message

        msg = self._make_dashboard(template_data={"widgets": []})
        errors = validate_message(msg)
        assert any("empty" in e.lower() for e in errors)

    def test_dashboard_too_many_widgets(self):
        from synapse.canvas.protocol import MAX_WIDGETS, validate_message

        widgets = [{"title": f"W{i}", "blocks": [0]} for i in range(MAX_WIDGETS + 1)]
        msg = self._make_dashboard(template_data={"widgets": widgets})
        errors = validate_message(msg)
        assert any("widget" in e.lower() for e in errors)

    def test_dashboard_invalid_cols(self):
        from synapse.canvas.protocol import validate_message

        msg = self._make_dashboard(
            template_data={
                "cols": 5,
                "widgets": [{"title": "A", "blocks": [0]}],
            }
        )
        errors = validate_message(msg)
        assert any("cols" in e.lower() for e in errors)

    def test_dashboard_widget_missing_title(self):
        from synapse.canvas.protocol import validate_message

        msg = self._make_dashboard(template_data={"widgets": [{"blocks": [0]}]})
        errors = validate_message(msg)
        assert any("title" in e.lower() for e in errors)

    def test_dashboard_invalid_widget_size(self):
        from synapse.canvas.protocol import validate_message

        msg = self._make_dashboard(
            template_data={
                "widgets": [{"title": "Big", "blocks": [0], "size": "3x3"}],
            }
        )
        errors = validate_message(msg)
        assert any("size" in e.lower() for e in errors)

    def test_dashboard_valid_sizes(self):
        from synapse.canvas.protocol import validate_message

        for size in ("1x1", "2x1", "1x2", "2x2"):
            msg = self._make_dashboard(
                template_data={
                    "widgets": [{"title": "W", "blocks": [0], "size": size}],
                }
            )
            errors = validate_message(msg)
            assert errors == [], f"Size {size} should be valid"

    def test_dashboard_blocks_out_of_range(self):
        from synapse.canvas.protocol import validate_message

        msg = self._make_dashboard(
            template_data={"widgets": [{"title": "A", "blocks": [99]}]}
        )
        errors = validate_message(msg)
        assert any("range" in e.lower() or "index" in e.lower() for e in errors)


# ============================================================
# TestStepsValidation — Steps template validation
# ============================================================


class TestStepsValidation:
    """Tests for steps template validation rules."""

    def _make_steps(self, **overrides):
        from synapse.canvas.protocol import CanvasMessage, ContentBlock

        defaults = {
            "type": "render",
            "content": [
                ContentBlock(format="markdown", body="## Step 1 details"),
                ContentBlock(format="markdown", body="## Step 2 details"),
            ],
            "agent_id": "synapse-claude-8103",
            "template": "steps",
            "template_data": {
                "steps": [
                    {"title": "Setup", "blocks": [0], "done": True},
                    {"title": "Deploy", "blocks": [1], "done": False},
                ],
            },
        }
        defaults.update(overrides)
        return CanvasMessage(**defaults)

    def test_steps_valid(self):
        from synapse.canvas.protocol import validate_message

        errors = validate_message(self._make_steps())
        assert errors == []

    def test_steps_missing_steps(self):
        from synapse.canvas.protocol import validate_message

        msg = self._make_steps(template_data={"summary": "no steps"})
        errors = validate_message(msg)
        assert any("steps" in e.lower() for e in errors)

    def test_steps_empty(self):
        from synapse.canvas.protocol import validate_message

        msg = self._make_steps(template_data={"steps": []})
        errors = validate_message(msg)
        assert any("empty" in e.lower() for e in errors)

    def test_steps_too_many(self):
        from synapse.canvas.protocol import MAX_STEPS, validate_message

        steps = [{"title": f"Step {i}"} for i in range(MAX_STEPS + 1)]
        msg = self._make_steps(template_data={"steps": steps})
        errors = validate_message(msg)
        assert any("step" in e.lower() for e in errors)

    def test_steps_missing_title(self):
        from synapse.canvas.protocol import validate_message

        msg = self._make_steps(template_data={"steps": [{"blocks": [0]}]})
        errors = validate_message(msg)
        assert any("title" in e.lower() for e in errors)

    def test_steps_blocks_out_of_range(self):
        from synapse.canvas.protocol import validate_message

        msg = self._make_steps(
            template_data={"steps": [{"title": "Bad", "blocks": [99]}]}
        )
        errors = validate_message(msg)
        assert any("range" in e.lower() or "index" in e.lower() for e in errors)

    def test_steps_without_blocks(self):
        """Step without blocks (description only) should pass."""
        from synapse.canvas.protocol import validate_message

        msg = self._make_steps(
            template_data={
                "steps": [
                    {"title": "Plan", "description": "Think about it"},
                    {"title": "Execute", "blocks": [0]},
                ],
            }
        )
        errors = validate_message(msg)
        assert errors == []

    def test_steps_with_summary(self):
        from synapse.canvas.protocol import validate_message

        msg = self._make_steps(
            template_data={
                "summary": "Deployment workflow",
                "steps": [{"title": "Deploy", "blocks": [0]}],
            }
        )
        errors = validate_message(msg)
        assert errors == []


# ============================================================
# TestSlidesValidation — Slides template validation
# ============================================================


class TestSlidesValidation:
    """Tests for slides template validation rules."""

    def _make_slides(self, **overrides):
        from synapse.canvas.protocol import CanvasMessage, ContentBlock

        defaults = {
            "type": "render",
            "content": [
                ContentBlock(format="markdown", body="# Slide 1"),
                ContentBlock(format="mermaid", body="graph TD; A-->B"),
                ContentBlock(format="markdown", body="# Slide 3"),
            ],
            "agent_id": "synapse-claude-8103",
            "template": "slides",
            "template_data": {
                "slides": [
                    {"title": "Intro", "blocks": [0]},
                    {"blocks": [1]},
                    {"title": "Summary", "blocks": [2], "notes": "Wrap up"},
                ],
            },
        }
        defaults.update(overrides)
        return CanvasMessage(**defaults)

    def test_slides_valid(self):
        from synapse.canvas.protocol import validate_message

        errors = validate_message(self._make_slides())
        assert errors == []

    def test_slides_missing_slides(self):
        from synapse.canvas.protocol import validate_message

        msg = self._make_slides(template_data={})
        errors = validate_message(msg)
        assert any("slides" in e.lower() for e in errors)

    def test_slides_empty(self):
        from synapse.canvas.protocol import validate_message

        msg = self._make_slides(template_data={"slides": []})
        errors = validate_message(msg)
        assert any("empty" in e.lower() for e in errors)

    def test_slides_too_many(self):
        from synapse.canvas.protocol import MAX_SLIDES, validate_message

        slides = [{"blocks": [0]} for _ in range(MAX_SLIDES + 1)]
        msg = self._make_slides(template_data={"slides": slides})
        errors = validate_message(msg)
        assert any("slide" in e.lower() for e in errors)

    def test_slides_missing_blocks(self):
        from synapse.canvas.protocol import validate_message

        msg = self._make_slides(template_data={"slides": [{"title": "No blocks"}]})
        errors = validate_message(msg)
        assert any("blocks" in e.lower() for e in errors)

    def test_slides_blocks_out_of_range(self):
        from synapse.canvas.protocol import validate_message

        msg = self._make_slides(template_data={"slides": [{"blocks": [99]}]})
        errors = validate_message(msg)
        assert any("range" in e.lower() or "index" in e.lower() for e in errors)

    def test_slides_without_title(self):
        """Slide without title should pass (title is optional)."""
        from synapse.canvas.protocol import validate_message

        msg = self._make_slides(
            template_data={"slides": [{"blocks": [0]}, {"blocks": [1]}]}
        )
        errors = validate_message(msg)
        assert errors == []

    def test_slides_with_notes(self):
        from synapse.canvas.protocol import validate_message

        msg = self._make_slides(
            template_data={
                "slides": [
                    {"blocks": [0], "notes": "Speaker notes here"},
                ],
            }
        )
        errors = validate_message(msg)
        assert errors == []


# ============================================================
# TestPlanValidation — Plan template validation
# ============================================================


class TestPlanValidation:
    """Tests for plan template validation rules."""

    def _make_plan(self, **overrides):
        from synapse.canvas.protocol import CanvasMessage, ContentBlock

        defaults = {
            "type": "render",
            "content": ContentBlock(format="plan", body={}),
            "agent_id": "synapse-claude-8100",
            "template": "plan",
            "template_data": {
                "plan_id": "plan-oauth2",
                "status": "proposed",
                "mermaid": "graph TD\n  A[Design] --> B[Implement]",
                "steps": [
                    {
                        "id": "step-1",
                        "subject": "OAuth2 Design",
                        "agent": "claude",
                        "status": "pending",
                        "blocked_by": [],
                    },
                    {
                        "id": "step-2",
                        "subject": "OAuth2 Implement",
                        "agent": "codex",
                        "status": "pending",
                        "blocked_by": ["step-1"],
                    },
                ],
            },
        }
        defaults.update(overrides)
        return CanvasMessage(**defaults)

    def test_plan_valid(self):
        from synapse.canvas.protocol import validate_message

        errors = validate_message(self._make_plan())
        assert errors == []

    def test_plan_missing_plan_id(self):
        from synapse.canvas.protocol import validate_message

        msg = self._make_plan(
            template_data={
                "steps": [{"id": "s1", "subject": "Do stuff"}],
            }
        )
        errors = validate_message(msg)
        assert any("plan_id" in e for e in errors)

    def test_plan_invalid_status(self):
        from synapse.canvas.protocol import validate_message

        msg = self._make_plan(
            template_data={
                "plan_id": "p1",
                "status": "invalid_status",
                "steps": [{"id": "s1", "subject": "Do stuff"}],
            }
        )
        errors = validate_message(msg)
        assert any("status" in e.lower() for e in errors)

    def test_plan_missing_steps(self):
        from synapse.canvas.protocol import validate_message

        msg = self._make_plan(template_data={"plan_id": "p1"})
        errors = validate_message(msg)
        assert any("steps" in e.lower() for e in errors)

    def test_plan_empty_steps(self):
        from synapse.canvas.protocol import validate_message

        msg = self._make_plan(template_data={"plan_id": "p1", "steps": []})
        errors = validate_message(msg)
        assert any("empty" in e.lower() for e in errors)

    def test_plan_too_many_steps(self):
        from synapse.canvas.protocol import validate_message

        steps = [{"id": f"s{i}", "subject": f"Step {i}"} for i in range(31)]
        msg = self._make_plan(template_data={"plan_id": "p1", "steps": steps})
        errors = validate_message(msg)
        assert any("too many" in e.lower() for e in errors)

    def test_plan_step_missing_id(self):
        from synapse.canvas.protocol import validate_message

        msg = self._make_plan(
            template_data={
                "plan_id": "p1",
                "steps": [{"subject": "No ID step"}],
            }
        )
        errors = validate_message(msg)
        assert any("id" in e.lower() for e in errors)

    def test_plan_step_missing_subject(self):
        from synapse.canvas.protocol import validate_message

        msg = self._make_plan(
            template_data={
                "plan_id": "p1",
                "steps": [{"id": "s1"}],
            }
        )
        errors = validate_message(msg)
        assert any("subject" in e.lower() for e in errors)

    def test_plan_step_duplicate_id(self):
        from synapse.canvas.protocol import validate_message

        msg = self._make_plan(
            template_data={
                "plan_id": "p1",
                "steps": [
                    {"id": "s1", "subject": "First"},
                    {"id": "s1", "subject": "Duplicate"},
                ],
            }
        )
        errors = validate_message(msg)
        assert any("duplicate" in e.lower() for e in errors)

    def test_plan_step_invalid_status(self):
        from synapse.canvas.protocol import validate_message

        msg = self._make_plan(
            template_data={
                "plan_id": "p1",
                "steps": [{"id": "s1", "subject": "Bad status", "status": "bogus"}],
            }
        )
        errors = validate_message(msg)
        assert any("status" in e.lower() for e in errors)

    def test_plan_step_blocked_by_not_list(self):
        from synapse.canvas.protocol import validate_message

        msg = self._make_plan(
            template_data={
                "plan_id": "p1",
                "steps": [{"id": "s1", "subject": "Step", "blocked_by": "not-a-list"}],
            }
        )
        errors = validate_message(msg)
        assert any("blocked_by" in e for e in errors)

    def test_plan_without_mermaid(self):
        """Plan without mermaid field should still be valid."""
        from synapse.canvas.protocol import validate_message

        msg = self._make_plan(
            template_data={
                "plan_id": "p1",
                "steps": [{"id": "s1", "subject": "Step 1"}],
            }
        )
        errors = validate_message(msg)
        assert errors == []

    def test_plan_all_step_statuses(self):
        """All valid step statuses should pass validation."""
        from synapse.canvas.protocol import validate_message

        statuses = ["pending", "blocked", "in_progress", "completed", "failed"]
        steps = [
            {"id": f"s{i}", "subject": f"Step {i}", "status": s}
            for i, s in enumerate(statuses)
        ]
        msg = self._make_plan(template_data={"plan_id": "p1", "steps": steps})
        errors = validate_message(msg)
        assert errors == []

    def test_plan_all_plan_statuses(self):
        """All valid plan statuses should pass validation."""
        from synapse.canvas.protocol import validate_message

        for status in ["proposed", "active", "completed", "cancelled"]:
            msg = self._make_plan(
                template_data={
                    "plan_id": "p1",
                    "status": status,
                    "steps": [{"id": "s1", "subject": "Step"}],
                }
            )
            errors = validate_message(msg)
            assert errors == [], f"Status '{status}' should be valid"


# ============================================================
# TestPhase6Formats — Progress, Terminal, DependencyGraph, Cost
# ============================================================


class TestPhase6Formats:
    """Tests for phase 6 card format validation."""

    def test_progress_valid(self):
        """Valid progress card should pass validation."""
        from synapse.canvas.protocol import (
            CanvasMessage,
            ContentBlock,
            validate_message,
        )

        msg = CanvasMessage(
            type="render",
            content=ContentBlock(
                format="progress",
                body={
                    "current": 3,
                    "total": 7,
                    "label": "Running tests",
                    "steps": [
                        "Parse",
                        "Build",
                        "Lint",
                        "Test",
                        "Deploy",
                        "Verify",
                        "Done",
                    ],
                    "status": "in_progress",
                },
            ),
            agent_id="synapse-claude-8103",
        )
        errors = validate_message(msg)
        assert errors == []

    def test_progress_minimal(self):
        """Progress card with only current/total should pass."""
        from synapse.canvas.protocol import (
            CanvasMessage,
            ContentBlock,
            validate_message,
        )

        msg = CanvasMessage(
            type="render",
            content=ContentBlock(
                format="progress",
                body={"current": 1, "total": 5},
            ),
            agent_id="synapse-claude-8103",
        )
        errors = validate_message(msg)
        assert errors == []

    def test_terminal_valid(self):
        """Valid terminal card should pass validation."""
        from synapse.canvas.protocol import (
            CanvasMessage,
            ContentBlock,
            validate_message,
        )

        msg = CanvasMessage(
            type="render",
            content=ContentBlock(
                format="terminal",
                body="$ pytest tests/\n\x1b[32mPASSED\x1b[0m 42 tests in 3.2s",
            ),
            agent_id="synapse-claude-8103",
        )
        errors = validate_message(msg)
        assert errors == []

    def test_dependency_graph_valid(self):
        """Valid dependency-graph card should pass validation."""
        from synapse.canvas.protocol import (
            CanvasMessage,
            ContentBlock,
            validate_message,
        )

        msg = CanvasMessage(
            type="render",
            content=ContentBlock(
                format="dependency-graph",
                body={
                    "nodes": [
                        {"id": "synapse.cli", "group": "core"},
                        {"id": "synapse.server", "group": "core"},
                    ],
                    "edges": [
                        {"from": "synapse.cli", "to": "synapse.server"},
                    ],
                },
            ),
            agent_id="synapse-claude-8103",
        )
        errors = validate_message(msg)
        assert errors == []

    def test_cost_valid(self):
        """Valid cost card should pass validation."""
        from synapse.canvas.protocol import (
            CanvasMessage,
            ContentBlock,
            validate_message,
        )

        msg = CanvasMessage(
            type="render",
            content=ContentBlock(
                format="cost",
                body={
                    "agents": [
                        {
                            "name": "claude",
                            "input_tokens": 50000,
                            "output_tokens": 12000,
                            "cost": 0.45,
                        },
                        {
                            "name": "gemini",
                            "input_tokens": 30000,
                            "output_tokens": 8000,
                            "cost": 0.12,
                        },
                    ],
                    "total_cost": 0.57,
                    "currency": "USD",
                },
            ),
            agent_id="synapse-claude-8103",
        )
        errors = validate_message(msg)
        assert errors == []

    def test_cost_minimal(self):
        """Cost card with only agents and total should pass."""
        from synapse.canvas.protocol import (
            CanvasMessage,
            ContentBlock,
            validate_message,
        )

        msg = CanvasMessage(
            type="render",
            content=ContentBlock(
                format="cost",
                body={
                    "agents": [{"name": "claude", "cost": 0.45}],
                    "total_cost": 0.45,
                },
            ),
            agent_id="synapse-claude-8103",
        )
        errors = validate_message(msg)
        assert errors == []
