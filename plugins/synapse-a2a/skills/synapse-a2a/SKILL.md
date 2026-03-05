---
name: synapse-a2a
description: This skill provides comprehensive guidance for inter-agent communication using the Synapse A2A framework. Use this skill when sending messages to other agents via synapse send/reply commands, understanding priority levels, handling A2A protocol operations, managing task history, configuring settings, or using File Safety features for multi-agent coordination. Automatically triggered when agent communication, A2A protocol tasks, history operations, or file safety operations are detected.
---

# Synapse A2A Communication

Inter-agent communication framework via Google A2A Protocol.

## Quick Reference

| Task | Command |
|------|---------|
| List agents (Rich TUI) | `synapse list` (event-driven refresh via file watcher with 10s fallback, ↑/↓ or 1-9 to select, Enter/j jump, k kill, / filter by TYPE/NAME/WORKING_DIR) |
| Agent detail status | `synapse status <target> [--json]` (agent info, current task with elapsed time, recent messages, file locks, task board) |
| Send message | `synapse send <target> "<message>"` (default: `--notify`; `--from` auto-detected; warns if target is in a different working directory; use `--force` to bypass) |
| Broadcast to cwd agents | `synapse broadcast "<message>"` (default: `--notify`) |
| Synchronous wait | `synapse send <target> "<message>" --wait` |
| Async notification | `synapse send <target> "<message>" --notify` |
| Fire-and-forget | `synapse send <target> "<message>" --silent` |
| Reply to last message | `synapse reply "<response>"` |
| Reply to specific sender | `synapse reply "<response>" --to <sender_id>` |
| List reply targets | `synapse reply --list-targets` |
| Soft interrupt (priority 4) | `synapse interrupt <target> "<message>" [--from <sender>]` (same `--force` flag available) |
| Emergency stop | `synapse send <target> "STOP" --priority 5` |
| Stop agent | `synapse stop <profile\|id>` |
| Kill agent (graceful) | `synapse kill <target>` (shutdown request → SIGTERM → SIGKILL, 30s budget) |
| Kill agent (force) | `synapse kill <target> -f` (immediate SIGKILL) |
| Jump to terminal | `synapse jump <target>` |
| Rename agent | `synapse rename <target> --name <name> --role <role>` |
| List saved agents | `synapse agents list` |
| Show saved agent | `synapse agents show <id-or-name>` |
| Add saved agent | `synapse agents add <id> --name <name> --profile <profile> [--role <role>] [--skill-set <set>] [--scope project\|user]` |
| Delete saved agent | `synapse agents delete <id-or-name>` |
| Check file locks | `synapse file-safety locks` |
| View history | `synapse history list` |
| History stats (with token usage) | `synapse history stats [--agent <name>]` |
| Initialize settings | `synapse init` |
| Edit settings (TUI) | `synapse config` (includes List Display for column config) |
| View settings | `synapse config show [--scope user\|project]` |
| Reset settings | `synapse reset [--scope user\|project\|both]` |
| Show instructions | `synapse instructions show <agent>` |
| Send instructions | `synapse instructions send <agent> [--preview]` |
| View logs | `synapse logs <profile> [-f] [-n <lines>]` |
| Add external agent | `synapse external add <url> [--alias <name>]` |
| List external agents | `synapse external list` |
| External agent info | `synapse external info <alias>` |
| Send to external | `synapse external send <alias> "<message>" [--wait]` |
| Remove external agent | `synapse external remove <alias>` |
| Skill Manager (TUI) | `synapse skills` |
| List skills | `synapse skills list [--scope synapse\|user\|project\|plugin]` |
| Show skill detail | `synapse skills show <name>` |
| Deploy skill | `synapse skills deploy <name> --agent claude,codex --scope user` |
| Import skill | `synapse skills import <name>` |
| Install from repo | `synapse skills add <repo>` |
| Create skill | `synapse skills create` |
| Delete skill | `synapse skills delete <name> [--force]` |
| Move skill | `synapse skills move <name> --to <scope>` |
| List skill sets | `synapse skills set list` |
| Show skill set detail | `synapse skills set show <name>` |
| Trace task | `synapse trace <task_id>` |
| Save memory | `synapse memory save <key> "<content>" [--tags tag1,tag2] [--notify]` |
| List memories | `synapse memory list [--author <id>] [--tags <tags>] [--limit N]` |
| Show memory | `synapse memory show <id_or_key>` |
| Search memories | `synapse memory search <query>` (default limit: 100) |
| Delete memory | `synapse memory delete <id_or_key> [--force]` |
| Memory stats | `synapse memory stats` |
| Save session | `synapse session save <name> [--project \| --user \| --workdir DIR]` |
| List sessions | `synapse session list [--project \| --user \| --workdir DIR]` |
| Show session | `synapse session show <name> [--project \| --user \| --workdir DIR]` |
| Restore session | `synapse session restore <name> [--project \| --user \| --workdir DIR] [--worktree] [--resume] [-- tool_args...]` |
| Delete session | `synapse session delete <name> [--project \| --user \| --workdir DIR] [--force]` |
| Create workflow | `synapse workflow create <name> [--project \| --user] [--force]` |
| List workflows | `synapse workflow list [--project \| --user]` |
| Show workflow | `synapse workflow show <name> [--project \| --user]` |
| Run workflow | `synapse workflow run <name> [--project \| --user] [--dry-run] [--continue-on-error]` |
| Delete workflow | `synapse workflow delete <name> [--project \| --user] [--force]` |
| Auth setup | `synapse auth setup` (generate keys + instructions) |
| Generate API key | `synapse auth generate-key [-n <count>] [-e]` |
| List task board | `synapse tasks list [--status pending] [--agent claude]` |
| Create task | `synapse tasks create "subject" [-d "desc"] [--priority N] [--blocked-by id]` |
| Assign task | `synapse tasks assign <task_id> <agent>` |
| Complete task | `synapse tasks complete <task_id>` |
| Report task failure | `synapse tasks fail <id> [--reason "reason"]` |
| Reopen task | `synapse tasks reopen <id>` |
| Approve plan | `synapse approve <task_id>` |
| Reject plan | `synapse reject <task_id> --reason "reason"` |
| Start team (CLI) | `synapse team start <spec...> [--layout ...] [--all-new] [--worktree]` (1st=handoff, rest=new panes; `--all-new` for all new) |
| Start team (API) | `POST /team/start` with `{"agents": [...], "layout": "split"}` |
| Spawn agent | `synapse spawn <profile\|saved-agent> [--port] [--name] [--role] [--skill-set] [--terminal] [--worktree]` |
| Start with saved agent | `synapse claude --agent <id> [--role "override"]` (short: `-A`; CLI args override saved values) |
| Role from file | `synapse claude --role "@./path/to/role.md"` (`@` prefix reads file content as role) |
| Delegate mode | `synapse claude --delegate-mode [--name manager]` |
| Version info | `synapse --version` |
| Check CI status | `/check-ci` (CI checks + merge conflicts + CodeRabbit review) |
| Fix CI failures | `/fix-ci` (auto-diagnose and fix GitHub Actions failures) |
| Fix merge conflicts | `/fix-conflict` (auto-resolve PR merge conflicts) |
| Fix CodeRabbit review | `/fix-review` (auto-address CodeRabbit inline comments) |

**Tip:** Run `synapse list` before sending to verify the target agent is READY.

## Collaboration Patterns

### When You Receive a Task
1. If `[REPLY EXPECTED]`, complete the work and reply with `synapse reply`
2. Execute the task
3. Report completion: `synapse send <sender> "Done: <summary>" --silent`

### When You Need Help from Other Agents
1. Run `synapse list` to check available agents (prefer same WORKING_DIR)
2. Run `synapse memory search "<topic>"` to check shared knowledge
3. If no suitable agent exists, spawn one: `synapse spawn <profile> --name <name> --role "<role>"`
   - **Cross-model preference**: Spawn a different model type than yourself for diverse perspectives
4. Send request: `synapse send <target> "<specific request>" --wait`

### When You Complete a Large Task
1. Save knowledge: `synapse memory save <key> "<what you learned>" --tags <topic>`
2. Notify stakeholders: `synapse send <requester> "Completed: <summary>" --silent`
3. Check task board: `synapse tasks list --status pending`

### When You Are Stuck
1. Search shared knowledge: `synapse memory search "<problem>"`
2. If a manager exists, ask them: `synapse send <manager> "<specific question>" --wait`
3. Otherwise, ask a teammate: `synapse send <agent> "<specific question>" --wait`
4. If no agents are available, spawn a specialist: `synapse spawn <profile> --name <name> --role "<role>"`

### Worker Autonomy — You Can Delegate Too
Even if you are a worker agent (not a manager), you should proactively:
- **Spawn helpers** for independent subtasks (prefer different model types for diversity)
- **Request reviews** from other agents (different models catch different issues)
- **Delegate out-of-scope work** instead of doing everything yourself
- **Kill agents you spawn** when their work is done: `synapse kill <name> -f`

## Use Synapse Features Actively

Synapse provides powerful coordination tools. Use them proactively — don't just communicate via `send`/`reply`.

### Task Board — Structure Your Work
Use the shared task board for visibility and tracking, not just ad-hoc messages:
```bash
synapse tasks create "Write unit tests for auth module" -d "Cover login, logout, token refresh" --priority 4
synapse tasks list --status pending          # Check what needs doing
synapse tasks assign <id> <agent>            # Claim or assign work
synapse tasks complete <id>                  # Mark done
synapse tasks fail <id> --reason "..."       # Report failures transparently
```

### Shared Memory — Build Collective Knowledge
Save discoveries so the entire team benefits, not just you:
```bash
synapse memory save <key> "<insight>" --tags <topic> --notify   # --notify tells other agents
synapse memory search "<topic>"              # Check before reinventing the wheel
synapse memory list --tags architecture      # Browse by topic
```

### File Safety — Prevent Conflicts
Lock files before editing in multi-agent setups:
```bash
synapse file-safety lock <file> $SYNAPSE_AGENT_ID
synapse file-safety unlock <file> $SYNAPSE_AGENT_ID
synapse file-safety locks                    # Check who is editing what
```

### Worktree Isolation — Safe Parallel Edits
When multiple agents edit files, use worktrees to avoid conflicts:
```bash
synapse spawn claude --worktree --name Impl --role "implementation"
synapse spawn gemini -w review --name Reviewer --role "code review"
```

### Broadcast — Team-Wide Communication
Use broadcast for announcements that affect everyone:
```bash
synapse broadcast "Status check" --priority 4    # Ask all agents for status
synapse broadcast "Build passed" --silent         # Inform all agents
```

### History & Tracing — Audit and Learn
Review past work and trace task execution:
```bash
synapse history list --agent <name>          # What did this agent do?
synapse history stats                        # Token usage overview
synapse trace <task_id>                      # Full audit trail
```

### Spawn — Scale the Team Dynamically
Don't work alone when you can parallelize. Prefer spawning a different model type to distribute
token usage across providers and avoid rate limits.
```bash
synapse spawn gemini --name Tester --role "test writer"     # Spawn a specialist (different model)
synapse spawn codex -w --name Impl --role "implementation"  # Spawn with worktree isolation
```

**CLEANUP IS MANDATORY**: Always kill agents you spawned after their work is complete.
Leaving orphaned agents wastes resources and can cause conflicts.
```bash
synapse kill Tester -f
synapse kill Impl -f
```

## Sending Messages (Recommended)

**Use `synapse send` command for inter-agent communication.** This works reliably from any environment including sandboxed agents.

```bash
synapse send gemini "Please review this code" --notify
synapse send claude "What is the status?" --wait
synapse send codex-8120 "Fix this bug" --silent --priority 3
```

**Important:**
- `--from` is **auto-detected** from the `SYNAPSE_AGENT_ID` environment variable (set by Synapse at startup). You can omit it in most environments.
- If auto-detection fails (e.g., sandboxed environments like Codex), specify explicitly: `--from $SYNAPSE_AGENT_ID`.
- When using `--from`, always use the **Runtime ID** format (`synapse-<type>-<port>`). Do NOT use custom names or agent types.
- By default, use `--notify` to get async notification on completion.
- Use `--wait` for synchronous blocking if you need an immediate reply.
- Use `--silent` for purely informational notifications or fire-and-forget tasks.

**Target Resolution (Matching Priority):**
1. Custom name: `my-claude` (highest priority, exact match, case-sensitive)
2. Exact ID: `synapse-claude-8100` (direct match)
3. Type-port: `claude-8100`, `codex-8120`, `opencode-8130`, `copilot-8140` (shorthand)
4. Type only: `claude`, `gemini`, `codex`, `opencode`, `copilot` (only if single instance)

**Note:** When multiple agents of the same type are running, type-only targets (e.g., `claude`) will fail with an ambiguity error showing runnable `synapse send` commands for each matching agent. Use custom name (e.g., `my-claude`) or type-port shorthand (e.g., `claude-8100`) instead.

### Working Directory Check

`synapse send` and `synapse interrupt` verify that the sender's current working directory matches the target agent's working directory. If they differ, the command exits with code 1 and prints a warning:

```text
Warning: Target agent "my-claude" is in a different directory:
  Sender:  /home/user/project-a
  Target:  /home/user/project-b
Agents in current directory:
  gemini (gemini) - READY
Use --force to send anyway.
```

If no agents are running in the sender's directory, the warning suggests `synapse spawn` instead:

```text
Warning: Target agent "my-claude" is in a different directory:
  Sender:  /home/user/project-a
  Target:  /home/user/project-b
No agents in current directory. Spawn one with:
  synapse spawn gemini --name <name>
Use --force to send anyway.
```

To bypass the check, use `--force`:

```bash
synapse send my-claude "Cross-project message" --force
synapse interrupt my-claude "Urgent" --force
```

### Choosing response mode

Analyze the message content and determine if you need immediate results:
- If you need immediate results and want to block until reply → use `--wait`
- If you want to be notified when the task is done (async) → use `--notify` (default)
- If the message is purely informational with no notification needed → use `--silent`

```bash
# Wait for immediate reply (blocking)
synapse send gemini "What is the best approach?" --wait

# Task with async notification (default)
synapse send gemini "Run tests and report" --notify

# Purely informational, no notification needed
synapse send codex "FYI: Build completed" --silent
```

### Roundtrip Communication (--wait)

For request-response patterns:

```bash
# Sender: Wait for response (blocks until reply received)
synapse send gemini "Analyze this data" --wait

# Receiver: Reply to sender (auto-routes via reply tracking)
synapse reply "Analysis result: ..."
```

The `--wait` flag makes the sender wait. The receiver should reply using the `synapse reply` command.

**Reply Tracking:** Synapse automatically tracks senders who expect a reply (`[REPLY EXPECTED]` messages). Use `synapse reply` for responses - it automatically knows who to reply to.

### Broadcasting to All Agents

Send a message to all agents sharing the same working directory:

```bash
# Broadcast status check to all cwd agents
synapse broadcast "Status check"

# Urgent broadcast
synapse broadcast "Urgent: stop all work" --priority 4

# Fire-and-forget broadcast
synapse broadcast "FYI: Build completed" --silent
```

**Note:** Broadcast only targets agents in the **same working directory** as the sender. This prevents unintended messages to agents working on different projects.

## Receiving and Replying to Messages

When you receive an A2A message, it appears with the `A2A:` prefix that includes optional sender identification and reply expectations:

**Message Formats:**
```
A2A: [From: NAME (SENDER_ID)] [REPLY EXPECTED] <message content>
```

- **From**: Identifies the sender's display name and Runtime ID.
- **REPLY EXPECTED**: Indicates that the sender is waiting for a response (blocking).

If sender information is not available, it falls back to:
- `A2A: [From: SENDER_ID] <message content>`
- `A2A: <message content>` (backward compatible format)

If `[REPLY EXPECTED]` marker is present, you **MUST** reply using `synapse reply`.

**IMPORTANT:** Do NOT manually include `[REPLY EXPECTED]` in your messages. Synapse adds this marker automatically when `--wait` is used. Manually adding it causes duplication.

**Reply Tracking:** Synapse stores sender info only for messages with `[REPLY EXPECTED]` marker. Multiple senders can be tracked simultaneously (each sender has one entry).

**Replying to messages:**

```bash
# Use the reply command (auto-routes to last sender)
synapse reply "Here is my analysis..."

# When multiple senders are pending, inspect and choose target
synapse reply --list-targets
synapse reply "Here is my analysis..." --to <sender_id>

# In sandboxed environments (like Codex), specify your Runtime ID
synapse reply "Here is my analysis..." --from $SYNAPSE_AGENT_ID
```

**Example - Question received (MUST reply):**
```
Received: A2A: [From: Claude (synapse-claude-8100)] [REPLY EXPECTED] What is the project structure?
Reply:    synapse reply "The project has src/, tests/..."
```

**Example - Delegation received (no reply needed):**
```
Received: A2A: [From: Gemini (synapse-gemini-8110)] Run the tests and fix failures
Action:   Just do the task. No reply needed unless you have questions.
```

## Priority Levels

| Priority | Description | Use Case |
|----------|-------------|----------|
| 1-2 | Low | Background tasks |
| 3 | Normal | Standard tasks |
| 4 | Urgent | Follow-ups, status checks |
| 5 | Interrupt | Emergency (sends SIGINT first, bypasses Readiness Gate) |

Default priority: `send` = 3 (normal), `broadcast` = 1 (low).

```bash
# Normal priority (default: 3) - with response
synapse send gemini "Analyze this" --wait

# Higher priority - urgent request
synapse send claude "Urgent review needed" --wait --priority 4

# Soft interrupt (shorthand for send -p 4 --silent)
synapse interrupt gemini "Stop and review"

# Emergency interrupt
synapse send codex "STOP" --priority 5
```

## Agent Status

| Status | Meaning | Color |
|--------|---------|-------|
| READY | Idle, waiting for input | Green |
| WAITING | Awaiting user input (selection, confirmation); auto-expires after `waiting_expiry` seconds (default 10s) | Cyan |
| PROCESSING | Busy handling a task | Yellow |
| DONE | Task completed (auto-clears after 10s) | Blue |
| SHUTTING_DOWN | Graceful shutdown in progress | Red |

**Compound Signal Detection:** Status transitions use multiple signals beyond PTY output patterns:
- **task_active flag**: Set when an A2A task is received, cleared on reply. Suppresses premature READY transitions during active tasks (configurable via `task_protection_timeout`, default 30s).
- **File locks**: Agents holding file locks remain in PROCESSING even if PTY output looks idle.
- **WAITING auto-expiry**: WAITING status auto-clears after `waiting_expiry` seconds (default 10s) to prevent stale states.

**CURRENT column** in `synapse list` shows the current task preview with elapsed time (e.g., `Review code (2m 15s)`).

**Verify before sending:** Run `synapse list` and confirm the target agent's Status column shows `READY`. Also check WORKING_DIR to ensure the target is in the same directory (to avoid the working directory mismatch warning):

```bash
synapse list
# Output (NAME column shows custom name if set, otherwise agent type):
# NAME        TYPE    STATUS      PORT   CURRENT              WORKING_DIR
# my-claude   claude  READY       8100   -                    my-project
# gemini      gemini  PROCESSING  8110   Review code (1m 5s)  my-project
# codex       codex   PROCESSING  8120   Fix tests (30s)      other-project
```

**Note:** Non-TTY text output (e.g., when piped or used in scripts) includes the WORKING_DIR column, making it easy to check agent directories programmatically.

**Detailed status:** Use `synapse status <target>` for a comprehensive view of a single agent, including uptime, current task elapsed time, recent messages, file locks, and task board assignments.

```bash
synapse status my-claude          # Human-readable output
synapse status my-claude --json   # Machine-readable JSON
```

**Status meanings:**
- `READY`: Safe to send messages
- `WAITING`: Agent needs user input - use terminal jump (see below) to respond (auto-clears after `waiting_expiry`)
- `PROCESSING`: Busy, wait or use `--priority 5` for emergency interrupt
- `DONE`: Recently completed, will return to READY shortly

**Readiness Gate:** Messages sent to an agent that is still initializing (has not reached READY for the first time) are held for up to 30 seconds (`AGENT_READY_TIMEOUT`). If the agent does not become ready in time, the API returns HTTP 503 with `Retry-After: 5`. Priority 5 and reply messages bypass this gate.

## Interactive Controls

In `synapse list`, you can interact with agents:

| Key | Action |
|-----|--------|
| `1-9` | Select agent row (direct) |
| `↑/↓` | Navigate agent rows |
| `Enter` or `j` | Jump to selected agent's terminal |
| `k` | Kill selected agent (with confirmation) |
| `/` | Filter by TYPE, NAME, or WORKING_DIR |
| `ESC` | Clear filter first, then selection |
| `q` | Quit |

**Supported Terminals:**
- iTerm2 (macOS) - Switches to correct tab/pane
- Terminal.app (macOS) - Switches to correct tab
- Ghostty (macOS) - Activates application. **Note:** Ghostty uses AppleScript to target the focused tab. Do not switch tabs during spawn.
- VS Code integrated terminal - Opens to working directory
- tmux - Switches to agent's session
- Zellij - Activates terminal app (direct pane focus not supported via CLI)

**Use case:** When an agent shows `WAITING` status, use terminal jump to quickly respond to its selection prompt.

## Agent Naming

Assign custom names and roles to agents for easier identification:

```bash
# Start with name and role
synapse claude --name my-claude --role "code reviewer"

# Start with skill set
synapse claude --skill-set dev-set

# Start with saved agent definition (--agent / -A)
synapse claude --agent calm-lead
synapse claude --agent calm-lead --role "override role"  # CLI args override saved values

# Role from file (@prefix reads file content as role)
synapse claude --name reviewer --role "@./roles/reviewer.md"
synapse gemini --role "@~/my-roles/analyst.md"

# Skip interactive name/role setup
synapse claude --no-setup

# Update name/role after agent is running
synapse rename synapse-claude-8100 --name my-claude --role "test writer"
synapse rename my-claude --role "documentation"  # Change role only
synapse rename my-claude --clear                 # Clear name and role
```

Once named, use the custom name for all operations:

```bash
synapse send my-claude "Review this code"
synapse jump my-claude
synapse kill my-claude
```

**Name vs ID:**
- **Display/Prompts**: Shows name if set, otherwise ID (e.g., `Kill my-claude (PID: 1234)?`)
- **Internal processing**: Always uses Runtime ID (`synapse-claude-8100`)
- **Target resolution**: Name has highest priority when matching targets

## External Agent Management

Connect to external A2A-compatible agents over HTTP/HTTPS:

```bash
# Discover and add an external agent
synapse external add https://agent.example.com --alias myagent

# List registered external agents
synapse external list

# Show agent details (capabilities, skills)
synapse external info myagent

# Send message to external agent
synapse external send myagent "Analyze this data"
synapse external send myagent "Process file" --wait  # Wait for completion

# Remove agent
synapse external remove myagent
```

External agents are stored persistently in `~/.a2a/external/`.

## Authentication

Secure A2A communication with API key authentication:

```bash
# Interactive setup (generates keys + shows instructions)
synapse auth setup

# Generate API key(s)
synapse auth generate-key
synapse auth generate-key -n 3 -e  # 3 keys in export format

# Enable authentication
export SYNAPSE_AUTH_ENABLED=true
export SYNAPSE_API_KEYS=<key>
export SYNAPSE_ADMIN_KEY=<admin_key>
synapse claude
```

## Resume Mode

Start agents without sending initial instructions (for session recovery):

```bash
synapse claude -- --resume
synapse gemini -- --resume
synapse codex -- resume        # Codex: resume is a subcommand
synapse opencode -- --continue
synapse copilot -- --continue
```

To inject instructions later: `synapse instructions send <agent>`.

## Key Features

- **Agent Naming**: Custom names and roles for easy identification
- **Saved Agent Definitions**: Persist reusable agent definitions with `synapse agents` (add/list/show/delete). Stored as `.agent` files in project or user scope. Use `--agent`/`-A` flag to start from a saved definition (e.g., `synapse claude --agent calm-lead`), or pass the saved ID/name directly to `synapse spawn`.
- **Agent Communication**: `synapse send` command, `synapse broadcast` for cwd-scoped messaging, priority control, response handling
- **Sender Identification**: Auto-identify sender via `SYNAPSE_AGENT_ID` env var → `metadata.sender` + PID matching (fallback)
- **Soft Interrupt**: `synapse interrupt` — shorthand for `synapse send -p 4 --silent` (urgent, fire-and-forget)
- **Priority Interrupt**: Priority 5 sends SIGINT before message delivery (emergency stop, bypasses Readiness Gate)
- **Readiness Gate**: `/tasks/send` and `/tasks/send-priority` return HTTP 503 with `Retry-After: 5` while agent is initializing; priority 5 and replies bypass
- **Multi-Instance**: Run multiple agents of the same type with automatic port assignment
- **Task History**: Search, export, statistics (`synapse history`). `synapse history stats` shows a TOKEN USAGE section when token data exists (skeleton — no agent parsers yet).
- **File Safety**: Lock files to prevent conflicts (`synapse file-safety`); active locks shown in `synapse list` EDITING_FILE column
- **External Agents**: Connect to external A2A agents (`synapse external`)
- **Authentication**: API key-based security (`synapse auth`)
- **Skill Management**: Central skill store, deploy, import, create, skill sets (`synapse skills`). Skill set details (name, description, skills) are included in agent initial instructions when selected.
- **Settings**: Configure via `settings.json` (`synapse init`)
- **Approval Mode**: Control initial instruction approval (`approvalMode` in settings)
- **Learning Mode**: Append structured learning feedback to agent responses.
  - `SYNAPSE_LEARNING_MODE_ENABLED=true` — adds PROMPT IMPROVEMENT section (Goal/Problem/Fix, recommended rewrite, detail-level options)
  - `SYNAPSE_LEARNING_MODE_TRANSLATION=true` — adds JP→EN LEARNING section (reusable English pattern, slot mapping, assembled prompt with JP paraphrase, quick alternatives)
  - Either flag can be used alone or together. When either flag is enabled, `.synapse/learning.md` is auto-injected and TIPS are appended.
  - **Formatting rule**: RESPONSE uses normal formatting (no separators or section headers); structured format (━━━ separators, numbered sub-sections) is only for learning feedback sections (PROMPT IMPROVEMENT / JP → EN LEARNING / TIPS).
  - **Mustache conditionals**: `{{#learning_mode}}...{{/learning_mode}}` and `{{#learning_translation}}...{{/learning_translation}}` include content when the flag is enabled. Inverse sections `{{^learning_mode}}...{{/learning_mode}}` and `{{^learning_translation}}...{{/learning_translation}}` include content when the flag is disabled/unset. Both positive and inverse blocks are supported in `learning.md`.
- **Shared Task Board**: Create, claim, and complete tasks with dependency tracking (`synapse tasks`)
  - Task lifecycle: pending → in_progress → completed/failed → reopen to pending
  - Priority-based ordering (1-5, higher served first)
  - `fail_task()` preserves assignee for audit trail, does NOT unblock dependents
  - `reopen_task()` clears assignee/fail_reason, returns task to available pool
- **Shared Memory**: Project-local SQLite knowledge base for cross-agent knowledge sharing (`synapse memory`)
  - UPSERT on key: `synapse memory save <key> "<content>" [--tags tag1,tag2]`
  - Search across key, content, and tags: `synapse memory search <query>` (bounded, default limit: 100)
  - Filter by author or tags: `synapse memory list [--author <id>] [--tags <tags>]`
  - Statistics: `synapse memory stats` (total, per-author, per-tag breakdown)
  - Optional broadcast notification on save: `--notify` flag
  - Storage: `.synapse/memory.db` (SQLite with WAL mode)
  - Enabled by default (`SYNAPSE_SHARED_MEMORY_ENABLED=true`)
- **Quality Gates**: Configurable hooks (`on_idle`, `on_task_completed`) that gate status transitions
- **Plan Approval**: Plan-mode workflow with `synapse approve/reject` for review
- **Graceful Shutdown**: `synapse kill` — multi-phase: shutdown request → SIGTERM → SIGKILL (30s budget, `-f` for immediate SIGKILL)
- **Delegate Mode**: `--delegate-mode` creates a manager that delegates instead of editing files
- **Auto-Spawn Panes**: `synapse team start` — 1st agent takes over current terminal (handoff), others in new panes. `--all-new` for all new panes. `--worktree` for per-agent worktree isolation. Supports `profile:name:role:skill_set:port` spec (tmux/iTerm2/Terminal.app/Ghostty/zellij). Ports are pre-allocated to avoid race conditions when multiple agents of the same type start simultaneously.
- **Session Save/Restore**: `synapse session` — Save running team configurations as named JSON snapshots and restore them later. Captures each agent's profile, name, role, skill set, worktree setting, and `session_id` (CLI conversation identifier). Scopes: project (`.synapse/sessions/`), user (`~/.synapse/sessions/`), or `--workdir DIR` (`DIR/.synapse/sessions/`). Restore spawns all agents from the snapshot via `spawn_agent()`. Use `--resume` to resume each agent's previous CLI session (conversation history); if resume fails within 10 seconds, the agent is retried without resume args (shell-level fallback).
- **Workflow Automation**: `synapse workflow` — Define multi-step agent workflows as YAML files (`synapse workflow create`), list/show saved workflows, and execute steps sequentially (`synapse workflow run`). Each step targets an agent with a message, priority, and response mode. Supports `--dry-run` and `--continue-on-error`. Storage: `.synapse/workflows/` (project) or `~/.synapse/workflows/` (user).
- **Spawn Single Agent**: `synapse spawn <profile>` — Spawn a single agent in a new terminal pane or window. `--no-setup --headless` are always added.
- **Worktree Isolation**: `--worktree` / `-w` is a Synapse-level flag that gives each agent an isolated git worktree under `.synapse/worktrees/<name>/`, preventing file conflicts in multi-agent setups. Works for ALL agent types (Claude, Gemini, Codex, OpenCode, Copilot). Usage: `synapse spawn claude --worktree`, `synapse team start claude gemini --worktree`. `synapse list` shows `[WT]` prefix for worktree agents. Env vars: `SYNAPSE_WORKTREE_PATH`, `SYNAPSE_WORKTREE_BRANCH`, `SYNAPSE_WORKTREE_BASE_BRANCH`. Cleanup detects both uncommitted changes and new commits (vs. the base branch) before deciding whether to auto-delete.
- **CI Monitoring**: Automated PostToolUse hooks (`poll-ci.sh`, `poll-pr-status.sh`) detect `git push` and `gh pr create`, then poll GitHub Actions CI status, merge conflict state, and CodeRabbit reviews. Reports results via `systemMessage` and suggests `/fix-ci`, `/fix-conflict`, or `/fix-review` as appropriate.

### Task Board Workflow Pattern (Kanban)

Manager (delegate-mode) monitors the TaskBoard and assigns tasks to worker agents:

1. **Manager** creates tasks with dependencies and priorities
   ```bash
   synapse tasks create "Write tests" --priority 5
   synapse tasks create "Implement feature" --blocked-by <test-task-id> --priority 4
   synapse tasks create "Code review" --blocked-by <impl-task-id> --priority 3
   ```

2. **Manager** checks available tasks, assigns, and notifies agents
   ```bash
   synapse tasks list --status pending
   synapse tasks assign <task_id> <agent>
   synapse send <agent> "Execute task: <description>" --silent
   ```

3. **Worker agents** report completion or failure
   ```bash
   synapse tasks complete <task_id>
   synapse tasks fail <task_id> --reason "Tests failed"
   ```

4. **Manager** handles failures
   ```bash
   synapse tasks list --status failed
   synapse tasks reopen <task_id>    # Return to pending for retry
   ```

**Status transitions:**
```
pending → in_progress → completed
                     → failed → (reopen) → pending
completed → (reopen) → pending
```

## Spawning Agents (Sub-Agent Delegation)

**Spawn is sub-agent delegation.** The parent spawns child agents to offload subtasks. Goals:

- **Context preservation** — keep the parent's context window focused on the main task
- **Efficiency & speed** — parallelize independent subtasks to reduce total execution time
- **Precision** — assign specialists with dedicated roles for higher-quality results

The parent always owns the lifecycle: spawn → send task → evaluate result → kill.

### When to Spawn

Choose the right approach based on the situation:

| Situation | Action | Why |
|-----------|--------|-----|
| Task is small or within your expertise | **Do it yourself** | No overhead, fastest path |
| Another agent is already running and READY | **`synapse send` to existing agent** | Reuse running agents before spawning new ones |
| Task is large and would consume your context | **`synapse spawn` a new agent** | Offload to preserve context; specialist role improves precision |
| Task has independent parallel subtasks | **`synapse spawn` N agents** | Parallel execution cuts total time; each agent focuses on one subtask |

**Rule of thumb:** Spawn when delegating would be faster, more precise, or prevent your context from being consumed by a large subtask.

### Mental Model

```
Parent receives task
  │
  ├─ User-specified agent count? ──→ Use that count ─────┐
  │                                                      │
  └─ No specification? ──→ Parent decides count & roles ─┘
                                                         │
                                                         ▼
                                                   spawn child(ren)
                                                         │
                                                         ▼
                                                   send task  ◄──────────┐
                                                         │               │
                                                         ▼               │
                                                   evaluate result       │
                                                         │               │
                                                   ├─ Sufficient? → kill ✓
                                                   │
                                                   └─ Insufficient? ─────┘
```

### How Many Agents

1. **User-specified count** → follow it exactly (top priority)
2. **No user specification** → parent analyzes the task and decides:
   - Single focused subtask → 1 agent
   - Independent parallel subtasks → N specialists (one per subtask)
   - The parent assigns a name and role to each spawned agent

### Basic Lifecycle

```bash
# 1. Spawn a helper
synapse spawn gemini --name Tester --role "test writer"

# 2. Confirm readiness (synapse list is a point-in-time snapshot — poll until READY)
elapsed=0
while ! synapse list | grep -q "Tester.*READY"; do
  sleep 1; elapsed=$((elapsed + 1))
  [ "$elapsed" -ge 30 ] && echo "ERROR: Tester not READY after ${elapsed}s" >&2 && exit 1
done

# 3. Send task (wait for result)
synapse send Tester "Write unit tests for src/auth.py" --wait

# 4. Evaluate result — if insufficient, re-send
synapse send Tester "Add edge-case tests for expired tokens" --wait

# 5. MUST kill when done (parent owns lifecycle)
synapse kill Tester -f
```

**Note:** `$SYNAPSE_AGENT_ID` is automatically set by Synapse when an agent starts (e.g., `synapse-claude-8100`). The `--from` flag is auto-detected from this env var, so you can usually omit it. You can verify your ID with `synapse list`.

### How to Evaluate Results

After receiving a `--wait` reply from a spawned agent:

1. **Read the reply content** — does it address what you asked?
2. **Verify artifacts if needed** — run `git diff`, `pytest`, or read modified files to confirm the work
3. **Decide next step:**
   - Result is sufficient → `synapse kill <child> -f`
   - Result is insufficient → re-send with refined instructions (do NOT kill and re-spawn)

### Permission Skip Flags (per CLI)

Each CLI has its own flag to skip interactive permission prompts. Pass these after `--` as tool args:

| CLI | Flag | Notes |
|-----|------|-------|
| **Claude Code** | `--dangerously-skip-permissions` | Skips all permission prompts |
| **Gemini CLI** | `-y` | Yolo mode — auto-approve all actions |
| **Codex CLI** | `--full-auto` | Sandboxed auto-approve (`-a on-request --sandbox workspace-write`) |
| **OpenCode** | *(no flag)* | No auto-approve flag available |
| **Copilot CLI** | `--allow-all-tools` | Allow all tools without prompts |

```bash
# Spawn with permission skip (per CLI)
synapse spawn claude -- --dangerously-skip-permissions
synapse spawn gemini -- -y
synapse spawn codex -- --full-auto
synapse spawn copilot -- --allow-all-tools

# Team start with permission skip (flag applies to ALL agents)
# Only use when all agents support the same flag, or target specific CLIs:
synapse team start claude gemini -- --dangerously-skip-permissions  # Only Claude uses it; Gemini ignores unknown flags
# For Codex full unrestricted mode: --dangerously-bypass-approvals-and-sandbox
```

### CLI & API

```bash
# CLI
synapse spawn claude                          # Spawn in new pane
synapse spawn gemini --port 8115              # Explicit port
synapse spawn claude --name Reviewer --role "code review" --skill-set dev-set
synapse spawn claude --terminal tmux          # Specific terminal
synapse spawn sharp-checker                    # Spawn by saved Agent ID
synapse spawn Claud                           # Spawn by saved agent display name
synapse spawn claude --worktree              # Spawn in isolated worktree
synapse spawn claude -w my-feature           # Named worktree
synapse spawn claude -- --dangerously-skip-permissions   # Tool args after '--'
synapse spawn gemini -- -y                               # Gemini yolo mode
synapse spawn codex -- --full-auto                       # Codex sandboxed auto-approve
synapse spawn copilot -- --allow-all-tools               # Copilot allow all
```

```jsonc
// POST /spawn (API — agents can spawn programmatically)
{"profile": "gemini", "name": "Helper", "skill_set": "dev-set", "tool_args": ["-y"]}
// With worktree isolation:
{"profile": "gemini", "name": "Worker", "worktree": true}
{"profile": "claude", "name": "Worker", "worktree": "my-feature"}
// Returns: {agent_id, port, terminal_used, status, worktree_path, worktree_branch, worktree_base_branch}
// Claude example:
{"profile": "claude", "name": "Worker", "tool_args": ["--dangerously-skip-permissions"]}
// Codex example:
{"profile": "codex", "name": "Coder", "tool_args": ["--full-auto"]}
// On failure: {"status": "failed", "reason": "..."}
```

### Worktree Isolation (Synapse-native flag)

`--worktree` / `-w` is a **Synapse-level flag** that creates an isolated git worktree for each agent. It works for **all** agent types (Claude, Gemini, Codex, OpenCode, Copilot) and is placed **before** `--` (not as a tool arg). Each worktree is created under `.synapse/worktrees/<name>/` with a branch named `worktree-<name>`.

**Decision Table:**

| Situation | Action |
|-----------|--------|
| Multiple agents may edit the same files | Use `--worktree` |
| Coordinator + Worker pattern (Worker edits code) | Worker gets `--worktree` |
| Read-only tasks (investigation, analysis, review) | Worktree not needed |
| Single agent working alone | Worktree not needed |

**Usage:**

```bash
# Spawn any agent in an isolated worktree (auto-generated name)
synapse spawn claude --name Impl --role "implementer" --worktree
synapse spawn gemini --name Analyst --role "analyzer" -w

# Named worktree (creates .synapse/worktrees/feat-auth/ with branch worktree-feat-auth)
synapse spawn claude --name Impl --role "implementer" --worktree feat-auth

# Team start with worktree per agent
synapse team start claude gemini --worktree
synapse team start claude gemini codex -w my-feature  # Named prefix: my-feature-claude-0, my-feature-gemini-1, etc.
```

**`synapse list` indicator:**

Agents running in worktrees show a `[WT]` prefix in the WORKING_DIR column.

**Environment variables** (set automatically by Synapse for worktree agents):

| Variable | Description |
|----------|-------------|
| `SYNAPSE_WORKTREE_PATH` | Absolute path to the worktree directory |
| `SYNAPSE_WORKTREE_BRANCH` | Branch name of the worktree |
| `SYNAPSE_WORKTREE_BASE_BRANCH` | Base branch the worktree was created from (e.g., `origin/main`). Used for change detection during cleanup. Determined via 3-step fallback: `git symbolic-ref` -> `origin/main` -> `HEAD`. |

**API (`POST /spawn`):**

```jsonc
{"profile": "gemini", "name": "Worker", "worktree": true}          // auto-named
{"profile": "claude", "name": "Worker", "worktree": "feat-auth"}   // named
// Response includes: worktree_path, worktree_branch, worktree_base_branch
```

**Caveats:**

- `--worktree` is a **Synapse flag**. Place it **before** `--`. Placing it after `--` triggers a warning because it would be passed to the underlying CLI as a tool arg instead.
- `.gitignore`-listed files (`.env`, `.venv/`, `node_modules/`) are **not copied** to the worktree. Run `uv sync`, `npm install`, or copy `.env` manually if needed.
- On exit: worktrees with no uncommitted changes **and** no new commits (vs. the base branch) are auto-deleted; worktrees with either uncommitted changes or new commits prompt to keep or remove.
- `synapse kill` also handles worktree cleanup for killed agents.
- The registry stores `worktree_base_branch` so cleanup can compare the worktree HEAD against the branch it was created from.
- Consider adding `.synapse/worktrees/` to your `.gitignore` to prevent untracked worktree files from cluttering `git status`.

### Technical Notes

- **Headless mode:** `synapse spawn` (and `synapse team start`) always add `--no-setup --headless`, skipping interactive setup while keeping the A2A server and initial instructions active.
- **Readiness:** After spawning, Synapse waits for the agent to register and warns with concrete `synapse send` examples if not yet ready. At the HTTP level, a Readiness Gate blocks `/tasks/send` until the agent finishes initialization (returns HTTP 503 + `Retry-After: 5` if not ready within 30s).
- **Pane auto-close:** Spawned panes close automatically when the agent process terminates (tmux, zellij, iTerm2, Terminal.app, Ghostty).
- **Known limitation ([#237](https://github.com/s-hiraoku/synapse-a2a/issues/237)):** Spawned agents cannot use `synapse reply` (PTY injection does not register sender info). Use `synapse send <target> "message"` for bidirectional communication (`--from` is auto-detected).

## Path Overrides

When running multiple environments or tests, override storage paths via env vars:

- `SYNAPSE_REGISTRY_DIR` (default: `~/.a2a/registry`)
- `SYNAPSE_REPLY_TARGET_DIR` (default: `~/.a2a/reply`)
- `SYNAPSE_EXTERNAL_REGISTRY_DIR` (default: `~/.a2a/external`)
- `SYNAPSE_HISTORY_DB_PATH` (default: `~/.synapse/history/history.db`)
- `SYNAPSE_SKILLS_DIR` (default: `~/.synapse/skills`)
- `SYNAPSE_SHARED_MEMORY_DB_PATH` (default: `.synapse/memory.db`)
- `SYNAPSE_SHARED_MEMORY_ENABLED` (default: `true`)

## References

For detailed documentation, read:

- `references/commands.md` - Full CLI command reference
- `references/file-safety.md` - File Safety detailed guide
- `references/api.md` - A2A endpoints and message format
- `references/examples.md` - Multi-agent workflow examples

### Related Skills

| Skill | Purpose |
|-------|---------|
| `/synapse-manager` | Multi-agent management — task delegation, monitoring, quality verification, feedback, and cross-review orchestration |
| `/synapse-reinst` | Re-inject Synapse A2A initial instructions after `/clear` or context reset |
| `/doc-organizer` | Audit, restructure, and consolidate project documentation for clarity and maintainability |
| `/check-ci` | Check CI status, merge conflicts, and CodeRabbit review state for the current PR |
| `/fix-ci` | Auto-diagnose and fix GitHub Actions CI failures (lint, format, type, test) |
| `/fix-conflict` | Auto-resolve merge conflicts with the base branch |
| `/fix-review` | Auto-address CodeRabbit inline review comments (bug/style categories) |

These skills are triggered manually or suggested by the CI monitoring hooks (`poll-ci.sh`, `poll-pr-status.sh`) after `git push` or `gh pr create`.
