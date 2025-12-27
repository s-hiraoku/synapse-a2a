#!/usr/bin/env python3
"""Synapse Shell - Interactive shell with @Agent support."""

import cmd
import os
import re
import subprocess
import sys
import requests
from synapse.registry import AgentRegistry


class SynapseShell(cmd.Cmd):
    intro = """
╔═══════════════════════════════════════════════════════════╗
║  Synapse Shell - Agent-to-Agent Communication             ║
║  Type @Agent <message> to send to an agent                ║
║  Type 'help' for commands, 'exit' to quit                 ║
╚═══════════════════════════════════════════════════════════╝
"""
    prompt = "synapse> "

    def __init__(self):
        super().__init__()
        self.registry = AgentRegistry()
        # Pattern: @AgentName [--return] message
        self.agent_pattern = re.compile(
            r'^@(\w+)\s*(--return\s+)?(.+)$',
            re.IGNORECASE
        )

    def default(self, line):
        """Handle input that doesn't match a command."""
        # Check for @Agent pattern
        match = self.agent_pattern.match(line)
        if match:
            agent_name = match.group(1).lower()
            wait_response = bool(match.group(2))
            message = match.group(3).strip()
            self.send_to_agent(agent_name, message, wait_response)
            return

        # Otherwise, execute as shell command
        if line.strip():
            os.system(line)

    def send_to_agent(self, agent_name: str, message: str, wait_response: bool = False):
        """Send a message to an agent."""
        agents = self.registry.list_agents()

        # Find agent by name/type
        target = None
        for agent_id, info in agents.items():
            if info.get("agent_type", "").lower() == agent_name:
                target = info
                break

        if not target:
            print(f"Agent '{agent_name}' not found. Available agents:")
            for agent_id, info in agents.items():
                print(f"  - {info.get('agent_type')}")
            return

        endpoint = target.get("endpoint")
        if not endpoint:
            print(f"No endpoint found for {agent_name}")
            return

        # Send message
        priority = 1
        try:
            print(f"[Sending to {agent_name}...]")
            response = requests.post(
                f"{endpoint}/message",
                json={"content": message, "priority": priority},
                timeout=10
            )
            response.raise_for_status()
            print(f"[Message sent to {agent_name}]")

            if wait_response:
                self.wait_for_response(endpoint, agent_name)

        except requests.exceptions.RequestException as e:
            print(f"Error sending to {agent_name}: {e}")

    def wait_for_response(self, endpoint: str, agent_name: str, timeout: int = 30):
        """Wait for agent to become IDLE and get response."""
        import time
        print(f"[Waiting for {agent_name} response...]")

        start_time = time.time()
        last_context = ""

        while time.time() - start_time < timeout:
            try:
                response = requests.get(f"{endpoint}/status", timeout=5)
                data = response.json()
                status = data.get("status", "")
                context = data.get("context", "")

                if status == "IDLE" and context != last_context:
                    # Agent became IDLE, extract new content
                    new_content = context[len(last_context):] if last_context else context
                    # Clean ANSI escape codes
                    clean_content = re.sub(r'\x1b\[[0-9;]*m', '', new_content)
                    if clean_content.strip():
                        print(f"\n[{agent_name}]:")
                        print(clean_content[-1000:])  # Last 1000 chars
                    return

                last_context = context
                time.sleep(1)

            except requests.exceptions.RequestException:
                time.sleep(1)

        print(f"[Timeout waiting for {agent_name}]")

    def do_list(self, arg):
        """List running agents."""
        agents = self.registry.list_agents()
        if not agents:
            print("No agents running.")
            return

        print(f"\n{'TYPE':<10} {'PORT':<8} {'STATUS':<10} {'ENDPOINT'}")
        print("-" * 50)
        for agent_id, info in agents.items():
            print(f"{info.get('agent_type', 'unknown'):<10} "
                  f"{info.get('port', '-'):<8} "
                  f"{info.get('status', '-'):<10} "
                  f"{info.get('endpoint', '-')}")
        print()

    def do_status(self, arg):
        """Check status of an agent. Usage: status <agent>"""
        if not arg:
            print("Usage: status <agent>")
            return

        agent_name = arg.lower()
        agents = self.registry.list_agents()

        for agent_id, info in agents.items():
            if info.get("agent_type", "").lower() == agent_name:
                endpoint = info.get("endpoint")
                try:
                    response = requests.get(f"{endpoint}/status", timeout=5)
                    data = response.json()
                    print(f"Status: {data.get('status')}")
                    context = data.get('context', '')[-500:]
                    # Clean ANSI codes
                    clean = re.sub(r'\x1b\[[0-9;]*m', '', context)
                    print(f"Context:\n{clean}")
                except requests.exceptions.RequestException as e:
                    print(f"Error: {e}")
                return

        print(f"Agent '{agent_name}' not found.")

    def do_exit(self, arg):
        """Exit the shell."""
        print("Goodbye!")
        return True

    def do_quit(self, arg):
        """Exit the shell."""
        return self.do_exit(arg)

    def do_EOF(self, arg):
        """Handle Ctrl+D."""
        print()
        return self.do_exit(arg)

    def emptyline(self):
        """Do nothing on empty line."""
        pass


def main():
    try:
        shell = SynapseShell()
        shell.cmdloop()
    except KeyboardInterrupt:
        print("\nGoodbye!")


if __name__ == "__main__":
    main()
