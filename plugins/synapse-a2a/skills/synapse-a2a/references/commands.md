# CLI Command Reference

## Agent Management

### List Running Agents

```bash
# Show all running agents
synapse list

# Watch mode with auto-refresh (2s default, shows TRANSPORT column)
synapse list --watch
synapse list -w

# Custom refresh interval (0.5s recommended for observing communication)
synapse list --watch --interval 0.5
synapse list -w -i 0.5
```

**Output includes:**
- Agent name and type
- Status (READY / PROCESSING)
- Port number
- Working directory
- **TRANSPORT** (watch mode only): Communication method during inter-agent messages
  - `UDS→` / `TCP→`: Sending via UDS/TCP
  - `→UDS` / `→TCP`: Receiving via UDS/TCP
  - `-`: No active communication

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
synapse send <target> "<message>" [--from <sender>] [--priority <1-5>] [--response | --no-response] [--reply-to <task_id>]
```

**Target Formats (in priority order):**

| Format | Example | Description |
|--------|---------|-------------|
| Full ID | `synapse-claude-8100` | Always works, unique identifier |
| Type-port | `claude-8100` | Use when multiple agents of same type |
| Agent type | `claude` | Only when single instance exists |

**Parameters:**
- `--from, -f`: Sender agent ID (for reply identification) - **always include this**
- `--priority, -p`: 1-2 low, 3 normal, 4 urgent, 5 critical (default: 1)
- `--response`: Roundtrip mode - sender waits, **receiver MUST reply** using `--reply-to`
- `--no-response`: Oneway mode - fire and forget, no reply expected (default)
- `--reply-to`: Attach response to a specific task ID (use when replying to `--response` requests)

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

# Wait for response (roundtrip)
synapse send gemini "Analyze this" --response --from codex

# Reply to a --response request (use task_id from [A2A:task_id:sender])
synapse send codex "Here is my analysis..." --reply-to abc123 --from gemini
```

**Important:** Always use `--from` to identify yourself. When replying to a `--response` request, use `--reply-to <task_id>` to link your response.

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
# Interactive - prompts for scope selection
synapse init

# Output:
# ? Where do you want to create .synapse/?
#   ❯ User scope (~/.synapse/)
#     Project scope (./.synapse/)
```

Creates `.synapse/` directory with all template files (settings.json, default.md, gemini.md, delegate.md, file-safety.md).

### Edit Settings (Interactive TUI)

```bash
# Interactive TUI for editing settings
synapse config

# Edit specific scope directly
synapse config --scope user     # Edit ~/.synapse/settings.json
synapse config --scope project  # Edit ./.synapse/settings.json

# View current settings (read-only)
synapse config show
synapse config show --scope user
synapse config show --scope project
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
| `SYNAPSE_UDS_DIR` | UDS socket directory | `/tmp/synapse-a2a/` |

## Storage Locations

```text
~/.a2a/registry/     # Running agents (auto-cleaned)
~/.a2a/external/     # External A2A agents (persistent)
~/.synapse/          # User-level settings and logs
.synapse/            # Project-level settings
/tmp/synapse-a2a/    # Unix Domain Sockets (UDS) for inter-agent communication
```

**Note:** UDS socket location can be customized with `SYNAPSE_UDS_DIR` environment variable.
