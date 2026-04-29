"""PTY context sanitisation helpers.

Originally introduced for permission notifications (#582/#586) which
embed a tail of the agent's PTY buffer. The same sanitisation is now
also applied at the A2A artifact persistence boundary (#664/PR #668)
and the long-message file persistence boundary (#677/PR #678) so PTY
scrape residue (CSI escapes, line-overwrite fragments, C0/C1 control
bytes, mid-sequence truncation when `[-512:]` bisects a CSI) cannot
leak into either history or A2A message files. Downstream renders
remain readable and safe to persist.
"""

from __future__ import annotations

import re

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
