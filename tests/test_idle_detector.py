"""Tests for extracted idle detection logic."""

import time

from synapse.idle_detector import IdleDetector


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
