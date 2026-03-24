# Settings & Configuration

## Overview

Synapse uses a hierarchical settings system with three scopes:

| Scope | Location | Priority |
|-------|----------|:--------:|
| **Local** | `.synapse/settings.local.json` | Highest |
| **Project** | `.synapse/settings.json` | Medium |
| **User** | `~/.synapse/settings.json` | Lowest |

Settings are merged top-down — local overrides project, project overrides user.

## Initialization

```bash
synapse init                           # Interactive scope selection
synapse init --scope user              # Create ~/.synapse/settings.json
synapse init --scope project           # Create ./.synapse/settings.json
```

`synapse init` uses a **merge strategy**: only template files are copied into the `.synapse/` directory. If the directory already exists, user-generated data is preserved:

| Overwritten (templates) | Preserved (user data) |
|------------------------|-----------------------|
| `settings.json` | `agents/` (saved agent definitions) |
| `default.md` | `*.db` (file_safety, memory) |
| `gemini.md` | `sessions/` |
| `file-safety.md` | `workflows/` |
| `learning.md` | `worktrees/` |
| `shared-memory.md` | `settings.local.json` |
| `proactive.md` | |

This makes it safe to re-run `synapse init` after upgrading to pick up new templates without losing project data.

## Interactive Config Editor

```bash
synapse config                         # Interactive TUI editor
synapse config --scope user            # Edit user settings directly
synapse config --scope project         # Edit project settings directly
```

## View Settings

```bash
synapse config show                    # Show merged settings (read-only)
synapse config show --scope user       # Show user settings only
synapse config show --scope project    # Show project settings only
```

## Reset Settings

```bash
synapse reset                          # Interactive scope selection
synapse reset --scope user             # Reset user settings to defaults
synapse reset --scope both -f          # Reset both without confirmation
```

## Settings Schema

```json
{
  "env": {
    "SYNAPSE_HISTORY_ENABLED": "true",
    "SYNAPSE_FILE_SAFETY_ENABLED": "true",
    "SYNAPSE_FILE_SAFETY_DB_PATH": ".synapse/file_safety.db",
    "SYNAPSE_LEARNING_MODE_ENABLED": "false",
    "SYNAPSE_LEARNING_MODE_TRANSLATION": "false",
    "SYNAPSE_TASK_BOARD_ENABLED": "true",
    "SYNAPSE_SHARED_MEMORY_ENABLED": "true",
    "SYNAPSE_SHARED_MEMORY_DB_PATH": ".synapse/memory.db",
    "SYNAPSE_PROACTIVE_MODE_ENABLED": "false"
  },
  "a2a_flow": "auto",
  "approvalMode": "required",
  "hooks": {
    "on_idle": "",
    "on_task_completed": ""
  },
  "shutdown": {
    "timeout_seconds": 30,
    "graceful_enabled": true
  },
  "delegate_mode": {
    "deny_file_locks": true
  },
  "list": {
    "columns": ["ID", "NAME", "STATUS", "TYPE", "PORT", "TRANSPORT", "WORKING_DIR"]
  }
}
```

## Environment Variables

### Core

| Variable | Default | Description |
|----------|---------|-------------|
| `SYNAPSE_AGENT_ID` | Auto-set | Current agent ID |
| `SYNAPSE_AGENT_TYPE` | Auto-set | Agent type (claude/gemini/etc.) |
| `SYNAPSE_PORT` | Auto-set | A2A server port |
| `SYNAPSE_TOOL_ARGS` | — | Tool arguments (JSON) |

### Features

| Variable | Default | Description |
|----------|---------|-------------|
| `SYNAPSE_HISTORY_ENABLED` | `true` | Enable task history |
| `SYNAPSE_FILE_SAFETY_ENABLED` | `false` | Enable file safety |
| `SYNAPSE_TASK_BOARD_ENABLED` | `true` | Enable task board |
| `SYNAPSE_SHARED_MEMORY_ENABLED` | `true` | Enable shared memory |
| `SYNAPSE_LEARNING_MODE_ENABLED` | `false` | Enable learning mode |
| `SYNAPSE_LEARNING_MODE_TRANSLATION` | `false` | Enable translation mode |
| `SYNAPSE_PROACTIVE_MODE_ENABLED` | `false` | Enable [proactive mode](proactive-mode.md) |

### Authentication

| Variable | Default | Description |
|----------|---------|-------------|
| `SYNAPSE_AUTH_ENABLED` | `false` | Enable API authentication |
| `SYNAPSE_API_KEYS` | — | Comma-separated API keys |
| `SYNAPSE_ADMIN_KEY` | — | Admin API key |
| `SYNAPSE_ALLOW_LOCALHOST` | `true` | Skip auth for localhost |

### Paths

| Variable | Default | Description |
|----------|---------|-------------|
| `SYNAPSE_UDS_DIR` | `/tmp/synapse-a2a` | Unix Domain Socket directory |
| `SYNAPSE_FILE_SAFETY_DB_PATH` | `.synapse/file_safety.db` | File safety database |
| `SYNAPSE_SHARED_MEMORY_DB_PATH` | `.synapse/memory.db` | Shared memory database |
| `SYNAPSE_SKILLS_DIR` | `~/.synapse/skills` | Central skill store |

### Message Handling

| Variable | Default | Description |
|----------|---------|-------------|
| `SYNAPSE_SEND_MESSAGE_THRESHOLD` | ~100KB | Auto-file threshold for send |
| `SYNAPSE_LONG_MESSAGE_THRESHOLD` | 200 chars | PTY long message threshold |
| `SYNAPSE_LONG_MESSAGE_TTL` | 3600s | Temp file TTL |

### Timeouts

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENT_READY_TIMEOUT` | 30s | Readiness Gate timeout |
| `SYNAPSE_HOOK_TIMEOUT` | 30s | Hook execution timeout |
| `SYNAPSE_WEBHOOK_TIMEOUT` | 10s | Webhook delivery timeout |

## Instructions Customization

Customize the initial instructions sent to agents:

```bash
synapse instructions show                  # Show default instruction
synapse instructions show claude           # Show Claude-specific
synapse instructions files claude          # List instruction files
synapse instructions send claude           # Send to running agent
synapse instructions send claude --preview # Preview without sending
```

Instructions support placeholders:

| Placeholder | Replaced With |
|-------------|---------------|
| `{agent_id}` | Runtime ID (e.g., `synapse-claude-8100`) |
| `{port}` | Server port |
| `{agent_type}` | Agent type |
| `{name}` | Custom name |
| `{role}` | Agent role |

## Quality Gates (Hooks)

Configure shell commands that run on status transitions:

```json
{
  "hooks": {
    "on_idle": "pytest tests/ --tb=short",
    "on_task_completed": "pytest tests/ && ruff check"
  }
}
```

Exit codes:

| Code | Behavior |
|:----:|----------|
| 0 | Allow transition |
| 2 | Deny transition |
| Other | Allow with warning |

## .gitignore Recommendations

```gitignore
# Synapse local settings (don't commit)
.synapse/settings.local.json
.synapse/file_safety.db
.synapse/memory.db

# Keep project settings (commit)
# .synapse/settings.json
# .synapse/default.md
```
