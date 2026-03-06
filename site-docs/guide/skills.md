# Skills

## Overview

The Skills system lets you discover, deploy, and manage specialized capabilities across agents. Skills are Markdown-based definitions that configure agent behavior for specific tasks.

## Install Core Skills

The `synapse-a2a` skill package is the foundation for all agent communication. Install it before using multi-agent features.

### Quick Install

```bash
# 1. Initialize Synapse (creates .synapse/ directory)
synapse init

# 2. Install skills via skills.sh
npx skills add s-hiraoku/synapse-a2a
```

!!! info "What is skills.sh?"
    [skills.sh](https://skills.sh/) is a platform for discovering and installing agent skills. `npx skills add` downloads skill definitions into your project's `.claude/skills/` and `.agents/skills/` directories.

### What Gets Installed

| Skill | Purpose | Included In |
|-------|---------|-------------|
| **synapse-a2a** | Core A2A communication — message sending, file safety, task board, settings management | All skill sets |
| **synapse-manager** | 7-step multi-agent orchestration: Plan, Delegate, Monitor, Approve, Verify, Feedback, Review | `manager` set |
| **synapse-reinst** | Re-inject initial instructions after `/clear` or context reset — restores agent identity and A2A config | `manager` set |

### Verification

```bash
synapse skills list --scope project
```

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

### Deploy Indicators (TUI only)

When using the interactive manager (`synapse skills`), deploy indicators show which agent directories have the skill:

```
[C✓ A✓] code-review    # Deployed to Claude and Agents
[C· A·] new-skill      # Not yet deployed
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
- `~/.agents/skills/code-review/` (for Gemini, Codex, OpenCode, and Copilot)

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
synapse skills create [name]
```

Creates a new skill template in the central store (`~/.synapse/skills/`). If no name is provided, you will be prompted for one.

The command creates a standard skill structure:

```
my-skill/
├── SKILL.md          # Skill definition (frontmatter + instructions)
├── references/       # Optional reference documents
│   └── docs.md
└── scripts/          # Optional automation scripts
    └── helper.sh
```

!!! info "Progressive Disclosure Pattern"
    Core skills use a **Progressive Disclosure** pattern: `SKILL.md` is kept concise (under ~200 lines) with essential instructions only. Detailed reference material, examples, and command catalogs live in `references/` subdirectories. Automation scripts live in `scripts/`. This keeps the main skill file focused while allowing agents to load deeper context on demand.

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

## Built-in Skills

Install via [`npx skills add s-hiraoku/synapse-a2a`](#install-core-skills). Four core skills provide multi-agent capabilities:

| Skill | Description |
|-------|-------------|
| **synapse-a2a** | Core A2A communication — concise SKILL.md with `references/` for commands, API, messaging, spawning, collaboration, features, examples, and file safety |
| **synapse-manager** | 7-step multi-agent orchestration (Plan, Delegate, Monitor, Approve, Verify, Feedback, Review) with `references/` (worker guide, feature tables, command quick-ref) and `scripts/` (team status check, regression triage, readiness wait) |
| **synapse-reinst** | Re-inject initial instructions after `/clear` — restores agent identity using preserved `SYNAPSE_*` env vars |
| **doc-organizer** | Documentation audit, restructure, and consolidation — inventory docs, detect staleness, deduplicate content, normalize terminology, and improve navigation |

!!! tip "synapse-manager"
    The `synapse-manager` skill teaches an agent a structured 7-step workflow: **Plan & Setup** (assess agents and fill gaps), **Delegate** (task board + detailed instructions), **Monitor** (status and artifacts), **Approve** (gate execution with plan review), **Verify** (tests with regression triage), **Feedback** (actionable fix instructions), and **Review** (cross-review and cleanup). It also includes a **Worker Agent Guide** that teaches worker agents autonomous task execution -- receiving tasks, reporting progress, delegating subtasks, and cleaning up spawned agents. Activate it via the `manager` skill set or deploy it directly.

    **When to use**: Coordinating 2+ agents, monitoring delegated work, verifying outputs, sending feedback, orchestrating cross-review, implementing multi-phase plans (3+ phases or 10+ file changes), executing plans with multiple deliverables, or planning agent assignment for multi-file changes across a codebase.

!!! tip "synapse-reinst"
    When an agent runs `/clear` or loses context, it forgets its Synapse instructions.
    The `synapse-reinst` skill rebuilds and re-injects the complete instruction set using
    persistent environment variables (`SYNAPSE_AGENT_ID`, `SYNAPSE_PORT`, etc.).
    Included in the `manager` skill set.

!!! tip "doc-organizer"
    The `doc-organizer` skill guides an agent through a 4-step workflow: **Audit** (inventory all docs and classify topics), **Plan** (propose restructuring with moves, merges, deletions), **Execute** (apply changes), and **Verify** (cross-check links, terminology, completeness). Activate it via the `documentation` skill set or deploy it directly.

## Skill Sets

Skill sets are predefined groups of skills activated together.

### Available Skill Sets

| Set | Description | Included Skills |
|-----|-------------|-----------------|
| **architect** | System architecture and design — design docs, API contracts, code review | synapse-a2a, system-design, api-design, code-review, project-docs |
| **developer** | Implementation and quality — test-first development, refactoring, code simplification | synapse-a2a, test-first, refactoring, code-simplifier, agent-memory |
| **reviewer** | Code review and security — structured reviews, security audits, code simplification | synapse-a2a, code-review, security-audit, code-simplifier |
| **frontend** | Frontend development — React/Next.js performance, component composition, design systems, accessibility | synapse-a2a, react-performance, frontend-design, react-composition, web-accessibility |
| **manager** | Multi-agent management — task delegation, progress monitoring, quality verification, cross-review orchestration, re-instruction | synapse-a2a, synapse-manager, task-planner, agent-memory, code-review, synapse-reinst |
| **documentation** | Documentation expert — audit, restructure, synchronize, and maintain project documentation | synapse-a2a, project-docs, doc-organizer, api-design, agent-memory |

### List Skill Sets

```bash
synapse skills set list
```

### Show Set Details

```bash
synapse skills set show manager
```

### Activate at Startup

```bash
synapse claude --skill-set manager
```

The skill set details are included in the agent's initial instructions.

### Apply to a Running Agent

You can apply a skill set to an agent that is already running. This copies the skill files to the agent's skill directory, updates the registry, and sends the skill set information via A2A:

```bash
synapse skills apply my-claude manager
```

Use `--dry-run` to preview what would happen without making any changes:

```bash
synapse skills apply gemini-8110 developer --dry-run
```

**What `apply` does:**

1. Resolves the target agent (by name, ID, type-port, or type)
2. Copies all skills in the set to the agent's skill directory
3. Updates the agent's registry entry with the new skill set
4. Sends the skill set details to the agent via A2A message

!!! tip "Dynamic Reconfiguration"
    Use `synapse skills apply` to change an agent's skill set without restarting it. For example, switch a general-purpose agent to a `reviewer` role mid-session:
    ```bash
    synapse skills apply my-claude reviewer
    ```

### Example: Manager Skill Set

Start a manager agent with the `manager` skill set to orchestrate other agents:

```bash
synapse claude --delegate-mode --name manager --skill-set manager
```

This equips the agent with multi-agent management capabilities (from `synapse-manager`), task planning, shared memory access, code review, and re-instruction skills.

## Source of Truth

!!! important
    `plugins/synapse-a2a/skills/` is the source of truth for published skills (`synapse-a2a`, `synapse-manager`, etc.). Always edit skills in `plugins/` and sync to agent directories with `sync-plugin-skills`. Never edit agent directories directly.

!!! note "Dev-only skills"
    Some skills like `synapse-docs` live only in `.agents/skills/` and are not published via `plugins/`. These are development-only utilities not intended for end-user distribution.
