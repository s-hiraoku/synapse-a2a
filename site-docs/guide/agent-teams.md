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

Specify name, role, skill set, and port per agent:

```
profile[:name[:role[:skill_set[:port]]]]
```

```bash
synapse team start \
  claude:Reviewer:code-review:reviewer \
  gemini:Searcher \
  codex:Implementer:implementation
```

!!! tip "Automatic Port Pre-Allocation"
    When launching multiple agents of the same type, `team start` pre-allocates a unique port for each agent before spawning. This prevents race conditions where simultaneous agents could bind to the same port.

### Tool Arguments

Pass arguments to the underlying CLI tools after `--`:

```bash
synapse team start claude gemini -- --dangerously-skip-permissions
```

### Worktree Isolation

Give each agent an isolated git worktree:

```bash
synapse team start claude gemini -- --worktree
```

!!! info "Claude Code Only"
    `--worktree` is a Claude Code flag. Other CLIs silently ignore unknown flags, so it's safe to pass to all agents.

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
synapse spawn 狗巻棘                     # Spawn by saved agent display name
```

The saved agent's profile, name, role, and skill set are automatically resolved. CLI flags override saved values when specified.

See [Saved Agent Definitions](#saved-agent-definitions) below for how to create saved agents.

### With Tool Arguments

```bash
synapse spawn claude -- --dangerously-skip-permissions
```

### With Worktree

```bash
synapse spawn claude --name Worker --role "feature implementation" -- --worktree
```

### Spawn via API

Agents can spawn other agents programmatically:

```bash
curl -X POST http://localhost:8100/spawn \
  -H "Content-Type: application/json" \
  -d '{"profile": "gemini", "name": "Helper", "tool_args": ["--dangerously-skip-permissions"]}'
```

## Delegate Mode

Start an agent as a coordinator that delegates instead of editing files directly:

```bash
synapse claude --delegate-mode --name coordinator --role "task manager"
```

The coordinator receives instructions to:

- Use `synapse send` to delegate tasks
- Monitor progress via `synapse list` and `synapse history`
- Coordinate results across team members
- Never directly edit files

### Delegate Workflow

```bash
# Terminal 1: Coordinator
synapse claude --delegate-mode --name coordinator

# Terminal 2-3: Workers
synapse gemini --name worker-1
synapse codex --name worker-2

# Coordinator delegates
synapse send worker-1 "Implement OAuth2 authentication" --no-response
synapse send worker-2 "Write tests for auth module" --no-response

# Check progress
synapse send worker-1 "Progress?" --response
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

Git worktrees give each agent an isolated copy of the repository:

```
Main Worktree (Coordinator)
├── Coordinates and integrates
└── Reviews merged results

.claude/worktrees/worker-1/ (Agent B)
└── Implements feature on worktree-worker-1 branch

.claude/worktrees/worker-2/ (Agent C)
└── Writes tests on worktree-worker-2 branch
```

**Benefits:**

- No file conflicts between agents
- Each agent has an independent staging area
- Changes merge via Git at the end
- Efficient disk usage (shared `.git/objects/`)

**Cleanup:**

```bash
# After work is done
synapse kill worker-1 -f
synapse kill worker-2 -f

# Merge changes
git merge worktree-worker-1
git merge worktree-worker-2

# Clean up worktrees
git worktree remove .claude/worktrees/worker-1
git worktree remove .claude/worktrees/worker-2
```

## Saved Agent Definitions

Save reusable agent definitions for repeated use with `synapse spawn`. Definitions are stored as `.agent` files in petname-keyed format.

### Creating a Saved Agent

```bash
synapse agents add silent-snake \
  --name 狗巻棘 \
  --profile codex \
  --role @./roles/reviewer.md \
  --skill-set architect \
  --scope project
```

| Field | Description |
|-------|-------------|
| `<id>` | Petname-format identifier (e.g. `silent-snake`) |
| `--name` | Display name (required) |
| `--profile` | Agent profile: `claude`, `codex`, `gemini`, `opencode`, `copilot` (required) |
| `--role` | Role description or `@path` file reference |
| `--skill-set` | Skill set to activate |
| `--scope` | `project` (`.synapse/agents/`) or `user` (`~/.synapse/agents/`) |

### Listing and Inspecting

```bash
synapse agents list          # Table of all saved agents
synapse agents show 狗巻棘    # Show details for one agent
```

### Deleting

```bash
synapse agents delete silent-snake
```

### Using with Spawn

Once defined, spawn by saved agent ID or display name:

```bash
synapse spawn silent-snake
synapse spawn 狗巻棘
```

CLI flags override saved values:

```bash
synapse spawn silent-snake --role "temporary override role"
```

### Save on Exit

When an interactive agent exits (with a name set), Synapse prompts whether to save the current agent definition for reuse. This provides a convenient way to capture agent configurations without using `synapse agents add` directly.

!!! info "Scope Precedence"
    Project-scope definitions (`.synapse/agents/`) take precedence over user-scope (`~/.synapse/agents/`) when IDs collide.

## Patterns

### Single-Task Delegation

```bash
synapse spawn gemini --name Tester --role "test writer"
# Wait for READY...
synapse send Tester "Write unit tests for auth.py" --response
# Evaluate result
synapse kill Tester -f
```

### Parallel Specialists

```bash
synapse spawn gemini --name Tester --role "test writer"
synapse spawn codex --name Fixer --role "bug fixer"

# Parallel tasks
synapse send Tester "Write tests for auth.py" --no-response
synapse send Fixer "Fix timeout bug in server.py" --no-response

# Collect results
synapse send Tester "Progress?" --response
synapse send Fixer "Progress?" --response

# Cleanup
synapse kill Tester -f
synapse kill Fixer -f
```
