# Agent Teams

## Overview

Synapse supports multi-agent teams with automatic terminal pane creation, delegation, and worktree isolation.

## Team Start

Launch multiple agents at once:

```bash
synapse team start claude gemini codex
```

**Default behavior**: The first agent takes over the current terminal, others get new panes.

### Layout Options

```bash
synapse team start claude gemini codex --layout horizontal
synapse team start claude gemini codex --layout vertical
synapse team start claude gemini codex --layout split      # Default
```

### All New Panes

Keep the current terminal free:

```bash
synapse team start claude gemini --all-new
```

### Extended Spec Format

Specify target, name, role, skill set, and port per agent using colon-separated format:

```
target[:name[:role[:skill_set[:port]]]]
```

The `target` can be a built-in profile name (`claude`, `gemini`, etc.) or a saved agent ID/name.

```bash
synapse team start \
  claude:Reviewer:code-review:reviewer \
  gemini:Searcher \
  codex:Implementer:implementation
```

!!! tip "Automatic Port Pre-Allocation"
    When launching multiple agents of the same type, `team start` pre-allocates a unique port for each agent before spawning. This prevents race conditions where simultaneous agents could bind to the same port.

!!! tip "Dynamic Skill Set Changes"
    Skill sets specified in the extended spec are applied at startup. To change an agent's skill set after it has started, use `synapse skills apply`:
    ```bash
    synapse skills apply Reviewer developer
    ```
    See [Applying Skill Sets](skills.md#apply-to-a-running-agent) for details.

### Tool Arguments

Pass arguments to the underlying CLI tools after `--`:

```bash
synapse team start claude gemini -- --dangerously-skip-permissions
```

### Worktree Isolation

Give each agent an isolated git worktree:

```bash
# Synapse-native worktree (all agents supported)
synapse team start claude gemini --worktree

# With name prefix (generates task-claude-0, task-gemini-1)
synapse team start claude gemini --worktree task
```

Each agent gets its own worktree under `.synapse/worktrees/` with a dedicated branch. No file conflicts between agents.

!!! tip "Synapse vs Claude Code worktree"
    `--worktree` (before `--`) is a Synapse flag that works with **all** agent types. The older `-- --worktree` (after `--`) is a Claude Code-only flag. See [Worktree Isolation](../advanced/worktree.md) for details.

## Spawn Single Agent

Spawn a single agent in a new pane:

```bash
synapse spawn claude
synapse spawn gemini --port 8115
synapse spawn claude --name Tester --role "test writer"
synapse spawn claude --terminal tmux
```

### Spawn from Saved Agent Definition

You can also spawn using a saved agent ID or display name instead of a profile:

```bash
synapse spawn silent-snake              # Spawn by saved agent ID
synapse spawn Alice                     # Spawn by saved agent display name
```

The saved agent's profile, name, role, and skill set are automatically resolved. CLI flags override saved values when specified.

See [Saved Agent Definitions](#saved-agent-definitions) below for how to create saved agents.

### With Tool Arguments

```bash
synapse spawn claude -- --dangerously-skip-permissions
```

### With Worktree

```bash
# Synapse-native worktree (all agents)
synapse spawn claude --worktree
synapse spawn gemini --worktree feature-auth --name Auth --role "auth implementation"
synapse spawn codex -w  # short flag
```

See [Worktree Isolation](../advanced/worktree.md) for full details.

### Spawn via API

Agents can spawn other agents programmatically:

```bash
curl -X POST http://localhost:8100/spawn \
  -H "Content-Type: application/json" \
  -d '{"profile": "gemini", "name": "Helper", "tool_args": ["--dangerously-skip-permissions"]}'
```

## Delegate Mode

Start an agent as a manager that delegates instead of editing files directly:

```bash
synapse claude --delegate-mode --name manager --role "task manager"
```

The manager receives instructions to:

- Use `synapse send` to delegate tasks
- Monitor progress via `synapse list` and `synapse history`
- Coordinate results across team members
- Never directly edit files

### Delegate Workflow

```bash
# Terminal 1: Manager
synapse claude --delegate-mode --name manager

# Terminal 2-3: Workers
synapse gemini --name worker-1
synapse codex --name worker-2

# Manager delegates (fire-and-forget — no reply needed)
synapse send worker-1 "Implement OAuth2 authentication" --silent
synapse send worker-2 "Write tests for auth module" --silent

# Check progress (expects a reply — use --wait)
synapse send worker-1 "Progress?" --wait
```

## Supported Terminals

| Terminal | spawn | team start | Layout Control |
|----------|:---:|:---:|:---:|
| **tmux** | :material-check: | :material-check: | :material-check: |
| **iTerm2** | :material-check: | :material-check: | :material-check: |
| **Terminal.app** | :material-check: | :material-check: | :material-check: |
| **Ghostty** | :material-check: | :material-check: | — |
| **VS Code** | :material-check: | :material-check: | :material-check: |
| **Zellij** | :material-check: | :material-check: | :material-check: |

!!! note
    Terminal detection is automatic. Use `--terminal <name>` to override.

!!! info "Ghostty Pane Creation"
    Ghostty creates split panes using its `Cmd+D` keybinding (`new_split:right`). The `--layout` and `--all-new` flags are not applicable — each agent always gets a right-split pane in the current window. Commands are injected via clipboard paste to avoid character mangling.

    **Pane auto-close**: All terminals auto-close spawned panes when the agent process exits.

    - iTerm2 and Terminal.app use `exec` to replace the shell process.
    - Ghostty appends `; exit` to the command (since clipboard paste injection is incompatible with `exec`).

!!! warning "Ghostty Limitation: Focus-dependent targeting"
    Ghostty uses AppleScript to target the **currently focused window/tab**. If you switch tabs while `spawn` or `team start` is running, agents may be created in the wrong tab. Wait for the command to complete before interacting with the terminal.

## Team Start via API

```bash
curl -X POST http://localhost:8100/team/start \
  -H "Content-Type: application/json" \
  -d '{
    "agents": ["gemini", "codex"],
    "layout": "split",
    "tool_args": ["--dangerously-skip-permissions"]
  }'
```

## Worktree Isolation Details

Git worktrees give each agent an isolated copy of the repository under `.synapse/worktrees/`:

```
Main Worktree (Manager)
├── Coordinates and integrates
└── Reviews merged results

.synapse/worktrees/worker-1/ (Agent B)
└── Implements feature on worktree-worker-1 branch

.synapse/worktrees/worker-2/ (Agent C)
└── Writes tests on worktree-worker-2 branch
```

**Benefits:**

- No file conflicts between agents
- Each agent has an independent staging area
- Changes merge via Git at the end
- Efficient disk usage (shared `.git/objects/`)
- Works with all agent types, not just Claude Code

**Cleanup:**

```bash
# After work is done
synapse kill worker-1 -f
synapse kill worker-2 -f

# Merge changes from worktree branches
git merge worktree-worker-1
git merge worktree-worker-2

# Clean up branches (worktrees auto-removed on agent exit if no changes and no new commits)
git branch -d worktree-worker-1
git branch -d worktree-worker-2
```

## Saved Agent Definitions

Save reusable agent definitions for repeated use with `synapse <profile> --agent`, `synapse spawn`, and `synapse team start`. Definitions are stored as `.agent` files in Agent ID-keyed format.

### Creating a Saved Agent

```bash
synapse agents add silent-snake \
  --name Alice \
  --profile codex \
  --role @./roles/reviewer.md \
  --skill-set architect \
  --scope project
```

| Field | Description |
|-------|-------------|
| `<id>` | Agent ID in petname format (lowercase words joined by hyphens, e.g. `silent-snake`, `wise-strategist`) |
| `--name` | Display name (required) |
| `--profile` | Agent profile: `claude`, `codex`, `gemini`, `opencode`, `copilot` (required) |
| `--role` | Role description or `@path` file reference (e.g. `@./roles/reviewer.md`) |
| `--skill-set` | Skill set to activate |
| `--scope` | `project` (`.synapse/agents/`) or `user` (`~/.synapse/agents/`) |

### Listing and Inspecting

```bash
synapse agents list          # Table of all saved agents
synapse agents show Alice    # Show details for one agent
```

### Deleting

```bash
synapse agents delete silent-snake
```

### Using at Startup

Start an agent with a saved definition using `--agent` / `-A`:

```bash
synapse claude --agent wise-strategist        # By saved agent ID
synapse claude -A Alice                       # By display name
synapse claude --agent wise-strategist --role "temporary override"  # CLI overrides
```

The saved agent's profile must match the profile shortcut. For example, a saved agent with `profile=gemini` cannot be used with `synapse claude`.

### Using with Spawn

Spawn by saved agent ID or display name:

```bash
synapse spawn silent-snake
synapse spawn Alice
```

CLI flags override saved values:

```bash
synapse spawn silent-snake --role "temporary override role"
```

### Using with Team Start

Saved agent IDs/names work as targets in team start specs:

```bash
synapse team start silent-snake happy-crab              # By saved agent IDs
synapse team start silent-snake:Reviewer gemini:Searcher  # Mix saved + profile
```

### Storage and Scope

| Scope | Path | Precedence |
|-------|------|------------|
| Project | `.synapse/agents/*.agent` | Higher (takes priority) |
| User | `~/.synapse/agents/*.agent` | Lower (fallback) |

Project-scope definitions take precedence over user-scope when IDs collide. Use project scope for team-specific agents and user scope for personal templates.

**File format** (key=value):

```ini
id=silent-snake
name=Alice
profile=codex
role=code reviewer
skill_set=architect
```

### Save on Exit

When an interactive agent exits (with a name set), Synapse prompts whether to save the current agent definition for reuse. This provides a convenient way to capture agent configurations without using `synapse agents add` directly.

!!! tip "Role Files"
    Roles can reference Markdown files using the `@` prefix. Store project-shared roles in `./roles/` (committed to Git) and personal roles in `~/my-roles/` or `~/.synapse/roles/`.

## Patterns

### Single-Task Delegation

```bash
synapse spawn gemini --name Tester --role "test writer"
# Wait for READY...
synapse send Tester "Write unit tests for auth.py" --wait
# Evaluate result
synapse kill Tester -f
```

### Parallel Specialists

```bash
synapse spawn gemini --name Tester --role "test writer"
synapse spawn codex --name Fixer --role "bug fixer"

# Parallel tasks (fire-and-forget — no reply needed)
synapse send Tester "Write tests for auth.py" --silent
synapse send Fixer "Fix timeout bug in server.py" --silent

# Collect results (expects a reply — use --wait)
synapse send Tester "Progress?" --wait
synapse send Fixer "Progress?" --wait

# Cleanup
synapse kill Tester -f
synapse kill Fixer -f
```

## Best Practices

### team start vs spawn

| Feature | `team start` | `spawn` |
|---------|--------------|---------|
| **Usage** | Manual orchestration by human | Programmatic delegation by agent |
| **Visibility** | Always visible in panes/tabs | Usually headless/minimized |
| **Lifecycle** | Long-running session | Task-oriented (spawn-work-kill) |
| **Isolation** | Shared or isolated worktrees | Shared or isolated worktrees |

### Use Worktrees for Workers

Always use `--worktree` for agents that modify code. This prevents:
- **Git lock conflicts**: Multiple agents trying to `git add` simultaneously.
- **PTY mangling**: One agent seeing the other's unfinished changes in `git status`.
- **Merge noise**: Uncontrolled file system changes affecting both agents.

### Kill Your Darlings

Ensure your implementation includes `synapse kill <name> -f` at the end of a delegated task. Unused resident agents consume:
- **Memory**: ~12MB per process.
- **Ports**: Limited to 10 per type (e.g., 8100-8109).
- **Registry space**: `synapse list` becomes cluttered.

### Verification Pattern

After an agent completes a task, always verify its work from the manager's perspective:

```bash
# 1. Wait for completion
synapse send Worker "Status?" --wait

# 2. Inspect artifacts
git diff worktree-Worker

# 3. Run validation tests
pytest tests/affected_module.py

# 4. Finalize
synapse kill Worker -f
git merge worktree-Worker
```
