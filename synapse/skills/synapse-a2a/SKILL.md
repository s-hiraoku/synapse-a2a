---
name: synapse-a2a
description: This skill provides comprehensive guidance for inter-agent communication using the Synapse A2A framework. Use this skill when sending messages to other agents, routing @agent patterns, understanding priority levels, or handling A2A protocol operations. Also covers task history management including search, statistics, export, and cleanup operations. Automatically triggered when agent communication, A2A protocol tasks, or history operations are detected.
---

# Synapse A2A Communication

## Overview

Synapse A2A enables inter-agent communication via Google A2A Protocol. All communication uses Message/Part + Task format. Messages are prefixed with `[A2A:<task_id>:<sender_id>]` for identification.

Additionally, Synapse A2A provides comprehensive task history management capabilities:
- **Search**: Find tasks by keywords with flexible logic (OR/AND)
- **Statistics**: View task counts, success rates, and per-agent metrics
- **Export**: Extract data in JSON or CSV formats
- **Cleanup**: Manage database size with retention policies (days-based or size-based)

## Core Commands

### Task History Management

View, search, and analyze task execution history with these commands:

```bash
# List task history (default: 50 entries)
synapse history list
synapse history list --agent claude --limit 100

# Show task details
synapse history show <task_id>

# Search by keywords
synapse history search "Python" "Docker" --logic OR
synapse history search "error" --agent claude --limit 20

# View statistics
synapse history stats
synapse history stats --agent gemini

# Export data
synapse history export --format json > history.json
synapse history export --format csv --agent claude > claude_tasks.csv
synapse history export --format json --output export.json

# Cleanup old data
synapse history cleanup --days 30
synapse history cleanup --max-size 100
```

**Parameters:**
- `--agent`: Filter by agent name (e.g., `claude`, `gemini`, `codex`)
- `--limit`: Maximum number of results (default: 50)
- `--logic`: Search logic - `OR` (any keyword) or `AND` (all keywords)
- `--format`: Export format - `json` or `csv`
- `--output`: Output file path (default: stdout)
- `--days`: Delete observations older than N days
- `--max-size`: Keep database under N megabytes

**Enable History:**
```bash
export SYNAPSE_HISTORY_ENABLED=true
synapse claude  # Start with history enabled
```

### Send Message to Agent

```bash
python3 synapse/tools/a2a.py send --target <AGENT> [--priority <1-5>] [--non-response] "<MESSAGE>"
```

**Parameters:**
- `--target`: Agent ID (exact, e.g., `synapse-claude-8100`) or agent type (fuzzy, e.g., `claude`)
- `--priority`: 1-4 normal, 5 = emergency interrupt (sends SIGINT first)
- `--non-response`: Do not require response from receiver (default: response required)
- `<MESSAGE>`: Content to send

**Examples:**
```bash
# Send with response expected (default)
python3 synapse/tools/a2a.py send --target claude "Please review this code"

# Send without expecting response
python3 synapse/tools/a2a.py send --target gemini --non-response "Log this event"

# Emergency interrupt (priority 5)
python3 synapse/tools/a2a.py send --target codex --priority 5 "STOP"
```

### List Available Agents

```bash
python3 synapse/tools/a2a.py list [--live]
```

- `--live`: Only show running agents (auto-cleanup stale entries)

### Cleanup Stale Entries

```bash
python3 synapse/tools/a2a.py cleanup
```

Removes registry entries for agents that are no longer running.

## @Agent Routing Pattern

When typing in an agent terminal, use:

```
@<agent_name> [--non-response] <message>
```

**Behavior:**
- **Default**: Response is expected from receiver
- **`--non-response`**: Receiver processes the task and does not send response back

### Target Resolution

1. **Exact ID match**: `@synapse-claude-8100` matches exactly
2. **Type-port shorthand**: `@claude-8100` matches agent with type=claude, port=8100
3. **Type match (single)**: `@claude` works if only one claude agent exists
4. **Type match (multiple)**: Fails with hint to use `@type-port` format

## Priority Levels

| Priority | Description | Use Case |
|----------|-------------|----------|
| 1 | Normal | Default priority |
| 2-4 | Elevated | Higher urgency tasks |
| 5 | Interrupt | Emergency, sends SIGINT first |

**Priority 5 behavior:**
1. Sends SIGINT to target agent
2. Waits briefly for interrupt processing
3. Sends the message

## Message Format

All A2A messages use this format in PTY output:

```
[A2A:<task_id>:<sender_id>] <message_content>
```

- `task_id`: Unique identifier for the task
- `sender_id`: ID of the sending agent (e.g., `synapse-claude-8100`)

## Response Handling

### Default (response required)
1. Message is sent to target
2. Target processes the message
3. Target sends response back to sender

### With --non-response
1. Message is sent to target
2. Target processes the message
3. No response is sent back

## Port Ranges

| Agent  | Ports     |
|--------|-----------|
| Claude | 8100-8109 |
| Gemini | 8110-8119 |
| Codex  | 8120-8129 |

## Error Handling

### Agent Not Found
```
Error: No agent found matching 'xyz'
```
Use `python3 synapse/tools/a2a.py list --live` to see available agents.

### Multiple Agents Found
```
Error: Ambiguous target 'codex'. Multiple agents found.
```
Use specific identifier like `@codex-8120`.

### Agent Not Responding
```
Error: Agent 'synapse-claude-8100' server on port 8100 is not responding.
```
The A2A server may not be started. Restart the agent.

## A2A Endpoints

Standard Google A2A endpoints are available:

- **Agent Card**: `http://localhost:<port>/.well-known/agent.json`
- **Send Task**: `http://localhost:<port>/tasks/send`
- **Send Priority**: `http://localhost:<port>/tasks/send-priority?priority=<1-5>`
- **Task Status**: `http://localhost:<port>/tasks/<id>`

## Metadata

Messages include metadata:

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
