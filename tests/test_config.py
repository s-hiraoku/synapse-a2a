"""Tests for synapse/config.py constants."""

import pytest

from synapse.config import (
    AGENT_WAIT_TIMEOUT,
    API_RESPONSE_CONTEXT_SIZE,
    COMPLETED_TASK_STATES,
    CONTEXT_RECENT_SIZE,
    IDENTITY_WAIT_TIMEOUT,
    IDLE_CHECK_WINDOW,
    OUTPUT_BUFFER_MAX,
    OUTPUT_IDLE_THRESHOLD,
    PORT_CHECK_TIMEOUT,
    POST_WRITE_IDLE_DELAY,
    REQUEST_TIMEOUT,
    STARTUP_DELAY,
    TASK_POLL_INTERVAL,
    WRITE_PROCESSING_DELAY,
)


class TestTimeoutConstants:
    """Tests for timeout-related constants."""

    def test_startup_delay_is_positive_int(self):
        """STARTUP_DELAY should be a positive integer."""
        assert isinstance(STARTUP_DELAY, int)
        assert STARTUP_DELAY > 0

    def test_output_idle_threshold_is_positive_float(self):
        """OUTPUT_IDLE_THRESHOLD should be a positive float."""
        assert isinstance(OUTPUT_IDLE_THRESHOLD, float)
        assert OUTPUT_IDLE_THRESHOLD > 0

    def test_identity_wait_timeout_is_positive_int(self):
        """IDENTITY_WAIT_TIMEOUT should be a positive integer."""
        assert isinstance(IDENTITY_WAIT_TIMEOUT, int)
        assert IDENTITY_WAIT_TIMEOUT > 0

    def test_write_processing_delay_is_positive_float(self):
        """WRITE_PROCESSING_DELAY should be a positive float."""
        assert isinstance(WRITE_PROCESSING_DELAY, float)
        assert WRITE_PROCESSING_DELAY > 0

    def test_post_write_idle_delay_is_positive_float(self):
        """POST_WRITE_IDLE_DELAY should be a positive float."""
        assert isinstance(POST_WRITE_IDLE_DELAY, float)
        assert POST_WRITE_IDLE_DELAY > 0

    def test_request_timeout_is_tuple(self):
        """REQUEST_TIMEOUT should be a tuple of (connect, read) timeouts."""
        assert isinstance(REQUEST_TIMEOUT, tuple)
        assert len(REQUEST_TIMEOUT) == 2
        assert all(isinstance(t, int) and t > 0 for t in REQUEST_TIMEOUT)

    def test_port_check_timeout_is_positive_float(self):
        """PORT_CHECK_TIMEOUT should be a positive float."""
        assert isinstance(PORT_CHECK_TIMEOUT, float)
        assert PORT_CHECK_TIMEOUT > 0

    def test_agent_wait_timeout_is_positive_int(self):
        """AGENT_WAIT_TIMEOUT should be a positive integer."""
        assert isinstance(AGENT_WAIT_TIMEOUT, int)
        assert AGENT_WAIT_TIMEOUT > 0

    def test_task_poll_interval_is_positive_float(self):
        """TASK_POLL_INTERVAL should be a positive float."""
        assert isinstance(TASK_POLL_INTERVAL, float)
        assert TASK_POLL_INTERVAL > 0


class TestBufferSizeConstants:
    """Tests for buffer size constants."""

    def test_output_buffer_max_is_positive_int(self):
        """OUTPUT_BUFFER_MAX should be a positive integer."""
        assert isinstance(OUTPUT_BUFFER_MAX, int)
        assert OUTPUT_BUFFER_MAX > 0

    def test_idle_check_window_is_positive_int(self):
        """IDLE_CHECK_WINDOW should be a positive integer."""
        assert isinstance(IDLE_CHECK_WINDOW, int)
        assert IDLE_CHECK_WINDOW > 0

    def test_context_recent_size_is_positive_int(self):
        """CONTEXT_RECENT_SIZE should be a positive integer."""
        assert isinstance(CONTEXT_RECENT_SIZE, int)
        assert CONTEXT_RECENT_SIZE > 0

    def test_api_response_context_size_is_positive_int(self):
        """API_RESPONSE_CONTEXT_SIZE should be a positive integer."""
        assert isinstance(API_RESPONSE_CONTEXT_SIZE, int)
        assert API_RESPONSE_CONTEXT_SIZE > 0

    def test_idle_check_window_lte_output_buffer(self):
        """IDLE_CHECK_WINDOW should not exceed OUTPUT_BUFFER_MAX."""
        assert IDLE_CHECK_WINDOW <= OUTPUT_BUFFER_MAX

    def test_api_response_context_size_lte_context_recent(self):
        """API_RESPONSE_CONTEXT_SIZE should not exceed CONTEXT_RECENT_SIZE."""
        assert API_RESPONSE_CONTEXT_SIZE <= CONTEXT_RECENT_SIZE


class TestCompletedTaskStates:
    """Tests for COMPLETED_TASK_STATES."""

    def test_is_frozenset(self):
        """COMPLETED_TASK_STATES should be a frozenset (immutable)."""
        assert isinstance(COMPLETED_TASK_STATES, frozenset)

    def test_contains_expected_states(self):
        """Should contain completed, failed, and canceled states."""
        assert "completed" in COMPLETED_TASK_STATES
        assert "failed" in COMPLETED_TASK_STATES
        assert "canceled" in COMPLETED_TASK_STATES

    def test_does_not_contain_working_states(self):
        """Should not contain active/working states."""
        assert "submitted" not in COMPLETED_TASK_STATES
        assert "working" not in COMPLETED_TASK_STATES
        assert "pending" not in COMPLETED_TASK_STATES

    def test_immutable(self):
        """COMPLETED_TASK_STATES should be immutable."""
        with pytest.raises(AttributeError):
            COMPLETED_TASK_STATES.add("new_state")  # type: ignore[attr-defined]


class TestConstantRelationships:
    """Tests for relationships between constants."""

    def test_startup_delay_less_than_identity_wait(self):
        """STARTUP_DELAY should be less than IDENTITY_WAIT_TIMEOUT."""
        assert STARTUP_DELAY < IDENTITY_WAIT_TIMEOUT

    def test_write_delay_less_than_post_write_delay(self):
        """WRITE_PROCESSING_DELAY should be less than POST_WRITE_IDLE_DELAY."""
        assert WRITE_PROCESSING_DELAY < POST_WRITE_IDLE_DELAY

    def test_poll_interval_reasonable(self):
        """TASK_POLL_INTERVAL should be reasonable (< 5s)."""
        assert TASK_POLL_INTERVAL < 5.0

    def test_request_timeout_reasonable(self):
        """REQUEST_TIMEOUT values should be reasonable."""
        connect_timeout, read_timeout = REQUEST_TIMEOUT
        assert connect_timeout <= 10  # Connect should be quick
        assert read_timeout <= 60  # Read can be longer
