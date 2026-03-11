# Changelog

For the complete changelog, see [CHANGELOG.md on GitHub](https://github.com/s-hiraoku/synapse-a2a/blob/main/CHANGELOG.md).

## Recent Highlights

### v0.11.12

- **Fixed**: Use returned task IDs instead of numeric indices in skill docs and guides
- **Fixed**: Handle invalid UTF-8 `.agent` files in canvas saved agent reader

### v0.11.11

- **Added**: Anthropic official skill-creator plugin, pr-guardian skill with auto-trigger hook
- **Added**: Auto-skip PTY bootstrap when MCP config detected, task board mandatory for delegations
- **Fixed**: Canvas stale process problem with robust PID management
- **Fixed**: Defer spotlight DOM clear to prevent blank fallback rendering
- **Changed**: Simplify canvas process management after code review
- **Documentation**: Update Canvas docs for stale process management

### v0.11.10

- **Fixed**: Test failures from CLAUDE.md slimdown and `LongMessageStore` singleton pollution
- **Fixed**: Missing `user_dir` parameter in `SynapseSettings._load_instruction_file()`
- **Fixed**: Tighten test assertions for storage doc and MCP stdio protocol verification
- **Documentation**: Add per-agent MCP configuration to Getting Started guides

### v0.11.9

- **Added**: MCP bootstrap server (`synapse mcp serve`) for stdio-based instruction distribution
- **Added**: MCP client configuration for Gemini CLI and OpenCode
- **Changed**: Cache `SynapseSettings` in MCP server, deduplicate agent_type parsing, remove dead code
- **Documentation**: Slim down `AGENTS.md`, improve `code-simplifier` skill, add MCP design doc

### v0.11.8

- **Fixed**: `synapse canvas stop` now detects server via health endpoint (works with foreground `serve`)
- **Fixed**: Verify `synapse-canvas` service identity before killing process
- **Fixed**: `canvas stop` accepts `--port` for non-default ports

### v0.11.7

- **Fixed**: Include canvas templates and static files in package data (fixes "template not found" on pip install)

### v0.11.6

- **Changed**: Increase `MAX_BLOCKS_PER_CARD` from 10 to 30 for richer composite cards

### v0.11.5

- **Added**: Dashboard view with expandable summary+detail widgets (Agents, Tasks, File Locks, Worktrees, Memory, Errors)
- **Added**: Clickable task cards with detail view (description, priority, created by, created at)
- **Changed**: Dashboard widgets use progressive disclosure — compact summary by default, full table on expand

### v0.11.4

- **Added**: Dedicated `#/system` route for the Canvas System panel
- **Added**: Expanded System view with skills, sessions, workflows, environment, and tips sections
- **Added**: Canvas UI visual refresh with glassmorphism accents, iconography, and a refined color palette
- **Fixed**: `Latest Posts` no longer follows dashboard filters; `Agent Messages` filters now hide non-target agent panels

### v0.11.3

- **Added**: Canvas Templates — 5 built-in templates (`briefing`, `comparison`, `dashboard`, `steps`, `slides`) for structured card layouts
- **Added**: `synapse canvas briefing` CLI command for posting structured reports with sections
- **Added**: Canvas cache-busting and SSE reconnection fixes for reliable browser display
- **Fixed**: Canvas View empty after server restart (stale JS cache)
- **Fixed**: Mermaid diagrams overlapping sections (auto-sizing SVGs)

### v0.11.2

- **Changed**: Task board lifecycle commands accept unique short task ID prefixes
- **Fixed**: Canvas raw JSON posts autofill `agent_name` from registry
- **Fixed**: Canvas system panel surfaces registry read errors

### v0.11.1

- **Added**: Completion callback for `--silent` sends — sender-side history is updated (`sent` -> `completed`/`failed`/`canceled`) via best-effort callback when the receiver finishes processing
- **Added**: `POST /history/update` API endpoint for receiver-to-sender history status notification
- **Added**: `HistoryManager.update_observation_status()` for atomic history record updates with metadata merge
- **Added**: Proactive Mode — `SYNAPSE_PROACTIVE_MODE_ENABLED=true` injects mandatory checklist for using all Synapse features (task board, shared memory, canvas, file safety, delegation, broadcast)
- **Added**: New proactive mode user guide and specification document

### v0.11.0

- **Added**: Canvas SPA routing — `#/` (full-viewport Canvas view) and `#/history` (History view with system panel, live feed, agent messages)
- **Added**: Highlight.js syntax highlighting for `code` and `file-preview` card formats, side-by-side diff renderer, HTML iframe full-height in Canvas view
- **Added**: Chart.js supports all types (bar, line, pie, doughnut, radar, polarArea, scatter, bubble)
- **Changed**: Content size limit increased from 500KB to 2MB per content block
- **Changed**: Theme toggle moved to header level (visible in both Canvas and History views)
- **Changed**: Canvas performance — debounced rendering, skip-unchanged spotlight, O(n) latest card lookup
- **Changed**: iframe sandbox reverted to `allow-scripts` only (security fix)
- **Fixed**: `from_dict` guards non-dict content input
- **Fixed**: `simpleMarkdown` blocks `javascript:` URLs (XSS hardening)
- **Fixed**: `card_id` is globally unique (not per-agent); server returns 403 on cross-agent reuse

### v0.10.1

- **Changed**: Skill Progressive Disclosure — `synapse-a2a` SKILL.md reduced from 877→159 lines, `synapse-manager` from 426→199 lines. Detail moved to `references/` for on-demand loading
- **Added**: Manager helper scripts (`wait_ready.sh`, `check_team_status.sh`, `regression_triage.sh`) for deterministic operations
- **Added**: Skill structure tests (`test_skill_structure.py`) enforcing Progressive Disclosure best practices
- **Fixed**: tmux pane scoped splitting — `split-window` now targets `$TMUX_PANE` so new panes stay next to the source pane instead of applying a global layout
- **Removed**: `synapse-docs` from plugins (dev-only, now in `.agents/skills/` only)

### v0.9.5

- **Fixed**: Spawn pane layout (#336) — `synapse spawn` creates side-by-side panes instead of top-bottom
- **Fixed**: ANSI escape sequences in A2A replies (#337) — `get_context()` strips ANSI codes
- **Changed**: Task receipt collaboration flow — agents delegate independent work units via `synapse spawn` + `synapse send --silent`

### v0.9.4

- **Fixed**: `synapse init` data loss — was replacing entire `.synapse/` directory, destroying saved agent definitions, databases, sessions, workflows, and worktrees. Now uses merge strategy (template files only).
- **Added**: `synapse status <target>` command — detailed single-agent view with uptime, current task elapsed time, recent messages, file locks, and task board assignments (supports `--json` output)
- **Added**: Compound signal status detection — PROCESSING-to-READY transitions now check `task_active` flag and file lock state to prevent premature status changes
- **Added**: WAITING detection improvements — fresh-output-only matching eliminates false positives from old buffer content; auto-expiry when pattern disappears from visible buffer
- **Added**: Elapsed time display in CURRENT column of `synapse list` (e.g., `Review code (2m 15s)`)
- **Changed**: `parallel-docs-simplify-sync` skill now uses Claude Code built-in `/simplify` instead of custom subagent

### v0.9.3

- **Added**: Proactive Collaboration Framework — agents receive a decision framework at startup for when to delegate, ask for help, report progress, and share knowledge
- **Added**: Cross-model spawn preference — agents are guided to spawn different model types for diverse perspectives and rate limit distribution
- **Added**: Worker autonomy — worker agents can proactively spawn helpers, delegate subtasks, and request reviews
- **Added**: USE SYNAPSE FEATURES ACTIVELY section — explicit guidance for task board, shared memory, file safety, worktree, broadcast, and history
- **Added**: TRANSPORT column in text-mode `synapse list` for scripted use
- **Changed**: synapse-manager Step 1 now checks existing agents before spawning
- **Changed**: Mandatory cleanup enforcement for spawned agents across all skill docs

### v0.9.2

- **Added**: `synapse session restore --resume` flag to resume each agent's CLI conversation session
  - Saved sessions now capture `session_id` from the agent registry
  - Per-agent resume args: Claude (`--resume`/`--continue`), Gemini (`--resume`), Codex (`resume`/`resume --last`), Copilot (`--resume`), OpenCode (no support)
  - Shell-level time-guarded fallback: if resume fails within 10 seconds, retries without resume args
- **Added**: `synapse session sessions` command to browse CLI tool session files from the filesystem
  - Supports Claude, Gemini, Codex, and Copilot session discovery
  - Filter by `--profile` and `--limit`; sorted by modification time (newest first)
- **Added**: Automatic `session_id` capture from CLI tool filesystems on agent startup (`synapse/session_id_detector.py`)
  - Background detection after readiness gate; stored in agent registry for use by `session save`
- **Changed**: `synapse session show` now displays `session_id` for each agent entry

### v0.9.1

- **Added**: Saved Workflows (`synapse workflow`) — define and replay reusable message sequences to running agents
- **Added**: Enhance help discoverability for root/team/session commands
- **Fixed**: Corrupted YAML no longer bypasses workflow overwrite protection
- **Fixed**: Validate WorkflowStep target/message are `str` type
- **Docs**: Add workflow guide and CLI reference to GitHub Pages

### v0.9.0

- **Added**: Session Save/Restore (`synapse session`) — save and restore team configurations as named snapshots
- **Docs**: Add Session Save/Restore guide, update CLI reference and plugin skills

### v0.8.6

- **Changed**: Unify agent example names with model-hinting English names (Claud, Cody, Rex, Gem)
- **Docs**: Expand delegate-mode guide with architecture, config, and use cases
- **Docs**: Document `--agent`/`-A` flag for starting agents with saved agent definitions
- **Docs**: Document role file conventions, petname ID format, scope precedence, `.agent` file format
- **Docs**: Update all site-docs, guides, CLAUDE.md, and plugin skills with consistent agent names

### v0.8.5

- **Changed**: Replace copyrighted character names with generic English names (Alice, Bob, Charlie, Dave, Eve, Frank)
- **Docs**: Add skill installation guide (`npx skills add`) to Getting Started and Skills pages
- **Docs**: Add `synapse-reinst` to Built-in Skills; remove `doc-organizer` from core install tables

### v0.8.4

- **Added**: Synapse-native worktree isolation (`--worktree` / `-w`) for all agent types
  - Isolated git worktrees under `.synapse/worktrees/` with auto-generated or explicit names
  - Automatic cleanup on exit; prompts if unsaved changes or new commits exist
  - Per-agent worktrees in `synapse team start --worktree`
  - API support via `POST /spawn` with `worktree` field
  - `[WT]` indicator in `synapse list`
- **Fixed**: Worktree name validation, defensive subprocess handling, cleanup error recovery

### v0.8.3

- **Breaking**: Unify `.gemini/skills/` into `.agents/skills/` — Gemini now uses the same skill directory as Codex, OpenCode, and Copilot
  - **Migration**: copy or move skills from `.gemini/skills/` to `.agents/skills/`
  - TUI deploy indicators simplified from `[C✓ A✓ G·]` to `[C✓ A✓]`
- **Changed**: Add `synapse-docs` skill to `plugins/` source of truth
- **Fixed**: `AgentProfileStore` scope inconsistency — shutdown save now uses startup store

### v0.8.2

- **Changed**: Unify agent identifier terminology — **Runtime ID** (`synapse-claude-8100`) vs **Agent ID** (`wise-strategist`)
- **Changed**: Response mode refactoring — replaced `--response`/`--no-response` flags with `--wait`/`--notify`/`--silent`
  - `--wait`: Synchronous blocking (replaces `--response`)
  - `--notify`: Async notification on completion (new default)
  - `--silent`: Fire-and-forget (replaces `--no-response`)
- **Fixed**: IDLE status bug in task completion detection
- **Added**: Controller status-change callback for proactive completion detection

### v0.8.1

- **Fixed**: Add missing `manager` and `documentation` skill set definitions to bundled defaults
- **Fixed**: Merge `coordinator` skill set into `manager` (adds `synapse-reinst`)
- **Docs**: Update skill set tables across all documentation to reflect 6 default sets

### v0.8.0

- **Added**: Saved Agent Manager — reusable agent configurations via `synapse agents` commands
- **Added**: Completion callback for `--silent` task tracking (`POST /history/update`)
- **Added**: Sender identification in PTY-injected A2A messages
- **Added**: Ghostty split pane support for `team start` and `spawn`
- **Added**: Agent name uniqueness enforcement across interactive start, spawn, and team start
- **Added**: Save-on-exit prompt for interactive named agents
- **Added**: `synapse-manager` skill — structured 5-step multi-agent management workflow
- **Added**: `manager` and `documentation` skill sets for multi-agent management and docs-focused agents
- **Added**: `doc-organizer` skill — documentation audit, restructure, and deduplication
- **Changed**: `synapse spawn` and `synapse team start` accept saved-agent ID/name
- **Changed**: Reply target persistence moved to dedicated `~/.a2a/reply/` directory
- **Changed**: Registry writes hardened with registry-wide lock and atomic name conflict rejection
- **Changed**: Agent spec format simplified to `profile[:name[:role[:skill_set[:port]]]]`
- **Fixed**: Ghostty split panes (`Cmd+D`) instead of new windows, clipboard paste for commands
- **Fixed**: Ghostty panes auto-close on agent exit
- **Fixed**: Port pre-allocation in `team start` to avoid race conditions
- **Fixed**: Shared memory bugs (#286-#291) and memory CLI tag parsing
- **Fixed**: Soft interrupt priority corrected (p5→p4)
- **Fixed**: `registry.py` `list_agents()` handles `KeyError` gracefully
- **Docs**: Saved-agent definitions guide and CLI reference

### v0.7.0

- **Added**: Shared Memory for cross-agent knowledge sharing (`synapse memory` commands)
- **Added**: GitHub Pages documentation site with MkDocs Material
- **Added**: github-pages-sync skill for site-docs maintenance
- **Docs**: Sync list and configuration docs with current implementation

### v0.6.12

- **Fixed**: Store identity instructions in files via LongMessageStore (prevents Ink TUI paste collapse)
- **Fixed**: Update Installers workflow version extraction with `gh release view` fallback
- **Fixed**: Copilot CLI write_delay increased to 0.5s for reliable submit
- **Tests**: Shared test helper `read_stored_instruction` in `tests/helpers.py`

### v0.6.11

- **Fixed**: Per-profile `write_delay` for Copilot CLI submit timing
- **Fixed**: Prevent REPLY EXPECTED marker duplication
- **Fixed**: PTY_WRITE_MAX constant for kernel buffer safety
- **Fixed**: Auto-release → publish → update-installers workflow chain

### v0.6.10

- **Added**: Injection observability with INJECT/* structured logs
- **Added**: Soft interrupt command (`synapse interrupt`)
- **Added**: Token/cost tracking skeleton (`TokenUsage` dataclass)

### v0.6.x Series

- Copilot CLI profile and spawn support
- Tool args passthrough (`synapse spawn claude -- --worktree`) — Synapse-native `--worktree` flag is now recommended; passthrough remains supported for Claude Code
- Send UX improvements (message-file, stdin, auto-temp)
- File attachment support (`--attach`)

### v0.5.x Series

- Agent Teams features (B1-B6)
- Shared Task Board with dependencies
- Quality Gates (hooks)
- Plan Approval workflow
- Graceful Shutdown
- Delegate Mode
- Auto-Spawn Panes

### v0.4.x Series

- Skills system with TUI manager
- Multi-scope skill deployment
- Skill sets for grouped capabilities
- Interactive setup with name/role

### v0.3.x Series

- Task history (enabled by default)
- File Safety system
- Learning mode
- Settings management TUI
- External agent connectivity

### v0.2.x Series

- Core A2A implementation
- Multi-agent communication
- Agent registry
- Priority levels
- @Agent pattern routing

## Version Policy

Synapse A2A follows [Semantic Versioning](https://semver.org/):

- **MAJOR**: Breaking changes
- **MINOR**: New features (backward compatible)
- **PATCH**: Bug fixes (backward compatible)
