"""MCP support for Synapse."""

from .server import SynapseMCPServer, UnknownMCPResourceError, serve_stdio

__all__ = ["SynapseMCPServer", "UnknownMCPResourceError", "serve_stdio"]
