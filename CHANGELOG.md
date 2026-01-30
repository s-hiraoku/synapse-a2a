# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.8] - 2026-01-28

### Fixed

- Fix instruction file path display to correctly show user directory (`~/.synapse/`) vs project directory (`.synapse/`)
  - `synapse instructions files` now shows accurate file locations
  - `synapse instructions send` references correct paths in messages
  - Project directory takes precedence when file exists in both locations

### Documentation

- Update `guides/references.md` and skill references with new output examples

### Tests

- Add `TestInstructionFilePaths` test class for path resolution logic

### Chores

- Add `types-pyperclip` dev dependency for mypy type checking

## [0.3.7] - 2026-01-27

### Changed

- Simplify A2A reply flow with Reply Stack automation
  - Remove `--reply-to` option from `synapse send` command
  - Add `--from` flag to `synapse reply` for sandboxed environments (Codex)
  - Simplify message format from `[A2A:<task_id>:<sender_id>]` to `A2A: <message>`
- Agents no longer need to track task_id or sender_id for replies

### Documentation

- Add "Agent Ignorance Principle" to project philosophy
  - Agents operate as if standalone; Synapse handles all routing
- Update all agent skills and templates with simplified format
- Remove internal implementation details from skill references

## [0.3.6] - 2026-01-25

### Added

- Interactive filter and kill functionality for `synapse list` (#158)
  - Press `/` to filter agents by TYPE or DIR
  - Press `k` to kill selected agent (with confirmation)
  - ESC clears filter, `q` quits

### Fixed

- `synapse list` display corruption and keyboard navigation issues (#156)
  - Fix rendering artifacts when list updates
  - Improve arrow key navigation reliability

### Documentation

- Add resident agent memory usage note (#157)

## [0.3.5] - 2026-01-24

### Added

- GitHub Copilot CLI agent support
  - New agent profile: `synapse/profiles/copilot.yaml`
  - Port range 8140-8149 for Copilot instances
  - Full A2A protocol integration with `synapse copilot` command
  - Timeout-based idle detection (500ms) for interactive TUI

### Documentation

- Sync plugin skills with Copilot support across all agent directories
- Update `synapse list` documentation (auto-refresh is now default TUI behavior)
- Fix DONE status color (magenta → blue) to match README
- Add Copilot to all skill references (commands, API, delegation)

## [0.3.4] - 2026-01-23

### Documentation

- Update skill installation method to use skills.sh (`npx skills add s-hiraoku/synapse-a2a`)
- Rename "Claude Code Plugin" section to "Skills" in README
- Add skills.sh reference links (https://skills.sh/)

## [0.3.3] - 2026-01-23

### Added

- Gemini CLI skills support via `.gemini/skills/` directory
  - `synapse-a2a` skill for inter-agent communication
  - `delegation` skill for task delegation configuration
- Skills section in `GEMINI.md` and `synapse/templates/.synapse/gemini.md`

### Documentation

- Update README.md to note Gemini skills directory support alongside Codex

## [0.3.2] - 2026-01-23

### Changed

- Replace `--watch` mode with event-driven auto-update for `synapse list`
  - Use watchdog file watcher for instant registry change detection
  - Add 2-second fallback polling for reliability
  - Remove `--watch`, `--interval`, `--no-rich` CLI options
  - Rich TUI with auto-refresh is now the default behavior

### Fixed

- Disable WAITING status detection to fix false positives on startup (#140)

### Documentation

- Update README and guides for event-driven `synapse list`
- Add keyboard shortcuts: 1-9 select, Enter/j jump, ESC clear, q quit

## [0.3.1] - 2026-01-22

### Changed

- Use hyphenated "open-source" consistently in all documentation
- Clarify tool exclusions in OpenCode agents documentation (todowrite/todoread)
- Add `pattern_use: "never"` to OpenCode profile for schema compliance
- Document Synapse metadata field naming convention (non-x- prefixed fields in metadata namespace)

### Documentation

- Add OpenCode to delegation skill Available Agents table (port 8130-8139)
- Update sender_type enumeration to include "opencode" in API docs
- Synchronize opencode-expert skill across .claude, .codex, and .opencode directories

## [0.3.0] - 2026-01-22

### Added

- OpenCode agent support (#135)
  - New agent profile: `synapse/profiles/opencode.yaml`
  - Port range 8130-8139 for OpenCode instances
  - Full A2A protocol integration with `synapse opencode` command
  - OpenCode expert skill for comprehensive OpenCode guidance
- OpenCode skills for multi-agent environments
  - `.opencode/skills/synapse-a2a/` - Synapse A2A integration skill
  - `.opencode/skills/delegation/` - Task delegation skill
  - `.opencode/skills/opencode-expert/` - OpenCode CLI/tools/agents reference

### Changed

- Consolidated instruction templates: removed redundant `opencode.md`, uses `default.md`
- Updated `settings.json` template with OpenCode resume flags (`--continue`, `-c`)

### Documentation

- Added OpenCode to all documentation (README, guides, CLAUDE.md)
- Synchronized plugin skills with OpenCode references
- Added OpenCode port range (8130-8139) to all port documentation

### Tests

- Added 21 tests for OpenCode support (`tests/test_opencode.py`)
- Updated port manager tests for OpenCode port range

## [0.2.30] - 2026-01-21

### Added

- Rich TUI for `synapse config` command with keyboard navigation (#133)
  - Arrow keys (↑/↓) for cursor movement
  - Enter to select, ESC/q to go back
  - Number keys (1-9) for quick jumps
  - Box-style headers with status bar showing controls
- `simple-term-menu` dependency for terminal menu selection

### Changed

- Replace questionary-based config UI with simple-term-menu
- Extract helper methods in RichConfigCommand for cleaner code structure

## [0.2.29] - 2026-01-20

### Fixed

- AppleScript validation now checks for expected token in output
  - `_jump_iterm2` and `_jump_terminal_app` verify "found" response
  - Scripts returning "not found" now correctly return False
- DONE status color changed from blue to magenta for consistency with documentation
- Zellij terminal jump updated (CLI doesn't support direct pane focus)
  - Falls back to activating terminal app with pane ID logged for reference
- Markdown lint MD058: added blank lines before Agent Status tables in skill docs

### Changed

- `_run_applescript` now accepts optional `expected_token` parameter for output validation

### Documentation

- Update VS Code terminal jump description (activates window, not working directory)
- Update Zellij description to note CLI limitation for direct pane focus
- Sync skill documentation across .claude, .codex, and plugins directories

## [0.2.28] - 2026-01-19

### Added

- Terminal jump feature in `synapse list --watch` mode
  - Press `Enter` or `j` to jump directly to selected agent's terminal
  - Supports iTerm2, Terminal.app, Ghostty, VS Code, tmux, and Zellij
- Expanded 4-state agent status system
  - READY (green): Idle, waiting for input
  - WAITING (cyan): Awaiting user input (selection, confirmation prompts)
  - PROCESSING (yellow): Busy handling a task
  - DONE (magenta): Task completed (auto-clears after 10s)
- WAITING status detection via regex patterns in profile YAML
  - Claude: Selection UI (❯), checkboxes (☐/☑), Y/n prompts
  - Gemini: Numbered choices (●/○), Allow execution prompts
  - Codex: Numbered list selection
- Zellij terminal multiplexer support for terminal jump

### Fixed

- Ghostty terminal jump simplified to activate-only (AppleScript limitation)
- Working directory display shows only directory name in list view (full path in detail panel)

### Changed

- WAITING detection refactored from pattern list to single regex for accuracy

### Documentation

- Add Agent Monitor section to README.md and README.ja.md
- Update plugin skills with 4-state status and terminal jump documentation

## [0.2.27] - 2026-01-18

### Added

- Rich TUI for `synapse list --watch` with interactive features
  - Color-coded status display (READY=green, PROCESSING=yellow)
  - Row selection via number keys (1-9) to view full paths in detail panel
  - ESC key to close detail panel, Ctrl+C to exit
  - `--no-rich` flag for plain text output mode
  - TRANSPORT column shows real-time communication status (UDS→/→UDS, TCP→/→TCP)

### Changed

- Extract `_is_agent_alive` helper method in list.py to reduce duplication
- Consolidate `pkg_version` retrieval in list.py
- Simplify stale locks handling in rich_renderer.py
- Extract `_handle_task_response` helper in input_router.py

### Documentation

- Sync plugin skills with Rich TUI documentation
- Add Rich TUI features to Quick Reference (--no-rich, interactive mode)
- Document synapse config show --scope options
- Add synapse instructions send --preview to Quick Reference
- Document TUI categories in commands.md

## [0.2.26] - 2026-01-18

### Fixed

- Display response artifacts in `synapse send --response` mode
  - Response content from `task.artifacts` was not displayed to the user
  - Now shows response content with proper indentation for multiline output

## [0.2.25] - 2026-01-18

### Added

- PTY display `:R` flag to indicate response is expected
  - New format: `[A2A:<task_id>:<sender_id>:R]` when `response_expected=true`
  - Agents can now visually identify when `--reply-to` is required
- Failsafe retry for `--reply-to` 404 errors
  - When `--reply-to` target task doesn't exist (404), automatically retry as new message
  - Prevents message loss when receiver mistakenly uses `--reply-to` for `--no-response` messages

### Documentation

- Sync plugin skills with `.claude/skills/` and `.codex/skills/` directories
- Add `/tasks/create` endpoint to API reference in skill documentation
- Update short task ID documentation for `--reply-to` option
- Update agent templates (default.md, gemini.md) with `:R` flag documentation

## [0.2.24] - 2026-01-18

### Fixed

- Poll sender's server for reply when using `--response` flag
  - Problem: `synapse send --response` never received replies because it polled the target server instead of the sender's server where `--reply-to` stores the response
  - Solution: When `--response` is used, poll the sender's server for `sender_task_id` completion instead of the target server

## [0.2.23] - 2026-01-18

### Added

- Support prefix match for `--reply-to` short task IDs
  - Add `TaskStore.get_by_prefix()` method for case-insensitive prefix matching
  - PTY displays 8-char short IDs (e.g., `[A2A:54241e7e:sender]`)
  - `--reply-to 54241e7e` now works with short IDs displayed in PTY
  - Return 400 error for ambiguous prefixes (multiple matches)

### Documentation

- Sync .codex/skills with plugins and fix metadata field naming

## [0.2.22] - 2026-01-18

### Fixed

- Register task on sender's server for `--reply-to` to work
  - Problem: `--reply-to` always failed with "Task not found" because `sender_task_id` was created in the CLI process's in-memory task_store, which disappeared when the process exited
  - Solution: When `--response` is used, call `POST /tasks/create` on the sender's running agent server (via UDS or HTTP) instead of creating the task locally
  - The agent server's task_store persists as long as the agent is running, enabling `--reply-to` to find the task

### Added

- New `POST /tasks/create` endpoint to create task without sending to PTY
- `sender_endpoint` and `sender_uds_path` fields in sender_info for server-side task registration

### Changed

- Extract `_extract_sender_info_from_agent()` helper function to reduce code duplication

### Documentation

- Update task ownership design document with new server-side registration approach
- Update A2A communication guide with metadata structure changes
- Add `/tasks/create` to API reference

## [0.2.21] - 2026-01-18

### Documentation

- Clarify `--response` vs `--no-response` flag usage guidance
  - Add decision table for choosing the correct flag based on message intent
  - Rule: If your message asks for a reply, use `--response`
- Clarify `--reply-to` usage when receiving messages
  - Use `--reply-to` only when replying to questions/requests
  - Delegated tasks don't need a reply
- Sync changes across all skill files and templates

## [0.2.20] - 2026-01-17

### Fixed

- Redesign task ownership for `--reply-to` to work across agents
  - Tasks are now created on the **sender** side when using `--response` flag
  - `sender_task_id` is included in request metadata and displayed in PTY output
  - Enables `--reply-to` to work for same-type agent communication (e.g., claude-to-claude)

### Changed

- Simplify codebase by removing duplications
  - Consolidate duplicate artifact formatting functions in `a2a_compat.py`
  - Remove redundant regex search in `error_detector.py`
  - Consolidate exception handlers in `controller.py`
  - Remove redundant settings lookup in `input_router.py`

### Documentation

- Add task ownership design document (`docs/TASK_OWNERSHIP_DESIGN.md`)
- Add fallback strategy for `--reply-to` when sender didn't use `--response`
- Add receiving and replying section to A2A communication guide

## [0.2.19] - 2026-01-17

### Fixed

- Add type-port shorthand support for `synapse send` command
  - When multiple agents of the same type are running, use `claude-8100` format to target specific instances
  - Target resolution priority: Full ID > Type-port > Agent type
  - Show helpful hints when ambiguous target is detected

### Documentation

- Clarify `/tasks/send-priority` naming convention in API docs
  - Document that endpoint path intentionally omits `x-` prefix for URL readability
  - Note that `x-` prefix is used for metadata fields (`x-sender`, `x-response-expected`)
- Sync target format documentation across all files
  - README.md, CLAUDE.md, guides/references.md, skill files, templates

## [0.2.18] - 2026-01-17

### Fixed

- Fix `synapse config` saving "Back to main menu" as a settings key
  - questionary `Choice(value=None)` uses title as value, not None
  - Use sentinel value `_BACK_SENTINEL` to properly detect back navigation
- Fix confirm dialog in `synapse config` not exiting on Ctrl+C
  - Handle `None` return from `questionary.confirm().ask()`

### Documentation

- Add `--reply-to` parameter documentation for roundtrip communication
  - Essential for completing `--response` requests
  - Receiver MUST use `--reply-to <task_id>` to link their response
  - Updated: README.md, CLAUDE.md, guides, skill files, templates
- Clarify `--response` / `--no-response` flag descriptions
  - `--response`: Roundtrip mode - sender waits, receiver MUST reply
  - `--no-response`: Oneway mode - fire and forget (default)
- Fix Priority 5 sequence documentation in api.md
  - Corrected to: `controller.interrupt()` followed immediately by `controller.write()` (no waiting)
- Add `delegate.md` schema documentation to delegation skill
  - YAML frontmatter structure, field reference, rule evaluation

## [0.2.17] - 2026-01-16

### Added

- `synapse config` command for interactive settings management (#72)
  - TUI-based settings editor using questionary library
  - Edit user (`~/.synapse/settings.json`) or project (`./.synapse/settings.json`) settings
  - Categories: Environment Variables, Instructions, A2A Protocol, Delegation, Resume Flags
  - `synapse config show` displays current merged settings (read-only)
  - `synapse config show --scope user|project|merged` for scope-specific view

### Dependencies

- Add `questionary>=2.0.0` for interactive TUI prompts

## [0.2.16] - 2026-01-15

### Added

- Critical Write Protocol (Read-After-Write verification) in `.synapse/file-safety.md`
  - Agents must verify their writes by reading the file back immediately
  - Retry mechanism for failed or incorrect writes
  - New enforcement rule: "EVERY WRITE NEEDS VERIFICATION. NO EXCEPTIONS."

### Fixed

- Fix "EDITING FILE" not displaying in `synapse list` for some agents
  - `synapse file-safety lock` now correctly passes `agent_id` and `agent_type` to database
  - Support short agent names (e.g., "claude") by looking up live agents via `get_live_agents()`
  - Extract `agent_type` from agent_id format (`synapse-{type}-{port}`) as fallback
  - Refactored agent lookup logic into `_resolve_agent_info()` helper function

## [0.2.15] - 2026-01-15

### Fixed

- Pass registry to `send_to_local()` in `a2a.py send` command for transport display
  - TRANSPORT column was not updating because registry was not passed
  - Now correctly shows `UDS→` / `→UDS` during communication

## [0.2.14] - 2026-01-15

### Added

- Transport display retention feature for `synapse list --watch` mode
  - Communication events now persist for 3 seconds after completion
  - Makes it possible to observe brief communication events in real-time
  - New `registry.get_transport_display()` method with configurable retention period
  - Stores `last_transport` and `transport_updated_at` for retention logic

## [0.2.13] - 2026-01-15

### Added

- Real-time transport display in `synapse list --watch` mode
  - Show `UDS→` / `TCP→` for sending agent
  - Show `→UDS` / `→TCP` for receiving agent
  - Clear to `-` when communication completes
  - TRANSPORT column only appears in watch mode
- New `registry.update_transport()` method for tracking active communication
- Specification document: `docs/transport-display-spec.md`

## [0.2.12] - 2026-01-14

### Changed

- Unify response option flags between `synapse send` and `a2a.py send` (#96)
  - Replace `--return` flag with `--response/--no-response` flags
  - Default behavior is now "do not wait for response" (safer)
  - Both commands now have consistent flag names and defaults
- Update shell.py and shell_hook.py to use `--response` flag instead of `--return`

### Documentation

- Update all guides, skills, and templates to use new `--response/--no-response` flags
- Update `docs/universal-agent-communication-spec.md` with new flag names

## [0.2.11] - 2026-01-14

### Added

- `--reply-to` option for `a2a.py send` command to attach response to existing task (#99)
  - Enables agents to complete tasks by sending responses back to original task
  - Used for same-type agent communication (e.g., Claude to Claude)

### Fixed

- Accurate "EDITING FILE" display in `synapse list` using PID-based file locks (#100)
  - Only show files locked by the agent's own process tree
  - Filter out stale locks from other processes
- Same-type agent communication deadlock issue (#99)
  - Add `in_reply_to` metadata support for task completion

### Changed

- Refactor codebase by extracting helpers and reducing duplication (#98)
  - Add `A2ATask.from_dict()` class method
  - Add `_db_connection()` context manager for cleaner DB handling
  - Extract helper functions across multiple modules
  - Total: -109 lines of code while preserving functionality

### Tests

- Improve test coverage for logging, server, cli, and proto modules (#101)
- Fix proto import test failure in CI environment

## [0.2.10] - 2026-01-13

### Fixed

- `synapse send` command now works from any directory (#92)
  - Use package-relative path instead of hardcoded relative path
  - Remove unnecessary `PYTHONPATH` manipulation

## [0.2.9] - 2026-01-13

### Added

- `synapse init` now copies all template files from `templates/.synapse/` to target directory
  - Includes: `settings.json`, `default.md`, `delegate.md`, `file-safety.md`, `gemini.md`
  - Prompts for overwrite confirmation when `.synapse/` directory already exists

### Changed

- `synapse init` now checks for `.synapse/` directory existence (not just `settings.json`)
- Overwrite prompt now asks about the entire `.synapse/` directory

## [0.2.8] - 2025-01-13

### Added

- `synapse send` command with `--from` option for inter-agent communication (#86)
- `synapse instructions` command for manual instruction management (#87)
  - `synapse instructions show [agent]` - Display instruction content
  - `synapse instructions files [agent]` - List instruction files
  - `synapse instructions send <agent>` - Send instructions to running agent

### Fixed

- UDS server startup and socket existence checks (#89)
- Always allow HTTP fallback when UDS connection fails
- Set UDS directory permissions to 755 for sandboxed apps
- Move UDS socket to `/tmp/synapse-a2a/` for sandbox compatibility
- Update test mocks for UDS server startup
- Address CodeRabbit review comments on PR #89

### Changed

- Standardize on `synapse send` command across all documentation
- Recommend `synapse send` for inter-agent communication
- Clarify `@agent` pattern vs external A2A tool usage

### Documentation

- Add UDS transport layer and separate standard/extension endpoints
- Use `x-` prefix for Synapse extension fields in A2A metadata
- Add explicit READY status verification instructions
- Add Codex sandbox network configuration guide
- Update delegation skill and api.md documentation
- Sync skill files across .claude and plugins

## [0.2.6] - 2025-01-12

### Added

- Unix Domain Socket (UDS) transport for local A2A communication (#81)
  - Lower latency and overhead for same-machine agent communication
  - Automatic fallback to HTTP when UDS unavailable

### Fixed

- PID-based lock management for stale lock detection (#80)
  - Detect and clean up stale locks from crashed processes
  - Improve file safety reliability in multi-agent scenarios
- Enable history and file safety in default settings.json
- Add httpx to requirements (#83)
- Resolve AsyncMock RuntimeWarning in test_a2a_compat_extended (#84)
- Fix deprecated `asyncio.get_event_loop_policy` usage in conftest (#84)
- Fix deprecated `datetime.utcnow` usage in test_utils (#84)

### Changed

- Install gRPC dependency group to enable previously skipped tests (#84)
- Achieve 100% test pass rate (985 tests)

### Documentation

- Update file-safety guide with PID-based lock management (#82)

## [0.2.5] - 2025-01-12

### Fixed

- Handle `PermissionError` correctly in `is_process_running` (#75)
  - `PermissionError` from `os.kill(pid, 0)` means the process exists but we don't have permission to signal it
  - Previously this was incorrectly treated as "process not found", causing agents to wrongly delete other agents' registry files

## [0.2.4] - 2025-01-12

### Changed

- Separate `@agent` pattern (user PTY input) and `a2a.py send` (AI agent command)
  - `@agent` pattern no longer accepts `--response`/`--no-response` flags
  - AI agents use `python3 synapse/tools/a2a.py send` with explicit flags
- Refactor `delegation.mode` into two independent settings:
  - `a2a.flow` - Controls response behavior (roundtrip/oneway/auto)
  - `delegation.enabled` - Enables/disables automatic task delegation
- Remove `synapse delegate` CLI subcommand (use settings.json instead)

### Added

- `--response` / `--no-response` flags for `a2a.py send` command
- `a2a.flow` setting with three modes:
  - `roundtrip`: Always wait for response (flags ignored)
  - `oneway`: Never wait for response (flags ignored)
  - `auto`: AI decides via flags (default)
- New guide: `guides/a2a-communication.md`

### Documentation

- Update SKILL.md with AI judgment guidance for response control
- Update agent templates (gemini.md, default.md) with send command examples
- Clarify separation between user and AI agent communication methods

## [0.2.3] - 2025-01-11

### Added

- `synapse --version` flag to display version information (#66)
- `synapse stop` now accepts agent ID for precise control (#67)
  - Example: `synapse stop synapse-claude-8100`

### Documentation

- Enhanced `synapse stop --help` with detailed examples and tips

## [0.2.2] - 2025-01-11

### Fixed

- Add `httpx` to runtime dependencies (was causing ModuleNotFoundError) (#64)
- Remove `$schema` key from plugin.json (was causing installation error) (#62)
- Move type stubs (`types-pyyaml`, `types-requests`) from runtime to dev dependencies

### Documentation

- Improve CLI `--help` with detailed descriptions and examples (#63)

## [0.2.1] - 2025-01-11

### Added

- Agent-memory skill for knowledge persistence (#52)
- Claude Code plugin marketplace support (#51)
- `.synapse` templates for `synapse init` (#55)
- Skip initial instructions when resuming context (#54)

### Fixed

- Apply settings env before checking history enabled (#59)
- Support `--flag=value` forms in `is_resume_mode()`
- Add correct resume flags for codex and gemini
- Add `-r` flag for gemini based on agent feedback

### Changed

- Reorganize skills into plugins directory structure
- Reorganize skills with references pattern

### Documentation

- Update README and guides for Resume Mode
- Add instructions for Codex skill expansion via `.codex` directory
- Add release guide (#50)
- Enhance synapse-a2a and delegation skills with comprehensive features

## [0.2.0] - 2025-01-05

### Added

- File locking and modification tracking for multi-agent safety (#46)
- Session history persistence with search, cleanup, stats, and export (#30, #34)
- Automatic task delegation between agents (#42)
- A2A response mechanism for inter-agent communication (#41)
- `.synapse` settings for customizable instructions and env (#37)
- Skill installation to `synapse init/reset` commands
- Pre-commit hooks for ruff and mypy
- `synapse list` command with watch mode (#28)
- synapse-a2a skill with Phase 2 history features
- gRPC support for high-performance A2A communication
- Webhook notifications for task completion
- API Key authentication for A2A endpoints
- SSE streaming for real-time task output
- HTTPS support with SSL certificates
- Output parser for structured CLI output artifacts
- Error detection and failed status for tasks

### Fixed

- Race conditions and silent failures in `synapse list --watch` (#31)
- Gemini initial instruction delivery race condition (#32)
- Interactive mode idle detection and Gemini PROCESSING status
- All mypy type checking errors
- Ruff formatting and linting violations

### Changed

- Reorganize delegation config to `delegation.md` format
- Use file references for initial instructions to avoid PTY buffer limits
- Update Claude Code profile to use hybrid pattern + timeout detection

### Documentation

- Add File Safety user guide
- Add session history feature documentation
- Add testing guidelines for registry status updates
- Define project mission - enable agent collaboration without changing behavior

## [0.1.0] - 2024-12-28

### Added

- Initial release of Synapse A2A
- PTY wrapper for CLI agents (Claude Code, Codex, Gemini)
- Google A2A Protocol implementation
- Agent Card with context extension (`x-synapse-context`)
- `@agent` pattern routing for inter-agent communication
- File-based agent registry (`~/.a2a/registry/`)
- External A2A agent connectivity
- Profile-based configuration (YAML configs per agent type)
- Port range management per agent type
- Idle detection strategies (pattern, timeout, hybrid)

### Documentation

- A2A design documents and project guidelines
- External agent connectivity vision document
- PyPI publishing instructions

[0.2.17]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.16...v0.2.17
[0.2.16]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.15...v0.2.16
[0.2.15]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.14...v0.2.15
[0.2.14]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.13...v0.2.14
[0.2.13]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.12...v0.2.13
[0.2.12]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.11...v0.2.12
[0.2.11]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.10...v0.2.11
[0.2.10]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.9...v0.2.10
[0.2.9]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.8...v0.2.9
[0.2.8]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.7...v0.2.8
[0.2.6]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.5...v0.2.6
[0.2.5]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.4...v0.2.5
[0.2.4]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.3...v0.2.4
[0.2.3]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.2...v0.2.3
[0.2.2]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/s-hiraoku/synapse-a2a/releases/tag/v0.1.0
