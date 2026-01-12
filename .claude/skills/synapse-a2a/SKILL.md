---
name: synapse-a2a
description: This skill provides comprehensive guidance for inter-agent communication using the Synapse A2A framework. Use this skill when sending messages to other agents, routing @agent patterns, understanding priority levels, or handling A2A protocol operations. Automatically triggered when agent communication or A2A protocol tasks are detected.
---

# Synapse A2A Communication

## Overview

Synapse A2A enables inter-agent communication via Google A2A Protocol. All communication uses Message/Part + Task format. Messages are prefixed with `[A2A:<task_id>:<sender_id>]` for identification.

## Core Commands

### Send Message to Agent

```bash
python3 synapse/tools/a2a.py send --target <AGENT> [--priority <1-5>] [--response|--no-response] "<MESSAGE>"
```

**Parameters:**
- `--target`: Agent ID (exact, e.g., `synapse-claude-8100`) or agent type (fuzzy, e.g., `claude`)
- `--priority`: 1-4 normal, 5 = emergency interrupt (sends SIGINT first)
- `--response`: Wait for and receive response from target agent
- `--no-response`: Do not wait for response (fire and forget)
- `<MESSAGE>`: Content to send

**Response Control:**
- When `a2a.flow` is `roundtrip`: Always waits for response (flags ignored)
- When `a2a.flow` is `oneway`: Never waits for response (flags ignored)
- When `a2a.flow` is `auto` (default): **You decide** using `--response` or `--no-response`

### Deciding When to Use --response vs --no-response

**Use `--response` when:**
- You need the result to continue your work
- The task is a question that requires an answer
- You need to verify the task was completed correctly
- The result will be integrated into your response to the user

**Use `--no-response` when:**
- The task is a background/fire-and-forget operation
- You're delegating work that doesn't need immediate feedback
- The other agent will report results through other means
- You're sending multiple parallel tasks

**Examples:**
```bash
# Need the answer - use --response
python3 synapse/tools/a2a.py send --target gemini --response "What is the best practice for error handling in Python?"

# Background task - use --no-response
python3 synapse/tools/a2a.py send --target codex --no-response "Run the test suite and commit if all tests pass"

# Parallel delegation - use --no-response
python3 synapse/tools/a2a.py send --target gemini --no-response "Research React best practices"
python3 synapse/tools/a2a.py send --target codex --no-response "Refactor the auth module"

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

## @Agent Routing Pattern (User Input)

When users type in the agent terminal, they can use:

```
@<agent_name> <message>
```

This is for **user-initiated** communication. Response behavior is controlled by the `a2a.flow` setting.

**Note:** AI agents should use `synapse/tools/a2a.py send` instead, which allows explicit control over response behavior.

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

### With --response
1. Message is sent to target
2. Target processes the message
3. Target sends response back to sender
4. Sender receives and can use the response

### With --no-response
1. Message is sent to target
2. Target processes the message
3. No response is sent back
4. Sender continues immediately

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
    "response_expected": true
  }
}
```

## a2a.flow Settings

The `a2a.flow` setting in `.synapse/settings.json` controls response behavior:

| Setting | Behavior |
|---------|----------|
| `roundtrip` | Always wait for response (flags ignored) |
| `oneway` | Never wait for response (flags ignored) |
| `auto` | AI decides per-message using `--response`/`--no-response` flags |

```json
{
  "a2a": {
    "flow": "auto"
  }
}
```
