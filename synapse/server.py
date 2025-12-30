from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import argparse
import asyncio
import os
import yaml
from synapse.controller import TerminalController
from synapse.registry import AgentRegistry
from synapse.a2a_compat import create_a2a_router, TaskStore, Message, TextPart
from synapse.agent_context import (
    AgentContext,
    build_bootstrap_message,
    get_other_agents_from_registry,
)

# Global app instance for standalone mode
app = FastAPI(
    title="Synapse A2A Server",
    description="CLI agent wrapper with Google A2A protocol compatibility",
    version="1.0.0"
)

# Global controller and registry instances (for standalone mode)
controller: TerminalController = None
registry: AgentRegistry = None
current_agent_id: str = None
agent_port: int = 8100
agent_profile: str = 'claude'
submit_sequence: str = '\n'  # Default submit sequence


def create_app(ctrl: TerminalController, reg: AgentRegistry, agent_id: str, port: int,
               submit_seq: str = '\n', agent_type: str = 'claude', registry: AgentRegistry = None) -> FastAPI:
    """Create a FastAPI app with external controller and registry."""
    new_app = FastAPI(
        title="Synapse A2A Server",
        description="CLI agent wrapper with Google A2A protocol compatibility",
        version="1.0.0"
    )

    class MessageRequest(BaseModel):
        priority: int
        content: str

    # Task store shared with A2A router (will be set when router is created)
    task_store = TaskStore()

    # --------------------------------------------------------
    # Original Synapse API (maintained for backward compatibility)
    # DEPRECATED: Use /tasks/send or /tasks/send-priority instead
    # --------------------------------------------------------

    @new_app.post("/message", tags=["Synapse Original (Deprecated)"], deprecated=True)
    async def send_message(msg: MessageRequest):
        """
        Send message to agent (Synapse original API).

        DEPRECATED: Use /tasks/send or /tasks/send-priority instead.
        This endpoint now creates A2A tasks internally for consistency.
        """
        if not ctrl:
            raise HTTPException(status_code=503, detail="Agent not running")

        # Convert to A2A Message format internally
        a2a_message = Message(
            role="user",
            parts=[TextPart(text=msg.content)]
        )

        # Create task for tracking
        task = task_store.create(a2a_message)

        if msg.priority >= 5:
            ctrl.interrupt()

        # Update task status to working
        task_store.update_status(task.id, "working")

        # Use the profile's submit sequence (e.g., \r for TUI apps, \n for readline)
        ctrl.write(msg.content, submit_seq=submit_seq)

        return {"status": "sent", "priority": msg.priority, "task_id": task.id}

    @new_app.get("/status", tags=["Synapse Original"])
    async def get_status():
        """Get agent status (Synapse original API)"""
        if not ctrl:
            return {"status": "NOT_STARTED", "context": ""}

        return {
            "status": ctrl.status,
            "context": ctrl.get_context()[-2000:]
        }

    # --------------------------------------------------------
    # Google A2A Compatible API
    # --------------------------------------------------------
    a2a_router = create_a2a_router(
        ctrl, agent_type, port, submit_seq, agent_id, registry or reg
    )
    new_app.include_router(a2a_router)

    return new_app

def load_profile(profile_name: str):
    profile_path = os.path.join(os.path.dirname(__file__), 'profiles', f"{profile_name}.yaml")
    if not os.path.exists(profile_path):
        raise FileNotFoundError(f"Profile {profile_name} not found")
    
    with open(profile_path, 'r') as f:
        return yaml.safe_load(f)

@app.on_event("startup")
async def startup_event():
    global controller, registry, current_agent_id, agent_port, agent_profile, submit_sequence

    # Get profile and port from environment variables (set by CLI args)
    profile_name = os.environ.get("SYNAPSE_PROFILE", agent_profile)
    agent_port = int(os.environ.get("SYNAPSE_PORT", agent_port))
    agent_profile = profile_name

    # Get tool args from environment (null-separated)
    tool_args_str = os.environ.get("SYNAPSE_TOOL_ARGS", "")
    tool_args = tool_args_str.split('\x00') if tool_args_str else []

    profile = load_profile(profile_name)

    # Load submit sequence from profile (decode escape sequences)
    submit_sequence = profile.get('submit_sequence', '\n').encode().decode('unicode_escape')

    # Merge profile args with CLI tool args
    profile_args = profile.get('args', [])
    all_args = profile_args + tool_args

    # Merge profile env with system env
    env = os.environ.copy()
    if 'env' in profile:
        env.update(profile['env'])

    # Registry Registration (before controller to pass agent_id)
    registry = AgentRegistry()
    current_agent_id = registry.get_agent_id(profile_name, agent_port)

    # Set sender identification environment variables for child processes
    # These are used by CLI tools (a2a.py) to auto-detect sender info
    env["SYNAPSE_AGENT_ID"] = current_agent_id
    env["SYNAPSE_AGENT_TYPE"] = profile_name
    env["SYNAPSE_PORT"] = str(agent_port)

    controller = TerminalController(
        command=profile['command'],
        args=all_args,
        idle_regex=profile['idle_regex'],
        env=env,
        agent_id=current_agent_id,
        agent_type=profile_name,
        submit_seq=submit_sequence,
        port=agent_port,
        registry=registry,
    )
    controller.start()

    registry.register(current_agent_id, profile_name, agent_port, status="BUSY")

    # Add Google A2A compatible routes
    a2a_router = create_a2a_router(
        controller, profile_name, agent_port, submit_sequence, current_agent_id, registry
    )
    app.include_router(a2a_router)

    print(f"Started agent: {profile['command']}")
    print(f"Registered Agent ID: {current_agent_id}")
    print(f"Submit sequence: {repr(submit_sequence)}")
    print(f"Agent Card available at: http://localhost:{agent_port}/.well-known/agent.json")

    # Schedule minimal initial instructions (after CLI is ready)
    asyncio.create_task(send_initial_instructions(
        controller, current_agent_id, agent_port, submit_sequence
    ))


async def send_initial_instructions(
    ctrl: TerminalController,
    agent_id: str,
    port: int,
    submit_seq: str
):
    """
    Send minimal initial instructions to the AI agent via A2A Task.

    Only sends identity and basic commands (3 lines).
    Detailed routing is handled by InputRouter and inline message instructions.
    """
    # Wait for CLI to be ready (IDLE state)
    max_wait = 30
    waited = 0
    while waited < max_wait:
        if ctrl.status == "IDLE":
            break
        await asyncio.sleep(1)
        waited += 1

    # Build minimal bootstrap message
    bootstrap = build_bootstrap_message(agent_id, port)

    # Create A2A Task for tracking
    task_store = TaskStore()
    message = Message(
        role="user",
        parts=[TextPart(text=bootstrap)]
    )
    task = task_store.create(
        message,
        metadata={
            "sender": {
                "sender_id": "synapse-system",
                "sender_type": "system",
            }
        }
    )
    task_store.update_status(task.id, "working")

    # Send to PTY with A2A format
    try:
        prefixed_content = f"[A2A:{task.id[:8]}:synapse-system] {bootstrap}"
        ctrl.write(prefixed_content, submit_seq=submit_seq)
        print(f"Sent bootstrap instructions (Task ID: {task.id[:8]})")
    except Exception as e:
        print(f"Warning: Failed to send bootstrap: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    if controller:
        controller.stop()
    if registry and current_agent_id:
        registry.unregister(current_agent_id)

class MessageRequest(BaseModel):
    priority: int
    content: str

# Global task store for standalone mode
standalone_task_store: TaskStore = None

@app.post("/message", tags=["Synapse Original (Deprecated)"], deprecated=True)
async def send_message(msg: MessageRequest):
    """
    Send message to agent (Synapse original API).

    DEPRECATED: Use /tasks/send or /tasks/send-priority instead.
    This endpoint now creates A2A tasks internally for consistency.
    """
    global standalone_task_store

    if not controller:
        raise HTTPException(status_code=503, detail="Agent not running")

    # Initialize task store if needed
    if standalone_task_store is None:
        standalone_task_store = TaskStore()

    # Convert to A2A Message format internally
    a2a_message = Message(
        role="user",
        parts=[TextPart(text=msg.content)]
    )

    # Create task for tracking
    task = standalone_task_store.create(a2a_message)

    if msg.priority >= 5:
        # Emergency: Interrupt first
        controller.interrupt()

    # Update task status to working
    standalone_task_store.update_status(task.id, "working")

    # For Priority < 5, we just write.
    # Use the profile's submit sequence (e.g., \r for TUI apps, \n for readline)
    try:
        controller.write(msg.content, submit_seq=submit_sequence)
    except Exception as e:
        print(f"Error writing to controller: {e}")
        standalone_task_store.update_status(task.id, "failed")
        raise HTTPException(status_code=500, detail=f"Write failed: {str(e)}")

    return {"status": "sent", "priority": msg.priority, "task_id": task.id}

@app.get("/status")
async def get_status():
    if not controller:
        return {"status": "NOT_STARTED", "context": ""}
        
    return {
        "status": controller.status,
        "context": controller.get_context()[-2000:] # Return last 2000 chars
    }

if __name__ == "__main__":
    import uvicorn

    parser = argparse.ArgumentParser(description="Synapse A2A Server")
    parser.add_argument("--profile", default="claude", help="Agent profile (claude, codex, gemini, dummy)")
    parser.add_argument("--port", type=int, default=8100, help="Server port")
    args = parser.parse_args()

    # Set environment variables for startup_event
    os.environ["SYNAPSE_PROFILE"] = args.profile
    os.environ["SYNAPSE_PORT"] = str(args.port)

    uvicorn.run(app, host="0.0.0.0", port=args.port)
