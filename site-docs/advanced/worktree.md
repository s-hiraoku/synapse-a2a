# Worktree Isolation

## Overview

Git worktrees provide isolated working copies for each agent, enabling parallel work without file conflicts. Each agent operates on its own branch with an independent staging area.

## How It Works

```
Main Worktree (Agent A — Coordinator)
├── Coordinates and reviews
└── Merges results

.claude/worktrees/worker-1/ (Agent B)
├── Independent branch: worktree-worker-1
├── Independent staging area
└── Shared .git/objects/ (disk efficient)

.claude/worktrees/worker-2/ (Agent C)
├── Independent branch: worktree-worker-2
├── Independent staging area
└── Shared .git/objects/
```

**Benefits:**

- No file conflicts between agents (different branches)
- Efficient disk usage (shared object database)
- Each agent has a fully independent working copy
- Changes merge via standard Git at the end

## Usage

### Team Start with Worktree

```bash
synapse team start claude gemini -- --worktree
```

Each agent gets a worktree in `.claude/worktrees/<name>/` with a dedicated branch.

### Single Agent with Worktree

```bash
synapse spawn claude --name Worker --role "feature implementation" -- --worktree
```

### Named Worktree

```bash
synapse spawn claude --name auth-worker -- --worktree auth-feature
```

!!! info "Claude Code Only"
    `--worktree` is a Claude Code flag passed after `--`. Other CLI tools silently ignore unknown flags.

## Lifecycle

1. **Create**: Agent starts → worktree created at `.claude/worktrees/<name>/`
2. **Work**: Agent makes changes on isolated branch
3. **Cleanup**:
    - No changes → auto-delete worktree and branch
    - Has changes → keep for manual merge

## Post-Work Merge

After agents complete their work:

```bash
# Kill workers
synapse kill worker-1 -f
synapse kill worker-2 -f

# Merge changes
git merge worktree-worker-1
git merge worktree-worker-2

# Clean up worktrees
git worktree remove .claude/worktrees/worker-1
git worktree remove .claude/worktrees/worker-2

# Delete branches
git branch -d worktree-worker-1
git branch -d worktree-worker-2
```

## Important Notes

- Files in `.gitignore` are **not copied** to worktrees (e.g., `.env`, `node_modules/`)
- Each worktree may need dependency installation (`uv sync`, `npm install`)
- Add `.claude/worktrees/` to your `.gitignore`
- Crashed agents may leave worktrees behind — clean up with `git worktree remove -f`
- The same branch cannot be checked out in multiple worktrees simultaneously

## Directory Structure

```
project/
├── .git/
│   ├── objects/              ← Shared (all worktrees use this)
│   ├── refs/heads/
│   │   ├── main
│   │   ├── worktree-alpha
│   │   └── worktree-beta
│   └── worktrees/
│       ├── alpha/            ← Worktree metadata
│       └── beta/
├── .claude/worktrees/
│   ├── alpha/                ← Full working copy
│   │   ├── .git (file)      ← Points to main .git
│   │   ├── src/
│   │   └── ...
│   └── beta/
│       ├── .git (file)
│       ├── src/
│       └── ...
└── src/                      ← Main worktree files
```
