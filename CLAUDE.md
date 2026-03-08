# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Flow (Mandatory)

1. When receiving a feature request or modification, write tests first
2. Present the tests to confirm the specification
3. Proceed to implementation only after confirmation
4. Adjust implementation until all tests pass

### Branch Management Rules

- **Default base branch is `main`** — All PRs should target `main` unless explicitly instructed otherwise
- **Do NOT change branches during active work** - Stay on the current branch until the task is complete
- **If branch change is needed**, always ask the user for confirmation first
- Before switching branches, ensure all changes are committed or stashed
- When receiving tasks from other agents, work on the same branch

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
pytest tests/test_skill_structure.py -v   # Skill directory structure validation
pytest tests/test_cmd_skill_manager.py -v # Skill manager command tests
pytest tests/test_send_message_file.py -v # Send --message-file/--stdin/auto-temp tests
pytest tests/test_file_attachment.py -v   # --attach file attachment tests
pytest tests/test_cmd_trace.py -v         # synapse trace command tests
pytest tests/test_interactive_setup.py -v # Interactive setup + core skills tests
pytest tests/test_learning_mode.py -v    # Learning mode tests
pytest tests/test_completion_callback.py -v # Completion callback (--silent history update)
pytest tests/test_proactive_mode.py -v   # Proactive mode tests

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

# Saved agent definitions tests
pytest tests/test_agent_profiles.py -v      # AgentProfileStore core tests

# Spawn command tests
pytest tests/test_spawn.py -v               # Spawn CLI + core function
pytest tests/test_spawn_api.py -v           # Spawn API endpoint
pytest tests/test_tool_args_passthrough.py -v # tool_args passthrough (spawn/team)
pytest tests/test_copilot_spawn_fixes.py -v # Copilot spawn parsing + send UX fixes
pytest tests/test_auto_layout.py -v         # Spawn zone tiling + auto layout tests

# Worktree tests
pytest tests/test_worktree.py -v              # Worktree core operations (cleanup, change detection, base branch fallback)
pytest tests/test_worktree_cli.py -v          # Worktree CLI integration

# Status detection tests
pytest tests/test_cmd_status.py -v         # synapse status command
pytest tests/test_compound_signal.py -v    # Compound signal status detection + WAITING false positive fix
pytest tests/test_task_elapsed.py -v       # Task elapsed time display in CURRENT column

# Injection observability tests
pytest tests/test_injection_observability.py -v # INJECT/* structured logs

# Soft interrupt tests
pytest tests/test_soft_interrupt.py -v         # synapse interrupt CLI command

# Token/Cost tracking tests
pytest tests/test_token_parser.py -v           # Token parser registry + TokenUsage
pytest tests/test_token_stats.py -v            # Token statistics aggregation

# Shared Memory tests
pytest tests/test_shared_memory.py -v    # SharedMemory core tests
pytest tests/test_cli_memory.py -v       # CLI command tests  
pytest tests/test_memory_api.py -v       # API endpoint tests

# Session Save/Restore tests
pytest tests/test_session.py -v            # SessionStore core tests
pytest tests/test_cli_session.py -v        # Session CLI command tests
pytest tests/test_session_id_detector.py -v # Session ID detection tests

# Workflow tests
pytest tests/test_workflow.py -v           # WorkflowStore core tests
pytest tests/test_cli_workflow.py -v       # Workflow CLI command tests

# Run agent (interactive)
synapse claude
synapse codex
synapse gemini
synapse opencode
synapse copilot

# Run agent with name and role
synapse claude --name my-claude --role "code reviewer"
synapse gemini --name test-writer --role "test specialist"

# Run agent with saved agent definition (--agent / -A)
synapse claude --agent calm-lead
synapse claude --agent calm-lead --role "override role"

# Run agent with role from file (@prefix reads file content as role)
synapse claude --name reviewer --role "@./roles/reviewer.md"
synapse gemini --role "@~/my-roles/analyst.md"

# Skip interactive name/role setup
synapse claude --no-setup

# List agents (Rich TUI with event-driven auto-update)
synapse list                              # Show all running agents with auto-refresh on changes
# Interactive controls: 1-9 or ↑/↓ select agent, Enter/j jump to terminal, k kill (with confirm), / filter by TYPE/NAME/DIR, ESC clear, q quit

# Detailed agent status (single agent)
synapse status my-claude                  # Show detailed status (info, current task, history, file locks, task board)
synapse status claude-8100 --json         # JSON output for scripting

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

# Shared Memory (cross-agent knowledge sharing)
synapse memory save <key> <content> [--tags tag1,tag2] [--notify]
synapse memory list [--author <id>] [--tags <tags>] [--limit <n>]
synapse memory show <id_or_key>
synapse memory search <query>
synapse memory delete <id_or_key> [--force]
synapse memory stats

# Session Save/Restore
synapse session save <name> [--project|--user|--workdir <dir>]
synapse session list [--project|--user|--workdir <dir>]
synapse session show <name> [--project|--user|--workdir <dir>]
synapse session restore <name> [--project|--user|--workdir <dir>] [--worktree] [--resume] [-- tool_args...]
synapse session delete <name> [--project|--user|--workdir <dir>] [--force]
synapse session sessions                                       # List CLI tool sessions from filesystem
synapse session sessions --profile claude                      # Filter by profile
synapse session sessions --limit 10                            # Limit results

# Workflow (saved message sequences)
synapse workflow create <name> [--project|--user] [--force]     # Create workflow template YAML
synapse workflow list [--project|--user]                        # List saved workflows
synapse workflow show <name> [--project|--user]                 # Show workflow details
synapse workflow run <name> [--project|--user] [--dry-run] [--continue-on-error]  # Execute workflow steps
synapse workflow delete <name> [--project|--user] [--force]    # Delete a saved workflow

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
synapse skills create [name]              # Create new skill template
synapse skills set list                   # List skill sets
synapse skills set show <name>            # Show skill set details
synapse skills apply <target> <set_name>        # Apply skill set to running agent
synapse skills apply <target> <set_name> --dry-run  # Preview changes only

# Saved agent definitions (reusable templates for synapse spawn)
synapse agents list                       # List saved agent definitions
synapse agents show <id_or_name>          # Show details for a saved agent
synapse agents add <id> --name <name> --profile <profile> [--role <role>] [--skill-set <set>] [--scope project|user]
synapse agents delete <id_or_name>        # Delete a saved agent by ID or name

# Settings management (interactive TUI)
synapse config                            # Interactive config editor
synapse config --scope user               # Edit user settings directly
synapse config --scope project            # Edit project settings directly
synapse config show                       # Show merged settings (read-only)
synapse config show --scope user          # Show user settings only

# Initialize / reset configuration
synapse init                              # Interactive scope selection
synapse init --scope user                 # Create ~/.synapse/settings.json
synapse init --scope project              # Create ./.synapse/settings.json
synapse reset                             # Interactive scope selection
synapse reset --scope user                # Reset user settings to defaults
synapse reset --scope both -f             # Reset both without confirmation

# Soft interrupt (shorthand for send -p 4 --silent)
synapse interrupt claude "Stop and review"
                  # Interrupt an agent
synapse interrupt gemini "Check status"                            # --from auto-detected
synapse interrupt claude "Stop" --force                     # Bypass working_dir mismatch check

# Broadcast message to all agents in current directory
synapse broadcast "Status check"                           # Send to all agents
synapse broadcast "Urgent update" -p 4                     # Urgent broadcast
synapse broadcast "FYI only" --silent                      # Fire-and-forget

# API key authentication
synapse auth setup                        # Generate keys and show setup instructions
synapse auth generate-key                 # Generate a single API key
synapse auth generate-key -n 3 -e         # Generate 3 keys in export format

# Send messages (default is --notify: async notification on completion)
# Target formats: name (my-claude), agent-type (claude), type-port (claude-8100), Runtime ID (synapse-claude-8100)
# Note: --from is optional — auto-detected from SYNAPSE_AGENT_ID env var (set by Synapse at startup)
# Choosing response_mode:
#   --wait:   Task with result expected (question, review, analysis) - synchronous blocking
#   --notify: Async notification on completion (default)
#   --silent: Delegated task (fire-and-forget, no result needed)
#   If unsure, use --wait (safer default for blocking)
synapse send my-claude "Review this code" --wait
synapse send gemini "Analyze this" --wait
synapse send codex "Fix this bug and commit" --silent

# Working directory mismatch warning:
# synapse send checks if sender CWD matches target's working_dir.
# If different, it warns and exits with code 1. Use --force to bypass.
synapse send claude "Review this" --force  # Bypass working_dir check

# Send to specific instance when multiple agents of same type exist
synapse send claude-8100 "Hello"

# Send long messages via file or stdin (avoids ARG_MAX shell limits)
synapse send claude --message-file /tmp/review.txt --silent
echo "long message" | synapse send claude --stdin --silent
synapse send claude --message-file - --silent   # '-' reads from stdin

# Attach files to messages
synapse send claude "Review this" --attach src/main.py --wait
synapse send claude "Review these" --attach src/a.py --attach src/b.py --wait

# Messages >100KB are automatically written to temp files (configurable via SYNAPSE_SEND_MESSAGE_THRESHOLD)

# Reply to a received message (auto-routes to sender via reply tracking)
synapse reply "Result here"

# Reply with explicit sender ID (for sandboxed environments like Codex)
synapse reply "Result here" --from $SYNAPSE_AGENT_ID

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
synapse tasks create "Task subject" -d "description" --priority 4  # Create with priority (1-5, default 3)
synapse tasks assign <task_id> claude     # Assign task to agent
synapse tasks complete <task_id>          # Mark task completed
synapse tasks fail <task_id> [--reason "reason"]  # Mark task failed
synapse tasks reopen <task_id>            # Reopen completed/failed task → pending

# Agent Teams: Plan Approval (B3)
synapse approve <task_id>                 # Approve a plan
synapse reject <task_id> --reason "Use different approach"  # Reject with reason

# Agent Teams: Delegate Mode (B5)
synapse claude --delegate-mode            # Start as manager (no file editing)
synapse claude --delegate-mode --name manager --role "task manager"

# Agent Teams: Auto-Spawn Panes (B6, requires tmux/iTerm2/Terminal.app/Ghostty/zellij)
# Ghostty limitation: targets the focused window/tab — do not switch tabs during spawn
# Default: 1st agent takes over current terminal, others get new panes
synapse team start claude gemini          # claude=here, gemini=new pane
synapse team start claude gemini codex --layout horizontal  # Custom layout
synapse team start claude:Reviewer:code-review:reviewer gemini:Searcher  # Extended spec
synapse team start claude gemini --all-new  # All agents in new panes (current terminal stays)

# Pass tool-specific arguments after '--' (applied to all spawned agents)
synapse team start claude gemini -- --dangerously-skip-permissions

# Synapse-native worktree isolation (all agents get their own worktree)
synapse team start claude gemini --worktree
synapse team start claude gemini --worktree task  # name prefix (task-claude-0, task-gemini-1)

# Claude Code-specific worktree (legacy, Claude only — passed after --)
synapse team start claude -- --worktree

# Agent Teams: Team Start via A2A API (B6)
# POST /team/start - agents can spawn teams programmatically
curl -X POST http://localhost:8100/team/start \
  -H "Content-Type: application/json" \
  -d '{"agents": ["gemini", "codex"], "layout": "split"}'

# With tool_args (passed through to underlying CLI tool)
curl -X POST http://localhost:8100/team/start \
  -H "Content-Type: application/json" \
  -d '{"agents": ["gemini", "codex"], "tool_args": ["--dangerously-skip-permissions"]}'

# Spawn single agent in new pane (requires tmux/iTerm2/Terminal.app/Ghostty/zellij)
# Default layout is "auto" (spawn zone tiling — first spawn creates a zone pane, subsequent spawns tile within that zone)
synapse spawn claude                          # Spawn Claude in a new pane
synapse spawn steady-builder                  # Spawn by saved Agent ID
synapse spawn gemini --port 8115              # Spawn with explicit port
synapse spawn claude --name Tester --role "test writer"  # With name/role
synapse spawn claude --terminal tmux          # Use specific terminal

# Pass tool-specific arguments after '--' (e.g., skip Claude Code permissions)
synapse spawn claude -- --dangerously-skip-permissions

# Synapse-native worktree isolation (all agents, .synapse/worktrees/)
synapse spawn claude --worktree                   # Auto-generated name
synapse spawn claude --worktree feature-auth --name Auth --role "auth implementation"
synapse spawn gemini -w                           # Short flag

# Profile shortcut with worktree
synapse claude --worktree my-feature              # Start in worktree in current terminal
synapse gemini --worktree review --name Reviewer --role "code reviewer"

# Claude Code-specific worktree (legacy, Claude only — pass after --)
synapse spawn claude --name Worker --role "feature implementation" -- --worktree

# Spawn via A2A API (agents can spawn other agents programmatically)
# POST /spawn - returns {agent_id, port, terminal_used, status, worktree_path, worktree_branch, worktree_base_branch}
curl -X POST http://localhost:8100/spawn \
  -H "Content-Type: application/json" \
  -d '{"profile": "gemini", "name": "Helper"}'

# With worktree (auto-generated name)
curl -X POST http://localhost:8100/spawn \
  -H "Content-Type: application/json" \
  -d '{"profile": "gemini", "worktree": true}'

# With worktree (explicit name)
curl -X POST http://localhost:8100/spawn \
  -H "Content-Type: application/json" \
  -d '{"profile": "codex", "worktree": "helper-task"}'

# With tool_args
curl -X POST http://localhost:8100/spawn \
  -H "Content-Type: application/json" \
  -d '{"profile": "gemini", "tool_args": ["--dangerously-skip-permissions"]}'
```

## Target Resolution

When using `synapse send`, `synapse status`, `synapse interrupt`, `synapse kill`, `synapse jump`, `synapse rename`, or `synapse skills apply`, targets are resolved in priority order:

1. **Custom name** (highest priority): `my-claude`
2. **Full Runtime ID**: `synapse-claude-8100`
3. **Type-port shorthand**: `claude-8100`
4. **Agent type** (only if single instance): `claude`

Custom names are case-sensitive. Agent type resolution is fuzzy (partial match).

**Name vs ID:**
- **Display/Prompts**: Shows name if set, otherwise ID (e.g., `Kill my-claude (PID: 1234)?`)
- **Internal processing**: Always uses Runtime ID (`synapse-claude-8100`)
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
├── shared_memory.py # Cross-agent shared memory persistence and retrieval
├── task_board.py    # Shared Task Board: SQLite-based task coordination (B1)
├── hooks.py         # Quality Gates: Hook mechanism for status transitions (B2)
├── approval.py      # Plan Approval: instruction approval + plan mode (B3)
├── spawn.py         # Single-agent pane spawning (synapse spawn + POST /spawn)
├── worktree.py      # Synapse-native git worktree isolation for all agent types
├── session.py       # Session save/restore: team configuration snapshots
├── session_id_detector.py # Session ID auto-detection from CLI tool filesystems
├── workflow.py      # Workflow definitions: saved YAML-based message sequences
├── agent_profiles.py # Saved agent definitions: AgentProfileStore (synapse agents)
├── token_parser.py  # Token/cost tracking: TokenUsage dataclass + parse_tokens() registry
├── skills.py        # Skill discovery, deploy, import, skill sets
├── reply_target.py  # Reply target file-based persistence (~/.a2a/reply/)
├── paths.py         # Centralized path management (env var overrides)
├── commands/        # CLI command implementations
│   ├── instructions.py    # synapse instructions command
│   ├── list.py            # synapse list command
│   ├── status.py          # synapse status command (detailed single-agent status)
│   ├── skill_manager.py   # synapse skills command (TUI + non-interactive)
│   ├── session.py         # synapse session command
│   ├── workflow.py        # synapse workflow command
│   └── start.py           # synapse start command
└── profiles/        # YAML configs per agent type (claude.yaml, codex.yaml, etc.)

plugins/synapse-a2a/skills/synapse-a2a/   # Skills source of truth (plugin scope)
├── SKILL.md                               # Main skill definition (Progressive Disclosure)
└── references/                            # Detailed reference docs
    ├── api.md
    ├── collaboration.md
    ├── commands.md
    ├── examples.md
    ├── features.md
    ├── file-safety.md
    ├── messaging.md
    └── spawning.md

plugins/synapse-a2a/skills/synapse-manager/  # Multi-agent management skill
├── SKILL.md                                 # Delegation, monitoring, verification, feedback, review
├── references/                              # Detailed reference docs
│   ├── auto-approve-flags.md
│   ├── commands-quick-ref.md
│   ├── features-table.md
│   └── worker-guide.md
└── scripts/                                 # Reusable shell scripts
    ├── check_team_status.sh
    ├── regression_triage.sh
    └── wait_ready.sh

.claude/hooks/                             # Claude Code PostToolUse hooks
├── check-ci-trigger.sh                    # PostToolUse: triggers CI poll + PR status poll on git push / gh pr create
├── poll-ci.sh                             # Background: polls GitHub Actions CI status
└── poll-pr-status.sh                      # Background: polls merge conflict state + CodeRabbit reviews

.claude/skills/                            # Claude Code project-local skills
├── check-ci/SKILL.md                      # /check-ci: manual CI + conflict + review status check
├── fix-ci/SKILL.md                        # /fix-ci: auto-fix CI failures (lint, format, type-check, test)
├── fix-conflict/SKILL.md                  # /fix-conflict: auto-resolve merge conflicts
└── fix-review/SKILL.md                    # /fix-review: auto-fix CodeRabbit review comments

# Sync targets (auto-synced from plugins/ via sync-plugin-skills):
.claude/skills/synapse-a2a/      # Claude Code
.claude/skills/synapse-manager/  # Claude Code
.agents/skills/synapse-a2a/      # Codex / OpenCode / Copilot / Gemini
.agents/skills/synapse-manager/  # Codex / OpenCode / Copilot / Gemini
```

### Skill Update Rules

**`plugins/synapse-a2a/skills/` がスキルのソースオブトゥルース（`synapse-a2a`, `synapse-manager` 等）。** スキルを更新する際は必ず `plugins/` 側を編集し、`sync-plugin-skills` で `.claude/`, `.agents/` に同期すること。個別のエージェントディレクトリを直接編集してはならない。

**Progressive Disclosure パターン**: スキルは SKILL.md をコンパクトな概要（判断フレームワーク、コマンド早見表）に留め、詳細リファレンスは `references/` サブディレクトリに分離する。これによりトークン消費を抑えつつ、エージェントが必要に応じて詳細を参照できる。`synapse-manager` はさらに再利用可能なシェルスクリプトを `scripts/` に格納する。

### CI Automation: Hooks and Skills

Claude Code の PostToolUse フックと専用スキルにより、CI 監視・修復を自動化する。

**Hook チェーン**:
1. `check-ci-trigger.sh` (PostToolUse) — `git push` / `gh pr create` を検出し、以下をバックグラウンド起動:
   - `poll-ci.sh` — GitHub Actions の CI ステータスをポーリング
   - `poll-pr-status.sh` — マージコンフリクト状態 + CodeRabbit レビューをポーリング
2. `poll-pr-status.sh` は `systemMessage` JSON を出力してエージェントに通知:
   - コンフリクト検出時: `/fix-conflict` の実行を提案
   - CodeRabbit レビューコメント検出時: `/fix-review` の実行を提案

**Skills**:

| Skill | 用途 |
|-------|------|
| `/check-ci` | CI ステータス + コンフリクト + CodeRabbit レビューを手動確認。`--fix` で修復コマンドを提案 |
| `/fix-ci` | GitHub Actions の失敗を自動診断・修復（lint, format, type-check, test） |
| `/fix-conflict` | マージコンフリクトを自動解決（test merge → 解析 → resolve → verify → push） |
| `/fix-review` | CodeRabbit レビューコメントを自動修正（Bug/Style は自動修正、Suggestion は報告のみ） |

**設定** (`.claude/settings.json`):
- `hooks.PostToolUse` に `check-ci-trigger.sh` を登録
- `permissions.allow` に `Skill(fix-conflict)`, `Skill(fix-review)`, `Bash(gh api:*)`, `Bash(gh repo view:*)` を追加

## Key Flows

**Startup Sequence**:

1. Load profile YAML → 2. Register in AgentRegistry → 3. Start FastAPI server (background thread) → 4. `pty.spawn()` CLI → 5. On first IDLE, send initial instructions via `A2A:` prefix (long messages >200 chars are stored in files via `LongMessageStore` and a short file reference is sent to the PTY instead; includes role section if set, skill set details if selected) → 6. Mark agent as ready (opens the Readiness Gate)

**Readiness Gate**:

The `/tasks/send` and `/tasks/send-priority` endpoints are blocked by a readiness gate until the agent completes initialization (identity instruction sending). This prevents messages from being lost or garbled during startup.

- **Implementation**: `_send_task_message()` in `synapse/a2a_compat.py` waits on `controller._agent_ready_event` (a `threading.Event`)
- **Timeout**: `AGENT_READY_TIMEOUT = 30` seconds (defined in `synapse/config.py`). If the agent does not become ready within this period, the request is rejected.
- **HTTP response when not ready**: `503 Service Unavailable` with `Retry-After: 5` header
- **Bypasses**: Priority 5 (emergency interrupt) and reply messages (`in_reply_to`) skip the gate entirely
- **Controller attributes**: `_agent_ready` (bool), `_agent_ready_event` (threading.Event)

**Agent Status System**:

Agents use a five-state status system:
- **READY** (green): Agent is idle, waiting for user input
- **WAITING** (cyan): Agent is showing selection UI, waiting for user choice (detected via regex in `new_data` only)
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

**Compound signal status detection**: The `PROCESSING` → `READY` transition is suppressed when either of these signals is active, preventing premature READY detection during A2A task processing:
- **`task_active` flag**: Set via `set_task_active()` when an A2A task is received. Cleared by `clear_task_active()` when the task completes. Protected by `TASK_PROTECTION_TIMEOUT` (default 30s, configurable via `task_protection_timeout` in `idle_detection` profile config).
- **File locks**: If the agent holds file locks (via `FileSafetyManager`), READY transition is suppressed until locks are released.

**WAITING detection improvements**: WAITING status now only triggers from fresh PTY output (`new_data`), not from stale buffer content. WAITING auto-expires after `WAITING_EXPIRY_SECONDS` (default 10s, configurable via `waiting_expiry` in `waiting_detection` profile config) unless the pattern is still visible in the buffer tail (re-check on expiry). This eliminates false positives from old prompt patterns lingering in the output buffer.

**Elapsed time in CURRENT column**: When an agent is PROCESSING with a current task, `synapse list` shows elapsed time (e.g., "Review code (2m 15s)") using `task_received_at` timestamp.

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
  task_protection_timeout: 30  # Compound signal: seconds to suppress READY during A2A task (default: TASK_PROTECTION_TIMEOUT)

waiting_detection:
  regex: "\\[Y/n\\]"          # Regex to detect WAITING state (matched against new_data only)
  require_idle: true           # Require idle state before checking
  idle_timeout: 0.3            # Seconds of idle before checking waiting pattern
  waiting_expiry: 10           # Auto-clear WAITING after N seconds if pattern gone from buffer (default: WAITING_EXPIRY_SECONDS)
```

### Claude Code (Ink TUI) - Hybrid Strategy

Claude Code uses Ink-based TUI with BRACKETED_PASTE_MODE sequence:

```yaml
# synapse/profiles/claude.yaml
submit_sequence: "\r"          # CR required (not LF or CRLF)

idle_detection:
  strategy: "hybrid"           # Pattern first, then timeout
  pattern: "BRACKETED_PASTE_MODE"  # ESC[?2004h = ready for input
  pattern_use: "startup_only"  # Only check pattern at startup
  timeout: 0.5                 # 500ms no output = idle (fallback)
  task_protection_timeout: 15  # Suppress READY during A2A task

waiting_detection:
  regex: "^❯\\s+.+|^[☐☑]\\s+|\\[[Yy]/[Nn]\\]"
  require_idle: true
  idle_timeout: 0.3
  waiting_expiry: 10           # Auto-clear WAITING after 10s
```

**Why hybrid?**: BRACKETED_PASTE_MODE indicates the TUI input area is ready at startup. Pattern detection is used only for first IDLE; subsequent idle states use timeout-based detection (0.5s) for reliability.

- **Submit Sequence**: `\r` (CR only) is required for v2.0.76+. CRLF does not work.
- **Write Strategy**: Data and submit sequence are sent as **separate** `os.write()` calls with a configurable delay between them. The delay is controlled by the `write_delay` profile key (default: `WRITE_PROCESSING_DELAY` = 0.5s). This prevents bracketed paste mode (v2.1.52+) from trapping the CR inside the paste boundary. A `_write_all()` helper handles partial write retries.
- **WAITING detection**: Re-enabled with new_data-only matching and auto-expiry to prevent false positives.
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

waiting_detection:
  regex: "[●○]\\s+\\d+\\.|Allow (execution|once|for this session)"
  require_idle: true
  idle_timeout: 0.5
  waiting_expiry: 10               # Auto-clear WAITING after 10s
```

**Why hybrid?**: BRACKETED_PASTE_MODE indicates the TUI input area is ready. Pattern detection is used only for startup; subsequent idle states use timeout-based detection for reliability.

### Codex - Timeout Strategy

Codex uses timeout-based detection for reliability:

```yaml
# synapse/profiles/codex.yaml
idle_detection:
  strategy: "timeout"
  timeout: 3.0                 # 3.0 seconds of no output = idle
  task_protection_timeout: 30  # Suppress READY during A2A task

waiting_detection:
  regex: "^\\s+\\d+\\.\\s+.+$"
  require_idle: true
  idle_timeout: 0.5
  waiting_expiry: 10           # Auto-clear WAITING after 10s
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
submit_sequence: "\r"
write_delay: 0.5                 # 500ms delay — lets TUI finish rendering before CR

idle_detection:
  strategy: "timeout"
  pattern_use: "never"         # No pattern detection for Copilot CLI
  timeout: 0.5                 # 500ms of no output = idle
```

**Why timeout?**: GitHub Copilot CLI uses an interactive TUI without consistent prompt patterns. Timeout-based detection (0.5s) reliably detects when Copilot CLI is waiting for input.

**Why `write_delay: 0.5`?**: Copilot's Ink TUI collapses long pasted text into a shortcut display. CR sent during rendering is ignored. 0.5s gives the TUI time to finish rendering before CR is sent as a submit action.

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
~/.a2a/reply/        # Reply target persistence (auto-cleaned)
~/.a2a/external/     # External A2A agents (persistent)
~/.synapse/skills/   # Central skill store (SYNAPSE scope)
~/.synapse/agents/   # Saved agent definitions (user scope)
~/.synapse/logs/     # Log files
~/.synapse/sessions/ # Saved session configurations (user scope)
~/.synapse/workflows/ # Saved workflow definitions (user scope)

.synapse/agents/     # Saved agent definitions (project scope)
.synapse/worktrees/  # Synapse-native git worktrees (per-agent isolation)
.synapse/memory.db   # Shared memory database (project-local, SQLite WAL)
.synapse/file_safety.db  # File safety database (project-local)
.synapse/task_board.db   # Shared task board database (project-local)
.synapse/sessions/   # Saved session configurations (project scope)
.synapse/workflows/  # Saved workflow definitions (project scope)
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
synapse send gemini "hello"

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

# Detailed status for a specific agent (info, current task with elapsed time, history, file locks, task board)
synapse status my-claude
synapse status gemini --json              # JSON output for scripting

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

2. **Delegate task** (use `--wait` if result is needed, `--silent` for fire-and-forget, or default `--notify` for async):
   ```bash
synapse send gemini "Write tests for X and report results" --wait
   ```

3. **Monitor progress**:
   ```bash
   synapse list                            # Auto-updates on changes
   git status && git log --oneline -5
   ```

4. **Send follow-up** (if needed):
   ```bash
synapse send gemini "Status update?" --priority 4 --wait
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

### Proactive Collaboration

Agents are configured to proactively evaluate collaboration opportunities before starting any task. The default agent instructions (`.synapse/default.md`) include a structured decision framework:

**Collaboration Decision Framework:**

| Situation | Action |
|-----------|--------|
| Small task within your role | Do it yourself |
| Task outside your role, READY agent exists | Delegate with `synapse send --notify` or `--silent` |
| No suitable agent exists | Spawn one with `synapse spawn` |
| Stuck or need expertise | Ask for help with `synapse send --wait` |
| Completed a milestone | Report progress with `synapse send --silent` |
| Discovered a pattern/convention | Share via `synapse memory save` |

**Mandatory Collaboration Gate (STEP 3):**
For tasks with 3+ phases OR 10+ file changes, agents MUST go through a mandatory collaboration gate before writing any code:
1. Run `synapse list` to check available agents
2. Run `synapse memory search` to check shared knowledge
3. Create a task board entry with `synapse tasks create`
4. Build an Agent Assignment Plan (Phase / Agent / Rationale table) to distribute work
5. Spawn specialists if no suitable agent exists
6. Prefer a different model type for subtasks (diversity improves quality)

This gate ensures large tasks are parallelized across agents rather than executed sequentially by a single agent.

**Cross-Model Spawning Preference:**
When spawning or delegating, prefer a DIFFERENT model type (e.g., Claude spawns Gemini, Gemini spawns Codex). This provides:
1. Diverse model strengths for better quality
2. Distributed token usage across providers to avoid rate limits
3. Fresh perspectives for code review and problem solving

**Worker Autonomy:**
Worker agents (not just managers) can also spawn helpers and delegate subtasks:
```bash
# Worker spawns a helper for an independent subtask
synapse spawn gemini --worktree --name Helper --role "test writer"
synapse send Helper "Write tests for auth.py" --silent
# After completion:
synapse kill Helper -f
```

**Mandatory Cleanup:**
Any agent that spawns another agent MUST clean up after the work is done:
```bash
synapse kill <spawned-agent-name> -f
synapse list  # Verify cleanup
```

**Active Feature Usage:**
Agents are instructed to actively use all Synapse coordination features:
- **Task Board**: `synapse tasks create/assign/complete/fail` for transparent work tracking
- **Shared Memory**: `synapse memory save/search` for collective knowledge building
- **File Safety**: `synapse file-safety lock/unlock` before editing in multi-agent setups
- **Worktree**: `synapse spawn --worktree` for file isolation when multiple agents edit
- **Broadcast**: `synapse broadcast` for team-wide announcements
- **History**: `synapse history list/trace` to review past work

**Manager Awareness:**
Managers check existing agents with `synapse list` BEFORE spawning new ones. Assigning tasks to existing READY agents is more efficient than spawning (avoids startup overhead, instruction injection, and readiness wait).

### Best Practices

- Always check `synapse list` before sending tasks to ensure agents are READY
- Prefer existing READY agents over spawning new ones (less overhead)
- When spawning, prefer a different model type to distribute load and avoid rate limits
- Use `git log` and `git status` to verify completed work
- Track task IDs from responses for follow-up
- Use `--priority 4-5` for urgent status checks
- Monitor `synapse list` during active orchestration (auto-updates on registry changes)
- ALWAYS kill agents you spawn after their work is complete: `synapse kill <name> -f`
- Use `synapse memory save` to share discoveries and patterns across agents
- Use `synapse tasks` to make work visible to the whole team
