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


@pytest.fixture(scope="module")
def template_content() -> str:
    """Read the default.md template content."""
    return TEMPLATE_DEFAULT_MD.read_text()


@pytest.fixture(scope="module")
def live_content() -> str:
    """Read the live .synapse/default.md content."""
    return LIVE_DEFAULT_MD.read_text()


@pytest.fixture(scope="module")
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


# ===========================================================================
# AC2: Agent demonstrates collaboration on multi-phase tasks
# ===========================================================================


class TestMandatoryCollaborationGate:
    """default.md must enforce collaboration evaluation for large tasks."""

    def test_mandatory_gate_for_multi_phase(self, template_content: str) -> None:
        """Must require collaboration check for tasks with 3+ phases."""
        assert "3+" in template_content or "3 or more" in template_content

    def test_mandatory_gate_for_many_files(self, template_content: str) -> None:
        """Must require collaboration check for tasks with many file changes."""
        assert "9+" in template_content or "9 or more" in template_content

    def test_must_keyword_enforcement(self, template_content: str) -> None:
        """Must use MUST (not should/consider) to enforce the gate."""
        lines = template_content.split("\n")
        found_must = any(
            ("3+" in line or "9+" in line) and "MUST" in line for line in lines
        )
        assert found_must, "Large task gate must use MUST keyword for enforcement"

    def test_synapse_list_required_before_implementation(
        self, template_content: str
    ) -> None:
        """Large task gate must require synapse list check."""
        assert "synapse list" in template_content


# ===========================================================================
# AC3: synapse-manager skill triggers on implementation tasks
# ===========================================================================


class TestManagerSkillTriggers:
    """synapse-manager SKILL.md must trigger on implementation keywords."""

    @pytest.mark.parametrize(
        "keyword",
        ["implement", "phase", "plan", "multi-file"],
    )
    def test_triggers_on_keyword(
        self, manager_skill_content: str, keyword: str
    ) -> None:
        """Skill must mention the keyword in its content."""
        assert keyword in manager_skill_content.lower()

    def test_when_to_use_covers_implementation(
        self, manager_skill_content: str
    ) -> None:
        """When to Use section must cover implementation task scenarios."""
        lower = manager_skill_content.lower()
        assert "implementation" in lower or "multi-phase" in lower


# ===========================================================================
# Consistency: template and live default.md match
# ===========================================================================


class TestTemplateConsistency:
    """Template and live .synapse/default.md should have matching structure."""

    def test_live_default_md_exists(self) -> None:
        """Live .synapse/default.md must exist."""
        assert LIVE_DEFAULT_MD.exists(), f"{LIVE_DEFAULT_MD} does not exist"

    def test_live_has_agent_assignment(self, live_content: str) -> None:
        """Live default.md must also include agent assignment section."""
        assert "Agent Assignment" in live_content

    def test_live_has_mandatory_gate(self, live_content: str) -> None:
        """Live default.md must also include mandatory collaboration gate."""
        assert "MUST" in live_content
        has_gate = "3+" in live_content or "3 or more" in live_content
        assert has_gate, "Live default.md missing large-task collaboration gate"
