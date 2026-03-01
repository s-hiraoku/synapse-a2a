# Communication

## Overview

Synapse A2A provides three ways to send messages between agents:

| Method | Description | Best For |
|--------|-------------|----------|
| `synapse send` | Direct CLI command | Explicit agent-to-agent messaging |
| `synapse broadcast` | Send to all agents in same directory | Status checks, announcements |
| `@agent` pattern | Type in terminal | Quick inline mentions |

## Sending Messages

### Basic Send

```bash
synapse send <target> "<message>" \
  --wait          # Wait for reply
```

`--from` is auto-detected from `$SYNAPSE_AGENT_ID` (set at agent startup). You can omit it in most cases.

### Fire-and-Forget

```bash
synapse send codex "Refactor the auth module" --silent
```

### With Priority

```bash
synapse send gemini "Urgent: check this security issue" \
  --priority 4 --wait
```

### All Options

```bash
synapse send <target> "<message>" \
  --from <sender_id> \
  --priority 1-5 \
  --wait | --notify | --silent \
  --message-file <path> \
  --stdin \
  --attach <file> \
  --force
```

| Option | Description |
|--------|-------------|
| `--from <sender_id>` | Sender identification (optional — auto-detected from `$SYNAPSE_AGENT_ID`) |
| `--priority 1-5` | Priority level (default: 3) |
| `--wait` / `--notify` / `--silent` | Wait for reply, async notify (default), or fire-and-forget |
| `--message-file <path>` | Read message from file |
| `--stdin` | Read message from stdin |
| `--attach <file>` | Attach file(s) — repeatable |
| `--force` | Bypass working_dir mismatch check |

!!! info "Sender Auto-Detection"
    The `--from` flag is resolved in the following order: (1) explicit `--from` value, (2) `SYNAPSE_AGENT_ID` environment variable (auto-set at startup), (3) PID ancestry matching against the registry. In most environments, you can omit `--from` entirely.

### Choosing Response Mode

Three response modes are available:

| Mode | Behavior | Use Case |
|------|----------|----------|
| `--notify` | Return immediately, PTY notification on completion (**default**) | Most use cases |
| `--wait` | Block until receiver replies | Questions, results needed before proceeding |
| `--silent` | Fire-and-forget, no notification | Pure notifications, delegated tasks |

```bash
# Default (--notify) — returns immediately, notifies on completion
synapse send gemini "Analyze this codebase"

# Synchronous wait — blocks until reply
synapse send gemini "What is the best approach for auth?" --wait

# Fire-and-forget — no completion notification
synapse send codex "Run the full test suite and fix any failures" --silent
```

### Name vs ID

**Targets (who you're talking to)** — use custom names. Names are resolved first, making them the easiest way to address agents:

```bash
synapse send my-claude "Review this code" --wait
synapse send 釘崎野薔薇 "テストを書いて" --silent
```

**Sender (`--from`)** — always uses agent ID format (`synapse-<type>-<port>`). This is auto-detected, so you rarely need to specify it.

| Context | Use | Example |
|---------|-----|---------|
| Human → Agent | Custom name | `synapse send my-claude "..."` |
| Agent → Agent | Custom name or ID | `synapse send gemini "..."` |
| `--from` (sender) | Agent ID (auto-detected) | `synapse-claude-8100` |

Target resolution priority: (1) Custom name → (2) Agent ID → (3) Type-port → (4) Type only.
See [Agent Management](agent-management.md#target-resolution-priority) for details.

## Receiving Messages

When a message arrives at an agent, it appears in the PTY with a prefix that includes optional sender identification and reply expectations:

```
A2A: [From: NAME (SENDER_ID)] [REPLY EXPECTED] <message content>
```

- **From**: Identifies the sender's display name and unique agent ID. This helps you know who you are talking to.
- **REPLY EXPECTED**: Indicates that the sender is waiting for a response (blocking).

If sender information is not fully available, it falls back to:
- `A2A: [From: SENDER_ID] <message content>` (No name found in registry)
- `A2A: <message content>` (Backward-compatible format)

!!! info "Sender Identification"
    The name is retrieved from the agent registry based on the sender's PID or explicit `--from` ID. If an agent has a custom name (e.g., `釘崎野薔薇`), that name is shown for better context.

## Replying

### Basic Reply

```bash
synapse reply "Here are my findings..."
```

Reply automatically routes to the last sender.

### Reply to Specific Sender

When multiple senders are pending:

```bash
synapse reply --list-targets              # See who's waiting
synapse reply "Result" --to claude-8100   # Reply to specific sender
```

### Reply with Sender ID

For sandboxed environments (e.g., Codex):

```bash
synapse reply "Result" --from $SYNAPSE_AGENT_ID
```

## Priority Levels

| Level | Name | Use Case | Behavior |
|:-----:|------|----------|----------|
| 1-2 | Low | Background tasks | Normal delivery |
| **3** | **Normal** | **Default** | **Normal delivery** |
| 4 | Urgent | Follow-ups, status checks | Higher queue priority |
| 5 | Emergency | Critical issues | Sends SIGINT first, bypasses Readiness Gate |

!!! warning "Priority 5"
    Emergency priority (5) sends SIGINT to the agent before delivering the message. This interrupts whatever the agent is doing. Use only for genuine emergencies.

## Soft Interrupt

A convenience shorthand for priority-4 fire-and-forget messages:

```bash
synapse interrupt claude "Stop and review the current approach"

# Equivalent to:
synapse send claude "Stop and review" -p 4 --silent
```

## Broadcast

Send a message to all agents in the current working directory:

```bash
synapse broadcast "Status check — what's everyone working on?" --wait

# Fire-and-forget broadcast
synapse broadcast "FYI: deploying to staging" --silent
```

## Roundtrip Communication

When using `--wait`, the full roundtrip flow is:

```mermaid
sequenceDiagram
    participant A as Sender (Claude)
    participant S as Synapse
    participant B as Target (Gemini)

    A->>S: synapse send gemini "question" --wait
    S->>S: Create task context (no PTY send yet)
    S->>B: POST /tasks/send with [REPLY EXPECTED]
    B->>B: PTY shows "A2A: [From: Claude (synapse-claude-8100)] [REPLY EXPECTED] question"
    B->>S: synapse reply "answer"
    S->>S: Pop reply stack → route to sender
    S->>A: Display response
```

## Long Messages

Messages longer than ~100KB are automatically stored in temp files:

```bash
# Explicitly use file for large messages
synapse send claude --message-file /tmp/review.txt --silent

# Read from stdin
echo "long message content" | synapse send claude --stdin --silent

# '-' reads from stdin
synapse send claude --message-file - --silent
```

The recipient sees a file reference:

```
A2A: [LONG MESSAGE - FILE ATTACHED]
The full message content is stored at: /tmp/synapse-a2a/messages/<task_id>.txt
Please read this file to get the complete message.
```

!!! info "Threshold"
    The auto-file threshold is configurable via `SYNAPSE_SEND_MESSAGE_THRESHOLD` (default: ~100KB).

## File Attachments

Attach files to messages:

```bash
synapse send claude "Review this" --attach src/main.py --silent
synapse send claude "Review these" --attach src/a.py --attach src/b.py --silent
```

## Working Directory Check

Synapse warns when the sender's working directory doesn't match the target's:

```
WARNING: Working directory mismatch
  Sender: /path/to/project-a
  Target: /path/to/project-b
Use --force to bypass this check.
```

Use `--force` to bypass:

```bash
synapse send claude "message" --force
```

## @Agent Pattern

Type directly in the agent's terminal:

```
@gemini Review this code for security issues
```

The InputRouter detects the `@agent` pattern and routes it via A2A.

## Advanced Patterns

### Priority Interruption

Interrupt a busy agent without killing it:

```bash
# High priority message (does not interrupt execution)
synapse send gemini "Status?" --priority 4 --wait

# Emergency interrupt (sends SIGINT first)
synapse send gemini "STOP - critical vulnerability in current path" --priority 5
```

!!! info "Readiness Gate Bypass"
    Priority 5 messages bypass the Readiness Gate, meaning they are delivered even if the agent hasn't finished its initial setup instructions.

### Cross-Project Messaging

Communicate with agents working in different directories using the `--force` flag:

```bash
# Warning: Target agent "worker" is in /path/to/project-b (Sender: /path/to/project-a)
synapse send worker "Can you check the API compatibility?" --force
```

### Response Polling (Agent-to-Agent)

When an agent needs to check if a delegated task is done without blocking:

```bash
# Initial delegation
synapse send Worker "Fix bug" --silent

# Later, check status
synapse send Worker "Are you finished?" --wait
```

## A2A Flow Configuration

Configure default communication behavior in settings:

| Mode | Behavior |
|------|----------|
| `roundtrip` | Always wait for reply (like `--wait`) |
| `oneway` | Never wait (like `--silent`) |
| `auto` | Decide based on context (default) |

Configure in `.synapse/settings.json`:

```json
{
  "a2a_flow": "auto"
}
```
