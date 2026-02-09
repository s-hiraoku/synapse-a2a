"""Tests for B5: Coordinator / Delegate Mode feature.

Test-first development: these tests define the expected behavior
for delegate mode before implementation.
"""

from __future__ import annotations

import pytest

# ============================================================
# TestDelegateModeSettings - Settings integration
# ============================================================


class TestDelegateModeSettings:
    """Tests for delegate mode settings in DEFAULT_SETTINGS."""

    def test_default_settings_has_delegate_mode_section(self):
        """DEFAULT_SETTINGS should contain a 'delegate_mode' section."""
        from synapse.settings import DEFAULT_SETTINGS

        assert "delegate_mode" in DEFAULT_SETTINGS
        dm = DEFAULT_SETTINGS["delegate_mode"]
        assert isinstance(dm, dict)

    def test_default_deny_file_locks_is_true(self):
        """deny_file_locks should default to True for coordinators."""
        from synapse.settings import DEFAULT_SETTINGS

        assert DEFAULT_SETTINGS["delegate_mode"]["deny_file_locks"] is True

    def test_delegate_mode_has_instruction_template(self):
        """delegate_mode should contain an instruction_template."""
        from synapse.settings import DEFAULT_SETTINGS

        dm = DEFAULT_SETTINGS["delegate_mode"]
        assert "instruction_template" in dm
        template = dm["instruction_template"]
        assert isinstance(template, str)
        assert len(template) > 0

    def test_settings_known_keys_includes_delegate_mode(self):
        """KNOWN_SETTINGS_KEYS should include 'delegate_mode'."""
        from synapse.settings import KNOWN_SETTINGS_KEYS

        assert "delegate_mode" in KNOWN_SETTINGS_KEYS


# ============================================================
# TestDelegateModeFlag - CLI flag parsing
# ============================================================


class TestDelegateModeFlag:
    """Tests for --delegate-mode CLI flag."""

    def test_delegate_mode_flag_parsed(self):
        """--delegate-mode should be parsed as a boolean flag."""
        import argparse

        # Simulate what the parser would produce
        args = argparse.Namespace(delegate_mode=True)
        assert args.delegate_mode is True

    def test_delegate_mode_default_false(self):
        """delegate_mode should default to False."""
        import argparse

        args = argparse.Namespace(delegate_mode=False)
        assert args.delegate_mode is False

    def test_delegate_mode_with_role(self):
        """--delegate-mode should work together with --role."""
        import argparse

        args = argparse.Namespace(
            delegate_mode=True, role="coordinator", name="lead-gemini"
        )
        assert args.delegate_mode is True
        assert args.role == "coordinator"
        assert args.name == "lead-gemini"


# ============================================================
# TestDelegateModeInstructions - Instruction generation
# ============================================================


class TestDelegateModeInstructions:
    """Tests for coordinator instruction generation in delegate mode."""

    def test_coordinator_instruction_mentions_no_editing(self):
        """Coordinator instruction should tell agent not to edit files."""
        from synapse.settings import DEFAULT_SETTINGS

        template = DEFAULT_SETTINGS["delegate_mode"]["instruction_template"]
        # Should mention not editing files directly
        assert "edit" in template.lower() or "ファイル" in template

    def test_coordinator_instruction_mentions_synapse_send(self):
        """Coordinator instruction should mention synapse send for delegation."""
        from synapse.settings import DEFAULT_SETTINGS

        template = DEFAULT_SETTINGS["delegate_mode"]["instruction_template"]
        assert "synapse send" in template or "synapse" in template.lower()

    def test_controller_appends_delegate_instructions(self):
        """TerminalController with delegate_mode should append coordinator instructions."""
        from synapse.controller import TerminalController

        controller = TerminalController(
            command="echo",
            agent_id="synapse-gemini-8110",
            agent_type="gemini",
            port=8110,
            delegate_mode=True,
        )

        assert controller.delegate_mode is True

    def test_controller_without_delegate_mode(self):
        """TerminalController without delegate_mode should not have it set."""
        from synapse.controller import TerminalController

        controller = TerminalController(
            command="echo",
            agent_id="synapse-claude-8100",
            agent_type="claude",
            port=8100,
        )

        assert controller.delegate_mode is False


# ============================================================
# TestDelegateModeFileSafety - File lock denial
# ============================================================


class TestDelegateModeFileSafety:
    """Tests for file safety integration with delegate mode."""

    @pytest.fixture
    def manager(self, tmp_path):
        """Create a FileSafetyManager instance."""
        from synapse.file_safety import FileSafetyManager

        db_path = tmp_path / "safety.db"
        return FileSafetyManager(db_path=str(db_path))

    def test_delegate_mode_deny_file_locks(self, manager):
        """With deny_file_locks=True, coordinator should be denied file locks."""
        from synapse.file_safety import LockStatus

        result = manager.acquire_lock(
            "test.py",
            "gemini",
            agent_id="synapse-gemini-8110",
            delegate_mode=True,
        )
        assert result["status"] == LockStatus.FAILED
        assert (
            "delegate" in result.get("reason", "").lower()
            or "coordinator" in result.get("reason", "").lower()
        )

    def test_delegate_mode_allows_read(self, manager):
        """Delegate mode should not affect read operations."""
        # Read operations (get_file_history, etc.) should still work
        history = manager.get_file_history("test.py")
        assert isinstance(history, list)

    def test_normal_agent_not_affected(self, manager):
        """Normal agents (non-delegate) should not be affected."""
        from synapse.file_safety import LockStatus

        result = manager.acquire_lock(
            "test.py",
            "claude",
            agent_id="synapse-claude-8100",
            delegate_mode=False,
        )
        assert result["status"] == LockStatus.ACQUIRED
