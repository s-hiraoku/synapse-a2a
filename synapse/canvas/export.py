"""Canvas Card Export — convert cards to downloadable file formats.

Supports Markdown, JSON, CSV, HTML, and native format exports.
Each canvas format maps to an optimal download format via FORMAT_DOWNLOAD_MAP.
"""

from __future__ import annotations

import base64
import binascii
import csv
import io
import json
import re
from typing import Any

from synapse.controller import strip_ansi

_SENTINEL = object()


def _safe_json_loads(value: str, fallback: Any = _SENTINEL) -> Any:
    """Parse JSON string, returning fallback on failure.

    If fallback is not provided, returns the original string value.
    """
    try:
        return json.loads(value)
    except (json.JSONDecodeError, ValueError):
        return value if fallback is _SENTINEL else fallback


# ============================================================
# Language → file extension mapping (for code blocks)
# ============================================================

LANG_TO_EXT: dict[str, str] = {
    "python": ".py",
    "javascript": ".js",
    "typescript": ".ts",
    "jsx": ".jsx",
    "tsx": ".tsx",
    "java": ".java",
    "kotlin": ".kt",
    "swift": ".swift",
    "go": ".go",
    "rust": ".rs",
    "c": ".c",
    "cpp": ".cpp",
    "csharp": ".cs",
    "ruby": ".rb",
    "php": ".php",
    "html": ".html",
    "css": ".css",
    "scss": ".scss",
    "sql": ".sql",
    "shell": ".sh",
    "bash": ".sh",
    "zsh": ".zsh",
    "powershell": ".ps1",
    "yaml": ".yaml",
    "yml": ".yml",
    "toml": ".toml",
    "json": ".json",
    "xml": ".xml",
    "markdown": ".md",
    "lua": ".lua",
    "perl": ".pl",
    "r": ".r",
    "scala": ".scala",
    "elixir": ".ex",
    "erlang": ".erl",
    "haskell": ".hs",
    "clojure": ".clj",
    "dart": ".dart",
    "zig": ".zig",
    "nim": ".nim",
    "dockerfile": ".dockerfile",
    "makefile": ".makefile",
    "graphql": ".graphql",
    "protobuf": ".proto",
}

# ============================================================
# Markdown converters — Group A
# ============================================================


def _markdown_passthrough(block: dict) -> str:
    return str(block.get("body", ""))


def _checklist_to_md(block: dict) -> str:
    body = block.get("body", [])
    if isinstance(body, str):
        return body
    lines = []
    for item in body:
        if isinstance(item, dict):
            checked = "x" if item.get("done") or item.get("checked") else " "
            text = item.get("text") or item.get("label", "")
            lines.append(f"- [{checked}] {text}")
        elif isinstance(item, str):
            lines.append(f"- [ ] {item}")
    return "\n".join(lines)


def _tip_to_md(block: dict) -> str:
    body = str(block.get("body", ""))
    return f"> **Tip:** {body}"


def _alert_to_md(block: dict) -> str:
    body = block.get("body", {})
    if isinstance(body, str):
        return f"> **Alert:** {body}"
    severity = body.get("severity", "info").upper()
    message = body.get("message", "")
    return f"> **{severity}:** {message}"


def _status_to_md(block: dict) -> str:
    body = block.get("body", {})
    if isinstance(body, str):
        return f"# {body}"
    state = body.get("state", "")
    label = body.get("label", "")
    detail = body.get("detail", "")
    lines = [f"# {state}"]
    if label:
        lines.append(f"\n**{label}**")
    if detail:
        lines.append(f"\n{detail}")
    return "\n".join(lines)


def _metric_to_md(block: dict) -> str:
    body = block.get("body", {})
    if isinstance(body, str):
        return body
    value = body.get("value", "")
    unit = body.get("unit", "")
    label = body.get("label", "")
    lines = [f"# {value} {unit}".strip()]
    if label:
        lines.append(f"\n{label}")
    return "\n".join(lines)


def _progress_to_md(block: dict) -> str:
    body = block.get("body", {})
    if isinstance(body, str):
        return body
    label = body.get("label", "Progress")
    value = body.get("value", 0)
    total = body.get("total", 100)
    pct = int(value / total * 100) if total else 0
    filled = pct // 5
    bar = "[" + "#" * filled + "-" * (20 - filled) + "]"
    return f"{label}\n{bar} {pct}%"


def _timeline_to_md(block: dict) -> str:
    body = block.get("body", [])
    if isinstance(body, str):
        return body
    lines = []
    for entry in body:
        if isinstance(entry, dict):
            ts = entry.get("timestamp") or entry.get("time", "")
            text = entry.get("text") or entry.get("label", "")
            lines.append(f"- **{ts}** — {text}")
        elif isinstance(entry, str):
            lines.append(f"- {entry}")
    return "\n".join(lines)


def _link_preview_to_md(block: dict) -> str:
    body = block.get("body", {})
    if isinstance(body, str):
        return body
    url = body.get("url", "")
    title = body.get("title", url)
    description = body.get("description", "")
    lines = [f"[{title}]({url})"]
    if description:
        lines.append(f"\n{description}")
    return "\n".join(lines)


def _mermaid_to_md(block: dict) -> str:
    body = str(block.get("body", ""))
    return f"```mermaid\n{body}\n```"


def _chart_to_md(block: dict) -> str:
    body = block.get("body", {})
    if isinstance(body, str):
        return f"```json\n{body}\n```"
    if isinstance(body, dict):
        chart_type = str(body.get("type", "chart"))
        json_str = json.dumps(body, indent=2, ensure_ascii=False)
        return f"### {chart_type.title()} Chart\n\n```json\n{json_str}\n```"
    json_str = json.dumps(body, indent=2, ensure_ascii=False)
    return f"```json\n{json_str}\n```"


# ============================================================
# Native converters — Group B
# ============================================================


def _code_to_native(block: dict) -> tuple[bytes, str, str]:
    """Return (content_bytes, extension, mime_type) for code blocks."""
    lang = (block.get("lang") or "").lower()
    ext = LANG_TO_EXT.get(lang, ".txt")
    body = str(block.get("body", ""))
    return body.encode("utf-8"), ext, "text/plain; charset=utf-8"


def _html_to_native(block: dict) -> tuple[bytes, str, str]:
    body = str(block.get("body", ""))
    return body.encode("utf-8"), ".html", "text/html; charset=utf-8"


def _diff_to_native(block: dict) -> tuple[bytes, str, str]:
    body = str(block.get("body", ""))
    return body.encode("utf-8"), ".diff", "text/x-diff; charset=utf-8"


def _mermaid_to_native(block: dict) -> tuple[bytes, str, str]:
    body = str(block.get("body", ""))
    return body.encode("utf-8"), ".mmd", "text/plain; charset=utf-8"


def _terminal_to_native(block: dict) -> tuple[bytes, str, str]:
    body = str(block.get("body", ""))
    cleaned = strip_ansi(body)
    return cleaned.encode("utf-8"), ".txt", "text/plain; charset=utf-8"


def _image_to_native(block: dict) -> tuple[bytes, str, str]:
    """Decode data URI images or return redirect hint for external URLs."""
    body = str(block.get("body", ""))
    # data:image/png;base64,...
    m = re.match(r"data:image/([^;]+);base64,(.+)", body, re.DOTALL)
    if m:
        fmt = m.group(1).lower()
        ext_map = {
            "png": ".png",
            "jpeg": ".jpg",
            "jpg": ".jpg",
            "svg+xml": ".svg",
            "gif": ".gif",
        }
        ext = ext_map.get(fmt, f".{fmt}")
        mime = f"image/{fmt}"
        try:
            data = base64.b64decode(m.group(2), validate=True)
        except binascii.Error:
            return body.encode("utf-8"), ".txt", "text/plain; charset=utf-8"
        return data, ext, mime
    # Fallback: treat as text reference
    return body.encode("utf-8"), ".txt", "text/plain; charset=utf-8"


# ============================================================
# CSV converters — Group D
# ============================================================


def _table_to_csv(block: dict) -> bytes:
    body = block.get("body", {})
    if isinstance(body, str):
        return body.encode("utf-8")
    headers = body.get("headers", [])
    rows = body.get("rows", [])
    buf = io.StringIO()
    writer = csv.writer(buf)
    if headers:
        writer.writerow(headers)
    for row in rows:
        writer.writerow(row)
    return buf.getvalue().encode("utf-8")


def _cost_to_csv(block: dict) -> bytes:
    body = block.get("body", {})
    if isinstance(body, str):
        return body.encode("utf-8")
    agents = body.get("agents", [])
    total = body.get("total", {})
    buf = io.StringIO()
    writer = csv.writer(buf)
    # Header row from first agent's keys
    if agents:
        keys = list(agents[0].keys())
        writer.writerow(keys)
        for agent in agents:
            writer.writerow([agent.get(k, "") for k in keys])
    if total:
        writer.writerow([])
        writer.writerow(["Total"])
        for k, v in total.items():
            writer.writerow([k, v])
    return buf.getvalue().encode("utf-8")


# ============================================================
# Template → Markdown converters
# ============================================================

# Native format exporter dispatch (Group B)
_NATIVE_EXPORTERS: dict[str, Any] = {
    "code": _code_to_native,
    "html": _html_to_native,
    "artifact": _html_to_native,
    "diff": _diff_to_native,
    "mermaid": _mermaid_to_native,
    "terminal": _terminal_to_native,
    "image": _image_to_native,
}

# Markdown converter dispatch for individual block formats
_BLOCK_MD_CONVERTERS: dict[str, Any] = {
    "markdown": _markdown_passthrough,
    "checklist": _checklist_to_md,
    "tip": _tip_to_md,
    "alert": _alert_to_md,
    "status": _status_to_md,
    "metric": _metric_to_md,
    "progress": _progress_to_md,
    "timeline": _timeline_to_md,
    "link-preview": _link_preview_to_md,
    "mermaid": _mermaid_to_md,
    "chart": _chart_to_md,
}


def _block_to_markdown(block: dict) -> str:
    """Convert any block to Markdown representation."""
    fmt = block.get("format", "")
    converter = _BLOCK_MD_CONVERTERS.get(fmt)
    if converter:
        return str(converter(block))
    # Fallback: JSON dump for structured data, string for text
    body = block.get("body", "")
    if isinstance(body, str):
        return body
    return f"```json\n{json.dumps(body, indent=2, ensure_ascii=False)}\n```"


def _blocks_at_indices(blocks: list[dict], indices: list[int]) -> list[dict]:
    """Safely extract blocks by index list."""
    return [blocks[i] for i in indices if isinstance(i, int) and 0 <= i < len(blocks)]


def _template_to_markdown(
    card: dict, *, pre_parsed_blocks: list[dict] | None = None
) -> str:
    """Convert a template card to Markdown.

    Args:
        card: Card dict.
        pre_parsed_blocks: If provided, skip re-parsing content from card dict.
    """
    template = card.get("template", "")
    td = card.get("template_data", {})
    if isinstance(td, str):
        td = _safe_json_loads(td, {})
    if pre_parsed_blocks is not None:
        blocks = pre_parsed_blocks
    else:
        content = card.get("content", [])
        if isinstance(content, str):
            content = _safe_json_loads(content, [])
        blocks = content if isinstance(content, list) else [content]

    title = card.get("title", "")
    lines = [f"# {title}\n"] if title else []

    if template == "briefing":
        summary = td.get("summary", "")
        if summary:
            lines.append(f"{summary}\n")
        for section in td.get("sections", []):
            lines.append(f"## {section.get('title', '')}\n")
            s_summary = section.get("summary", "")
            if s_summary:
                lines.append(f"{s_summary}\n")
            for blk in _blocks_at_indices(blocks, section.get("blocks", [])):
                lines.append(_block_to_markdown(blk))
                lines.append("")

    elif template == "comparison":
        summary = td.get("summary", "")
        if summary:
            lines.append(f"{summary}\n")
        for side in td.get("sides", []):
            lines.append(f"## {side.get('label', '')}\n")
            for blk in _blocks_at_indices(blocks, side.get("blocks", [])):
                lines.append(_block_to_markdown(blk))
                lines.append("")

    elif template == "dashboard":
        for widget in td.get("widgets", []):
            lines.append(f"## {widget.get('title', '')}\n")
            for blk in _blocks_at_indices(blocks, widget.get("blocks", [])):
                lines.append(_block_to_markdown(blk))
                lines.append("")

    elif template == "steps":
        summary = td.get("summary", "")
        if summary:
            lines.append(f"{summary}\n")
        for i, step in enumerate(td.get("steps", []), 1):
            done = "x" if step.get("done") else " "
            lines.append(f"{i}. [{done}] {step.get('title', '')}")
            desc = step.get("description", "")
            if desc:
                lines.append(f"   {desc}")
            for blk in _blocks_at_indices(blocks, step.get("blocks", [])):
                for line in _block_to_markdown(blk).splitlines():
                    lines.append(f"   {line}")
            lines.append("")

    elif template == "slides":
        for i, slide in enumerate(td.get("slides", [])):
            if i > 0:
                lines.append("---\n")
            slide_title = slide.get("title", "")
            if slide_title:
                lines.append(f"## {slide_title}\n")
            for blk in _blocks_at_indices(blocks, slide.get("blocks", [])):
                lines.append(_block_to_markdown(blk))
                lines.append("")
            notes = slide.get("notes", "")
            if notes:
                lines.append(f"> {notes}\n")

    elif template == "plan":
        plan_status = td.get("status", "")
        if plan_status:
            lines.append(f"**Status:** {plan_status}\n")
        mermaid = td.get("mermaid", "")
        if mermaid:
            lines.append(f"```mermaid\n{mermaid}\n```\n")
        steps = td.get("steps", [])
        if steps:
            lines.append("| # | Step | Agent | Status |")
            lines.append("|---|------|-------|--------|")
            for i, step in enumerate(steps, 1):
                sid = step.get("id", "")
                subject = step.get("subject", "")
                agent = step.get("agent", "")
                status = step.get("status", "pending")
                lines.append(f"| {i} | {subject} ({sid}) | {agent} | {status} |")
            lines.append("")

    return "\n".join(lines)


# ============================================================
# Format → download spec
# ============================================================

# Each entry: (group, default_ext, default_mime)
# group: "md", "native", "json", "csv"
FORMAT_DOWNLOAD_MAP: dict[str, tuple[str, str, str]] = {
    # Group A: Markdown
    "markdown": ("md", ".md", "text/markdown; charset=utf-8"),
    "checklist": ("md", ".md", "text/markdown; charset=utf-8"),
    "tip": ("md", ".md", "text/markdown; charset=utf-8"),
    "alert": ("md", ".md", "text/markdown; charset=utf-8"),
    "status": ("md", ".md", "text/markdown; charset=utf-8"),
    "metric": ("md", ".md", "text/markdown; charset=utf-8"),
    "progress": ("md", ".md", "text/markdown; charset=utf-8"),
    "timeline": ("md", ".md", "text/markdown; charset=utf-8"),
    "link-preview": ("md", ".md", "text/markdown; charset=utf-8"),
    # Group B: Native
    "code": ("native", ".txt", "text/plain; charset=utf-8"),
    "html": ("native", ".html", "text/html; charset=utf-8"),
    "artifact": ("native", ".html", "text/html; charset=utf-8"),
    "diff": ("native", ".diff", "text/x-diff; charset=utf-8"),
    "mermaid": ("native", ".mmd", "text/plain; charset=utf-8"),
    "terminal": ("native", ".txt", "text/plain; charset=utf-8"),
    "image": ("native", ".png", "image/png"),
    # Group C: JSON
    "json": ("json", ".json", "application/json; charset=utf-8"),
    "chart": ("json", ".json", "application/json; charset=utf-8"),
    "dependency-graph": ("json", ".json", "application/json; charset=utf-8"),
    "trace": ("json", ".json", "application/json; charset=utf-8"),
    "log": ("json", ".json", "application/json; charset=utf-8"),
    "file-preview": ("json", ".json", "application/json; charset=utf-8"),
    "plan": ("json", ".json", "application/json; charset=utf-8"),
    # Group D: CSV
    "table": ("csv", ".csv", "text/csv; charset=utf-8"),
    "cost": ("csv", ".csv", "text/csv; charset=utf-8"),
}

MAX_EXPORT_SIZE = 50 * 1024 * 1024  # 50 MB


def _sanitize_filename(name: str) -> str:
    """Replace non-alphanumeric characters with hyphens.

    Strips control characters, quotes, and newlines to prevent
    Content-Disposition header injection.
    """
    # Remove control chars and quotes first
    name = re.sub(r'[\x00-\x1f\x7f"\'\\]', "", name)
    sanitized = re.sub(r"[^a-zA-Z0-9_\-]", "-", name)
    sanitized = re.sub(r"-+", "-", sanitized).strip("-")
    # Limit length to prevent overly long filenames
    return sanitized[:80] if sanitized else "card"


def export_card(
    card_dict: dict,
    target_format: str | None = None,
) -> tuple[bytes, str, str]:
    """Export a card to downloadable format.

    Args:
        card_dict: Full card dict from CanvasStore.get_card().
        target_format: Override format ("md", "json", "csv", "html", "txt", "native").
            If None, uses the optimal format for the card's content format.

    Returns:
        (content_bytes, filename, content_type)
    """
    title = card_dict.get("title", "")
    card_id = _sanitize_filename(card_dict.get("card_id", "unknown"))
    template = card_dict.get("template", "")
    content = card_dict.get("content", [])
    if isinstance(content, str):
        parsed = _safe_json_loads(content, None)
        content = (
            parsed if parsed is not None else [{"format": "markdown", "body": content}]
        )

    blocks = content if isinstance(content, list) else [content]
    primary_format = blocks[0].get("format", "") if blocks else ""

    base_name = _sanitize_filename(title) if title else "card"
    filename_base = f"{base_name}-{card_id[:8]}"

    # Template cards
    if template:
        if target_format == "json":
            data = json.dumps(card_dict, indent=2, ensure_ascii=False).encode("utf-8")
            return data, f"{filename_base}.json", "application/json; charset=utf-8"
        # Default: Markdown (pass pre-parsed blocks to avoid double parsing)
        md = _template_to_markdown(card_dict, pre_parsed_blocks=blocks)
        return md.encode("utf-8"), f"{filename_base}.md", "text/markdown; charset=utf-8"

    # Non-template cards
    if not blocks:
        return b"", f"{filename_base}.txt", "text/plain; charset=utf-8"

    # Multi-block non-template: join all blocks as Markdown, or JSON if requested
    if len(blocks) > 1:
        if target_format == "json":
            data = json.dumps(
                [b.get("body", "") for b in blocks], indent=2, ensure_ascii=False
            ).encode("utf-8")
            return data, f"{filename_base}.json", "application/json; charset=utf-8"
        parts = [_block_to_markdown(b) for b in blocks]
        md = "\n\n".join(parts)
        return md.encode("utf-8"), f"{filename_base}.md", "text/markdown; charset=utf-8"

    block = blocks[0]
    spec = FORMAT_DOWNLOAD_MAP.get(primary_format)
    if not spec:
        # Unknown format fallback
        body = block.get("body", "")
        if isinstance(body, str):
            data = body.encode("utf-8")
        else:
            data = json.dumps(body, indent=2, ensure_ascii=False).encode("utf-8")
        return data, f"{filename_base}.txt", "text/plain; charset=utf-8"

    group, default_ext, default_mime = spec

    # Override with target_format if specified
    if target_format:
        if target_format == "md":
            md = _block_to_markdown(block)
            return (
                md.encode("utf-8"),
                f"{filename_base}.md",
                "text/markdown; charset=utf-8",
            )
        elif target_format == "json":
            body = block.get("body", "")
            if isinstance(body, str):
                body = _safe_json_loads(body, body)
            data = json.dumps(body, indent=2, ensure_ascii=False).encode("utf-8")
            return data, f"{filename_base}.json", "application/json; charset=utf-8"
        elif target_format == "csv":
            if primary_format == "table":
                data = _table_to_csv(block)
            elif primary_format == "cost":
                data = _cost_to_csv(block)
            else:
                # Format doesn't support CSV natively; export as empty CSV
                data = b""
            return data, f"{filename_base}.csv", "text/csv; charset=utf-8"
        elif target_format in ("html", "native"):
            group = "native"
        elif target_format == "txt":
            body = block.get("body", "")
            text = (
                strip_ansi(str(body))
                if isinstance(body, str)
                else json.dumps(body, indent=2, ensure_ascii=False)
            )
            return (
                text.encode("utf-8"),
                f"{filename_base}.txt",
                "text/plain; charset=utf-8",
            )

    # Default conversion by group
    if group == "md":
        md = _block_to_markdown(block)
        return md.encode("utf-8"), f"{filename_base}.md", "text/markdown; charset=utf-8"

    elif group == "native":
        exporter = _NATIVE_EXPORTERS.get(primary_format)
        if exporter:
            data, ext, mime = exporter(block)
        else:
            body = str(block.get("body", ""))
            data, ext, mime = body.encode("utf-8"), default_ext, default_mime
        return data, f"{filename_base}{ext}", mime

    elif group == "json":
        body = block.get("body", "")
        if isinstance(body, str):
            body = _safe_json_loads(body, body)
        data = json.dumps(body, indent=2, ensure_ascii=False).encode("utf-8")
        return data, f"{filename_base}.json", "application/json; charset=utf-8"

    elif group == "csv":
        if primary_format == "table":
            data = _table_to_csv(block)
        elif primary_format == "cost":
            data = _cost_to_csv(block)
        else:
            data = b""
        return data, f"{filename_base}.csv", "text/csv; charset=utf-8"

    # Fallback
    body = block.get("body", "")
    if isinstance(body, str):
        data = body.encode("utf-8")
    else:
        data = json.dumps(body, indent=2, ensure_ascii=False).encode("utf-8")
    return data, f"{filename_base}.txt", "text/plain; charset=utf-8"
