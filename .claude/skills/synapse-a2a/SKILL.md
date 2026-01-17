---
name: synapse-a2a
description: This skill provides comprehensive guidance for inter-agent communication using the Synapse A2A framework. Use this skill when sending messages to other agents, routing @agent patterns, understanding priority levels, handling A2A protocol operations, managing task history, configuring settings, or using File Safety features for multi-agent coordination. Automatically triggered when agent communication, A2A protocol tasks, history operations, or file safety operations are detected.
---

# Synapse A2A Communication

Inter-agent communication framework via Google A2A Protocol.

## Quick Reference

| Task | Command |
|------|---------|
| List agents | `synapse list` |
| Watch agents | `synapse list --watch` (shows TRANSPORT column) |
| Send message | `synapse send <target> "<message>" --from <sender>` |
| Wait for reply | `synapse send <target> "<message>" --response --from <sender>` |
| Reply to request | `synapse send <target> "<response>" --reply-to <task_id> --from <sender>` |
| Emergency stop | `synapse send <target> "STOP" --priority 5 --from <sender>` |
| Stop agent | `synapse stop <profile\|id>` |
| Check file locks | `synapse file-safety locks` |
| View history | `synapse history list` |
| Initialize settings | `synapse init` |
| Edit settings (TUI) | `synapse config` |
| Show instructions | `synapse instructions show <agent>` |
| Send instructions | `synapse instructions send <agent>` |

**Tip:** Run `synapse list` before sending to verify the target agent is READY.

## Sending Messages (Recommended)

**Use `synapse send` command for inter-agent communication.** This works reliably from any environment including sandboxed agents.

```bash
synapse send gemini "Please review this code" --from claude
synapse send claude "What is the status?" --from codex
synapse send codex-8120 "Fix this bug" --priority 3 --from gemini
```

**Important:** Always use `--from` to identify yourself so the recipient knows who sent the message and can reply.

**Target Resolution (Matching Priority):**
1. Exact ID: `synapse-claude-8100` (direct match)
2. Type-port: `claude-8100`, `codex-8120` (shorthand)
3. Type only: `claude`, `gemini`, `codex` (only if single instance)

**Note:** When multiple agents of the same type are running, type-only targets (e.g., `claude`) will fail with an ambiguity error. Use type-port shorthand (e.g., `claude-8100`) instead.

### Roundtrip Communication (--response / --reply-to)

For request-response patterns:

```bash
# Sender: Wait for response (blocks until reply received)
synapse send gemini "Analyze this data" --response --from claude

# Receiver: Reply to the request (use task_id from [A2A:task_id:sender])
synapse send claude "Analysis result: ..." --reply-to <task_id> --from gemini
```

The `--response` flag makes the sender wait. The receiver MUST use `--reply-to` with the task_id to link the response.

## Priority Levels

| Priority | Description | Use Case |
|----------|-------------|----------|
| 1-2 | Low | Background tasks |
| 3 | Normal | Standard tasks |
| 4 | Urgent | Follow-ups, status checks |
| 5 | Interrupt | Emergency (sends SIGINT first) |

```bash
# Normal priority (default)
synapse send gemini "Analyze this"

# Higher priority
synapse send claude "Urgent review needed" --priority 4

# Emergency interrupt
synapse send codex "STOP" --priority 5
```

## Agent Status

| Status | Meaning |
|--------|---------|
| READY | Idle, waiting for input |
| PROCESSING | Busy handling a task |

**Verify before sending:** Run `synapse list` and confirm the target agent's Status column shows `READY`:

```bash
synapse list
# Output:
# NAME                  TYPE    STATUS      PORT
# synapse-claude-8100   claude  READY       8100
# synapse-codex-8120    codex   PROCESSING  8120  # <- busy, wait or use --priority 5
```

If the agent is `PROCESSING`, either wait for it to become `READY` or use `--priority 5` for emergency interrupt.

## Key Features

- **Agent Communication**: @agent pattern, priority control, response handling
- **Task History**: Search, export, statistics (`synapse history`)
- **File Safety**: Lock files to prevent conflicts (`synapse file-safety`)
- **Settings**: Configure via `settings.json` (`synapse init`)

## References

For detailed documentation, read:

- `references/commands.md` - Full CLI command reference
- `references/file-safety.md` - File Safety detailed guide
- `references/api.md` - A2A endpoints and message format
- `references/examples.md` - Multi-agent workflow examples
