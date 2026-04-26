---
name: synapse-a2a
license: MIT
description: "Synapse A2A agent communication -- sending messages, spawning agents, delegating tasks, sharing memory, managing the LLM wiki, and coordinating file edits. Use this skill when: running synapse send/reply/broadcast/interrupt, spawning agents with synapse spawn or synapse team start, sharing knowledge with synapse memory, managing wiki pages with synapse wiki, locking files with synapse file-safety, checking agent status with synapse list/status, or orchestrating any multi-agent workflow. For AI/programmatic use, prefer synapse list --json, synapse status <target> --json, or the MCP list_agents tool instead of interactive synapse list."
---

# Synapse A2A Communication

Inter-agent communication framework via Google A2A Protocol.

## Worktree Discipline (subagents, read this first)

> **NEVER `cd` into `.synapse/worktrees/<name>/` directories.**
>
> Subagents (Claude Code Agent tool, Codex subprocess, and any other
> sub-process driven by the parent session) inherit a persistent shell
> from the parent. A stray `cd` into a worktree leaks out of the subagent
> turn and silently corrupts the parent's working directory — `git status`,
> `git diff`, and even `git commit` then land on the wrong worktree, which
> wastes debugging time and can put commits on the wrong branch.
>
> Rules for working with `.synapse/worktrees/`:
>
> - Do **not** `cd` into a worktree, ever. Stay in the original working
>   directory for the entire session.
> - Read and write files inside a worktree using **absolute paths only**
>   (for example `Read /Volumes/.../.synapse/worktrees/foo/src/bar.py`,
>   not `cd .synapse/worktrees/foo && cat src/bar.py`).
> - Run `git` against a worktree with `git -C /abs/path/to/worktree ...`
>   instead of changing directory.
> - Worktrees are managed by Synapse (`synapse spawn --worktree`,
>   `synapse team start --worktree`). Treat them as read/write data
>   surfaces, not as places to live.
>
> If you need to operate from inside a worktree (e.g. running `pytest`
> there), spawn a dedicated agent for it with `synapse spawn --worktree`
> rather than changing the parent shell's directory.


## Quick Reference

| Task | Command |
|------|---------|
| List agents | `synapse list` for humans (auto-refresh, interactive: arrows/1-9 select, Enter jump, k kill, / filter). For AI/scripts use `synapse list --json`, `synapse list --plain`, or MCP `list_agents` |
| Agent detail | `synapse status <target> [--json]` |
| Send message | `synapse send <target> "<msg>"` (default: `--notify`; `--from` auto-detected) |
| Broadcast | `synapse broadcast "<msg>"` |
| Wait for reply | `synapse send <target> "<msg>" --wait` |
| Fire-and-forget | `synapse send <target> "<msg>" --silent` |
| Reply | `synapse reply "<response>"` |
| Reply to specific | `synapse reply "<response>" --to <sender_id>` |
| Reply with failure | `synapse reply --fail "<reason>"` |
| Interrupt (priority 4) | `synapse interrupt <target> "<msg>"` |
| Spawn agent | `synapse spawn <type> --name <n> --role "<r>" -- <tool-specific-automation-args>` |
| **Spawn + send first task** (preferred for delegation) | `synapse spawn <type> --name <n> --role "<r>" --task-file <path> --task-timeout 600 --notify` |
| Spawn with worktree | `synapse spawn <type> --worktree --name <n> --role "<r>" -- <tool-specific-automation-args>` |
| Team start | `synapse team start <homogeneous-profiles...> [--worktree] -- <tool-specific-automation-args>` |
| Approve plan | `synapse approve <id>` |
| Reject plan | `synapse reject <id> --reason "<feedback>"` |
| Save knowledge | `synapse memory save <key> "<content>" --tags <t> --notify` |
| Search knowledge | `synapse memory search "<query>"` |
| Lock file | `synapse file-safety lock <file> <agent_id> --intent "..."` |
| Check locks | `synapse file-safety locks` |
| Task history | `synapse history list --agent <name>` |
| Kill agent | `synapse kill <name> -f` |
| Cleanup orphans | `synapse cleanup --dry-run` (list); `synapse cleanup -f` (kill all orphans whose parent crashed/cleared) |
| Attach files | `synapse send <target> "<msg>" --attach <file> --wait` |
| Saved agents | `synapse agents list` / `synapse spawn <agent_id>` |
| Post to Canvas | `synapse canvas post <format> "<body>" --title "<title>"` |
| Link preview | `synapse canvas link "<url>" --title "<title>"` |
| Post template | `synapse canvas briefing '<json>' --title "<title>"` |
| Post plan card | `synapse canvas plan '<json>' --title "<title>"` (Mermaid DAG + step list with status tracking) |
| Open Canvas | `synapse canvas open` (auto-starts server, opens browser) |
| Restart Canvas | `synapse canvas restart` (stop + start; use when `canvas status` reports `⚠ STALE` after upgrade) |
| Sync workflow skills | `synapse workflow sync` (regenerate skills from workflow YAMLs, remove orphans) |
| Run workflow (auto-spawn) | `synapse workflow run <name> --auto-spawn` (spawn missing agents on the fly) |
| Multi-agent patterns | `synapse map init/list/show/run/status/stop` (built-in: `generator-verifier`, `orchestrator-subagent`, `agent-teams`, `message-bus`, `shared-state`) |
| Wiki ingest | `synapse wiki ingest <source> [--scope project\|global]` (ingest a source file into the wiki) |
| Wiki query | `synapse wiki query "<question>" [--scope project\|global]` (search wiki pages) |
| Wiki lint | `synapse wiki lint [--scope project\|global]` (validate wiki consistency) |
| Wiki status | `synapse wiki status [--scope project\|global]` (show wiki index stats) |

## Collaboration Decision Framework

Evaluate collaboration opportunities before starting work:

| Situation | Action |
|-----------|--------|
| Small task within your role | Do it yourself |
| Task outside your role, READY agent exists | Delegate: `synapse send --notify` or `--silent` |
| No suitable agent exists, need to delegate a task | Spawn + task in one command: `synapse spawn <type> --name <n> --role "<r>" --task-file <spec.md> --task-timeout 600 --notify`. This spawns, waits for READY, and sends the first task — no manual readiness polling needed. |
| Need a bare agent (no initial task) | `synapse spawn <type> --name <n> --role "<r>"` (send tasks later via `synapse send`) |
| Stuck or need expertise | Ask: `synapse send <target> "<question>" --wait` |
| Completed a milestone | Report: `synapse send <manager> "<summary>" --silent` |
| Discovered a pattern | Share: `synapse memory save <key> "<pattern>" --tags ... --notify` |

**Recommended Collaboration Gate** (3+ phases OR 10+ file changes):
Consider these steps before diving into large work:
1. `synapse list --json` or MCP `list_agents` — check available agents
2. `synapse memory search "<topic>"` — check if someone already solved this
3. Build Agent Assignment Plan (Phase / Agent / Rationale) when delegation is beneficial
4. Spawn specialists if needed (prefer different model types for diversity)

Skip this gate for small/medium tasks where the overhead exceeds the benefit.

## Use Synapse Features Actively

| Feature | Why It Matters | Commands |
|---------|---------------|----------|
| **Shared Memory** | Collective knowledge survives agent restarts | `synapse memory save/search/list` |
| **File Safety** | Locking prevents data loss when two agents edit the same file -- skip inside worktrees (`SYNAPSE_WORKTREE_PATH`) | `synapse file-safety lock/unlock/locks` |
| **Worktree** | File isolation eliminates merge conflicts in parallel editing | `synapse spawn --worktree` |
| **Broadcast** | Team-wide announcements reach all agents instantly | `synapse broadcast "<msg>"` |
| **History** | Audit trail tracks what happened and when | `synapse history list/show/stats` |
| **Plan Approval** | Gated execution ensures quality before action | `synapse approve/reject` |
| **Canvas** | Visual dashboard for sharing rich cards and templates (briefing, comparison, dashboard, steps, slides, plan); cards downloadable as Markdown, JSON, CSV, or native format via browser button or `GET /api/cards/{card_id}/download` | `synapse canvas post/link/briefing/plan/open/list/restart` |
| **Agent Control** | Browser-based agent management via Canvas `#/admin` view (select agents, send messages, view responses, double-click agent row to jump to terminal) | `synapse canvas open` → navigate to `#/admin` |
| **Workflow View** | Browser-based workflow management via Canvas `#/workflow` view (list workflows, inspect steps, trigger runs, monitor progress with live SSE updates; run history persisted to SQLite across restarts) | `synapse canvas open` → navigate to `#/workflow` |
| **Harnesses View** | Browser-based browser for agent harness resources at Canvas `#/harnesses` — sub-views `#/harnesses/skills` (SKILL.md inventory across user/project/synapse/plugin scopes, scanned per active project root) and `#/harnesses/mcp` (MCP server configs from project `.mcp.json` per active root, plus user-scope: Claude Code `~/.claude.json`, Codex `~/.codex/config.toml`, Gemini `~/.gemini/settings.json`, OpenCode `~/.config/opencode/opencode.json`, and Claude Desktop config) | `synapse canvas open` → navigate to `#/harnesses` |
| **Plan Cards** | Mermaid DAG + step list with dependency visualization | `synapse canvas plan` |
| **LLM Wiki** | Structured knowledge base for ingesting, querying, and validating project/global docs | `synapse wiki ingest/query/lint/status` |
| **Smart Suggest** | MCP tool that analyzes prompts and suggests team/task splits for large work | MCP tool: `analyze_task` |
| **Proactive Mode** | Task-size-based feature usage guide (`SYNAPSE_PROACTIVE_MODE_ENABLED=true`) | See `references/features.md` |
| **MCP Bootstrap** | Distribute instructions via MCP resources for compatible clients (opt-in, including Copilot via tools-only). MCP tools: `bootstrap_agent`, `list_agents`, `analyze_task` | `synapse mcp serve` / `python -m synapse.mcp` |

### When to Use Canvas

Use Canvas when the output benefits from visual structure or will be referenced later:

- **Use Canvas for:** diagrams, comparison tables, multi-step plans, design docs, results with rich formatting
- **Skip Canvas for:** simple completion reports, single-file changes, quick status updates (use broadcast or reply instead)

Template selection guide:
- `briefing` — structured reports, status updates, release summaries
- `comparison` — before/after, option trade-offs, review diffs
- `steps` — plans, migration sequences, execution checklists
- `slides` — walkthroughs, demos, page-by-page narratives
- `dashboard` — multi-widget operational snapshots, compact status boards
- `plan` — task DAGs with Mermaid visualization and step tracking

Use raw `synapse canvas post <format>` for single blocks; templates for multi-section content.

## Spawning Decision Table

> **⚠️ Same-model rule — try subagents first.** When a Claude Code agent needs
> another claude (or a codex agent needs another codex), use the in-process
> subagent (`Agent` / `Task` tool for Claude, subprocess for Codex) **before**
> reaching for `synapse spawn`. Spawning the same model on the same account
> shares the rate-limit window — it doubles consumption against the same quota
> instead of distributing it. Reserve same-model `synapse spawn` for cases
> where the helper must outlive the parent session, needs file isolation that
> subagents can't provide, or holds a distinct long-running role.
>
> `synapse spawn` is the right tool for **cross-model** delegation
> (Claude → codex / gemini), agents that lack subagent support
> (Gemini / OpenCode / Copilot), or persistent multi-task helpers.

**Default spawn policy:** When using `synapse spawn`, pass the underlying CLI's
tool-specific automation args after `--` so spawned agents can run unattended.
For most CLIs this is an approval-skip / auto-approve flag; for OpenCode use
`--agent build` to select the build agent profile and rely on OpenCode's
permission config for approval behavior.

Apply the same rule to `synapse team start`: include the appropriate forwarded
CLI args by default, and keep teams homogeneous when those args are
CLI-specific.

Common defaults (Synapse already injects these automatically — pass `--no-auto-approve`
to opt out):
- Claude Code: `synapse spawn claude --name <n> --role "<r>" -- --permission-mode=auto`
- Gemini CLI: `synapse spawn gemini --name <n> --role "<r>" -- --approval-mode=yolo`
- Codex CLI: `synapse spawn codex --name <n> --role "<r>" -- --full-auto`
- OpenCode: `synapse spawn opencode --name <n> --role "<r>" -- --agent build` (selects the build agent profile; not a skip-approval flag)
- Copilot CLI: `synapse spawn copilot --name <n> --role "<r>" -- --allow-all`
- Claude team: `synapse team start claude claude -- --permission-mode=auto`
- Gemini team: `synapse team start gemini gemini -- --approval-mode=yolo`
- Codex team: `synapse team start codex codex -- --full-auto`
- OpenCode team: `synapse team start opencode opencode -- --agent build` (selects the build agent profile; permission prompts still depend on OpenCode config)
- Copilot team: `synapse team start copilot copilot -- --allow-all`

> **2026-04 migration:** Anthropic deprecated `--dangerously-skip-permissions`
> in favor of `--permission-mode=auto` (safety classifier instead of disabling
> all checks). Gemini similarly recommends `--approval-mode=yolo` over the
> legacy `--yolo` / `-y` short forms. Synapse now injects the new flags by
> default; the legacy forms still work and remain in each profile's
> `alternative_flags`.

| Condition | Action |
|-----------|--------|
| Existing READY agent can handle it | `synapse send` — reuse is faster (avoids startup overhead) |
| **Same-model helper needed (Claude → claude, Codex → codex)** | **Use the in-process subagent first** (`Agent`/`Task` tool for Claude, subprocess for Codex). `synapse spawn` same-model shares the rate-limit window. |
| Need parallel execution | `synapse spawn` with `--worktree -- <tool-specific-automation-args>` for file isolation (cross-model preferred) |
| Task needs a different model's strengths | `synapse spawn` a different type (Claude spawns Gemini / Codex, etc.) |
| User specified agent count | Follow exactly |
| Single focused subtask | Subagent (same model) or `synapse spawn` (cross model) |
| N independent subtasks | Subagents for same-model fan-out, `synapse spawn` for cross-model |

**Spawn lifecycle (preferred, one-command)**: `synapse spawn --task-file ... --task-timeout 600 --notify` → wait for A2A completion notification → evaluate result → `synapse kill <name> -f` → confirm in `synapse list --json`

**Legacy lifecycle (only when you need control between spawn and first task)**: spawn → poll `synapse list --json` or `synapse status <target> --json` for READY (allow **several minutes**; default 30s timeout is too short for most profiles) → `synapse send --notify` → evaluate → `synapse kill -f` → confirm cleanup.

> **⚠️ Common pitfall:** sending to an agent that is not yet READY either hangs at the HTTP layer or blocks on the internal readiness wait. Either use `synapse spawn --task-file` (preferred — it handles readiness for you), or explicitly confirm `"status": "READY"` before calling `synapse send`. Do not assume 30 seconds is enough — most profiles take 1-5 minutes.

**Agent status set** (`synapse list --json` `.status`):

| Status | Meaning | Action |
|--------|---------|--------|
| `READY` | Idle, can accept new work | `synapse send` |
| `PROCESSING` | Actively working a task | Wait, or `synapse interrupt` if stuck |
| `WAITING` | Awaiting a permission/approval prompt | `synapse approve` / `synapse reject` |
| `WAITING_FOR_INPUT` | Task is paused asking for non-permission input (#538) | `synapse reply <task_id>` with the answer |
| `RATE_LIMITED` | Last task failed due to LLM provider rate limit (#561) | Wait for the provider window to reset, then re-send |
| `DONE` | Task complete; demotes to READY after ~10s | Read result, then proceed |
| `SHUTTING_DOWN` | Agent is exiting | Do not send |

Killing spawned agents after completion frees ports, memory, and PTY sessions,
and prevents orphaned agents from accidentally accepting future tasks.

```bash
# Preferred: one-command spawn + delegate (handles readiness wait internally)
synapse spawn gemini \
    --name Tester \
    --role "test writer" \
    --task-file /tmp/test-spec.md \
    --task-timeout 600 \
    --notify
# (do other work; receive async A2A notification when Tester finishes)
# Evaluate result, then cleanup
synapse kill Tester -f
synapse list --json                       # Verify cleanup (AI-safe)
```

If `synapse kill` fails or the agent still appears in `synapse list --json`, retry with `-f`,
check the agent status/logs, and report the cleanup failure instead of leaving an
orphaned agent behind.

## Response Mode Guide

Choose based on whether you need the result:

| Mode | Flag | Use When |
|------|------|----------|
| **Wait** | `--wait` | You need the answer before continuing (questions, reviews) |
| **Notify** | `--notify` (default) | Async — you'll be notified on completion |
| **Silent** | `--silent` | Fire-and-forget delegation (no response needed; sender history still updates best-effort on completion) |

## Worker Agent Guide

When you receive a task from a manager:

### On Task Receipt
1. Start work immediately (`[REPLY EXPECTED]` requires a reply; otherwise no reply needed)
2. Check shared knowledge: `synapse memory search "<task topic>"`
3. Lock files before editing (**skip if SYNAPSE_WORKTREE_PATH is set**): `synapse file-safety lock <file> $SYNAPSE_AGENT_ID`

### During Work
- Report progress if task takes >5 minutes: `synapse send <manager> "Progress: <update>" --silent`
- Report blockers immediately: `synapse send <manager> "<question>" --wait`
- Save findings: `synapse memory save <key> "<finding>" --tags <topic>`
- You can delegate subtasks too — spawn helpers (prefer different model types)
- Always clean up agents you spawn: `synapse kill <name> -f`

### On Completion
1. Report to manager: `synapse send <manager> "Done: <summary>" --silent`

### On Failure
1. Report details: `synapse send <manager> "Failed: <error details>" --silent`

## Related Skills

| Skill | Purpose |
|-------|---------|
| `synapse-manager` | Multi-agent orchestration workflow (delegation, monitoring, verification) |
| `synapse-reinst` | Re-inject instructions after `/clear` or context reset |

## References

For detailed information, consult these reference files:

| Reference | Contents |
|-----------|----------|
| `references/commands.md` | Full CLI command documentation with all options |
| `references/api.md` | A2A endpoints, readiness gate, error handling |
| `references/examples.md` | Multi-agent workflow examples and patterns |
| `references/file-safety.md` | File locking workflow and commands |
| `references/messaging.md` | Sending, replying, priorities, status states, interactive controls |
| `references/spawning.md` | Spawn lifecycle, patterns, worktree, permissions, API |
| `references/collaboration.md` | Agent naming, external agents, auth, resume, path overrides |
| `references/features.md` | Sessions, workflows, saved agents, tokens, skills, settings, Canvas |
