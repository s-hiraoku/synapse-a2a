# Synapse A2A Reference

CLAUDE.md から分離した詳細リファレンス。

## Full Command Reference

```bash
# Run agent
synapse claude
synapse codex
synapse gemini
synapse opencode
synapse copilot

# With name/role
synapse claude --name my-claude --role "code reviewer"
synapse claude --agent calm-lead              # Saved agent definition
synapse claude --role "@./roles/reviewer.md"   # Role from file
synapse claude --no-setup                      # Skip interactive setup

# Agent management
synapse list                                   # Rich TUI with auto-refresh
synapse list --json                            # JSON array output for AI/scripts
synapse status my-claude                       # Detailed single-agent status
synapse kill my-claude                         # Graceful shutdown
synapse kill my-claude -f                      # Force kill
synapse jump my-claude                         # Jump to terminal
synapse rename claude --name my-claude         # Assign name

# Messaging
synapse send my-claude "Review this" --wait    # Synchronous
synapse send gemini "Fix this" --silent        # Fire-and-forget
synapse send claude "Update" --notify          # Async notification (default)
synapse send claude --message-file /tmp/msg.txt --silent  # From file
synapse send claude "Review" --attach src/main.py --wait  # With file
synapse send claude "Implement auth" --task    # Auto-create linked board task
synapse send claude "Fix bug" -T               # Short form of --task
synapse reply "Result here"                    # Auto-route to sender
synapse broadcast "Status check"               # All agents in CWD
synapse interrupt claude "Stop and review"      # Soft interrupt (priority 4)

# Task Board (mandatory for delegations — create+assign before synapse send)
synapse tasks list
synapse tasks create "Subject" -d "description" --priority 4
synapse tasks assign <task_id> claude
synapse tasks complete <task_id>
synapse tasks purge                            # Delete all completed/failed tasks
synapse tasks purge --status completed         # Delete only completed tasks
synapse approve <task_id>
synapse reject <task_id> --reason "reason"

# History
synapse history list --agent claude
synapse history show <task_id>
synapse trace <task_id>

# Shared Memory
synapse memory save <key> <content> [--tags tag1,tag2]
synapse memory list [--author <id>] [--tags <tags>]
synapse memory search <query>

# Canvas
synapse canvas serve [--port 3000] [--no-open]
synapse canvas post mermaid "graph TD; A-->B" --title "Flow"
synapse canvas post markdown "## Doc" --title "Doc"
synapse canvas post-raw '{"content":{"format":"code","body":"print(1)","x_title":"Demo"}}'
synapse canvas briefing '{"content":[...],"sections":[...]}'
synapse canvas link "https://example.com/article" --title "Reference"
synapse canvas list [--mine] [--search TERM]
synapse canvas open [--port 3000]
synapse canvas status [--port 3000]
synapse canvas stop [--port 3000]

# Session/Workflow
synapse session save <name>
synapse session restore <name>
synapse workflow run <name>

# Spawn/Teams
synapse spawn claude --name Tester --role "test writer"
synapse spawn claude --worktree feature-auth
synapse team start claude gemini
synapse team start claude gemini --worktree

# Skills
synapse skills list
synapse skills show <name>
synapse skills deploy <name> --agent claude

# Config
synapse config
synapse init
synapse reset

# MCP Bootstrap
synapse mcp serve                          # Start MCP server over stdio
synapse mcp serve --agent-id synapse-claude-8100 --agent-type claude --port 8100

# MCP Tools (available via JSON-RPC tools/call)
# bootstrap_agent    — Returns runtime context (agent_id, port, features)
# list_agents        — List all running Synapse agents with status and connection info
#                      Optional input: {"status": "READY"}  (filter by status)

# Auth
synapse auth setup
```

## Target Resolution

Targets resolve in priority order:
1. Custom name: `my-claude`
2. Full Runtime ID: `synapse-claude-8100`
3. Type-port shorthand: `claude-8100`
4. Agent type (single instance only): `claude`

## Profile Configuration

### Idle Detection Strategies

- **pattern**: Regex-based (Gemini, Codex)
- **timeout**: No-output timeout (OpenCode, Copilot)
- **hybrid**: Pattern first, then timeout (Claude Code, Gemini)

```yaml
idle_detection:
  strategy: "hybrid"
  pattern: "BRACKETED_PASTE_MODE"
  pattern_use: "startup_only"
  timeout: 0.5
  task_protection_timeout: 15

waiting_detection:
  regex: "\\[Y/n\\]"
  require_idle: true
  idle_timeout: 0.3
  waiting_expiry: 10
```

### Agent-Specific Notes

- **Claude Code**: `submit_sequence: "\r"` (CR only). Separate `os.write()` calls for data and submit with `write_delay`.
- **Gemini**: Hybrid strategy with 3.0s timeout fallback.
- **Codex**: Timeout strategy, 3.0s.
- **OpenCode**: Timeout strategy, 1.0s (Bubble Tea TUI).
- **Copilot**: Timeout strategy, 0.5s. `write_delay: 0.5` for Ink TUI rendering. `bracketed_paste: true` for Ink's `usePaste` hook. `submit_retry_delay: 0.15` as the first Enter safety net, plus bounded submit confirmation (`submit_confirm_timeout`, `submit_confirm_poll_interval`, `submit_confirm_retries`) when injected text appears to remain pending.

## Agent Status System

States: READY → PROCESSING → DONE → READY (auto after 10s), WAITING, SHUTTING_DOWN

Compound signal: PROCESSING→READY suppressed when `task_active` flag set or file locks held.

## Readiness Gate

`/tasks/send` blocked until agent completes initialization. Timeout: 30s. Bypasses: priority 5 and reply messages.

## Storage

```
~/.a2a/registry/        # Running agents
~/.a2a/reply/            # Reply targets
~/.synapse/skills/       # Central skill store
~/.synapse/agents/       # Saved agent definitions (user)
~/.synapse/sessions/     # Sessions (user)
~/.synapse/workflows/    # Workflows (user)
~/.synapse/canvas.pid    # Canvas server PID file (stale process detection)
.synapse/                # Project-local (canvas.db, memory.db, file_safety.db, task_board.db, etc.)
```

## Testing

See test files in `tests/` directory. Key test groups:

- Core: `test_a2a_compat.py`, `test_registry.py`, `test_controller_registry_sync.py`
- Canvas: `test_canvas_store.py`, `test_canvas_protocol.py`, `test_canvas_server.py`
- Agent Teams: `test_task_board.py`, `test_hooks.py`, `test_plan_approval.py`, `test_delegate_mode.py`
- Spawn: `test_spawn.py`, `test_auto_spawn.py`, `test_auto_layout.py`
- Memory: `test_shared_memory.py`, `test_cli_memory.py`
- MCP: `test_mcp_bootstrap.py`, `test_mcp_list_agents.py`
- Status: `test_cmd_status.py`, `test_compound_signal.py`

## Priority Levels

| Priority | Use Case |
|----------|----------|
| 1-2 | Background tasks |
| 3 | Normal |
| 4 | Urgent |
| 5 | Emergency |
