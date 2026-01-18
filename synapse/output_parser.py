"""
Output Parser for CLI output.

Parses CLI output into structured segments for A2A Artifacts.
Segments include: code blocks, file references, errors, and plain text.
"""

import re
from dataclasses import dataclass, field


@dataclass
class ParsedSegment:
    """A parsed segment of CLI output."""

    type: str  # "text", "code", "file", "error"
    content: str
    metadata: dict = field(default_factory=dict)
    start: int = 0  # Start position in original text
    end: int = 0  # End position in original text


# Error patterns (subset for output parsing - full detection in error_detector.py)
ERROR_PATTERNS: list[tuple[str, str]] = [
    (r"(?:^|\n)\s*error[:\s]", "error"),
    (r"(?:^|\n)\s*Error[:\s]", "error"),
    (r"(?:^|\n)\s*ERROR[:\s]", "error"),
    (r"traceback \(most recent call last\)", "traceback"),
    (r"(?:^|\n)\s*exception:", "exception"),
    (r"command not found", "command_not_found"),
    (r"permission denied", "permission_denied"),
    (r"no such file or directory", "file_not_found"),
    (r"syntax error", "syntax_error"),
    (r"(?:^|\n)fatal:", "fatal"),
    (r"(?:^|\n)panic:", "panic"),
]

# File action patterns - quoted patterns only to avoid double-matching
FILE_ACTION_PATTERNS: list[tuple[str, str]] = [
    # Quoted file paths (most common in CLI output)
    (
        r'(?:created|wrote|saved|generated|output)\s+(?:file\s+)?[`"\']([^`"\']+)[`"\']',
        "created",
    ),
    (r'(?:modified|updated|changed)\s+(?:file\s+)?[`"\']([^`"\']+)[`"\']', "modified"),
    (r'(?:deleted|removed)\s+(?:file\s+)?[`"\']([^`"\']+)[`"\']', "deleted"),
    (r'(?:read|reading|opened)\s+(?:file\s+)?[`"\']([^`"\']+)[`"\']', "read"),
    # Unquoted file paths with extension (only if not already quoted)
    (
        r'(?:created|wrote|saved|generated|output)\s+(?:file\s+)?(?![`"\'])(\S+\.(?:py|js|ts|tsx|jsx|json|yaml|yml|md|txt|html|css|sh|go|rs|java|c|cpp|h|hpp))(?![`"\'])',
        "created",
    ),
    (
        r'(?:modified|updated|changed)\s+(?:file\s+)?(?![`"\'])(\S+\.(?:py|js|ts|tsx|jsx|json|yaml|yml|md|txt|html|css|sh|go|rs|java|c|cpp|h|hpp))(?![`"\'])',
        "modified",
    ),
]


def extract_code_blocks(output: str) -> list[ParsedSegment]:
    """Extract code blocks from markdown-style fenced code."""
    segments = []

    # Pattern for fenced code blocks: ```lang\ncode\n``` or ```lang code```
    # Language can include +, -, #, . (e.g., c++, c#, objective-c, .net)
    # Newline after language is optional (allows inline code blocks)
    code_pattern = r"```([\w+#.-]*)[ \t]*\n?(.*?)```"

    for match in re.finditer(code_pattern, output, re.DOTALL):
        lang = match.group(1) or "text"
        code = match.group(2).rstrip("\n")

        segments.append(
            ParsedSegment(
                type="code",
                content=code,
                metadata={"language": lang},
                start=match.start(),
                end=match.end(),
            )
        )

    return segments


def extract_file_references(output: str) -> list[ParsedSegment]:
    """Extract file references from output."""
    segments = []
    seen_entries = set()  # Avoid duplicates (file + action combinations)

    for pattern, action in FILE_ACTION_PATTERNS:
        for match in re.finditer(pattern, output, re.IGNORECASE):
            filepath = match.group(1)

            # Skip duplicates of same file+action (different actions allowed)
            entry_key = (filepath, action)
            if entry_key in seen_entries:
                continue
            seen_entries.add(entry_key)

            segments.append(
                ParsedSegment(
                    type="file",
                    content=filepath,
                    metadata={"action": action},
                    start=match.start(),
                    end=match.end(),
                )
            )

    return segments


def extract_errors(output: str) -> list[ParsedSegment]:
    """Extract error segments from output."""
    segments = []

    # Check for Python tracebacks (multi-line)
    # Captures from "Traceback" through the final error line (e.g., "NameError: ...")
    traceback_pattern = (
        r"Traceback \(most recent call last\):(?:\n.*?)+?\n\w+Error[^\n]*"
    )
    for match in re.finditer(traceback_pattern, output, re.DOTALL | re.IGNORECASE):
        segments.append(
            ParsedSegment(
                type="error",
                content=match.group(0),
                metadata={"error_type": "traceback"},
                start=match.start(),
                end=match.end(),
            )
        )

    # Check for single-line errors
    for pattern, error_type in ERROR_PATTERNS:
        for match in re.finditer(pattern, output, re.IGNORECASE | re.MULTILINE):
            # Get the full line containing the error
            line_start = output.rfind("\n", 0, match.start()) + 1
            line_end = output.find("\n", match.end())
            if line_end == -1:
                line_end = len(output)

            error_line = output[line_start:line_end].strip()

            # Skip if already captured in traceback
            if any(s.start <= line_start < s.end for s in segments):
                continue

            segments.append(
                ParsedSegment(
                    type="error",
                    content=error_line,
                    metadata={"error_type": error_type},
                    start=line_start,
                    end=line_end,
                )
            )

    return segments


def parse_output(output: str) -> list[ParsedSegment]:
    """
    Parse CLI output into structured segments.

    Returns segments in order of appearance, with remaining text
    captured as "text" type segments.

    Args:
        output: Raw CLI output string

    Returns:
        List of ParsedSegment objects
    """
    if not output:
        return []

    # Extract all special segments
    code_segments = extract_code_blocks(output)
    file_segments = extract_file_references(output)
    error_segments = extract_errors(output)

    # Combine and sort by position
    all_segments = code_segments + file_segments + error_segments
    all_segments.sort(key=lambda s: s.start)

    # Remove overlapping segments (keep first/earlier one)
    non_overlapping = []
    last_end = 0
    for seg in all_segments:
        if seg.start >= last_end:
            non_overlapping.append(seg)
            last_end = seg.end

    # Fill gaps with text segments
    result = []
    pos = 0

    for seg in non_overlapping:
        # Add text segment for gap before this segment
        if seg.start > pos:
            text_content = output[pos : seg.start].strip()
            if text_content:
                result.append(
                    ParsedSegment(
                        type="text", content=text_content, start=pos, end=seg.start
                    )
                )

        result.append(seg)
        pos = seg.end

    # Add remaining text after last segment
    if pos < len(output):
        text_content = output[pos:].strip()
        if text_content:
            result.append(
                ParsedSegment(
                    type="text", content=text_content, start=pos, end=len(output)
                )
            )

    # If no segments found, return entire output as text
    if not result and output.strip():
        result.append(
            ParsedSegment(type="text", content=output.strip(), start=0, end=len(output))
        )

    return result


def segments_to_artifacts(segments: list[ParsedSegment]) -> list[dict]:
    """
    Convert ParsedSegments to A2A Artifact format.

    Args:
        segments: List of ParsedSegment objects

    Returns:
        List of A2A-compatible artifact dictionaries
    """
    artifacts: list[dict] = []

    for i, seg in enumerate(segments):
        artifact: dict = {"index": i, "parts": []}

        if seg.type == "code":
            artifact["parts"].append(
                {
                    "type": "code",
                    "code": seg.content,
                    "language": seg.metadata.get("language", "text"),
                }
            )
        elif seg.type == "file":
            artifact["parts"].append(
                {
                    "type": "file",
                    "file": {
                        "path": seg.content,
                        "action": seg.metadata.get("action", "unknown"),
                    },
                }
            )
        elif seg.type == "error":
            artifact["parts"].append(
                {
                    "type": "error",
                    "error": {
                        "type": seg.metadata.get("error_type", "error"),
                        "message": seg.content,
                    },
                }
            )
        else:  # text
            artifact["parts"].append({"type": "text", "text": seg.content})

        artifacts.append(artifact)

    return artifacts
