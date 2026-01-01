# Claude Code Submit Sequence Configuration - UPDATED

## Solution

**Use `\r` (CR) as `submit_sequence` for Claude Code v2.0.76.**

Claude Code v2.0.76 accepts CR (`\r`) for Enter, and CRLF (`\r\n`) does not submit input reliably in this version.

## Configuration

```yaml
# synapse/profiles/claude.yaml
command: "claude"
args: []
idle_regex: "BRACKETED_PASTE_MODE"
submit_sequence: "\r"  # CR required for Ink TUI (v2.0.76)
env:
  TERM: "xterm-256color"
```

## Technical Details

### IDLE Detection
- Uses `BRACKETED_PASTE_MODE` special pattern
- Detects when Claude Code emits `ESC[?2004h` (bracketed paste mode enabled)
- This indicates the TUI is ready to accept input

### Input Submission
- Text is written to PTY first
- 0.5 second delay allows TUI to process input
- Submit sequence (`\r`) is sent separately
- CR is required because CRLF does not submit in v2.0.76

### Interactive Input Path
- For Claude Code, `run_interactive()` bypasses `input_callback` and lets `pty.spawn()` handle stdin directly.
- This avoids Enter handling issues seen when stdin is intercepted and rewritten.
- You can force bypass for any agent by setting `SYNAPSE_INTERACTIVE_PASSTHROUGH=1`.

### Why CR (v2.0.76)?
- CR only (`\r`): Works correctly
- LF only (`\n`): Text appears but not submitted
- CRLF (`\r\n`): Text appears but not submitted

This is likely due to Node.js/Ink's terminal input handling which processes line endings differently than traditional Unix terminal apps.

## Comparison with Other Agents

| Agent | submit_sequence | Notes |
|-------|-----------------|-------|
| Claude Code | `\r` | Ink TUI requires CR in v2.0.76 |
| Gemini | `\r` | Standard CR works |
| Codex | `\r` | Standard CR works |

## Related Files

- `synapse/profiles/claude.yaml` - Profile configuration
- `synapse/controller.py` - PTY write logic
- `synapse/agent_context.py` - Bootstrap message generation
