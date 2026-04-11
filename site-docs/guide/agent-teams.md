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

Specify target, name, role, and skill set per agent using colon-separated format:

```
target[:name[:role[:skill_set[:port]]]]
```

The `target` can be a built-in profile name (`claude`, `gemini`, etc.) or a saved agent ID/name.

```bash
synapse team start \
  gemini:Gem:code-review:reviewer \
  codex:Rex \
  codex:Cody:implementation
```

!!! tip "Automatic Port Pre-Allocation"
    When launching multiple agents of the same type, `team start` pre-allocates a unique port for each agent before spawning. This prevents race conditions where simultaneous agents could bind to the same port.

### Auto-Approval Control

Disable automatic tool approval injection for all agents launched by `team start`:

```bash
synapse team start claude gemini --no-auto-approve
```

!!! tip "Dynamic Skill Set Changes"
    Skill sets specified in the extended spec are applied at startup. To change an agent's skill set after it has started, use `synapse skills apply`:
    ```bash
    synapse skills apply Cody developer
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
synapse spawn codex --name Rex --role "test writer"
synapse spawn claude --terminal tmux
```

### Spawn from Saved Agent Definition

You can also spawn using a saved agent ID or display name instead of a profile:

```bash
synapse spawn sharp-checker             # Spawn by saved agent ID
synapse spawn Rex                     # Spawn by saved agent display name
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
  -d '{"profile": "claude", "name": "Claud", "tool_args": ["--dangerously-skip-permissions"]}'
```

## Delegate Mode

Start an agent as a **manager** that coordinates work without editing files directly:

```bash
synapse claude --delegate-mode
synapse claude --delegate-mode --name manager --role "task manager"
```

### How It Works

When `--delegate-mode` is enabled, Synapse applies two constraints:

1. **File lock denial** — The agent's file lock requests are always rejected by the [File Safety](file-safety.md) system. This prevents the manager from directly editing files, enforcing a clean separation of concerns.

2. **Manager instructions** — Synapse automatically injects a `[MANAGER MODE]` instruction on startup, telling the agent to:
    - Delegate tasks via `synapse send`
    - Monitor agents via `synapse list`
    - Coordinate work via `synapse send` and `synapse list`
    - Focus on task analysis, splitting, assignment, and review

```
┌──────────────────────────────────────┐
│   Manager (--delegate-mode)          │
│   Analyzes, splits, assigns, reviews │
└────────┬─────────────┬──────────────┘
         │             │
    synapse send   synapse send
         │             │
   ┌─────▼─────┐ ┌────▼──────┐
   │  Worker A  │ │  Worker B  │
   │  (gemini)  │ │  (codex)   │
   │  Implements │ │  Tests     │
   └───────────┘ └───────────┘
```

!!! tip "Combine with Skill Sets"
    Equip the manager with the `manager` skill set for enhanced orchestration capabilities:
    ```bash
    synapse claude --delegate-mode --name manager --skill-set manager
    ```
    The `manager` skill set includes `synapse-manager` (structured 5-step management workflow) and `synapse-reinst` (instruction recovery).

### Delegate Workflow

```bash
# Terminal 1: Manager (cannot edit files)
synapse claude --delegate-mode --name manager

# Terminal 2-3: Workers (edit files normally)
synapse codex --name Cody
synapse codex --name Rex

# Delegate tasks (fire-and-forget — no reply needed)
synapse send Cody "Implement OAuth2 authentication — add OAuth2 to API layer" --silent
synapse send Rex "Write tests for auth module — unit + integration tests" --silent

# Check progress (expects a reply — use --wait)
synapse send Cody "Progress?" --wait
```

### Full Team Setup Example

Use `team start` to launch a manager and workers together:

```bash
# Manager + 2 workers with worktree isolation
synapse team start \
  claude:Claud:task-coordinator:manager \
  codex:Cody:implementation \
  codex:Rex:test-writer \
  --worktree

# Then enable delegate mode on the manager
# (delegate-mode is set per-agent at startup, not via team start)
```

Or start the manager separately:

```bash
# Start manager in current terminal
synapse claude --delegate-mode --name manager --skill-set manager

# Spawn workers in new panes
synapse spawn codex --name Cody --role "implementation" --worktree
synapse spawn codex --name Rex --role "test writer" --worktree
```

### When to Use Delegate Mode

| Scenario | Recommended |
|----------|:-----------:|
| Large feature with multiple files | :material-check: |
| Code review + implementation split | :material-check: |
| Coordinating 3+ specialist agents | :material-check: |
| Simple single-agent task | :material-close: |
| Solo development with one agent | :material-close: |

!!! info "Why Not Just Tell the Agent Not to Edit?"
    While you could manually instruct an agent not to edit files, `--delegate-mode` provides a **system-level guarantee** via File Safety. Even if the agent ignores the instruction, file lock requests are rejected at the framework level. This prevents accidental edits and ensures the manager stays in its coordination role.

### Configuration

The delegate mode instruction template can be customized in [settings](settings.md):

```json
{
  "delegate_mode": {
    "deny_file_locks": true,
    "instruction_template": "\n\n[MANAGER MODE]\nYou are a manager. Do NOT edit files directly.\nInstead, use `synapse send` to delegate tasks to other agents.\nFocus on: task analysis, splitting, assignment, and review.\nUse `synapse list` to check agent availability."
  }
}
```

| Key | Default | Description |
|-----|---------|-------------|
| `deny_file_locks` | `true` | Reject all file lock requests from this agent |
| `instruction_template` | `[MANAGER MODE] ...` | Instructions injected on startup |

!!! warning
    Setting `deny_file_locks: false` removes the system-level file editing guard. The agent will receive manager instructions but can still acquire file locks. This is not recommended.

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

!!! info "tmux Pane Scoping"
    In tmux, `split-window` targets `$TMUX_PANE` so new panes are created adjacent to the source pane. This prevents layout disruption when other panes or windows are open in the same tmux session.

!!! info "tmux Pane Titles"
    Synapse automatically labels each tmux pane with a title like `synapse(claude)` or `synapse(claude:Reviewer)` and enables `pane-border-status top` so the title is visible in the pane border. This makes it easy to identify which agent is running in each pane at a glance.

!!! info "Ghostty Pane Creation"
    Ghostty creates split panes using AppleScript keystrokes: `Cmd+D` (`new_split:right`) and `Cmd+Shift+D` (`new_split:down`). The `--layout` flag controls direction: `split` alternates right/down per agent for balanced tiling, `horizontal` always splits right, and `vertical` always splits down. Commands are injected via clipboard paste to avoid character mangling.

    **Pane auto-close**: All terminals auto-close spawned panes when the agent process exits.

    - iTerm2 and Terminal.app use `exec` to replace the shell process.
    - Ghostty appends `; exit` to the command (since clipboard paste injection is incompatible with `exec`).

!!! warning "Ghostty Limitation: Focus-dependent targeting"
    Ghostty uses AppleScript to target the **currently focused window/tab**. If you switch tabs while `spawn` or `team start` is running, agents may be created in the wrong tab. Wait for the command to complete before interacting with the terminal.

## Spawn Zone Tiling

When using `synapse spawn` to add agents one at a time, panes are organized using a **spawn zone** concept with **automatic tiling**:

1. **First spawn** — splits the current pane horizontally to create a dedicated spawn zone
2. **Subsequent spawns** — automatically apply tmux tile layout when 2+ agents exist in the spawn zone, leaving your working pane untouched

!!! tip "Auto-Tile (since v0.23.4)"
    Tile layout is applied automatically — no extra flags needed. When a second or subsequent agent is spawned, Synapse detects the existing spawn zone panes via `SYNAPSE_SPAWN_PANES` and applies an optimal tile arrangement.

The largest pane in the spawn zone is selected for splitting, with direction determined by aspect ratio:

- **Wide pane** (width ≥ height × 2) → horizontal split (side-by-side)
- **Tall pane** → vertical split (stacked)

```
After 1 spawn:           After 3 spawns:
┌────────┬────────┐      ┌────────┬───┬────┐
│  You   │ Agent1 │      │  You   │A1 │ A3 │
│        │        │      │        ├───┴────┤
└────────┴────────┘      │        │ Agent2 │
                         └────────┴────────┘
```

!!! info "SYNAPSE_SPAWN_PANES"
    Synapse tracks spawn zone pane IDs in the `SYNAPSE_SPAWN_PANES` environment variable (comma-separated). This is managed automatically by `spawn_agent()` — no manual configuration needed.

!!! note "Terminal-specific behavior"
    | Terminal | Tiling Strategy |
    |----------|----------------|
    | **tmux** | Largest-pane detection within spawn zone via `SYNAPSE_SPAWN_PANES` |
    | **iTerm2** | Alternating vertical/horizontal splits based on session count |
    | **Ghostty** | Alternating `Cmd+D` / `Cmd+Shift+D` |
    | **zellij** | Alternating right/down splits based on pane count |

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

.synapse/worktrees/steady-builder/ (Agent B)
└── Implements feature on worktree-steady-builder branch

.synapse/worktrees/sharp-checker/ (Agent C)
└── Writes tests on worktree-sharp-checker branch
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
synapse kill steady-builder -f
synapse kill sharp-checker -f

# Merge changes from worktree branches
git merge worktree-steady-builder
git merge worktree-sharp-checker

# Clean up branches (worktrees auto-removed on agent exit if no changes and no new commits)
git branch -d worktree-steady-builder
git branch -d worktree-sharp-checker
```

## Saved Agent Definitions

Save reusable agent definitions for repeated use with `synapse <profile> --agent`, `synapse spawn`, and `synapse team start`. Definitions are stored as `.agent` files in Agent ID-keyed format.

### Creating a Saved Agent

```bash
synapse agents add sharp-checker \
  --name Rex \
  --profile codex \
  --role @./roles/tester.md \
  --skill-set developer \
  --scope project
```

| Field | Description |
|-------|-------------|
| `<id>` | Agent ID in petname format (lowercase words joined by hyphens, e.g. `sharp-checker`, `calm-lead`) |
| `--name` | Display name (required) |
| `--profile` | Agent profile: `claude`, `codex`, `gemini`, `opencode`, `copilot` (required) |
| `--role` | Role description or `@path` file reference (e.g. `@./roles/reviewer.md`) |
| `--skill-set` | Skill set to activate |
| `--scope` | `project` (`.synapse/agents/`) or `user` (`~/.synapse/agents/`) |

### Listing and Inspecting

```bash
synapse agents list          # Table of all saved agents
synapse agents show Rex    # Show details for one agent
```

### Deleting

```bash
synapse agents delete sharp-checker
```

### Using at Startup

Start an agent with a saved definition using `--agent` / `-A`:

```bash
synapse claude --agent calm-lead        # By saved agent ID
synapse claude -A Claud                 # By display name
synapse claude --agent calm-lead --role "temporary override"  # CLI overrides
```

The saved agent's profile must match the profile shortcut. For example, a saved agent with `profile=gemini` cannot be used with `synapse claude`.

### Using with Spawn

Spawn by saved agent ID or display name:

```bash
synapse spawn sharp-checker
synapse spawn Rex
```

CLI flags override saved values:

```bash
synapse spawn sharp-checker --role "temporary override role"
```

### Using with Team Start

Saved agent IDs/names work as targets in team start specs:

```bash
synapse team start sharp-checker steady-builder              # By saved agent IDs
synapse team start sharp-checker:Checker gemini:Gem  # Mix saved + profile
```

### Storage and Scope

| Scope | Path | Precedence |
|-------|------|------------|
| Project | `.synapse/agents/*.agent` | Higher (takes priority) |
| User | `~/.synapse/agents/*.agent` | Lower (fallback) |

Project-scope definitions take precedence over user-scope when IDs collide. Use project scope for team-specific agents and user scope for personal templates.

**File format** (key=value):

```ini
id=sharp-checker
name=Rex
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
synapse spawn codex --name Rex --role "test writer"
# Wait for READY...

synapse send Rex "Write unit tests for auth.py — cover all auth flows" --wait
# Evaluate result
synapse kill Rex -f
```

### Parallel Specialists

```bash
synapse spawn codex --name Rex --role "test writer"
synapse spawn codex --name Cody --role "bug fixer"

# Parallel tasks (fire-and-forget — no reply needed)
synapse send Rex "Write tests for auth.py" --silent
synapse send Cody "Fix timeout bug in server.py" --silent

# Collect results (expects a reply — use --wait)
synapse send Rex "Progress?" --wait
synapse send Cody "Progress?" --wait

# Cleanup
synapse kill Rex -f
synapse kill Cody -f
```

## Best Practices

### team start vs spawn

| Feature | `team start` | `spawn` |
|---------|--------------|---------|
| **Usage** | Manual orchestration by human | Programmatic delegation by agent |
| **Visibility** | Always visible in panes/tabs | Usually headless/minimized |
| **Lifecycle** | Long-running session | Task-oriented (spawn-work-kill) |
| **Tiling** | Layout via `--layout` flag | Auto-tile when 2+ agents in spawn zone |
| **Isolation** | Shared or isolated worktrees | Shared or isolated worktrees |

### Use Worktrees for Workers

Always use `--worktree` for agents that modify code. This prevents:
- **Git lock conflicts**: Multiple agents trying to `git add` simultaneously.
- **PTY mangling**: One agent seeing the other's unfinished changes in `git status`.
- **Merge noise**: Uncontrolled file system changes affecting both agents.

### Spawn Cross-Model

When spawning agents for delegation or parallel work, prefer a **different model type** than the one doing the spawning. This provides two benefits:

1. **Diverse perspectives** -- Different LLMs have distinct strengths and blind spots
2. **Rate limit distribution** -- Spreading token usage across providers avoids hitting rate limits on any single model

```bash
# Claude manager spawning Gemini and Codex workers (cross-model)
synapse spawn gemini --name Reviewer --role "code reviewer"
synapse spawn codex -w --name Impl --role "implementation"
```

### Worker Autonomy

Worker agents are not limited to receiving tasks -- they can also delegate:

- **Spawn helpers** for independent subtasks (prefer different model types)
- **Request reviews** from other agents
- **Delegate out-of-scope work** instead of handling everything yourself
- **Share findings** via `synapse memory save` so the team benefits
- **Always clean up** -- kill agents you spawn when done: `synapse kill <name> -f`

See [Proactive Collaboration](cross-agent-scenarios.md#proactive-collaboration-framework) for the full decision framework.

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
