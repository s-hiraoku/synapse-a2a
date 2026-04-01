# Worktree Isolation

## Overview

Git worktrees provide isolated working copies for each agent, enabling parallel work without file conflicts. Synapse manages worktrees natively under `.synapse/worktrees/`, so **all agent types** (Claude, Gemini, Codex, OpenCode, Copilot) benefit from isolation — not just Claude Code.

## How It Works

```
Main Worktree (your terminal)
├── Normal repo checkout
└── .synapse/worktrees/
    ├── bold-hawk/           (Agent A — auto-generated name)
    │   ├── .git (file)      ← Points to main .git
    │   ├── src/
    │   └── ...              Branch: worktree-bold-hawk
    └── feature-auth/        (Agent B — explicit name)
        ├── .git (file)
        ├── src/
        └── ...              Branch: worktree-feature-auth
```

**Benefits:**

- No file conflicts between agents (each on its own branch)
- Efficient disk usage (shared object database under `.git/`)
- Works with every CLI agent, not just Claude Code
- Automatic cleanup on agent exit or `synapse kill` (checks both uncommitted changes and new commits)

## Usage

### Spawn with Worktree

```bash
# Auto-generated name (e.g., bold-hawk)
synapse spawn claude --worktree

# Explicit name
synapse spawn claude --worktree feature-auth --name Auth --role "auth implementation"

# Short flag
synapse spawn gemini -w

# Specify base branch (worktree branches off from the given branch)
synapse spawn codex --worktree --branch renovate/major-eslint-monorepo
synapse spawn claude -w feature-auth -b develop
```

### Team Start with Worktree

Each agent gets its own worktree automatically:

```bash
# Auto names
synapse team start claude gemini --worktree

# Name prefix (generates task-claude-0, task-gemini-1)
synapse team start claude gemini --worktree task

# All agents branch off a specific base branch
synapse team start claude gemini --worktree --branch feature/api-v2
```

### Profile Shortcut

```bash
synapse claude --worktree my-feature
synapse gemini -w
```

### Spawn via API

```bash
# Auto name
curl -X POST http://localhost:8100/spawn \
  -H "Content-Type: application/json" \
  -d '{"profile": "gemini", "worktree": true}'

# Explicit name
curl -X POST http://localhost:8100/spawn \
  -H "Content-Type: application/json" \
  -d '{"profile": "codex", "worktree": "helper-task"}'
```

Response includes worktree metadata:

```json
{
  "agent_id": "synapse-gemini-8110",
  "port": 8110,
  "status": "submitted",
  "worktree_path": "/repo/.synapse/worktrees/bold-hawk",
  "worktree_branch": "worktree-bold-hawk"
}
```

## Lifecycle

1. **Create**: `git worktree add .synapse/worktrees/<name> -b worktree-<name> <base-branch>`
2. **Run**: Agent process starts with `cwd` set to the worktree directory
3. **Register**: Registry records `worktree_path`, `worktree_branch`, and `worktree_base_branch`
4. **Display**: `synapse list` shows `[WT]` prefix in the WORKING_DIR column
5. **Cleanup** (checks for uncommitted changes **and** new commits beyond the base branch):
    - No changes AND no new commits → auto-delete worktree and branch
    - Changes or new commits exist (interactive) → prompt to keep or force-remove
    - Changes or new commits exist (non-interactive) → keep worktree, print path and branch

The base branch is determined in the following order:

1. `--branch` / `-b` CLI flag (highest priority)
2. `SYNAPSE_WORKTREE_BASE_BRANCH` environment variable
3. `get_default_remote_branch()` auto-detection:
    1. `git symbolic-ref refs/remotes/origin/HEAD` (e.g., `origin/main`)
    2. `origin/main` (if the ref exists locally)
    3. `HEAD` (last resort)

## Monitoring

`synapse list` shows worktree agents with a `[WT]` indicator:

```
TYPE    NAME    PORT  STATUS  WORKING_DIR
claude  Auth    8100  READY   [WT] feature-auth
gemini  -       8110  READY   synapse-a2a
```

## Post-Work Merge

After agents complete their work:

```bash
# Kill workers (worktree auto-cleaned if no changes and no new commits)
synapse kill Auth -f
synapse kill gemini -f

# If worktrees were kept (had uncommitted changes or new commits):
# Merge changes from worktree branches
git merge worktree-feature-auth
git merge worktree-bold-hawk

# Clean up branches
git branch -d worktree-feature-auth
git branch -d worktree-bold-hawk
```

## Synapse vs Claude Code Worktree

| Feature | Synapse `--worktree` | Claude Code `-- --worktree` |
|---------|---------------------|---------------------------|
| Directory | `.synapse/worktrees/` | `.claude/worktrees/` |
| Managed by | Synapse | Claude Code |
| Supported agents | All (Claude, Gemini, Codex, OpenCode, Copilot) | Claude Code only |
| Cleanup | On agent exit or `synapse kill` | On Claude Code session end |
| Flag position | Before `--` (Synapse flag) | After `--` (tool flag) |

!!! tip "Which to use?"
    Use Synapse's `--worktree` for multi-agent workflows. Use Claude Code's `-- --worktree` only when you need Claude Code-specific worktree behavior. Do not combine both — it would create nested worktrees.

## Use Cases

### Implementation + Testing in Parallel

```bash
synapse team start claude:Cody gemini:Gem --worktree
# Cody works in .synapse/worktrees/<name-1>/ on feature code
# Gem works in .synapse/worktrees/<name-2>/ on test code
# No file conflicts — merge both branches when done
```

### Isolated Code Review

```bash
synapse spawn claude --worktree review --name Rex --role "code reviewer"
# Rex operates on worktree-review branch
# Review annotations don't touch the main working directory
```

### Multiple Features Simultaneously

```bash
synapse spawn claude --worktree auth --name Cody --role "implement auth"
synapse spawn gemini --worktree api --name Gem --role "implement API endpoints"
# Each agent on its own branch, merge independently

# Branch off a Renovate/Dependabot PR for testing
synapse spawn codex --worktree --branch renovate/major-eslint-monorepo --name Tester --role "run tests"
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SYNAPSE_WORKTREE_PATH` | Auto | Worktree directory path (set at spawn) |
| `SYNAPSE_WORKTREE_BRANCH` | Auto | Worktree branch name (set at spawn) |
| `SYNAPSE_WORKTREE_BASE_BRANCH` | Auto | Base branch used for new-commit detection during cleanup (set at spawn via `get_default_remote_branch()`) |

## Cross-Worktree Communication

Agents in worktrees operate in a different working directory than the main repo. Synapse blocks sends by default to prevent accidental cross-project messages. Use `--force` (or `--message-file` for complex content) to bridge the gap.

See [Scenario 9: Cross-Worktree Knowledge Transfer](../guide/cross-agent-scenarios.md#scenario-9-cross-worktree-knowledge-transfer) for a complete walkthrough.

## Important Notes

- Files in `.gitignore` are **not copied** to worktrees (e.g., `.env`, `node_modules/`)
- Each worktree may need dependency installation (`uv sync`, `npm install`)
- Add `.synapse/worktrees/` to your `.gitignore`
- Crashed agents may leave worktrees behind — clean up with `git worktree remove -f`
- The same branch cannot be checked out in multiple worktrees simultaneously

## Directory Structure

```
project/
├── .git/
│   ├── objects/              ← Shared (all worktrees use this)
│   ├── refs/heads/
│   │   ├── main
│   │   ├── worktree-bold-hawk
│   │   └── worktree-feature-auth
│   └── worktrees/
│       ├── bold-hawk/        ← Worktree metadata
│       └── feature-auth/
├── .synapse/worktrees/
│   ├── bold-hawk/            ← Full working copy
│   │   ├── .git (file)       ← Points to main .git
│   │   ├── src/
│   │   └── ...
│   └── feature-auth/
│       ├── .git (file)
│       ├── src/
│       └── ...
└── src/                      ← Main worktree files
```
