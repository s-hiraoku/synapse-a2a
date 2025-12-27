from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import argparse
import asyncio
import os
import yaml
from synapse.controller import TerminalController
from synapse.registry import AgentRegistry

# Global app instance for standalone mode
app = FastAPI(title="Synapse A2A Server")

# Global controller and registry instances (for standalone mode)
controller: TerminalController = None
registry: AgentRegistry = None
current_agent_id: str = None
agent_port: int = 8100
agent_profile: str = 'claude'
submit_sequence: str = '\n'  # Default submit sequence


def create_app(ctrl: TerminalController, reg: AgentRegistry, agent_id: str, port: int,
               submit_seq: str = '\n') -> FastAPI:
    """Create a FastAPI app with external controller and registry."""
    new_app = FastAPI(title="Synapse A2A Server")

    class MessageRequest(BaseModel):
        priority: int
        content: str

    @new_app.post("/message")
    async def send_message(msg: MessageRequest):
        if not ctrl:
            raise HTTPException(status_code=503, detail="Agent not running")

        if msg.priority >= 5:
            ctrl.interrupt()

        # Use the profile's submit sequence (e.g., \r for TUI apps, \n for readline)
        # Pass content only, submit_seq is handled separately in write()
        ctrl.write(msg.content, submit_seq=submit_seq)
        return {"status": "sent", "priority": msg.priority}

    @new_app.get("/status")
    async def get_status():
        if not ctrl:
            return {"status": "NOT_STARTED", "context": ""}

        return {
            "status": ctrl.status,
            "context": ctrl.get_context()[-2000:]
        }

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

    profile = load_profile(profile_name)

    # Load submit sequence from profile (decode escape sequences)
    submit_sequence = profile.get('submit_sequence', '\n').encode().decode('unicode_escape')

    # Merge profile env with system env
    env = os.environ.copy()
    if 'env' in profile:
        env.update(profile['env'])

    controller = TerminalController(
        command=profile['command'],
        idle_regex=profile['idle_regex'],
        env=env
    )
    controller.start()

    # Registry Registration
    registry = AgentRegistry()
    current_agent_id = registry.get_agent_id(profile_name, os.getcwd())
    registry.register(current_agent_id, profile_name, agent_port, status="BUSY")

    print(f"Started agent: {profile['command']}")
    print(f"Registered Agent ID: {current_agent_id}")
    print(f"Submit sequence: {repr(submit_sequence)}")

@app.on_event("shutdown")
async def shutdown_event():
    if controller:
        controller.stop()
    if registry and current_agent_id:
        registry.unregister(current_agent_id)

class MessageRequest(BaseModel):
    priority: int
    content: str

@app.post("/message")
async def send_message(msg: MessageRequest):
    if not controller:
        raise HTTPException(status_code=503, detail="Agent not running")

    if msg.priority >= 5:
        # Emergency: Interrupt first
        controller.interrupt()

    # For Priority < 5, we just write.
    # Use the profile's submit sequence (e.g., \r for TUI apps, \n for readline)
    # Pass content only, submit_seq is handled separately in write()
    try:
        controller.write(msg.content, submit_seq=submit_sequence)
    except Exception as e:
        print(f"Error writing to controller: {e}")
        raise HTTPException(status_code=500, detail=f"Write failed: {str(e)}")

    return {"status": "sent", "priority": msg.priority}

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
