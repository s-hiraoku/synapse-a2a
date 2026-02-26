# Skills

## Overview

The Skills system lets you discover, deploy, and manage specialized capabilities across agents. Skills are Markdown-based definitions that configure agent behavior for specific tasks.

## Skills TUI

Launch the interactive skills manager:

```bash
synapse skills
```

## Listing Skills

```bash
synapse skills list                    # All skills across scopes
synapse skills list --scope synapse    # Central store only
synapse skills list --scope plugin     # Plugin skills only
```

Deploy indicators show which agent directories have the skill:

```
[C✓ A✓ G·] code-review    # Deployed to Claude and Agents, not Gemini
[C· A· G·] new-skill      # Not yet deployed
```

## Skill Details

```bash
synapse skills show code-review
```

## Skill Scopes

| Scope | Location | Purpose |
|-------|----------|---------|
| **Synapse** | `~/.synapse/skills/` | Central deploy point |
| **User** | `~/.claude/skills/`, `~/.agents/skills/` | Per-user skills |
| **Project** | `./.claude/skills/`, `./.agents/skills/` | Project-local skills |
| **Plugin** | `./plugins/*/skills/` | Plugin-bundled (read-only) |

## Deploying Skills

Deploy a skill from the central store to agent directories:

```bash
synapse skills deploy code-review --agent claude,codex --scope user
```

This copies the skill to:

- `~/.claude/skills/code-review/` (for Claude)
- `~/.agents/skills/code-review/` (for Codex)

## Importing Skills

Import a skill to the central store (`~/.synapse/skills/`):

```bash
synapse skills import code-review
```

## Installing from Repository

```bash
synapse skills add <repo-url>
```

## Creating Skills

```bash
synapse skills create
```

Guides you through creating a new skill with the proper structure:

```
my-skill/
├── SKILL.md          # Skill definition (frontmatter + instructions)
└── references/       # Optional reference documents
    └── docs.md
```

## Moving Skills

```bash
synapse skills move my-skill --to user     # Move to user scope
synapse skills move my-skill --to project  # Move to project scope
```

## Deleting Skills

```bash
synapse skills delete old-skill
synapse skills delete old-skill --force    # Skip confirmation
```

## Skill Sets

Skill sets are predefined groups of skills activated together.

### List Skill Sets

```bash
synapse skills set list
```

### Show Set Details

```bash
synapse skills set show architect
```

### Activate at Startup

```bash
synapse claude --skill-set architect
```

The skill set details are included in the agent's initial instructions.

## Source of Truth

!!! important
    `plugins/synapse-a2a/skills/synapse-a2a/` is the source of truth for skills. Always edit skills in `plugins/` and sync to agent directories with `sync-plugin-skills`. Never edit agent directories directly.
