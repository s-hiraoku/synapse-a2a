"""Tests for CLI kill and jump commands (v0.3.11)."""

import argparse
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from synapse.registry import AgentRegistry


@pytest.fixture
def registry():
    """Setup: Use a temp directory for registry."""
    reg = AgentRegistry()
    reg.registry_dir = Path("/tmp/a2a_test_cli_registry")
    reg.registry_dir.mkdir(parents=True, exist_ok=True)
    yield reg
    # Teardown: Cleanup temp directory
    shutil.rmtree(reg.registry_dir, ignore_errors=True)


# ============================================================================
# Tests for cmd_kill
# ============================================================================


def test_kill_by_name(registry):
    """Should kill agent by custom name."""
    from synapse.cli import cmd_kill

    registry.register(
        "synapse-claude-8100",
        "claude",
        8100,
        name="my-claude",
    )

    args = argparse.Namespace(target="my-claude", force=True)

    with patch("synapse.cli.AgentRegistry", return_value=registry):
        with patch("os.kill") as mock_kill:
            with patch.object(registry, "unregister") as mock_unreg:
                # Mock get_live_agents to return our test agent with current PID
                agent_data = registry.get_agent("synapse-claude-8100")
                agent_data["pid"] = 12345  # Use a fake PID
                with patch.object(
                    registry,
                    "get_live_agents",
                    return_value={"synapse-claude-8100": agent_data},
                ):
                    cmd_kill(args)

                mock_kill.assert_called_once()
                mock_unreg.assert_called_once_with("synapse-claude-8100")


def test_kill_by_agent_id(registry):
    """Should kill agent by full agent ID."""
    from synapse.cli import cmd_kill

    registry.register("synapse-claude-8100", "claude", 8100)

    args = argparse.Namespace(target="synapse-claude-8100", force=True)

    with patch("synapse.cli.AgentRegistry", return_value=registry):
        with patch("os.kill") as mock_kill:
            with patch.object(registry, "unregister"):
                agent_data = registry.get_agent("synapse-claude-8100")
                agent_data["pid"] = 12345
                with patch.object(
                    registry,
                    "get_live_agents",
                    return_value={"synapse-claude-8100": agent_data},
                ):
                    cmd_kill(args)

                mock_kill.assert_called_once()


def test_kill_by_type_port(registry):
    """Should kill agent by type-port shorthand."""
    from synapse.cli import cmd_kill

    registry.register("synapse-claude-8100", "claude", 8100)

    args = argparse.Namespace(target="claude-8100", force=True)

    with patch("synapse.cli.AgentRegistry", return_value=registry):
        with patch("os.kill") as mock_kill:
            agent_data = registry.get_agent("synapse-claude-8100")
            agent_data["pid"] = 12345
            with patch.object(
                registry,
                "get_live_agents",
                return_value={"synapse-claude-8100": agent_data},
            ):
                cmd_kill(args)

            mock_kill.assert_called_once()


def test_kill_by_type_single(registry):
    """Should kill agent by type when only one instance."""
    from synapse.cli import cmd_kill

    registry.register("synapse-claude-8100", "claude", 8100)

    args = argparse.Namespace(target="claude", force=True)

    with patch("synapse.cli.AgentRegistry", return_value=registry):
        with patch("os.kill") as mock_kill:
            agent_data = registry.get_agent("synapse-claude-8100")
            agent_data["pid"] = 12345
            with patch.object(
                registry,
                "get_live_agents",
                return_value={"synapse-claude-8100": agent_data},
            ):
                cmd_kill(args)

            mock_kill.assert_called_once()


def test_kill_requires_confirmation(registry, capsys, monkeypatch):
    """Should prompt for confirmation when --force not specified."""
    from synapse.cli import cmd_kill

    registry.register(
        "synapse-claude-8100",
        "claude",
        8100,
        name="my-claude",
    )

    args = argparse.Namespace(target="my-claude", force=False)

    # Simulate user saying 'n' to confirmation
    monkeypatch.setattr("builtins.input", lambda _: "n")

    with patch("synapse.cli.AgentRegistry", return_value=registry):
        with patch("os.kill") as mock_kill:
            agent_data = registry.get_agent("synapse-claude-8100")
            agent_data["pid"] = 12345
            with patch.object(
                registry,
                "get_live_agents",
                return_value={"synapse-claude-8100": agent_data},
            ):
                cmd_kill(args)

            # Should NOT kill when user says no
            mock_kill.assert_not_called()


def test_kill_force_skips_confirmation(registry, monkeypatch):
    """Should skip confirmation when --force is specified."""
    from synapse.cli import cmd_kill

    registry.register(
        "synapse-claude-8100",
        "claude",
        8100,
        name="my-claude",
    )

    args = argparse.Namespace(target="my-claude", force=True)

    # This should not be called when force=True
    mock_input = MagicMock()
    monkeypatch.setattr("builtins.input", mock_input)

    with patch("synapse.cli.AgentRegistry", return_value=registry):
        with patch("os.kill") as mock_kill:
            agent_data = registry.get_agent("synapse-claude-8100")
            agent_data["pid"] = 12345
            with patch.object(
                registry,
                "get_live_agents",
                return_value={"synapse-claude-8100": agent_data},
            ):
                cmd_kill(args)

            mock_input.assert_not_called()
            mock_kill.assert_called_once()


def test_kill_not_found(registry, capsys):
    """Should show error when target not found."""
    from synapse.cli import cmd_kill

    args = argparse.Namespace(target="nonexistent", force=True)

    with patch("synapse.cli.AgentRegistry", return_value=registry):
        with patch.object(registry, "get_live_agents", return_value={}):
            with pytest.raises(SystemExit) as exc_info:
                cmd_kill(args)

            assert exc_info.value.code == 1

    captured = capsys.readouterr()
    assert "not found" in captured.out.lower() or "Agent not found" in captured.out


def test_kill_ambiguous(registry, capsys):
    """Should show error when multiple agents match type."""
    from synapse.cli import cmd_kill

    registry.register("synapse-claude-8100", "claude", 8100)
    registry.register("synapse-claude-8101", "claude", 8101)

    args = argparse.Namespace(target="claude", force=True)

    with patch("synapse.cli.AgentRegistry", return_value=registry):
        agents = registry.list_agents()
        with patch.object(registry, "get_live_agents", return_value=agents):
            with pytest.raises(SystemExit) as exc_info:
                cmd_kill(args)

            assert exc_info.value.code == 1

    captured = capsys.readouterr()
    assert "ambiguous" in captured.out.lower() or "multiple" in captured.out.lower()


# ============================================================================
# Tests for cmd_jump
# ============================================================================


def test_jump_by_name(registry):
    """Should jump to terminal by agent name."""
    from synapse.cli import cmd_jump

    registry.register(
        "synapse-claude-8100",
        "claude",
        8100,
        name="my-claude",
        tty_device="/dev/ttys001",
    )

    args = argparse.Namespace(target="my-claude")

    with (
        patch("synapse.cli.AgentRegistry", return_value=registry),
        patch("synapse.terminal_jump.jump_to_terminal", return_value=True) as mock_jump,
    ):
        agent_data = registry.get_agent("synapse-claude-8100")
        with patch.object(
            registry,
            "get_live_agents",
            return_value={"synapse-claude-8100": agent_data},
        ):
            cmd_jump(args)

        mock_jump.assert_called_once()
        call_args = mock_jump.call_args[0][0]
        assert call_args["agent_id"] == "synapse-claude-8100"


def test_jump_by_agent_id(registry):
    """Should jump to terminal by agent ID."""
    from synapse.cli import cmd_jump

    registry.register(
        "synapse-claude-8100",
        "claude",
        8100,
        tty_device="/dev/ttys001",
    )

    args = argparse.Namespace(target="synapse-claude-8100")

    with (
        patch("synapse.cli.AgentRegistry", return_value=registry),
        patch("synapse.terminal_jump.jump_to_terminal", return_value=True) as mock_jump,
    ):
        agent_data = registry.get_agent("synapse-claude-8100")
        with patch.object(
            registry,
            "get_live_agents",
            return_value={"synapse-claude-8100": agent_data},
        ):
            cmd_jump(args)

        mock_jump.assert_called_once()


def test_jump_not_found(registry, capsys):
    """Should show error when target not found."""
    from synapse.cli import cmd_jump

    args = argparse.Namespace(target="nonexistent")

    with patch("synapse.cli.AgentRegistry", return_value=registry):
        with patch.object(registry, "get_live_agents", return_value={}):
            with pytest.raises(SystemExit) as exc_info:
                cmd_jump(args)

            assert exc_info.value.code == 1

    captured = capsys.readouterr()
    assert "not found" in captured.out.lower()


def test_jump_no_tty(registry, capsys):
    """Should show error when agent has no TTY device."""
    from synapse.cli import cmd_jump

    registry.register(
        "synapse-claude-8100",
        "claude",
        8100,
        # No tty_device set
    )

    args = argparse.Namespace(target="synapse-claude-8100")

    with patch("synapse.cli.AgentRegistry", return_value=registry):
        agent_data = registry.get_agent("synapse-claude-8100")
        with patch.object(
            registry,
            "get_live_agents",
            return_value={"synapse-claude-8100": agent_data},
        ):
            # jump_to_terminal returns False when no TTY is available
            with patch("synapse.terminal_jump.jump_to_terminal", return_value=False):
                with pytest.raises(SystemExit) as exc_info:
                    cmd_jump(args)

                assert exc_info.value.code == 1

    captured = capsys.readouterr()
    assert "failed" in captured.out.lower() or "terminal" in captured.out.lower()


def test_jump_unsupported_terminal(registry, capsys):
    """Should show error when terminal is not supported."""
    from synapse.cli import cmd_jump

    registry.register(
        "synapse-claude-8100",
        "claude",
        8100,
        tty_device="/dev/ttys001",
    )

    args = argparse.Namespace(target="synapse-claude-8100")

    with patch("synapse.cli.AgentRegistry", return_value=registry):
        with patch("synapse.terminal_jump.jump_to_terminal", return_value=False):
            agent_data = registry.get_agent("synapse-claude-8100")
            with patch.object(
                registry,
                "get_live_agents",
                return_value={"synapse-claude-8100": agent_data},
            ):
                with pytest.raises(SystemExit) as exc_info:
                    cmd_jump(args)

                assert exc_info.value.code == 1


# ============================================================================
# Tests for cmd_rename
# ============================================================================


def test_rename_set_name_and_role(registry):
    """Should update name and role for an agent."""
    from synapse.cli import cmd_rename

    registry.register("synapse-claude-8100", "claude", 8100)

    args = argparse.Namespace(
        target="synapse-claude-8100",
        name="my-claude",
        role="レビュー担当",
        clear=False,
    )

    with patch("synapse.cli.AgentRegistry", return_value=registry):
        agent_data = registry.get_agent("synapse-claude-8100")
        with patch.object(
            registry,
            "get_live_agents",
            return_value={"synapse-claude-8100": agent_data},
        ):
            cmd_rename(args)

    info = registry.get_agent("synapse-claude-8100")
    assert info["name"] == "my-claude"
    assert info["role"] == "レビュー担当"


def test_rename_by_current_name(registry):
    """Should find agent by current name and update."""
    from synapse.cli import cmd_rename

    registry.register("synapse-claude-8100", "claude", 8100, name="old-name")

    args = argparse.Namespace(
        target="old-name",
        name="new-name",
        role=None,
        clear=False,
    )

    with patch("synapse.cli.AgentRegistry", return_value=registry):
        agent_data = registry.get_agent("synapse-claude-8100")
        with patch.object(
            registry,
            "get_live_agents",
            return_value={"synapse-claude-8100": agent_data},
        ):
            cmd_rename(args)

    info = registry.get_agent("synapse-claude-8100")
    assert info["name"] == "new-name"


def test_rename_clear(registry):
    """Should clear name and role with --clear flag."""
    from synapse.cli import cmd_rename

    registry.register(
        "synapse-claude-8100",
        "claude",
        8100,
        name="my-claude",
        role="テスト担当",
    )

    args = argparse.Namespace(
        target="my-claude",
        name=None,
        role=None,
        clear=True,
    )

    with patch("synapse.cli.AgentRegistry", return_value=registry):
        agent_data = registry.get_agent("synapse-claude-8100")
        with patch.object(
            registry,
            "get_live_agents",
            return_value={"synapse-claude-8100": agent_data},
        ):
            cmd_rename(args)

    info = registry.get_agent("synapse-claude-8100")
    assert info.get("name") is None
    assert info.get("role") is None


def test_rename_not_found(registry, capsys):
    """Should show error when target not found."""
    from synapse.cli import cmd_rename

    args = argparse.Namespace(
        target="nonexistent",
        name="new-name",
        role=None,
        clear=False,
    )

    with patch("synapse.cli.AgentRegistry", return_value=registry):
        with patch.object(registry, "get_live_agents", return_value={}):
            with pytest.raises(SystemExit) as exc_info:
                cmd_rename(args)

            assert exc_info.value.code == 1

    captured = capsys.readouterr()
    assert "not found" in captured.out.lower()


def test_rename_duplicate_name(registry, capsys):
    """Should show error when new name is already taken."""
    from synapse.cli import cmd_rename

    registry.register("synapse-claude-8100", "claude", 8100, name="existing-name")
    registry.register("synapse-gemini-8110", "gemini", 8110)

    args = argparse.Namespace(
        target="synapse-gemini-8110",
        name="existing-name",  # Already taken
        role=None,
        clear=False,
    )

    with patch("synapse.cli.AgentRegistry", return_value=registry):
        agents = registry.list_agents()
        with patch.object(registry, "get_live_agents", return_value=agents):
            with pytest.raises(SystemExit) as exc_info:
                cmd_rename(args)

            assert exc_info.value.code == 1

    captured = capsys.readouterr()
    assert "already" in captured.out.lower() or "taken" in captured.out.lower()
