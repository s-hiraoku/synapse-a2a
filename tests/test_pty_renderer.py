"""Tests for synapse.pty_renderer.PtyRenderer.

Covers the #572 scenario: raw PTY bytes containing cursor-motion ANSI
sequences should be resolved against a virtual terminal screen so
downstream waiting_detection sees the *rendered* text, not the raw
byte stream (which previously came out garbled like
``Working•Working•orking•rking•kinging``).
"""

from __future__ import annotations

import pytest

from synapse.pty_renderer import PtyRenderer


class TestFeedAndRender:
    def test_plain_text_lines_are_preserved(self) -> None:
        r = PtyRenderer(columns=80, rows=24)
        r.feed(b"hello\r\nworld\r\n")
        lines = r.render()
        assert lines[0] == "hello"
        assert lines[1] == "world"

    def test_cursor_motion_overwrites_collapse_to_final_state(self) -> None:
        """Regression test for #572 root cause.

        Simulates ratatui-style repeated in-place updates: home-cursor
        then write "Working" twice. Old strip_ansi regex would leave
        both copies in the stream; pyte-backed rendering resolves them
        to a single final cell state.
        """
        r = PtyRenderer(columns=80, rows=24)
        r.feed(b"\x1b[H" + b"Working" + b"\x1b[H" + b"Working")
        lines = r.render()
        assert lines[0] == "Working"

    def test_feed_accepts_bytes_and_str(self) -> None:
        r = PtyRenderer(columns=80, rows=24)
        r.feed(b"alpha\r\n")
        r.feed("beta\r\n")
        assert r.render()[0] == "alpha"
        assert r.render()[1] == "beta"

    def test_invalid_utf8_does_not_crash(self) -> None:
        r = PtyRenderer(columns=80, rows=24)
        r.feed(b"hi\xff\xfe world")
        # Should not raise; replacement char or similar.
        lines = r.render()
        assert "hi" in lines[0]
        assert "world" in lines[0]

    def test_wide_char_stub_cell_overwrite_does_not_crash(self) -> None:
        """Regression test for #590.

        Writing a wide CJK character creates an empty continuation cell.
        Overwriting the first cell with a narrow character can leave that
        empty stub in pyte's buffer, and pyte.Screen.display raises
        IndexError when it indexes char[0] for that cell.
        """
        r = PtyRenderer(columns=10, rows=3)
        r.feed("漢\x1b[1Gx".encode())

        assert r.render_text().splitlines()[0] == "x"


class TestDisplayShape:
    def test_default_dimensions_match_constructor(self) -> None:
        r = PtyRenderer(columns=80, rows=24)
        lines = r.render()
        assert len(lines) == 24
        for line in lines:
            assert len(line) <= 80

    def test_custom_dimensions(self) -> None:
        r = PtyRenderer(columns=40, rows=10)
        lines = r.render()
        assert len(lines) == 10

    def test_render_lines_are_right_stripped(self) -> None:
        """Trailing whitespace in cells should be trimmed per line so
        regex searches don't trip on padding."""
        r = PtyRenderer(columns=80, rows=24)
        r.feed(b"hi\r\n")
        lines = r.render()
        assert lines[0] == "hi"


class TestRenderText:
    def test_render_text_joins_non_blank_lines(self) -> None:
        r = PtyRenderer(columns=80, rows=24)
        r.feed(b"one\r\ntwo\r\n\r\nthree\r\n")
        text = r.render_text()
        assert "one" in text
        assert "two" in text
        assert "three" in text

    def test_render_text_is_searchable_for_waiting_regex(self) -> None:
        """End-to-end: after feeding ratatui-style garbled bytes the
        rendered text must match a plain substring regex."""
        import re

        r = PtyRenderer(columns=80, rows=24)
        r.feed(b"\x1b[H" + b"Working" + b"\x1b[H" + b"Working")
        assert re.search(r"Working", r.render_text()) is not None


class TestAltScreen:
    def test_enter_alt_screen_resets_display(self) -> None:
        """DECSET 1049 (enter alt screen) should give a fresh canvas so
        the TUI overlay is what the regex sees, not whatever scrolled
        before it."""
        r = PtyRenderer(columns=80, rows=24)
        r.feed(b"pre-alt content\r\n")
        r.feed(b"\x1b[?1049h")
        r.feed(b"overlay content")
        lines = [line for line in r.render() if line]
        assert "pre-alt content" not in lines
        assert any("overlay content" in line for line in lines)

    def test_leave_alt_screen_restores_prior_display(self) -> None:
        """DECRST 1049 (leave alt screen) should restore the pre-alt
        content."""
        r = PtyRenderer(columns=80, rows=24)
        r.feed(b"pre-alt content\r\n")
        r.feed(b"\x1b[?1049h")
        r.feed(b"overlay content")
        r.feed(b"\x1b[?1049l")
        lines = [line for line in r.render() if line]
        assert any("pre-alt content" in line for line in lines)

    def test_alt_screen_flag_reflects_state(self) -> None:
        r = PtyRenderer(columns=80, rows=24)
        assert r.in_alt_screen is False
        r.feed(b"\x1b[?1049h")
        assert r.in_alt_screen is True
        r.feed(b"\x1b[?1049l")
        assert r.in_alt_screen is False


class TestCursor:
    def test_cursor_position_reported(self) -> None:
        r = PtyRenderer(columns=80, rows=24)
        r.feed(b"abc")
        assert r.cursor == (3, 0)

    def test_cursor_position_after_newline(self) -> None:
        r = PtyRenderer(columns=80, rows=24)
        r.feed(b"abc\r\n")
        assert r.cursor == (0, 1)


class TestSnapshot:
    def test_snapshot_returns_display_cursor_and_alt_flag(self) -> None:
        r = PtyRenderer(columns=80, rows=24)
        r.feed(b"hello")
        snap = r.snapshot()
        assert snap["display"][0] == "hello"
        assert snap["cursor"] == {"x": 5, "y": 0}
        assert snap["alt_screen"] is False
        assert snap["columns"] == 80
        assert snap["rows"] == 24


class TestUsageLimitCapture:
    """Regression fixture built from the real PTY bytes captured during
    the Step D diagnostic run (2026-04-15) where codex hit its OpenAI
    usage limit. The raw bytes contained cursor-motion sequences that
    strip_ansi collapsed into garbage like
    ``Working•Working•orking•rking•kinging``. With PtyRenderer the
    rendered display should contain the clean "usage limit" banner.
    """

    def test_renders_usage_limit_banner_cleanly(self) -> None:
        # Synthetic minimal reproduction: cursor home + repeated
        # "Working" overwrites + final banner line.
        frame = (
            b"\x1b[H"
            + b"Working"
            + b"\x1b[H"
            + b"Working"
            + b"\x1b[2;1H"
            + b"\xe2\x96\xa0 You've hit your usage limit. Upgrade to Pro"
        )
        r = PtyRenderer(columns=120, rows=24)
        r.feed(frame)
        text = r.render_text()
        assert "You've hit your usage limit" in text
        # And the Working spam must not still be visible as garbage:
        assert "Working•Working" not in text


@pytest.mark.parametrize(
    "columns,rows",
    [(80, 24), (120, 40), (200, 50)],
)
def test_constructor_dimensions_respected(columns: int, rows: int) -> None:
    r = PtyRenderer(columns=columns, rows=rows)
    snap = r.snapshot()
    assert snap["columns"] == columns
    assert snap["rows"] == rows


class TestIncrementalDecoding:
    def test_split_utf8_across_chunks(self) -> None:
        """Multi-byte UTF-8 split across os.read() calls must not
        produce replacement characters."""
        r = PtyRenderer(columns=80, rows=24)
        # '日' is U+65E5 = 3 bytes: e6 97 a5
        r.feed(b"\xe6\x97")
        r.feed(b"\xa5")
        assert "日" in r.render()[0]

    def test_split_csi_across_chunks(self) -> None:
        """Alt-screen marker split across two feed() calls must still
        be detected."""
        r = PtyRenderer(columns=80, rows=24)
        r.feed(b"primary")
        # Split \x1b[?1049h across two calls
        r.feed(b"\x1b[?10")
        r.feed(b"49hoverlay")
        assert r.in_alt_screen is True
        text = "\n".join(r.render())
        assert "overlay" in text
        assert "primary" not in text

    def test_complete_csi_not_held_back(self) -> None:
        """A complete CSI at the end of a chunk should not be deferred."""
        r = PtyRenderer(columns=80, rows=24)
        r.feed(b"hello\x1b[2;1Hworld")
        assert r.render()[1] == "world"
