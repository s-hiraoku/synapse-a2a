# Spawning Reference

Spawning is sub-agent delegation. The parent spawns child agents to offload subtasks, preserving its own context window for the main task. The parent always owns the full lifecycle: **spawn, send task, evaluate result, kill**.

## Why Spawn

- **Context preservation** -- offloading a subtask keeps the parent's context window focused on the primary goal.
- **Parallel execution** -- independent subtasks run simultaneously, cutting total wall-clock time.
- **Specialist precision** -- a dedicated role (e.g., "test writer") produces higher-quality results than a generalist handling everything.

## When to Spawn vs. Subagent vs. Self

Call `analyze_task` first — it returns a `delegation_strategy` recommendation.

| Situation | Action | Why |
|-----------|--------|-----|
| ≤3 files, ≤100 lines, 1 directory | **Do it yourself** (strategy: "self") | No overhead, fastest path |
| 4-8 files, ≤2 dirs, Claude/Codex agent | **Use built-in subagent** (strategy: "subagent") | Same-process, context shared, no startup cost |
| Another agent is already running and READY | **`synapse send` to existing agent** | Reusing avoids startup cost, instruction injection, and readiness wait |
| 9+ files, 3+ dirs, or different model needed | **`synapse spawn` a new agent** (strategy: "spawn") | Offloads work, different model perspective, rate-limit distribution |
| Task has independent parallel subtasks | **`synapse team start` N agents** | Proper tile layout; each agent focuses on one subtask |

**Subagent vs. Synapse spawn:**
- Subagent (Claude Code Agent tool / Codex subprocess): same process, same model, shared context, low cost. Use for medium-scope work that doesn't need a different perspective.
- Synapse spawn: separate process, different model possible, file isolation via --worktree. Use for large scope, cross-model review, or rate-limit distribution.
- Only Claude Code and Codex have subagent capability. Gemini, OpenCode, Copilot always use Synapse spawn.

**Rule of thumb:** Spawn when delegating would be faster, more precise, or prevent your context from being consumed by a large subtask.

## How Many Agents

1. **User-specified count** -- follow it exactly (top priority).
2. **No user specification** -- the parent analyzes the task and decides:
   - Single focused subtask: 1 agent.
   - Independent parallel subtasks: N specialists (one per subtask).
   - The parent assigns a name and role to each spawned agent.

## Spawn Lifecycle

```
Parent receives task
  |
  +-- User-specified agent count? --> Use that count ----+
  |                                                      |
  +-- No specification? --> Parent decides count & roles-+
                                                         |
                                                         v
                                                   spawn child(ren)
                                                         |
                                                         v
                                                   send task  <-----------+
                                                         |                |
                                                         v                |
                                                   evaluate result        |
                                                         |                |
                                                   +- Sufficient? -> kill |
                                                   |                      |
                                                   +- Insufficient? ------+
```

### Basic Example — **use `--task-file` for the first task**

**⚠️ Reality check:** `synapse spawn` takes **several minutes** to reach `READY` for most profiles (CLI init + MCP bootstrap + PTY stabilization). Polling every second for 30 seconds is **too short** and will almost always time out. Let `synapse spawn` handle the readiness wait for you instead — it has a built-in `--task` / `--task-file` / `--task-timeout` combo that spawns the agent, waits for `READY`, and sends the first task in **one command**.

**✅ Recommended pattern** (use this):

```bash
# 1. Spawn and send the first task in one command.
#    --task-timeout gives spawn up to 600s (10 min) to wait for the agent
#    to register before sending the initial task. --notify returns control
#    immediately and delivers the completion via an async A2A message.
synapse spawn gemini \
    --name Tester \
    --role "test writer" \
    --task-file /tmp/tester-spec.md \
    --task-timeout 600 \
    --notify

# 2. Do other work. When Tester finishes, you receive an A2A notification
#    with the result. No polling needed.

# 3. Refine if the first reply is insufficient (agent retains its session
#    context, so just send a follow-up message — do NOT kill and re-spawn).
synapse send Tester "Add edge-case tests for expired tokens" --notify

# 4. Kill when done -- frees ports, memory, PTY sessions, and prevents orphaned agents
synapse kill Tester -f
```

**Why `--task-file` instead of inline `--task`:** the spec / first-task
prompt is often long, contains backticks or `$` that the shell would
expand, or has newlines. Put the prompt in a file and pass `--task-file`
— it avoids every shell-expansion trap.

**Send mode cheat sheet:**

| Flag | When to use |
|------|-------------|
| `--notify` (default) | Most cases. Parent returns immediately, gets an async A2A notification when the agent finishes. Parent can do other work in the meantime. |
| `--wait` | Only when the parent cannot make progress without the reply (e.g., the agent's answer is the next function argument). Blocks the parent until the agent replies. |
| `--silent` | Fire-and-forget. No completion notification. Use for side-effect-only instructions and one-way announcements. |

`$SYNAPSE_AGENT_ID` is set automatically by Synapse at startup (e.g., `synapse-claude-8100`). The `--from` flag is auto-detected from this env var, so you can usually omit it. In headless sessions, startup/setup logs are routed to the per-agent log file before PTY handoff, so a quiet terminal during spawn is expected.

### Legacy pattern (avoid — kept for reference)

If you cannot use `--task` (e.g., you need to send multiple messages
sequentially with very different readiness requirements), the old
two-step pattern still works, but **give it enough time**:

```bash
# 1. Spawn (returns immediately with agent_id)
synapse spawn gemini --name Tester --role "test writer"

# 2. Poll for readiness -- allow several MINUTES, not seconds.
#    Agents commonly take 60-300 seconds to reach READY.
elapsed=0
while ! synapse status Tester --json 2>/dev/null | grep -Eq '"status"[[:space:]]*:[[:space:]]*"READY"'; do
  sleep 5; elapsed=$((elapsed + 5))
  [ "$elapsed" -ge 600 ] && echo "ERROR: Tester not READY after ${elapsed}s" >&2 && exit 1
done

# 3. Send the task
synapse send Tester "Write unit tests for src/auth.py" --notify
```

**Common pitfall:** sending to an agent that is still initializing will
either hang at the `/tasks/send` HTTP call (PTY write blocks while the
CLI is starting up) or get blocked behind the internal "wait until READY"
logic. Always confirm `READY` before `synapse send`, or use `--task-file`
on `synapse spawn` which handles this for you.

### Evaluating Results

After receiving a `--wait` reply from a spawned agent:

1. **Read the reply content** -- does it address what you asked?
2. **Verify artifacts if needed** -- run `git diff`, `pytest`, or read modified files to confirm the work.
3. **Decide next step:**
   - Result is sufficient: `synapse kill <child> -f`
   - Result is insufficient: re-send with refined instructions (do NOT kill and re-spawn; the agent retains context from the previous attempt)

### Mandatory Cleanup

Killing spawned agents after completion frees ports, memory, and PTY sessions, and prevents orphaned agents from accidentally accepting future tasks.

```bash
synapse kill <spawned-agent-name> -f
synapse list --json  # Verify the agent is gone
```

## Auto-Approve (Automatic)

Since v0.17.16, `synapse spawn` and `synapse team start` **automatically inject**
the appropriate CLI permission bypass flag for each agent profile. You no longer
need to pass `-- <flags>` manually.

| CLI | Auto-injected Flag | Notes |
|-----|-------------------|-------|
| **Claude Code** | `--permission-mode=auto` | Anthropic's documented successor to the deprecated `--dangerously-skip-permissions`. Safety classifier active. Requires Max/Team/Enterprise/API plan + Sonnet 4.6 / Opus 4.6+. |
| **Gemini CLI** | `--approval-mode=yolo` | Unified `--approval-mode` form preferred over the legacy `--yolo` / `-y`. |
| **Codex CLI** | `--full-auto` | `-a on-request -s workspace-write` (sandboxed auto-approve). |
| **Copilot CLI** | `--allow-all` | `--yolo` is an alias and still recognized. |
| **OpenCode** | env `OPENCODE_DANGEROUSLY_SKIP_PERMISSIONS=true` | OpenCode has no CLI flag; uses env var. |

To disable auto-approve: `synapse spawn claude --no-auto-approve`

Runtime safety: if an agent hits a permission prompt despite the CLI flag,
the controller detects WAITING status and auto-sends the approval response.

For full details, see `docs/agent-permission-modes.md`.

## CLI and API

### CLI

```bash
# Single agent (auto-approve flags injected automatically)
synapse spawn claude                          # Spawn in new pane
synapse spawn gemini --port 8115              # Explicit port
synapse spawn claude --name Reviewer --role "code review" --skill-set dev-set
synapse spawn claude --worktree               # Spawn in isolated worktree
synapse spawn claude -w my-feature            # Named worktree
synapse spawn claude --no-auto-approve        # Disable auto-approve
synapse spawn sharp-checker                   # Spawn by saved Agent ID

# Spawn + send first task in ONE command (preferred for delegation)
synapse spawn codex \
    --name Fixer \
    --role "bug fixer" \
    --task-file /tmp/bug-spec.md \
    --task-timeout 600 \
    --notify

# Spawn + inline task (only for short prompts; prefer --task-file)
synapse spawn gemini --name Searcher --task "Search for TODO comments in src/"

# Spawn + task + worktree isolation (common for code-generation work)
synapse spawn codex \
    --name Feature \
    --worktree feature-auth \
    --branch main \
    --task-file /tmp/feature-spec.md \
    --task-timeout 900 \
    --notify

# Multiple agents — use team start for proper tile layout
synapse team start claude gemini codex        # Mixed team (each gets its own auto-approve flag)
synapse team start claude:Reviewer gemini:Searcher  # With names
synapse team start claude gemini --worktree   # Each in isolated worktree
synapse team start claude gemini --no-auto-approve  # Disable auto-approve for all
```

**Key options for the spawn + task combo:**

| Option | Purpose |
|--------|---------|
| `--task TASK` | Inline first-task prompt. Use for short one-liners. |
| `--task-file PATH` | Read the first-task prompt from a file. Preferred for long prompts, multi-line specs, or anything containing shell-special characters (`` ` ``, `$`, `"`). |
| `--task-timeout N` | Seconds to wait for the agent to reach READY before giving up on the initial task. **Default is 30s which is almost always too short.** Set 300-900 for real-world agents. |
| `--wait` / `--notify` / `--silent` | Same meaning as `synapse send`. `--notify` is default and correct for most delegation. |

### Spawn via API

Agents can spawn other agents programmatically via `POST /spawn`:

```jsonc
// Basic spawn
{"profile": "gemini", "name": "Helper", "skill_set": "dev-set", "tool_args": ["--approval-mode=yolo"]}

// With worktree isolation
{"profile": "gemini", "name": "Worker", "worktree": true}
{"profile": "claude", "name": "Worker", "worktree": "my-feature"}

// Claude with auto permission mode (was --dangerously-skip-permissions)
{"profile": "claude", "name": "Worker", "tool_args": ["--permission-mode=auto"]}

// Codex with auto-approve
{"profile": "codex", "name": "Coder", "tool_args": ["--full-auto"]}

// On failure: {"status": "failed", "reason": "..."}
// On success: {agent_id, port, terminal_used, status, worktree_path, worktree_branch, worktree_base_branch}
```

### Team Start

```bash
synapse team start claude gemini          # claude=current terminal, gemini=new pane
synapse team start claude gemini codex --layout horizontal
synapse team start claude gemini --all-new  # All agents in new panes
synapse team start claude gemini --worktree  # Each agent in its own worktree
synapse team start claude gemini codex -w my-feature  # Named prefix: my-feature-claude-0, etc.
synapse team start claude gemini --no-auto-approve  # Disable auto-approve
```

Team Start via API (`POST /team/start`):

```jsonc
{"agents": ["gemini", "codex"], "layout": "split"}
```

## Worktree Isolation

`--worktree` / `-w` is a **Synapse-level flag** that creates an isolated git worktree for each agent. It works for all agent types and is placed **before** `--` (not as a tool arg). Each worktree is created under `.synapse/worktrees/<name>/` with a branch named `worktree-<name>`.

### When to Use Worktrees

| Situation | Action |
|-----------|--------|
| Multiple agents may edit the same files | Use `--worktree` to avoid conflicts |
| Coordinator + Worker pattern (Worker edits code) | Worker gets `--worktree` |
| Read-only tasks (investigation, analysis, review) | Worktree not needed |
| Single agent working alone | Worktree not needed |

### Usage

```bash
# Auto-generated worktree name
synapse spawn claude --name Impl --role "implementer" --worktree
synapse spawn gemini --name Analyst --role "analyzer" -w

# Named worktree (creates .synapse/worktrees/feat-auth/ with branch worktree-feat-auth)
synapse spawn claude --name Impl --role "implementer" --worktree feat-auth

# Team start with worktree per agent
synapse team start claude gemini --worktree
synapse team start claude gemini codex -w my-feature
```

### Indicators and Environment

Agents running in worktrees show a `[WT]` prefix in the WORKING_DIR column of `synapse list`.

Environment variables set automatically for worktree agents:

| Variable | Description |
|----------|-------------|
| `SYNAPSE_WORKTREE_PATH` | Absolute path to the worktree directory |
| `SYNAPSE_WORKTREE_BRANCH` | Branch name of the worktree |
| `SYNAPSE_WORKTREE_BASE_BRANCH` | Base branch the worktree was created from (e.g., `origin/main`). Used for change detection during cleanup. Determined via 3-step fallback: `git symbolic-ref` -> `origin/main` -> `HEAD`. |

### Caveats

- `--worktree` is a Synapse flag -- place it **before** `--`. Placing it after `--` triggers a warning because it would be passed to the underlying CLI as a tool arg instead.
- `.gitignore`-listed files (`.env`, `.venv/`, `node_modules/`) are **not copied** to the worktree. Run `uv sync`, `npm install`, or copy `.env` manually if needed.
- On exit: worktrees with no uncommitted changes and no new commits (vs. the base branch) are auto-deleted; worktrees with changes prompt to keep or remove.
- `synapse kill` also handles worktree cleanup for killed agents.
- Consider adding `.synapse/worktrees/` to your `.gitignore` to prevent untracked worktree files from cluttering `git status`.

## Spawn Zone Tiling (tmux)

`synapse spawn` uses `layout="auto"` by default. In tmux this enables **spawn zone tiling** — spawned panes are tracked and subsequent splits target the largest pane in the zone, producing balanced layouts automatically.

**How it works:**

1. **First spawn** (no existing spawn zone): splits the current pane horizontally (`-h`), creating a side-by-side layout.
2. **Subsequent spawns**: Synapse queries all panes in the spawn zone, finds the largest one (by area = width x height), and splits it. The split direction is chosen automatically (horizontal if the pane is wider than tall, vertical otherwise).
3. **Tracking**: Spawned pane IDs are stored in `SYNAPSE_SPAWN_PANES` (comma-separated) in the **tmux session environment** (`tmux set-environment` / `tmux show-environment`). This persists across CLI invocations within the same tmux session.

**Result:** Spawning 1, 2, or 4 agents produces evenly tiled layouts without manual `--layout` flags.

Other terminals (iTerm2, Ghostty, zellij) have their own auto-alternation logic but do not use the spawn zone mechanism.

## Technical Notes

- **Headless mode:** `synapse spawn` and `synapse team start` always add `--no-setup --headless`, skipping interactive setup while keeping the A2A server and initial instructions active.
- **Readiness:** After spawning, Synapse waits for the agent to register and warns with concrete `synapse send` examples if not yet ready. At the HTTP level, a Readiness Gate blocks `/tasks/send` until the agent finishes initialization (returns HTTP 503 + `Retry-After: 5` if not ready within 30s).
- **Pane titles (tmux):** Each spawned tmux pane is labelled with `synapse(<profile>)` or `synapse(<profile>:<name>)` via `tmux select-pane -T`. This makes it easy to identify agents when pane border status is enabled (`tmux set -g pane-border-status top`).
- **Pane auto-close:** Spawned panes close automatically when the agent process terminates (tmux, zellij, iTerm2, Terminal.app, Ghostty).
- **Known limitation ([#237](https://github.com/s-hiraoku/synapse-a2a/issues/237)):** Spawned agents cannot use `synapse reply` (PTY injection does not register sender info). Use `synapse send <target> "message"` for bidirectional communication (`--from` is auto-detected).
