"""Tests for injection observability logging in TerminalController.

Validates that _send_identity_instruction() emits structured log messages
at each stage: RESOLVE, DECISION, DELIVER, and SUMMARY.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

from synapse.controller import TerminalController

# ============================================================
# Helpers
# ============================================================


def _make_controller(
    *,
    agent_id: str = "synapse-claude-8100",
    agent_type: str = "claude",
    skip_initial_instructions: bool = False,
    input_ready_pattern: str | None = None,
    master_fd: int | None = None,
    name: str | None = None,
    role: str | None = None,
) -> TerminalController:
    """Build a TerminalController with mocked registry for unit testing."""
    registry = MagicMock()
    registry.update_status.return_value = True

    ctrl = TerminalController(
        command="echo",
        registry=registry,
        agent_id=agent_id,
        agent_type=agent_type,
        skip_initial_instructions=skip_initial_instructions,
        input_ready_pattern=input_ready_pattern,
        name=name,
        role=role,
    )
    ctrl.running = True
    if master_fd is not None:
        ctrl.master_fd = master_fd
    return ctrl


# ============================================================
# RESOLVE logs
# ============================================================


class TestResolveLog:
    """INJECT/RESOLVE should report which instruction files were found."""

    def test_resolve_log_with_default_fallback(self, caplog) -> None:
        """When no agent-specific file, fallback=default should be logged."""
        ctrl = _make_controller(master_fd=5)

        mock_settings = MagicMock()
        mock_settings.get_instruction_file_paths.return_value = [".synapse/default.md"]
        mock_settings.instructions = {"default": "default.md"}

        with (
            caplog.at_level(logging.INFO),
            patch("synapse.controller.get_settings", return_value=mock_settings),
            patch("synapse.controller.format_a2a_message", return_value="msg"),
            patch.object(ctrl, "write", return_value=True),
            patch("time.sleep"),
        ):
            ctrl._send_identity_instruction()

        resolve_logs = [
            r
            for r in caplog.records
            if "INJECT/RESOLVE" in r.message and "synapse-claude-8100" in r.message
        ]
        assert len(resolve_logs) == 1
        assert "fallback=default" in resolve_logs[0].message
        assert "agent_type=claude" in resolve_logs[0].message

    def test_resolve_log_with_agent_specific(self, caplog) -> None:
        """When agent-specific file exists, fallback=none should be logged."""
        ctrl = _make_controller(master_fd=5)

        mock_settings = MagicMock()
        mock_settings.get_instruction_file_paths.return_value = [".synapse/claude.md"]
        mock_settings.instructions = {"claude": "claude.md", "default": "default.md"}

        with (
            caplog.at_level(logging.INFO),
            patch("synapse.controller.get_settings", return_value=mock_settings),
            patch("synapse.controller.format_a2a_message", return_value="msg"),
            patch.object(ctrl, "write", return_value=True),
            patch("time.sleep"),
        ):
            ctrl._send_identity_instruction()

        resolve_logs = [
            r
            for r in caplog.records
            if "INJECT/RESOLVE" in r.message and "synapse-claude-8100" in r.message
        ]
        assert len(resolve_logs) == 1
        assert "fallback=none" in resolve_logs[0].message


# ============================================================
# DECISION logs
# ============================================================


class TestDecisionLog:
    """INJECT/DECISION should report which action branch was taken."""

    def test_decision_send(self, caplog) -> None:
        """Normal flow should log action=send."""
        ctrl = _make_controller(master_fd=5)

        mock_settings = MagicMock()
        mock_settings.get_instruction_file_paths.return_value = [".synapse/default.md"]
        mock_settings.instructions = {"default": "default.md"}

        with (
            caplog.at_level(logging.INFO),
            patch("synapse.controller.get_settings", return_value=mock_settings),
            patch("synapse.controller.format_a2a_message", return_value="msg"),
            patch.object(ctrl, "write", return_value=True),
            patch("time.sleep"),
        ):
            ctrl._send_identity_instruction()

        decision_logs = [
            r
            for r in caplog.records
            if "INJECT/DECISION" in r.message and "synapse-claude-8100" in r.message
        ]
        assert len(decision_logs) == 1
        assert "action=send" in decision_logs[0].message

    def test_decision_skip_resume(self, caplog) -> None:
        """Resume mode should log action=skip_resume."""
        ctrl = _make_controller(skip_initial_instructions=True)

        with caplog.at_level(logging.INFO):
            ctrl._send_identity_instruction()

        decision_logs = [
            r
            for r in caplog.records
            if "INJECT/DECISION" in r.message and "synapse-claude-8100" in r.message
        ]
        assert len(decision_logs) == 1
        assert "action=skip_resume" in decision_logs[0].message

    def test_decision_skip_no_files(self, caplog) -> None:
        """Empty instruction file list should log action=skip_no_files."""
        ctrl = _make_controller(master_fd=5)

        mock_settings = MagicMock()
        mock_settings.get_instruction_file_paths.return_value = []
        mock_settings.instructions = {}

        with (
            caplog.at_level(logging.INFO),
            patch("synapse.controller.get_settings", return_value=mock_settings),
        ):
            ctrl._send_identity_instruction()

        decision_logs = [
            r
            for r in caplog.records
            if "INJECT/DECISION" in r.message and "synapse-claude-8100" in r.message
        ]
        assert len(decision_logs) == 1
        assert "action=skip_no_files" in decision_logs[0].message

    def test_decision_abort_master_fd_timeout(self, caplog) -> None:
        """When master_fd never becomes available, should log action=abort_master_fd_timeout."""
        ctrl = _make_controller(master_fd=None)

        with (
            caplog.at_level(logging.INFO),
            patch("synapse.controller.IDENTITY_WAIT_TIMEOUT", 0.1),
            patch("time.sleep"),
        ):
            ctrl._send_identity_instruction()

        decision_logs = [
            r
            for r in caplog.records
            if "INJECT/DECISION" in r.message and "synapse-claude-8100" in r.message
        ]
        assert len(decision_logs) == 1
        assert "action=abort_master_fd_timeout" in decision_logs[0].message


# ============================================================
# DELIVER logs
# ============================================================


class TestDeliverLog:
    """INJECT/DELIVER should report input_ready detection and write_size."""

    def test_deliver_log_pattern_found(self, caplog) -> None:
        """When input_ready_pattern is found in buffer, should log pattern_found."""
        ctrl = _make_controller(master_fd=5, input_ready_pattern=">")
        # Pre-fill output buffer with the pattern
        ctrl.output_buffer = b"some output >"

        mock_settings = MagicMock()
        mock_settings.get_instruction_file_paths.return_value = [".synapse/default.md"]
        mock_settings.instructions = {"default": "default.md"}

        with (
            caplog.at_level(logging.INFO),
            patch("synapse.controller.get_settings", return_value=mock_settings),
            patch("synapse.controller.format_a2a_message", return_value="msg"),
            patch.object(ctrl, "write", return_value=True),
            patch("time.sleep"),
        ):
            ctrl._send_identity_instruction()

        deliver_logs = [
            r
            for r in caplog.records
            if "INJECT/DELIVER" in r.message and "synapse-claude-8100" in r.message
        ]
        assert len(deliver_logs) == 1
        assert "input_ready=pattern_found" in deliver_logs[0].message

    def test_deliver_log_timeout(self, caplog) -> None:
        """When input_ready_pattern is NOT found, should log timeout."""
        ctrl = _make_controller(master_fd=5, input_ready_pattern=">")
        ctrl.output_buffer = b"no prompt here"

        mock_settings = MagicMock()
        mock_settings.get_instruction_file_paths.return_value = [".synapse/default.md"]
        mock_settings.instructions = {"default": "default.md"}

        with (
            caplog.at_level(logging.INFO),
            patch("synapse.controller.get_settings", return_value=mock_settings),
            patch("synapse.controller.format_a2a_message", return_value="msg"),
            patch.object(ctrl, "write", return_value=True),
            patch("time.sleep"),
        ):
            ctrl._send_identity_instruction()

        deliver_logs = [
            r
            for r in caplog.records
            if "INJECT/DELIVER" in r.message and "synapse-claude-8100" in r.message
        ]
        assert len(deliver_logs) == 1
        assert "input_ready=timeout" in deliver_logs[0].message

    def test_deliver_log_no_pattern(self, caplog) -> None:
        """When no input_ready_pattern configured, should log input_ready=none."""
        ctrl = _make_controller(master_fd=5, input_ready_pattern=None)

        mock_settings = MagicMock()
        mock_settings.get_instruction_file_paths.return_value = [".synapse/default.md"]
        mock_settings.instructions = {"default": "default.md"}

        with (
            caplog.at_level(logging.INFO),
            patch("synapse.controller.get_settings", return_value=mock_settings),
            patch("synapse.controller.format_a2a_message", return_value="msg"),
            patch.object(ctrl, "write", return_value=True),
            patch("time.sleep"),
        ):
            ctrl._send_identity_instruction()

        deliver_logs = [
            r
            for r in caplog.records
            if "INJECT/DELIVER" in r.message and "synapse-claude-8100" in r.message
        ]
        assert len(deliver_logs) == 1
        assert "input_ready=none" in deliver_logs[0].message

    def test_deliver_log_write_size(self, caplog) -> None:
        """write_size should match len(prefixed) from format_a2a_message."""
        ctrl = _make_controller(master_fd=5)
        test_message = "A2A:test-task:synapse-system hello world"

        mock_settings = MagicMock()
        mock_settings.get_instruction_file_paths.return_value = [".synapse/default.md"]
        mock_settings.instructions = {"default": "default.md"}

        with (
            caplog.at_level(logging.INFO),
            patch("synapse.controller.get_settings", return_value=mock_settings),
            patch("synapse.controller.format_a2a_message", return_value=test_message),
            patch.object(ctrl, "write", return_value=True),
            patch("time.sleep"),
        ):
            ctrl._send_identity_instruction()

        deliver_logs = [
            r
            for r in caplog.records
            if "INJECT/DELIVER" in r.message and "synapse-claude-8100" in r.message
        ]
        assert len(deliver_logs) == 1
        assert f"write_size={len(test_message)}" in deliver_logs[0].message


# ============================================================
# SUMMARY logs
# ============================================================


class TestSummaryLog:
    """INJECT/SUMMARY should report final outcome on every exit path."""

    def test_summary_sent(self, caplog) -> None:
        """Successful send should log initial_instructions=sent."""
        ctrl = _make_controller(master_fd=5)

        mock_settings = MagicMock()
        mock_settings.get_instruction_file_paths.return_value = [".synapse/default.md"]
        mock_settings.instructions = {"default": "default.md"}

        with (
            caplog.at_level(logging.INFO),
            patch("synapse.controller.get_settings", return_value=mock_settings),
            patch("synapse.controller.format_a2a_message", return_value="msg"),
            patch.object(ctrl, "write", return_value=True),
            patch("time.sleep"),
        ):
            ctrl._send_identity_instruction()

        summary_logs = [
            r
            for r in caplog.records
            if "INJECT/SUMMARY" in r.message and "synapse-claude-8100" in r.message
        ]
        assert len(summary_logs) == 1
        assert "initial_instructions=sent" in summary_logs[0].message

    def test_summary_skipped_resume(self, caplog) -> None:
        """Resume mode should log initial_instructions=skipped reason=resume_mode."""
        ctrl = _make_controller(skip_initial_instructions=True)

        with caplog.at_level(logging.INFO):
            ctrl._send_identity_instruction()

        summary_logs = [
            r
            for r in caplog.records
            if "INJECT/SUMMARY" in r.message and "synapse-claude-8100" in r.message
        ]
        assert len(summary_logs) == 1
        assert "initial_instructions=skipped" in summary_logs[0].message
        assert "reason=resume_mode" in summary_logs[0].message

    def test_summary_skipped_no_files(self, caplog) -> None:
        """No instruction files should log initial_instructions=skipped reason=no_files."""
        ctrl = _make_controller(master_fd=5)

        mock_settings = MagicMock()
        mock_settings.get_instruction_file_paths.return_value = []
        mock_settings.instructions = {}

        with (
            caplog.at_level(logging.INFO),
            patch("synapse.controller.get_settings", return_value=mock_settings),
        ):
            ctrl._send_identity_instruction()

        summary_logs = [
            r
            for r in caplog.records
            if "INJECT/SUMMARY" in r.message and "synapse-claude-8100" in r.message
        ]
        assert len(summary_logs) == 1
        assert "initial_instructions=skipped" in summary_logs[0].message
        assert "reason=no_files" in summary_logs[0].message

    def test_summary_failed_master_fd_timeout(self, caplog) -> None:
        """master_fd timeout should log initial_instructions=failed reason=master_fd_timeout."""
        ctrl = _make_controller(master_fd=None)

        with (
            caplog.at_level(logging.INFO),
            patch("synapse.controller.IDENTITY_WAIT_TIMEOUT", 0.1),
            patch("time.sleep"),
        ):
            ctrl._send_identity_instruction()

        summary_logs = [
            r
            for r in caplog.records
            if "INJECT/SUMMARY" in r.message and "synapse-claude-8100" in r.message
        ]
        assert len(summary_logs) == 1
        assert "initial_instructions=failed" in summary_logs[0].message
        assert "reason=master_fd_timeout" in summary_logs[0].message

    def test_summary_failed_write_exception(self, caplog) -> None:
        """Write exception should log initial_instructions=failed reason=write_exception."""
        ctrl = _make_controller(master_fd=5)

        mock_settings = MagicMock()
        mock_settings.get_instruction_file_paths.return_value = [".synapse/default.md"]
        mock_settings.instructions = {"default": "default.md"}

        with (
            caplog.at_level(logging.INFO),
            patch("synapse.controller.get_settings", return_value=mock_settings),
            patch("synapse.controller.format_a2a_message", return_value="msg"),
            patch.object(ctrl, "write", side_effect=OSError("write failed")),
            patch("time.sleep"),
        ):
            ctrl._send_identity_instruction()

        summary_logs = [
            r
            for r in caplog.records
            if "INJECT/SUMMARY" in r.message and "synapse-claude-8100" in r.message
        ]
        assert len(summary_logs) == 1
        assert "initial_instructions=failed" in summary_logs[0].message
        assert "reason=write_exception" in summary_logs[0].message


# ============================================================
# Logger unification
# ============================================================


class TestLoggerUnified:
    """Verify that _send_identity_instruction uses logger.* not logging.*."""

    def test_no_direct_logging_calls_in_send_identity(self) -> None:
        """The method should use module-level logger, not logging.info/error directly."""
        import inspect

        from synapse.controller import TerminalController

        source = inspect.getsource(TerminalController._send_identity_instruction)
        # Should NOT contain direct logging.info/logging.error/logging.debug/logging.warning
        # (these should all be logger.info/logger.error/etc. instead)
        for call in [
            "logging.info(",
            "logging.error(",
            "logging.debug(",
            "logging.warning(",
        ]:
            assert call not in source, (
                f"Found direct '{call}' in _send_identity_instruction. "
                f"Use 'logger.*' instead for consistency."
            )
