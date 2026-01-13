"""Extended tests for Synapse A2A Server."""

import os
from unittest.mock import MagicMock, mock_open, patch

import pytest
from fastapi import FastAPI

from synapse.server import lifespan, load_profile, run_dual_server


class TestServerExtended:
    """Extended tests for server.py."""

    @pytest.fixture
    def mock_profile(self):
        return {
            "command": "echo hello",
            "args": ["-v"],
            "submit_sequence": "\n",
            "idle_detection": {"strategy": "pattern", "pattern": "> "},
            "env": {"TEST_VAR": "1"},
        }

    def test_load_profile(self, mock_profile):
        """Test load_profile loads yaml correctly."""
        with (
            patch("builtins.open", mock_open(read_data="command: echo\n")),
            patch("os.path.exists", return_value=True),
        ):
            profile = load_profile("test")
            assert profile["command"] == "echo"

    def test_load_profile_not_found(self):
        """Test load_profile raises FileNotFoundError."""
        with (
            patch("os.path.exists", return_value=False),
            pytest.raises(FileNotFoundError),
        ):
            load_profile("nonexistent")

    def test_load_profile_invalid_yaml(self):
        """Test load_profile raises ValueError for invalid structure."""
        with (
            patch("builtins.open", mock_open(read_data="- list item\n")),
            patch("os.path.exists", return_value=True),
            pytest.raises(ValueError),
        ):
            load_profile("test")

    @pytest.mark.asyncio
    async def test_lifespan(self, mock_profile):
        """Test lifespan context manager."""
        app = FastAPI()

        mock_registry_cls = MagicMock()
        mock_registry_inst = MagicMock()
        mock_registry_cls.return_value = mock_registry_inst
        mock_registry_inst.get_agent_id.return_value = "agent-123"

        mock_controller_cls = MagicMock()
        mock_controller_inst = MagicMock()
        mock_controller_cls.return_value = mock_controller_inst

        with (
            patch("synapse.server.load_profile", return_value=mock_profile),
            patch("synapse.server.AgentRegistry", mock_registry_cls),
            patch("synapse.server.TerminalController", mock_controller_cls),
            patch("synapse.server.create_a2a_router") as mock_create_router,
            patch.dict(os.environ, {"SYNAPSE_PORT": "9000"}, clear=True),
        ):
            async with lifespan(app):
                # Check Registry usage
                mock_registry_inst.get_agent_id.assert_called()
                mock_registry_inst.register.assert_called_with(
                    "agent-123", "claude", 9000, status="PROCESSING"
                )

                # Check Controller usage
                mock_controller_cls.assert_called()
                # Verify env vars were merged
                call_kwargs = mock_controller_cls.call_args[1]
                assert call_kwargs["port"] == 9000
                assert call_kwargs["agent_id"] == "agent-123"
                assert call_kwargs["env"]["TEST_VAR"] == "1"
                assert call_kwargs["env"]["SYNAPSE_AGENT_ID"] == "agent-123"

                mock_controller_inst.start.assert_called()

                # Check Router usage
                mock_create_router.assert_called()

            # Check Cleanup
            mock_controller_inst.stop.assert_called()
            mock_registry_inst.unregister.assert_called_with("agent-123")

    @pytest.mark.asyncio
    async def test_lifespan_legacy_profile(self):
        """Test lifespan with legacy profile (idle_regex)."""
        app = FastAPI()
        legacy_profile = {
            "command": "echo hello",
            "idle_regex": "> ",
        }

        mock_registry_cls = MagicMock()
        mock_controller_cls = MagicMock()

        with (
            patch("synapse.server.load_profile", return_value=legacy_profile),
            patch("synapse.server.AgentRegistry", mock_registry_cls),
            patch("synapse.server.TerminalController", mock_controller_cls),
            patch("synapse.server.create_a2a_router"),
            patch.dict(os.environ, {"SYNAPSE_PORT": "9000"}, clear=True),
        ):
            async with lifespan(app):
                pass

            # Verify idle_regex was converted to idle_detection
            call_kwargs = mock_controller_cls.call_args[1]
            assert call_kwargs["idle_detection"] == {
                "strategy": "pattern",
                "pattern": "> ",
                "timeout": 1.5,
            }

    @patch("uvicorn.Server")
    @patch("threading.Thread")
    def test_run_dual_server(self, mock_thread, mock_server):
        """Test run_dual_server starts TCP and UDS servers."""
        app = FastAPI()

        # Mock resolve_uds_path to return a mock path object
        mock_uds_path = MagicMock()
        mock_uds_path.exists.return_value = True

        with patch("synapse.server.resolve_uds_path", return_value=mock_uds_path):
            run_dual_server(app, "127.0.0.1", 8000, agent_id="agent-123")

        # Check that uvicorn.Server was instantiated twice (TCP and UDS)
        assert mock_server.call_count == 2

        # Check that UDS path was cleaned up
        mock_uds_path.unlink.assert_called()

        # Check that thread was started for UDS
        mock_thread.assert_called()
        mock_thread.return_value.start.assert_called()

        # Check that run() was called on instances
        # We can't easily check which instance run() was called on without more complex mocking,
        # but at least one run() (TCP) is called directly, and one via thread (UDS)
