# Proactive Mode

## Overview

Proactive Mode makes agents **mandatorily** use ALL Synapse coordination features for every task, regardless of size. When enabled, agents always create task board entries, search shared memory, lock files, post canvas artifacts, and delegate work -- no exceptions.

Without Proactive Mode, agents use a collaboration decision framework that recommends feature usage based on task complexity. Proactive Mode removes this discretion and enforces full feature usage on every task.

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

When Proactive Mode is enabled, agents follow a mandatory checklist for **every** task:

### Before Starting

| Action | Command |
|--------|---------|
| Create a task board entry | `synapse tasks create "Subject" -d "description"` |
| Search shared memory | `synapse memory search <keywords>` |
| Check available agents | `synapse list` |

### During Execution

| Action | Command |
|--------|---------|
| Lock files before editing | `synapse file-safety lock <file>` |
| Post progress to canvas | `synapse canvas post` |
| Save discoveries to memory | `synapse memory save <key> <content>` |
| Delegate independent work | `synapse spawn` / `synapse send --silent` |
| Unlock files when done | `synapse file-safety unlock <file>` |

### After Completion

| Action | Command |
|--------|---------|
| Mark task complete | `synapse tasks complete <task_id>` |
| Broadcast completion | `synapse broadcast "Task done"` |
| Post summary to canvas | `synapse canvas post` |

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
| Critical project requiring audit trail | Enable for full task board + memory tracking |

## Testing

```bash
pytest tests/test_proactive_mode.py -v
```
