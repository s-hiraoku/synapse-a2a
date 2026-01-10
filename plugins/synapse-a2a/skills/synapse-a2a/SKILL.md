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
| Send message | `@<agent> <message>` or `python3 synapse/tools/a2a.py send --target <agent> "<message>"` |
| Check file locks | `synapse file-safety locks` |
| View history | `synapse history list` |
| Initialize settings | `synapse init` |

## @Agent Routing

Send messages to other agents using the `@agent` pattern:

```
@codex Please refactor this file
@gemini Research this API
@claude-8100 Review this code
```

**Target Resolution:**
1. Exact ID: `@synapse-claude-8100`
2. Type-port: `@claude-8100`
3. Type only: `@claude` (if single instance)

## Priority Levels

| Priority | Description | Use Case |
|----------|-------------|----------|
| 1 | Normal | Default for standard tasks |
| 2-3 | Elevated | Higher urgency |
| 4 | Urgent | Follow-ups, status checks |
| 5 | Interrupt | Emergency (sends SIGINT first) |

```bash
# Emergency interrupt
python3 synapse/tools/a2a.py send --target codex --priority 5 "STOP"
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
