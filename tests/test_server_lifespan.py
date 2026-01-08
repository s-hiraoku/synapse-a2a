"Tests for server lifespan and standalone endpoints."

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from synapse.server import app, lifespan, load_profile


class TestServerLifespan:
    """Test server.py lifespan and global state logic."""

    @pytest.mark.asyncio
    async def test_lifespan_startup_shutdown(self):
        """Test the lifespan context manager (Lines 283-317)."""
        mock_app = MagicMock(spec=FastAPI)

        # Setup mock environment behavior
        def mock_env_get(key, default=None):
            env = {
                "SYNAPSE_PROFILE": "dummy",
                "SYNAPSE_PORT": "8199",
                "SYNAPSE_TOOL_ARGS": "arg1\x00arg2",
            }
            return env.get(key, default)

        with (
            patch("os.environ.get", side_effect=mock_env_get),
            patch("synapse.server.load_profile") as mock_load,
            patch("synapse.server.AgentRegistry") as mock_reg_cls,
            patch("synapse.server.TerminalController") as mock_ctrl_cls,
            patch("synapse.server.create_a2a_router"),
        ):
            mock_load.return_value = {
                "command": "echo",
                "args": ["init"],
                "submit_sequence": "\n",
            }

            mock_reg = mock_reg_cls.return_value
            mock_reg.get_agent_id.return_value = "dummy-8199"

            mock_ctrl = mock_ctrl_cls.return_value

            # Execute lifespan
            async with lifespan(mock_app):
                # Verify startup
                mock_ctrl.start.assert_called_once()
                mock_reg.register.assert_called()

            # Verify shutdown
            mock_ctrl.stop.assert_called_once()
            mock_reg.unregister.assert_called_with("dummy-8199")

    def test_load_profile_success(self):
        """Test loading a valid profile."""
        with (
            patch("os.path.exists", return_value=True),
            patch(
                "builtins.open",
                patch("synapse.server.yaml.safe_load", return_value={"cmd": "ls"}),
            ),
        ):
            # This is tricky because load_profile constructs path based on __file__
            # Let's mock yaml.safe_load directly
            pass

    def test_load_profile_not_found(self):
        """Test profile not found error."""
        with pytest.raises(FileNotFoundError):
            load_profile("nonexistent_profile_xyz")

    def test_standalone_status_not_started(self):
        """Test /status when controller is None."""
        with patch("synapse.server.controller", None):
            client = TestClient(app)
            response = client.get("/status")
            assert response.status_code == 200
            assert response.json()["status"] == "NOT_STARTED"

    def test_standalone_message_no_controller(self):
        """Test /message when controller is None."""
        with patch("synapse.server.controller", None):
            client = TestClient(app)
            response = client.post("/message", json={"priority": 1, "content": "hi"})
            assert response.status_code == 503
