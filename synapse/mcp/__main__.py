"""Dedicated module entrypoint for Synapse MCP stdio server."""

from __future__ import annotations

import argparse

from synapse.mcp.server import SynapseMCPServer, serve_stdio


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m synapse.mcp",
        description="Serve Synapse MCP resources over stdio.",
    )
    parser.add_argument(
        "--agent-id",
        default="synapse-mcp",
        help="Agent ID used for bootstrap tool context.",
    )
    parser.add_argument(
        "--agent-type",
        default="default",
        help="Agent type used for instruction resolution.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="Port value used for bootstrap context.",
    )
    args = parser.parse_args()

    server = SynapseMCPServer(
        agent_type=args.agent_type,
        agent_id=args.agent_id,
        port=args.port,
    )
    serve_stdio(server)


if __name__ == "__main__":
    main()
