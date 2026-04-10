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
synapse kill my-claude                         # Graceful shutdown (auto-merges worktree branch)
synapse kill my-claude -f                      # Force kill (auto-merges worktree branch)
synapse kill my-claude --no-merge              # Skip worktree auto-merge
synapse jump my-claude                         # Jump to terminal
synapse rename claude --name my-claude         # Assign name

# Agent Summary
synapse set-summary my-claude "Frontend specialist handling React components"
synapse set-summary my-claude --auto           # Auto-generate from git context
synapse set-summary my-claude --clear          # Remove summary

# Messaging
synapse send claude "Update" --notify          # Async notification (default, recommended)
synapse send my-claude "Review this" --wait    # Synchronous (blocks caller)
synapse send gemini "Fix this" --silent        # Fire-and-forget
synapse send claude --message-file /tmp/msg.txt --silent  # From file
synapse send claude "Review" --attach src/main.py --wait  # With file
synapse reply "Result here"                    # Auto-route to sender
synapse reply --fail "Could not complete"      # Send a failed reply
synapse broadcast "Status check"               # All agents in CWD
synapse interrupt claude "Stop and review"      # Soft interrupt (priority 4)

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

# Wiki (LLM Wiki — Knowledge Accumulation)
synapse wiki ingest <source-path> [--scope project|global]
synapse wiki query "<question>" [--scope project|global]
synapse wiki lint [--scope project|global]              # Also detects stale pages (source_files changed)
synapse wiki status [--scope project|global]            # Shows page count, staleness, and health
synapse wiki refresh [--apply] [--scope project|global] # List stale pages; --apply updates source_commit
synapse wiki init [--scope project|global]              # Create skeleton architecture & patterns pages

# Canvas
synapse canvas serve [--port 3000] [--no-open]
synapse canvas post mermaid "graph TD; A-->B" --title "Flow"
synapse canvas post markdown "## Doc" --title "Doc"
synapse canvas post artifact '<!doctype html>...' --title "Counter App"
synapse canvas post-raw '{"content":{"format":"code","body":"print(1)","x_title":"Demo"}}'
synapse canvas briefing '{"content":[...],"sections":[...]}'
synapse canvas link "https://example.com/article" --title "Reference"
synapse canvas plan '{"title":"...","plan_id":"...","steps":[...]}'  # Plan Card
synapse canvas list [--mine] [--search TERM]
synapse canvas open [--port 3000]
synapse canvas status [--port 3000]
synapse canvas stop [--port 3000]

# Session/Workflow
synapse session save <name>
synapse session restore <name>
synapse workflow run <name>
synapse workflow sync                            # Re-generate skills from all workflow YAMLs

# Spawn/Teams (auto-approve enabled by default, auto-tile on 2+ spawns)
synapse spawn claude --name Tester --role "test writer"
synapse spawn claude --worktree feature-auth
synapse spawn codex --branch renovate/major-eslint-monorepo   # --branch auto-enables --worktree
synapse spawn claude --no-auto-approve             # Disable auto-approve
synapse spawn gemini --task "Write tests for auth" --notify    # Spawn + auto-send task
synapse spawn claude --task-file /tmp/instructions.md --wait   # Task from file
synapse merge my-agent                             # Merge worktree branch (agent stays running)
synapse merge --all                                # Merge all worktree branches
synapse merge my-agent --dry-run                   # Preview merge without executing
synapse merge my-agent --resolve-with gemini       # Delegate conflict resolution to another agent
synapse worktree prune                             # Remove orphan worktrees (dir gone, git ref remains)
synapse team start claude gemini                   # Defaults to --worktree isolation
synapse team start claude gemini --no-worktree     # Opt out of worktree default
synapse team start claude gemini --worktree --branch feature/api  # Base branch for all worktrees
synapse team start claude gemini --no-auto-approve # Disable for all agents

# Skills
synapse skills list
synapse skills show <name>
synapse skills deploy <name> --agent claude

# Config
synapse config
synapse init
synapse reset

# MCP Bootstrap
synapse mcp serve                          # Start MCP server over stdio (options auto-resolved from $SYNAPSE_AGENT_ID)

# MCP Tools (available via JSON-RPC tools/call)
# bootstrap_agent    — Returns runtime context (agent_id, port, features)
# list_agents        — List all running Synapse agents with status and connection info
#                      Optional input: {"status": "READY"}  (filter by status)
# analyze_task       — Analyze user prompt and suggest team/task split (Smart Suggest)
#                      Input: {"prompt": "user instruction text", "files": [...], "agent_type": "claude"}
#                      Returns delegation_strategy: "self" | "subagent" | "spawn"
#                      Returns recommended_worktree: true when spawn strategy or high file conflicts
#                      Context includes diff_stats, file_conflicts, dependencies, parallelizable
#                      Triggers configurable via .synapse/suggest.yaml

# Self-Learning Pipeline
synapse learn                                    # Analyze observations → persist instincts
synapse instinct                                 # List learned instincts
synapse instinct --scope project                 # Filter by scope (project/global)
synapse instinct --domain "error-handling"        # Filter by domain
synapse instinct --min-confidence 0.7            # Filter by minimum confidence
synapse instinct promote <instinct_id>           # Promote project instinct to global
synapse evolve                                   # Discover skill candidates from instincts
synapse evolve --generate                        # Generate skill files from candidates
synapse evolve --output-dir .synapse/evolved/skills  # Custom output directory

# Auth
synapse auth setup
```

## Shared Memory vs LLM Wiki

Synapse には知識共有のための機能が 2 つ存在するが、**これは移行期間の結果**であり、**LLM Wiki (`synapse wiki`) が Shared Memory (`synapse memory`) を置き換える**ことが [design/llm-wiki.md](design/llm-wiki.md#shared-memory-の廃止) で決定されている。新規の知識記録は必ず LLM Wiki を使うこと。

### 現状 (2026-04-10)

| | **`synapse memory`** (Shared Memory) | **`synapse wiki`** (LLM Wiki / Living Wiki) |
|---|---|---|
| **Status** | **Deprecation planned** (`docs/design/llm-wiki.md` で廃止決定済み、コードはまだ残存) | **Actively developed** (v0.21.0 導入, v0.23.0 で Living Wiki 拡張) |
| **新規使用** | **非推奨** | **推奨** |
| **データモデル** | Flat key-value + tags | Markdown pages + frontmatter + `[[wikilinks]]` |
| **知識の構造化** | フラット | 階層的、ページ間リンク、Mermaid graph |
| **メンテナンス機能** | なし | source_files 追跡、stale 検出、`wiki refresh`、`wiki lint` |
| **UI** | CLI のみ | CLI + Canvas Knowledge view (`#/knowledge`) + MCP instruction |
| **page type** | なし | `learning` type で bug fix / discovered pattern を記録 |
| **検索** | SQLite 全文検索 | `synapse wiki query` (意味的クエリ) |
| **コマンド** | `save/list/show/search/delete/stats` | `ingest/query/lint/status/refresh/init` |

### 使い分けの指針

**✅ LLM Wiki を使う** — 原則としてすべての知識蓄積ユースケース

- Bug fix の原因と対策の記録（`learning` page type の典型用途）
- アーキテクチャ決定とその理由
- 相互リンクで体系化したい知識（`[[wikilink]]`）
- source コード変更時の自動陳腐化検出（`source_files` frontmatter）
- Canvas UI での閲覧・共有
- エージェント間で長期的に蓄積されるプロジェクト知識

**⚠️ Shared Memory が許容される限定的ケース**

- 既に `synapse memory` を使っている既存プロジェクトの一時的な継続運用
- ごく短命で構造化不要な key-value（例: 進行中 job の ID 共有）
- ただし、これらも長期的には Wiki に移行することが望ましい

**❌ Shared Memory を新たに導入しない** — 設計ドキュメント上は廃止予定の機能である

### 移行

- **新規の知識**: 必ず `synapse wiki ingest` を使う
- **既存の `synapse memory` エントリ**: 必要なら `synapse wiki ingest` で Wiki ページに変換（公式の一括移行ツールは未提供、手動作業）
- **MCP instruction**: `synapse://instructions/default` には現在も "SHARED MEMORY" セクションが残っているが、これは古い情報。LLM Wiki の正式な instruction は `synapse://instructions/wiki`

詳細:
- LLM Wiki 設計書: [design/llm-wiki.md](design/llm-wiki.md)（§「Shared Memory の廃止」に廃止の根拠）
- Shared Memory 現行仕様: [shared-memory-spec.md](shared-memory-spec.md)（冒頭に Maintenance mode 注記）

## Target Resolution

Targets resolve in priority order:
1. Custom name: `my-claude`
2. Full Runtime ID: `synapse-claude-8100`
3. Type-port shorthand: `claude-8100`
4. Agent type (single instance only): `claude`

**Display Name Resolution**: `resolve_display_name` resolves agent IDs (e.g., `synapse-claude-8100`) to human-friendly display names (e.g., `my-claude`) in Canvas views.

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
- **OpenCode**: Timeout strategy, 1.0s (Bubble Tea TUI). It does not expose a stable `input_ready_pattern`, so Synapse falls back to timeout-based idle detection before sending initial instructions.
- **Copilot**: Timeout strategy, 0.5s. `bracketed_paste: true` — Copilot CLI 1.0.12+ enables bracketed paste mode (`ESC[?2004h`), so Synapse wraps input in `ESC[200~`/`ESC[201~` markers and Ink routes it through `usePaste` as a single event. Because input is delivered atomically, slash-command autocomplete does not trigger and `/` replacement is skipped. Input delivery uses an **inject pipe** mechanism: because `pty.spawn()` manages master fd I/O through its `_copy` loop, direct writes from other threads were lost; the inject pipe merges keyboard input and programmatic writes into a single stream. `input_ready_pattern: "❯"` detects when the TUI is ready before sending initial instructions. `auto_approve.cli_flag` uses the canonical `--allow-all` flag. Bounded submit confirmation (`submit_confirm_timeout`, `submit_confirm_poll_interval`, `submit_confirm_retries`) verifies that Copilot cleared the prompt. Long multiline or file-reference sends use a larger confirmation budget (`long_submit_confirm_timeout`, `long_submit_confirm_retries`). **Kitty Keyboard Protocol (KKP) mitigation**: Copilot CLI enables KKP on startup, which changes Enter key encoding from `\r` to CSI 13 u (`ESC[13u`). This causes injected `\r` submit sequences to be ignored. The controller detects KKP activation (`ESC[>…u`) in PTY output and immediately disables it by sending the pop sequence (`ESC[<u`). As a safety net, KKP is also proactively disabled before the first submit if it was not already caught by the output monitor.

For `response_mode=wait` and `response_mode=notify`, Synapse completes the sender-side task via structured reply artifacts. Completion finalization now prefers the PTY output delta captured since task start rather than the raw terminal tail, reducing reply corruption from transient TUI lines such as update banners, permission rows, and status bars. TUI response cleaning (`clean_copilot_response()`) now runs for **all agents** (not just Copilot), stripping Ink TUI artifacts (spinners, box-drawing borders, status bar, and input echo) from the captured delta before building the reply. Additional TUI artifact removal covers OpenCode (Bubble Tea) block-element lines (Unicode Block Elements U+2580-U+259F, Geometric Shapes U+25A0-U+25FF), TUI frame content lines (bordered rows from Bubble Tea/Ink layouts), and Gemini CLI input prompt lines. The `strip_ansi()` helper uses three-stage removal (full ANSI sequences, orphaned SGR fragments, bare SGR fragments) to handle cases where `\r` overwrites the ESC prefix, and also handles unterminated OSC sequences. Quota-exhaustion output such as `402 You have no quota` is classified as a failed task instead of being returned as a normal reply.

In server mode (when `agent_name` is set), startup/runtime logging is redirected from stderr to file-only to prevent log output from corrupting the agent TUI. Controller logging uses the module-level `logger` (`logging.getLogger(__name__)`) instead of the root logger, so log messages are correctly scoped and can be filtered per-module.

## Agent Status System

States: READY → PROCESSING → DONE → READY (auto after 10s), WAITING, SHUTTING_DOWN

Compound signal: PROCESSING→READY suppressed when `task_active` flag set or file locks held.

**WAITING auto-approve**: When an agent enters WAITING status (permission prompt detected), the controller automatically sends the profile-specific approval response (e.g., `y\r` for Claude, `\r` for Gemini). PTY output is passed through `strip_ansi()` before regex matching, ensuring reliable WAITING detection for TUI-based agents (ratatui, Ink, Bubble Tea). Enabled by default for spawned agents; disable with `--no-auto-approve` or `SYNAPSE_AUTO_APPROVE=false`. Safety: unlimited consecutive approvals by default (`max_consecutive=0`), no cooldown (`cooldown=0.0`). Set `max_consecutive` to a positive integer to cap consecutive approvals. See [docs/agent-permission-modes.md](agent-permission-modes.md).

**WAITING → input_required (A2A)**: When an agent enters WAITING status, the A2A task status is mapped to `input_required` per the Google A2A spec. The task metadata includes `x-permission-prompt` (the detected prompt text) and `x-permission-options` (available responses). Callers can approve or deny via the permission endpoints below. See [docs/permission-detection-spec.md](permission-detection-spec.md).

### Permission Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/tasks/{id}/permission/approve` | Approve a permission prompt (sends profile-specific approval response to the agent PTY) |
| POST | `/tasks/{id}/permission/deny` | Deny a permission prompt (sends the profile's `deny_response` to the agent PTY) |

## Readiness Gate

`/tasks/send` blocked until agent completes initialization. Timeout: 30s. Bypasses: priority 5 and reply messages.

**PROCESSING wait**: `synapse send` also waits up to 30s for a PROCESSING target to become idle before delivering. Skipped for `--force`, priority 5, and `--silent`.

## Storage

```
~/.a2a/registry/        # Running agents
~/.a2a/reply/            # Reply targets
~/.synapse/skills/       # Central skill store
~/.synapse/agents/       # Saved agent definitions (user)
~/.synapse/sessions/     # Sessions (user)
~/.synapse/workflows/    # Workflows (user)
~/.synapse/canvas.pid    # Canvas server PID file (stale process detection)
~/.synapse/history/      # history.db (task history, user-global)
~/.synapse/canvas.db     # Canvas card storage (user-global)
~/.synapse/memory.db     # Shared memory (user-global)
~/.synapse/wiki/         # Global Wiki (cross-project knowledge)
.synapse/wiki/           # Project-local Wiki (pages, sources, schema, index, log)
.synapse/                # Project-local (file_safety.db, workflow_runs.db, observations.db, instincts.db, etc.)
```

## Testing

See test files in `tests/` directory. Key test groups:

- Core: `test_a2a_compat.py`, `test_registry.py`, `test_controller_registry_sync.py`
- Canvas: `test_canvas_store.py`, `test_canvas_protocol.py`, `test_canvas_server.py`, `test_canvas_artifact.py`, `test_canvas_export.py`
  - Dashboard widget preserves task card expand/collapse state across polling refreshes
  - Task descriptions render as Markdown in the Canvas dashboard
  - View toggle active tab uses improved contrast (white text, semi-bold weight)
- Agent Teams: `test_hooks.py`, `test_plan_approval.py`, `test_delegate_mode.py`
- Spawn: `test_spawn.py`, `test_auto_spawn.py`, `test_auto_layout.py`
- Memory: `test_shared_memory.py`, `test_cli_memory.py`
- MCP: `test_mcp_bootstrap.py`, `test_mcp_list_agents.py`, `test_mcp_analyze_task.py`
- Smart Suggest / Plan: `test_plan_accept.py`
- Permission: `test_permission_notify.py`, `test_permission_api.py`
- Status: `test_cmd_status.py`, `test_compound_signal.py`
- Live CLI E2E: `test_live_e2e_agents.py` (opt-in via `SYNAPSE_LIVE_E2E=1`; filter profiles with `SYNAPSE_LIVE_E2E_PROFILES=claude,copilot`)

Live E2E tests start real agent CLIs with `synapse <profile> --headless --no-setup`,
send a tokenized prompt through `/tasks/send`, and wait for task completion. They are
skipped by default because they require installed/authenticated agent binaries and
network access.

## Priority Levels

| Priority | Use Case |
|----------|----------|
| 1-2 | Background tasks |
| 3 | Normal |
| 4 | Urgent |
| 5 | Emergency |
