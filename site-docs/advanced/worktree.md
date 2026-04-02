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
# --branch implies --worktree, so -w is not required
synapse spawn codex --branch renovate/major-eslint-monorepo
synapse spawn claude -w feature-auth -b develop
```

!!! note "`--branch` implies `--worktree`"
    When you pass `--branch` / `-b` to `synapse spawn`, worktree mode is enabled automatically. You do not need to add `--worktree` / `-w` separately.

### Team Start with Worktree

`synapse team start` **defaults to worktree mode** (`--worktree` is implied). Each agent gets its own worktree automatically. Use `--no-worktree` to opt out.

```bash
# Default: each agent gets a worktree (no flag needed)
synapse team start claude gemini

# Explicit opt-out — agents share the main working directory
synapse team start claude gemini --no-worktree

# Name prefix (generates task-claude-0, task-gemini-1)
synapse team start claude gemini --worktree task

# All agents branch off a specific base branch
synapse team start claude gemini --branch feature/api-v2
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
  "worktree_branch": "worktree-bold-hawk",
  "worktree_base_branch": "origin/main"
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
6. **Auto-merge** (default on `synapse kill`):
    - Uncommitted changes are auto-committed as WIP
    - `git merge worktree-<name> --no-edit` is attempted on the parent branch
    - On success: worktree and branch are removed
    - On conflict: branch is preserved with a warning message
    - Use `synapse kill <agent> --no-merge` to skip auto-merge

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

By default, `synapse kill` performs **auto-merge**: uncommitted changes are committed as WIP, and the worktree branch is merged into the parent branch. If the merge succeeds, the worktree and branch are removed automatically.

```bash
# Kill with auto-merge (default)
synapse kill Auth -f
synapse kill gemini -f

# Skip auto-merge — keep worktree branch for manual review
synapse kill Auth -f --no-merge

# If auto-merge failed due to conflicts, the branch is preserved.
# Resolve manually:
git merge worktree-feature-auth
# ... fix conflicts ...
git commit
git branch -d worktree-feature-auth
```

## Synapse vs Claude Code Worktree

| Feature | Synapse `--worktree` | Claude Code `-- --worktree` |
|---------|---------------------|---------------------------|
| Directory | `.synapse/worktrees/` | `.claude/worktrees/` |
| Managed by | Synapse | Claude Code |
| Supported agents | All (Claude, Gemini, Codex, OpenCode, Copilot) | Claude Code only |
| Cleanup | On agent exit or `synapse kill` (uncommitted changes + commit detection) | On Claude Code session end |
| Flag position | Before `--` (Synapse flag) | After `--` (tool flag) |

!!! tip "Which to use?"
    Use Synapse's `--worktree` for multi-agent workflows. Use Claude Code's `-- --worktree` only when you need Claude Code-specific worktree behavior. Do not combine both — it would create nested worktrees.

### Merge Strategy Comparison

Claude Code and Synapse have fundamentally different merge strategies after worker completion.

| Aspect | Claude Code (`isolation: "worktree"`) | Synapse (`synapse kill`) |
|--------|----------------------------------------------|--------------------------|
| **Auto-merge** | No — preserves branch for human review | **Yes** — auto-merges on `synapse kill` by default |
| **Uncommitted changes** | Left in worktree; discarded on remove | Auto-committed as WIP (`wip: uncommitted changes from <name>`) |
| **On conflict** | Manual resolution (Git tools) | `git merge --abort` → branch preserved + warning. Parent agent resolves |
| **Design philosophy** | "Human decides" — review before merge | "Parent agent decides" — reliably integrate worker results |
| **Merge responsibility** | User (human) | Agent that runs kill (parent/manager) |
| **Opt-out** | N/A (no auto-merge) | `synapse kill <agent> --no-merge` |

```text
Claude Code:
  subagent done → changes? → YES → preserve branch → human reviews → manual merge
                           → NO  → auto-delete

Synapse:
  synapse kill → changes? → YES → auto-merge attempt → success → delete
                                                      → failure → preserve branch + parent resolves
                          → NO  → auto-delete
```

!!! tip "Choosing the right strategy"
    - **Claude Code worktree**: Review-oriented. Use when you want a human to review changes before merging.
    - **Synapse worktree**: Automation-oriented. Use when you want worker results reliably integrated in multi-agent workflows.
    - For high conflict risk, use `synapse file-safety lock` to lock files and prevent conflicts proactively.

## When To Use (and When Not To)

### Use worktree when:

| Situation | Why worktree helps |
|-----------|-------------------|
| **Multiple agents editing overlapping files** | Each agent gets an isolated copy — no file conflicts |
| **Working on an existing PR branch** (e.g., Renovate, Dependabot) | `--branch` lets you branch off the PR directly instead of `origin/main` |
| **Parallel review + implementation** | Reviewer reads code in isolation while implementer keeps editing |
| **Rate-limit distribution across models** | Spawn different model types in worktrees to avoid single-provider limits |

```bash
# Typical multi-agent workflow (worktree is the default for team start)
synapse team start claude gemini

# Fix a Renovate PR with a dedicated agent (--branch implies --worktree)
synapse spawn codex --branch renovate/major-eslint-monorepo

# Review in parallel while you keep working
synapse spawn gemini --worktree --name Reviewer --role "code reviewer"
synapse send Reviewer "Review the auth module changes" --notify
```

### Skip worktree when:

| Situation | Why worktree is unnecessary |
|-----------|---------------------------|
| **Single agent only** | No conflict risk — worktree adds overhead for no benefit |
| **Multiple agents touching different files** | File safety locks (`synapse file-safety lock`) are lighter weight |
| **Quick question or status check** | Use `synapse send` directly — no need for an isolated environment |
| **Read-only tasks** (review without edits) | Agents can read the same files safely |

!!! tip "Rule of thumb"
    If two agents might `git add` the same file at the same time, use worktree.
    Otherwise, file-safety locks or simple coordination is enough.

### Auto-Recommendation via `analyze_task`

The MCP `analyze_task` tool returns a `recommended_worktree` field in its response. When the task analysis determines that worktree isolation would be beneficial (e.g., multiple agents editing overlapping files), this field is set to `true`. Clients can use this signal to automatically enable `--worktree` when spawning agents.

### Branch management in worktrees

Worktree agents are **exempt from the branch-change restriction**. Since they operate
in an isolated directory, switching branches won't affect other agents or your main
checkout. Non-worktree agents still require user confirmation before changing branches.

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
