---
name: delegation
description: This skill configures automatic task delegation between agents in Synapse A2A. Use /delegate to set up rules for routing coding tasks to Codex, research to Gemini, etc. Supports orchestrator mode (Claude coordinates) and passthrough mode (direct forwarding). Includes agent status verification, priority levels, error handling, and File Safety integration.
---

# Delegation Skill

Configure automatic task delegation to other agents based on natural language rules.

## Configuration

> **Note**: The `/delegate` CLI subcommand has been removed.
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
synapse send codex "Refactor this function" --from claude
synapse send gemini "Status update?" --priority 4 --from claude
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
