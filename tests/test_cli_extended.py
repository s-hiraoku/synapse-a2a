"""Extended tests for CLI commands in synapse/cli.py."""

import shutil
from unittest.mock import MagicMock, patch

from synapse.cli import (
    _stop_agent,
    cmd_list,
    cmd_logs,
    install_skills,
)
from synapse.registry import AgentRegistry


class TestCliExtended:
    """Extended tests for CLI."""

    def test_install_skills_success(self, tmp_path):
        """Test install_skills successfully copies files."""
        # Setup source structure
        pkg_dir = tmp_path / "pkg"
        pkg_dir.mkdir()

        # Mock synapse.__file__
        synapse_file = pkg_dir / "synapse" / "__init__.py"
        synapse_file.parent.mkdir()
        synapse_file.touch()

        # Create source skills
        source_skills = synapse_file.parent / "skills"
        source_skills.mkdir()
        (source_skills / "synapse-a2a").mkdir()
        (source_skills / "synapse-a2a" / "skill.json").touch()
        (source_skills / "delegation").mkdir()

        # Setup target structure (home dir)
        home_dir = tmp_path / "home"
        home_dir.mkdir()

        with (
            patch("synapse.cli.Path.home", return_value=home_dir),
            patch("synapse.cli.shutil.copytree", side_effect=shutil.copytree),
            patch("builtins.print"),
        ):
            # We need to mock the import of synapse to return our mocked file path
            mock_synapse = MagicMock()
            mock_synapse.__file__ = str(synapse_file)
            with patch.dict("sys.modules", {"synapse": mock_synapse}):
                install_skills()

        # Verify copies
        claude_skills = home_dir / ".claude" / "skills"
        assert (claude_skills / "synapse-a2a").exists()
        assert (claude_skills / "delegation").exists()

        codex_skills = home_dir / ".codex" / "skills"
        assert (codex_skills / "synapse-a2a").exists()
        assert (codex_skills / "delegation").exists()

    def test_stop_agent_cleans_registry_on_process_error(self):
        """Test _stop_agent removes from registry if process not found."""
        registry = MagicMock(spec=AgentRegistry)
        info = {"agent_id": "agent-1", "pid": 12345}

        with patch("synapse.cli.os.kill", side_effect=ProcessLookupError):
            _stop_agent(registry, info)

        registry.unregister.assert_called_with("agent-1")

    def test_cmd_list_runs(self):
        """Test cmd_list instantiates and runs ListCommand."""
        args = MagicMock()

        with patch("synapse.cli.ListCommand") as mock_list_cls:
            cmd_list(args)

            mock_list_cls.assert_called()
            mock_list_cls.return_value.run.assert_called_with(args)

    def test_cmd_logs_path_expansion(self):
        """Test cmd_logs expands user path correctly."""
        args = MagicMock()
        args.profile = "test-profile"
        args.follow = False
        args.lines = 10

        with (
            patch("synapse.cli.os.path.expanduser") as mock_expand,
            patch("synapse.cli.os.path.exists", return_value=True),
            patch("synapse.cli.subprocess.run") as mock_run,
        ):
            mock_expand.side_effect = lambda p: p.replace("~", "/mock/home")

            cmd_logs(args)

            mock_expand.assert_called_with("~/.synapse/logs/test-profile.log")
            cmd_args = mock_run.call_args[0][0]
            assert "/mock/home/.synapse/logs/test-profile.log" in cmd_args
