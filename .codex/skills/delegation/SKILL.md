---
name: delegation
description: This skill explains task delegation between agents in Synapse A2A. Delegation is configured via `.synapse/settings.json` and delegation rules are defined in `.synapse/delegate.md`. Tasks are delegated using the `@agent` pattern (e.g., `@codex`, `@gemini`). Supports orchestrator mode (Claude coordinates) and passthrough mode (direct forwarding).
---

# Delegation Skill

Configure automatic task delegation to other agents based on natural language rules.

## Configuration

> **Note**: The `/delegate` CLI subcommand has been removed (see CHANGELOG v0.2.4).
> Delegation is now configured via settings files.

### Configuration Files

| File | Purpose |
|------|---------|
| `.synapse/settings.json` | Enable/disable delegation and set A2A flow mode |
| `.synapse/delegate.md` | Define delegation rules and agent responsibilities |

### Settings Structure

In `.synapse/settings.json`:

```json
{
  "a2a": {
    "flow": "auto"  // "roundtrip" | "oneway" | "auto"
  },
  "delegation": {
    "enabled": true  // Enable automatic task delegation
  }
}
```

## Delegating Tasks

Use the `@agent` pattern to send tasks to other agents:

```text
@codex Please refactor this function
@gemini Research the latest API changes
@claude Review this design document
```

For programmatic delegation (from AI agents):

```bash
python -m synapse.tools.a2a send --target codex "Refactor this function"
python -m synapse.tools.a2a send --target gemini --priority 4 "Status update?"
```

## Modes

### Orchestrator Mode (Recommended)

Claude analyzes tasks, delegates to appropriate agent, waits for response, integrates results.

```text
User → Claude (analyze) → @codex/@gemini → Claude (integrate) → User
```

### Passthrough Mode

Direct forwarding without processing.

```text
User → Claude (route) → @codex/@gemini → User
```

### Manual Mode (Default)

No automatic delegation. User explicitly uses @agent patterns.

## Pre-Delegation Checklist

Before delegating any task:

1. **Verify agent is READY**: `synapse list`
2. **Check file locks**: `synapse file-safety locks` (for file edits)
3. **Verify branch**: `git branch --show-current` (for coding tasks)

## Priority Levels

| Priority | Use Case |
|----------|----------|
| 1-2 | Low priority, background tasks |
| 3 | Normal tasks (default) |
| 4 | Urgent follow-ups |
| 5 | Critical/emergency tasks |

## Available Agents

| Agent | Strengths | Port Range |
|-------|-----------|------------|
| codex | Coding, file editing, refactoring | 8120-8129 |
| gemini | Research, web search, documentation | 8110-8119 |
| claude | Code review, analysis, planning | 8100-8109 |

## References

For detailed documentation, read:

- `references/modes.md` - Delegation modes and workflows
- `references/file-safety.md` - File Safety integration
- `references/examples.md` - Example sessions and configurations
