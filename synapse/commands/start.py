"""Start command implementation for Synapse CLI."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from typing import Any

from synapse.port_manager import PortManager
from synapse.registry import AgentRegistry


class StartCommand:
    """Start an agent in background or foreground."""

    def __init__(self, subprocess_module: Any = subprocess) -> None:
        self._subprocess = subprocess_module

    def run(self, args: argparse.Namespace) -> None:
        profile = args.profile
        port = args.port
        foreground = args.foreground
        ssl_cert = getattr(args, "ssl_cert", None)
        ssl_key = getattr(args, "ssl_key", None)

        # Validate SSL options
        if (ssl_cert and not ssl_key) or (ssl_key and not ssl_cert):
            print("Error: Both --ssl-cert and --ssl-key must be provided together")
            sys.exit(1)

        # Extract tool args (filter out -- if present at start)
        tool_args = getattr(args, "tool_args", [])
        if tool_args and tool_args[0] == "--":
            tool_args = tool_args[1:]

        # Auto-select port if not specified
        if port is None:
            registry = AgentRegistry()
            port_manager = PortManager(registry)
            port = port_manager.get_available_port(profile)

            if port is None:
                print(port_manager.format_exhaustion_error(profile))
                sys.exit(1)

        # Build command
        cmd = [
            sys.executable,
            "-m",
            "synapse.server",
            "--profile",
            profile,
            "--port",
            str(port),
        ]

        # Add SSL options if provided
        if ssl_cert and ssl_key:
            cmd.extend(["--ssl-cert", ssl_cert, "--ssl-key", ssl_key])

        # Set up environment with tool args (null-separated for safe parsing)
        env = os.environ.copy()
        if tool_args:
            env["SYNAPSE_TOOL_ARGS"] = "\x00".join(tool_args)

        protocol = "https" if ssl_cert else "http"
        mode = "foreground" if foreground else "background"

        print(f"Starting {profile} on port {port} ({mode}, {protocol.upper()})...")
        if ssl_cert:
            print(f"SSL: {ssl_cert}")
        if tool_args:
            print(f"Tool args: {' '.join(tool_args)}")

        if foreground:
            try:
                self._subprocess.run(cmd, env=env)
            except KeyboardInterrupt:
                print("\nStopped.")
        else:
            log_dir = os.path.expanduser("~/.synapse/logs")
            os.makedirs(log_dir, exist_ok=True)
            log_file = os.path.join(log_dir, f"{profile}.log")

            with open(log_file, "w") as log:
                process = self._subprocess.Popen(
                    cmd, stdout=log, stderr=log, start_new_session=True, env=env
                )

            # Wait a bit and check if it started
            time.sleep(2)
            if process.poll() is None:
                print(f"Started {profile} (PID: {process.pid})")
                print(f"Logs: {log_file}")
            else:
                print(f"Failed to start {profile}. Check logs: {log_file}")
                sys.exit(1)
