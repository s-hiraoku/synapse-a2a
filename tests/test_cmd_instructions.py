"""Tests for synapse instructions command."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from synapse.commands.instructions import InstructionsCommand
from synapse.registry import AgentRegistry
from synapse.settings import SynapseSettings


def create_settings_from_dir(synapse_dir: Path) -> SynapseSettings:
    """Create SynapseSettings from a .synapse directory."""
    return SynapseSettings.load(
        user_path=synapse_dir / "settings.json",
        project_path=synapse_dir / "settings.json",
        local_path=synapse_dir / "settings.local.json",
    )


@pytest.fixture
def temp_registry_dir(tmp_path: Path) -> Path:
    """Create a temporary registry directory."""
    registry_dir = tmp_path / "registry"
    registry_dir.mkdir(parents=True, exist_ok=True)
    return registry_dir


@pytest.fixture
def temp_synapse_dir(tmp_path: Path) -> Path:
    """Create a temporary .synapse directory with settings."""
    synapse_dir = tmp_path / ".synapse"
    synapse_dir.mkdir(parents=True, exist_ok=True)

    # Create default.md instruction file
    default_md = synapse_dir / "default.md"
    default_md.write_text(
        "[SYNAPSE A2A AGENT CONFIGURATION]\n"
        "Agent: {{agent_id}} | Port: {{port}}\n"
        "\n"
        "This is the default instruction."
    )

    # Create claude-specific instruction
    claude_md = synapse_dir / "claude.md"
    claude_md.write_text(
        "[CLAUDE SPECIFIC INSTRUCTIONS]\n"
        "Agent: {{agent_id}} | Port: {{port}}\n"
        "\n"
        "This is Claude-specific instruction."
    )

    # Create settings.json
    settings = {
        "instructions": {
            "default": "default.md",
            "claude": "claude.md",
        }
    }
    settings_file = synapse_dir / "settings.json"
    settings_file.write_text(json.dumps(settings))

    return synapse_dir


@pytest.fixture
def temp_registry(temp_registry_dir: Path) -> AgentRegistry:
    """Create a test registry with temp directory."""
    reg = AgentRegistry()
    reg.registry_dir = temp_registry_dir
    return reg


@pytest.fixture
def mock_a2a_client() -> MagicMock:
    """Create a mock A2A client."""
    client = MagicMock()
    client.send_to_local.return_value = MagicMock(
        id="test-task-123",
        status="submitted",
    )
    return client


class TestInstructionsShow:
    """Tests for 'synapse instructions show' command."""

    def test_show_default_instruction(self, temp_synapse_dir: Path) -> None:
        """Should show default instruction when no agent type specified."""
        output_lines: list[str] = []

        with patch("synapse.settings.Path.cwd", return_value=temp_synapse_dir.parent):
            cmd = InstructionsCommand(
                settings_factory=lambda: create_settings_from_dir(temp_synapse_dir),
                registry_factory=lambda: MagicMock(spec=AgentRegistry),
                a2a_client_factory=lambda: MagicMock(),
                print_func=lambda s: output_lines.append(s),
            )
            cmd.show(agent_type=None)

        output = "\n".join(output_lines)
        assert "default.md" in output.lower() or "default instruction" in output.lower()

    def test_show_agent_specific_instruction(self, temp_synapse_dir: Path) -> None:
        """Should show agent-specific instruction when agent type specified."""
        output_lines: list[str] = []

        with patch("synapse.settings.Path.cwd", return_value=temp_synapse_dir.parent):
            cmd = InstructionsCommand(
                settings_factory=lambda: create_settings_from_dir(temp_synapse_dir),
                registry_factory=lambda: MagicMock(spec=AgentRegistry),
                a2a_client_factory=lambda: MagicMock(),
                print_func=lambda s: output_lines.append(s),
            )
            cmd.show(agent_type="claude")

        output = "\n".join(output_lines)
        assert "claude" in output.lower()

    def test_show_default_fallback_instruction(self, tmp_path: Path) -> None:
        """Should show default instruction when no specific instruction is configured."""
        synapse_dir = tmp_path / ".synapse"
        synapse_dir.mkdir()
        settings_file = synapse_dir / "settings.json"
        # Even with empty instructions, defaults are loaded
        settings_file.write_text(json.dumps({"instructions": {}}))

        output_lines: list[str] = []

        with patch("synapse.settings.Path.cwd", return_value=tmp_path):
            cmd = InstructionsCommand(
                settings_factory=lambda: create_settings_from_dir(synapse_dir),
                registry_factory=lambda: MagicMock(spec=AgentRegistry),
                a2a_client_factory=lambda: MagicMock(),
                print_func=lambda s: output_lines.append(s),
            )
            cmd.show(agent_type="codex")

        output = "\n".join(output_lines)
        # Default instruction is loaded, so it shows instruction content
        assert "instruction for" in output.lower() or "synapse" in output.lower()


class TestInstructionsFiles:
    """Tests for 'synapse instructions files' command."""

    def test_files_lists_instruction_files(self, temp_synapse_dir: Path) -> None:
        """Should list instruction files for agent type."""
        output_lines: list[str] = []

        with patch("synapse.settings.Path.cwd", return_value=temp_synapse_dir.parent):
            cmd = InstructionsCommand(
                settings_factory=lambda: create_settings_from_dir(temp_synapse_dir),
                registry_factory=lambda: MagicMock(spec=AgentRegistry),
                a2a_client_factory=lambda: MagicMock(),
                print_func=lambda s: output_lines.append(s),
            )
            cmd.files(agent_type="claude")

        output = "\n".join(output_lines)
        assert "claude.md" in output

    def test_files_shows_default_files(self, temp_synapse_dir: Path) -> None:
        """Should list default instruction files when no agent type specified."""
        output_lines: list[str] = []

        with patch("synapse.settings.Path.cwd", return_value=temp_synapse_dir.parent):
            cmd = InstructionsCommand(
                settings_factory=lambda: create_settings_from_dir(temp_synapse_dir),
                registry_factory=lambda: MagicMock(spec=AgentRegistry),
                a2a_client_factory=lambda: MagicMock(),
                print_func=lambda s: output_lines.append(s),
            )
            # For an agent type without specific config, it falls back to default
            cmd.files(agent_type="gemini")

        output = "\n".join(output_lines)
        assert "default.md" in output

    def test_files_no_files_configured(self, tmp_path: Path) -> None:
        """Should show message when no files are configured."""
        synapse_dir = tmp_path / ".synapse"
        synapse_dir.mkdir()
        settings_file = synapse_dir / "settings.json"
        settings_file.write_text(json.dumps({"instructions": {}}))

        output_lines: list[str] = []

        with patch("synapse.settings.Path.cwd", return_value=tmp_path):
            cmd = InstructionsCommand(
                settings_factory=lambda: create_settings_from_dir(synapse_dir),
                registry_factory=lambda: MagicMock(spec=AgentRegistry),
                a2a_client_factory=lambda: MagicMock(),
                print_func=lambda s: output_lines.append(s),
            )
            cmd.files(agent_type="codex")

        output = "\n".join(output_lines)
        assert "no instruction files" in output.lower() or "none" in output.lower()


class TestInstructionsSend:
    """Tests for 'synapse instructions send' command."""

    def test_send_to_running_agent_by_profile(
        self,
        temp_synapse_dir: Path,
        temp_registry: AgentRegistry,
        mock_a2a_client: MagicMock,
    ) -> None:
        """Should send instructions to a running agent by profile name."""
        # Register a running agent
        temp_registry.register(
            "synapse-claude-8100",
            "claude",
            8100,
            status="READY",
        )

        output_lines: list[str] = []

        with patch("synapse.settings.Path.cwd", return_value=temp_synapse_dir.parent):
            cmd = InstructionsCommand(
                settings_factory=lambda: create_settings_from_dir(temp_synapse_dir),
                registry_factory=lambda: temp_registry,
                a2a_client_factory=lambda: mock_a2a_client,
                print_func=lambda s: output_lines.append(s),
            )
            result = cmd.send(target="claude", preview=False)

        assert result is True
        mock_a2a_client.send_to_local.assert_called_once()
        output = "\n".join(output_lines)
        assert "sent" in output.lower() or "success" in output.lower()

    def test_send_to_running_agent_by_agent_id(
        self,
        temp_synapse_dir: Path,
        temp_registry: AgentRegistry,
        mock_a2a_client: MagicMock,
    ) -> None:
        """Should send instructions to a running agent by agent ID."""
        # Register a running agent
        temp_registry.register(
            "synapse-claude-8100",
            "claude",
            8100,
            status="READY",
        )

        output_lines: list[str] = []

        with patch("synapse.settings.Path.cwd", return_value=temp_synapse_dir.parent):
            cmd = InstructionsCommand(
                settings_factory=lambda: create_settings_from_dir(temp_synapse_dir),
                registry_factory=lambda: temp_registry,
                a2a_client_factory=lambda: mock_a2a_client,
                print_func=lambda s: output_lines.append(s),
            )
            result = cmd.send(target="synapse-claude-8100", preview=False)

        assert result is True
        mock_a2a_client.send_to_local.assert_called_once()

    def test_send_fails_when_no_agent_running(
        self,
        temp_synapse_dir: Path,
        temp_registry: AgentRegistry,
        mock_a2a_client: MagicMock,
    ) -> None:
        """Should fail when target agent is not running."""
        output_lines: list[str] = []

        with patch("synapse.settings.Path.cwd", return_value=temp_synapse_dir.parent):
            cmd = InstructionsCommand(
                settings_factory=lambda: create_settings_from_dir(temp_synapse_dir),
                registry_factory=lambda: temp_registry,
                a2a_client_factory=lambda: mock_a2a_client,
                print_func=lambda s: output_lines.append(s),
            )
            result = cmd.send(target="claude", preview=False)

        assert result is False
        mock_a2a_client.send_to_local.assert_not_called()
        output = "\n".join(output_lines)
        assert "no running agent" in output.lower()

    def test_send_preview_mode(
        self,
        temp_synapse_dir: Path,
        temp_registry: AgentRegistry,
        mock_a2a_client: MagicMock,
    ) -> None:
        """Should show preview without sending when --preview is used."""
        temp_registry.register(
            "synapse-claude-8100",
            "claude",
            8100,
            status="READY",
        )

        output_lines: list[str] = []

        with patch("synapse.settings.Path.cwd", return_value=temp_synapse_dir.parent):
            cmd = InstructionsCommand(
                settings_factory=lambda: create_settings_from_dir(temp_synapse_dir),
                registry_factory=lambda: temp_registry,
                a2a_client_factory=lambda: mock_a2a_client,
                print_func=lambda s: output_lines.append(s),
            )
            result = cmd.send(target="claude", preview=True)

        assert result is True
        # Should NOT have sent anything
        mock_a2a_client.send_to_local.assert_not_called()
        output = "\n".join(output_lines)
        assert "preview" in output.lower()

    def test_send_to_multiple_agents_of_same_type(
        self,
        temp_synapse_dir: Path,
        temp_registry: AgentRegistry,
        mock_a2a_client: MagicMock,
    ) -> None:
        """Should send to one of the agents when multiple agents of same type exist."""
        # Register multiple claude agents
        temp_registry.register(
            "synapse-claude-8100",
            "claude",
            8100,
            status="READY",
        )
        temp_registry.register(
            "synapse-claude-8101",
            "claude",
            8101,
            status="PROCESSING",
        )

        output_lines: list[str] = []

        with patch("synapse.settings.Path.cwd", return_value=temp_synapse_dir.parent):
            cmd = InstructionsCommand(
                settings_factory=lambda: create_settings_from_dir(temp_synapse_dir),
                registry_factory=lambda: temp_registry,
                a2a_client_factory=lambda: mock_a2a_client,
                print_func=lambda s: output_lines.append(s),
            )
            result = cmd.send(target="claude", preview=False)

        assert result is True
        # Should have sent to one of the agents (order is not guaranteed)
        mock_a2a_client.send_to_local.assert_called_once()
        call_args = mock_a2a_client.send_to_local.call_args
        endpoint = call_args.kwargs.get(
            "endpoint", call_args.args[0] if call_args.args else ""
        )
        assert "8100" in endpoint or "8101" in endpoint


class TestInstructionsSendEdgeCases:
    """Edge case tests for send command."""

    def test_send_with_invalid_target(
        self,
        temp_synapse_dir: Path,
        temp_registry: AgentRegistry,
    ) -> None:
        """Should fail gracefully with invalid target."""
        output_lines: list[str] = []

        with patch("synapse.settings.Path.cwd", return_value=temp_synapse_dir.parent):
            cmd = InstructionsCommand(
                settings_factory=lambda: create_settings_from_dir(temp_synapse_dir),
                registry_factory=lambda: temp_registry,
                a2a_client_factory=lambda: MagicMock(),
                print_func=lambda s: output_lines.append(s),
            )
            result = cmd.send(target="invalid-agent-name", preview=False)

        assert result is False
        output = "\n".join(output_lines)
        assert (
            "not found" in output.lower()
            or "invalid" in output.lower()
            or "not running" in output.lower()
        )

    def test_send_handles_network_error(
        self,
        temp_synapse_dir: Path,
        temp_registry: AgentRegistry,
    ) -> None:
        """Should handle network errors gracefully."""
        temp_registry.register(
            "synapse-claude-8100",
            "claude",
            8100,
            status="READY",
        )

        mock_client = MagicMock()
        mock_client.send_to_local.return_value = None  # Simulates failure

        output_lines: list[str] = []

        with patch("synapse.settings.Path.cwd", return_value=temp_synapse_dir.parent):
            cmd = InstructionsCommand(
                settings_factory=lambda: create_settings_from_dir(temp_synapse_dir),
                registry_factory=lambda: temp_registry,
                a2a_client_factory=lambda: mock_client,
                print_func=lambda s: output_lines.append(s),
            )
            result = cmd.send(target="claude", preview=False)

        assert result is False
        output = "\n".join(output_lines)
        assert "failed" in output.lower() or "error" in output.lower()


class TestParseTarget:
    """Tests for target parsing logic."""

    def test_parse_profile_name(self, temp_synapse_dir: Path) -> None:
        """Should correctly identify profile names."""
        with patch("synapse.settings.Path.cwd", return_value=temp_synapse_dir.parent):
            cmd = InstructionsCommand(
                settings_factory=lambda: create_settings_from_dir(temp_synapse_dir),
                registry_factory=lambda: MagicMock(spec=AgentRegistry),
                a2a_client_factory=lambda: MagicMock(),
                print_func=print,
            )

            assert cmd._parse_target("claude") == ("claude", None)
            assert cmd._parse_target("gemini") == ("gemini", None)
            assert cmd._parse_target("codex") == ("codex", None)

    def test_parse_agent_id(self, temp_synapse_dir: Path) -> None:
        """Should correctly identify agent IDs."""
        with patch("synapse.settings.Path.cwd", return_value=temp_synapse_dir.parent):
            cmd = InstructionsCommand(
                settings_factory=lambda: create_settings_from_dir(temp_synapse_dir),
                registry_factory=lambda: MagicMock(spec=AgentRegistry),
                a2a_client_factory=lambda: MagicMock(),
                print_func=print,
            )

            profile, agent_id = cmd._parse_target("synapse-claude-8100")
            assert profile == "claude"
            assert agent_id == "synapse-claude-8100"

            profile, agent_id = cmd._parse_target("synapse-gemini-8110")
            assert profile == "gemini"
            assert agent_id == "synapse-gemini-8110"

    def test_parse_unknown_target(self, temp_synapse_dir: Path) -> None:
        """Should return None for unknown targets."""
        with patch("synapse.settings.Path.cwd", return_value=temp_synapse_dir.parent):
            cmd = InstructionsCommand(
                settings_factory=lambda: create_settings_from_dir(temp_synapse_dir),
                registry_factory=lambda: MagicMock(spec=AgentRegistry),
                a2a_client_factory=lambda: MagicMock(),
                print_func=print,
            )

            assert cmd._parse_target("unknown") == (None, None)
            assert cmd._parse_target("random-string") == (None, None)
