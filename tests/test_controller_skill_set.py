"""Tests for skill set information in initial instructions."""

from unittest.mock import Mock, patch

import pytest

from synapse.controller import TerminalController
from synapse.registry import AgentRegistry
from synapse.skills import SkillSetDefinition


class TestSkillSetInInstructions:
    """Tests for including skill set details in identity instructions."""

    @pytest.fixture
    def mock_registry(self):
        registry = Mock(spec=AgentRegistry)
        registry.list_agents.return_value = {}
        registry.get_live_agents.return_value = {}
        return registry

    @pytest.fixture
    def controller_with_skill_set(self, mock_registry):
        """Controller with skill_set parameter set."""
        return TerminalController(
            command="echo test",
            idle_regex=r"\$",
            registry=mock_registry,
            agent_id="synapse-claude-8100",
            agent_type="claude",
            submit_seq="\r",
            skill_set="architect",
        )

    @pytest.fixture
    def controller_without_skill_set(self, mock_registry):
        """Controller without skill_set parameter."""
        return TerminalController(
            command="echo test",
            idle_regex=r"\$",
            registry=mock_registry,
            agent_id="synapse-claude-8100",
            agent_type="claude",
            submit_seq="\r",
        )

    def test_controller_stores_skill_set(self, controller_with_skill_set):
        """Controller should store skill_set as instance variable."""
        assert controller_with_skill_set.skill_set == "architect"

    def test_controller_skill_set_default_none(self, controller_without_skill_set):
        """Controller should default skill_set to None."""
        assert controller_without_skill_set.skill_set is None

    def test_identity_includes_skill_set_section(self, controller_with_skill_set):
        """Identity instruction should include skill set details when set."""
        ctrl = controller_with_skill_set
        ctrl.running = True
        ctrl.master_fd = 1

        written_data = []

        def mock_write(data, submit_seq=None):
            written_data.append(data)

        ctrl.write = mock_write

        mock_skill_set = SkillSetDefinition(
            name="architect",
            description="System architecture and design — design docs, API contracts, code review",
            skills=[
                "synapse-a2a",
                "system-design",
                "api-design",
                "code-review",
                "project-docs",
            ],
        )

        with (
            patch("synapse.controller.get_settings") as mock_settings,
            patch("synapse.controller.load_skill_sets") as mock_load,
            patch("synapse.controller.POST_WRITE_IDLE_DELAY", 0),
        ):
            settings = Mock()
            settings.get_instruction_file_paths.return_value = [".synapse/default.md"]
            mock_settings.return_value = settings
            mock_load.return_value = {"architect": mock_skill_set}

            ctrl._send_identity_instruction()

        assert len(written_data) == 1
        instruction = written_data[0]

        # Should contain skill set name
        assert "architect" in instruction
        # Should contain description
        assert "System architecture and design" in instruction
        # Should contain skill names
        assert "system-design" in instruction
        assert "api-design" in instruction
        assert "code-review" in instruction
        assert "project-docs" in instruction

    def test_identity_excludes_skill_set_when_none(self, controller_without_skill_set):
        """Identity instruction should NOT include skill set section when not set."""
        ctrl = controller_without_skill_set
        ctrl.running = True
        ctrl.master_fd = 1

        written_data = []

        def mock_write(data, submit_seq=None):
            written_data.append(data)

        ctrl.write = mock_write

        with (
            patch("synapse.controller.get_settings") as mock_settings,
            patch("synapse.controller.POST_WRITE_IDLE_DELAY", 0),
        ):
            settings = Mock()
            settings.get_instruction_file_paths.return_value = [".synapse/default.md"]
            mock_settings.return_value = settings

            ctrl._send_identity_instruction()

        assert len(written_data) == 1
        instruction = written_data[0]

        # Should NOT contain skill set section header
        assert "SKILL SET" not in instruction

    def test_identity_handles_missing_skill_set_definition(self, mock_registry):
        """Should handle gracefully when skill set name is not found in definitions."""
        ctrl = TerminalController(
            command="echo test",
            idle_regex=r"\$",
            registry=mock_registry,
            agent_id="synapse-claude-8100",
            agent_type="claude",
            submit_seq="\r",
            skill_set="nonexistent",
        )
        ctrl.running = True
        ctrl.master_fd = 1

        written_data = []

        def mock_write(data, submit_seq=None):
            written_data.append(data)

        ctrl.write = mock_write

        with (
            patch("synapse.controller.get_settings") as mock_settings,
            patch("synapse.controller.load_skill_sets") as mock_load,
            patch("synapse.controller.POST_WRITE_IDLE_DELAY", 0),
        ):
            settings = Mock()
            settings.get_instruction_file_paths.return_value = [".synapse/default.md"]
            mock_settings.return_value = settings
            mock_load.return_value = {}  # No skill sets found

            ctrl._send_identity_instruction()

        assert len(written_data) == 1
        instruction = written_data[0]

        # Should not crash, and should not include skill set section
        assert "SKILL SET" not in instruction

    def test_identity_skill_set_section_format(self, controller_with_skill_set):
        """Skill set section should use a clear, structured format."""
        ctrl = controller_with_skill_set
        ctrl.running = True
        ctrl.master_fd = 1

        written_data = []

        def mock_write(data, submit_seq=None):
            written_data.append(data)

        ctrl.write = mock_write

        mock_skill_set = SkillSetDefinition(
            name="developer",
            description="Implementation and quality — test-first development, refactoring",
            skills=["synapse-a2a", "test-first", "refactoring"],
        )

        with (
            patch("synapse.controller.get_settings") as mock_settings,
            patch("synapse.controller.load_skill_sets") as mock_load,
            patch("synapse.controller.POST_WRITE_IDLE_DELAY", 0),
        ):
            settings = Mock()
            settings.get_instruction_file_paths.return_value = [".synapse/default.md"]
            mock_settings.return_value = settings
            mock_load.return_value = {
                "architect": mock_skill_set,
                "developer": mock_skill_set,
            }

            # Change skill_set to developer for this test
            ctrl.skill_set = "developer"
            ctrl._send_identity_instruction()

        assert len(written_data) == 1
        instruction = written_data[0]

        # Verify section structure
        assert "SKILL SET" in instruction
        assert "developer" in instruction
        assert "Implementation and quality" in instruction
        assert "test-first" in instruction
        assert "refactoring" in instruction
