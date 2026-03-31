# MCP Bootstrap Setup

Synapse provides an MCP (Model Context Protocol) server that distributes bootstrap instructions to MCP-capable agents. Instead of injecting the full startup instructions via PTY, agents receive a short PTY bootstrap that points them at structured MCP resources and tools.

!!! warning "Experimental"
    MCP bootstrap is Phase 1 (experimental). PTY-based instruction injection remains the primary method and continues to work for all agents.

!!! note "Startup behavior"
    When Claude Code, Codex, Gemini CLI, OpenCode, or GitHub Copilot has a Synapse MCP server configured, Synapse sends a minimal PTY MCP bootstrap automatically instead of the full startup instruction payload. Approval prompts still apply unless the session is resumed.

## Overview

The MCP server exposes:

- **Resources**: Instruction documents (`synapse://instructions/default`, plus optional file-safety, shared-memory, learning, proactive instructions)
- **Tools**:
    - `bootstrap_agent()` — returns runtime context (agent_id, port, available features)
    - `list_agents()` — lists all running Synapse agents with status and connection info

## Prerequisites

- Synapse A2A installed (`uv sync` or `pip install -e .`)
- An MCP-capable agent (Claude Code, Codex, Gemini CLI, OpenCode, or GitHub Copilot)

## Quick Start

```bash
# Verify MCP server works
synapse mcp serve
# Should wait for JSON-RPC input on stdin. Press Ctrl+C to exit.
# Note: SYNAPSE_AGENT_ID 未設定時はデフォルト ID "synapse-mcp" が使われ、
#       agent-type に "mcp" が推論されます。正確な解決には --agent-type を
#       明示するか、環境変数 SYNAPSE_AGENT_ID を設定してください。
```

## Client Configuration

Each agent requires a configuration file telling it how to start the Synapse MCP server. The recommended command uses `uv run` to ensure the correct version:

```
uv run --directory /path/to/synapse-a2a python -m synapse.mcp
```

Replace `/path/to/synapse-a2a` with your actual checkout path.

!!! tip "agent-id / agent-type は自動解決"
    `--agent-id` と `--agent-type` を明示する必要はありません。Synapse はエージェント起動時に環境変数 `SYNAPSE_AGENT_ID` を自動セットし、MCP サーバーはそこから agent-id を取得、agent-type は agent-id から推論します。

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
        "python", "-m", "synapse.mcp"
      ]
    }
  }
}
```

Or add via CLI:

```bash
claude mcp add --scope user synapse \
  /path/to/uv run --directory /path/to/synapse-a2a \
  python -m synapse.mcp
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
        "python", "-m", "synapse.mcp"
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
        "python", "-m", "synapse.mcp"
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

### GitHub Copilot

**Config file**: `~/.copilot/mcp-config.json`

```json
{
  "mcpServers": {
    "synapse": {
      "command": "/path/to/uv",
      "args": [
        "run", "--directory", "/path/to/synapse-a2a",
        "python", "-m", "synapse.mcp"
      ]
    }
  }
}
```

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
      "transport": "-",
      "current_task_preview": null,
      "task_received_at": null
    }
  ]
}
```

!!! tip "Agent discovery without shell access"
    `list_agents` is especially useful for agents running in sandboxed environments (e.g., Codex) where shell command execution may be restricted. It provides the same information as `synapse list --json` but through the MCP protocol.

### analyze_task

Analyzes a user prompt and suggests team/task splits when the work appears large enough. This is the Smart Suggest feature -- it helps agents decompose complex tasks before implementation begins.

**Input schema:**

| Parameter | Type | Required | Description |
|-----------|------|:--------:|-------------|
| `prompt` | string | Yes | User instruction to analyze for team/task split suggestions |
| `files` | array of strings | No | File paths the task is expected to touch (hint for conflict/dependency detection) |
| `agent_type` | string | No | Calling agent's type (e.g. claude, codex, gemini) for subagent capability check |

**Trigger conditions** (configurable via `.synapse/suggest.yaml`):

| Trigger | Default | Description |
|---------|---------|-------------|
| `min_files` | 10 | Minimum number of changed files (from `git status`) |
| `multi_directory` | true | Changes span 2 or more directories |
| `missing_tests` | true | Source files lack corresponding test files |
| `min_prompt_length` | 200 | Prompt exceeds this character count |
| `keywords` | refactor, migrate, review, redesign, etc. | Prompt contains task-splitting keywords |
| `diff_size.min_lines` | 200 | Total insertions + deletions from `git diff --numstat` |

When enabled, the response always includes a `delegation_strategy` field indicating the recommended execution approach:

| Strategy | Meaning |
|----------|---------|
| `self` | Handle the task yourself (small scope, no delegation needed) |
| `subagent` | Use your built-in subagent capability (Claude: Agent tool, Codex: subprocess) |
| `spawn` | Use `synapse spawn` or `synapse team start` for multi-agent execution |

When one or more triggers match, the tool also returns a suggested task split (design/implement/verify pattern). When no triggers match, `suggestion` is `null`, indicating the task can be handled with the recommended strategy without further decomposition.

**Example call** (JSON-RPC `tools/call`):

```json
{
  "name": "analyze_task",
  "arguments": {
    "prompt": "Refactor the authentication module to use OAuth2 with JWT tokens across all API endpoints"
  }
}
```

**Configuration** (`.synapse/suggest.yaml`):

```yaml
suggest:
  enabled: true
  triggers:
    min_files: 10
    multi_directory: true
    missing_tests: true
    min_prompt_length: 200
    keywords:
      - refactor
      - migrate
      - review
      - redesign
    diff_size:
      min_lines: 200
  delegation_thresholds:
    self_max_files: 3
    self_max_lines: 100
    subagent_max_files: 8
    subagent_max_dirs: 2
  subagent_capable_agents:
    - claude
    - codex
```

When Smart Suggest is enabled, the default instruction resource automatically includes guidance for agents to call `analyze_task` on new tasks and act according to the returned `delegation_strategy`:

- **`self`** or **`subagent`**: Continue normally with the recommended approach.
- **`spawn`**: If a suggestion is returned, share it with the user and ask for approval before spawning agents.

!!! tip "From Suggestion to Plan Card"
    When `analyze_task` returns a suggestion, the agent can post it as a Canvas Plan Card (`synapse canvas plan`). See [Canvas -- Plan Template](canvas.md#plan).

## Verification

After configuring, restart the agent and check that the MCP server connects:

1. The agent should show `synapse` as a connected MCP server
2. Run `synapse mcp serve` manually to debug if connection fails
3. On the next `synapse <agent>` launch, Synapse should not paste the long initial instruction block into the PTY

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `failed` status | `uv` or `synapse` not found in PATH | Use absolute path to `uv` binary |
| Connection timeout | Import takes too long | Check `uv sync` completed, try `python -m synapse.mcp` directly |
| Server starts but no resources | Agent type could not be inferred | Ensure `SYNAPSE_AGENT_ID` is set or pass `--agent-type` explicitly |

## Design Reference

For architectural details, see [MCP Bootstrap Design](https://github.com/s-hiraoku/synapse-a2a/blob/main/docs/design/mcp-bootstrap.md) on GitHub.
