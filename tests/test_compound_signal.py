"""Tests for compound signal status detection (#314) and WAITING false positive fix (#140)."""

import threading
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from synapse.config import TASK_PROTECTION_TIMEOUT, WAITING_EXPIRY_SECONDS
from synapse.controller import TerminalController

PROFILES_DIR = Path(__file__).resolve().parent.parent / "synapse" / "profiles"


def _make_controller(**kwargs):
    """Create a TerminalController with minimal config for testing."""
    defaults = {
        "command": "echo",
        "idle_detection": {"strategy": "timeout", "timeout": 0.5},
        "agent_id": "synapse-test-8100",
        "agent_type": "test",
    }
    defaults.update(kwargs)
    ctrl = TerminalController(**defaults)
    # Simulate running state for status transitions
    ctrl.running = True
    ctrl.status = "PROCESSING"
    ctrl._last_output_time = time.time()
    return ctrl


# ============================================================
# Compound Signal Tests (#314)
# ============================================================


class TestCompoundSignalTaskActive:
    """Tests for task_active flag suppressing premature READY transitions."""

    def test_task_active_suppresses_ready_transition(self):
        """When task_active=True and PTY is idle, status should remain PROCESSING."""
        ctrl = _make_controller()
        ctrl.set_task_active()

        # Simulate idle state (no output for longer than threshold)
        ctrl._last_output_time = time.time() - 10.0
        ctrl._check_idle_state(b"")

        assert ctrl.status == "PROCESSING"

    def test_task_active_timeout_allows_ready(self):
        """After protection timeout expires, READY transition should be allowed."""
        ctrl = _make_controller(
            idle_detection={
                "strategy": "timeout",
                "timeout": 0.1,
                "task_protection_timeout": 0.2,
            }
        )
        ctrl.set_task_active()

        # Set task_active_since to past (beyond protection timeout)
        ctrl._task_active_since = time.time() - 1.0

        # Simulate idle
        ctrl._last_output_time = time.time() - 10.0
        ctrl._check_idle_state(b"")

        assert ctrl.status == "READY"

    def test_set_task_active_sets_count_and_timestamp(self):
        """set_task_active() should increment count and record timestamp."""
        ctrl = _make_controller()
        before = time.time()
        ctrl.set_task_active()

        assert ctrl._task_active_count == 1
        assert ctrl._task_active_since is not None
        assert ctrl._task_active_since >= before

        # Second call increments further
        ctrl.set_task_active()
        assert ctrl._task_active_count == 2

    def test_clear_task_active_decrements_count(self):
        """clear_task_active() should decrement count; clears timestamp at 0."""
        ctrl = _make_controller()
        ctrl.set_task_active()
        ctrl.set_task_active()

        ctrl.clear_task_active()
        assert ctrl._task_active_count == 1
        assert ctrl._task_active_since is not None  # Still active

        ctrl.clear_task_active()
        assert ctrl._task_active_count == 0
        assert ctrl._task_active_since is None

    def test_clear_task_active_floor_at_zero(self):
        """clear_task_active() should not go below 0."""
        ctrl = _make_controller()
        ctrl.clear_task_active()  # No prior set
        assert ctrl._task_active_count == 0

    def test_done_state_unaffected_by_task_active(self):
        """DONE state should not be affected by task_active flag."""
        ctrl = _make_controller()
        ctrl.set_task_active()
        ctrl.set_done()

        assert ctrl.status == "DONE"

    def test_waiting_unaffected_by_task_active(self):
        """WAITING detection should not be blocked by task_active."""
        ctrl = _make_controller(
            waiting_detection={
                "regex": r"\[Y/n\]",
                "require_idle": False,
                "waiting_expiry": 60,
            }
        )
        ctrl.set_task_active()

        # Inject WAITING pattern into new_data
        new_data = b"Do you want to continue? [Y/n]"
        ctrl._append_output(new_data)
        ctrl._last_output_time = time.time() - 10.0
        ctrl._check_idle_state(new_data)

        assert ctrl.status == "WAITING"


class TestCompoundSignalFileLocks:
    """Tests for file lock detection suppressing READY transitions."""

    def test_file_locks_suppress_ready_transition(self):
        """When file locks are held, READY transition should be suppressed."""
        ctrl = _make_controller()

        # Mock FileSafetyManager
        mock_fsm = MagicMock()
        mock_fsm.list_locks.return_value = [
            {"file_path": "/tmp/test.py", "agent_name": "synapse-test-8100"}
        ]
        ctrl.set_file_safety_manager(mock_fsm)

        # Simulate idle
        ctrl._last_output_time = time.time() - 10.0
        ctrl._check_idle_state(b"")

        assert ctrl.status == "PROCESSING"

    def test_no_file_locks_allows_ready(self):
        """When no file locks, READY transition should proceed normally."""
        ctrl = _make_controller(idle_detection={"strategy": "timeout", "timeout": 0.1})

        mock_fsm = MagicMock()
        mock_fsm.list_locks.return_value = []
        ctrl.set_file_safety_manager(mock_fsm)

        # Simulate idle
        ctrl._last_output_time = time.time() - 10.0
        ctrl._check_idle_state(b"")

        assert ctrl.status == "READY"

    def test_no_file_safety_manager_allows_ready(self):
        """When no FileSafetyManager is set, READY transition should proceed."""
        ctrl = _make_controller(idle_detection={"strategy": "timeout", "timeout": 0.1})

        # No file_safety_manager set
        ctrl._last_output_time = time.time() - 10.0
        ctrl._check_idle_state(b"")

        assert ctrl.status == "READY"


class TestCompoundSignalCombined:
    """Tests for combined compound signal behavior."""

    def test_task_active_and_file_locks_both_suppress(self):
        """Both signals active — PROCESSING should be maintained."""
        ctrl = _make_controller()
        ctrl.set_task_active()

        mock_fsm = MagicMock()
        mock_fsm.list_locks.return_value = [{"file_path": "/tmp/x.py"}]
        ctrl.set_file_safety_manager(mock_fsm)

        ctrl._last_output_time = time.time() - 10.0
        ctrl._check_idle_state(b"")

        assert ctrl.status == "PROCESSING"

    def test_protection_methods_are_threadsafe(self):
        """set/clear_task_active should be safe to call from multiple threads."""
        ctrl = _make_controller()
        errors = []

        def toggle():
            try:
                for _ in range(100):
                    ctrl.set_task_active()
                    ctrl.clear_task_active()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=toggle) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        # Final state should be cleared (each thread does equal set/clear)
        assert ctrl._task_active_count == 0


# ============================================================
# WAITING False Positive Fix Tests (#140)
# ============================================================


class TestWaitingFreshOutput:
    """Tests for WAITING detection using only fresh output data."""

    def test_waiting_only_matches_fresh_output(self):
        """WAITING should only trigger from new_data, not old buffer content."""
        ctrl = _make_controller(
            waiting_detection={
                "regex": r"\[Y/n\]",
                "require_idle": False,
                "waiting_expiry": 60,
            }
        )

        # Old buffer has the pattern, but new_data does not
        ctrl.output_buffer = b"Continue? [Y/n] yes\nWorking on task..."
        ctrl._last_output_time = time.time() - 10.0

        new_data = b"Still processing output here"
        ctrl._append_output(new_data)
        ctrl._check_idle_state(new_data)

        # Should NOT be WAITING since new_data doesn't contain the pattern
        assert ctrl.status != "WAITING"

    def test_waiting_clears_when_new_output_arrives(self):
        """WAITING should clear when pattern is gone from buffer and expiry passed."""
        ctrl = _make_controller(
            idle_detection={"strategy": "timeout", "timeout": 0.1},
            waiting_detection={
                "regex": r"\[Y/n\]",
                "require_idle": False,
                "waiting_expiry": 0.1,  # Short for testing
            },
        )

        # First: trigger WAITING with pattern data
        waiting_data = b"Do you want to continue? [Y/n]"
        ctrl._append_output(waiting_data)
        ctrl._last_output_time = time.time() - 10.0
        ctrl._check_idle_state(waiting_data)
        assert ctrl.status == "WAITING"

        # Overwrite buffer with non-pattern output (pattern no longer on screen)
        ctrl.output_buffer = b"Processing new task now... done."
        # Expire the waiting pattern timestamp
        ctrl._waiting_pattern_time = time.time() - 1.0
        ctrl._last_output_time = time.time() - 10.0
        ctrl._check_idle_state(b"")

        # Pattern gone from buffer + expired → should transition to READY
        assert ctrl.status == "READY"

    def test_waiting_expires_after_timeout(self):
        """WAITING should auto-expire after waiting_expiry seconds when pattern gone."""
        ctrl = _make_controller(
            idle_detection={"strategy": "timeout", "timeout": 0.1},
            waiting_detection={
                "regex": r"\[Y/n\]",
                "require_idle": False,
                "waiting_expiry": 0.1,  # Very short for testing
            },
        )

        # Trigger WAITING
        waiting_data = b"Continue? [Y/n]"
        ctrl._append_output(waiting_data)
        ctrl._last_output_time = time.time() - 10.0
        ctrl._check_idle_state(waiting_data)
        assert ctrl.status == "WAITING"

        # Clear buffer (pattern no longer visible) and set pattern time to past
        ctrl.output_buffer = b"New output without pattern"
        ctrl._waiting_pattern_time = time.time() - 1.0
        ctrl._last_output_time = time.time() - 10.0

        # Check again — pattern gone from buffer + expired → should not be WAITING
        ctrl._check_idle_state(b"")
        assert ctrl.status != "WAITING"

    def test_waiting_persists_when_pattern_still_in_buffer(self):
        """WAITING should persist past expiry if pattern is still visible in buffer."""
        ctrl = _make_controller(
            idle_detection={"strategy": "timeout", "timeout": 0.1},
            waiting_detection={
                "regex": r"\[Y/n\]",
                "require_idle": False,
                "waiting_expiry": 0.1,
            },
        )

        # Trigger WAITING
        waiting_data = b"Continue? [Y/n]"
        ctrl._append_output(waiting_data)
        ctrl._last_output_time = time.time() - 10.0
        ctrl._check_idle_state(waiting_data)
        assert ctrl.status == "WAITING"

        # Pattern is still in buffer but expiry has passed
        ctrl._waiting_pattern_time = time.time() - 1.0
        ctrl._last_output_time = time.time() - 10.0
        # Buffer still contains pattern
        ctrl._check_idle_state(b"")

        # Should still be WAITING (buffer tail re-check refreshes timestamp)
        assert ctrl.status == "WAITING"

    def test_waiting_detection_enabled_in_claude(self):
        """Claude profile should have WAITING detection enabled."""
        from pathlib import Path

        import yaml

        profile_path = (
            Path(__file__).resolve().parent.parent
            / "synapse"
            / "profiles"
            / "claude.yaml"
        )
        with open(profile_path) as f:
            profile = yaml.safe_load(f)

        # After fix, waiting_detection should be enabled (not commented out)
        assert "waiting_detection" in profile
        assert "regex" in profile["waiting_detection"]
        assert "waiting_expiry" in profile["waiting_detection"]


# ============================================================
# Per-Agent WAITING Pattern Accuracy Tests
# ============================================================

# Load regex patterns directly from YAML profiles to prevent drift.
# Tests use require_idle=False to isolate regex matching from timing.


def _load_profile_regex(agent: str) -> str:
    with open(PROFILES_DIR / f"{agent}.yaml") as f:
        return yaml.safe_load(f)["waiting_detection"]["regex"]


def _check_pattern(regex: str, text: str) -> bool:
    ctrl = _make_controller(
        waiting_detection={"regex": regex, "require_idle": False, "waiting_expiry": 60}
    )
    return ctrl._check_waiting_state(text.encode("utf-8"))


# fmt: off
WAITING_POSITIVE_CASES = [
    # Gemini CLI — Ink TUI with ● selector
    ("gemini", "● 1. Allow once"),
    ("gemini", "Action Required"),
    ("gemini", "Allow once"),
    ("gemini", "Allow for this session"),
    ("gemini", "Allow for this file in all future sessions"),
    ("gemini", "No, suggest changes (esc)"),
    ("gemini", "\x1b[32m● 1. Allow once\x1b[0m"),
    # Codex CLI — ratatui TUI with › selector
    ("codex", "› 1. Yes, proceed (y)"),
    ("codex", "Yes, proceed"),
    ("codex", "Yes, and don't ask again"),
    ("codex", "No, and tell Codex what to do differently"),
    ("codex", "Press enter to confirm or esc to cancel"),
    ("codex", "\x1b[0m› 1. Yes, proceed\x1b[0m"),
    # Copilot CLI — Ink TUI with numbered selection
    ("copilot", "  1. Yes"),
    ("copilot", "  2. Yes, and approve touch for the rest of the running session"),
    ("copilot", "  3. No, and tell Copilot what to do differently (Esc)"),
    ("copilot", "[y/N]"),
    # OpenCode — Bubble Tea TUI with horizontal button bar
    ("opencode", "Permission Required"),
    ("opencode", "Allow (a)"),
    ("opencode", "Allow for session (s)"),
    ("opencode", "Deny (d)"),
    ("opencode", "╭─ Permission Required ─╮"),
    ("opencode", "\x1b[1mPermission Required\x1b[0m"),
]

WAITING_NEGATIVE_CASES = [
    # Gemini — should not match normal output or plain numbered lists
    ("gemini", "Generating code..."),
    ("gemini", "1. First item in a list"),
    # Codex — should not match plain numbered output
    ("codex", "  1. Some numbered output"),
    ("codex", "Working on your request..."),
    # Copilot — should not match normal processing output
    ("copilot", "Working on task..."),
    # OpenCode — old patterns must NOT match; also guard against partial matches
    ("opencode", "  1. First item"),
    ("opencode", "[y/N]"),
    ("opencode", "Permission denied: /etc/shadow"),
    ("opencode", "Processing your request..."),
]
# fmt: on


class TestPerAgentWaitingPatterns:
    """Verify that each profile's deployed regex matches actual approval prompts
    and does not false-positive on normal output.

    Regex is loaded from YAML profiles at test time to prevent test/profile drift.
    """

    @pytest.mark.parametrize(
        "agent,text",
        WAITING_POSITIVE_CASES,
        ids=[f"{a}-{t[:40]}" for a, t in WAITING_POSITIVE_CASES],
    )
    def test_pattern_matches(self, agent, text):
        regex = _load_profile_regex(agent)
        assert _check_pattern(regex, text) is True

    @pytest.mark.parametrize(
        "agent,text",
        WAITING_NEGATIVE_CASES,
        ids=[f"{a}-{t[:40]}" for a, t in WAITING_NEGATIVE_CASES],
    )
    def test_pattern_no_false_positive(self, agent, text):
        regex = _load_profile_regex(agent)
        assert _check_pattern(regex, text) is False


class TestWaitingExpiryConfig:
    """Tests for waiting_expiry configuration."""

    def test_default_waiting_expiry(self):
        """Default waiting_expiry should come from config constant."""
        ctrl = _make_controller(
            waiting_detection={
                "regex": r"\[Y/n\]",
                "require_idle": True,
            }
        )
        assert ctrl._waiting_expiry == WAITING_EXPIRY_SECONDS

    def test_custom_waiting_expiry(self):
        """Custom waiting_expiry should override default."""
        ctrl = _make_controller(
            waiting_detection={
                "regex": r"\[Y/n\]",
                "require_idle": True,
                "waiting_expiry": 20.0,
            }
        )
        assert ctrl._waiting_expiry == 20.0


class TestTaskProtectionTimeout:
    """Tests for task protection timeout configuration."""

    def test_default_task_protection_timeout(self):
        """Default task_protection_timeout should come from config."""
        ctrl = _make_controller()
        assert ctrl._task_protection_timeout == TASK_PROTECTION_TIMEOUT

    def test_custom_task_protection_timeout(self):
        """Custom task_protection_timeout from idle_detection config."""
        ctrl = _make_controller(
            idle_detection={
                "strategy": "timeout",
                "timeout": 0.5,
                "task_protection_timeout": 15.0,
            }
        )
        assert ctrl._task_protection_timeout == 15.0


class TestConfigConstants:
    """Tests for new config constants."""

    def test_task_protection_timeout_value(self):
        """TASK_PROTECTION_TIMEOUT should be 30.0 seconds."""
        assert TASK_PROTECTION_TIMEOUT == 30.0

    def test_waiting_expiry_seconds_value(self):
        """WAITING_EXPIRY_SECONDS should be 10.0 seconds."""
        assert WAITING_EXPIRY_SECONDS == 10.0
