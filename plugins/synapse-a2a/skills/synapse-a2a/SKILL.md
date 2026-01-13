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
| Watch agents | `synapse list --watch` |
| Send message | `synapse send <agent> "<message>"` |
| Check file locks | `synapse file-safety locks` |
| View history | `synapse history list` |
| Initialize settings | `synapse init` |

## Sending Messages (Recommended)

**Use `synapse send` command for inter-agent communication.** This works reliably from any environment including sandboxed agents.

```bash
synapse send gemini "Please review this code"
synapse send claude "What is the status?" --from codex
synapse send codex-8120 "Fix this bug" --priority 3 --from gemini
```

**Important:** Always use `--from` to identify yourself so the recipient knows who sent the message and can reply.

**Target Resolution:**
1. Type only: `claude`, `gemini`, `codex` (if single instance)
2. Type-port: `claude-8100`, `codex-8120`
3. Exact ID: `synapse-claude-8100`

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

Always verify target agent is READY before sending tasks.

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
