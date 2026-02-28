# Configuration Reference

## Settings Files

| Scope | Path | Priority |
|-------|------|:--------:|
| Local | `.synapse/settings.local.json` | 1 (highest) |
| Project | `.synapse/settings.json` | 2 |
| User | `~/.synapse/settings.json` | 3 (lowest) |

## Complete Settings Schema

```json
{
  "env": {
    "SYNAPSE_HISTORY_ENABLED": "true",
    "SYNAPSE_FILE_SAFETY_ENABLED": "true",
    "SYNAPSE_FILE_SAFETY_DB_PATH": ".synapse/file_safety.db",
    "SYNAPSE_FILE_SAFETY_RETENTION_DAYS": "30",
    "SYNAPSE_AUTH_ENABLED": "false",
    "SYNAPSE_API_KEYS": "",
    "SYNAPSE_ADMIN_KEY": "",
    "SYNAPSE_ALLOW_LOCALHOST": "true",
    "SYNAPSE_USE_HTTPS": "false",
    "SYNAPSE_WEBHOOK_SECRET": "",
    "SYNAPSE_WEBHOOK_TIMEOUT": "10",
    "SYNAPSE_WEBHOOK_MAX_RETRIES": "3",
    "SYNAPSE_LONG_MESSAGE_THRESHOLD": "200",
    "SYNAPSE_LONG_MESSAGE_TTL": "3600",
    "SYNAPSE_LONG_MESSAGE_DIR": "",
    "SYNAPSE_TASK_BOARD_ENABLED": "true",
    "SYNAPSE_TASK_BOARD_DB_PATH": ".synapse/task_board.db",
    "SYNAPSE_SHARED_MEMORY_ENABLED": "true",
    "SYNAPSE_SHARED_MEMORY_DB_PATH": ".synapse/memory.db",
    "SYNAPSE_LEARNING_MODE_ENABLED": "false",
    "SYNAPSE_LEARNING_MODE_TRANSLATION": "false"
  },
  "instructions": {
    "default": "default.md",
    "claude": "",
    "gemini": "",
    "codex": ""
  },
  "approvalMode": "required",
  "a2a": {
    "flow": "auto"
  },
  "resume_flags": {
    "claude": ["--continue", "--resume", "-c", "-r"],
    "codex": ["resume"],
    "gemini": ["--resume", "-r"]
  },
  "list": {
    "columns": ["ID", "NAME", "STATUS", "CURRENT", "TRANSPORT", "WORKING_DIR", "EDITING_FILE"]
  },
  "shutdown": {
    "timeout_seconds": 30,
    "graceful_enabled": true
  },
  "delegate_mode": {
    "deny_file_locks": true
  },
  "hooks": {
    "on_idle": "",
    "on_task_completed": ""
  }
}
```

## Environment Variables

### Core Runtime

| Variable | Default | Description |
|----------|---------|-------------|
| `SYNAPSE_AGENT_ID` | Auto | Agent identifier (e.g., `synapse-claude-8100`) |
| `SYNAPSE_AGENT_TYPE` | Auto | Agent type (`claude`, `gemini`, etc.) |
| `SYNAPSE_PORT` | Auto | A2A server port |
| `SYNAPSE_TOOL_ARGS` | — | Tool arguments as JSON string |

### Feature Toggles

| Variable | Default | Description |
|----------|---------|-------------|
| `SYNAPSE_HISTORY_ENABLED` | `true` | Task history tracking |
| `SYNAPSE_FILE_SAFETY_ENABLED` | `true` | File locking and tracking |
| `SYNAPSE_FILE_SAFETY_RETENTION_DAYS` | `30` | Retention period for file safety records |
| `SYNAPSE_TASK_BOARD_ENABLED` | `true` | Shared task board |
| `SYNAPSE_SHARED_MEMORY_ENABLED` | `true` | Cross-agent shared memory |
| `SYNAPSE_LEARNING_MODE_ENABLED` | `false` | Prompt improvement feedback |
| `SYNAPSE_LEARNING_MODE_TRANSLATION` | `false` | JP→EN translation assistance |

### Authentication

| Variable | Default | Description |
|----------|---------|-------------|
| `SYNAPSE_AUTH_ENABLED` | `false` | API key authentication |
| `SYNAPSE_API_KEYS` | — | Comma-separated API keys |
| `SYNAPSE_ADMIN_KEY` | — | Admin key for management ops |
| `SYNAPSE_ALLOW_LOCALHOST` | `true` | Skip auth for localhost |
| `SYNAPSE_USE_HTTPS` | `false` | Enable HTTPS URLs in generated endpoints |

### Storage Paths

| Variable | Default | Description |
|----------|---------|-------------|
| `SYNAPSE_UDS_DIR` | `/tmp/synapse-a2a` | Unix Domain Socket directory |
| `SYNAPSE_REPLY_TARGET_DIR` | `~/.a2a/reply` | Reply target persistence directory |
| `SYNAPSE_FILE_SAFETY_DB_PATH` | `.synapse/file_safety.db` | File safety database |
| `SYNAPSE_TASK_BOARD_DB_PATH` | `.synapse/task_board.db` | Task board database |
| `SYNAPSE_SHARED_MEMORY_DB_PATH` | `.synapse/memory.db` | Shared memory database |
| `SYNAPSE_SKILLS_DIR` | `~/.synapse/skills` | Central skill store |

### Message Handling

| Variable | Default | Description |
|----------|---------|-------------|
| `SYNAPSE_SEND_MESSAGE_THRESHOLD` | ~100KB | Auto-file for `synapse send` |
| `SYNAPSE_LONG_MESSAGE_THRESHOLD` | 200 chars | PTY long message threshold |
| `SYNAPSE_LONG_MESSAGE_TTL` | 3600s | Temp message file TTL |
| `SYNAPSE_LONG_MESSAGE_DIR` | System temp dir | Override long message temp directory |

### Timeouts

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENT_READY_TIMEOUT` | 30s | Readiness Gate timeout |
| `SYNAPSE_HOOK_TIMEOUT` | 30s | Hook execution timeout |
| `SYNAPSE_WEBHOOK_TIMEOUT` | 10s | Webhook delivery timeout |
| `SYNAPSE_WEBHOOK_MAX_RETRIES` | 3 | Webhook retry count |

### Webhook

| Variable | Default | Description |
|----------|---------|-------------|
| `SYNAPSE_WEBHOOK_SECRET` | — | Global webhook HMAC secret |
| `SYNAPSE_WEBHOOK_TIMEOUT` | 10s | Delivery timeout |
| `SYNAPSE_WEBHOOK_MAX_RETRIES` | 3 | Retry count |

## Storage Locations

| Storage | Path | Format | Purpose |
|---------|------|--------|---------|
| Agent Registry | `~/.a2a/registry/` | JSON files | Running agents |
| Reply Targets | `~/.a2a/reply/` | JSON files | Reply routing persistence |
| External Agents | `~/.a2a/external/` | JSON files | External A2A agents |
| User Settings | `~/.synapse/settings.json` | JSON | User preferences |
| Project Settings | `.synapse/settings.json` | JSON | Project config |
| Local Settings | `.synapse/settings.local.json` | JSON | Local overrides |
| Task History | `~/.synapse/history/history.db` | SQLite | Task records |
| Task Board | `.synapse/task_board.db` | SQLite (WAL) | Task coordination |
| File Safety | `.synapse/file_safety.db` | SQLite (WAL) | File locks/tracking |
| Shared Memory | `.synapse/memory.db` | SQLite (WAL) | Cross-agent knowledge base |
| Logs | `~/.synapse/logs/` | Text | Agent logs |
| Skills | `~/.synapse/skills/` | Markdown | Central skill store |

## Instruction Placeholders

Available in instruction templates:

| Placeholder | Replaced With |
|-------------|---------------|
| `{{agent_id}}` | Agent ID (`synapse-claude-8100`) |
| `{{port}}` | Server port (`8100`) |
| `{{agent_type}}` | Agent type (`claude`) |
| `{{agent_name}}` | Custom name (fallback: agent ID) |
| `{{role}}` | Agent role |

## Hook Configuration

```json
{
  "hooks": {
    "on_idle": "pytest tests/ --tb=short",
    "on_task_completed": "pytest tests/ && ruff check"
  }
}
```

**Environment variables passed to hooks:**

| Variable | Description |
|----------|-------------|
| `SYNAPSE_AGENT_ID` | Agent ID |
| `SYNAPSE_AGENT_NAME` | Custom name |
| `SYNAPSE_LAST_TASK_ID` | Last completed task |
| `SYNAPSE_STATUS_FROM` | Previous status |
| `SYNAPSE_STATUS_TO` | New status |

**Exit codes:**

| Code | Behavior |
|:----:|----------|
| 0 | Allow transition |
| 2 | Deny transition |
| Other | Allow with warning |
