# Changelog

For the complete changelog, see [CHANGELOG.md on GitHub](https://github.com/s-hiraoku/synapse-a2a/blob/main/CHANGELOG.md).

## Recent Highlights

### v0.8.1

- **Fixed**: Add missing `manager` and `documentation` skill set definitions to bundled defaults
- **Fixed**: Merge `coordinator` skill set into `manager` (adds `synapse-reinst`)
- **Docs**: Update skill set tables across all documentation to reflect 6 default sets

### v0.8.0

- **Added**: Saved Agent Manager — reusable agent configurations via `synapse agents` commands
- **Added**: Completion callback for `--no-response` task tracking (`POST /history/update`)
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
