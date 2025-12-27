# Known Issues & Future Tasks

## Current Status

### Working
- [x] dummy <-> gemini bidirectional communication
- [x] dummy <-> dummy communication
- [x] @Agent pattern detection and routing
- [x] submit_sequence configuration per profile

### Not Working
- [ ] Claude Code - Multiple input fields rendering bug (upstream issue)
- [ ] Codex CLI - Screen doesn't display properly
- [ ] Same agent type multiple instances (e.g., @gemini:8102)

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

### 3. Same Agent Type Multiple Instances
**Priority:** Low
**Type:** Feature Request

Currently cannot distinguish between multiple instances of same agent type:
- Two `gemini` instances on different ports both register as "gemini"
- `@gemini` command cannot specify which instance

**Proposed Solutions:**
1. Support `@gemini:8102` format (with port)
2. Support `@gemini-1`, `@gemini-2` aliases
3. Allow custom agent names in profile

---

### 4. TUI Submit Sequence
**Priority:** Medium
**Type:** Compatibility

Some TUI apps (Ink-based) may not respond to `\r` for submission.

**Current Status:**
- `\r` works for Gemini CLI
- Not tested with all TUI frameworks

**Investigation Needed:**
- Test with other Ink-based CLIs
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
Implement `@agent --response` to return responses to sender's terminal.
