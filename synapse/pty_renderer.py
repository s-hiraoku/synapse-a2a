"""Virtual terminal rendering for captured PTY bytes.

The pre-#572 waiting_detection path evaluated its profile regex against
text produced by stripping ANSI escape sequences from the raw PTY byte
stream. That loses information: cursor-motion CSI sequences (``\\x1b[H``,
``\\x1b[<n>;<m>H``) are removed but the repeated payloads they wrote in
place are still concatenated end-to-end. For TUIs like ratatui (used by
codex) the result is garbled output such as
``Working•Working•orking•rking•kinging`` that no regex can match.

``PtyRenderer`` feeds raw bytes into a ``pyte`` virtual screen so the
downstream consumer sees what the user would have seen: the final state
of each cell after cursor motion, erases, and overwrites have been
applied. Alt-screen toggles (DECSET/DECRST 1049) are tracked so
full-screen overlays are exposed cleanly.
"""

from __future__ import annotations

import codecs
import logging
from typing import Any

import pyte
from wcwidth import wcwidth

_ALT_SCREEN_ENTER = "\x1b[?1049h"
_ALT_SCREEN_LEAVE = "\x1b[?1049l"

logger = logging.getLogger(__name__)


def _split_trailing_incomplete_csi(text: str) -> tuple[str, str]:
    """Split an incomplete ESC/CSI sequence off the end of *text*.

    Returns ``(pending, clean)`` where *pending* is the trailing
    fragment that might be the start of an escape sequence (held back
    for the next ``feed`` call) and *clean* is the remainder that is
    safe to process now.
    """
    if not text:
        return "", ""
    last_esc = text.rfind("\x1b")
    if last_esc == -1:
        return "", text
    tail = text[last_esc:]
    # A complete CSI sequence ends with a letter (@ through ~).
    # If the tail is just ESC or ESC[ followed by parameter bytes
    # (digits, semicolons, question marks) but no final byte, it is
    # incomplete and must be held back.
    if len(tail) == 1:
        # Bare ESC — could be start of CSI, OSC, SS2/SS3, etc.
        return tail, text[:last_esc]
    if tail[1] == "[":
        # CSI: \x1b[ followed by parameter/intermediate bytes, ended
        # by a byte in 0x40–0x7E range.
        for i in range(2, len(tail)):
            ch = tail[i]
            if "\x40" <= ch <= "\x7e":
                # Complete sequence found — nothing to hold back.
                return "", text
        # Reached end of tail without a final byte.
        return tail, text[:last_esc]
    if tail[1] == "]":
        # OSC: terminated by ST (\x1b\\) or BEL (\x07).
        if "\x07" in tail or "\x1b\\" in tail[1:]:
            return "", text
        return tail, text[:last_esc]
    # Two-character escape (e.g. \x1b= , \x1bM) — already complete.
    return "", text


class PtyRenderer:
    """Feed raw PTY bytes and read back the rendered terminal state."""

    def __init__(self, columns: int = 80, rows: int = 24) -> None:
        self._columns = columns
        self._rows = rows
        self._screen = pyte.Screen(columns, rows)
        self._stream = pyte.Stream(self._screen)
        self._in_alt_screen = False
        self._saved_display: list[str] | None = None
        self._decoder = codecs.getincrementaldecoder("utf-8")("replace")
        self._pending = ""

    @property
    def in_alt_screen(self) -> bool:
        return self._in_alt_screen

    @property
    def cursor(self) -> tuple[int, int]:
        return (self._screen.cursor.x, self._screen.cursor.y)

    def feed(self, data: bytes | str) -> None:
        """Feed a chunk of PTY output into the virtual screen.

        Accepts either bytes (typical output from ``os.read``) or a
        pre-decoded string. Uses an incremental decoder so multi-byte
        UTF-8 split across ``os.read`` boundaries is handled correctly.
        """
        if isinstance(data, bytes):
            text = self._decoder.decode(data, final=False)
        else:
            text = data
        text = self._pending + text
        self._pending, text = _split_trailing_incomplete_csi(text)
        # Handle alt-screen transitions ourselves: pyte does not treat
        # DECSET 1049 as a distinct buffer, so we snapshot/restore the
        # primary display across the toggle to keep the rendered view
        # consistent with what the user sees.
        while text:
            if not self._in_alt_screen:
                idx = text.find(_ALT_SCREEN_ENTER)
                if idx == -1:
                    self._stream.feed(text)
                    return
                self._stream.feed(text[:idx])
                self._saved_display = list(self._screen.display)
                self._screen.reset()
                self._in_alt_screen = True
                text = text[idx + len(_ALT_SCREEN_ENTER) :]
            else:
                idx = text.find(_ALT_SCREEN_LEAVE)
                if idx == -1:
                    self._stream.feed(text)
                    return
                self._stream.feed(text[:idx])
                self._screen.reset()
                if self._saved_display is not None:
                    for y, line in enumerate(self._saved_display):
                        if y >= self._rows:
                            break
                        self._stream.feed(f"\x1b[{y + 1};1H" + line.rstrip())
                self._saved_display = None
                self._in_alt_screen = False
                text = text[idx + len(_ALT_SCREEN_LEAVE) :]

    def render(self) -> list[str]:
        """Return the current display as a list of right-stripped lines."""
        broken_cells = 0
        lines: list[str] = []
        for y in range(self._rows):
            line = self._screen.buffer[y]
            chars: list[str] = []
            skip_wide_stub = False
            for x in range(self._columns):
                if skip_wide_stub:
                    skip_wide_stub = False
                    continue
                cell_data = line[x].data
                try:
                    if not cell_data:
                        raise IndexError("empty pyte cell data")
                    if sum(map(wcwidth, cell_data[1:])) != 0:
                        raise AssertionError("unexpected wide continuation data")
                    skip_wide_stub = wcwidth(cell_data[0]) == 2
                except (AssertionError, IndexError):
                    broken_cells += 1
                    cell_data = " "
                    skip_wide_stub = False
                chars.append(cell_data)
            lines.append("".join(chars).rstrip())
        if broken_cells:
            logger.debug(
                "Substituted blanks for %d broken pyte screen cells during render",
                broken_cells,
            )
        return lines

    def render_text(self) -> str:
        """Return the rendered display as a newline-joined string.

        Blank trailing lines are preserved so positional regexes still
        see consistent line indices, but leading/trailing whitespace is
        trimmed off each line.
        """
        return "\n".join(self.render())

    def snapshot(self) -> dict[str, Any]:
        """Return a JSON-serialisable snapshot of the current state.

        Intended for the ``GET /debug/pty`` endpoint and for structured
        logging of regex evaluation context.
        """
        return {
            "display": self.render(),
            "cursor": {"x": self._screen.cursor.x, "y": self._screen.cursor.y},
            "alt_screen": self._in_alt_screen,
            "columns": self._columns,
            "rows": self._rows,
        }
