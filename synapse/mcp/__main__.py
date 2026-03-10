"""Dedicated module entrypoint for Synapse MCP stdio server."""

from __future__ import annotations

import argparse
import os

from synapse.mcp.server import SynapseMCPServer, serve_stdio
from synapse.tools.a2a import _extract_agent_type_from_id


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m synapse.mcp",
        description="Serve Synapse MCP resources over stdio.",
    )
    parser.add_argument(
        "--agent-id",
        default=os.environ.get("SYNAPSE_AGENT_ID", "synapse-mcp"),
        help="Agent ID used for bootstrap tool context.",
    )
    parser.add_argument(
        "--agent-type",
        default=None,
        help="Agent type used for instruction resolution.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="Port value used for bootstrap context.",
    )
    args = parser.parse_args()
    agent_type = args.agent_type or _extract_agent_type_from_id(args.agent_id)

    server = SynapseMCPServer(
        agent_type=agent_type or "default",
        agent_id=args.agent_id,
        port=args.port,
    )
    serve_stdio(server)


if __name__ == "__main__":
    main()
