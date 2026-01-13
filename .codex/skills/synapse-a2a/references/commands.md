# CLI Command Reference

## Agent Management

### List Running Agents

```bash
# Show all running agents
synapse list

# Watch mode with auto-refresh (2s default)
synapse list --watch
synapse list -w

# Custom refresh interval
synapse list --watch --interval 0.5
synapse list -w -i 1
```

**Output includes:**
- Agent name and type
- Status (READY / PROCESSING)
- Port number
- Working directory

### Start Agents

```bash
# Interactive mode (foreground)
synapse claude
synapse gemini
synapse codex

# With specific port
synapse claude --port 8101

# With history enabled
SYNAPSE_HISTORY_ENABLED=true synapse claude

# With File Safety enabled
SYNAPSE_FILE_SAFETY_ENABLED=true synapse claude

# With all features
SYNAPSE_HISTORY_ENABLED=true SYNAPSE_FILE_SAFETY_ENABLED=true synapse claude
```

### Port Ranges

| Agent  | Ports     |
|--------|-----------|
| Claude | 8100-8109 |
| Gemini | 8110-8119 |
| Codex  | 8120-8129 |

## Sending Messages

### synapse send (Recommended)

**Use this command for inter-agent communication.** Works from any environment including sandboxed agents.

```bash
synapse send <target> "<message>" [--from <sender>] [--priority <1-5>] [--return]
```

**Parameters:**
- `target`: Agent type (`claude`, `gemini`, `codex`) or type-port (`claude-8100`)
- `message`: Message to send
- `--from, -f`: Sender agent ID (for reply identification) - **always include this**
- `--priority, -p`: 1-2 low, 3 normal, 4 urgent, 5 critical (default: 1)
- `--return, -r`: Wait for response

**Examples:**
```bash
# Send message to Gemini (identifying as Codex)
synapse send gemini "Please review this code" --from codex

# Send with normal priority
synapse send codex "Fix this bug" --priority 3 --from claude

# Send to specific instance
synapse send claude-8100 "Status update?" --from gemini

# Emergency interrupt
synapse send codex "STOP" --priority 5 --from claude

# Wait for response
synapse send gemini "Analyze this" --return --from codex
```

**Important:** Always use `--from` so the recipient knows who sent the message and can reply.

### @Agent Pattern (User Input)

When typing directly in the terminal (not from agent code), you can use:

```text
@<agent_name> <message>
```

Examples:
```text
@codex Please refactor this file
@gemini Research this API
@claude-8100 Review this code
```

> **Note**: The `@agent` pattern only works for user input. Agents should use `synapse send` command.

### A2A Tool (Advanced)

For advanced use cases or external scripts:

```bash
python -m synapse.tools.a2a send --target <AGENT> [--priority <1-5>] "<MESSAGE>"
python -m synapse.tools.a2a list       # List agents
python -m synapse.tools.a2a cleanup    # Cleanup stale entries
```

## Task History

Enable with `SYNAPSE_HISTORY_ENABLED=true`.

### List History

```bash
# Recent tasks (default: 50)
synapse history list

# Filter by agent
synapse history list --agent claude

# Limit results
synapse history list --limit 100
```

### Show Task Details

```bash
synapse history show <task_id>
```

### Search Tasks

```bash
# Search by keywords (OR logic)
synapse history search "Python" "Docker" --logic OR

# Search with AND logic
synapse history search "error" "authentication" --logic AND

# Filter by agent
synapse history search "bug" --agent claude --limit 20
```

### View Statistics

```bash
# Overall statistics
synapse history stats

# Per-agent statistics
synapse history stats --agent gemini
```

### Export Data

```bash
# Export to JSON
synapse history export --format json > history.json

# Export to CSV
synapse history export --format csv --agent claude > claude_tasks.csv

# Export to file
synapse history export --format json --output export.json
```

### Cleanup

```bash
# Delete entries older than 30 days
synapse history cleanup --days 30

# Keep database under 100MB
synapse history cleanup --max-size 100
```

## Settings Management

### Initialize Settings

```bash
# Project-level settings (./.synapse/settings.json)
synapse init --scope project

# User-level settings (~/.synapse/settings.json)
synapse init --scope user
```

### Reset Settings

```bash
synapse reset
```

### Settings File Format

`.synapse/settings.json`:
```json
{
  "env": {
    "SYNAPSE_HISTORY_ENABLED": "true",
    "SYNAPSE_FILE_SAFETY_ENABLED": "true",
    "SYNAPSE_FILE_SAFETY_DB_PATH": ".synapse/file_safety.db"
  }
}
```

**Available Settings:**

| Variable | Description | Default |
|----------|-------------|---------|
| `SYNAPSE_HISTORY_ENABLED` | Enable task history | `false` |
| `SYNAPSE_FILE_SAFETY_ENABLED` | Enable file safety | `false` |
| `SYNAPSE_FILE_SAFETY_DB_PATH` | File safety DB path | `~/.synapse/file_safety.db` |

## Storage Locations

```text
~/.a2a/registry/     # Running agents (auto-cleaned)
~/.a2a/external/     # External A2A agents (persistent)
~/.synapse/          # User-level settings and logs
.synapse/            # Project-level settings
/tmp/synapse-a2a/    # Unix Domain Sockets (UDS) for inter-agent communication
```

**Note:** UDS socket location can be customized with `SYNAPSE_UDS_DIR` environment variable.
