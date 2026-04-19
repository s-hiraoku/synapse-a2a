---
name: synapse-a2a
license: MIT
description: "Synapse A2A agent communication -- sending messages, spawning agents, delegating tasks, sharing memory, managing the LLM wiki, and coordinating file edits. Use this skill when: running synapse send/reply/broadcast/interrupt, spawning agents with synapse spawn or synapse team start, sharing knowledge with synapse memory, managing wiki pages with synapse wiki, locking files with synapse file-safety, checking agent status with synapse list/status, or orchestrating any multi-agent workflow. For AI/programmatic use, prefer synapse list --json, synapse status <target> --json, or the MCP list_agents tool instead of interactive synapse list."
---

# Synapse A2A Communication

Inter-agent communication framework via Google A2A Protocol.

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
| Attach files | `synapse send <target> "<msg>" --attach <file> --wait` |
| Saved agents | `synapse agents list` / `synapse spawn <agent_id>` |
| Post to Canvas | `synapse canvas post <format> "<body>" --title "<title>"` |
| Link preview | `synapse canvas link "<url>" --title "<title>"` |
| Post template | `synapse canvas briefing '<json>' --title "<title>"` |
| Post plan card | `synapse canvas plan '<json>' --title "<title>"` (Mermaid DAG + step list with status tracking) |
| Open Canvas | `synapse canvas open` (auto-starts server, opens browser) |
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
| **Canvas** | Visual dashboard for sharing rich cards and templates (briefing, comparison, dashboard, steps, slides, plan); cards downloadable as Markdown, JSON, CSV, or native format via browser button or `GET /api/cards/{card_id}/download` | `synapse canvas post/link/briefing/plan/open/list` |
| **Agent Control** | Browser-based agent management via Canvas `#/admin` view (select agents, send messages, view responses, double-click agent row to jump to terminal) | `synapse canvas open` → navigate to `#/admin` |
| **Workflow View** | Browser-based workflow management via Canvas `#/workflow` view (list workflows, inspect steps, trigger runs, monitor progress with live SSE updates; run history persisted to SQLite across restarts) | `synapse canvas open` → navigate to `#/workflow` |
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

**Default spawn policy:** When using `synapse spawn`, pass the underlying CLI's
tool-specific automation args after `--` so spawned agents can run unattended.
For most CLIs this is an approval-skip / auto-approve flag; for OpenCode use
`--agent build` to select the build agent profile and rely on OpenCode's
permission config for approval behavior.

Apply the same rule to `synapse team start`: include the appropriate forwarded
CLI args by default, and keep teams homogeneous when those args are
CLI-specific.

Common defaults:
- Claude Code: `synapse spawn claude --name <n> --role "<r>" -- --dangerously-skip-permissions`
- Gemini CLI: `synapse spawn gemini --name <n> --role "<r>" -- --approval-mode=yolo`
- Codex CLI: `synapse spawn codex --name <n> --role "<r>" -- --full-auto`
- OpenCode: `synapse spawn opencode --name <n> --role "<r>" -- --agent build` (selects the build agent profile; not a skip-approval flag)
- Copilot CLI: `synapse spawn copilot --name <n> --role "<r>" -- --allow-all-tools`
- Claude team: `synapse team start claude claude -- --dangerously-skip-permissions`
- Gemini team: `synapse team start gemini gemini -- --approval-mode=yolo`
- Codex team: `synapse team start codex codex -- --full-auto`
- OpenCode team: `synapse team start opencode opencode -- --agent build` (selects the build agent profile; permission prompts still depend on OpenCode config)
- Copilot team: `synapse team start copilot copilot -- --allow-all-tools`

| Condition | Action |
|-----------|--------|
| Existing READY agent can handle it | `synapse send` — reuse is faster (avoids startup overhead) |
| Need parallel execution | `synapse spawn` with `--worktree -- <tool-specific-automation-args>` for file isolation |
| Task needs a different model's strengths | Spawn a different type (Claude spawns Gemini, etc.) |
| User specified agent count | Follow exactly |
| Single focused subtask | Spawn 1 agent |
| N independent subtasks | Spawn N agents |

**Spawn lifecycle (preferred, one-command)**: `synapse spawn --task-file ... --task-timeout 600 --notify` → wait for A2A completion notification → evaluate result → `synapse kill <name> -f` → confirm in `synapse list --json`

**Legacy lifecycle (only when you need control between spawn and first task)**: spawn → poll `synapse list --json` or `synapse status <target> --json` for READY (allow **several minutes**; default 30s timeout is too short for most profiles) → `synapse send --notify` → evaluate → `synapse kill -f` → confirm cleanup.

> **⚠️ Common pitfall:** sending to an agent that is not yet READY either hangs at the HTTP layer or blocks on the internal readiness wait. Either use `synapse spawn --task-file` (preferred — it handles readiness for you), or explicitly confirm `"status": "READY"` before calling `synapse send`. Do not assume 30 seconds is enough — most profiles take 1-5 minutes.

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
