import argparse
import os
import sys
import threading
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
import yaml
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from synapse.a2a_compat import Message, TaskStore, TextPart, create_a2a_router
from synapse.controller import TerminalController
from synapse.registry import AgentRegistry, resolve_uds_path

# Global controller and registry instances (for standalone mode)
controller: TerminalController | None = None
registry: AgentRegistry | None = None
current_agent_id: str | None = None
agent_port: int = 8100
agent_profile: str = "claude"
submit_sequence: str = "\n"  # Default submit sequence


def load_profile(profile_name: str) -> dict:
    """Load agent profile configuration from YAML file."""
    profile_path = os.path.join(
        os.path.dirname(__file__), "profiles", f"{profile_name}.yaml"
    )
    if not os.path.exists(profile_path):
        raise FileNotFoundError(f"Profile {profile_name} not found")

    with open(profile_path) as f:
        result = yaml.safe_load(f)
        if not isinstance(result, dict):
            raise ValueError(f"Profile {profile_name} must be a dictionary")
        return result


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Lifespan context manager for startup and shutdown events."""
    global \
        controller, \
        registry, \
        current_agent_id, \
        agent_port, \
        agent_profile, \
        submit_sequence

    # Get profile and port from environment variables (set by CLI args)
    profile_name = os.environ.get("SYNAPSE_PROFILE", agent_profile)
    agent_port = int(os.environ.get("SYNAPSE_PORT", str(agent_port)))
    agent_profile = profile_name

    # Get tool args from environment (null-separated)
    tool_args_str = os.environ.get("SYNAPSE_TOOL_ARGS", "")
    tool_args = tool_args_str.split("\x00") if tool_args_str else []

    profile = load_profile(profile_name)

    # Load submit sequence from profile (decode escape sequences)
    submit_sequence = (
        profile.get("submit_sequence", "\n").encode().decode("unicode_escape")
    )

    # Parse idle detection config (with backward compatibility)
    idle_detection = profile.get("idle_detection", {})
    if not idle_detection:
        # Legacy mode: Use top-level idle_regex
        idle_regex = profile.get("idle_regex")
        if idle_regex:
            idle_detection = {
                "strategy": "pattern",
                "pattern": idle_regex,
                "timeout": 1.5,
            }

    # Merge profile args with CLI tool args
    profile_args = profile.get("args", [])
    all_args = profile_args + tool_args

    # Merge profile env with system env
    env = os.environ.copy()
    if "env" in profile:
        env.update(profile["env"])

    # Registry Registration (before controller to pass agent_id)
    registry = AgentRegistry()
    current_agent_id = registry.get_agent_id(profile_name, agent_port)

    # Set sender identification environment variables for child processes
    # These are used by CLI tools (a2a.py) to auto-detect sender info
    env["SYNAPSE_AGENT_ID"] = current_agent_id
    env["SYNAPSE_AGENT_TYPE"] = profile_name
    env["SYNAPSE_PORT"] = str(agent_port)

    controller = TerminalController(
        command=profile["command"],
        args=all_args,
        idle_detection=idle_detection if idle_detection else None,
        idle_regex=(
            profile.get("idle_regex") if not idle_detection else None
        ),  # Backward compat
        env=env,
        agent_id=current_agent_id,
        agent_type=profile_name,
        submit_seq=submit_sequence,
        port=agent_port,
        registry=registry,
    )
    controller.start()

    registry.register(current_agent_id, profile_name, agent_port, status="PROCESSING")

    # Add Google A2A compatible routes
    a2a_router = create_a2a_router(
        controller,
        profile_name,
        agent_port,
        submit_sequence,
        current_agent_id,
        registry,
    )
    app.include_router(a2a_router)

    print(f"Started agent: {profile['command']}")
    print(f"Registered Agent ID: {current_agent_id}")
    print(f"Submit sequence: {repr(submit_sequence)}")
    print(
        f"Agent Card available at: http://localhost:{agent_port}/.well-known/agent.json"
    )

    # Note: Initial instructions are sent by controller._send_identity_instruction()
    # when the agent first reaches IDLE state (detected by idle_regex)

    yield  # Application runs here

    # Shutdown
    if controller:
        controller.stop()
    if registry and current_agent_id:
        registry.unregister(current_agent_id)


# Global app instance for standalone mode
app = FastAPI(
    title="Synapse A2A Server",
    description="CLI agent wrapper with Google A2A protocol compatibility",
    version="1.0.0",
    lifespan=lifespan,
)


class MessageRequest(BaseModel):
    priority: int
    content: str


def _send_legacy_message(
    ctrl: TerminalController | None,
    task_store: TaskStore,
    msg: MessageRequest,
    submit_seq: str,
) -> dict:
    """Send a legacy /message request using a TaskStore for tracking."""
    if not ctrl:
        raise HTTPException(status_code=503, detail="Agent not running")

    # Convert to A2A Message format internally
    a2a_message = Message(role="user", parts=[TextPart(text=msg.content)])

    # Create task for tracking
    task = task_store.create(a2a_message)

    if msg.priority >= 5:
        ctrl.interrupt()

    # Update task status to working
    task_store.update_status(task.id, "working")

    # Use the profile's submit sequence (e.g., \r for TUI apps, \n for readline)
    try:
        ctrl.write(msg.content, submit_seq=submit_seq)
    except Exception as e:
        task_store.update_status(task.id, "failed")
        raise HTTPException(status_code=500, detail=f"Write failed: {str(e)}") from e

    return {"status": "sent", "priority": msg.priority, "task_id": task.id}


def _get_standalone_task_store() -> TaskStore:
    """Return the singleton TaskStore for standalone mode."""
    global standalone_task_store
    if standalone_task_store is None:
        standalone_task_store = TaskStore()
    return standalone_task_store


def create_app(
    ctrl: TerminalController,
    reg: AgentRegistry,
    agent_id: str,
    port: int,
    submit_seq: str = "\n",
    agent_type: str = "claude",
) -> FastAPI:
    """Create a FastAPI app with external controller and registry."""
    new_app = FastAPI(
        title="Synapse A2A Server",
        description="CLI agent wrapper with Google A2A protocol compatibility",
        version="1.0.0",
    )

    task_store = TaskStore()

    @new_app.post("/message", tags=["Synapse Original (Deprecated)"], deprecated=True)
    async def send_message(msg: MessageRequest) -> dict:
        """Send message to agent (Synapse original API). DEPRECATED."""
        return _send_legacy_message(ctrl, task_store, msg, submit_seq)

    @new_app.get("/status", tags=["Synapse Original"])
    async def get_status() -> dict:
        """Get agent status (Synapse original API)"""
        if not ctrl:
            return {"status": "NOT_STARTED", "context": ""}
        return {"status": ctrl.status, "context": ctrl.get_context()[-2000:]}

    a2a_router = create_a2a_router(ctrl, agent_type, port, submit_seq, agent_id, reg)
    new_app.include_router(a2a_router)

    return new_app


# Global task store for standalone mode
standalone_task_store: TaskStore | None = None


@app.post("/message", tags=["Synapse Original (Deprecated)"], deprecated=True)
async def send_message(msg: MessageRequest) -> dict:
    """
    Send message to agent (Synapse original API).

    DEPRECATED: Use /tasks/send or /tasks/send-priority instead.
    This endpoint now creates A2A tasks internally for consistency.
    """
    if not controller:
        raise HTTPException(status_code=503, detail="Agent not running")
    task_store = _get_standalone_task_store()
    return _send_legacy_message(controller, task_store, msg, submit_sequence)


@app.get("/status")
async def get_status() -> dict:
    """Get the current status of the agent and recent output context."""
    if not controller:
        return {"status": "NOT_STARTED", "context": ""}

    return {
        "status": controller.status,
        "context": controller.get_context()[-2000:],  # Return last 2000 chars
    }


def run_dual_server(
    app: FastAPI,
    host: str,
    port: int,
    agent_id: str | None = None,
    log_level: str = "info",
    **ssl_config: Any,
) -> None:
    """Run both TCP and UDS servers."""
    # TCP Server Config
    tcp_config = uvicorn.Config(
        app, host=host, port=port, log_level=log_level, **ssl_config
    )
    tcp_server = uvicorn.Server(tcp_config)

    # UDS Server Config
    uds_path = None
    uds_server = None
    if agent_id:
        # Directory created by resolve_uds_path with correct permissions
        uds_path = resolve_uds_path(agent_id)
        if uds_path.exists():
            uds_path.unlink()

        uds_config = uvicorn.Config(
            app, uds=str(uds_path), log_level=log_level, **ssl_config
        )
        uds_config.lifespan = "off"
        uds_server = uvicorn.Server(uds_config)

    def run_tcp() -> None:
        tcp_server.run()

    if uds_server:
        # Run UDS server in a separate thread
        uds_thread = threading.Thread(target=uds_server.run, daemon=True)
        uds_thread.start()
        print(f"UDS listener started at: {uds_path}")

    # Run TCP server in main thread (blocking)
    run_tcp()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Synapse A2A Server")
    parser.add_argument(
        "--profile",
        default="claude",
        help="Agent profile (claude, codex, gemini, dummy)",
    )
    parser.add_argument("--port", type=int, default=8100, help="Server port")
    parser.add_argument(
        "--host", default="127.0.0.1", help="Server host (default: localhost only)"
    )
    parser.add_argument("--ssl-cert", default=None, help="SSL certificate file path")
    parser.add_argument("--ssl-key", default=None, help="SSL private key file path")
    args = parser.parse_args()

    # Set environment variables for startup_event
    os.environ["SYNAPSE_PROFILE"] = args.profile
    os.environ["SYNAPSE_PORT"] = str(args.port)

    # Resolve agent_id for UDS path
    registry = AgentRegistry()
    agent_id = registry.get_agent_id(args.profile, args.port)

    # Configure SSL if certificates provided
    ssl_config = {}
    if args.ssl_cert and args.ssl_key:
        if not os.path.isfile(args.ssl_cert):
            print(f"Error: SSL certificate not found: {args.ssl_cert}")
            sys.exit(1)
        if not os.path.isfile(args.ssl_key):
            print(f"Error: SSL key not found: {args.ssl_key}")
            sys.exit(1)
        ssl_config["ssl_certfile"] = args.ssl_cert
        ssl_config["ssl_keyfile"] = args.ssl_key
        os.environ["SYNAPSE_USE_HTTPS"] = "true"
        print(f"HTTPS enabled with certificate: {args.ssl_cert}")

    run_dual_server(
        app, host=args.host, port=args.port, agent_id=agent_id, **ssl_config
    )
