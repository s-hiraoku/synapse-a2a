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


# Reuse strip_ansi from controller (tested, handles CSI/OSC/charset/keypad)
from synapse.controller import strip_ansi  # noqa: E402

# Additional control character pattern (BEL, etc.) not covered by strip_ansi
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

# Copilot TUI patterns
_COPILOT_STATUS_BAR_RE = re.compile(
    r"shift\+tab\s+switch\s+mode(?:\s+[·•]\s+ctrl\+\w\s+[\w ]+)*\s*",
    re.IGNORECASE,
)
_MODEL_NAME_RE = re.compile(
    r"(?:claude|gpt|gemini|copilot)[\w.-]*\s*\(\d+x?\)", re.IGNORECASE
)
_COPILOT_THINKING_RE = re.compile(
    r"(?:^|[\s)])[○◉◎●]?\s*Thinking\s+\(Esc to cancel(?:\s+[·•]\s+[\d.]+\s+\w+i?B)?\)",
    re.IGNORECASE,
)
_COPILOT_CANCEL_FRAGMENT_RE = re.compile(
    r"(?:^|[\s(])(?:E|Es|Esc|sc)\s+to\s+cancel(?:\s+[·•]\s+[\d.]+\s+\w+i?B)?\)?",
    re.IGNORECASE,
)
_LONG_MESSAGE_ECHO_RE = re.compile(
    r"(?:\]2;)?A2A:\s+\[LONG MESSAGE - FILE ATTACHED\]",
    re.IGNORECASE,
)
_SENDER_ECHO_RE = re.compile(
    r"^A2A:\s+\[From:\s+[^\]]+\]\s*",
    re.IGNORECASE,
)
_COPILOT_PERMISSION_RE = re.compile(
    r"permissions\s+(?:on|off)\s*\(shift\+tab\s+to\s+cycle\)",
    re.IGNORECASE,
)
_COPILOT_ESC_STOP_RE = re.compile(
    r"^Esc\s+to\s+stop\s*$",
    re.IGNORECASE,
)
_BARE_CSI_FRAGMENT_RE = re.compile(r"^\[\??\d*(?:;\d+)*[A-Za-z]$")
_BRANCH_STATUS_LINE_RE = re.compile(r"⎇\s+\S+.*\(\+\d+,-\d+\)")
_SPINNER_CHARS = frozenset("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏ ")
_BOX_CHARS = frozenset("─│┌┐└┘├┤┬┴┼╔╗╚╝║═╭╮╰╯┃╌╍╎╏ \u200b")

# TUI block elements (U+2580-U+259F), geometric shapes (U+25A0-U+25FF),
# and additional block/geometric characters used by OpenCode (Bubble Tea)
# and Gemini CLI (Ink) for progress bars, borders, and decorations.
# fmt: off
_TUI_BLOCK_CHARS = frozenset(
    # Block Elements U+2580-U+259F
    "▀▁▂▃▄▅▆▇█▉▊▋▌▍▎▏▐░▒▓▔▕▖▗▘▙▚▛▜▝▞▟"
    # Geometric Shapes U+25A0-U+25FF (common subset)
    "■□▢▣▤▥▦▧▨▩▪▫▬▭▮▯▰▱"
    # Miscellaneous Symbols used by TUI frameworks
    "⬝"  # U+2B1D — used by OpenCode for empty progress slots
    " "   # Space (lines may be padded)
)
# fmt: on

# Gemini CLI input prompt pattern: " > Type your message..."
_GEMINI_INPUT_PROMPT_RE = re.compile(
    r"^\s*>\s+Type your message\.\.\.\s*$",
    re.IGNORECASE,
)

# Sent message echo comparison length (shared with a2a_compat storage)
SENT_MESSAGE_COMPARE_LEN = 50


def _is_update_banner_line(line: str) -> bool:
    """Return True for CLI self-update banners that are not real replies."""
    compact = re.sub(r"[^a-z0-9:+.-]+", "", line.lower())
    if "run:brewupgrade" not in compact:
        return False
    return any(
        marker in compact
        for marker in (
            "claude-code",
            "codex",
            "gemini-cli",
            "opencode",
            "copilot",
            "updateavailable",
        )
    )


def _is_branch_status_line(line: str) -> bool:
    """Return True for git branch/status lines emitted by TUI shells."""
    return _BRANCH_STATUS_LINE_RE.search(line) is not None


# Characters that are allowed as minor residue in a TUI block line.
# These appear when ANSI sequences are partially stripped (e.g. trailing 'm').
_ANSI_RESIDUE_CHARS = frozenset("m0123456789;[")


def _is_tui_block_line(line: str) -> bool:
    """Return True for lines that are mostly TUI block/geometric chars.

    Allows up to 3 chars of ANSI residue (e.g. leading 'm' from orphaned SGR).
    Requires at least one actual block char to avoid false-positiving on
    short numeric strings like "42".
    """
    residue = 0
    has_block = False
    for c in line:
        if c in _TUI_BLOCK_CHARS:
            has_block = True
            continue
        if c in _ANSI_RESIDUE_CHARS:
            residue += 1
            if residue > 3:
                return False
        else:
            return False
    return has_block


# Vertical border characters used by TUI frames
_VERTICAL_BORDER_CHARS = frozenset("│┃║")
# Max inner text length for TUI frame content lines (avoids false positives
# on markdown tables or code that legitimately uses box-drawing chars)
_MAX_TUI_FRAME_INNER_LEN = 40


def _is_tui_frame_content_line(line: str) -> bool:
    """Return True for TUI frame content lines like '┃ prompt ┃'.

    These lines start and end with a vertical border character, with
    arbitrary (non-meaningful) content between them.  Only short inner
    text is stripped to avoid false-positiving on real code that uses
    box-drawing in markdown tables, etc.
    """
    if len(line) < 3:
        return False
    if line[0] not in _VERTICAL_BORDER_CHARS or line[-1] not in _VERTICAL_BORDER_CHARS:
        return False
    inner = line[1:-1].strip()
    return len(inner) <= _MAX_TUI_FRAME_INNER_LEN


def clean_copilot_response(raw_delta: str, sent_message: str | None = None) -> str:
    """Remove Copilot TUI artifacts from response context delta.

    Filters out spinner lines, box-drawing borders, input prompt echoes,
    and collapses consecutive duplicate lines caused by Ink re-renders.
    """
    raw_delta = strip_ansi(raw_delta)
    raw_delta = _CONTROL_CHAR_RE.sub("", raw_delta)
    cleaned: list[str] = []
    for line in raw_delta.split("\n"):
        stripped = line.strip()
        # Skip empty/whitespace-only (but keep one blank between content)
        if not stripped:
            if cleaned and cleaned[-1] != "":
                cleaned.append("")
            continue
        # Skip spinner lines (pure braille or braille prefix like "⠋ Thinking...")
        if all(c in _SPINNER_CHARS for c in stripped):
            continue
        if stripped[0] in _SPINNER_CHARS and stripped[0] != " ":
            continue
        # Skip box-drawing / border lines
        if all(c in _BOX_CHARS for c in stripped):
            continue
        # Skip TUI block element / geometric shape lines (OpenCode/Gemini),
        # allowing up to 3 chars of ANSI residue (e.g. "m■⬝⬝..." where
        # "m" is a leftover SGR suffix)
        if _is_tui_block_line(stripped):
            continue
        # Skip TUI frame content lines: ┃ text ┃ or │ text │
        if _is_tui_frame_content_line(stripped):
            continue
        # Skip Gemini CLI input prompt
        if _GEMINI_INPUT_PROMPT_RE.match(stripped):
            continue
        if _is_update_banner_line(stripped):
            continue
        if _is_branch_status_line(stripped):
            continue
        if _BARE_CSI_FRAGMENT_RE.match(stripped):
            continue
        # Strip Copilot status bar (keyboard shortcuts, model name).
        if _COPILOT_STATUS_BAR_RE.search(stripped):
            remainder = _COPILOT_STATUS_BAR_RE.sub("", stripped)
            remainder = _MODEL_NAME_RE.sub("", remainder).strip(" \t─│\u200b")
            if not remainder:
                continue
            line = remainder
            stripped = line.strip()
        line = _COPILOT_THINKING_RE.sub("", line)
        line = _COPILOT_CANCEL_FRAGMENT_RE.sub("", line)
        line = _LONG_MESSAGE_ECHO_RE.sub("", line)
        line = _SENDER_ECHO_RE.sub("", line)
        line = _COPILOT_PERMISSION_RE.sub("", line)
        if _COPILOT_ESC_STOP_RE.match(stripped):
            continue
        stripped = line.strip(" \t·•)")
        if not stripped:
            continue
        # Skip input prompt echo (> followed by sent message)
        if sent_message and stripped.lstrip("> ").startswith(
            sent_message[:SENT_MESSAGE_COMPARE_LEN]
        ):
            continue
        # Deduplicate consecutive identical lines (TUI re-render artifacts)
        if cleaned and line == cleaned[-1]:
            continue
        cleaned.append(line)

    return "\n".join(cleaned).strip()
