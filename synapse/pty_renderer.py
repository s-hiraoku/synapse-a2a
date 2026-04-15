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

from typing import Any

import pyte

_ALT_SCREEN_ENTER = "\x1b[?1049h"
_ALT_SCREEN_LEAVE = "\x1b[?1049l"


class PtyRenderer:
    """Feed raw PTY bytes and read back the rendered terminal state."""

    def __init__(self, columns: int = 80, rows: int = 24) -> None:
        self._columns = columns
        self._rows = rows
        self._screen = pyte.Screen(columns, rows)
        self._stream = pyte.Stream(self._screen)
        self._in_alt_screen = False
        self._saved_display: list[str] | None = None

    @property
    def columns(self) -> int:
        return self._columns

    @property
    def rows(self) -> int:
        return self._rows

    @property
    def in_alt_screen(self) -> bool:
        return self._in_alt_screen

    @property
    def cursor(self) -> tuple[int, int]:
        return (self._screen.cursor.x, self._screen.cursor.y)

    def feed(self, data: bytes | str) -> None:
        """Feed a chunk of PTY output into the virtual screen.

        Accepts either bytes (typical output from ``os.read``) or a
        pre-decoded string. Invalid UTF-8 is tolerated via replacement.
        """
        text = (
            data.decode("utf-8", errors="replace") if isinstance(data, bytes) else data
        )
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
        return [line.rstrip() for line in self._screen.display]

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
