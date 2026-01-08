"""Tests for Synapse Server lifespan and profile loading."""

from unittest.mock import MagicMock, patch

import pytest
import yaml
from fastapi import FastAPI

from synapse.server import lifespan, load_profile

# ============================================================
# Profile Loading Tests
# ============================================================


class TestLoadProfile:
    """Tests for load_profile function."""

    def test_load_profile_success(self, tmp_path):
        """Should load valid profile."""
        profile_content = (
            'command: "bash"\n'
            'args: ["-c", "echo hello"]\n'
            "idle_regex: '$'\n"
            'submit_sequence: "\\n"\n'
        )
        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()
        profile_path = profiles_dir / "test.yaml"
        profile_path.write_text(profile_content)

        with patch("synapse.server.os.path.dirname") as mock_dirname:
            mock_dirname.return_value = str(tmp_path)

            profile = load_profile("test")

            assert profile["command"] == "bash"
            assert profile["idle_regex"] == "$"
            assert profile["submit_sequence"] == "\n"

    def test_load_profile_not_found(self, tmp_path):
        """Should raise FileNotFoundError for missing profile."""
        with patch("synapse.server.os.path.dirname") as mock_dirname:
            mock_dirname.return_value = str(tmp_path)

            with pytest.raises(FileNotFoundError):
                load_profile("nonexistent")

    def test_load_profile_invalid_yaml(self, tmp_path):
        """Should raise ValueError for invalid YAML content."""
        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()
        profile_path = profiles_dir / "invalid.yaml"
        profile_path.write_text("invalid: [unclosed list")

        with patch("synapse.server.os.path.dirname") as mock_dirname:
            mock_dirname.return_value = str(tmp_path)

            with pytest.raises(yaml.YAMLError):  # yaml.safe_load raises parser errors
                load_profile("invalid")

    def test_load_profile_not_dict(self, tmp_path):
        """Should raise ValueError if profile is not a dictionary."""
        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()
        profile_path = profiles_dir / "list.yaml"
        profile_path.write_text("- item1\n- item2")

        with patch("synapse.server.os.path.dirname") as mock_dirname:
            mock_dirname.return_value = str(tmp_path)

            with pytest.raises(ValueError, match="must be a dictionary"):
                load_profile("list")


# ============================================================
# Lifespan Tests
# ============================================================


class TestLifespan:
    """Tests for server lifespan context manager."""

    @pytest.fixture
    def mock_dependencies(self):
        """Mock all external dependencies used in lifespan."""
        with (
            patch("synapse.server.load_profile") as mock_load,
            patch("synapse.server.AgentRegistry") as mock_registry_cls,
            patch("synapse.server.TerminalController") as mock_controller_cls,
            patch("synapse.server.create_a2a_router") as mock_router,
            patch("synapse.server.os") as mock_os,
        ):
            # Setup load_profile
            mock_load.return_value = {
                "command": "echo",
                "args": ["test"],
                "submit_sequence": "\n",
                "idle_regex": "\\$",
                "env": {"TEST_VAR": "1"},
            }

            # Setup Registry
            mock_registry = mock_registry_cls.return_value
            mock_registry.get_agent_id.return_value = "agent-123"

            # Setup Controller
            mock_controller = mock_controller_cls.return_value

            # Setup OS environ
            mock_os.environ = MagicMock()
            mock_os.environ.copy.return_value = {}

            def get_env(key, default=None):
                if key == "SYNAPSE_PROFILE":
                    return "test_profile"
                if key == "SYNAPSE_PORT":
                    return "8100"
                if key == "SYNAPSE_TOOL_ARGS":
                    return "--arg\x00value"
                return default

            mock_os.environ.get.side_effect = get_env

            yield {
                "load_profile": mock_load,
                "registry": mock_registry,
                "controller": mock_controller,
                "create_router": mock_router,
                "controller_cls": mock_controller_cls,
                "os": mock_os,
            }

    @pytest.mark.asyncio
    async def test_lifespan_startup_and_shutdown(self, mock_dependencies):
        """Should initialize components on startup and cleanup on shutdown."""
        app = FastAPI(lifespan=lifespan)

        async with lifespan(app):
            # Startup checks
            mock_dependencies["load_profile"].assert_called_with("test_profile")

            # Controller initialization
            mock_dependencies["controller_cls"].assert_called_once()
            call_kwargs = mock_dependencies["controller_cls"].call_args.kwargs
            assert call_kwargs["command"] == "echo"
            assert call_kwargs["agent_id"] == "agent-123"
            assert call_kwargs["port"] == 8100

            # Verify tool args merged
            assert "--arg" in call_kwargs["args"]

            # Start called
            mock_dependencies["controller"].start.assert_called_once()

            # Registration
            mock_dependencies["registry"].register.assert_called_once()

            # Router creation
            mock_dependencies["create_router"].assert_called_once()

        # Shutdown checks
        mock_dependencies["controller"].stop.assert_called_once()
        mock_dependencies["registry"].unregister.assert_called_with("agent-123")

    @pytest.mark.asyncio
    async def test_lifespan_idle_detection_config(self, mock_dependencies):
        """Should handle idle_detection configuration correctly."""
        # Update profile to have explicit idle_detection
        mock_dependencies["load_profile"].return_value = {
            "command": "echo",
            "idle_detection": {"strategy": "pattern", "pattern": ">", "timeout": 2.0},
        }

        app = FastAPI(lifespan=lifespan)

        async with lifespan(app):
            call_kwargs = mock_dependencies["controller_cls"].call_args.kwargs
            assert call_kwargs["idle_detection"]["pattern"] == ">"
            assert (
                call_kwargs["idle_regex"] is None
            )  # Should be None if idle_detection is present

    @pytest.mark.asyncio
    async def test_lifespan_legacy_idle_regex(self, mock_dependencies):
        """Should handle legacy idle_regex correctly."""
        # Update profile to have only idle_regex
        mock_dependencies["load_profile"].return_value = {
            "command": "echo",
            "idle_regex": ">",
        }

        app = FastAPI(lifespan=lifespan)

        async with lifespan(app):
            call_kwargs = mock_dependencies["controller_cls"].call_args.kwargs
            # Should construct idle_detection from regex
            assert call_kwargs["idle_detection"]["pattern"] == ">"
            assert call_kwargs["idle_regex"] is None  # Logic converts it
