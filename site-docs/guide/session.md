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

Each agent entry captures: profile, name, role, skill set, worktree flag, and **session_id** (the CLI conversation/session identifier from the agent registry). The session_id is used by `--resume` during restore.

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

Displays the full session record including each agent's profile, name, role, skill set, worktree flag, and session_id (if captured). Use this to inspect the saved snapshot before restore.

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

### Resume Conversations (`--resume`)

Add `--resume` to restore each agent's CLI conversation session alongside the team configuration. When saved session_ids are present, agents resume the exact conversation; otherwise they resume the most recent session.

```bash
synapse session restore review-team --resume
```

Per-agent resume behavior depends on the CLI tool:

| Agent | With session_id | Without session_id |
|-------|----------------|--------------------|
| Claude | `--resume <id>` | `--continue` (latest) |
| Gemini | `--resume <id>` | `--resume` (latest) |
| Codex | `resume <id>` | `resume --last` (latest) |
| Copilot | `--resume` (latest only) | `--resume` (latest only) |
| OpenCode | No resume support | No resume support |

!!! note "Time-guarded fallback"
    If an agent's resume fails within the first 10 seconds (e.g., the saved session no longer exists), Synapse automatically retries without resume arguments. This prevents a stale session_id from blocking the restore entirely. Agents that run longer than 10 seconds before failing are not retried, avoiding silent restarts after a long-running session crashes.

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

Each file contains the session name, agent list (profile, name, role, skill set, worktree flag, session_id), working directory, creation timestamp, and scope.

## Browsing CLI Sessions

The `synapse session sessions` command lists CLI tool session files directly from the filesystem. This is useful for discovering available session IDs before saving or understanding what conversations exist for each agent.

```bash
synapse session sessions                          # All profiles
synapse session sessions --profile claude         # Claude only
synapse session sessions --profile gemini         # Gemini only
synapse session sessions --limit 10               # Limit results
```

The output shows each session's profile, session ID, last modification time, and file size. Sessions are sorted by modification time (newest first).

### Supported CLI Tools

| Tool | Session Location | ID Format |
|------|-----------------|-----------|
| Claude | `~/.claude/projects/<project-hash>/*.jsonl` | JSONL file stem |
| Gemini | `~/.gemini/tmp/<project-hash>/chats/*.json` | JSON file stem |
| Codex | `~/.codex/sessions/**/*.jsonl` | JSONL file stem |
| Copilot | `~/.copilot/session-state/*.jsonl` | JSONL file stem |

!!! note "Project-scoped detection"
    Claude and Gemini sessions are scoped to the current working directory. The command uses the same directory-based lookup that `session save` uses when auto-capturing session IDs.

### Session ID Auto-Capture

When agents start, Synapse automatically detects the CLI tool's session ID from the filesystem and stores it in the agent registry. This happens in a background thread after the agent passes the readiness gate, so it does not delay startup.

The auto-captured `session_id` is then included when you run `synapse session save`, enabling `--resume` to target the exact conversation rather than falling back to "most recent."

**Flow:**

1. Agent starts and reaches READY state
2. Background thread calls `detect_session_id()` for the agent's profile
3. The detected ID is written to the registry via `update_session_id()`
4. `synapse session save` reads the registry and stores the `session_id` per agent
5. `synapse session restore --resume` uses the saved `session_id` to resume the exact conversation

## Combining with Workflows

Sessions restore agents; workflows send them tasks. A common pattern is to restore a session and then run a workflow:

```bash
synapse session restore review-team --worktree --resume
# Wait for agents to become READY...
synapse workflow run review-and-test
```

See [Workflows](workflow.md) for details on defining and running saved message sequences.
