from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import patch


@dataclass
class _SSD:
    description: str
    skills: list[str]


def _make_sets(n: int) -> dict[str, _SSD]:
    # Deterministic names for sorted() behavior
    return {
        f"set-{i:02d}": _SSD(description=f"desc {i}", skills=["s"]) for i in range(n)
    }


def test_interactive_skill_set_setup_select_by_number(capsys) -> None:
    """Selecting by row number returns the set on the current page."""
    from synapse.cli import interactive_skill_set_setup

    sets = {"b": _SSD("B", ["s"]), "a": _SSD("A", ["s"]), "c": _SSD("C", ["s"])}

    with (
        patch("synapse.skills.load_skill_sets", return_value=sets),
        patch("synapse.cli.input", side_effect=["2"]),
    ):
        selected = interactive_skill_set_setup()

    # Sorted rows are a,b,c -> row 2 = b
    assert selected == "b"
    out = capsys.readouterr().out
    assert "Synapse A2A" in out
    assert "Skill Set Selector" in out


def test_interactive_skill_set_setup_filter_then_select(capsys) -> None:
    """Typing /query filters rows before numeric selection."""
    from synapse.cli import interactive_skill_set_setup

    sets = {
        "reviewer": _SSD("Code review", ["code-quality"]),
        "writer": _SSD("Docs writer", ["project-docs"]),
    }

    with (
        patch("synapse.skills.load_skill_sets", return_value=sets),
        patch("synapse.cli.input", side_effect=["/rev", "1"]),
    ):
        selected = interactive_skill_set_setup()

    assert selected == "reviewer"
    out = capsys.readouterr().out
    assert "Filter: rev" in out


def test_interactive_skill_set_setup_pagination_then_select(capsys) -> None:
    """For many rows, n moves to next page then row number selects there."""
    from synapse.cli import interactive_skill_set_setup

    sets = _make_sets(15)  # page size is 10

    with (
        patch("synapse.skills.load_skill_sets", return_value=sets),
        patch("synapse.cli.input", side_effect=["n", "1"]),
    ):
        selected = interactive_skill_set_setup()

    assert selected == "set-10"
    out = capsys.readouterr().out
    assert "Showing 11-15 of 15" in out
