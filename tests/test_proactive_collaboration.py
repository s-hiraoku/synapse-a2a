"""Tests for proactive collaboration improvements (issue #335).

Validates that:
1. default.md template includes mandatory collaboration gate for large tasks
2. default.md template includes agent assignment plan template
3. synapse-manager SKILL.md triggers on implementation task keywords
"""

from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DEFAULT_MD = REPO_ROOT / "synapse" / "templates" / ".synapse" / "default.md"
LIVE_DEFAULT_MD = REPO_ROOT / ".synapse" / "default.md"
MANAGER_SKILL_MD = (
    REPO_ROOT / "plugins" / "synapse-a2a" / "skills" / "synapse-manager" / "SKILL.md"
)


@pytest.fixture
def template_content() -> str:
    """Read the default.md template content."""
    return TEMPLATE_DEFAULT_MD.read_text()


@pytest.fixture
def manager_skill_content() -> str:
    """Read the synapse-manager SKILL.md content."""
    return MANAGER_SKILL_MD.read_text()


# ===========================================================================
# AC1: Plan template includes agent assignment section
# ===========================================================================


class TestAgentAssignmentTemplate:
    """default.md must include agent assignment guidance for multi-phase plans."""

    def test_agent_assignment_section_exists(self, template_content: str) -> None:
        """Template must have an agent assignment section."""
        assert "Agent Assignment" in template_content

    def test_agent_assignment_has_table_format(self, template_content: str) -> None:
        """Agent assignment section must include a table template."""
        assert "Phase" in template_content
        assert "Agent" in template_content
        assert "Rationale" in template_content

    def test_agent_assignment_mentions_task_board(self, template_content: str) -> None:
        """Agent assignment section should reference task board for tracking."""
        # After planning agent assignment, agents should create tasks
        assert "synapse tasks create" in template_content


# ===========================================================================
# AC2: Agent demonstrates collaboration on multi-phase tasks
# ===========================================================================


class TestMandatoryCollaborationGate:
    """default.md must enforce collaboration evaluation for large tasks."""

    def test_mandatory_gate_for_multi_phase(self, template_content: str) -> None:
        """Must require collaboration check for tasks with 3+ phases."""
        assert "3+" in template_content or "3 or more" in template_content

    def test_mandatory_gate_for_many_files(self, template_content: str) -> None:
        """Must require collaboration check for tasks with 10+ file changes."""
        assert "10+" in template_content or "10 or more" in template_content

    def test_must_keyword_enforcement(self, template_content: str) -> None:
        """Must use MUST (not should/consider) to enforce the gate."""
        # Find the section about large task collaboration
        lines = template_content.split("\n")
        found_must = False
        for line in lines:
            if ("3+" in line or "10+" in line) and "MUST" in line:
                found_must = True
                break
        assert found_must, "Large task gate must use MUST keyword for enforcement"

    def test_synapse_list_required_before_implementation(
        self, template_content: str
    ) -> None:
        """Large task gate must require synapse list check."""
        # The gate section should mention synapse list as mandatory
        assert "synapse list" in template_content

    def test_task_board_entry_required(self, template_content: str) -> None:
        """Large task gate must require creating a task board entry."""
        assert "synapse tasks create" in template_content


# ===========================================================================
# AC3: synapse-manager skill triggers on implementation tasks
# ===========================================================================


class TestManagerSkillTriggers:
    """synapse-manager SKILL.md must trigger on implementation keywords."""

    def test_triggers_on_implement(self, manager_skill_content: str) -> None:
        """Skill must list 'implement' as a trigger context."""
        lower = manager_skill_content.lower()
        assert "implement" in lower

    def test_triggers_on_phase(self, manager_skill_content: str) -> None:
        """Skill must list 'phase' as a trigger context."""
        lower = manager_skill_content.lower()
        assert "phase" in lower

    def test_triggers_on_multi_file(self, manager_skill_content: str) -> None:
        """Skill must mention multi-file changes as a trigger."""
        lower = manager_skill_content.lower()
        assert "multi-file" in lower or "multiple file" in lower

    def test_triggers_on_plan(self, manager_skill_content: str) -> None:
        """Skill must list 'plan' as a trigger context."""
        lower = manager_skill_content.lower()
        assert "plan" in lower

    def test_when_to_use_covers_implementation(
        self, manager_skill_content: str
    ) -> None:
        """When to Use section must cover implementation task scenarios."""
        # Should mention implementation plans or multi-phase work
        assert (
            "implementation" in manager_skill_content.lower()
            or "multi-phase" in manager_skill_content.lower()
        )


# ===========================================================================
# Consistency: template and live default.md match
# ===========================================================================


class TestTemplateConsistency:
    """Template and live .synapse/default.md should have matching structure."""

    def test_live_default_md_exists(self) -> None:
        """Live .synapse/default.md must exist."""
        assert LIVE_DEFAULT_MD.exists(), f"{LIVE_DEFAULT_MD} does not exist"

    def test_live_has_agent_assignment(self) -> None:
        """Live default.md must also include agent assignment section."""
        content = LIVE_DEFAULT_MD.read_text()
        assert "Agent Assignment" in content

    def test_live_has_mandatory_gate(self) -> None:
        """Live default.md must also include mandatory collaboration gate."""
        content = LIVE_DEFAULT_MD.read_text()
        assert "MUST" in content
        has_gate = "3+" in content or "3 or more" in content
        assert has_gate, "Live default.md missing large-task collaboration gate"
