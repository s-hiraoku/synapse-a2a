# Agent Management

## Starting Agents

### Interactive Mode (Foreground)

```bash
synapse claude                              # Start Claude Code
synapse gemini                              # Start Gemini CLI
synapse codex                               # Start Codex CLI
synapse opencode                            # Start OpenCode
synapse copilot                             # Start GitHub Copilot CLI
```

Each shortcut loads the corresponding profile and starts the agent interactively.

### With Name and Role

```bash
synapse claude --name my-claude --role "code reviewer"
synapse gemini --name test-writer --role "test specialist"
```

### With Saved Agent Definition

Use a [saved agent definition](agent-teams.md#saved-agent-definitions) to load name, role, and skill set from a reusable template:

```bash
synapse claude --agent calm-lead        # By saved agent ID
synapse claude -A Claud                       # By display name (short flag)
synapse claude --agent calm-lead --role "temporary override"  # CLI flags override saved values
```

The saved agent's profile must match the profile shortcut (e.g., a `gemini` saved agent cannot be used with `synapse claude`).

### Skip Interactive Setup

```bash
synapse claude --no-setup
```

### Background Mode

```bash
synapse start claude --port 8100
synapse start claude --port 8100 -f   # Foreground (don't detach)
```

### Delegate Mode (Manager)

Start an agent as a manager that delegates work instead of editing files directly:

```bash
synapse claude --delegate-mode --name manager --role "task coordinator"
```

The agent receives `[MANAGER MODE]` instructions and its file lock requests are denied at the system level. See [Delegate Mode](agent-teams.md#delegate-mode) for full details.

### Resume Mode

Pass resume flags to the underlying CLI tool via `--` to skip initial instructions (useful after context reset):

```bash
synapse claude -- --resume
synapse claude -- --continue   # Same as --resume
```

Synapse detects these flags and automatically skips sending initial instructions.

!!! note "MCP bootstrap startup"
    When Claude Code, Codex, Gemini CLI, OpenCode, or GitHub Copilot has a Synapse MCP server configured, Synapse sends a minimal PTY MCP bootstrap automatically instead of the full startup instruction payload. Approval prompts still apply unless you are resuming a session. See [MCP Bootstrap Setup](mcp-setup.md) for details.

## Monitoring Agents

### synapse list

The Rich TUI agent monitor with real-time updates:

```bash
synapse list
```

For machine-readable output (JSON array of all running agents):

```bash
synapse list --json
```

The `--json` flag skips the TUI and prints a JSON array with fields: `agent_id`, `agent_type`, `name`, `role`, `skill_set`, `port`, `status`, `pid`, `working_dir`, `endpoint`, `transport`, `current_task_preview`, `task_received_at`, `spawned_by`, `is_orphan` (plus `editing_file` when File Safety is enabled).

Displays a live table with:

| Column | Description |
|--------|-------------|
| `#` | Row number (for keyboard selection) |
| `ID` | Agent identifier |
| `NAME` | Custom name (if set) |
| `STATUS` | Current state with color coding (annotated with `[ORPHAN]` when the agent's spawn parent is gone — see [Orphan Cleanup](#orphan-cleanup)) |
| `CURRENT` | Current task preview with elapsed time (e.g., `Review code (2m 15s)`) |
| `TRANSPORT` | Active communication direction and protocol (see below) |
| `WORKING_DIR` | Agent's working directory |
| `SKILL_SET` | Applied skill set name (optional) |
| `EDITING_FILE` | Locked file name (shown when File Safety is enabled) |

Optional columns (`list.columns`): `TYPE`, `ROLE`, `SKILL_SET`.

**Interactive controls:**

| Key | Action |
|-----|--------|
| ++up++ / ++down++ | Select agent row |
| `1`-`9` | Jump to row number |
| ++enter++ / `j` | Jump to agent's terminal |
| `K` | Kill agent (with confirmation) |
| `/` | Filter by TYPE, NAME, or WORKING_DIR |
| ++escape++ | Clear filter |
| `q` | Quit |

**TRANSPORT column values:**

| Value | Meaning |
|-------|---------|
| `UDS→` | Sending a message via Unix Domain Socket |
| `→UDS` | Receiving a message via Unix Domain Socket |
| `TCP→` | Sending a message via TCP |
| `→TCP` | Receiving a message via TCP |
| `-` | No active communication |

The TRANSPORT column appears in both the Rich TUI (interactive mode) and the plain-text output (non-TTY / piped output). During a `synapse send` exchange, the sender briefly shows `UDS→` (or `TCP→`) while the receiver shows `→UDS` (or `→TCP`). Both return to `-` after the message is delivered.

!!! info "Real-Time Updates"
    `synapse list` uses file watchers (fsevents on macOS, inotify on Linux) to detect registry changes instantly. Falls back to 10-second polling if watchers are unavailable.

### Detailed Status

For a deep-dive into a single agent, use `synapse status`:

```bash
synapse status my-claude
```

This shows:

- **Agent Info**: ID, type, name, role, port, status, PID, working directory, uptime
- **Current Task**: Task preview with elapsed time since the task was received
- **Recent Messages**: Last 5 incoming/outgoing A2A messages from history
- **File Locks**: Files currently locked by this agent (when File Safety is enabled)

For machine-readable output:

```bash
synapse status my-claude --json
```

!!! tip "When to use `synapse status` vs `synapse list`"
    Use `synapse list` for a live overview of all agents. Use `synapse status <target>` when you need detailed information about a specific agent, including its message history, file locks, and assigned tasks.

## Stopping Agents

### Graceful Shutdown

```bash
synapse kill my-claude            # Graceful (30s timeout)
```

Graceful shutdown phases:

1. Send HTTP shutdown request to the agent
2. Wait for grace period (30s default)
3. Send SIGTERM
4. If still running, send SIGKILL

### Force Kill

```bash
synapse kill my-claude -f         # Immediate SIGKILL
```

### Stop Background Agent

```bash
synapse stop my-claude
synapse stop claude -a            # Stop all Claude instances
```

### Orphan Cleanup

When a parent agent crashes or is cleared while its spawned children are still running, those children become **orphans**. An orphan is a child agent (registered with a `spawned_by` link) whose parent has either been removed from the registry or whose parent PID is no longer alive.

```bash
synapse cleanup --dry-run         # Preview orphans without killing
synapse cleanup                   # Kill all orphans (with confirmation)
synapse cleanup -f                # Kill all orphans, no prompt
synapse cleanup <agent>           # Kill one specific orphan
```

Parent-child tracking is recorded at spawn time: `synapse spawn` propagates the current agent's ID to the child via the `SYNAPSE_SPAWNED_BY` environment variable, and the registry persists it under `spawned_by`.

`synapse cleanup` is deliberately conservative and complements `synapse kill`:

- Root agents (no `spawned_by`) are never touched.
- Children whose parent is still live are never touched.
- A per-agent target that is **not** an orphan is rejected with exit code 1, so `synapse kill` semantics are preserved.

!!! tip "Opportunistic cleanup on `synapse list`"
    Set `SYNAPSE_ORPHAN_IDLE_TIMEOUT=<seconds>` to enable best-effort sweeping of orphans that have been `READY` longer than the timeout. When enabled, `synapse list` quietly cleans up idle orphans in the background. Off by default.

## Terminal Jump

Jump to an agent's terminal window from `synapse list` or via CLI:

```bash
synapse jump my-claude
```

**Supported terminals:**

| Terminal | Jump Support |
|----------|:---:|
| tmux | :material-check: |
| iTerm2 | :material-check: |
| Terminal.app | :material-check: |
| Ghostty | :material-check: |
| VS Code Terminal | :material-check: |
| Zellij | :material-check: |

!!! info "Ghostty Focus Limitation"
    Ghostty uses AppleScript to target the **currently focused window/tab**. If you switch tabs while a `spawn` or `team start` command is running, the agent may be created in the unintended tab. Wait for the command to complete before switching tabs. The `jump` command only moves focus to an existing terminal and is not affected by this limitation.

## Naming and Roles

### Assign Name and Role

```bash
# At startup
synapse claude --name reviewer --role "security code review"

# After startup
synapse rename claude --name reviewer --role "security code review"
```

### Role from File

Use the `@` prefix to load role content from a file:

```bash
synapse claude --name reviewer --role "@./roles/reviewer.md"
synapse rename my-claude --role "@./roles/architect.md"
```

**Recommended directories:**

| Scope | Path | Use case |
|-------|------|----------|
| Project | `./roles/` | Team-shared role definitions (commit to Git) |
| Personal | `~/my-roles/` or `~/.synapse/roles/` | Personal role templates |

```bash
# Project-local role (shared with team)
synapse claude --name reviewer --role "@./roles/reviewer.md"

# Personal role (user-specific)
synapse gemini --role "@~/my-roles/analyst.md"
```

Role files are plain Markdown. A typical role file describes the agent's responsibilities and workflow:

```markdown
# Code Reviewer

You are an expert at reviewing code for correctness, security, and maintainability.

## Responsibilities
- Review pull requests for bugs and security issues
- Suggest improvements for readability and performance
- Verify test coverage
```

### Update Role Only

```bash
synapse rename my-claude --role "architecture review"
```

### Clear Name and Role

```bash
synapse rename my-claude --clear
```

### Save Agent Definition for Reuse

Save frequently used name/role/skill-set combinations as reusable definitions:

```bash
synapse agents add sharp-checker --name Rex --profile codex --role @./roles/tester.md --skill-set developer --scope project
synapse agents list
synapse codex --agent sharp-checker    # Start using saved definition (profile must match)
synapse spawn sharp-checker            # Spawn using saved definition (any profile OK)
```

On interactive exit, Synapse also offers a save prompt for the current
definition:

```text
Save this agent definition for reuse? [y/N]:
```

- Appears for interactive `synapse <profile>` sessions with a configured name.
- Does not appear in `--headless` or non-TTY sessions.
- Does not appear when terminating agents with `synapse stop ...` or `synapse kill ...`.
- Disable with `SYNAPSE_AGENT_SAVE_PROMPT_ENABLED=false`.

See [Saved Agent Definitions](agent-teams.md#saved-agent-definitions) for full details.

### Target Resolution Priority

When using `synapse send`, `synapse kill`, `synapse jump`, `synapse rename`, or `synapse skills apply`:

1. **Custom name** (highest): `my-claude`
2. **Full Runtime ID**: `synapse-claude-8100`
3. **Type-port shorthand**: `claude-8100`
4. **Agent type** (only if single instance): `claude`

!!! warning
    Custom names are case-sensitive. If multiple agents share the same type, you must use a name, full ID, or type-port to disambiguate.

## Agent Status

| Status | Color | Meaning |
|--------|:---:|---------|
| **READY** | :material-circle:{ .status-ready } | Idle, waiting for input |
| **PROCESSING** | :material-circle:{ .status-processing } | Actively working |
| **WAITING** | :material-circle:{ .status-waiting } | Showing selection UI |
| **DONE** | :material-circle:{ .status-done } | Task completed (auto-clears 10s) |
| **SHUTTING_DOWN** | :material-circle:{ .status-shutdown } | Shutdown in progress |

Dead processes are automatically cleaned from the registry and hidden from `synapse list`.

### Compound Signal Detection

Status transitions use **compound signals** to improve accuracy. The PROCESSING-to-READY transition is suppressed when:

- **task_active** is set (an A2A task was recently injected into the PTY), with a 30-second protection timeout
- **File locks** are held by the agent via File Safety

This prevents agents from briefly flickering to READY while still processing an injected task or actively editing files. WAITING detection uses **fresh-output-only** matching to avoid false positives from old prompt patterns in the scrollback buffer.

See [Architecture — Compound Signal Detection](../concepts/architecture.md#compound-signal-detection) for technical details.

### Renderer Availability

Each agent wraps its PTY output in a `PtyRenderer` (pyte-backed virtual terminal) so cursor motion, ratatui redraws, and alt-screen overlays are resolved into stable text before `waiting_detection` regexes run. If initialization fails (for example on a pyte import error), the controller falls back to a plain ANSI-stripping path — functional for line-oriented CLIs but less accurate for ratatui-style TUIs like Codex.

Fallback is observable rather than silent:

- `synapse list` / `synapse status` plain-text output annotates the status as `WAITING (renderer: off)` / `READY (renderer: off)` etc. when the renderer is down.
- `synapse list --json` and `synapse status --json` expose `renderer_available: bool` on each agent.
- `GET /debug/waiting` returns `renderer_available` at the top level.

If `(renderer: off)` persists on an agent, restart the agent (`synapse kill <id>` then respawn) — renderer failures are per-process and do not recover automatically.

### WAITING Detection Diagnostics (`--debug-waiting`)

`synapse status <agent> --debug-waiting` (added in v0.28.0, see #608/#627) prints the last ~50 WAITING-detection attempts that the agent recorded in-memory, plus aggregate counts:

- Total attempts, `pattern_matched` ratio, `path_used` distribution (renderer vs strip_ansi)
- `pattern_source` distribution (primary regex / heuristic / none)
- `confidence` distribution (1.0 primary / 0.6 heuristic / 0.0 miss)
- `idle_gate_passed=false` count — "prompt was visible but the idle gate dropped it"

Use this when a prompt *should* have flipped the agent to WAITING but did not: each attempt row includes `new_data_hex_prefix` (raw bytes) and `rendered_text_tail` (what the detector saw), so you can diagnose whether the regex missed, the idle gate dropped it, or the renderer garbled it.

The buffer is in-memory only — it empties on process restart. For long-running collection across multiple agents, use the Phase 1.5 `synapse waiting-debug` CLI (see below).

### Phase 1.5: Periodic Data Collection (`synapse waiting-debug`)

`synapse waiting-debug` (added in v0.28.1, see #630/#632) persists the `/debug/waiting` snapshot exposed by every running agent to `~/.synapse/waiting_debug.jsonl`, so Phase 2 detection-logic work has real data to lean on instead of guesses.

```bash
synapse waiting-debug collect                         # one-shot across all agents
synapse waiting-debug collect --agent <id>            # single agent
synapse waiting-debug collect --include-empty         # record agents whose ring is empty
synapse waiting-debug report                          # human-readable aggregate
synapse waiting-debug report --since 2026-04-23T00:00:00+00:00 --agent <id>
synapse waiting-debug report --json                   # machine-readable for analysis
```

The report groups results by profile, `pattern_source`, `path_used`, and `confidence`, and surfaces `idle_gate_drops` (prompt visible but gate dropped it) plus the ratio of agents whose snapshot reported `renderer_available=false`.

**Schedule it to run every five minutes** (see `docs/phase15-collection.md` for the canonical recipes):

```bash
# launchd (macOS)
cp plists/dev.synapse.waiting-debug.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/dev.synapse.waiting-debug.plist

# cron
crontab -e
*/5 * * * * /usr/bin/env synapse waiting-debug collect >> ~/.synapse/waiting_debug_collect.log 2>&1
```

!!! warning "Bump the installed CLI first"
    `synapse waiting-debug` only exists in v0.28.1+. Upgrade the globally-installed CLI (`uv tool upgrade synapse-a2a` or `pipx upgrade synapse-a2a`) before arming the schedule, otherwise every run emits `invalid choice: 'waiting-debug'`.

!!! info "Legacy agents return 404"
    Agents that are still running with a pre-0.28.0 `synapse` binary do not expose `GET /debug/waiting`. The collector logs one `HTTP Error 404: Not Found` warning per legacy agent to stderr and continues. Data accrues only for agents respawned after the CLI upgrade — stop and restart them with `synapse kill <id>` followed by the usual spawn when you want them in the dataset.
