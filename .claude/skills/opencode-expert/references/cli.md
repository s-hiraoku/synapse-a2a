# OpenCode CLI Complete Reference

## Global Flags

| Flag | Description |
|------|-------------|
| `--help`, `-h` | Show help |
| `--version`, `-v` | Show version |
| `--print-logs` | Print logs to stdout |
| `--log-level` | Set log level (DEBUG, INFO, WARN, ERROR) |

## opencode (TUI)

Start the terminal user interface.

```bash
opencode [project] [flags]
```

### Flags

| Flag | Short | Description |
|------|-------|-------------|
| `--continue` | `-c` | Continue previous session |
| `--session` | `-s` | Use specific session ID |
| `--prompt` | | Initial prompt to send |
| `--model` | `-m` | Model to use |
| `--agent` | | Agent to use (build, plan) |
| `--port` | | Server port |
| `--hostname` | | Server hostname |

### Examples

```bash
# Start in current directory
opencode

# Continue last session
opencode -c

# Start with specific model
opencode -m claude-3-5-sonnet

# Start in plan mode
opencode --agent plan

# Start with initial prompt
opencode --prompt "Help me refactor auth.py"
```

## opencode run

Execute prompts non-interactively.

```bash
opencode run [message..] [flags]
```

### Flags

| Flag | Short | Description |
|------|-------|-------------|
| `--command` | | Run shell command |
| `--continue` | `-c` | Continue session |
| `--session` | `-s` | Session ID |
| `--share` | | Share result |
| `--model` | `-m` | Model to use |
| `--agent` | | Agent (build, plan) |
| `--file` | `-f` | Attach file |
| `--format` | | Output format |
| `--title` | | Session title |
| `--attach` | | Attach to server |
| `--port` | | Server port |

### Examples

```bash
# Run single prompt
opencode run "Fix the TypeScript errors"

# Run with file
opencode run "Review this code" -f src/main.ts

# Run and share
opencode run "Explain this function" --share

# Run command
opencode run --command "npm test"

# Continue session
opencode run -c "Now add tests"
```

## opencode serve

Start headless API server.

```bash
opencode serve [flags]
```

### Flags

| Flag | Description |
|------|-------------|
| `--port` | Server port (default: 3000) |
| `--hostname` | Server hostname |
| `--mdns` | Enable mDNS discovery |
| `--cors` | Enable CORS |

### Examples

```bash
# Basic server
opencode serve

# Custom port
opencode serve --port 8080

# With mDNS discovery
opencode serve --mdns

# With CORS for web clients
opencode serve --cors
```

## opencode web

Start web interface.

```bash
opencode web [flags]
```

Same flags as `serve`.

## opencode attach

Attach to running server.

```bash
opencode attach [url] [flags]
```

### Flags

| Flag | Short | Description |
|------|-------|-------------|
| `--dir` | | Working directory |
| `--session` | `-s` | Session ID |

## opencode auth

Manage authentication.

```bash
opencode auth [login|list|logout]
```

### Subcommands

- `login` - Authenticate with provider
- `list` - List configured providers
- `logout` - Remove authentication

## opencode models

List available models.

```bash
opencode models [provider] [flags]
```

### Flags

| Flag | Description |
|------|-------------|
| `--refresh` | Refresh model cache |

### Examples

```bash
# List all models
opencode models

# List models from specific provider
opencode models anthropic

# Refresh cache
opencode models --refresh
```

## opencode agent

Manage agents.

```bash
opencode agent [create|list]
```

### Subcommands

- `create` - Interactive agent creation
- `list` - List available agents

## opencode mcp

Manage MCP servers.

```bash
opencode mcp [add|list|auth|logout|debug]
```

### Subcommands

- `add <server>` - Add MCP server
- `list` - List configured servers
- `auth` - Authenticate with MCP server
- `logout` - Remove MCP authentication
- `debug` - Debug MCP connection

## opencode session

Manage sessions.

```bash
opencode session list [flags]
```

### Flags

| Flag | Short | Description |
|------|-------|-------------|
| `--max-count` | `-n` | Maximum sessions to show |
| `--format` | | Output format |

## opencode stats

View usage statistics.

```bash
opencode stats [flags]
```

### Flags

| Flag | Description |
|------|-------------|
| `--days` | Number of days to include |
| `--tools` | Show tool usage |
| `--models` | Show model usage |
| `--project` | Filter by project |

### Examples

```bash
# Overall stats
opencode stats

# Last 7 days
opencode stats --days 7

# Tool usage
opencode stats --tools

# Model usage
opencode stats --models
```

## opencode export

Export session data.

```bash
opencode export [sessionID]
```

Exports session as JSON to stdout.

## opencode import

Import session data.

```bash
opencode import <file>
```

Imports from local JSON file or share URL.

## opencode github

GitHub automation.

```bash
opencode github [install|run]
```

### Subcommands

- `install` - Install GitHub integration
- `run` - Run GitHub automation

## opencode upgrade

Update OpenCode.

```bash
opencode upgrade [target]
```

Updates to latest version or specified target.

## opencode uninstall

Remove OpenCode.

```bash
opencode uninstall [flags]
```

### Flags

| Flag | Short | Description |
|------|-------|-------------|
| `--keep-config` | `-c` | Keep configuration files |
| `--keep-data` | `-d` | Keep data files |
