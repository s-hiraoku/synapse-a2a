# Proactive Mode

## Overview

Proactive Mode provides agents with a **task-size x feature matrix** that guides Synapse feature usage based on task scope and context. When enabled, agents receive structured guidance on when to use shared memory, file safety, canvas, delegation, and broadcasting -- scaled to the task at hand rather than applied uniformly.

Without Proactive Mode, agents have no specific guidance on when to use coordination features. Proactive Mode adds this decision framework so agents can make informed choices about which features to employ for each task.

## Activation

Proactive Mode is disabled by default. Enable it via environment variable or settings:

```bash
# Via environment variable
SYNAPSE_PROACTIVE_MODE_ENABLED=true synapse claude

# Or export for the session
export SYNAPSE_PROACTIVE_MODE_ENABLED=true
synapse claude
```

Or configure it in `.synapse/settings.json`:

```json
{
  "env": {
    "SYNAPSE_PROACTIVE_MODE_ENABLED": "true"
  }
}
```

## What Changes

When Proactive Mode is enabled, agents receive a **task-size x feature matrix** that maps each Synapse feature to task size categories. Instead of a mandatory checklist, agents use judgment based on task scope:

### Task Size Matrix

| Feature | Small (< 5 min, 1-2 files) | Medium (5-30 min, 3-5 files) | Large (30+ min, 5+ files) |
|---------|---------------------------|------------------------------|--------------------------|
| Memory search | Optional | Recommended | Required |
| File safety | Only if multi-agent + shared files | If multi-agent + shared files | Required in multi-agent |
| Canvas | Skip | Only for complex output | Plans, results, briefings |
| Delegation | Skip | If subtasks can parallelize | Actively delegate |
| Broadcast | Skip (unless blocking others) | On completion if others waiting | On milestones |

### Per-Feature Skip Conditions

Each feature includes explicit skip conditions to prevent unnecessary coordination overhead:

- **File Safety**: Skip for single-agent tasks, new file creation, read-only operations, or tests
- **Shared Memory**: Skip for task-specific notes only relevant to you; use for discoveries that benefit other agents
- **Canvas**: Skip for simple completion reports, single-file changes, or brief confirmations; use only when visual structure adds value
- **Delegation**: Skip when overhead exceeds the task or no suitable agent is available
- **Broadcast**: Skip for trivial completions or work that only concerns you

## How It Works

Proactive Mode follows the same pattern as [Learning Mode](../guide/settings.md#environment-variables): an environment variable activates a supplementary instruction file (`.synapse/proactive.md`) that is appended to the agent's initial instructions at startup.

The instruction file is deployed by `synapse init` as part of the standard template set. If you have an existing project, re-run `synapse init` to pick up the template:

```bash
synapse init --scope project
```

!!! info "Non-invasive"
    Proactive Mode only adds instructions -- it does not modify agent detection, profiles, or any runtime behavior. It layers on top of the base instructions in `.synapse/default.md`.

## Combining with Other Modes

Proactive Mode is independent of Learning Mode. Both can be enabled simultaneously:

```json
{
  "env": {
    "SYNAPSE_PROACTIVE_MODE_ENABLED": "true",
    "SYNAPSE_LEARNING_MODE_ENABLED": "true"
  }
}
```

When both are active, both instruction files are appended to the agent's startup instructions.

## When to Use

| Scenario | Recommendation |
|----------|---------------|
| Solo development, small fixes | Leave disabled (default) |
| Multi-agent team on a shared codebase | Enable for coordination discipline |
| Onboarding new team members to Synapse | Enable to demonstrate all features |
| Critical project requiring audit trail | Enable for full memory tracking |

## Testing

```bash
pytest tests/test_proactive_mode.py -v
```
