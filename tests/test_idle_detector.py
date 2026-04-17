"""Tests for extracted idle detection logic."""

import time

from synapse.idle_detector import IdleDetector
from synapse.pty_renderer import PtyRenderer


def test_pattern_detection_honors_startup_only_mode():
    detector = IdleDetector(
        idle_detection={
            "strategy": "hybrid",
            "pattern": "PROMPT:",
            "pattern_use": "startup_only",
            "timeout": 0.5,
        }
    )

    assert detector.check_pattern_idle(b"PROMPT: ", pattern_detected=False) is True
    assert detector.check_pattern_idle(b"PROMPT: ", pattern_detected=True) is False


def test_timeout_idle_requires_pattern_first_in_hybrid_mode():
    detector = IdleDetector(
        idle_detection={
            "strategy": "hybrid",
            "pattern": "PROMPT:",
            "timeout": 0.5,
        }
    )

    last_output_time = time.time() - 1.0

    assert (
        detector.check_timeout_idle(
            last_output_time=last_output_time,
            pattern_detected=False,
        )
        is False
    )
    assert (
        detector.check_timeout_idle(
            last_output_time=last_output_time,
            pattern_detected=True,
        )
        is True
    )


def test_waiting_detection_refreshes_visible_prompt_after_expiry():
    detector = IdleDetector(
        waiting_detection={
            "regex": r"Proceed\?",
            "idle_timeout": 0.5,
            "waiting_expiry": 0.1,
        }
    )

    waiting_pattern_time = time.time() - 0.2
    is_waiting, refreshed_time = detector.check_waiting_state(
        new_data=b"",
        output_buffer=b"\x1b[31mProceed?\x1b[0m",
        last_output_time=time.time() - 1.0,
        waiting_pattern_time=waiting_pattern_time,
    )

    assert is_waiting is True
    assert refreshed_time is not None
    assert refreshed_time > waiting_pattern_time


def test_waiting_detection_with_renderer_resolves_cursor_motion():
    """Regression for #572: ratatui-style cursor-motion overwrites
    previously produced garbled text like ``Working•Working•orking``
    that the waiting_detection regex could never match. When a
    PtyRenderer is injected, the regex should be evaluated against the
    rendered virtual screen instead of the raw byte stream."""
    renderer = PtyRenderer(columns=80, rows=24)
    detector = IdleDetector(
        waiting_detection={
            "regex": r"Proceed\?",
            "require_idle": False,
            "waiting_expiry": 30,
        },
        renderer=renderer,
    )

    # Cursor-home + "Working" twice, then a newline, then the real
    # prompt. strip_ansi would leave "WorkingWorkingProceed?" or worse
    # after SGR mangling; pyte resolves the overwrites.
    raw = b"\x1b[H" + b"Working" + b"\x1b[H" + b"Working" + b"\r\nProceed?"
    is_waiting, refreshed = detector.check_waiting_state(
        new_data=raw,
        output_buffer=raw,
        last_output_time=time.time() - 1.0,
        waiting_pattern_time=None,
    )

    assert is_waiting is True
    assert refreshed is not None


def test_waiting_detection_renderer_path_expiry_refresh():
    """With a renderer, expiry refresh uses the rendered screen as the
    source of truth. If the prompt is visible on the rendered screen,
    the WAITING state persists regardless of raw buffer state."""
    raw = b"\x1b[HProceed?"
    renderer = PtyRenderer(columns=80, rows=24)
    renderer.feed(raw)
    detector = IdleDetector(
        waiting_detection={
            "regex": r"Proceed\?",
            "require_idle": False,
            "waiting_expiry": 0.1,
        },
        renderer=renderer,
    )

    waiting_pattern_time = time.time() - 0.2
    is_waiting, refreshed = detector.check_waiting_state(
        new_data=b"",
        output_buffer=raw,
        last_output_time=time.time() - 1.0,
        waiting_pattern_time=waiting_pattern_time,
    )

    assert is_waiting is True
    assert refreshed is not None
    assert refreshed > waiting_pattern_time


def test_waiting_detection_renderer_path_clears_when_screen_gone():
    """Conversely, when the rendered screen no longer contains the
    waiting pattern, expiry should clear the WAITING state."""
    renderer = PtyRenderer(columns=80, rows=24)
    renderer.feed(b"idle prompt >")
    detector = IdleDetector(
        waiting_detection={
            "regex": r"Proceed\?",
            "require_idle": False,
            "waiting_expiry": 0.1,
        },
        renderer=renderer,
    )

    waiting_pattern_time = time.time() - 0.2
    is_waiting, refreshed = detector.check_waiting_state(
        new_data=b"",
        output_buffer=b"idle prompt >",
        last_output_time=time.time() - 1.0,
        waiting_pattern_time=waiting_pattern_time,
    )

    assert is_waiting is False
    assert refreshed is None


def test_waiting_detection_renderer_path_survives_garbled_raw_tail():
    """Core #572 scenario: raw tail is destroyed by cursor-motion
    overwrites but the rendered screen still shows the prompt.
    The renderer path should preserve WAITING."""
    renderer = PtyRenderer(columns=80, rows=24)
    # Feed cursor-home + repeated "Working" overwrites + prompt on row 2.
    # The raw bytes produce garbled strip_ansi output, but pyte resolves
    # the overwrites so the screen cleanly shows "Proceed?" on row 2.
    garbled_raw = (
        b"\x1b[H" + b"Working" * 10 + b"\x1b[H" + b"Working" * 10 + b"\x1b[2;1HProceed?"
    )
    renderer.feed(garbled_raw)

    detector = IdleDetector(
        waiting_detection={
            "regex": r"Proceed\?",
            "require_idle": False,
            "waiting_expiry": 0.1,
        },
        renderer=renderer,
    )

    # Raw tail is large enough that "Proceed?" falls outside the
    # last 512 bytes after strip_ansi — only the renderer can see it.
    big_raw = b"X" * 2048 + garbled_raw
    waiting_pattern_time = time.time() - 0.2
    is_waiting, refreshed = detector.check_waiting_state(
        new_data=b"",
        output_buffer=big_raw,
        last_output_time=time.time() - 1.0,
        waiting_pattern_time=waiting_pattern_time,
    )

    assert is_waiting is True
    assert refreshed is not None
    assert refreshed > waiting_pattern_time


def test_waiting_detection_without_renderer_uses_strip_ansi():
    """Backwards compatibility: when no renderer is injected the
    existing strip_ansi path must still work unchanged."""

    def strip_ansi(text: str) -> str:
        import re as _re

        return _re.sub(r"\x1b\[[0-9;?]*[a-zA-Z]", "", text)

    detector = IdleDetector(
        waiting_detection={
            "regex": r"Proceed\?",
            "require_idle": False,
        },
        strip_ansi_fn=strip_ansi,
    )

    is_waiting, refreshed = detector.check_waiting_state(
        new_data=b"\x1b[31mProceed?\x1b[0m",
        output_buffer=b"\x1b[31mProceed?\x1b[0m",
        last_output_time=time.time() - 1.0,
        waiting_pattern_time=None,
    )

    assert is_waiting is True


def test_done_state_remains_done_until_timeout_expires():
    detector = IdleDetector()

    decision = detector.determine_new_status(
        current_status="DONE",
        is_idle=True,
        is_waiting=False,
        done_time=time.time(),
        task_protection_active=False,
        has_file_locks=False,
    )

    assert decision.new_status == "DONE"
    assert decision.clear_done_time is False


def test_done_state_returns_ready_after_timeout_expires():
    detector = IdleDetector()

    decision = detector.determine_new_status(
        current_status="DONE",
        is_idle=True,
        is_waiting=False,
        done_time=time.time() - 10.0,
        task_protection_active=False,
        has_file_locks=False,
    )

    assert decision.new_status == "READY"
    assert decision.clear_done_time is True
