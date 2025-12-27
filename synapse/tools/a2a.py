import argparse
import sys
import json
import requests
from synapse.registry import AgentRegistry

def cmd_list(args):
    """List all available agents."""
    reg = AgentRegistry()
    agents = reg.list_agents()
    print(json.dumps(agents, indent=2))

def cmd_send(args):
    """Send a message to a target agent using Google A2A protocol."""
    reg = AgentRegistry()
    agents = reg.list_agents()

    # 1. Resolve Target
    target_agent = None

    # Check if exact match by ID
    if args.target in agents:
        target_agent = agents[args.target]
    else:
        # Fuzzy match by agent_type (e.g. 'claude')
        matches = [a for a in agents.values() if args.target.lower() in a['agent_type'].lower()]
        if len(matches) == 1:
            target_agent = matches[0]
        elif len(matches) > 1:
            print(f"Error: Ambiguous target '{args.target}'. Multiple agents found: {[m['agent_id'] for m in matches]}", file=sys.stderr)
            sys.exit(1)
        else:
             print(f"Error: No agent found matching '{args.target}'", file=sys.stderr)
             sys.exit(1)

    # 2. Send Request using Google A2A protocol
    url = f"{target_agent['endpoint']}/tasks/send-priority?priority={args.priority}"
    payload = {
        "message": {
            "role": "user",
            "parts": [{"type": "text", "text": args.message}]
        }
    }

    try:
        resp = requests.post(url, json=payload, timeout=30)
        resp.raise_for_status()
        result = resp.json()
        task = result.get("task", result)
        print(f"Success: Task created for {target_agent['agent_type']} ({target_agent['agent_id'][:8]}...)")
        print(f"  Task ID: {task.get('id', 'N/A')}")
        print(f"  Status: {task.get('status', 'N/A')}")

    except requests.RequestException as e:
        print(f"Error sending message: {e}", file=sys.stderr)
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Synapse A2A Client Tool")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # list command
    subparsers.add_parser("list", help="List active agents")
    
    # send command
    p_send = subparsers.add_parser("send", help="Send message to an agent")
    p_send.add_argument("--target", required=True, help="Target Agent ID or Type (e.g. 'claude')")
    p_send.add_argument("--priority", type=int, default=1, help="Priority (1-5, 5=Interrupt)")
    p_send.add_argument("message", help="Content of the message")
    
    args = parser.parse_args()
    
    if args.command == "list":
        cmd_list(args)
    elif args.command == "send":
        cmd_send(args)

if __name__ == "__main__":
    main()
