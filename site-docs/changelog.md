# Changelog

For the complete changelog, see [CHANGELOG.md on GitHub](https://github.com/s-hiraoku/synapse-a2a/blob/main/CHANGELOG.md).

## Recent Highlights

### v0.7.x (Post v0.7.0)

- **Fixed**: Ghostty panes now auto-close when the agent process exits (appends `; exit` to spawned commands; `exec` is incompatible with clipboard paste injection)
- **Fixed**: Ghostty `team start` now uses split panes (`Cmd+D`) instead of spawning new windows, preserving existing panes
- **Fixed**: Ghostty commands injected via clipboard paste (`Cmd+V`) to avoid character mangling with long arguments
- **Fixed**: `team start` pre-allocates unique ports to prevent race conditions when multiple agents of the same type start simultaneously
- **Changed**: Agent spec format simplified to `profile[:name[:role[:skill_set[:port]]]]` (removed 6th `headless` field)
- **Changed**: `_build_agent_command` always adds `--no-setup --headless` for all spawned agents

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
- Tool args passthrough (`synapse spawn claude -- --worktree`)
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
