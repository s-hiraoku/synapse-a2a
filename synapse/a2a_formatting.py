"""Pure formatting helpers for A2A compatibility output."""

from __future__ import annotations

from typing import Protocol

from synapse._pty_sanitize import strip_control_bytes


class ArtifactLike(Protocol):
    """Minimal artifact interface needed for text formatting."""

    type: str
    data: object


def format_artifact_text(artifact: ArtifactLike, use_markdown: bool = False) -> str:
    """Format an artifact as text for history or response."""
    if artifact.type == "code":
        code_data = artifact.data if isinstance(artifact.data, dict) else {}
        metadata = code_data.get("metadata", {})
        language = (
            metadata.get("language", "text") if isinstance(metadata, dict) else "text"
        )
        content = code_data.get("content", str(artifact.data))
        prefix = f"```{language}\n" if use_markdown else f"[Code: {language}]\n"
        suffix = "\n```" if use_markdown else ""
        text = f"{prefix}{content}{suffix}"
    elif artifact.type == "text":
        if isinstance(artifact.data, str):
            text = artifact.data
        elif isinstance(artifact.data, dict):
            text = str(artifact.data.get("content", artifact.data))
        else:
            text = str(artifact.data)
    else:
        text = f"[{artifact.type}] {artifact.data}"

    # Sanitize once at the single exit so PTY scrape residue (ANSI escapes,
    # C0/C1 control bytes) cannot leak into history or A2A output regardless
    # of artifact type. See PR #668 (#664) and #678 (#677, route C).
    return strip_control_bytes(text)
