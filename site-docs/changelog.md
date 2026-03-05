# Changelog

For the complete changelog, see [CHANGELOG.md on GitHub](https://github.com/s-hiraoku/synapse-a2a/blob/main/CHANGELOG.md).

## Recent Highlights

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
