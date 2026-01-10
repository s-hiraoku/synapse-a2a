---
name: synapse-a2a
description: This skill provides comprehensive guidance for inter-agent communication using the Synapse A2A framework. Use this skill when sending messages to other agents, routing @agent patterns, understanding priority levels, handling A2A protocol operations, managing task history, configuring settings, or using File Safety features for multi-agent coordination. Automatically triggered when agent communication, A2A protocol tasks, history operations, or file safety operations are detected.
---

# Synapse A2A Communication

## Overview

Synapse A2A enables inter-agent communication via Google A2A Protocol. All communication uses Message/Part + Task format. Messages are prefixed with `[A2A:<task_id>:<sender_id>]` for identification.

**Key Features:**
- **Agent Communication**: Send messages between agents with priority control
- **Task History**: Search, export, and analyze task execution history
- **File Safety**: Prevent file conflicts in multi-agent environments with locking
- **Settings Management**: Configure via settings.json or environment variables
- **Agent Monitoring**: Watch agent status in real-time

## Quick Reference

| Task | Command |
|------|---------|
| List agents | `synapse list` |
| Watch agents | `synapse list --watch` |
| Send message | `python3 synapse/tools/a2a.py send --target claude "message"` |
| Check file locks | `synapse file-safety locks` |
| View history | `synapse history list` |
| Initialize settings | `synapse init` |

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

### Agent Status

| Status | Meaning |
|--------|---------|
| **READY** | Agent is idle, waiting for input |
| **PROCESSING** | Agent is busy handling a task |

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
```

### Using A2A Tool

```bash
# List agents (with live check)
python3 synapse/tools/a2a.py list
python3 synapse/tools/a2a.py list --live

# Cleanup stale registry entries
python3 synapse/tools/a2a.py cleanup
```

## Sending Messages

### @Agent Routing Pattern

Use in agent terminal for quick messaging:

```
@<agent_name> [--non-response] <message>
```

**Examples:**
```
@codex このファイルをリファクタリングして
@gemini --non-response このイベントをログして
@claude-8100 コードレビューをお願いします
```

**Target Resolution:**
1. **Exact ID match**: `@synapse-claude-8100` matches exactly
2. **Type-port shorthand**: `@claude-8100` matches agent with type=claude, port=8100
3. **Type match (single)**: `@claude` works if only one claude agent exists
4. **Type match (multiple)**: Fails with hint to use `@type-port` format

### A2A Tool (Advanced)

For priority control and complex tasks:

```bash
python3 synapse/tools/a2a.py send --target <AGENT> [--priority <1-5>] [--non-response] "<MESSAGE>"
```

**Parameters:**
- `--target`: Agent ID (exact) or agent type (fuzzy)
- `--priority`: 1-4 normal, 5 = emergency interrupt (sends SIGINT first)
- `--non-response`: Do not require response from receiver

**Examples:**
```bash
# Normal task (default priority 1)
python3 synapse/tools/a2a.py send --target claude "Please review this code"

# Elevated priority
python3 synapse/tools/a2a.py send --target codex --priority 3 "Fix this bug"

# Emergency interrupt (priority 5)
python3 synapse/tools/a2a.py send --target codex --priority 5 "STOP immediately"

# Fire-and-forget (no response expected)
python3 synapse/tools/a2a.py send --target gemini --non-response "Log this event"
```

## Priority Levels

| Priority | Description | Use Case |
|----------|-------------|----------|
| 1 | Normal | Default priority for standard tasks |
| 2-3 | Elevated | Higher urgency tasks |
| 4 | Urgent | Follow-ups, status checks |
| 5 | Interrupt | Emergency, sends SIGINT first then message |

**Priority 5 behavior:**
1. Sends SIGINT to target agent (interrupts current task)
2. Waits briefly for interrupt processing
3. Sends the message

## Task History

Enable history tracking:
```bash
export SYNAPSE_HISTORY_ENABLED=true
synapse claude
```

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

## File Safety

File Safety prevents conflicts when multiple agents edit the same files.

### Enable File Safety

```bash
# Via environment variable
export SYNAPSE_FILE_SAFETY_ENABLED=true
synapse claude

# Via settings.json
synapse init
# Edit .synapse/settings.json
```

### Check Status

```bash
# Overall statistics
synapse file-safety status

# List active locks
synapse file-safety locks
synapse file-safety locks --agent claude
```

### Lock/Unlock Files

```bash
# Acquire lock
synapse file-safety lock /path/to/file.py claude --intent "Refactoring" --duration 300

# Release lock
synapse file-safety unlock /path/to/file.py claude
```

### View File History

```bash
# File modification history
synapse file-safety history /path/to/file.py
synapse file-safety history /path/to/file.py --limit 10

# Recent modifications (all files)
synapse file-safety recent
synapse file-safety recent --agent claude --limit 20
```

### Record Modifications

```bash
synapse file-safety record /path/to/file.py claude task-123 \
  --type MODIFY \
  --intent "Bug fix"
```

### Cleanup and Debug

```bash
# Clean old records
synapse file-safety cleanup --days 30 --force

# Debug info
synapse file-safety debug
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

## Port Ranges

| Agent  | Ports     |
|--------|-----------|
| Claude | 8100-8109 |
| Gemini | 8110-8119 |
| Codex  | 8120-8129 |

## A2A Endpoints

Standard Google A2A endpoints:

| Endpoint | URL |
|----------|-----|
| Agent Card | `http://localhost:<port>/.well-known/agent.json` |
| Send Task | `http://localhost:<port>/tasks/send` |
| Send Priority | `http://localhost:<port>/tasks/send-priority?priority=<1-5>` |
| Task Status | `http://localhost:<port>/tasks/<id>` |

## Message Format

PTY output format:
```
[A2A:<task_id>:<sender_id>] <message_content>
```

JSON payload:
```json
{
  "message": {
    "role": "user",
    "parts": [{"type": "text", "text": "<message>"}]
  },
  "metadata": {
    "sender": {
      "sender_id": "synapse-claude-8100",
      "sender_type": "claude",
      "sender_endpoint": "http://localhost:8100"
    },
    "response_required": true
  }
}
```

## Error Handling

### Agent Not Found

```
Error: No agent found matching 'xyz'
```
Solution: Use `synapse list` or `python3 synapse/tools/a2a.py list --live` to see available agents.

### Multiple Agents Found

```
Error: Ambiguous target 'codex'. Multiple agents found.
```
Solution: Use specific identifier like `@codex-8120`.

### Agent Not Responding

```
Error: Agent 'synapse-claude-8100' server on port 8100 is not responding.
```
Solution: The A2A server may not be started. Restart the agent with `synapse claude`.

### File Locked by Another Agent

```
Error: File is locked by gemini (expires: 2026-01-09T12:00:00)
```
Solution: Wait for lock to expire or coordinate with the other agent.

## Storage Locations

```
~/.a2a/registry/     # Running agents (auto-cleaned)
~/.a2a/external/     # External A2A agents (persistent)
~/.synapse/          # User-level settings and logs
.synapse/            # Project-level settings
```

## Multi-Agent Workflow Example

```bash
# Terminal 1: Start Claude with all features
SYNAPSE_HISTORY_ENABLED=true SYNAPSE_FILE_SAFETY_ENABLED=true synapse claude

# Terminal 2: Start Codex
SYNAPSE_HISTORY_ENABLED=true SYNAPSE_FILE_SAFETY_ENABLED=true synapse codex

# Terminal 3: Monitor
synapse list --watch

# In Claude terminal:
# 1. Check Codex is ready
# 2. Delegate coding task
@codex src/auth.py をリファクタリングして。作業前にファイルロックを取得してください。

# Monitor progress
synapse file-safety locks
synapse history list --agent codex --limit 5
```
