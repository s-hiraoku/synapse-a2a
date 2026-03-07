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
MAX_CONTENT_SIZE = 500_000  # 500KB per content block
MAX_BLOCKS_PER_CARD = 10


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

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for JSON transport."""

        def _block_to_dict(block: ContentBlock) -> dict[str, Any]:
            d: dict[str, Any] = {"format": block.format, "body": block.body}
            if block.lang is not None:
                d["lang"] = block.lang
            return d

        if isinstance(self.content, list):
            content_val: Any = [_block_to_dict(b) for b in self.content]
        else:
            content_val = _block_to_dict(self.content)

        return {
            "type": self.type,
            "content": content_val,
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "title": self.title,
            "card_id": self.card_id,
            "pinned": self.pinned,
            "tags": self.tags,
        }

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
                )
                for b in raw_content
            ]
        else:
            content = ContentBlock(
                format=raw_content.get("format", ""),
                body=raw_content.get("body", ""),
                lang=raw_content.get("lang"),
            )

        return cls(
            type=data.get("type", "render"),
            content=content,
            agent_id=data.get("agent_id", ""),
            agent_name=data.get("agent_name", ""),
            title=data.get("title", ""),
            card_id=data.get("card_id", ""),
            pinned=data.get("pinned", False),
            tags=data.get("tags", []),
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

    return errors
