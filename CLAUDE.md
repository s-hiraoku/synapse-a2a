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
- When delegating to other agents, they must work on the same branch

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

# Run agent (interactive)
synapse claude
synapse codex
synapse gemini
synapse opencode
synapse copilot

# List agents (Rich TUI with event-driven auto-update)
synapse list                              # Show all running agents with auto-refresh on changes
# Interactive controls: 1-9 or ↑/↓ select agent, Enter/j jump to terminal, ESC clear selection, q quit

# Task history (enable with SYNAPSE_HISTORY_ENABLED=true)
SYNAPSE_HISTORY_ENABLED=true synapse claude
synapse history list                      # Show recent task history
synapse history list --agent claude       # Filter by agent
synapse history show <task_id>            # Show task details

# Instructions management (for --resume mode or recovery)
synapse instructions show                 # Show default instruction
synapse instructions show claude          # Show Claude-specific instruction
synapse instructions files claude         # List instruction files for Claude
synapse instructions send claude          # Send instructions to running Claude agent
synapse instructions send claude --preview # Preview without sending

# Settings management (interactive TUI)
synapse config                            # Interactive config editor
synapse config --scope user               # Edit user settings directly
synapse config --scope project            # Edit project settings directly
synapse config show                       # Show merged settings (read-only)
synapse config show --scope user          # Show user settings only

# Send messages (--response waits for reply, --no-response sends only)
# Target formats: agent-type (claude), type-port (claude-8100), full-id (synapse-claude-8100)
synapse send gemini "Analyze this" --from claude --response
synapse send codex "Process this" --from claude --no-response

# Send to specific instance when multiple agents of same type exist
synapse send claude-8100 "Hello" --from synapse-claude-8101

# Reply to a --response request (receiver MUST use --reply-to)
synapse send claude "Result here" --reply-to <task_id> --from gemini

# Low-level A2A tool
python -m synapse.tools.a2a list
python -m synapse.tools.a2a send --target claude --priority 1 "message"
```

## Core Design Principle

**A2A Protocol First**: All communication must use Message/Part + Task format per Google A2A spec.

- Standard endpoints: `/.well-known/agent.json`, `/tasks/send`, `/tasks/{id}`
- Extensions use `x-` prefix (e.g., `x-synapse-context`)
- PTY output format: `[A2A:<task_id>:<sender_id>] <message>`

Reference: https://developers.googleblog.com/en/a2a-a-new-era-of-agent-interoperability/

## Architecture

```
synapse/
├── cli.py           # Entry point, profile loading, interactive mode orchestration
├── controller.py    # TerminalController: PTY management, READY/PROCESSING detection
├── server.py        # FastAPI server with A2A endpoints
├── a2a_compat.py    # A2A protocol implementation (Agent Card, Task API)
├── a2a_client.py    # Client for communicating with other A2A agents
├── input_router.py  # @Agent pattern detection and routing
├── registry.py      # File-based agent discovery (~/.a2a/registry/)
├── agent_context.py # Initial instructions generation for agents
├── history.py       # Session history persistence using SQLite
├── commands/        # CLI command implementations
│   ├── instructions.py  # synapse instructions command
│   ├── list.py          # synapse list command
│   └── start.py         # synapse start command
└── profiles/        # YAML configs per agent type (claude.yaml, codex.yaml, etc.)
```

## Key Flows

**Startup Sequence**:

1. Load profile YAML → 2. Register in AgentRegistry → 3. Start FastAPI server (background thread) → 4. `pty.spawn()` CLI → 5. On first IDLE, send initial instructions via `[A2A:id:synapse-system]` prefix

**@Agent Routing**:
User types `@codex review this` → InputRouter detects pattern → A2AClient.send_to_local() → POST /tasks/send-priority to target agent

**Agent Status System**:

Agents use a four-state status system:
- **READY** (green): Agent is idle, waiting for user input
- **WAITING** (cyan): Agent is showing selection UI, waiting for user choice (detected via regex)
- **PROCESSING** (yellow): Agent is actively processing (startup, handling requests, or producing output)
- **DONE** (blue): Task completed (auto-transitions to READY after 10 seconds)

Status transitions:
- Initial: `PROCESSING` (startup in progress)
- On idle detection: `PROCESSING` → `READY` (agent is ready for input)
- On output/activity: `READY` → `PROCESSING` (agent is handling work)
- On selection UI detected: → `WAITING` (agent waiting for user choice)
- On task completion: → `DONE` (via `set_done()` call)
- After 10s idle in DONE: `DONE` → `READY`

Dead processes are automatically cleaned up from the registry and not displayed in `synapse list`.

**Terminal Jump** (in `synapse list --watch`):
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

### Gemini - Pattern Strategy

Gemini uses consistent text prompts:

```yaml
# synapse/profiles/gemini.yaml
idle_detection:
  strategy: "pattern"
  pattern: "(> |\\*)"          # Gemini prompt patterns
  timeout: 1.5                 # Fallback if pattern fails
```

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
@gemini hello

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

# Tests specifically for bug fixes
pytest tests/test_cmd_list_watch.py::TestSilentFailures -v
pytest tests/test_cmd_list_watch.py::TestRegistryRaceConditions -v
pytest tests/test_cmd_list_watch.py::TestPartialJSONRead -v
pytest tests/test_cmd_list_watch.py::TestFileWatcher -v
```

## Multi-Agent Management with History

### Enabling History Tracking

```bash
# Start agents with history enabled
SYNAPSE_HISTORY_ENABLED=true synapse claude
SYNAPSE_HISTORY_ENABLED=true synapse gemini
SYNAPSE_HISTORY_ENABLED=true synapse codex
SYNAPSE_HISTORY_ENABLED=true synapse opencode
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
   synapse send gemini "Write tests for X" --priority 3 --from claude --no-response
   ```

3. **Monitor progress**:
   ```bash
   synapse list                            # Auto-updates on changes
   git status && git log --oneline -5
   ```

4. **Send follow-up** (if needed):
   ```bash
   synapse send gemini "Status update?" --priority 4 --from claude --response
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

- Always check `synapse list` before delegating to ensure agents are READY
- Use `git log` and `git status` to verify completed work
- Track task IDs from delegation responses for follow-up
- Use `--priority 4-5` for urgent status checks
- Monitor `synapse list` during active orchestration (auto-updates on registry changes)
