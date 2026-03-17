# Known Issues & Future Tasks

## Current Status

### Working
- [x] dummy <-> gemini bidirectional communication
- [x] dummy <-> dummy communication
- [x] @Agent pattern detection and routing
- [x] Multiple Agent Resolution (@type-port notation and custom naming)
- [x] submit_sequence configuration per profile

### Not Working
- [ ] Claude Code - Multiple input fields rendering bug (upstream issue)
- [ ] Codex CLI - Screen doesn't display properly

---

## Issues

### 1. Claude Code Multiple Input Fields Bug
**Priority:** High
**Type:** Upstream Bug

Claude Code CLI has a known rendering issue when running in PTY:
- Multiple input fields appear instead of one
- Causes duplicate command execution
- Related: [GitHub Issue #10413](https://github.com/anthropics/claude-code/issues/10413)
- Related: [GitHub Issue #9658](https://github.com/anthropics/claude-code/issues/9658)

**Root Cause:** Claude Code redraws entire terminal buffer on every update (4,000-6,700 scroll events/second)

**Workaround Options:**
1. Wait for upstream fix
2. Use `claude -p` (non-interactive mode) - loses persistent session
3. Use tmux send-keys approach

---

### 2. Codex CLI Screen Display Issue
**Priority:** Medium
**Type:** Unknown

Codex CLI doesn't display screen when launched via Synapse.

**Investigation Needed:**
- Check if Codex has specific PTY requirements
- Test with different TERM settings
- Check Codex logs for errors

---

### 3. TUI Submit Sequence
**Priority:** Medium
**Type:** Compatibility

Some TUI apps (Ink-based) may not respond to `\r` for submission.

**Current Status:**
- `\r` works for Gemini CLI
- Copilot CLI uses `submit_fallback_sequences` to cycle through alternative submit sequences (`\n`, `\x1b\r`) on each confirmation retry. Configured in `copilot.yaml`.

**Remaining Investigation:**
- Test with other Ink-based CLIs beyond Copilot
- Document which submit sequences work with which tools

---

## Future Enhancements

### tmux Integration
Consider using tmux send-keys as alternative to PTY:
```bash
tmux send-keys -t session "message" Enter
```
This may work better with problematic TUIs.

### MCP Server Mode
Implement Synapse as MCP server for agents that support MCP protocol.

### Response Routing
Implement `@agent` to return responses to sender's terminal.
