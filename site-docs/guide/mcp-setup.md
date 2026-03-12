# MCP Bootstrap Setup

Synapse provides an MCP (Model Context Protocol) server that distributes bootstrap instructions to MCP-capable agents. Instead of injecting instructions via PTY, agents receive them as structured MCP resources.

!!! warning "Experimental"
    MCP bootstrap is Phase 1 (experimental). PTY-based instruction injection remains the primary method and continues to work for all agents.

!!! note "Startup behavior"
    When Claude Code, Codex, Gemini CLI, or OpenCode has a Synapse MCP server configured, Synapse now skips PTY startup instruction injection automatically. GitHub Copilot is unchanged and continues to use PTY bootstrap.

## Overview

The MCP server exposes:

- **Resources**: Instruction documents (`synapse://instructions/default`, plus optional file-safety, shared-memory, learning, proactive instructions)
- **Tools**:
    - `bootstrap_agent()` — returns runtime context (agent_id, port, available features)
    - `list_agents()` — lists all running Synapse agents with status and connection info

## Prerequisites

- Synapse A2A installed (`uv sync` or `pip install -e .`)
- An MCP-capable agent (Claude Code, Codex, Gemini CLI, or OpenCode)

## Quick Start

```bash
# Verify MCP server works
synapse mcp serve --agent-type claude --port 8100
# Should wait for JSON-RPC input on stdin. Press Ctrl+C to exit.
```

## Client Configuration

Each agent requires a configuration file telling it how to start the Synapse MCP server. The recommended command uses `uv run` to ensure the correct version:

```
uv run --directory /path/to/synapse-a2a python -m synapse.mcp \
  --agent-id <agent-id> --agent-type <type> --port <port>
```

Replace `/path/to/synapse-a2a` with your actual checkout path.

### Claude Code

**Config file**: `~/.claude.json` (user scope) or `.mcp.json` (project scope)

```json
{
  "mcpServers": {
    "synapse": {
      "type": "stdio",
      "command": "/path/to/uv",
      "args": [
        "run", "--directory", "/path/to/synapse-a2a",
        "python", "-m", "synapse.mcp",
        "--agent-id", "synapse-claude-8100",
        "--agent-type", "claude",
        "--port", "8100"
      ]
    }
  }
}
```

Or add via CLI:

```bash
claude mcp add --scope user synapse \
  /path/to/uv run --directory /path/to/synapse-a2a \
  python -m synapse.mcp --agent-type claude --port 8100
```

**Docs**: <https://code.claude.com/docs/en/mcp>

### Codex CLI

**Config file**: `~/.codex/config.toml`

```toml
[mcp_servers.synapse]
command = "/path/to/uv"
args = [
  "run", "--directory", "/path/to/synapse-a2a",
  "python", "-m", "synapse.mcp",
  "--agent-id", "synapse-codex-8120",
  "--agent-type", "codex",
  "--port", "8120",
]
```

**Docs**: <https://developers.openai.com/resources/docs-mcp>

### Gemini CLI

**Config file**: `~/.gemini/settings.json` (user scope) or `.gemini/settings.json` (project scope)

```json
{
  "mcpServers": {
    "synapse": {
      "command": "/path/to/uv",
      "args": [
        "run", "--directory", "/path/to/synapse-a2a",
        "python", "-m", "synapse.mcp",
        "--agent-id", "synapse-gemini-8110",
        "--agent-type", "gemini",
        "--port", "8110"
      ],
      "timeout": 5000,
      "trust": true
    }
  }
}
```

**Docs**: <https://geminicli.com/docs/tools/mcp-server>

### OpenCode

**Config file**: `~/.config/opencode/opencode.json` (global) or `opencode.json` (project)

```json
{
  "mcp": {
    "synapse": {
      "type": "local",
      "command": [
        "/path/to/uv",
        "run", "--directory", "/path/to/synapse-a2a",
        "python", "-m", "synapse.mcp",
        "--agent-id", "synapse-opencode-8130",
        "--agent-type", "opencode",
        "--port", "8130"
      ],
      "enabled": true,
      "timeout": 5000
    }
  }
}
```

!!! note "OpenCode uses a different format"
    OpenCode's `command` is an **array** (not a string), and the root key is `"mcp"` (not `"mcpServers"`).

**Docs**: <https://opencode.ai/docs/mcp-servers>

## MCP Tools

### bootstrap_agent

Returns the agent's runtime context (agent_id, port, available features). Called automatically during agent initialization.

### list_agents

Lists all running Synapse agents with status and connection info. This is the MCP equivalent of `synapse list --json`, allowing agents to discover peers without running shell commands.

**Input schema:**

| Parameter | Type | Required | Description |
|-----------|------|:--------:|-------------|
| `status` | string | No | Filter by agent status (`READY`, `PROCESSING`, `WAITING`, `DONE`, etc.) |

**Example call** (JSON-RPC `tools/call`):

```json
{
  "name": "list_agents",
  "arguments": {
    "status": "READY"
  }
}
```

**Response:**

```json
{
  "agents": [
    {
      "agent_id": "synapse-claude-8100",
      "agent_type": "claude",
      "name": "my-claude",
      "role": "code reviewer",
      "skill_set": null,
      "port": 8100,
      "status": "READY",
      "pid": 12345,
      "working_dir": "/path/to/project",
      "endpoint": "http://localhost:8100",
      "transport": "http",
      "current_task_preview": null,
      "task_received_at": null
    }
  ]
}
```

!!! tip "Agent discovery without shell access"
    `list_agents` is especially useful for agents running in sandboxed environments (e.g., Codex) where shell command execution may be restricted. It provides the same information as `synapse list --json` but through the MCP protocol.

## Verification

After configuring, restart the agent and check that the MCP server connects:

1. The agent should show `synapse` as a connected MCP server
2. Run `synapse mcp serve --agent-type <type> --port <port>` manually to debug if connection fails
3. On the next `synapse <agent>` launch, Synapse should not paste the long initial instruction block into the PTY

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `failed` status | `uv` or `synapse` not found in PATH | Use absolute path to `uv` binary |
| Connection timeout | Import takes too long | Check `uv sync` completed, try `python -m synapse.mcp` directly |
| Server starts but no resources | Wrong `--agent-type` | Verify type matches agent profile (claude, codex, gemini, opencode) |

## Design Reference

For architectural details, see [MCP Bootstrap Design](https://github.com/s-hiraoku/synapse-a2a/blob/main/docs/design/mcp-bootstrap.md) on GitHub.
