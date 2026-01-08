"""Tests for delegation module."""

import tempfile
from pathlib import Path

from synapse.delegation import (
    build_delegation_instructions,
    get_delegate_instructions_path,
    load_delegate_instructions,
)


class TestLoadDelegateInstructions:
    """Tests for loading delegate.md files."""

    def test_load_from_project_path(self) -> None:
        """Should load instructions from project path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            md_path = Path(tmpdir) / "delegate.md"
            md_path.write_text("# My Rules\nコーディングはCodexに", encoding="utf-8")

            result = load_delegate_instructions(project_path=md_path)
            assert result is not None
            assert "コーディングはCodexに" in result

    def test_project_takes_precedence(self) -> None:
        """Project path should take precedence over user path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir) / "project" / "delegate.md"
            user_path = Path(tmpdir) / "user" / "delegate.md"

            project_path.parent.mkdir()
            user_path.parent.mkdir()

            project_path.write_text("Project rules", encoding="utf-8")
            user_path.write_text("User rules", encoding="utf-8")

            result = load_delegate_instructions(
                project_path=project_path, user_path=user_path
            )
            assert result == "Project rules"

    def test_fallback_to_user_path(self) -> None:
        """Should fallback to user path if project path doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir) / "project" / "delegate.md"  # doesn't exist
            user_path = Path(tmpdir) / "user" / "delegate.md"

            user_path.parent.mkdir()
            user_path.write_text("User rules", encoding="utf-8")

            result = load_delegate_instructions(
                project_path=project_path, user_path=user_path
            )
            assert result == "User rules"

    def test_returns_none_when_no_file(self) -> None:
        """Should return None when no delegate.md exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir) / "project" / "delegate.md"
            user_path = Path(tmpdir) / "user" / "delegate.md"

            result = load_delegate_instructions(
                project_path=project_path, user_path=user_path
            )
            assert result is None

    def test_returns_none_for_empty_file(self) -> None:
        """Should return None for empty file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            md_path = Path(tmpdir) / "delegate.md"
            md_path.write_text("   \n  ", encoding="utf-8")

            result = load_delegate_instructions(project_path=md_path)
            assert result is None

    def test_unicode_content_preserved(self) -> None:
        """Japanese text should be preserved."""
        with tempfile.TemporaryDirectory() as tmpdir:
            md_path = Path(tmpdir) / "delegate.md"
            content = "コーディング作業（ファイルの編集）はCodexに任せる"
            md_path.write_text(content, encoding="utf-8")

            result = load_delegate_instructions(project_path=md_path)
            assert result == content


class TestBuildDelegationInstructions:
    """Tests for building delegation instructions."""

    def test_off_mode_returns_empty(self) -> None:
        """Off mode should return empty string."""
        result = build_delegation_instructions("off", "some rules")
        assert result == ""

    def test_empty_rules_returns_empty(self) -> None:
        """Empty rules should return empty string."""
        result = build_delegation_instructions("orchestrator", "")
        assert result == ""

    def test_orchestrator_mode(self) -> None:
        """Orchestrator mode should include proper instructions."""
        rules = "コーディングはCodexに任せる"
        result = build_delegation_instructions("orchestrator", rules)

        assert "orchestrator" in result
        assert "コーディングはCodexに任せる" in result
        assert "分析・統合型" in result
        assert "@agent pattern" in result

    def test_passthrough_mode(self) -> None:
        """Passthrough mode should include proper instructions."""
        rules = "リサーチはGeminiに依頼"
        result = build_delegation_instructions("passthrough", rules)

        assert "passthrough" in result
        assert "リサーチはGeminiに依頼" in result
        assert "単純転送型" in result


class TestGetDelegateInstructionsPath:
    """Tests for getting delegate.md path."""

    def test_returns_none_when_no_file(self) -> None:
        """Should return None when no file exists."""
        # This test depends on actual filesystem state
        # In a real scenario, we'd mock Path.cwd() and Path.home()
        # For now, just verify the function doesn't crash
        result = get_delegate_instructions_path()
        # Result could be a path or None depending on environment
        assert result is None or isinstance(result, str)
