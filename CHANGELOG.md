# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.6.3] - 2026-02-19

### Added

- **git-cliff changelog generation**: `cliff.toml` config and `scripts/generate_changelog.py` wrapper for automated CHANGELOG.md generation from Conventional Commits (#242)

### Changed

- **Release workflow Step 1**: Updated to use `python scripts/generate_changelog.py` instead of manual changelog writing (#242)

### Fixed

- **Skill creator YAML template**: Quoted `description` field in `new_skill.sh` to prevent YAML array parsing (#242)
- **Skill creator name validation**: Reject leading/trailing/consecutive hyphens and purely numeric names (#242)
- **spawn/start `tool_args` passthrough**: `argparse.REMAINDER` now correctly handles named options and NUL bytes in env vars (#241)

### Documentation

- Updated release guide and `/release` skill with git-cliff generation steps (#242)

### Tests

- New `tests/test_generate_changelog.py` (15 tests): git-cliff binary detection, invocation wrapper, CHANGELOG update logic, CLI integration (#242)

## [0.6.2] - 2026-02-18

### Added

- **Agent directory deploy indicators**: Each skill row shows `[C✓ A✓ G·]` indicators for .claude/.agents/.gemini directory presence (#239)
- **Skill detail deploy status**: SYNAPSE scope skill detail view shows per-agent deployment status across user and project scopes (#239)
- **Deploy All action**: One-click deployment of a SYNAPSE skill to all agent directories in user scope, with confirmation prompt (#239)
- **`check_deploy_status()` helper**: New function in `skills.py` to check skill deployment across all agent directories (#239)

### Changed

- **Manage Skills TUI navigation**: Replaced flat skill list with scope-based submenu (Synapse → User → Project), PLUGIN scope excluded from end-user TUI (#239)
- **Python dependency**: Updated to Python 3.14 (#235)

### Fixed

- **`cmd_skills_move` dry-run order**: SYNAPSE/PLUGIN scope rejection now checked before dry-run branch to prevent misleading output (#239)
- **`_skills_menu` Back/Quit index**: Fixed off-by-one error in `build_numbered_items` footer index calculation (#239)
- **Path traversal in skill names**: `validate_skill_name()` now rejects `"."` and `".."` to prevent directory traversal (#239)
- **`create_skill` error handling**: `cmd_skills_create` and `_create_flow` now catch `ValueError` from `validate_skill_name` (#239)
- **CLAUDECODE env leak in spawn**: Unset `CLAUDECODE` env var in spawned agent commands to prevent nested-session detection failure (#238)

### Documentation

- Updated guides/usage.md and guides/references.md with scope submenu flow and agent directory indicator table (#239)
- Synced spawn docs across SKILL.md, commands.md, examples.md with `synapse reply` known limitation (#238)
- Added spawn troubleshooting section to guides/troubleshooting.md (#238)

### Tests

- Added `TestCheckDeployStatus` (6 tests) to `test_skills.py`: deployment detection across user/project scopes, shared agents dir, none dirs (#239)
- Added `TestManageSkillsDisplay` (6 tests) to `test_cmd_skill_manager.py`: skill labels, scope menu, detail header deploy status (#239)
- Added `test_reject_dot_and_dotdot` to `TestSkillNameValidation` (#239)
- Added CLAUDECODE env unset tests to `test_spawn.py` (#238)

## [0.6.1] - 2026-02-18

### Added

- **Auto GitHub Release workflow**: Creates git tag + GitHub Release automatically when `pyproject.toml` version changes on main (#234)

### Changed

- **Release process**: Tag creation and GitHub Release automated via `auto-release.yml`; manual steps reduced to version bump, changelog update, and PR merge (#234)

### Fixed

- **`extract_changelog` error handling**: Raises `ValueError` instead of `sys.exit(1)` for testability (#234)

### Documentation

- Updated release guide and READMEs for auto-release workflow (#234)

### Tests

- New `tests/test_extract_changelog.py`: changelog extraction script tests (#234)

## [0.6.0] - 2026-02-17

### Added

- **`synapse spawn` command**: Spawn a single agent in a new terminal pane (`synapse spawn claude --name Helper --role "task runner"`) with auto-assigned port, custom name/role, and skill set support (#195)
- **`POST /spawn` API endpoint**: Agents can programmatically spawn other agents via A2A protocol with `run_in_threadpool` for non-blocking execution
- **Headless mode (`--headless`)**: Spawned agents skip all interactive setup (name/role prompts, startup animation, approval prompts) while keeping A2A server and initial instructions active
- **Ghostty terminal support**: New `create_ghostty_window()` for spawning agents in Ghostty windows on macOS
- **Pane auto-close**: All supported terminals (tmux, zellij, iTerm2, Terminal.app, Ghostty) automatically close spawned panes when agent process terminates — zellij uses `--close-on-exit`, iTerm2/Terminal.app/Ghostty use `exec` to replace the shell process
- **tool_args passthrough**: `synapse spawn` and `synapse team start` now accept `-- <args>` to pass CLI flags (e.g., `--dangerously-skip-permissions`) through to the underlying agent tool. Also available via `tool_args` field in `POST /spawn` and `POST /team/start` API endpoints (#229)
- **Injection observability**: Structured `INJECT/{RESOLVE,DECISION,DELIVER,SUMMARY}` log points in `_send_identity_instruction()` for diagnosing initial instruction injection failures (`grep INJECT` in logs) (#229)

### Changed

- **Agent spec format**: Extended to 6 colon-separated fields (`profile:name:role:skill_set:port:headless`)
- **`_build_agent_command()`**: Uses `sys.executable -m synapse.cli` for consistent Python environment across parent/child processes, with `use_exec` parameter for shell-based terminals
- **Port validation**: Agent spec port field validated with `isdigit()` to reject non-numeric values
- **`--skill-set` short flag**: Changed from `-ss` to `-S` for standard single-character convention
- **Logger unification**: `_send_identity_instruction()` now uses module-level `logger.*` consistently (was mixing `logging.*` and `logger.*`)
- **Code simplification**: Extracted focused helper methods in `controller.py` (`_wait_for_input_ready()`, `_build_identity_message()`), `terminal_jump.py` (`_get_spec_field()`), and `cli.py` (`_run_pane_commands()`) to improve readability

### Fixed

- **Zellij pane revival**: Added `--close-on-exit` to all `zellij run` commands to prevent panes from surviving after agent kill
- **Plugin skill sync**: `.gemini/skills/synapse-a2a/references/file-safety.md` was missing `--wait` lock examples that existed in the plugin source
- **Spawn error handling**: `subprocess.run` uses `check=True` for proper error propagation; empty `create_panes` result raises `RuntimeError`
- **`POST /spawn` error response**: Returns HTTP 500 (not 200) when `spawn_agent` fails
- **CLAUDE.md**: Removed duplicated "Agent Teams feature tests" block

### Documentation

- Added spawn documentation to SKILL.md, commands.md, api.md, examples.md (synced across 4 locations)
- Updated README.md (all 6 languages), CLAUDE.md, guides/usage.md, guides/references.md
- Documented Ghostty layout/all_new limitation in docstring

### Tests

- New `tests/test_spawn.py` (31 tests): CLI parsing with real argparse, core `spawn_agent()`, Ghostty panes, port validation, headless mode, `wait_for_agent()`
- New `tests/test_spawn_api.py` (6 tests): POST /spawn endpoint behavior, error handling, parameter pass-through
- Added `TestExecPrefixForPaneAutoClose` (8 tests): exec behavior verification per terminal type
- Added `test_zellij_close_on_exit_always_present` to `test_auto_spawn.py`
- New `tests/test_injection_observability.py` (16 tests): RESOLVE/DECISION/DELIVER/SUMMARY structured log verification
- New `tests/test_tool_args_passthrough.py` (25 tests): tool_args through _build_agent_command, create_panes, spawn_agent, CLI parsing, API models

## [0.5.2] - 2026-02-15

### Added

- **anthropic-skill-creator plugin skill**: Bundled Anthropic's skill creation methodology as a plugin skill (`plugins/synapse-a2a/skills/anthropic-skill-creator/`)
- **Create Skill guided flow**: `synapse skills create` shows step-by-step guidance for creating skills using `/anthropic-skill-creator` inside an agent
- **Shared TUI helpers**: Extracted `TERM_MENU_STYLES`, `MENU_SEPARATOR`, `build_numbered_items()` to `synapse/styles.py` for consistent menu styling

### Changed

- **Skill Manager TUI**: Added `[N]` keyboard shortcuts to all menus, matching config TUI pattern
- **Scope display**: Manage Skills now shows descriptive scope headers (e.g., "Synapse — Central Store (~/.synapse/skills/)")
- **Config TUI**: Unified menu styling with shared helpers from `synapse/styles.py`

### Documentation

- Updated `synapse skills create` description across README, CLAUDE.md, guides, and plugin skills
- Added `anthropic-skill-creator` to plugin README

## [0.5.1] - 2026-02-14

### Added

- **Vim-style navigation**: `hjkl` key bindings for `synapse list` interactive selection (Enter=jump, K=kill confirmation)
- **SSL/TLS options**: `--ssl-cert` and `--ssl-key` for `synapse start` command
- **File safety wait options**: `--wait-interval` for `synapse file-safety lock`

### Changed

- **Installation docs**: Unified macOS/Linux/WSL2 install section across all 6 language READMEs with pipx as recommended method
- **Homebrew formula**: Added Rust build dependency, `preserve_rpath`, and resource marker insertion
- **Config TUI**: Added `--no-rich` flag to use legacy questionary-based interface
- **History cleanup**: Added `--dry-run` and `--no-vacuum` options

### Fixed

- **Homebrew formula**: Switched to pip+venv pattern for reliable installation (#216)

### Documentation

- Synced plugin skill references (commands.md, file-safety.md) across all 3 scopes
- Updated footer hints in `synapse list` for new key bindings

## [0.5.0] - 2026-02-13

### Added

- **Homebrew formula**: `homebrew/synapse-a2a.rb` using `Language::Python::Virtualenv` pattern for native macOS installation via `brew install`
- **Scoop manifest**: `scoop/synapse-a2a.json` with venv-based installer, `checkver`, and `autoupdate` for Windows users
- **CI/CD workflow**: `.github/workflows/update-installers.yml` auto-generates PR to update formula/manifest on `v*` tag push
- **Helper scripts**: `scripts/patch_homebrew_formula.py` (patches poet-generated resource stanzas) and `scripts/update_scoop_manifest.py` (updates version/hash from PyPI)

### Changed

- **README.md install section**: Platform-specific install instructions (macOS Homebrew / Linux pipx / Windows Scoop+WSL2 / Developer) with upgrade and uninstall commands
- **guides/multi-agent-setup.md**: Added user-facing install section (Homebrew / pipx / Scoop) alongside existing developer section

### Removed

- `requirements.txt` — redundant with `pyproject.toml` dependencies, not referenced by any code or CI

### Documentation

- Updated README.zh.md and README.es.md install sections to match English README

## [0.4.4] - 2026-02-12

### Added

- **Skill set details in initial instructions**: When an agent starts with a skill set, the skill set name, description, and included skills are now included in the agent's initial instructions
- `format_skill_set_section()` utility function for formatting skill set information
- `skill_set` parameter on `TerminalController` to pass skill set through to instruction generation

### Documentation

- Updated CLAUDE.md startup sequence to mention skill set info
- Added skill set integration section to `guides/agent-identity.md`
- Added skill set instruction note to `guides/references.md`
- Synced plugin skills (SKILL.md, commands.md) to `.claude/` and `.agents/`

### Tests

- Added `tests/test_controller_skill_set.py` with 6 tests covering skill set in instructions

## [0.4.3] - 2026-02-12

### Added

- **Handoff-by-default for `synapse team start`**: 1st agent takes over current terminal via `os.execvp`, remaining agents start in new panes
- `--all-new` flag to restore previous behavior (all agents in new panes)
- Terminal.app (tabs) support for team start pane creation

### Changed

- Default `synapse team start` behavior: 1st agent = handoff (current terminal), rest = new panes
- Agent spec format extended to `profile[:name[:role[:skill_set]]]`

### Documentation

- Updated all 7+ documentation files for handoff behavior and `--all-new` flag
- Plugin skills: added missing commands (`delete`/`move` skill, `set show`, `trace`), `--message-file`/`--stdin`/`--attach` options, `SHUTTING_DOWN` status
- Fixed Zellij terminal jump description to match implementation

### Tests

- Added `TestAgentSpecParsing` for `profile:name:role:skill_set` format
- Added handoff and `--all-new` behavior tests

## [0.4.2] - 2026-02-12

### Added

- Bundled default skill set definitions at `synapse/templates/.synapse/skill_sets.json`
- Fallback loading of bundled skill sets when project `skill_sets.json` is missing
- Support for `profile:name:role:skill_set` format in `synapse team start`

### Changed

- Startup skill-set selector switched to `simple_term_menu` based TUI
- Skill-set selector row format simplified to `N. <name> - <count> skills`
- Team start pane creation support expanded to zellij

### Documentation

- Updated `guides/usage.md` and `guides/references.md` for team start and zellij behavior

### Tests

- Added/updated tests for skill-set loading fallback, skill-set selector TUI, and team start auto-spawn behavior

## [0.4.1] - 2026-02-11

### Added

- **zellij support for `synapse team start`**
  - Added pane creation command generation for zellij environments
  - Added `--layout` mapping for zellij (`horizontal` -> right, `vertical` -> down, `split` -> balanced alternating splits)

### Changed

- Updated team-start terminal support messaging to include zellij

### Documentation

- Added/updated `synapse team start` references in `guides/usage.md` and `guides/references.md`

### Tests

- Added zellij coverage in `tests/test_auto_spawn.py` for pane generation, layout direction handling, and team-start execution path

## [0.4.0] - 2026-02-10

### Added

- **B1: Shared Task Board** - SQLite-based task coordination for multi-agent workflows
  - `synapse tasks list/create/assign/complete` CLI commands
  - `GET/POST /tasks/board`, `/tasks/board/{id}/claim`, `/tasks/board/{id}/complete` API endpoints
  - Atomic task claiming, dependency tracking (`blocked_by`), auto-unblocking on completion
- **B2: Quality Gates (Hooks)** - Configurable shell hooks for status transition control
  - `on_idle` and `on_task_completed` hook types
  - Exit code semantics: 0=allow, 2=deny, other=allow with warning
  - Environment variables: `SYNAPSE_AGENT_ID`, `SYNAPSE_AGENT_NAME`, `SYNAPSE_STATUS_FROM`, `SYNAPSE_STATUS_TO`
- **B3: Plan Approval Workflow** - Human-in-the-loop plan review
  - `synapse approve/reject` CLI commands
  - `POST /tasks/{id}/approve`, `POST /tasks/{id}/reject` API endpoints
  - `plan_mode` metadata flag for plan-only instructions
- **B4: Graceful Shutdown** - Cooperative agent shutdown
  - `synapse kill` now sends A2A shutdown request before SIGTERM (30s timeout)
  - `SHUTTING_DOWN` status (red) added to agent status system
  - `-f` flag for immediate SIGKILL (previous behavior)
- **B5: Delegate/Coordinator Mode** - Role-based agent separation
  - `--delegate-mode` flag for `synapse <agent>` commands
  - Coordinators cannot acquire file locks (file editing denied)
  - Auto-injected `[COORDINATOR MODE]` instructions for task delegation
- **B6: Auto-Spawn Split Panes** - Multi-agent terminal setup
  - `synapse team start <agents...> [--layout split|horizontal|vertical]`
  - `POST /team/start` A2A endpoint for agent-initiated team spawning
  - Supports tmux, iTerm2, Terminal.app (fallback: background spawn)
- **`synapse skills` command** - Unified skill management with interactive TUI and non-interactive subcommands
  - `synapse skills list [--scope]` - Discover skills across all scopes (Synapse, User, Project, Plugin)
  - `synapse skills show <name>` - Show skill metadata and paths
  - `synapse skills delete <name>` - Delete a skill (with confirmation, plugin skills protected)
  - `synapse skills move <name> --to <scope>` - Move skills between User/Project scopes
  - `synapse skills deploy <name> --agent claude,codex --scope user` - Deploy from central store to agent directories
  - `synapse skills import <name>` - Import skills to central store (`~/.synapse/skills/`)
  - `synapse skills add <repo>` - Install from repository via `npx skills` with auto-import to central store
  - `synapse skills create` - Create new skill template (uses skill-creator if available)
  - `synapse skills set list` / `synapse skills set show <name>` - Skill set management
- **SYNAPSE skill scope** - New central skill store at `~/.synapse/skills/` with flat structure
  - Skills are deployed from central store to agent-specific directories (`.claude/skills/`, `.agents/skills/`, `.gemini/skills/`)
  - `SYNAPSE_SKILLS_DIR` environment variable for path override
- **`synapse/skills.py`** - Core skill management module with discovery, deploy, import, create, and skill set CRUD
- **`synapse/commands/skill_manager.py`** - TUI and CLI command implementations for skill management

### Changed

- **`synapse/cli.py`** - Integrated `synapse skills` subcommand tree (list, show, delete, move, deploy, import, add, create, set)
- **`synapse/paths.py`** - Added `get_synapse_skills_dir()` for central skill store path resolution

### Removed

- **`synapse set skills`** - Removed separate skill set command tree; all functionality consolidated under `synapse skills`
- **`synapse/commands/skill_sets.py`** - Migrated to `skills.py` and `skill_manager.py`

### Documentation

- Updated `CLAUDE.md` with Agent Teams commands, architecture, and test entries
- Updated `README.md` feature table, CLI commands, and API endpoints
- Updated README.md, CLAUDE.md, guides/usage.md, guides/references.md with skill management commands
- Updated plugin skills (SKILL.md, references/commands.md) and synced to `.agents/` and `.gemini/`
- Updated code-doc-mapping.md with skills.py and skill_manager.py entries

### Tests

- Added 19 tests for core skills module (SYNAPSE scope, deploy, import, create, add, skill set CRUD)
- Added 6 tests for skill manager commands (deploy, import, create, set list/show, synapse scope listing)

## [0.3.25] - 2026-02-09

### Fixed

- **`synapse reply` documentation** - `--from` flag was incorrectly shown as required; it is only needed in sandboxed environments (like Codex). Basic usage is just `synapse reply "<message>"`
- **`synapse send` template examples** - Fixed `--from claude` (agent type) to use agent ID format (`synapse-<type>-<port>`) or omit `--from` entirely (auto-detected via PID matching)
- **Updated 30 files** across all documentation, skills, README translations (ja/ko/es/zh/fr), guides, and templates

## [0.3.24] - 2026-02-08

### Added

- **synapse-reinst skill** - Re-inject initial instructions after `/clear` or context reset
  - Script reads environment variables (`SYNAPSE_AGENT_ID`, `SYNAPSE_AGENT_TYPE`, `SYNAPSE_PORT`) to restore agent identity
  - Fallback path with conditional section processing when synapse module is not importable
  - Deployed to `.claude/`, `.gemini/`, and `.agents/` skill directories

### Changed

- **Migrate Codex skill directory** from `.codex/skills/` to `.agents/skills/` (official Codex CLI skill path)
  - Rename `_copy_skill_to_codex()` → `_copy_skill_to_agents()` in `cli.py`
  - Rename `_copy_claude_skills_to_codex()` → `_copy_claude_skills_to_agents()` in `cli.py`
- **Remove `.opencode/skills/`** - OpenCode auto-scans `.agents/skills/`, eliminating redundant copies
- **Update skill examples** to use `synapse send`/`synapse reply` commands exclusively
  - Replace all deprecated `@agent` patterns removed in v0.3.9
  - Add `--response`/`--no-response` flags and `synapse reply` examples
- **Update SKILL.md description** - Replace "routing @agent patterns" with "via synapse send/reply commands"
- **Update file-safety.md** - Replace `@gemini` pattern with `synapse send` command

### Removed

- Delete `.codex/` directory (migrated to `.agents/`)
- Delete `.opencode/` directory (redundant with `.agents/`)

### Documentation

- Update README.md and README.ja.md: `.codex/skills/` → `.agents/skills/`
- Update `guides/settings.md`: Codex skill path documentation
- Update `synapse-docs` skill references: code-doc-mapping.md, doc-inventory.md
- Update `opencode-expert` skill: add `.agents/skills/` to discovery paths
- Update `commands.md`: reset command description `.codex` → `.agents`

### Tests

- Add `tests/test_reinst_skill.py` with 9 test cases covering env var detection, registry lookup, instruction output, PID fallback, and edge cases
- Update `tests/test_settings.py`, `tests/test_cli.py`, `tests/test_cli_commands_coverage.py`, `tests/test_cli_extended.py` for `.codex` → `.agents` migration

## [0.3.23] - 2026-02-07

### Added

- **Reply target selection** - `synapse reply --to <sender_id>` to reply to a specific sender when multiple are pending
- **Reply target listing** - `synapse reply --list-targets --from <agent>` to show all pending senders
- **Configurable storage paths** - Override registry, external registry, and history DB paths via environment variables (`SYNAPSE_REGISTRY_DIR`, `SYNAPSE_EXTERNAL_REGISTRY_DIR`, `SYNAPSE_HISTORY_DB_PATH`)

### Changed

- **Simplify `paths.py`** - Extract `_resolve_path` helper to eliminate duplication across path resolution functions
- **Simplify `cli.py`** - De-duplicate `registry.unregister` calls and remove redundant `else` after `return`
- **Simplify `tools/a2a.py`** - Remove redundant `isinstance` type guards and unused variables
- **Move inline imports to module level** in `settings.py` for consistency

### Documentation

- Add external agent management commands (add, list, info, send, remove) to plugin skills
- Add authentication commands (setup, generate-key) to plugin skills
- Add logs, reset, resume mode, and file-safety cleanup-locks/debug commands to plugin skills
- Fix broadcast default priority documentation (3 → 1) to match implementation
- Add `--response` mode task creation flow and external agent endpoints to API reference

## [0.3.22] - 2026-02-06

### Fixed

- **Extra newline in CLI output** - `synapse send` / `synapse broadcast` no longer print double newlines
- **Error propagation** - `synapse send` and `synapse broadcast` now exit with non-zero code on failure (consistent with `synapse reply`)

### Changed

- **Refactor CLI a2a commands** - Extract shared helpers (`_get_a2a_tool_path`, `_run_a2a_command`, `_build_a2a_cmd`) to reduce duplication

### Documentation

- Add complete flags (`--from`, `--response`, `--no-response`) to broadcast command reference
- Fix inconsistent `DIR` → `WORKING_DIR` naming in skill documentation

## [0.3.21] - 2026-02-06

### Added

- **`synapse broadcast` command** - Send messages to all agents in the same working directory
  - `synapse broadcast "message" --from <agent_id>` - Send to all agents in current directory
  - `--cwd <path>` option to target a specific working directory
  - Useful for coordinating multiple agents working on the same project

### Removed

- **Gemini-specific instruction files** - Remove `gemini.md` templates in favor of unified default instructions

## [0.3.20] - 2026-02-05

### Fixed

- **Race condition in `synapse list`** - Add retry logic for port checks during agent status transitions
  - First port check uses 0.5s timeout, retry uses 1.0s timeout with 0.2s delay
  - Prevents false "agent dead" detection during PROCESSING → READY transitions
  - Improves reliability when multiple agents are starting simultaneously

### Added

- **Status timestamp tracking** - Add `status_updated_at` field to registry entries for debugging status transitions
- **Settings validation warnings** - Log warnings for unknown top-level keys in settings.json files
  - Helps catch typos and deprecated settings
  - Known keys: `env`, `instructions`, `approvalMode`, `a2a`, `resume_flags`, `list`

### Tests

- Add `TestPortCheckRetry` test class for port check retry logic
- Extract shared test helpers to reduce code duplication in test_cmd_list_watch.py

## [0.3.19] - 2026-02-04

### Removed

- **Delegation feature** - Remove auto-routing based on delegate.md rules
  - `synapse/delegation.py` and related tests
  - `delegate.md` template files
  - Delegation skill directories across all agent configs
  - `guides/delegation.md` guide
  - Delegation settings from settings.py and config TUI

### Changed

- Recommend using `--name` and `--role` flags (v0.3.11) for assigning specialized roles to agents instead of model-type-based delegation

### Documentation

- Update README and guides to remove delegation references
- Clarify one-way notifications vs delegated tasks

## [0.3.18] - 2026-02-04

### Documentation

- Add column descriptions to `synapse list --help` including EDITING_FILE requirement (#179)
- Add "Integration with synapse list" section to `synapse file-safety --help`
- Expand `synapse file-safety locks` help to mention EDITING_FILE column
- Add "List Integration" feature to README File Safety table
- Sync File Safety documentation across plugin skills

### Changed

- Simplify CLI with constants and data-driven patterns
  - Extract HISTORY_DISABLED_MSG and FILE_SAFETY_DISABLED_MSG constants
  - Consolidate subcommand help into subcommand_parsers dict
  - Use `name or agent_id` instead of ternary expressions

## [0.3.17] - 2026-02-03

### Fixed

- Type error in `synapse list` file safety lock lookup (removed redundant variable reassignment)
- Improve file-safety lock lookup with cleaner conditional expressions

### Changed

- Simplify non-interactive table output using data-driven column definitions
- Add `create_mock_list_locks` helper to test file for reduced duplication
- Add type annotations to test fixtures for better code quality

### Documentation

- Sync FILE_SAFETY env vars across documentation
- Add list category to synapse config TUI documentation

## [0.3.16] - 2026-02-02

### Added

- Long message file storage for TUI input limits
  - Messages exceeding ~200 characters are automatically stored in temporary files
  - Agents receive a file reference message instead of truncated content
  - Files are automatically cleaned up after TTL expires (default: 1 hour)
  - Configurable via `SYNAPSE_LONG_MESSAGE_THRESHOLD`, `SYNAPSE_LONG_MESSAGE_TTL`, `SYNAPSE_LONG_MESSAGE_DIR`

### Documentation

- Add long message handling documentation to skills and guides
- Update settings.md with new environment variables (Japanese)
- Sync plugin skills with long message feature documentation

## [0.3.15] - 2026-02-01

### Added

- File Safety instructions in default agent instructions (#168)
  - Add mandatory checklist for file locking before edits
  - Include lock/unlock commands in agent initial instructions
  - Prevents agents from forgetting to use file locking

### Changed

- Simplify code in core modules for improved readability
  - Extract `_format_ambiguous_target_error` helper in tools/a2a.py
  - Consolidate backspace key handling in list.py
  - Use walrus operator for regex match in registry.py
  - Simplify file path lookup in settings.py

### Documentation

- Improve file-safety.md with mandatory checklist and quick reference
- Update README test badge (1331 → 1389 tests)
- Add Task History and CURRENT column to Features table

## [0.3.14] - 2026-02-01

### Added

- Reply PTY injection for natural agent-to-agent conversation
  - When agent A sends a message with `--response` and agent B replies,
    the reply is written to agent A's PTY as `A2A: <message>`
  - Uses standard A2A: prefix for protocol consistency

- CURRENT column in `synapse list` display
  - Shows first 30 characters of the current task being processed
  - Helps users understand what each agent is working on

- History enabled by default
  - Task history is now enabled without setting environment variables
  - To disable, set `SYNAPSE_HISTORY_ENABLED=false` explicitly

### Fixed

- Use standard `A2A: ` prefix for PTY reply messages (protocol compliance)
- Task preview truncation to max 30 chars total (27 + "...")
- Handle undefined variables in conditional template sections
- Remove trailing newline from PTY reply content (let submit_seq handle it)
- Fix agent type regex to allow hyphens (e.g., `synapse-gpt-4-8120`)
- Normalize endpoint in `synapse reply` to avoid relative URL issues
- Fix `.serena/project.yml` empty base_modes/default_modes keys

### Documentation

- Update all documentation for history default change
- Update commands.md Output columns (ID, ROLE, CURRENT columns added)
- Sync skill files across all agent directories

## [0.3.13] - 2026-02-01

### Note

Features originally planned for v0.3.13 were consolidated into v0.3.14.
See v0.3.14 for reply PTY injection, CURRENT column, and history default changes.

## [0.3.12] - 2026-02-01

### Changed

- Refactor internal code for improved maintainability
  - Extract `format_role_section()` utility to reduce duplication between controller.py and instructions.py
  - Simplify `_evaluate_idle_status()` with dictionary lookup in controller.py
  - Extract `_determine_new_status()` helper for cleaner status transition logic
  - Simplify flow determination in tools/a2a.py with dictionary lookup
  - Extract sender validation helpers in tools/a2a.py

### Fixed

- Fix ruff linter errors in cli.py and instructions.py
  - Replace `try-except-pass` with `contextlib.suppress()` for cleaner exception handling
  - Remove extraneous f-string prefix from string without placeholders

### Documentation

- Synchronize `.synapse/` templates with source templates
  - Add role section (`{{#agent_role}}`) to default.md and gemini.md
  - Update `--response` / `--no-response` guidance with safer default recommendation
- Update skill files with consistent documentation across all agent directories
  - Sync synapse-a2a and delegation skills to .claude/, .codex/, .gemini/, .opencode/

## [0.3.11] - 2026-02-01

### Added

- Add Agent Naming feature for easy agent identification (#171)
  - `--name` and `--role` options for `synapse <profile>` command
  - `--no-setup` flag to skip interactive name/role prompts
  - `synapse rename <target> --name <name> --role <role>` command
  - `synapse rename <target> --clear` to remove name and role
  - Custom names have highest priority in target resolution
- Add `synapse kill <target>` command with confirmation dialog
  - Kill by custom name, agent ID, type-port, or agent type
  - `-f` flag for force kill without confirmation
- Add `synapse jump <target>` command for terminal navigation
  - Jump by custom name, agent ID, or agent type
  - Supports iTerm2, Terminal.app, Ghostty, VS Code, tmux, Zellij

### Changed

- Update target resolution priority order:
  1. Custom name (highest priority, exact match, case-sensitive)
  2. Full agent ID (`synapse-claude-8100`)
  3. Type-port shorthand (`claude-8100`)
  4. Agent type (only if single instance)
- Display shows name if set, internal processing uses agent ID
  - Prompts show name (e.g., `Kill my-claude (PID: 1234)?`)
  - `synapse list` NAME column shows custom name or agent type

### Documentation

- Update all skill files with Agent Naming documentation
- Add "Name vs ID" specification to README, CLAUDE.md, and guides
- Update target resolution examples in all documentation

## [0.3.10] - 2026-01-30

### Added

- Add `[REPLY EXPECTED]` marker to A2A message format
  - Messages sent with `--response` flag now include `A2A: [REPLY EXPECTED] <message>`
  - Receiving agents can identify when a reply is required vs optional
  - Messages without the marker indicate delegation/notification (no reply needed)
- Add `/reply-stack/get` endpoint for peek-before-send pattern
  - Get sender info without removing (use with `/reply-stack/pop` after successful reply)

### Changed

- Refactor reply stack from LIFO stack to map-based storage
  - Multiple senders can coexist without overwriting each other
  - Same sender's new message overwrites previous entry
  - Only store sender info when `response_expected=True`
- Unify parameter naming: `reply_expected` → `response_expected` in `format_a2a_message()`
  - Consistent with `response_expected` metadata field used throughout the codebase

### Documentation

- Update all skill files with `[REPLY EXPECTED]` message format documentation
- Update guides and README with new message format examples
- Update terminology from "reply stack" to "reply tracking" in user-facing docs

## [0.3.9] - 2026-01-30

### Added

- Add approval mode for initial instructions (#165)
  - New `approvalMode` setting: `"auto"` (skip prompt) or `"required"` (show preview before sending)
  - Show instruction preview with file list before agent startup
  - Support `[Y/n/s]` prompt for approve, cancel, or skip options
  - Add `--auto-approve` and `--require-approval` CLI flags
- Add startup TUI animation with animated Synapse logo
  - Left-to-right sweep animation effect
  - Display quick reference commands after logo
- Add `input_ready_pattern` profile setting for TUI ready detection
  - Detect when agent's input area is ready before sending instructions
  - Pattern-based detection (e.g., `❯` for Claude) or timeout-based fallback

### Removed

- Remove @Agent pattern feature
  - Delete `input_router.py` and all @Agent routing code
  - Use `synapse send` command exclusively for inter-agent communication
  - Simplify controller by removing input parsing and action execution

### Documentation

- Update all skill files with `approvalMode` settings
- Update README and guides to use `synapse send` instead of @Agent syntax

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

[0.6.3]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.6.2...v0.6.3
[0.6.2]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.6.1...v0.6.2
[0.6.1]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.6.0...v0.6.1
[0.6.0]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.5.2...v0.6.0
[0.5.2]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.5.1...v0.5.2
[0.5.1]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.4.4...v0.5.0
[0.4.4]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.4.3...v0.4.4
[0.4.3]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.3.24...v0.4.3
[0.2.17]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.16...v0.2.17
[0.3.24]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.3.23...v0.3.24
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
