# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[0.2.2]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/s-hiraoku/synapse-a2a/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/s-hiraoku/synapse-a2a/releases/tag/v0.1.0
