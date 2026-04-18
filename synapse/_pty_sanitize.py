"""PTY context sanitisation helpers for permission notifications.

Permission notifications embed a tail of the agent's PTY buffer so the
sender can decide whether to approve. The raw buffer can contain CSI
escapes, line-overwrite fragments, C0/C1 control bytes, and
mid-sequence truncation when `[-512:]` bisects a CSI. See issues #582
and #586. This module strips those byte classes so downstream renders
are readable and safe to persist.
"""

from __future__ import annotations

import re

# CSI / OSC / two-char escape sequences that may survive strip_ansi
# (e.g. because of mid-sequence truncation) plus standalone C0/C1
# control bytes. TAB / LF / CR are preserved.
# Strip CSI / OSC / two-char escape sequences, plus all C0/C1 control
# bytes except TAB (\x09) and LF (\x0a). CR (\x0d) is removed so that
# line-overwrite remnants don't re-merge subsequent lines when rendered.
_RESIDUAL_CONTROL_RE = re.compile(
    r"\x1b\[[0-?]*[ -/]*(?:[@-~]|$)"
    r"|\x9b[0-?]*[ -/]*(?:[@-~]|$)"
    r"|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\|$)"
    r"|\x9d[^\x07\x9c]*(?:\x07|\x9c|$)"
    r"|\x1b[()][AB0-2]"
    r"|\x1b[>=MD]"
    r"|[\x00-\x08\x0b-\x1f\x7f-\x9f]"
)


def strip_control_bytes(text: str) -> str:
    """Remove residual CSI/OSC fragments and C0/C1 control bytes.

    Keeps TAB and LF (so multi-line structure survives). CR is removed
    because the PTY-overwrite pattern that causes #586 relies on CR to
    re-merge repeated partial writes into the same line.
    """
    return _RESIDUAL_CONTROL_RE.sub("", text)


def tail_printable(text: str, limit: int = 512) -> str:
    """Take the last ``limit`` characters of sanitised text.

    Strips control bytes first so the limit is measured against
    meaningful output and the tail cannot start mid-ANSI sequence.
    """
    if not text:
        return ""
    return strip_control_bytes(text)[-limit:]


def printable_len(text: str) -> int:
    """Count printable characters (plus TAB/LF/CR) in ``text``."""
    if not text:
        return 0
    return sum(1 for ch in text if ch.isprintable() or ch in ("\t", "\n", "\r"))


def printable_ratio(text: str) -> float:
    """Fraction of bytes in ``text`` that are printable (plus TAB/LF/CR).

    Empty input returns 1.0 (treat as trivially printable).
    """
    if not text:
        return 1.0
    printable = sum(1 for ch in text if ch.isprintable() or ch in ("\t", "\n", "\r"))
    return printable / len(text)


def looks_like_garbage(text: str) -> bool:
    """Heuristic guard for permission-notification long-messages.

    Returns True when the content is most likely a corrupted PTY
    snapshot that should not be persisted:

    - More than 50% non-printable bytes, OR
    - More than five ``\\x1b[`` CSI fragments per 1 KB.
    """
    if not text:
        return False
    if printable_ratio(text) < 0.5:
        return True
    kb = max(1, len(text) // 1024)
    csi_fragments = text.count("\x1b[")
    return (csi_fragments / kb) > 5.0
