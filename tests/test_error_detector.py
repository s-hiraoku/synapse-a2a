"""Tests for error_detector module."""

from synapse.error_detector import (
    detect_error,
    detect_task_status,
    is_input_required,
)

# ============================================================
# Error Detection Tests
# ============================================================


class TestDetectError:
    """Test error pattern detection."""

    def test_detect_command_not_found(self):
        """Should detect 'command not found' error."""
        output = "bash: foo: command not found"
        error = detect_error(output)

        assert error is not None
        assert error.code == "COMMAND_NOT_FOUND"
        assert isinstance(error.data, dict)
        assert "command not found" in error.data["context"].lower()

    def test_detect_permission_denied(self):
        """Should detect 'permission denied' error."""
        output = "Error: Permission denied when accessing /etc/shadow"
        error = detect_error(output)

        assert error is not None
        assert error.code == "PERMISSION_DENIED"

    def test_detect_file_not_found(self):
        """Should detect 'no such file or directory' error."""
        output = "cat: /nonexistent: No such file or directory"
        error = detect_error(output)

        assert error is not None
        assert error.code == "FILE_NOT_FOUND"

    def test_detect_connection_refused(self):
        """Should detect connection refused error."""
        output = "curl: (7) Failed to connect: Connection refused"
        error = detect_error(output)

        assert error is not None
        assert error.code == "CONNECTION_REFUSED"

    def test_detect_timeout(self):
        """Should detect timeout error."""
        output = "Request timed out after 30 seconds"
        error = detect_error(output)

        assert error is not None
        assert error.code == "TIMEOUT"

    def test_detect_agent_refused(self):
        """Should detect AI agent refusal patterns."""
        outputs = [
            "I cannot help with that request.",
            "I'm unable to perform this action.",
            "I can't access that information.",
        ]

        for output in outputs:
            error = detect_error(output)
            assert error is not None, f"Failed to detect: {output}"
            assert error.code == "AGENT_REFUSED"

    def test_detect_generic_error(self):
        """Should detect generic error patterns."""
        output = "Error: Something went wrong during processing"
        error = detect_error(output)

        assert error is not None
        assert error.code == "CLI_ERROR"

    def test_detect_failed(self):
        """Should detect 'failed' pattern."""
        output = "Build failed: Missing dependencies"
        error = detect_error(output)

        assert error is not None
        assert error.code == "EXECUTION_FAILED"

    def test_detect_rate_limit(self):
        """Should detect rate limit errors."""
        output = "API Error: Rate limit exceeded. Please wait."
        error = detect_error(output)

        assert error is not None
        assert error.code == "RATE_LIMITED"

    def test_detect_auth_error(self):
        """Should detect authentication errors."""
        output = "Error: Authentication failed. Invalid token."
        error = detect_error(output)

        assert error is not None
        assert error.code == "AUTH_ERROR"

    def test_no_error_in_normal_output(self):
        """Should not detect error in normal output."""
        output = """
        Processing your request...
        File created successfully.
        All tests passed.
        """
        error = detect_error(output)
        assert error is None

    def test_no_error_in_empty_output(self):
        """Should handle empty output."""
        assert detect_error("") is None
        assert detect_error(None) is None

    def test_error_context_captured(self):
        """Should capture context around error."""
        output = "Some text before. Error: Something went wrong. Some text after."
        error = detect_error(output)

        assert error is not None
        assert error.data is not None
        assert "context" in error.data
        # Context should include surrounding text
        assert "Error:" in error.data["context"]


# ============================================================
# Task Status Detection Tests
# ============================================================


class TestDetectTaskStatus:
    """Test task status determination."""

    def test_failed_status_on_error(self):
        """Should return 'failed' status when error detected."""
        output = "Error: Something went wrong with exit code 1"
        status, error = detect_task_status(output)

        assert status == "failed"
        assert error is not None
        assert error.code == "CLI_ERROR"

    def test_completed_status_on_success(self):
        """Should return 'completed' status on normal output."""
        output = "Task completed successfully!"
        status, error = detect_task_status(output)

        assert status == "completed"
        assert error is None

    def test_failed_with_error_details(self):
        """Should return error details on failure."""
        output = "fatal: not a git repository"
        status, error = detect_task_status(output)

        assert status == "failed"
        assert error is not None
        assert error.code == "FATAL_ERROR"
        assert error.data is not None


# ============================================================
# Input Required Detection Tests
# ============================================================


class TestIsInputRequired:
    """Test input required detection."""

    def test_detect_question_mark(self):
        """Should detect question ending."""
        output = "Do you want to continue?"
        assert is_input_required(output) is True

    def test_detect_yn_prompt(self):
        """Should detect [y/n] prompt."""
        output = "Proceed with installation? [y/n]"
        assert is_input_required(output) is True

    def test_detect_yes_no_prompt(self):
        """Should detect [yes/no] prompt."""
        output = "Are you sure? [yes/no]"
        assert is_input_required(output) is True

    def test_detect_enter_prompt(self):
        """Should detect 'Enter X:' prompt."""
        output = "Enter your password:"
        assert is_input_required(output) is True

    def test_detect_please_provide(self):
        """Should detect 'Please provide' prompt."""
        output = "Please provide the API key"
        assert is_input_required(output) is True

    def test_detect_waiting_for_input(self):
        """Should detect 'waiting for input' prompt."""
        output = "Waiting for input..."
        assert is_input_required(output) is True

    def test_detect_press_enter(self):
        """Should detect 'Press enter' prompt."""
        output = "Press enter to continue..."
        assert is_input_required(output) is True

    def test_detect_continue_prompt(self):
        """Should detect 'Continue?' prompt."""
        output = "Would you like to continue?"
        assert is_input_required(output) is True

    def test_no_input_required_normal(self):
        """Should not detect input required on normal output."""
        output = "Processing complete. Files saved."
        assert is_input_required(output) is False

    def test_no_input_required_empty(self):
        """Should handle empty output."""
        assert is_input_required("") is False

    def test_checks_last_lines_only(self):
        """Should only check last few lines for prompts."""
        output = """
        Some question in history?
        More processing...
        Done.
        """
        # Question is not in last lines
        assert is_input_required(output) is False


# ============================================================
# Edge Cases
# ============================================================


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_long_output_only_checks_recent(self):
        """Should only analyze recent output for errors."""
        # Error in the beginning, but success at the end
        output = "Error: Initial failure\n" + "..." * 1000 + "\nSuccess: All done"
        error = detect_error(output)
        # Should not detect old error
        assert error is None

    def test_case_insensitive_detection(self):
        """Should detect errors case-insensitively."""
        outputs = [
            "ERROR: Something failed",
            "error: Something failed",
            "Error: Something failed",
        ]
        for output in outputs:
            error = detect_error(output)
            assert error is not None, f"Failed for: {output}"

    def test_pattern_priority(self):
        """More specific patterns should take precedence."""
        output = "Error: Command not found: foo"
        error = detect_error(output)
        # Should match "command not found" before generic "error:"
        assert error is not None
        assert error.code == "COMMAND_NOT_FOUND"
