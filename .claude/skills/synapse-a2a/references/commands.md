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

### @Agent Pattern

```text
@<agent_name> [--non-response] <message>
```

Examples:
```text
@codex Please refactor this file
@gemini --non-response Log this event
@claude-8100 Review this code
```

### A2A Tool

```bash
python -m synapse.tools.a2a send --target <AGENT> [--priority <1-5>] [--non-response] "<MESSAGE>"
```

**Parameters:**
- `--target`: Agent ID (exact) or agent type (fuzzy)
- `--priority`: 1-2 low/background, 3 normal, 4 urgent follow-up, 5 critical
- `--non-response`: Do not require response from receiver

Examples:
```bash
# Normal task (default priority 1)
python -m synapse.tools.a2a send --target claude "Please review this code"

# Normal priority
python -m synapse.tools.a2a send --target codex --priority 3 "Fix this bug"

# Urgent follow-up (priority 4)
python -m synapse.tools.a2a send --target codex --priority 4 "Status update?"

# Critical interrupt (priority 5)
python -m synapse.tools.a2a send --target codex --priority 5 "STOP immediately"

# Fire-and-forget (no response expected)
python -m synapse.tools.a2a send --target gemini --non-response "Log this event"
```

### A2A Tool Utilities

```bash
# List agents (with live check)
python -m synapse.tools.a2a list
python -m synapse.tools.a2a list --live

# Cleanup stale registry entries
python -m synapse.tools.a2a cleanup
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
```
