"""Canvas Message Protocol — dataclasses, validation, format registry.

All agent-to-Canvas communication uses this unified protocol.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ============================================================
# Constants
# ============================================================

VALID_MESSAGE_TYPES = {"render", "update", "clear", "notify"}
MAX_CONTENT_SIZE = 2_000_000  # 2MB per content block
MAX_BLOCKS_PER_CARD = 30

VALID_TEMPLATES = {"briefing", "comparison", "dashboard", "steps", "slides"}
MAX_SECTIONS = 20
MAX_SIDES = 4  # comparison: max N-way
MAX_WIDGETS = 20  # dashboard: max grid cells
MAX_STEPS = 30  # steps: max step count
MAX_SLIDES = 30  # slides: max page count

# ── template_data schemas ─────────────────────────────
#
# briefing:
#   {"summary?": str, "sections": [{"title": str, "blocks?": [int], "summary?": str, "collapsed?": bool}]}
#
# comparison:
#   2〜N-way (MAX_SIDES=4). Each side has label + blocks.
#   {"summary?": str, "sides": [{"label": str, "blocks": [int]}], "layout?": "side-by-side"|"stacked"}
#
# dashboard:
#   Flexible grid. cols controls column count, each widget has size hint.
#   {"cols?": int (1-4, default 2), "widgets": [{"title": str, "blocks": [int], "size?": "1x1"|"2x1"|"1x2"|"2x2"}]}
#
# steps:
#   Linear workflow with completion tracking.
#   {"summary?": str, "steps": [{"title": str, "blocks?": [int], "done?": bool, "description?": str}]}
#
# slides:
#   Page-by-page navigation. Each slide maps to content blocks.
#   {"slides": [{"title?": str, "blocks": [int], "notes?": str}]}


# ============================================================
# Format Registry
# ============================================================


@dataclass
class FormatSpec:
    """Specification for a content format."""

    body_type: str  # "string" | "object" | "any"
    cdn: str | None = None
    sandboxed: bool = False


FORMAT_REGISTRY: dict[str, FormatSpec] = {
    "mermaid": FormatSpec(body_type="string", cdn="mermaid/11.4.1/mermaid.min.js"),
    "markdown": FormatSpec(body_type="string", cdn="marked/15.0.0/marked.min.js"),
    "html": FormatSpec(body_type="string", cdn=None, sandboxed=True),
    "table": FormatSpec(body_type="object", cdn=None),
    "json": FormatSpec(body_type="any", cdn=None),
    "diff": FormatSpec(body_type="string", cdn="diff2html/3.4.48/diff2html.min.js"),
    "chart": FormatSpec(body_type="object", cdn="chart.js/4.4.7/chart.umd.min.js"),
    "image": FormatSpec(body_type="string", cdn=None),
    "code": FormatSpec(body_type="string", cdn="highlight.js/11.11.1/highlight.min.js"),
    "log": FormatSpec(body_type="any"),
    "status": FormatSpec(body_type="object"),
    "metric": FormatSpec(body_type="object"),
    "checklist": FormatSpec(body_type="any"),
    "timeline": FormatSpec(body_type="any"),
    "alert": FormatSpec(body_type="object"),
    "file-preview": FormatSpec(body_type="object"),
    "trace": FormatSpec(body_type="any"),
    "task-board": FormatSpec(body_type="object"),
    "tip": FormatSpec(body_type="string"),
    "progress": FormatSpec(body_type="object"),
    "terminal": FormatSpec(body_type="string"),
    "dependency-graph": FormatSpec(body_type="object"),
    "cost": FormatSpec(body_type="object"),
}


# ============================================================
# Dataclasses
# ============================================================


@dataclass
class ContentBlock:
    """A single content block within a Canvas message."""

    format: str
    body: str | dict | list
    lang: str | None = None
    x_title: str | None = None
    x_filename: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for JSON transport / DB storage."""
        d: dict[str, Any] = {"format": self.format, "body": self.body}
        if self.lang is not None:
            d["lang"] = self.lang
        if self.x_title is not None:
            d["x_title"] = self.x_title
        if self.x_filename is not None:
            d["x_filename"] = self.x_filename
        return d


@dataclass
class CanvasMessage:
    """A Canvas Message Protocol message."""

    type: str
    content: ContentBlock | list[ContentBlock]
    agent_id: str = ""
    agent_name: str = ""
    title: str = ""
    card_id: str = ""
    pinned: bool = False
    tags: list[str] = field(default_factory=list)
    template: str = ""
    template_data: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for JSON transport."""
        if isinstance(self.content, list):
            content_val: Any = [b.to_dict() for b in self.content]
        else:
            content_val = self.content.to_dict()

        d = {
            "type": self.type,
            "content": content_val,
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "title": self.title,
            "card_id": self.card_id,
            "pinned": self.pinned,
            "tags": self.tags,
        }
        if self.template:
            d["template"] = self.template
            d["template_data"] = self.template_data
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CanvasMessage:
        """Deserialize from dict."""
        raw_content = data.get("content", {})

        if isinstance(raw_content, list):
            content: ContentBlock | list[ContentBlock] = [
                ContentBlock(
                    format=b.get("format", ""),
                    body=b.get("body", ""),
                    lang=b.get("lang"),
                    x_title=b.get("x_title"),
                    x_filename=b.get("x_filename"),
                )
                for b in raw_content
                if isinstance(b, dict)
            ]
        elif isinstance(raw_content, dict):
            content = ContentBlock(
                format=raw_content.get("format", ""),
                body=raw_content.get("body", ""),
                lang=raw_content.get("lang"),
                x_title=raw_content.get("x_title"),
                x_filename=raw_content.get("x_filename"),
            )
        else:
            content = ContentBlock(format="", body="")

        return cls(
            type=data.get("type", "render"),
            content=content,
            agent_id=data.get("agent_id", ""),
            agent_name=data.get("agent_name", ""),
            title=data.get("title", ""),
            card_id=data.get("card_id", ""),
            pinned=data.get("pinned", False),
            tags=data.get("tags", []),
            template=data.get("template", ""),
            template_data=data.get("template_data", {}),
        )


# ============================================================
# Validation
# ============================================================


def _body_size(body: str | dict | list) -> int:
    """Estimate body size in bytes."""
    if isinstance(body, str):
        return len(body.encode("utf-8", errors="replace"))
    import json

    return len(json.dumps(body, ensure_ascii=False).encode("utf-8", errors="replace"))


def validate_message(msg: CanvasMessage) -> list[str]:
    """Validate a CanvasMessage. Returns list of error strings (empty = valid)."""
    errors: list[str] = []

    # Type check
    if msg.type not in VALID_MESSAGE_TYPES:
        errors.append(
            f"Invalid type '{msg.type}'. Must be one of: {', '.join(sorted(VALID_MESSAGE_TYPES))}"
        )

    # Agent ID required
    if not msg.agent_id:
        errors.append("agent_id is required")

    # Clear type doesn't need content validation
    if msg.type == "clear":
        return errors

    # Content validation
    blocks = msg.content if isinstance(msg.content, list) else [msg.content]

    if not blocks:
        errors.append("content must include at least one block")
        return errors

    if len(blocks) > MAX_BLOCKS_PER_CARD:
        errors.append(
            f"Too many content blocks ({len(blocks)}). Maximum is {MAX_BLOCKS_PER_CARD}."
        )

    for i, block in enumerate(blocks):
        if block.format not in FORMAT_REGISTRY:
            errors.append(
                f"Unknown format '{block.format}' in block {i}. "
                f"Registered formats: {', '.join(sorted(FORMAT_REGISTRY.keys()))}"
            )

        size = _body_size(block.body)
        if size > MAX_CONTENT_SIZE:
            errors.append(
                f"Content block {i} too large ({size} bytes). "
                f"Maximum size is {MAX_CONTENT_SIZE} bytes."
            )

    # Template validation
    if msg.template:
        if msg.template not in VALID_TEMPLATES:
            errors.append(
                f"Unknown template '{msg.template}'. "
                f"Valid templates: {', '.join(sorted(VALID_TEMPLATES))}"
            )
        else:
            validator = _TEMPLATE_VALIDATORS.get(msg.template)
            if validator:
                errors.extend(validator(msg))

    return errors


def _validate_briefing(msg: CanvasMessage) -> list[str]:
    """Validate briefing template_data against content blocks."""
    errors: list[str] = []
    td = msg.template_data

    # Content must be a list (composite) for briefing
    if not isinstance(msg.content, list):
        errors.append("Briefing template requires composite content (list of blocks)")
        return errors

    sections = td.get("sections")
    if sections is None:
        errors.append("Briefing template_data must contain 'sections'")
        return errors

    if not isinstance(sections, list):
        errors.append("Briefing template_data 'sections' must be a list")
        return errors

    if len(sections) == 0:
        errors.append("Briefing template_data 'sections' must not be empty")
        return errors

    if len(sections) > MAX_SECTIONS:
        errors.append(
            f"Too many sections ({len(sections)}). Maximum is {MAX_SECTIONS}."
        )

    num_blocks = len(msg.content)
    for i, section in enumerate(sections):
        if not isinstance(section, dict):
            errors.append(f"Section {i} must be a dict")
            continue

        title = section.get("title")
        if not title or not isinstance(title, str) or not title.strip():
            errors.append(f"Section {i} must have a non-empty 'title'")

    errors.extend(_validate_block_indices(sections, "Section", num_blocks))
    return errors


def _validate_block_indices(
    items: list, item_name: str, num_blocks: int, *, required: bool = False
) -> list[str]:
    """Shared helper: validate 'blocks' indices within a list of items."""
    errors: list[str] = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"{item_name} {i} must be a dict")
            continue
        block_indices = item.get("blocks")
        if block_indices is None:
            if required:
                errors.append(f"{item_name} {i} must have 'blocks'")
            continue
        if not isinstance(block_indices, list):
            errors.append(f"{item_name} {i} 'blocks' must be a list of indices")
        else:
            for idx in block_indices:
                if not isinstance(idx, int) or idx < 0 or idx >= num_blocks:
                    errors.append(
                        f"{item_name} {i} block index {idx} out of range "
                        f"(content has {num_blocks} blocks)"
                    )
    return errors


def _validate_comparison(msg: CanvasMessage) -> list[str]:
    """Validate comparison template_data."""
    errors: list[str] = []
    td = msg.template_data

    if not isinstance(msg.content, list):
        errors.append("Comparison template requires composite content (list of blocks)")
        return errors

    sides = td.get("sides")
    if sides is None:
        errors.append("Comparison template_data must contain 'sides'")
        return errors
    if not isinstance(sides, list):
        errors.append("Comparison template_data 'sides' must be a list")
        return errors
    if len(sides) < 2:
        errors.append("Comparison requires at least 2 sides")
        return errors
    if len(sides) > MAX_SIDES:
        errors.append(f"Too many sides ({len(sides)}). Maximum is {MAX_SIDES}.")

    num_blocks = len(msg.content)
    for i, side in enumerate(sides):
        if not isinstance(side, dict):
            errors.append(f"Side {i} must be a dict")
            continue
        label = side.get("label")
        if not label or not isinstance(label, str) or not label.strip():
            errors.append(f"Side {i} must have a non-empty 'label'")

    errors.extend(_validate_block_indices(sides, "Side", num_blocks, required=True))

    layout = td.get("layout")
    if layout is not None and layout not in ("side-by-side", "stacked"):
        errors.append(
            f"Invalid comparison layout '{layout}'. Must be 'side-by-side' or 'stacked'."
        )

    return errors


def _validate_dashboard(msg: CanvasMessage) -> list[str]:
    """Validate dashboard template_data."""
    errors: list[str] = []
    td = msg.template_data

    if not isinstance(msg.content, list):
        errors.append("Dashboard template requires composite content (list of blocks)")
        return errors

    widgets = td.get("widgets")
    if widgets is None:
        errors.append("Dashboard template_data must contain 'widgets'")
        return errors
    if not isinstance(widgets, list):
        errors.append("Dashboard template_data 'widgets' must be a list")
        return errors
    if len(widgets) == 0:
        errors.append("Dashboard template_data 'widgets' must not be empty")
        return errors
    if len(widgets) > MAX_WIDGETS:
        errors.append(f"Too many widgets ({len(widgets)}). Maximum is {MAX_WIDGETS}.")

    cols = td.get("cols")
    if cols is not None and (not isinstance(cols, int) or cols < 1 or cols > 4):
        errors.append("Dashboard 'cols' must be an integer between 1 and 4")

    valid_sizes = {"1x1", "2x1", "1x2", "2x2"}
    num_blocks = len(msg.content)
    for i, widget in enumerate(widgets):
        if not isinstance(widget, dict):
            errors.append(f"Widget {i} must be a dict")
            continue
        title = widget.get("title")
        if not title or not isinstance(title, str) or not title.strip():
            errors.append(f"Widget {i} must have a non-empty 'title'")
        size = widget.get("size")
        if size is not None and size not in valid_sizes:
            errors.append(
                f"Widget {i} invalid size '{size}'. Must be one of: {', '.join(sorted(valid_sizes))}"
            )

    errors.extend(_validate_block_indices(widgets, "Widget", num_blocks))
    return errors


def _validate_steps(msg: CanvasMessage) -> list[str]:
    """Validate steps template_data."""
    errors: list[str] = []
    td = msg.template_data

    if not isinstance(msg.content, list):
        errors.append("Steps template requires composite content (list of blocks)")
        return errors

    steps = td.get("steps")
    if steps is None:
        errors.append("Steps template_data must contain 'steps'")
        return errors
    if not isinstance(steps, list):
        errors.append("Steps template_data 'steps' must be a list")
        return errors
    if len(steps) == 0:
        errors.append("Steps template_data 'steps' must not be empty")
        return errors
    if len(steps) > MAX_STEPS:
        errors.append(f"Too many steps ({len(steps)}). Maximum is {MAX_STEPS}.")

    num_blocks = len(msg.content)
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            errors.append(f"Step {i} must be a dict")
            continue
        title = step.get("title")
        if not title or not isinstance(title, str) or not title.strip():
            errors.append(f"Step {i} must have a non-empty 'title'")

    errors.extend(_validate_block_indices(steps, "Step", num_blocks))
    return errors


def _validate_slides(msg: CanvasMessage) -> list[str]:
    """Validate slides template_data."""
    errors: list[str] = []
    td = msg.template_data

    if not isinstance(msg.content, list):
        errors.append("Slides template requires composite content (list of blocks)")
        return errors

    slides = td.get("slides")
    if slides is None:
        errors.append("Slides template_data must contain 'slides'")
        return errors
    if not isinstance(slides, list):
        errors.append("Slides template_data 'slides' must be a list")
        return errors
    if len(slides) == 0:
        errors.append("Slides template_data 'slides' must not be empty")
        return errors
    if len(slides) > MAX_SLIDES:
        errors.append(f"Too many slides ({len(slides)}). Maximum is {MAX_SLIDES}.")

    num_blocks = len(msg.content)
    errors.extend(_validate_block_indices(slides, "Slide", num_blocks, required=True))

    return errors


# Module-level validator dispatch (simple dict literal after all functions are defined)
_TEMPLATE_VALIDATORS: dict[str, Any] = {
    "briefing": _validate_briefing,
    "comparison": _validate_comparison,
    "dashboard": _validate_dashboard,
    "steps": _validate_steps,
    "slides": _validate_slides,
}
