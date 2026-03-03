# Interactive Setup

When you start an agent for the first time, Synapse offers an interactive setup flow for naming and configuring the agent.

## First Launch

```bash
synapse claude
```

You'll see prompts for:

1. **Agent Name** — A custom name for easy identification (e.g., `my-claude`, `reviewer`)
2. **Agent Role** — What the agent specializes in (e.g., `code reviewer`, `test writer`)
3. **Skill Set** — A predefined group of skills to activate (e.g., `architect`, `developer`, `manager`, `documentation`)

All fields are optional. Press ++enter++ to skip.

## Skip Interactive Setup

Use `--no-setup` to skip prompts entirely:

```bash
synapse claude --no-setup
```

Or provide values directly via CLI flags:

```bash
synapse claude --name my-claude --role "code reviewer"
```

### Role from File

Use the `@` prefix to load role content from a file:

```bash
synapse claude --name reviewer --role "@./roles/reviewer.md"
synapse gemini --role "@~/my-roles/analyst.md"
```

!!! tip "Recommended Role File Directories"
    Store project-shared roles in `./roles/` (committed to Git) and personal roles in `~/my-roles/` or `~/.synapse/roles/`. File-based roles are useful for detailed role definitions that are too long for command-line arguments. The file content is copied to the registry, so the original file can be modified later without affecting running agents.

### Using Saved Agent Definitions

If you have [saved agent definitions](../guide/agent-teams.md#saved-agent-definitions), use `--agent` / `-A` to load name, role, and skill set from a reusable template:

```bash
synapse claude --agent calm-lead        # By saved agent ID
synapse claude -A Claud                       # By display name
synapse claude --agent calm-lead --role "temporary override"  # CLI overrides
```

## Agent Names and Roles

### Setting Names

Names make agents easy to identify and target:

```bash
# At startup
synapse claude --name reviewer --role "security code review"

# After startup
synapse rename claude --name reviewer --role "security code review"
```

### Using Names as Targets

Once named, use the name instead of the agent type:

```bash
synapse send reviewer "Check this file for SQL injection" --wait
```

### Clearing Names

```bash
synapse rename reviewer --clear
```

## Skill Sets

Skill sets are predefined groups of skills that configure an agent's capabilities at startup.

### View Available Skill Sets

```bash
synapse skills set list
```

### Show Skill Set Details

```bash
synapse skills set show architect
```

Example output:

```
Skill Set: architect
Description: System architecture and design — design docs, API contracts, code review
Skills:
  - synapse-a2a
  - system-design
  - api-design
  - code-review
  - project-docs
```

### Start with a Skill Set

```bash
synapse claude --skill-set architect
```

The skill set details are included in the agent's initial instructions, informing it of its specialized capabilities.

## Resume Mode

If you need to reconnect to a session (e.g., after a context reset), use resume mode to skip initial instructions:

```bash
synapse claude --resume
# or
synapse claude --continue
```

!!! info
    Resume mode skips the initial instruction injection. Use it when an agent already has its context from a previous session.

## Configuration Files

For persistent configuration, use `synapse init` to create settings files:

```bash
# Project-scoped settings (creates ./.synapse/settings.json)
synapse init --scope project

# User-scoped settings (creates ~/.synapse/settings.json, applies to all projects)
synapse init --scope user
```

See [Settings & Configuration](../guide/settings.md) for details.

## Next Steps

- [Agent Management](../guide/agent-management.md) — Start, stop, list, and control agents
- [Communication](../guide/communication.md) — Send messages between agents
- [Settings & Configuration](../guide/settings.md) — Customize all aspects of Synapse
