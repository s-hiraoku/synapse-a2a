"""Tests for carriage return handling in TerminalController render buffer."""

from synapse.controller import TerminalController


def _make_controller(**kwargs):
    """Create a TerminalController with minimal config for render-buffer tests."""
    defaults = {
        "command": "echo",
        "idle_detection": {"strategy": "timeout", "timeout": 0.5},
        "agent_id": "synapse-test-8100",
        "agent_type": "test",
    }
    defaults.update(kwargs)
    return TerminalController(**defaults)


class TestRenderBufferCarriageReturn:
    """Tests for carriage-return overwrite behavior in the render buffer."""

    def test_cr_clears_stale_text(self):
        """Shorter replacement text should clear the old line tail."""
        ctrl = _make_controller()

        ctrl._append_output("長いテキスト\r短い".encode())

        assert ctrl.get_context() == "短い"

    def test_crlf_works_normally(self):
        """CRLF should still produce a normal newline in context."""
        ctrl = _make_controller()

        ctrl._append_output("行1\r\n行2".encode())

        assert ctrl.get_context() == "行1\n行2"

    def test_progress_bar_overwrite(self):
        """Progress updates should keep only the latest line content."""
        ctrl = _make_controller()

        ctrl._append_output(b"progress 40%\rprogress 80%")

        assert ctrl.get_context() == "progress 80%"

    def test_cr_does_not_affect_other_lines(self):
        """Clearing the current line should not modify previous lines."""
        ctrl = _make_controller()

        ctrl._append_output("行1\n長い行2\r短い".encode())

        assert ctrl.get_context() == "行1\n短い"

    def test_multiple_cr_in_sequence(self):
        """Multiple carriage returns should keep only the final overwrite."""
        ctrl = _make_controller()

        ctrl._append_output("最初\r中間\r最後".encode())

        assert ctrl.get_context() == "最後"

    def test_split_crlf_preserves_line(self):
        """CRLF split across two _append_output calls should preserve content."""
        ctrl = _make_controller()
        ctrl._append_output("行1\r".encode())
        ctrl._append_output("\n行2".encode())
        assert ctrl.get_context() == "行1\n行2"
