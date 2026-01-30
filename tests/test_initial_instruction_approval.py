"""Tests for approval mode feature (Issue #165)."""

import json
from pathlib import Path

from synapse.settings import SynapseSettings


class TestApprovalModeSetting:
    """Tests for approvalMode setting."""

    def test_default_approval_mode_is_required(self, tmp_path: Path) -> None:
        """Default approval mode should be 'required'."""
        settings = SynapseSettings.load(
            user_path=tmp_path / "nonexistent" / "settings.json",
            project_path=tmp_path / "nonexistent2" / "settings.json",
        )
        assert settings.get_approval_mode() == "required"

    def test_approval_mode_from_settings(self, tmp_path: Path) -> None:
        """Should read approval mode from settings file."""
        settings_dir = tmp_path / ".synapse"
        settings_dir.mkdir(parents=True)
        settings_file = settings_dir / "settings.json"
        settings_file.write_text(json.dumps({"approvalMode": "auto"}))

        settings = SynapseSettings.load(
            user_path=tmp_path / "nonexistent" / "settings.json",
            project_path=settings_file,
        )
        assert settings.get_approval_mode() == "auto"

    def test_approval_mode_required(self, tmp_path: Path) -> None:
        """Should support 'required' mode explicitly."""
        settings_dir = tmp_path / ".synapse"
        settings_dir.mkdir(parents=True)
        settings_file = settings_dir / "settings.json"
        settings_file.write_text(json.dumps({"approvalMode": "required"}))

        settings = SynapseSettings.load(
            user_path=tmp_path / "nonexistent" / "settings.json",
            project_path=settings_file,
        )
        assert settings.get_approval_mode() == "required"

    def test_invalid_approval_mode_falls_back_to_required(self, tmp_path: Path) -> None:
        """Invalid approval mode should fall back to 'required'."""
        settings_dir = tmp_path / ".synapse"
        settings_dir.mkdir(parents=True)
        settings_file = settings_dir / "settings.json"
        settings_file.write_text(json.dumps({"approvalMode": "invalid_mode"}))

        settings = SynapseSettings.load(
            user_path=tmp_path / "nonexistent" / "settings.json",
            project_path=settings_file,
        )
        # Invalid mode should fall back to required
        assert settings.get_approval_mode() == "required"


class TestApprovalPromptFormat:
    """Tests for the approval prompt format."""

    def test_format_approval_prompt_contains_agent_info(self) -> None:
        """Approval prompt should contain agent ID and port."""
        from synapse.approval import format_approval_prompt

        prompt = format_approval_prompt(
            agent_id="synapse-claude-8100",
            port=8100,
        )

        assert "synapse-claude-8100" in prompt
        assert "8100" in prompt

    def test_format_approval_prompt_contains_proceed_question(self) -> None:
        """Approval prompt should ask user to proceed."""
        from synapse.approval import format_approval_prompt

        prompt = format_approval_prompt(
            agent_id="synapse-claude-8100",
            port=8100,
        )

        assert "Proceed?" in prompt
        assert "[Y/n/s(skip)]" in prompt


class TestApprovalRequiredBehavior:
    """Tests for approval required behavior."""

    def test_should_require_approval_when_setting_is_required(
        self, tmp_path: Path
    ) -> None:
        """Should require approval when setting is 'required'."""
        settings_dir = tmp_path / ".synapse"
        settings_dir.mkdir(parents=True)
        settings_file = settings_dir / "settings.json"
        settings_file.write_text(json.dumps({"approvalMode": "required"}))

        settings = SynapseSettings.load(
            user_path=tmp_path / "nonexistent" / "settings.json",
            project_path=settings_file,
        )
        assert settings.should_require_approval() is True

    def test_should_not_require_approval_when_setting_is_auto(
        self, tmp_path: Path
    ) -> None:
        """Should not require approval when setting is 'auto'."""
        settings_dir = tmp_path / ".synapse"
        settings_dir.mkdir(parents=True)
        settings_file = settings_dir / "settings.json"
        settings_file.write_text(json.dumps({"approvalMode": "auto"}))

        settings = SynapseSettings.load(
            user_path=tmp_path / "nonexistent" / "settings.json",
            project_path=settings_file,
        )
        assert settings.should_require_approval() is False

    def test_should_require_approval_by_default(self, tmp_path: Path) -> None:
        """Should require approval by default."""
        settings = SynapseSettings.load(
            user_path=tmp_path / "nonexistent" / "settings.json",
            project_path=tmp_path / "nonexistent2" / "settings.json",
        )
        assert settings.should_require_approval() is True


class TestApprovalPromptResponses:
    """Tests for approval prompt response handling."""

    def test_yes_response_continues_with_instructions(self) -> None:
        """'y' or Enter should continue with instructions."""
        from synapse.approval import parse_approval_response

        assert parse_approval_response("y") == "approve"
        assert parse_approval_response("Y") == "approve"
        assert parse_approval_response("yes") == "approve"
        assert parse_approval_response("") == "approve"  # Enter = approve

    def test_no_response_aborts(self) -> None:
        """'n' should abort agent startup."""
        from synapse.approval import parse_approval_response

        assert parse_approval_response("n") == "abort"
        assert parse_approval_response("N") == "abort"
        assert parse_approval_response("no") == "abort"

    def test_skip_response_starts_without_instructions(self) -> None:
        """'s' should start agent without sending instructions."""
        from synapse.approval import parse_approval_response

        assert parse_approval_response("s") == "skip"
        assert parse_approval_response("S") == "skip"
        assert parse_approval_response("skip") == "skip"
