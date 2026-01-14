# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
