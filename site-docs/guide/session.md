# Session Save/Restore

## Overview

Synapse sessions let you save your running team configuration as a named snapshot and restore it later. A session captures agent settings such as profile, name, role, skill set, and worktree options so you can quickly resume recurring workflows.

Storage: `.synapse/sessions/` (project-local) or `~/.synapse/sessions/` (user-global)

## Save a Session

```bash
synapse session save review-team
```

This saves all agents in the current working directory to:

`.synapse/sessions/review-team.json` (project scope, default)

You can choose a different scope:

```bash
synapse session save review-team --user        # ~/.synapse/sessions/
synapse session save review-team --workdir /path/to/project
```

!!! note "Session naming rules"
    Session names must start with an alphanumeric character and contain only alphanumeric characters, dots, hyphens, or underscores (e.g., `review-team`, `sprint_3.1`).

## List Sessions

```bash
synapse session list                           # Project scope (current repo, default)
synapse session list --project                 # Project scope only
synapse session list --user                    # User scope only
synapse session list --workdir /path/to/project  # Project scope rooted at /path/to/project
```

In interactive terminals, sessions are displayed in a Rich TUI table with name, agent count, scope, working directory, and creation date.

## Show Session Details

```bash
synapse session show review-team
```

Displays the full session record including each agent's profile, name, role, skill set, and worktree flag. Use this to inspect the saved snapshot before restore.

## Restore a Session

```bash
synapse session restore review-team
```

Restore spawns each agent from the saved session in a new terminal pane (same behavior as `synapse spawn`).

Typical workflow:

```bash
# Save your current team
synapse session save review-team

# Later, restore the same configuration
synapse session restore review-team
```

## Delete a Session

```bash
synapse session delete review-team             # Prompts for confirmation
synapse session delete review-team --force     # Skip confirmation
```

## Scope Options

Session commands support three mutually exclusive scope flags:

| Flag | Description |
|------|-------------|
| `--project` | Project scope (default): `.synapse/sessions/` in the current repository |
| `--user` | User scope: `~/.synapse/sessions/` for cross-project reuse |
| `--workdir <path>` | Use project scope rooted at the given working directory (`<path>/.synapse/sessions/`) |

Without scope flags, session commands use project scope in the current repository.

!!! tip "Sharing sessions"
    Project-scope session files live in `.synapse/sessions/` and can be committed to version control. This lets team members share reusable team presets.

## Worktree Support

You can restore directly into isolated worktrees:

```bash
synapse session restore review-team --worktree
synapse session restore review-team -w           # Short form
synapse session restore review-team --worktree my-feature  # Named worktree
```

The `--worktree` flag overrides the saved worktree setting for all agents. This is useful when restarting multi-agent teams that should each work in their own git worktree to avoid file conflicts.

## Tool Args Passthrough

Pass CLI-specific arguments through `--` during restore:

```bash
synapse session restore review-team -- --dangerously-skip-permissions
```

Tool args are forwarded to every spawned agent, keeping session restore compatible with runtime options required by each underlying agent CLI.

## Storage Format

Sessions are stored as JSON files:

- Project scope: `.synapse/sessions/<name>.json`
- User scope: `~/.synapse/sessions/<name>.json`

Each file contains the session name, agent list (profile, name, role, skill set, worktree flag), working directory, creation timestamp, and scope.

## Combining with Workflows

Sessions restore agents; workflows send them tasks. A common pattern is to restore a session and then run a workflow:

```bash
synapse session restore review-team --worktree
# Wait for agents to become READY...
synapse workflow run review-and-test
```

See [Workflows](workflow.md) for details on defining and running saved message sequences.
