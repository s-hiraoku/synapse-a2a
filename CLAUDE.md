# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Flow (Mandatory)

1. When receiving a feature request or modification, write tests first
2. Present the tests to confirm the specification
3. Proceed to implementation only after confirmation
4. Adjust implementation until all tests pass

### Branch Management Rules

- **Do NOT change branches during active work** - Stay on the current branch until the task is complete
- **If branch change is needed**, always ask the user for confirmation first
- Before switching branches, ensure all changes are committed or stashed
- When sending tasks to other agents, they must work on the same branch

## Project Overview

**Mission: Enable agents to collaborate on tasks without changing their behavior.**

Synapse A2A is a framework that wraps CLI agents (Claude Code, Codex, Gemini, OpenCode, GitHub Copilot CLI) with PTY and enables inter-agent communication via Google A2A Protocol. Each agent runs as an A2A server (P2P architecture, no central server).

### Core Principles

1. **Non-Invasive**: Wrap agents transparently without modifying their behavior
2. **Collaborative**: Enable multiple agents to work together using their strengths
3. **Transparent**: Maintain existing workflows and user experience

## Commands

```bash
# Install
uv sync

# Run tests
pytest                                    # All tests
pytest tests/test_a2a_compat.py -v        # Specific file
pytest -k "test_identity" -v              # Pattern match
pytest tests/test_history.py -v           # History feature tests
pytest tests/test_file_safety_extended.py -v # File Safety tests
pytest tests/test_skills.py -v            # Skills core tests
pytest tests/test_cmd_skill_manager.py -v # Skill manager command tests
pytest tests/test_send_message_file.py -v # Send --message-file/--stdin/auto-temp tests
pytest tests/test_file_attachment.py -v   # --attach file attachment tests
pytest tests/test_cmd_trace.py -v         # synapse trace command tests
pytest tests/test_interactive_setup.py -v # Interactive setup + core skills tests

# Agent Teams feature tests
pytest tests/test_task_board.py -v           # B1: Shared Task Board
pytest tests/test_task_board_api.py -v       # B1: Task Board API
pytest tests/test_cli_tasks.py -v            # B1: Task Board CLI
pytest tests/test_hooks.py -v                # B2: Quality Gates (Hooks)
pytest tests/test_plan_approval.py -v        # B3: Plan Approval
pytest tests/test_graceful_shutdown.py -v    # B4: Graceful Shutdown
pytest tests/test_delegate_mode.py -v        # B5: Delegate Mode
pytest tests/test_auto_spawn.py -v           # B6: Auto-Spawn Panes
pytest tests/test_team_start_api.py -v       # B6: Team Start API

# Agent Teams feature tests
pytest tests/test_task_board.py -v           # B1: Shared Task Board
pytest tests/test_task_board_api.py -v       # B1: Task Board API
pytest tests/test_cli_tasks.py -v            # B1: Task Board CLI
pytest tests/test_hooks.py -v                # B2: Quality Gates (Hooks)
pytest tests/test_plan_approval.py -v        # B3: Plan Approval
pytest tests/test_graceful_shutdown.py -v    # B4: Graceful Shutdown
pytest tests/test_delegate_mode.py -v        # B5: Delegate Mode
pytest tests/test_auto_spawn.py -v           # B6: Auto-Spawn Panes
pytest tests/test_team_start_api.py -v       # B6: Team Start API

# Spawn command tests
pytest tests/test_spawn.py -v               # Spawn CLI + core function
pytest tests/test_spawn_api.py -v           # Spawn API endpoint

# Run agent (interactive)
synapse claude
synapse codex
synapse gemini
synapse opencode
synapse copilot

# Run agent with name and role
synapse claude --name my-claude --role "code reviewer"
synapse gemini --name test-writer --role "test specialist"

# Skip interactive name/role setup
synapse claude --no-setup

# List agents (Rich TUI with event-driven auto-update)
synapse list                              # Show all running agents with auto-refresh on changes
# Interactive controls: 1-9 or ↑/↓ select agent, Enter/j jump to terminal, k kill (with confirm), / filter by TYPE/NAME/DIR, ESC clear, q quit

# Agent management by name
synapse kill my-claude                    # Graceful shutdown (default, 30s timeout)
synapse kill my-claude -f                 # Force kill (immediate SIGKILL)
synapse jump my-claude                    # Jump to terminal by name
synapse rename claude --name my-claude    # Assign name to agent
synapse rename my-claude --role reviewer  # Update role only
synapse rename my-claude --clear          # Clear name and role

# Task history (enabled by default, v0.3.13+)
synapse history list                      # Show recent task history
synapse history list --agent claude       # Filter by agent
synapse history show <task_id>            # Show task details
# To disable: SYNAPSE_HISTORY_ENABLED=false synapse claude

# Instructions management (for --resume mode or recovery)
synapse instructions show                 # Show default instruction
synapse instructions show claude          # Show Claude-specific instruction
synapse instructions files claude         # List instruction files for Claude
synapse instructions send claude          # Send instructions to running Claude agent
synapse instructions send claude --preview # Preview without sending

# Skills management
synapse skills                            # Interactive TUI skill manager
synapse skills list                       # List all discovered skills
synapse skills list --scope synapse       # List central store skills only
synapse skills show <name>                # Show skill details
synapse skills delete <name> [--force]    # Delete a skill
synapse skills move <name> --to <scope>   # Move skill between scopes
synapse skills deploy <name> --agent claude,codex --scope user  # Deploy from central store
synapse skills import <name>              # Import to central store (~/.synapse/skills/)
synapse skills add <repo>                 # Install from repo (npx skills wrapper)
synapse skills create                     # Show guided skill creation steps
synapse skills set list                   # List skill sets
synapse skills set show <name>            # Show skill set details

# Settings management (interactive TUI)
synapse config                            # Interactive config editor
synapse config --scope user               # Edit user settings directly
synapse config --scope project            # Edit project settings directly
synapse config show                       # Show merged settings (read-only)
synapse config show --scope user          # Show user settings only

# Send messages (--response waits for reply, --no-response sends only)
# Target formats: name (my-claude), agent-type (claude), type-port (claude-8100), full-id (synapse-claude-8100)
synapse send my-claude "Review this code" --from synapse-gemini-8110 --response
synapse send gemini "Analyze this" --from synapse-claude-8100 --response
synapse send codex "Process this" --from synapse-claude-8100 --no-response

# Send to specific instance when multiple agents of same type exist
synapse send claude-8100 "Hello" --from synapse-claude-8101

# Send long messages via file or stdin (avoids ARG_MAX shell limits)
synapse send claude --message-file /tmp/review.txt --no-response
echo "long message" | synapse send claude --stdin --no-response
synapse send claude --message-file - --no-response   # '-' reads from stdin

# Attach files to messages
synapse send claude "Review this" --attach src/main.py --no-response
synapse send claude "Review these" --attach src/a.py --attach src/b.py --no-response

# Messages >100KB are automatically written to temp files (configurable via SYNAPSE_SEND_MESSAGE_THRESHOLD)

# Reply to a received message (auto-routes to sender via reply tracking)
synapse reply "Result here"

# Reply with explicit sender ID (for sandboxed environments like Codex)
synapse reply "Result here" --from synapse-codex-8121

# Reply to a specific sender when multiple are pending
synapse reply "Result here" --to synapse-claude-8100

# Trace a task across history and file modifications
synapse trace <task_id>                   # Show task history + file-safety records

# Low-level A2A tool
python -m synapse.tools.a2a list
python -m synapse.tools.a2a send --target claude --priority 1 "message"

# Agent Teams: Shared Task Board (B1)
synapse tasks list                        # List all tasks
synapse tasks list --status pending       # Filter by status
synapse tasks create "Task subject" -d "description"  # Create task
synapse tasks assign <task_id> claude     # Assign task to agent
synapse tasks complete <task_id>          # Mark task completed

# Agent Teams: Plan Approval (B3)
synapse approve <task_id>                 # Approve a plan
synapse reject <task_id> --reason "Use different approach"  # Reject with reason

# Agent Teams: Delegate Mode (B5)
synapse claude --delegate-mode            # Start as coordinator (no file editing)
synapse claude --delegate-mode --name coordinator --role "task manager"

# Agent Teams: Auto-Spawn Panes (B6, requires tmux/iTerm2/Terminal.app/zellij)
# Default: 1st agent takes over current terminal, others get new panes
synapse team start claude gemini          # claude=here, gemini=new pane
synapse team start claude gemini codex --layout horizontal  # Custom layout
synapse team start claude:Reviewer:code-review:reviewer gemini:Searcher  # Extended spec
synapse team start claude gemini --all-new  # All agents in new panes (current terminal stays)

# Agent Teams: Team Start via A2A API (B6)
# POST /team/start - agents can spawn teams programmatically
curl -X POST http://localhost:8100/team/start \
  -H "Content-Type: application/json" \
  -d '{"agents": ["gemini", "codex"], "layout": "split"}'

# Spawn single agent in new pane (requires tmux/iTerm2/Terminal.app/Ghostty/zellij)
synapse spawn claude                          # Spawn Claude in a new pane
synapse spawn gemini --port 8115              # Spawn with explicit port
synapse spawn claude --name Tester --role "test writer"  # With name/role
synapse spawn claude --terminal tmux          # Use specific terminal

# Spawn via A2A API (agents can spawn other agents programmatically)
# POST /spawn - returns {agent_id, port, terminal_used, status}
curl -X POST http://localhost:8100/spawn \
  -H "Content-Type: application/json" \
  -d '{"profile": "gemini", "name": "Helper"}'
```

## Target Resolution

When using `synapse send`, `synapse kill`, `synapse jump`, or `synapse rename`, targets are resolved in priority order:

1. **Custom name** (highest priority): `my-claude`
2. **Full agent ID**: `synapse-claude-8100`
3. **Type-port shorthand**: `claude-8100`
4. **Agent type** (only if single instance): `claude`

Custom names are case-sensitive. Agent type resolution is fuzzy (partial match).

**Name vs ID:**
- **Display/Prompts**: Shows name if set, otherwise ID (e.g., `Kill my-claude (PID: 1234)?`)
- **Internal processing**: Always uses agent ID (`synapse-claude-8100`)
- **`synapse list` NAME column**: Shows custom name if set, otherwise agent type

## Core Design Principle

**A2A Protocol First**: All communication must use Message/Part + Task format per Google A2A spec.

- Standard endpoints: `/.well-known/agent.json`, `/tasks/send`, `/tasks/{id}`
- Extensions use `x-` prefix (e.g., `x-synapse-context`)
- PTY output format: `A2A: <message>`

Reference: https://developers.googleblog.com/en/a2a-a-new-era-of-agent-interoperability/

## Architecture

```
synapse/
├── cli.py           # Entry point, profile loading, interactive mode orchestration
├── controller.py    # TerminalController: PTY management, READY/PROCESSING detection
├── server.py        # FastAPI server with A2A endpoints
├── a2a_compat.py    # A2A protocol implementation (Agent Card, Task API)
├── a2a_client.py    # Client for communicating with other A2A agents
├── registry.py      # File-based agent discovery (~/.a2a/registry/)
├── agent_context.py # Initial instructions generation for agents
├── history.py       # Session history persistence using SQLite
├── task_board.py    # Shared Task Board: SQLite-based task coordination (B1)
├── hooks.py         # Quality Gates: Hook mechanism for status transitions (B2)
├── approval.py      # Plan Approval: instruction approval + plan mode (B3)
├── spawn.py         # Single-agent pane spawning (synapse spawn + POST /spawn)
├── skills.py        # Skill discovery, deploy, import, skill sets
├── paths.py         # Centralized path management (env var overrides)
├── commands/        # CLI command implementations
│   ├── instructions.py    # synapse instructions command
│   ├── list.py            # synapse list command
│   ├── skill_manager.py   # synapse skills command (TUI + non-interactive)
│   └── start.py           # synapse start command
└── profiles/        # YAML configs per agent type (claude.yaml, codex.yaml, etc.)
```

## Key Flows

**Startup Sequence**:

1. Load profile YAML → 2. Register in AgentRegistry → 3. Start FastAPI server (background thread) → 4. `pty.spawn()` CLI → 5. On first IDLE, send initial instructions via `A2A:` prefix (includes role section if set, skill set details if selected)

**Agent Status System**:

Agents use a five-state status system:
- **READY** (green): Agent is idle, waiting for user input
- **WAITING** (cyan): Agent is showing selection UI, waiting for user choice (detected via regex)
- **PROCESSING** (yellow): Agent is actively processing (startup, handling requests, or producing output)
- **DONE** (blue): Task completed (auto-transitions to READY after 10 seconds)
- **SHUTTING_DOWN** (red): Graceful shutdown in progress (B4)

Status transitions:
- Initial: `PROCESSING` (startup in progress)
- On idle detection: `PROCESSING` → `READY` (agent is ready for input)
- On output/activity: `READY` → `PROCESSING` (agent is handling work)
- On selection UI detected: → `WAITING` (agent waiting for user choice)
- On task completion: → `DONE` (via `set_done()` call)
- After 10s idle in DONE: `DONE` → `READY`
- On shutdown request: → `SHUTTING_DOWN` (via graceful kill, B4)

Dead processes are automatically cleaned up from the registry and not displayed in `synapse list`.

**Terminal Jump** (in `synapse list`):
- Use ↑/↓ to select agent row
- Press Enter or j to jump to that agent's terminal window
- Supported terminals: iTerm2, Terminal.app, Ghostty, VS Code, tmux, Zellij

## Profile Configuration Notes

### Multi-Strategy Idle Detection

Synapse now supports configurable idle detection strategies per agent type in YAML profiles:

#### Detection Strategies

1. **pattern**: Regex-based detection (original behavior)
   - Checks for recurring text patterns in PTY output
   - Best for agents with consistent prompts (Gemini, Codex)

2. **timeout**: Timeout-based detection
   - Detects idle when no output received for N seconds
   - Fallback for agents without consistent prompts

3. **hybrid**: Two-phase detection (pattern then timeout)
   - Uses pattern for first idle detection
   - Falls back to timeout for subsequent idles
   - Ideal for Claude Code which has one-time initialization sequences

#### Configuration Structure

```yaml
idle_detection:
  strategy: "pattern"          # "pattern" | "timeout" | "hybrid"
  pattern: "(> |\\*)"          # Regex pattern or special name
  pattern_use: "always"        # "always" | "startup_only"
  timeout: 1.5                 # Seconds of no output to trigger idle
```

### Claude Code (Ink TUI) - Timeout Strategy

Claude Code uses Ink-based TUI with BRACKETED_PASTE_MODE sequence:

```yaml
# synapse/profiles/claude.yaml
submit_sequence: "\r"          # CR required (not LF or CRLF)

idle_detection:
  strategy: "timeout"          # Pure timeout-based detection
  timeout: 0.5                 # 500ms no output = idle
```

**Why timeout-only?**: BRACKETED_PASTE_MODE only appears once during TUI initialization, not on subsequent idle transitions. Since the pattern is unreliable for detecting ongoing idle states, we use pure timeout-based detection (0.5s) which reliably detects when Claude Code is waiting for input.

- **Submit Sequence**: `\r` (CR only) is required for v2.0.76+. CRLF does not work.
- See `docs/HANDOFF_CLAUDE_ENTER_KEY_ISSUE.md` for technical details.

### Gemini - Hybrid Strategy

Gemini uses hybrid strategy - pattern for first idle (UI ready), timeout for subsequent:

```yaml
# synapse/profiles/gemini.yaml
idle_detection:
  strategy: "hybrid"
  pattern: "BRACKETED_PASTE_MODE"  # ESC[?2004h = TUI input ready
  pattern_use: "startup_only"      # Only use pattern for first READY detection
  timeout: 3.0                     # 3.0 seconds of no output = idle (after first)
```

**Why hybrid?**: BRACKETED_PASTE_MODE indicates the TUI input area is ready. Pattern detection is used only for startup; subsequent idle states use timeout-based detection for reliability.

### Codex - Pattern Strategy

Codex uses a consistent prompt character:

```yaml
# synapse/profiles/codex.yaml
idle_detection:
  strategy: "pattern"
  pattern: "›"                 # Codex prompt
  timeout: 1.5                 # Fallback if pattern fails
```

### OpenCode - Timeout Strategy

OpenCode uses Bubble Tea TUI (similar to Claude Code):

```yaml
# synapse/profiles/opencode.yaml
idle_detection:
  strategy: "timeout"
  pattern_use: "never"         # No pattern detection for OpenCode
  timeout: 1.0                 # 1.0 second of no output = idle
```

**Why timeout?**: OpenCode uses Bubble Tea for its TUI, which doesn't have consistent prompt patterns. Timeout-based detection (1.0s) reliably detects when OpenCode is waiting for input.

### GitHub Copilot CLI - Timeout Strategy

GitHub Copilot CLI uses interactive TUI (similar to Claude Code):

```yaml
# synapse/profiles/copilot.yaml
idle_detection:
  strategy: "timeout"
  pattern_use: "never"         # No pattern detection for Copilot CLI
  timeout: 0.5                 # 500ms of no output = idle
```

**Why timeout?**: GitHub Copilot CLI uses an interactive TUI without consistent prompt patterns. Timeout-based detection (0.5s) reliably detects when Copilot CLI is waiting for input.

## Port Ranges

| Agent    | Ports     |
| -------- | --------- |
| Claude   | 8100-8109 |
| Gemini   | 8110-8119 |
| Codex    | 8120-8129 |
| OpenCode | 8130-8139 |
| Copilot  | 8140-8149 |

## Storage

```
~/.a2a/registry/     # Running agents (auto-cleaned)
~/.a2a/external/     # External A2A agents (persistent)
~/.synapse/skills/   # Central skill store (SYNAPSE scope)
~/.synapse/logs/     # Log files
```

## Testing Registry & Status Updates

### Manual Verification of `synapse list`

To verify the registry status update system works correctly:

```bash
# Terminal 1: Start a Claude agent
synapse claude

# Terminal 2: Start another agent
synapse gemini

# Terminal 3: Monitor agent status changes
synapse list
# Uses file watcher (inotify/fsevents) for instant updates when registry changes

# Expected behavior:
# 1. Agent starts in PROCESSING status (initializing)
# 2. After initialization completes, status changes to READY
# 3. Status updates instantly when registry files change
# 4. No "flickering" where agent disappears/reappears
# 5. No stale status values (always shows current state)
# 6. TRANSPORT column shows UDS→/→UDS or TCP→/→TCP during communication
```

**Observing TRANSPORT column**:
```bash
# In Terminal 1 (Claude), send message to Gemini:
synapse send gemini "hello" --from synapse-claude-8100

# In Terminal 3, observe:
# - Claude shows "UDS→" (sending via UDS)
# - Gemini shows "→UDS" (receiving via UDS)
# - After completion, both return to "-"
```

### Verifying Bug Fixes

**Bug #1 (Race Conditions)**:
- Start multiple agents simultaneously
- Status updates should be consistent (no lost updates)
- Each agent's status visible in list mode without flicker

**Bug #2 (Silent Failures)**:
- Check logs: `tail -f ~/.synapse/logs/*.log`
- If update fails, error message appears: `"Failed to update status for ..."`
- Registry file permissions issues are logged

**Bug #3 (Partial JSON)**:
- With atomic writes, agents never flicker
- Agent always visible once started (no temporary disappearances)
- Temp files (`.*.json.tmp`) should not appear in `~/.a2a/registry/`

### Running Test Suite

```bash
# All tests (should pass)
pytest

# Specific tests for registry/status system
pytest tests/test_cmd_list_watch.py -v   # List command tests
pytest tests/test_registry.py -v
pytest tests/test_controller_registry_sync.py -v

# Tests for agent naming (v0.3.11)
pytest tests/test_agent_naming.py -v     # Name/role registry tests
pytest tests/test_cli_kill_jump.py -v    # Kill/jump/rename commands
pytest tests/test_tools_a2a_resolve.py -v # Target resolution tests

# Agent Teams feature tests (B1-B6)
pytest tests/test_task_board.py tests/test_task_board_api.py tests/test_cli_tasks.py -v  # B1
pytest tests/test_hooks.py -v                # B2
pytest tests/test_plan_approval.py -v        # B3
pytest tests/test_graceful_shutdown.py -v    # B4
pytest tests/test_delegate_mode.py -v        # B5
pytest tests/test_auto_spawn.py -v           # B6

# Tests specifically for bug fixes
pytest tests/test_cmd_list_watch.py::TestSilentFailures -v
pytest tests/test_cmd_list_watch.py::TestRegistryRaceConditions -v
pytest tests/test_cmd_list_watch.py::TestPartialJSONRead -v
pytest tests/test_cmd_list_watch.py::TestFileWatcher -v
```

## Multi-Agent Management with History

### History Tracking

History is enabled by default (v0.3.13+). Just start agents normally:

```bash
synapse claude
synapse gemini
synapse codex
synapse opencode

# To disable history:
SYNAPSE_HISTORY_ENABLED=false synapse claude
```

### Monitoring Delegated Tasks

When orchestrating multiple agents, use these commands to track progress:

```bash
# Real-time agent status (auto-updates on registry changes)
synapse list

# Task history by agent
synapse history list --agent gemini
synapse history list --agent codex

# Task details
synapse history show <task_id>

# Statistics
synapse history stats
synapse history stats --agent gemini
```

### Delegation Workflow

1. **Check agent availability**:
   ```bash
   synapse list
   ```

2. **Delegate task**:
   ```bash
synapse send gemini "Write tests for X" --priority 3 --from synapse-claude-8100 --no-response
   ```

3. **Monitor progress**:
   ```bash
   synapse list                            # Auto-updates on changes
   git status && git log --oneline -5
   ```

4. **Send follow-up** (if needed):
   ```bash
synapse send gemini "Status update?" --priority 4 --from synapse-claude-8100 --response
   ```

5. **Review completion**:
   ```bash
   synapse history list --agent gemini --limit 5
   ```

### Priority Levels

| Priority | Use Case |
|----------|----------|
| 1-2 | Low priority, background tasks |
| 3 | Normal tasks |
| 4 | Urgent follow-ups |
| 5 | Critical/emergency tasks |

### Best Practices

- Always check `synapse list` before sending tasks to ensure agents are READY
- Use `git log` and `git status` to verify completed work
- Track task IDs from responses for follow-up
- Use `--priority 4-5` for urgent status checks
- Monitor `synapse list` during active orchestration (auto-updates on registry changes)
