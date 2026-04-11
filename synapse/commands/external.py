"""External agent command handlers for Synapse CLI."""

from __future__ import annotations

import argparse
import sys

from synapse.a2a_client import get_client


def cmd_external_add(args: argparse.Namespace) -> None:
    """Add an external A2A agent."""
    client = get_client()
    agent = client.discover(args.url, alias=args.alias)

    if agent:
        print(f"Added external agent: {agent.name}")
        print(f"  Alias: {agent.alias}")
        print(f"  URL: {agent.url}")
        print(f"  Description: {agent.description}")
        if agent.skills:
            skills_str = ", ".join(s.get("name", s.get("id", "")) for s in agent.skills)
            print(f"  Skills: {skills_str}")
    else:
        print(f"Failed to add agent from {args.url}")
        sys.exit(1)


def cmd_external_list(args: argparse.Namespace) -> None:
    """List external A2A agents."""
    client = get_client()
    agents = client.list_agents()

    if not agents:
        print("No external agents registered.")
        print("Use 'synapse external add <url>' to add one.")
        return

    print(f"{'ALIAS':<15} {'NAME':<20} {'URL':<40} {'LAST SEEN'}")
    print("-" * 90)
    for agent in agents:
        last_seen = agent.last_seen[:19] if agent.last_seen else "Never"
        print(f"{agent.alias:<15} {agent.name:<20} {agent.url:<40} {last_seen}")


def cmd_external_remove(args: argparse.Namespace) -> None:
    """Remove an external A2A agent."""
    client = get_client()

    if client.remove_agent(args.alias):
        print(f"Removed external agent: {args.alias}")
    else:
        print(f"Agent '{args.alias}' not found")
        sys.exit(1)


def cmd_external_send(args: argparse.Namespace) -> None:
    """Send a message to an external A2A agent."""
    client = get_client()

    task = client.send_message(args.alias, args.message, wait_for_completion=args.wait)

    if task:
        print(f"Task ID: {task.id}")
        print(f"Status: {task.status}")
        if task.artifacts:
            print("Artifacts:")
            for artifact in task.artifacts:
                print(f"  - {artifact}")
    else:
        print(f"Failed to send message to {args.alias}")
        sys.exit(1)


def cmd_external_info(args: argparse.Namespace) -> None:
    """Show detailed info about an external agent."""
    client = get_client()
    agent = client.registry.get(args.alias)

    if not agent:
        print(f"Agent '{args.alias}' not found")
        sys.exit(1)

    print(f"Name: {agent.name}")
    print(f"Alias: {agent.alias}")
    print(f"URL: {agent.url}")
    print(f"Description: {agent.description}")
    print(f"Added: {agent.added_at}")
    print(f"Last Seen: {agent.last_seen or 'Never'}")

    if agent.capabilities:
        print("\nCapabilities:")
        for key, value in agent.capabilities.items():
            print(f"  {key}: {value}")

    if agent.skills:
        print("\nSkills:")
        for skill in agent.skills:
            print(f"  - {skill.get('name', skill.get('id', 'Unknown'))}")
            if skill.get("description"):
                print(f"    {skill['description']}")
