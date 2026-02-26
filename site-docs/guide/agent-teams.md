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

Specify name, role, and skill set per agent:

```
profile[:name[:role[:skill_set]]]
```

```bash
synapse team start \
  claude:Reviewer:code-review:reviewer \
  gemini:Searcher \
  codex:Implementer:implementation
```

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
synapse send worker-1 "Implement OAuth2 authentication" \
  --from $SYNAPSE_AGENT_ID --no-response
synapse send worker-2 "Write tests for auth module" \
  --from $SYNAPSE_AGENT_ID --no-response

# Check progress
synapse send worker-1 "Progress?" --from $SYNAPSE_AGENT_ID --response
```

## Supported Terminals

| Terminal | spawn | team start | Layout Control |
|----------|:---:|:---:|:---:|
| **tmux** | :material-check: | :material-check: | :material-check: |
| **iTerm2** | :material-check: | :material-check: | :material-check: |
| **Terminal.app** | :material-check: | :material-check: | :material-check: |
| **Ghostty** | :material-check: | :material-check: | :material-check: |
| **Zellij** | :material-check: | :material-check: | :material-check: |

!!! note
    Terminal detection is automatic. Use `--terminal <name>` to override.

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

## Patterns

### Single-Task Delegation

```bash
synapse spawn gemini --name Tester --role "test writer"
# Wait for READY...
synapse send Tester "Write unit tests for auth.py" \
  --response --from $SYNAPSE_AGENT_ID
# Evaluate result
synapse kill Tester -f
```

### Parallel Specialists

```bash
synapse spawn gemini --name Tester --role "test writer"
synapse spawn codex --name Fixer --role "bug fixer"

# Parallel tasks
synapse send Tester "Write tests for auth.py" \
  --no-response --from $SYNAPSE_AGENT_ID
synapse send Fixer "Fix timeout bug in server.py" \
  --no-response --from $SYNAPSE_AGENT_ID

# Collect results
synapse send Tester "Progress?" --response --from $SYNAPSE_AGENT_ID
synapse send Fixer "Progress?" --response --from $SYNAPSE_AGENT_ID

# Cleanup
synapse kill Tester -f
synapse kill Fixer -f
```
