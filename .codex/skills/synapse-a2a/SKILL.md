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
| Send message | `@<agent> <message>` |
| Check file locks | `synapse file-safety locks` |
| View history | `synapse history list` |
| Initialize settings | `synapse init` |

## @Agent Routing (Recommended)

**Always use the `@agent` pattern for inter-agent communication.** This works reliably within the Synapse environment and handles sandbox restrictions automatically.

```text
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
| 1-2 | Low | Background tasks |
| 3 | Normal | Standard tasks |
| 4 | Urgent | Follow-ups, status checks |
| 5 | Interrupt | Emergency (sends SIGINT first) |

For priority control, use the `--priority` flag with `@agent`:

```text
# Priority is specified by Synapse automatically based on context
# For emergency interrupt, contact the user to use external tools
```

> **Note**: Direct use of `python -m synapse.tools.a2a` is for external tools only. Within Synapse, always use `@agent` pattern.

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
