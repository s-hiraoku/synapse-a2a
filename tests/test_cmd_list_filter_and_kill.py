"""Tests for synapse list --working-dir filter and kill functionality."""

import json
import signal
from unittest.mock import MagicMock, patch

import pytest

from synapse.commands.list import ListCommand
from synapse.registry import AgentRegistry


@pytest.fixture
def temp_registry(tmp_path):
    """Create a test registry with temp directory."""
    reg = AgentRegistry()
    reg.registry_dir = tmp_path / "a2a_test_list_filter"
    reg.registry_dir.mkdir(parents=True, exist_ok=True)
    yield reg


def _create_list_command(
    registry_factory=None,
    is_process_alive=lambda p: True,
    is_port_open=lambda host, port, timeout=0.5: True,
):
    """Create a ListCommand with mock dependencies."""
    return ListCommand(
        registry_factory=registry_factory or (lambda: MagicMock(spec=AgentRegistry)),
        is_process_alive=is_process_alive,
        is_port_open=is_port_open,
        clear_screen=lambda: None,
        time_module=MagicMock(),
        print_func=print,
    )


def _register_agent_with_working_dir(
    registry: AgentRegistry, agent_id: str, agent_type: str, port: int, working_dir: str
):
    """Register an agent and set its working_dir."""
    registry.register(agent_id, agent_type, port, status="READY")
    file_path = registry.registry_dir / f"{agent_id}.json"
    with open(file_path) as f:
        data = json.load(f)
    data["working_dir"] = working_dir
    with open(file_path, "w") as f:
        json.dump(data, f)


class TestWorkingDirFilter:
    """Tests for --working-dir filter functionality."""

    def test_working_dir_filter_partial_match(self, temp_registry):
        """Test --working-dir partial match filtering."""
        # Register two agents with different working directories
        _register_agent_with_working_dir(
            temp_registry,
            "synapse-claude-8100",
            "claude",
            8100,
            "/path/to/project-a",
        )
        _register_agent_with_working_dir(
            temp_registry,
            "synapse-gemini-8110",
            "gemini",
            8110,
            "/path/to/project-b",
        )

        list_cmd = _create_list_command()

        # Filter by "project-a" should return only one agent
        agents, _, _ = list_cmd._get_agent_data(
            temp_registry, working_dir_filter="project-a"
        )

        assert len(agents) == 1
        assert agents[0]["agent_type"] == "claude"
        assert agents[0]["working_dir_full"] == "/path/to/project-a"

    def test_working_dir_filter_case_insensitive(self, temp_registry):
        """Test --working-dir is case insensitive."""
        _register_agent_with_working_dir(
            temp_registry,
            "synapse-claude-8100",
            "claude",
            8100,
            "/path/to/MyProject",
        )

        list_cmd = _create_list_command()

        # Filter with different cases should all match
        for filter_str in ["myproject", "MYPROJECT", "MyProject", "MYPROJ"]:
            agents, _, _ = list_cmd._get_agent_data(
                temp_registry, working_dir_filter=filter_str
            )
            assert len(agents) == 1, f"Failed for filter: {filter_str}"

    def test_working_dir_filter_no_match(self, temp_registry):
        """Test --working-dir with no matching agents."""
        _register_agent_with_working_dir(
            temp_registry,
            "synapse-claude-8100",
            "claude",
            8100,
            "/path/to/project",
        )

        list_cmd = _create_list_command()

        # Filter that doesn't match anything
        agents, _, _ = list_cmd._get_agent_data(
            temp_registry, working_dir_filter="nonexistent"
        )

        assert len(agents) == 0

    def test_working_dir_filter_matches_full_path(self, temp_registry):
        """Test --working-dir matches against full path."""
        _register_agent_with_working_dir(
            temp_registry,
            "synapse-claude-8100",
            "claude",
            8100,
            "/home/user/projects/my-app",
        )

        list_cmd = _create_list_command()

        # Filter by parent directory should match
        agents, _, _ = list_cmd._get_agent_data(
            temp_registry, working_dir_filter="projects"
        )

        assert len(agents) == 1

    def test_working_dir_filter_none_returns_all(self, temp_registry):
        """Test that None filter returns all agents."""
        _register_agent_with_working_dir(
            temp_registry,
            "synapse-claude-8100",
            "claude",
            8100,
            "/path/to/project-a",
        )
        _register_agent_with_working_dir(
            temp_registry,
            "synapse-gemini-8110",
            "gemini",
            8110,
            "/path/to/project-b",
        )

        list_cmd = _create_list_command()

        # No filter should return all agents
        agents, _, _ = list_cmd._get_agent_data(temp_registry, working_dir_filter=None)

        assert len(agents) == 2

    def test_working_dir_filter_multiple_matches(self, temp_registry):
        """Test --working-dir with multiple matching agents."""
        _register_agent_with_working_dir(
            temp_registry,
            "synapse-claude-8100",
            "claude",
            8100,
            "/home/user/synapse-project",
        )
        _register_agent_with_working_dir(
            temp_registry,
            "synapse-gemini-8110",
            "gemini",
            8110,
            "/home/user/synapse-app",
        )
        _register_agent_with_working_dir(
            temp_registry,
            "synapse-codex-8120",
            "codex",
            8120,
            "/home/user/other-project",
        )

        list_cmd = _create_list_command()

        # Filter by "synapse" should match two agents
        agents, _, _ = list_cmd._get_agent_data(
            temp_registry, working_dir_filter="synapse"
        )

        assert len(agents) == 2
        agent_types = {a["agent_type"] for a in agents}
        assert agent_types == {"claude", "gemini"}

    def test_filter_by_agent_type(self, temp_registry):
        """Test filter matches agent_type (TYPE column)."""
        _register_agent_with_working_dir(
            temp_registry,
            "synapse-claude-8100",
            "claude",
            8100,
            "/home/user/project-a",
        )
        _register_agent_with_working_dir(
            temp_registry,
            "synapse-gemini-8110",
            "gemini",
            8110,
            "/home/user/project-b",
        )
        _register_agent_with_working_dir(
            temp_registry,
            "synapse-codex-8120",
            "codex",
            8120,
            "/home/user/project-c",
        )

        list_cmd = _create_list_command()

        # Filter by "claude" should match agent_type
        agents, _, _ = list_cmd._get_agent_data(
            temp_registry, working_dir_filter="claude"
        )

        assert len(agents) == 1
        assert agents[0]["agent_type"] == "claude"

    def test_filter_matches_type_or_dir(self, temp_registry):
        """Test filter matches either TYPE or WORKING_DIR."""
        _register_agent_with_working_dir(
            temp_registry,
            "synapse-claude-8100",
            "claude",
            8100,
            "/home/user/gemini-project",  # DIR contains "gemini"
        )
        _register_agent_with_working_dir(
            temp_registry,
            "synapse-gemini-8110",
            "gemini",  # TYPE is "gemini"
            8110,
            "/home/user/other-project",
        )

        list_cmd = _create_list_command()

        # Filter by "gemini" should match both (one by TYPE, one by DIR)
        agents, _, _ = list_cmd._get_agent_data(
            temp_registry, working_dir_filter="gemini"
        )

        assert len(agents) == 2
        agent_types = {a["agent_type"] for a in agents}
        assert agent_types == {"claude", "gemini"}


class TestKillAgent:
    """Tests for kill agent functionality."""

    def test_kill_agent_sends_sigterm(self, temp_registry):
        """Test _kill_agent sends SIGTERM to process."""
        _register_agent_with_working_dir(
            temp_registry,
            "synapse-claude-8100",
            "claude",
            8100,
            "/path/to/project",
        )

        # Add PID to the agent data
        file_path = temp_registry.registry_dir / "synapse-claude-8100.json"
        with open(file_path) as f:
            data = json.load(f)
        data["pid"] = 12345
        with open(file_path, "w") as f:
            json.dump(data, f)

        list_cmd = _create_list_command(registry_factory=lambda: temp_registry)

        agent = {
            "agent_id": "synapse-claude-8100",
            "pid": 12345,
        }

        with patch("os.kill") as mock_kill:
            list_cmd._kill_agent(temp_registry, agent)
            mock_kill.assert_called_once_with(12345, signal.SIGTERM)

    def test_kill_agent_unregisters_from_registry(self, temp_registry):
        """Test _kill_agent unregisters agent from registry."""
        _register_agent_with_working_dir(
            temp_registry,
            "synapse-claude-8100",
            "claude",
            8100,
            "/path/to/project",
        )

        list_cmd = _create_list_command(registry_factory=lambda: temp_registry)

        agent = {
            "agent_id": "synapse-claude-8100",
            "pid": 12345,
        }

        with patch("os.kill"):
            list_cmd._kill_agent(temp_registry, agent)

        # Agent should be unregistered
        agents = temp_registry.list_agents()
        assert "synapse-claude-8100" not in agents

    def test_kill_agent_handles_process_not_found(self, temp_registry):
        """Test _kill_agent handles ProcessLookupError gracefully."""
        _register_agent_with_working_dir(
            temp_registry,
            "synapse-claude-8100",
            "claude",
            8100,
            "/path/to/project",
        )

        list_cmd = _create_list_command(registry_factory=lambda: temp_registry)

        agent = {
            "agent_id": "synapse-claude-8100",
            "pid": 12345,
        }

        with patch("os.kill", side_effect=ProcessLookupError):
            # Should not raise exception
            list_cmd._kill_agent(temp_registry, agent)

        # Agent should still be unregistered (cleanup)
        agents = temp_registry.list_agents()
        assert "synapse-claude-8100" not in agents

    def test_kill_agent_skips_invalid_pid(self, temp_registry):
        """Test _kill_agent skips agents with invalid PID."""
        list_cmd = _create_list_command(registry_factory=lambda: temp_registry)

        # Agent with no PID
        agent = {
            "agent_id": "synapse-claude-8100",
            "pid": "-",
        }

        with patch("os.kill") as mock_kill:
            list_cmd._kill_agent(temp_registry, agent)
            mock_kill.assert_not_called()

        # Agent with None PID
        agent = {
            "agent_id": "synapse-claude-8100",
            "pid": None,
        }

        with patch("os.kill") as mock_kill:
            list_cmd._kill_agent(temp_registry, agent)
            mock_kill.assert_not_called()


class TestKillConfirmFooter:
    """Tests for kill confirmation footer in Rich TUI."""

    def test_footer_shows_kill_hint_when_selected(self):
        """Test footer shows 'k:kill' when agent is selected."""
        from synapse.commands.renderers.rich_renderer import RichRenderer

        renderer = RichRenderer()
        footer = renderer.build_footer(
            interactive=True,
            agent_count=2,
            jump_available=True,
            has_selection=True,
            kill_confirm_agent=None,
        )

        footer_str = str(footer)
        assert "k" in footer_str
        assert "kill" in footer_str

    def test_footer_shows_kill_confirmation(self):
        """Test footer shows kill confirmation dialog."""
        from synapse.commands.renderers.rich_renderer import RichRenderer

        renderer = RichRenderer()
        agent = {
            "agent_id": "synapse-claude-8100",
            "pid": 12345,
        }
        footer = renderer.build_footer(
            interactive=True,
            agent_count=2,
            jump_available=True,
            has_selection=True,
            kill_confirm_agent=agent,
        )

        footer_str = str(footer)
        assert "Kill" in footer_str
        assert "synapse-claude-8100" in footer_str
        assert "12345" in footer_str
        assert "y" in footer_str
        assert "n" in footer_str

    def test_footer_no_kill_hint_without_selection(self):
        """Test footer does not show 'k:kill' when no agent selected."""
        from synapse.commands.renderers.rich_renderer import RichRenderer

        renderer = RichRenderer()
        footer = renderer.build_footer(
            interactive=True,
            agent_count=2,
            jump_available=True,
            has_selection=False,
            kill_confirm_agent=None,
        )

        footer_str = str(footer)
        # Should not show kill when nothing is selected
        assert "k:kill" not in footer_str


class TestFilterModeFooter:
    """Tests for filter mode footer display."""

    def test_footer_shows_filter_input_mode(self):
        """Test footer shows filter input mode."""
        from synapse.commands.renderers.rich_renderer import RichRenderer

        renderer = RichRenderer()
        footer = renderer.build_footer(
            interactive=True,
            agent_count=2,
            jump_available=True,
            has_selection=False,
            filter_mode=True,
            filter_text="synapse",
        )

        footer_str = str(footer)
        assert "Filter (TYPE/DIR):" in footer_str
        assert "synapse" in footer_str
        assert "Enter" in footer_str
        assert "ESC" in footer_str

    def test_title_shows_active_filter(self):
        """Test title shows active filter when not in filter mode."""
        from io import StringIO

        from rich.console import Console

        from synapse.commands.renderers.rich_renderer import RichRenderer

        output = StringIO()
        console = Console(file=output, force_terminal=True, width=120)
        renderer = RichRenderer(console=console)

        display = renderer.render_display(
            agents=[
                {
                    "agent_type": "claude",
                    "port": 8100,
                    "status": "READY",
                    "pid": 123,
                    "working_dir": "project",
                    "working_dir_full": "/path/project",
                    "endpoint": "http://localhost:8100",
                    "transport": "-",
                }
            ],
            version="0.1.0",
            timestamp="2024-01-01 12:00:00",
            interactive=True,
            filter_text="project",
            filter_mode=False,
        )

        console.print(display)
        output_str = output.getvalue()
        assert "Filter: project" in output_str

    def test_footer_shows_filter_key_hint(self):
        """Test footer shows '/' key hint for filter."""
        from synapse.commands.renderers.rich_renderer import RichRenderer

        renderer = RichRenderer()
        footer = renderer.build_footer(
            interactive=True,
            agent_count=2,
            jump_available=True,
            has_selection=False,
            filter_mode=False,
            filter_text="",
        )

        footer_str = str(footer)
        assert "/" in footer_str
        assert "filter" in footer_str
