"""Tests for ``synapse claude --agent <saved>`` shortcut path."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def _setup_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a project-scope agent definition and patch CWD/HOME."""
    home = tmp_path / "home"
    home.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(tmp_path)

    agents_dir = tmp_path / ".synapse" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "wise-strategist.agent").write_text(
        "id=wise-strategist\n"
        "name=Strategist\n"
        "profile=claude\n"
        "role=code reviewer\n"
        "skill_set=reviewer\n",
        encoding="utf-8",
    )
    return agents_dir


def _run_main(monkeypatch: pytest.MonkeyPatch, argv: list[str]) -> MagicMock:
    """Run ``main()`` with *argv* and return the mocked ``cmd_run_interactive``."""
    import sys

    monkeypatch.setattr(sys, "argv", argv)

    mock_run = MagicMock()
    mock_port_mgr = MagicMock()
    mock_port_mgr.get_available_port.return_value = 8100

    with (
        patch("synapse.cli.cmd_run_interactive", mock_run),
        patch("synapse.cli.PortManager", return_value=mock_port_mgr),
        patch("synapse.cli.AgentRegistry"),
        patch("synapse.cli.install_skills"),
    ):
        from synapse.cli import main

        main()

    return mock_run


# ── Happy-path tests ──────────────────────────────────────────────


def test_agent_flag_resolves_saved_definition(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """--agent should expand name, role, and skill_set from saved definition."""
    _setup_store(tmp_path, monkeypatch)
    mock_run = _run_main(
        monkeypatch, ["synapse", "claude", "--agent", "wise-strategist"]
    )

    mock_run.assert_called_once()
    _, kwargs = mock_run.call_args
    assert kwargs["name"] == "Strategist"
    assert kwargs["role"] == "code reviewer"
    assert kwargs["skill_set"] == "reviewer"


def test_agent_flag_short_form(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """-A should work as a short form of --agent."""
    _setup_store(tmp_path, monkeypatch)
    mock_run = _run_main(monkeypatch, ["synapse", "claude", "-A", "wise-strategist"])

    mock_run.assert_called_once()
    _, kwargs = mock_run.call_args
    assert kwargs["name"] == "Strategist"


# ── CLI-override tests ────────────────────────────────────────────


def test_cli_args_override_saved_values(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Explicit --name / --role / --skill-set should override saved values."""
    _setup_store(tmp_path, monkeypatch)
    mock_run = _run_main(
        monkeypatch,
        [
            "synapse",
            "claude",
            "--agent",
            "wise-strategist",
            "--role",
            "test writer",
        ],
    )

    mock_run.assert_called_once()
    _, kwargs = mock_run.call_args
    assert kwargs["role"] == "test writer"
    # Name and skill_set still come from saved definition
    assert kwargs["name"] == "Strategist"
    assert kwargs["skill_set"] == "reviewer"


# ── Error tests ───────────────────────────────────────────────────


def test_profile_mismatch_exits(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """synapse gemini --agent <claude-definition> should exit with error."""
    _setup_store(tmp_path, monkeypatch)
    with pytest.raises(SystemExit, match="1"):
        _run_main(monkeypatch, ["synapse", "gemini", "--agent", "wise-strategist"])


def test_unknown_agent_exits(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """--agent with a non-existent ID should exit with error."""
    _setup_store(tmp_path, monkeypatch)
    with pytest.raises(SystemExit, match="1"):
        _run_main(monkeypatch, ["synapse", "claude", "--agent", "nonexistent"])


def test_resolve_by_name(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """--agent should also resolve by display name, not just by ID."""
    _setup_store(tmp_path, monkeypatch)
    mock_run = _run_main(monkeypatch, ["synapse", "claude", "--agent", "Strategist"])

    mock_run.assert_called_once()
    _, kwargs = mock_run.call_args
    assert kwargs["name"] == "Strategist"
    assert kwargs["role"] == "code reviewer"
