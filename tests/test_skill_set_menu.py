from __future__ import annotations

import sys
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


@dataclass
class _SSD:
    description: str
    skills: list[str]


def _make_sets(n: int) -> dict[str, _SSD]:
    # Deterministic names for sorted() behavior
    return {
        f"set-{i:02d}": _SSD(description=f"desc {i}", skills=["s"]) for i in range(n)
    }


def test_interactive_skill_set_setup_tui_select_by_arrow_menu() -> None:
    """TUI mode should select the item returned by TerminalMenu.show()."""
    from synapse.cli import interactive_skill_set_setup

    sets = {"b": _SSD("B", ["s"]), "a": _SSD("A", ["s"]), "c": _SSD("C", ["s"])}
    mock_menu = MagicMock()
    mock_menu.show.return_value = 1  # sorted => b
    mock_terminal_menu = MagicMock(return_value=mock_menu)
    mock_module = SimpleNamespace(TerminalMenu=mock_terminal_menu)

    with (
        patch.dict(sys.modules, {"simple_term_menu": mock_module}),
        patch("synapse.skills.load_skill_sets", return_value=sets),
    ):
        selected = interactive_skill_set_setup()

    assert selected == "b"
    mock_terminal_menu.assert_called_once()
    items = mock_terminal_menu.call_args.args[0]
    assert len(items) == 4  # a,b,c + skip
    assert "a" in items[0]
    assert "b" in items[1]
    assert "c" in items[2]
    assert "Skip" in items[3]
    assert all("NAME" not in row for row in items)


def test_interactive_skill_set_setup_tui_rows_are_simple() -> None:
    """TUI rows should be plain text to avoid redraw glitches."""
    from synapse.cli import interactive_skill_set_setup

    sets = {"reviewer": _SSD("Code review", ["code-quality"])}
    mock_menu = MagicMock()
    mock_menu.show.return_value = 0
    mock_terminal_menu = MagicMock(return_value=mock_menu)
    mock_module = SimpleNamespace(TerminalMenu=mock_terminal_menu)

    with (
        patch.dict(sys.modules, {"simple_term_menu": mock_module}),
        patch("synapse.skills.load_skill_sets", return_value=sets),
    ):
        selected = interactive_skill_set_setup()

    assert selected == "reviewer"
    items = mock_terminal_menu.call_args.args[0]
    assert items[0].startswith("1. reviewer - 1 skills")
    assert "Code review" not in items[0]
    assert all("\x1b[" not in row for row in items)


def test_interactive_skill_set_setup_tui_skip_returns_none() -> None:
    """TUI mode should return None when Skip is selected."""
    from synapse.cli import interactive_skill_set_setup

    sets = {
        "reviewer": _SSD("Code review", ["code-quality"]),
        "writer": _SSD("Docs writer", ["project-docs"]),
    }
    mock_menu = MagicMock()
    mock_menu.show.return_value = 2  # reviewer, writer, skip
    mock_terminal_menu = MagicMock(return_value=mock_menu)
    mock_module = SimpleNamespace(TerminalMenu=mock_terminal_menu)

    with (
        patch.dict(sys.modules, {"simple_term_menu": mock_module}),
        patch("synapse.skills.load_skill_sets", return_value=sets),
    ):
        selected = interactive_skill_set_setup()

    assert selected is None


def test_interactive_skill_set_setup_fallback_without_tui(capsys) -> None:
    """Fallback mode should still allow number selection when TUI is unavailable."""
    from synapse.cli import interactive_skill_set_setup

    sets = {
        "reviewer": _SSD("Code review", ["code-quality"]),
        "writer": _SSD("Docs writer", ["project-docs"]),
    }

    with (
        patch.dict(sys.modules, {"simple_term_menu": None}),
        patch("synapse.skills.load_skill_sets", return_value=sets),
        patch("synapse.cli.input", side_effect=["1"]),
    ):
        selected = interactive_skill_set_setup()

    assert selected == "reviewer"
    out = capsys.readouterr().out
    assert "Select a skill set (optional):" in out
