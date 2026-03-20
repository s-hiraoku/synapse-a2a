# Claude Code Submit Sequence Configuration - UPDATED

## Solution

**Use `\r` (CR) as `submit_sequence` for Claude Code v2.0.76.**

Claude Code v2.0.76 accepts CR (`\r`) for Enter, and CRLF (`\r\n`) does not submit input reliably in this version.

## Configuration

```yaml
# synapse/profiles/claude.yaml (v2.0.76+)
# Works with both v2.0.76 and v2.1.52+:
#   - startup_only: pattern detects first READY via ESC[?2004h
#   - timeout 0.5s: subsequent idle detection (no pattern dependency)
command: "claude"
args: []
submit_sequence: "\r"  # CR required for Ink TUI (v2.0.76+)
env:
  TERM: "xterm-256color"
idle_detection:
  strategy: "hybrid"
  pattern: "BRACKETED_PASTE_MODE"
  pattern_use: "startup_only"
  timeout: 0.5
```

## Technical Details

### READY Detection
- Uses `BRACKETED_PASTE_MODE` special pattern
- Detects when Claude Code emits `ESC[?2004h` (bracketed paste mode enabled)
- This indicates the TUI is ready to accept input

### Input Submission
- Text and submit sequence are written as **separate** `os.write()` calls with a configurable delay between them (default 0.5s, per-profile via `write_delay`)
- CR is required because CRLF does not submit in v2.0.76

### Bracketed Paste Mode (v2.1.52+)
Claude Code v2.1.52 enables bracketed paste mode (`ESC[?2004h`). When this mode is active, each `os.write()` to the PTY is wrapped in paste boundary markers (`ESC[200~...ESC[201~`). If data and CR are combined in a single write, the CR becomes a literal newline *inside* the paste boundary and is never treated as a submit action.

**Solution**: Split the write into two separate `os.write()` calls:
1. First write: the message data (wrapped in paste boundary by the terminal)
2. Delay: configurable per profile via `write_delay` (default `WRITE_PROCESSING_DELAY` = 0.5s) to let the paste boundary close
3. Second write: the submit sequence (`\r`) — arrives as a fresh keypress outside any paste context

This approach was introduced to fix the `[Pasted text #1 +27 lines]` issue where initial instructions were pasted but not submitted automatically.

### Interactive Input Path
- For Claude Code, `run_interactive()` bypasses `input_callback` and lets `pty.spawn()` handle stdin directly.
- This avoids Enter handling issues seen when stdin is intercepted and rewritten.
- You can force bypass for any agent by setting `SYNAPSE_INTERACTIVE_PASSTHROUGH=1`.

### Why CR (v2.0.76)?
- CR only (`\r`): Works correctly
- LF only (`\n`): Text appears but not submitted
- CRLF (`\r\n`): Text appears but not submitted

This is likely due to Node.js/Ink's terminal input handling which processes line endings differently than traditional Unix terminal apps.

### Per-Profile Write Delay (`write_delay`)

The delay between the data write and the submit sequence write is configurable per agent profile via the `write_delay` YAML key:

**Default** — omit the key to use `WRITE_PROCESSING_DELAY` (0.5s):

```yaml
# No write_delay key → defaults to 0.5s
submit_sequence: "\r"
```

**Copilot CLI** — uses adaptive paste echo wait instead of a fixed delay. After bracketed paste, Synapse polls PTY output until Copilot's Ink TUI re-renders (React `usePaste` state update), then sends Enter. Falls back to `write_delay` if no change is detected within 3 s. All messages use bracketed paste plus Enter; confirmation waits for prompt markers to clear:

```yaml
write_delay: 0.5          # fallback only; adaptive echo wait is used first
```

**Claude Code** — explicit default (0.5s for paste boundary to close):

```yaml
write_delay: 0.5
```

**Slower TUI frameworks** — longer delay if needed:

```yaml
write_delay: 1.0
```

When `write_delay` is `0`, `time.sleep()` is skipped entirely so the submit sequence is sent immediately after the data write. This is useful for TUI apps that process paste boundaries faster than the default 0.5s delay. **Note**: For Copilot, the adaptive paste echo wait (`_wait_for_copilot_paste_echo`) takes precedence over `write_delay` when bracketed paste is active; `write_delay` serves only as the fallback if the echo is not detected within the timeout.

### Write Strategy Evolution

| Bug | Strategy | Problem |
|-----|----------|---------|
| Bug 2 | Atomic write (data+CR in 1 call) | Split writes caused TUI apps to miss Enter |
| Bug 3 | Atomic write + retry loop | Partial writes lost data |
| Bug 4 | Split write + delay + retry loop | Fixed: bracketed paste mode previously trapped CR inside paste boundary |
| Bug 5 | Split write + per-profile delay | Fixed: Copilot CLI needed different delay than Claude Code |
| Bug 6 | Adaptive paste echo wait + nudge retry | Fixed: Copilot paste echo timing varies; poll for TUI re-render instead of fixed delay, nudge Enter before confirmation retries |

## Comparison with Other Agents

| Agent | submit_sequence | Notes |
|-------|-----------------|-------|
| Claude Code | `\r` | Ink TUI requires CR in v2.0.76 |
| Gemini | `\r` | Standard CR works |
| Codex | `\r` | Standard CR works |
| Copilot | `\r` (bracketed paste + Enter) | Paste-only path: no typed input, no Ctrl+S. Adaptive paste echo wait replaces fixed `write_delay`; nudge Enter retry before confirmation loop. `submit_confirm_timeout` / `long_submit_confirm_timeout` for bounded confirmation. |

## Related Files

- `synapse/profiles/claude.yaml` - Profile configuration
- `synapse/controller.py` - PTY write logic
- `synapse/agent_context.py` - Bootstrap message generation
