# Synapse A2A Protocol Instructions

You are participating in a multi-agent environment connected via the **Synapse A2A Protocol**.
Other agents (like Gemini, Claude, etc.) may be running in parallel.

## 1. How to Forward Messages (@Agent)

**IMPORTANT**: When you receive a message starting with `@AgentName` (e.g., `@Gemini`, `@Claude`):
- **FORWARD** the message to that agent immediately
- **DO NOT** process or execute the task yourself
- Just deliver the message using the A2A tool

### Syntax

```bash
python3 synapse/tools/a2a.py send --target [AgentType] --priority [1-5] "[Message]"
```

- **Target**: The name of the agent (e.g., `gemini`, `claude`, or `codex-8120` for specific instance).
- **Priority**:
  - `1`: Normal message (Info/Chat).
  - `5`: **EMERGENCY INTERRUPT**. Use this if you need to STOP them immediately (e.g., "Stop!", "Wait!").

### Target Resolution

| Pattern | Example | Description |
|---------|---------|-------------|
| `@type` | `@codex` | Works if only ONE agent of that type exists |
| `@type-port` | `@codex-8120` | Specific instance (required if multiple exist) |
| `@agent_id` | `@synapse-codex-8120` | Full agent ID |

If multiple agents of the same type exist, `@type` will fail with options shown.

### When to Process vs Forward

- Message starts with `@OtherAgent`: **FORWARD** to that agent (do NOT process yourself)
- Message addressed to you (or no @mention): **PROCESS** it yourself

### Example

User says: `@Gemini 天気を調べて`
You run (do NOT check weather yourself):

```bash
python3 synapse/tools/a2a.py send --target gemini --priority 1 "天気を調べて"
```

## 1.1 Sender Identification

When you receive a message from another agent, it appears with sender info:

```
[A2A:abc12345:synapse-claude-8100] Hello from Claude!
```

Format: `[A2A:<task_id>:<sender_id>] <message>`

To get full sender details, query the Task API:
```bash
curl -s http://localhost:YOUR_PORT/tasks/<task_id> | jq '.metadata.sender'
```

## 2. How to Check Status (Watchdog)

If asked to monitor another agent:

1. List agents to find them: `python3 synapse/tools/a2a.py list`
2. Check their status via curl (endpoint is in the list JSON).

```bash
curl -s [ENDPOINT]/status
```

If `status` is `IDLE` but the task isn't done, use `priority 5` (or 1) to nudge them.
