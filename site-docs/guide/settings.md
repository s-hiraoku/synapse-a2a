# Settings & Configuration

## Overview

Synapse uses a hierarchical settings system with three scopes:

| Scope | Location | Priority |
|-------|----------|:--------:|
| **Local** | `.synapse/settings.local.json` | Highest |
| **Project** | `.synapse/settings.json` | Medium |
| **User** | `~/.synapse/settings.json` | Lowest |

Settings are merged top-down — local overrides project, project overrides user.

## How Merging Works

Settings are merged section by section (`env`, `instructions`, `a2a`, etc.). Within each section, **only keys present in the higher-priority scope are overwritten**; keys that don't exist in the higher scope are kept from the lower scope.

### Example: Partial Override

If User scope has all settings and Project scope has just one:

```
User:    env: { SYNAPSE_HISTORY_ENABLED: "true", SYNAPSE_LEARNING_MODE_ENABLED: "false", SYNAPSE_LOG_LEVEL: "INFO", ... }
Project: env: { SYNAPSE_LEARNING_MODE_ENABLED: "true" }
```

Result:
```
env: { SYNAPSE_HISTORY_ENABLED: "true", SYNAPSE_LEARNING_MODE_ENABLED: "true", SYNAPSE_LOG_LEVEL: "INFO", ... }
```

Only `SYNAPSE_LEARNING_MODE_ENABLED` is overwritten by Project scope. All other values come from User scope.

### Watch Out: Unintended Overrides

If you enable a feature in User scope but the Project scope template has the default `"false"`, the project value wins:

```
User:    env: { SYNAPSE_LEARNING_MODE_ENABLED: "true" }      ← personal preference
Project: env: { SYNAPSE_LEARNING_MODE_ENABLED: "false" }      ← template default
→ Result: SYNAPSE_LEARNING_MODE_ENABLED = "false"              ← Project wins
```

**Fix**: Remove keys from Project scope that don't need project-wide control, or override in `settings.local.json` (Local scope, highest priority).

### Recommended Scope Usage

| Scope | What to put here | Examples |
|-------|-----------------|---------|
| **User** | Personal preferences, global defaults | Learning mode, log level, DB paths |
| **Project** | Project-specific, team-shared settings | File safety, approval mode, A2A flow |
| **Local** | Personal overrides for this project only | Override a Project setting just for you |

## Initialization

```bash
synapse init                           # Interactive scope selection
synapse init --scope user              # Create ~/.synapse/settings.json
synapse init --scope project           # Create ./.synapse/settings.json
```

`synapse init` uses a **merge strategy**: template files are copied into the `.synapse/` directory, and `settings.json` is **smart-merged** (new keys added, your values preserved). If the directory already exists, user-generated data is preserved:

| Updated (templates) | Smart-merged | Preserved (user data) |
|--------------------|-------------|----------------------|
| `default.md` | `settings.json` | `agents/` (saved agent definitions) |
| `gemini.md` | | `*.db` (file_safety) |
| `file-safety.md` | | `sessions/` |
| `learning.md` | | `workflows/` |
| `shared-memory.md` | | `worktrees/` |
| `proactive.md` | | `settings.local.json` |

This makes it safe to re-run `synapse init` after upgrading to pick up new templates and configuration keys without losing your customizations.

## Upgrading

After upgrading Synapse, run `synapse init` to pick up new configuration keys:

```bash
pip install --upgrade synapse-a2a   # or: pipx upgrade synapse-a2a
synapse init --scope project        # Smart-merge: adds new keys, keeps your values
synapse init --scope user           # Same for user-level settings
```

New environment variables are added to your `settings.json` with their default values. Any values you have already customized are preserved. You can verify the merged result with:

```bash
synapse config show --scope merged
```

## Interactive Config Editor

```bash
synapse config                         # Interactive TUI editor with effective values and sources
```

- `synapse config` automatically chooses the correct scope to edit for each setting
- Effective values show their current source, for example `LEARNING_MODE_ENABLED: ON (user) [env: ON]`
- Editing a setting writes directly to the file for the scope that currently provides the effective value
- Settings overridden by `os.environ` are shown as read-only
- Use `synapse config show --scope user|project|merged` when you want a scope-specific read-only view

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
    "SYNAPSE_SHARED_MEMORY_ENABLED": "true",
    "SYNAPSE_SHARED_MEMORY_DB_PATH": "~/.synapse/memory.db",
    "SYNAPSE_PROACTIVE_MODE_ENABLED": "false",
    "SYNAPSE_OBSERVATION_ENABLED": "true",
    "SYNAPSE_SEND_MESSAGE_THRESHOLD": "102400",
    "SYNAPSE_CANVAS_PORT": "3000",
    "SYNAPSE_LOG_LEVEL": "INFO",
    "SYNAPSE_LOG_FILE": "false",
    "SYNAPSE_AGENT_SAVE_PROMPT_ENABLED": "true"
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
| `SYNAPSE_FILE_SAFETY_ENABLED` | `true` | Enable file safety |
| `SYNAPSE_SHARED_MEMORY_ENABLED` | `true` | Enable shared memory |
| `SYNAPSE_LEARNING_MODE_ENABLED` | `false` | Enable learning mode |
| `SYNAPSE_LEARNING_MODE_TRANSLATION` | `false` | Enable translation mode |
| `SYNAPSE_PROACTIVE_MODE_ENABLED` | `false` | Enable [proactive mode](proactive-mode.md) |
| `SYNAPSE_OBSERVATION_ENABLED` | `true` | Enable observation / self-learning |
| `SYNAPSE_AGENT_SAVE_PROMPT_ENABLED` | `true` | Show save-agent-definition prompt on exit |

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
| `SYNAPSE_SHARED_MEMORY_DB_PATH` | `~/.synapse/memory.db` | Shared memory database |
| `SYNAPSE_HISTORY_DB_PATH` | `~/.synapse/history/history.db` | History database |
| `SYNAPSE_CANVAS_DB_PATH` | `~/.synapse/canvas.db` | Canvas database |
| `SYNAPSE_WORKFLOW_RUNS_DB_PATH` | `.synapse/workflow_runs.db` | Workflow runs database |
| `SYNAPSE_OBSERVATION_DB_PATH` | `.synapse/observations.db` | Observations database |
| `SYNAPSE_INSTINCT_DB_PATH` | `.synapse/instincts.db` | Instincts database |
| `SYNAPSE_REGISTRY_DIR` | `~/.a2a/registry` | Agent registry directory |
| `SYNAPSE_EXTERNAL_REGISTRY_DIR` | `~/.a2a/external` | External registry directory |
| `SYNAPSE_REPLY_TARGET_DIR` | `~/.a2a/reply` | Reply target persistence |
| `SYNAPSE_SKILLS_DIR` | `~/.synapse/skills` | Central skill store |

### Message Handling

| Variable | Default | Description |
|----------|---------|-------------|
| `SYNAPSE_SEND_MESSAGE_THRESHOLD` | `102400` | Auto-file threshold for send (bytes) |
| `SYNAPSE_LONG_MESSAGE_THRESHOLD` | `200` | PTY long message threshold (chars) |
| `SYNAPSE_LONG_MESSAGE_TTL` | `3600` | Temp file TTL (seconds) |
| `SYNAPSE_REPLY_TARGET_TTL_SECONDS` | `1800` | Reply target TTL (seconds) |

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

# Keep project settings (commit)
# .synapse/settings.json
# .synapse/default.md
```
