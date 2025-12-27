# Synapse A2A Protocol Instructions

You are participating in a multi-agent environment connected via the **Synapse A2A Protocol**.
Other agents (like Gemini, Claude, etc.) may be running in parallel.

## 1. How to Intervene (@Agent)

When you see a user instruction starting with `@AgentName` (e.g., `@Gemini`, `@Claude`), or if you decide you must intervene in another agent's process:

**DO NOT** just output text. You must **EXECUTE** the A2A tool to send the message to them.

### Syntax

```bash
python3 synapse/tools/a2a.py send --target [AgentType] --priority [1-5] "[Message]"
```

- **Target**: The name of the agent (e.g., `gemini`, `claude`).
- **Priority**:
  - `1`: Normal message (Info/Chat).
  - `5`: **EMERGENCY INTERRUPT**. Use this if you need to STOP them immediately (e.g., "Stop!", "Wait!").

### Example

User says: `@Gemini 処理を止めて`
You run:

```bash
python3 synapse/tools/a2a.py send --target gemini --priority 5 "処理を止めて"
```

## 2. How to Check Status (Watchdog)

If asked to monitor another agent:

1. List agents to find them: `python3 synapse/tools/a2a.py list`
2. Check their status via curl (endpoint is in the list JSON).

```bash
curl -s [ENDPOINT]/status
```

If `status` is `IDLE` but the task isn't done, use `priority 5` (or 1) to nudge them.
