"""Regression tests for long-message file sanitization (#677).

Bug C route C: ``LongMessageStore.store_message`` was writing raw content
to ``/var/folders/.../synapse-a2a/messages/<id>-<ts>.txt`` without any
sanitization, so PTY scrape residue (ANSI escapes, status-bar fragments,
partial-render bytes) could leak into the long-message file path.

PRs #663 (route A) and #668 (route B) already apply ``strip_control_bytes``
at the parent placeholder and artifact persistence boundaries. This is
the symmetric fix at the long-message file boundary.
"""

from pathlib import Path

from synapse.long_message import LongMessageStore


def _store(tmp_path: Path) -> LongMessageStore:
    return LongMessageStore(message_dir=tmp_path / "messages", threshold=10)


def test_strips_csi_escape(tmp_path: Path) -> None:
    """ANSI CSI escapes (\\x1b[...m) must not appear in the stored file."""
    store = _store(tmp_path)
    file_path = store.store_message("task-001", "hello\x1b[31mred\x1b[0m world")

    written = file_path.read_text(encoding="utf-8")
    assert "\x1b" not in written
    assert written == "hellored world"


def test_strips_status_bar_residue(tmp_path: Path) -> None:
    """Codex status-bar / autosuggestion bytes must not survive."""
    store = _store(tmp_path)
    # Real-world residue observed in 2026-04-29 session: leading SGR fragment
    # plus a ``Ptmux;\\`` envelope wrapping a status-bar suggestion.
    raw = (
        "8;49mg\x07orking5\n"
        "Real reply content here.\n"
        "\x1bPtmux;\\ \xe2\x80\xba Run /review"
    )
    file_path = store.store_message("task-002", raw)

    written = file_path.read_text(encoding="utf-8")
    assert "\x07" not in written  # BEL stripped
    assert "\x1b" not in written  # ESC stripped
    assert "Real reply content here." in written


def test_preserves_normal_text(tmp_path: Path) -> None:
    """Plain text with newlines, tabs, and multibyte chars survives."""
    store = _store(tmp_path)
    raw = "multi\nline\ttext\n日本語の説明\n"
    file_path = store.store_message("task-003", raw)

    written = file_path.read_text(encoding="utf-8")
    assert written == raw


def test_strips_c0_control_bytes(tmp_path: Path) -> None:
    """C0 control bytes (NUL, BEL, etc) are stripped except TAB/LF."""
    store = _store(tmp_path)
    raw = "before\x00null\x07bell\tafter\nline2"
    file_path = store.store_message("task-004", raw)

    written = file_path.read_text(encoding="utf-8")
    assert "\x00" not in written
    assert "\x07" not in written
    assert "\t" in written  # TAB preserved
    assert "\n" in written  # LF preserved
    assert written == "beforenullbell\tafter\nline2"


def test_threshold_check_uses_original_length(tmp_path: Path) -> None:
    """needs_file_storage checks pre-sanitization length; sanitization
    happens only inside store_message. This test guards against accidentally
    short-circuiting needs_file_storage on already-stripped content (which
    would change the file-vs-inline decision)."""
    store = _store(tmp_path)
    raw_with_ansi = "x\x1b[31m" * 30  # ~150 chars; sanitized would be much shorter
    assert store.needs_file_storage(raw_with_ansi) is True

    file_path = store.store_message("task-005", raw_with_ansi)
    written = file_path.read_text(encoding="utf-8")
    assert "\x1b" not in written
    assert written == "x" * 30
