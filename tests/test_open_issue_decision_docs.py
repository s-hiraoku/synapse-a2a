"""Documentation coverage for research/RFC open issues."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DECISIONS = REPO_ROOT / "docs" / "design" / "open-issue-decisions.md"


def test_research_and_rfc_issues_have_decision_artifacts() -> None:
    """Investigation/RFC tickets should resolve to concrete decision notes."""
    body = DECISIONS.read_text(encoding="utf-8")
    required = [
        "#18 Dependency Dashboard",
        "#48 Unified database",
        "#159 Compliance and permissions",
        "#217 Go rewrite RFC",
        "#406 Agent browser",
        "#434 everything-claude-code patterns",
        "#512 Claude Agent SDK",
    ]

    missing = [token for token in required if token not in body]

    assert not missing, "Missing open issue decision notes: " + ", ".join(missing)
