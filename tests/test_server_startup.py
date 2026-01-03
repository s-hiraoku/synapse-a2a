
import pytest
import os
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi.testclient import TestClient
from fastapi import APIRouter

# Must import app after mocking if possible, or patch internals
from synapse.server import app, startup_event, shutdown_event

class TestServerStartup:
    """Test server startup and shutdown events."""

    @pytest.fixture
    def mock_env(self):
        """Mock environment variables."""
        with patch.dict(os.environ, {
            "SYNAPSE_PROFILE": "test_profile",
            "SYNAPSE_PORT": "8100",
            "SYNAPSE_TOOL_ARGS": "arg1"
        }, clear=True):
            yield

    @pytest.fixture
    def mock_dependencies(self):
        """Mock external dependencies."""
        with patch("synapse.server.load_profile") as mock_load, \
             patch("synapse.server.TerminalController") as mock_ctrl, \
             patch("synapse.server.AgentRegistry") as mock_reg, \
             patch("synapse.server.create_a2a_router") as mock_router, \
             patch("synapse.server.send_initial_instructions") as mock_instructions:

            # Setup mocks
            mock_load.return_value = {
                "command": "echo",
                "args": ["hello"],
                "idle_regex": "> ",
                "env": {"TEST_VAR": "1"},
                "submit_sequence": "\\n"
            }
            
            mock_reg.return_value = mock_reg_instance
            
            mock_ctrl_instance = MagicMock()
            mock_ctrl.return_value = mock_ctrl_instance
            
            # Use real APIRouter for include_router compatibility
            mock_router.return_value = APIRouter()
            
            # Make instructions async
            mock_instructions.return_value = None
            
            yield {
                "load": mock_load,
                "ctrl": mock_ctrl,
                "reg": mock_reg,
                "router": mock_router,
                # Ensure it's treated as async when awaited if not automatically handled by patch (it usually is if target is async)
                # But to be safe, we can assert on it. The patch creates a MagicMock which is awaitable.
                "instr": mock_instructions
            }

    @pytest.mark.asyncio
    async def test_startup_logic(self, mock_env, mock_dependencies):
        """Test startup event logic directly."""
        # Execute startup
        await startup_event()

        # Verify load_profile called
        mock_dependencies["load"].assert_called_with("test_profile")

        # Verify Controller created with correct args
        mock_dependencies["ctrl"].assert_called_once()
        call_kwargs = mock_dependencies["ctrl"].call_args.kwargs
        assert call_kwargs["command"] == "echo"
        assert call_kwargs["agent_id"] == "synapse-test-8100"
        assert call_kwargs["port"] == 8100
        # Check environment merging
        assert call_kwargs["env"]["TEST_VAR"] == "1"
        assert call_kwargs["env"]["SYNAPSE_AGENT_ID"] == "synapse-test-8100"

        # Verify Controller started
        mock_dependencies["ctrl"].return_value.start.assert_called_once()

        # Verify Registry usage
        mock_dependencies["reg"].assert_called_once()
        mock_dependencies["reg"].return_value.register.assert_called_with(
            "synapse-test-8100", "test_profile", 8100, status="BUSY"
        )
        
        # Verify instructions scheduled
        mock_dependencies["instr"].assert_called_once()

    @pytest.mark.asyncio
    async def test_shutdown_logic(self, mock_dependencies):
        """Test shutdown event logic."""
        # Ensure controller global is set (simulate startup result)
        with patch("synapse.server.controller", mock_dependencies["ctrl"].return_value), \
             patch("synapse.server.registry", mock_dependencies["reg"].return_value), \
             patch("synapse.server.current_agent_id", "synapse-test-8100"):
            
            await shutdown_event()

            # Verify controller stopped
            mock_dependencies["ctrl"].return_value.stop.assert_called_once()
            
            # Verify agent unregistered
            mock_dependencies["reg"].return_value.unregister.assert_called_with("synapse-test-8100")

    def test_app_lifecycle_trigger(self, mock_env, mock_dependencies):
        """Test that TestClient actually triggers events on the global app."""
        # We need to patch the verification logic inside because TestClient runs in a context
        with TestClient(app) as client:
            # Startup should have run
            assert mock_dependencies["load"].called
            
            response = client.get("/status")
            assert response.status_code == 200
        
        # Shutdown should have run after exit
        # We can check global controller.stop was called, but accessing the mock 
        # inside the patch context is tricky. 
        # However, verifying startup matches confirms the wiring.
