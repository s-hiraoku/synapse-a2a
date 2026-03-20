"""Tests for strip_ansi() — ANSI escape sequence removal.

Fix #337: Codex agent sends raw PTY escape sequences (ANSI codes)
as A2A reply messages. strip_ansi() is applied in get_context() to
clean all downstream consumers (artifacts, history, replies).
"""

from __future__ import annotations

from synapse.controller import strip_ansi


class TestStripAnsi:
    """Tests for strip_ansi() function."""

    def test_no_ansi(self) -> None:
        """Plain text should pass through unchanged."""
        assert strip_ansi("hello world") == "hello world"

    def test_empty_string(self) -> None:
        """Empty string should return empty string."""
        assert strip_ansi("") == ""

    def test_sgr_color_codes(self) -> None:
        """SGR color/style codes like \\e[31m should be stripped."""
        assert strip_ansi("\x1b[31mred text\x1b[0m") == "red text"
        assert strip_ansi("\x1b[1;32mbold green\x1b[0m") == "bold green"

    def test_cursor_movement(self) -> None:
        """Cursor movement sequences (up, down, position) should be stripped."""
        assert strip_ansi("\x1b[2Ahello") == "hello"
        assert strip_ansi("\x1b[10;20Htext") == "text"

    def test_erase_sequences(self) -> None:
        """Erase line/screen sequences should be stripped."""
        assert strip_ansi("\x1b[2Jcleared") == "cleared"
        assert strip_ansi("\x1b[Kline") == "line"

    def test_bracketed_paste_mode(self) -> None:
        """Bracketed paste mode sequences (\\e[?2004h) should be stripped."""
        assert strip_ansi("\x1b[?2004h\x1b[?2004l") == ""

    def test_osc_sequences(self) -> None:
        """OSC sequences (title setting, hyperlinks) should be stripped."""
        # OSC terminated by BEL
        assert strip_ansi("\x1b]0;My Title\x07text") == "text"
        # OSC terminated by ST (ESC \\)
        assert (
            strip_ansi("\x1b]8;;https://example.com\x1b\\link\x1b]8;;\x1b\\") == "link"
        )

    def test_mixed_real_world(self) -> None:
        """Real-world PTY output with mixed sequences should be cleaned."""
        raw = "\x1b[?2004h\x1b[1;36m› \x1b[0mHello from codex\x1b[?2004l"
        assert strip_ansi(raw) == "› Hello from codex"

    def test_newline_preservation(self) -> None:
        """Newlines should be preserved while stripping ANSI."""
        raw = "\x1b[32mline1\x1b[0m\nline2\n\x1b[31mline3\x1b[0m"
        assert strip_ansi(raw) == "line1\nline2\nline3"

    def test_character_set_selection(self) -> None:
        """Character set selection sequences should be stripped."""
        assert strip_ansi("\x1b(Bhello\x1b)0") == "hello"

    def test_keypad_mode(self) -> None:
        """Keypad mode sequences should be stripped."""
        assert strip_ansi("\x1b=text\x1b>") == "text"


class TestGetContextStripsAnsi:
    """Integration test: get_context() should return ANSI-free text."""

    def test_get_context_strips_ansi(self) -> None:
        """get_context() should strip ANSI from render buffer content."""
        from unittest.mock import patch

        from synapse.controller import TerminalController

        with patch.object(TerminalController, "__init__", lambda self: None):
            ctrl = TerminalController.__new__(TerminalController)
            ctrl.lock = __import__("threading").Lock()
            ctrl._render_buffer = ["\x1b[31mred\x1b[0m", " plain"]

            result = ctrl.get_context()

        assert result == "red plain"
        assert "\x1b" not in result


class TestStripAnsiOrphanedFragments:
    """Tests for orphaned ANSI fragment cleanup (no leading ESC byte).

    When a TUI uses \\r to overwrite a line, \\x1b may be overwritten
    while the rest of the SGR sequence (e.g. [38;5;178m) remains.
    """

    def test_orphan_bracket_sgr(self) -> None:
        """[38;5;178m followed by text should leave only text."""
        assert strip_ansi("[38;5;178mhello") == "hello"

    def test_orphan_reset(self) -> None:
        """[0m should be removed entirely."""
        assert strip_ansi("[0m") == ""

    def test_real_world_diff_stat(self) -> None:
        """Real case: [38;5;178m(+233,-67) should yield (+233,-67)."""
        assert strip_ansi("[38;5;178m(+233,-67)") == "(+233,-67)"

    def test_bare_semicolon_sgr(self) -> None:
        """Bare 38;5;178m (no bracket) followed by non-alpha should be stripped."""
        assert strip_ansi("38;5;178m(+233,-67)") == "(+233,-67)"
        assert strip_ansi("38;5;178m ") == " "
        # Followed by alpha is intentionally kept (avoids false positives)
        assert strip_ansi("38;5;178mhello") == "38;5;178mhello"

    def test_no_false_positive_plain_text(self) -> None:
        """Plain text containing numbers and 'm' must not be altered."""
        # No semicolons — single number+m is not an SGR fragment
        assert strip_ansi("100m dash") == "100m dash"
        assert strip_ansi("ran 200m in 25s") == "ran 200m in 25s"
        # Preceded by alpha — not an orphaned fragment
        assert strip_ansi("item3m") == "item3m"
        # Followed by alpha — not an orphaned fragment
        assert strip_ansi("0mtest") == "0mtest"
        # Bracket after alpha is natural text, not an SGR fragment
        assert strip_ansi("see[3m above]") == "see[3m above]"
        # Bare [m] (no digits) should not match
        assert strip_ansi("[m]") == "[m]"

    def test_mixed_full_and_orphan(self) -> None:
        """Full ANSI sequences and orphaned fragments in the same string."""
        raw = "\x1b[1mbold\x1b[0m [38;5;178mcolored rest"
        assert strip_ansi(raw) == "bold colored rest"
