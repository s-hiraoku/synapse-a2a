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
    "SYNAPSE_SHARED_MEMORY_ENABLED": "true",
    "SYNAPSE_SHARED_MEMORY_DB_PATH": "~/.synapse/memory.db",
    "SYNAPSE_LEARNING_MODE_ENABLED": "false",
    "SYNAPSE_LEARNING_MODE_TRANSLATION": "false",
    "SYNAPSE_PROACTIVE_MODE_ENABLED": "false",
    "SYNAPSE_OBSERVATION_ENABLED": "true",
    "SYNAPSE_SEND_MESSAGE_THRESHOLD": "102400",
    "SYNAPSE_CANVAS_PORT": "3000",
    "SYNAPSE_LOG_LEVEL": "INFO",
    "SYNAPSE_LOG_FILE": "false",
    "SYNAPSE_AGENT_SAVE_PROMPT_ENABLED": "true"
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
| `SYNAPSE_AGENT_ID` | Auto | Runtime ID (e.g., `synapse-claude-8100`) |
| `SYNAPSE_AGENT_TYPE` | Auto | Agent type (`claude`, `gemini`, etc.) |
| `SYNAPSE_PORT` | Auto | A2A server port |
| `SYNAPSE_TOOL_ARGS` | — | Tool arguments as JSON string |
| `SYNAPSE_WORKTREE_PATH` | Auto | Worktree directory path (set when agent spawns with `--worktree`) |
| `SYNAPSE_WORKTREE_BRANCH` | Auto | Worktree branch name (set when agent spawns with `--worktree`) |
| `SYNAPSE_WORKTREE_BASE_BRANCH` | Auto | Base branch for worktree cleanup new-commit detection (3-step fallback: symbolic-ref, `origin/main`, `HEAD`) |

### Feature Toggles

| Variable | Default | Description |
|----------|---------|-------------|
| `SYNAPSE_HISTORY_ENABLED` | `true` | Task history tracking |
| `SYNAPSE_FILE_SAFETY_ENABLED` | `true` | File locking and tracking |
| `SYNAPSE_FILE_SAFETY_RETENTION_DAYS` | `30` | Retention period for file safety records |
| `SYNAPSE_SHARED_MEMORY_ENABLED` | `true` | Cross-agent shared memory |
| `SYNAPSE_LEARNING_MODE_ENABLED` | `false` | Prompt improvement feedback |
| `SYNAPSE_LEARNING_MODE_TRANSLATION` | `false` | JP→EN translation assistance |
| `SYNAPSE_PROACTIVE_MODE_ENABLED` | `false` | Judgment-based Synapse feature usage guidance |
| `SYNAPSE_OBSERVATION_ENABLED` | `true` | Enable observation / self-learning |
| `SYNAPSE_AGENT_SAVE_PROMPT_ENABLED` | `true` | Show save-agent-definition prompt on exit |

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
| `SYNAPSE_SHARED_MEMORY_DB_PATH` | `~/.synapse/memory.db` | Shared memory database |
| `SYNAPSE_HISTORY_DB_PATH` | `~/.synapse/history/history.db` | History database |
| `SYNAPSE_CANVAS_DB_PATH` | `~/.synapse/canvas.db` | Canvas database |
| `SYNAPSE_WORKFLOW_RUNS_DB_PATH` | `.synapse/workflow_runs.db` | Workflow runs database |
| `SYNAPSE_OBSERVATION_DB_PATH` | `.synapse/observations.db` | Observations database |
| `SYNAPSE_INSTINCT_DB_PATH` | `.synapse/instincts.db` | Instincts database |
| `SYNAPSE_REGISTRY_DIR` | `~/.a2a/registry` | Agent registry directory |
| `SYNAPSE_EXTERNAL_REGISTRY_DIR` | `~/.a2a/external` | External registry directory |
| `SYNAPSE_SKILLS_DIR` | `~/.synapse/skills` | Central skill store |

### Message Handling

| Variable | Default | Description |
|----------|---------|-------------|
| `SYNAPSE_SEND_MESSAGE_THRESHOLD` | ~100KB | Auto-file for `synapse send` |
| `SYNAPSE_LONG_MESSAGE_THRESHOLD` | 200 chars | PTY long message threshold |
| `SYNAPSE_LONG_MESSAGE_TTL` | 3600s | Temp message file TTL |
| `SYNAPSE_LONG_MESSAGE_DIR` | System temp dir | Override long message temp directory |

### Canvas & Logging

| Variable | Default | Description |
|----------|---------|-------------|
| `SYNAPSE_CANVAS_PORT` | `3000` | Canvas dashboard port |
| `SYNAPSE_LOG_LEVEL` | `INFO` | Log level (DEBUG/INFO/WARNING/ERROR) |
| `SYNAPSE_LOG_FILE` | `false` | Enable file logging |

### Timeouts

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENT_READY_TIMEOUT` | 30s | Readiness Gate timeout |
| `SYNAPSE_SEND_WAIT_TIMEOUT` | 30s | Max seconds `synapse send` waits for a PROCESSING target to become READY |
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
| Saved Agents (User) | `~/.synapse/agents/` | `.agent` files | User-scope saved agent definitions |
| Saved Agents (Project) | `.synapse/agents/` | `.agent` files | Project-scope saved agent definitions |
| Task History | `~/.synapse/history/history.db` | SQLite | Task records |
| File Safety | `.synapse/file_safety.db` | SQLite (WAL) | File locks/tracking |
| Shared Memory | `~/.synapse/memory.db` | SQLite (WAL) | Cross-agent knowledge base |
| Logs | `~/.synapse/logs/` | Text | Agent logs |
| Skills | `~/.synapse/skills/` | Markdown | Central skill store |

## Instruction Placeholders

Available in instruction templates:

| Placeholder | Replaced With |
|-------------|---------------|
| `{{agent_id}}` | Runtime ID (`synapse-claude-8100`) |
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
