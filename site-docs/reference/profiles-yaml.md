# Profile YAML Schema

## Complete Schema

```yaml
# Agent profile configuration
command: string                    # CLI command to execute (required)
args: [string]                     # Additional CLI arguments (optional)
submit_sequence: "\r" | "\n"       # Submit key: CR or LF (default: "\r")
write_delay: float                 # Delay between data and submit (seconds, default: WRITE_PROCESSING_DELAY=0.5)
submit_retry_delay: float          # Send submit_seq twice with this gap (seconds, default: 0 = disabled)
bracketed_paste: boolean           # Wrap PTY data in bracketed paste sequences (default: false)
typing_char_delay: float           # Copilot-only: delay between typed chars for short messages
typing_max_chars: integer          # Copilot-only: max length that uses typed input instead of paste
long_submit_settle_delay: float    # Copilot-only: multiline/file-reference delay before first submit
long_submit_retry_delay: float     # Copilot-only: multiline/file-reference delay before retry submit
submit_confirm_timeout: float      # Optional: poll window for post-submit confirmation (seconds)
submit_confirm_poll_interval: float # Optional: poll interval for submit confirmation (seconds)
submit_confirm_retries: integer    # Optional: extra submit attempts after confirmation failures
submit_fallback_sequences: [string] # Optional: alternative submit sequences tried on each confirmation retry

idle_detection:
  strategy: "pattern" | "timeout" | "hybrid"  # Detection strategy (required)
  pattern: string                  # Regex pattern or special name
  pattern_use: "always" | "startup_only" | "never"  # When to use pattern
  timeout: float                   # Seconds of no output = idle

waiting_detection:                 # Optional: detect selection UI
  regex: string                    # Pattern for selection UI
  require_idle: boolean            # Require idle state first
  idle_timeout: float              # Idle timeout before checking

env:                               # Additional environment variables
  KEY: "value"
```

## Field Reference

### command

The CLI command to execute.

```yaml
command: claude          # Claude Code
command: gemini          # Gemini CLI
command: copilot         # GitHub Copilot CLI
command: opencode        # OpenCode
command: codex           # Codex CLI
```

### args

Additional arguments passed to the command.

```yaml
args: []                 # Most agents use no extra args
args: ["--verbose"]      # Custom flags
```

### submit_sequence

The character sent to submit input (press Enter).

| Value | Name | Use Case |
|-------|------|----------|
| `"\r"` | CR (Carriage Return) | Ink TUI apps (Claude, Copilot) |
| `"\n"` | LF (Line Feed) | Simple CLI interfaces |

Copilot may override the configured submit sequence at runtime and send `Ctrl+S` when the footer explicitly advertises `ctrl+s run command`.

### write_delay

Delay in seconds between writing message data and sending the submit sequence.

```yaml
write_delay: 0.5    # Copilot (explicit in profile — Ink TUI needs time)
# Other profiles omit write_delay; the default (0.5s) is used
```

### submit_retry_delay

Send the submit sequence a second time after a short gap. This is a safety net for TUI frameworks where the first submit may fire before React state updates complete.

```yaml
submit_retry_delay: 0.15  # Copilot: retry after 150ms (one React render cycle)
# Default: 0 (disabled — submit_seq sent only once)
```

This retry is skipped when Copilot uses typed input for short single-line messages, because the message is already delivered character-by-character.

For multiline or file-reference sends, Copilot can use separate timing via `long_submit_settle_delay` and `long_submit_retry_delay` so the Ink UI has more time to reconcile a large paste before the initial or retry submit fires.

### bracketed_paste

Wrap PTY data writes in bracketed paste escape sequences (`ESC[200~ ... ESC[201~`). Required for agents whose TUI uses a paste hook (e.g., Ink's `usePaste`) to receive multi-character input atomically instead of character-by-character via `useInput`.

```yaml
bracketed_paste: true   # Copilot CLI (Ink usePaste hook)
# Default: false
```

### typing_char_delay / typing_max_chars

Copilot-only typing mode for short single-line messages. When enabled, Synapse writes the message one character at a time instead of using bracketed paste, which better matches how a human user interacts with Ink-based TUIs. Inside tmux, Synapse enforces a slower minimum character delay so tmux does not batch the writes into a burst.

```yaml
typing_char_delay: 0.01   # Delay between typed characters
typing_max_chars: 400     # Use typed input up to this length
# Default: not set (typed input disabled)
```

### long_submit_settle_delay / long_submit_retry_delay

Additional Copilot-only timing controls for multiline or file-reference sends:

```yaml
long_submit_settle_delay: 0.8   # Wait after paste, before the first submit
long_submit_retry_delay: 0.3    # Wait before the retry submit stroke
```

Use these when large pasted messages are visible in the prompt but the first Enter/Ctrl+S fires too early.

### submit_confirm_timeout / submit_confirm_poll_interval / submit_confirm_retries

Bounded post-submit confirmation for TUIs where text may land in the input box without executing. Synapse polls recent context after the normal submit sequence and, if the text still appears pending, sends extra submit keys up to the configured retry limit. For Copilot, a repeated WAITING frame is only accepted if the visible prompt advances or clears; WAITING-to-WAITING by itself stays pending.

```yaml
submit_confirm_timeout: 1.5         # Per confirmation round
submit_confirm_poll_interval: 0.05  # Poll every 50ms
submit_confirm_retries: 3           # Extra submit attempts after initial retry
```

### submit_fallback_sequences

Alternative submit sequences tried in order on each confirmation retry when the primary `submit_sequence` fails to execute input. Each entry is sent as a raw byte string (C-style escapes are expanded). This is useful for TUI frameworks where different versions may respond to different key sequences.

```yaml
submit_fallback_sequences:
  - "\n"        # LF — some Ink versions accept this instead of CR
  - "\x1b\r"   # ESC + CR — alternative for certain terminal modes
# Default: not set (only submit_sequence is used)
```

### idle_detection.strategy

| Strategy | Description |
|----------|-------------|
| `pattern` | Match regex in PTY output |
| `timeout` | No output for N seconds |
| `hybrid` | Pattern first, then timeout |

### idle_detection.pattern

Regex pattern or special name:

| Value | Meaning |
|-------|---------|
| `"BRACKETED_PASTE_MODE"` | `ESC[?2004h` sequence (TUI ready, used by Claude/Gemini) |
| Custom regex | Any valid regex |

### idle_detection.pattern_use

| Value | When Pattern Is Used |
|-------|---------------------|
| `always` | Every idle detection cycle |
| `startup_only` | Only for the first idle |
| `never` | Pattern disabled |

### idle_detection.timeout

Seconds of no PTY output before considering the agent idle.

## Default Profiles

### Claude Code

```yaml
command: claude
submit_sequence: "\r"
idle_detection:
  strategy: "hybrid"
  pattern: "BRACKETED_PASTE_MODE"
  pattern_use: "startup_only"
  timeout: 0.5
```

### Gemini CLI

```yaml
command: gemini
submit_sequence: "\r"
idle_detection:
  strategy: "hybrid"
  pattern: "BRACKETED_PASTE_MODE"
  pattern_use: "startup_only"
  timeout: 3.0
```

### Codex CLI

```yaml
command: codex
submit_sequence: "\r"
idle_detection:
  strategy: "timeout"
  timeout: 3.0
```

### OpenCode

```yaml
command: opencode
submit_sequence: "\r"
idle_detection:
  strategy: "timeout"
  pattern_use: "never"
  timeout: 1.0
```

### GitHub Copilot CLI

```yaml
command: copilot
args: []
submit_sequence: "\r"
write_delay: 0.5
submit_retry_delay: 0.15
bracketed_paste: true
submit_confirm_timeout: 1.5
submit_confirm_poll_interval: 0.05
submit_confirm_retries: 3
submit_fallback_sequences:
  - "\n"
  - "\x1b\r"
idle_detection:
  strategy: "timeout"
  pattern_use: "never"
  timeout: 0.5
```

### Dummy (Testing)

```yaml
command: bash
submit_sequence: "\n"
idle_detection:
  strategy: "pattern"
  pattern: "\\$"
  timeout: 1.0
```

## Custom Profile Example

Create `.synapse/profiles/my-agent.yaml`:

```yaml
command: my-custom-agent
args: ["--interactive", "--color=auto"]
submit_sequence: "\n"
write_delay: 0

idle_detection:
  strategy: "pattern"
  pattern: "\\$ "
  timeout: 2.0

waiting_detection:
  regex: "Select an option"
  require_idle: true
  idle_timeout: 0.5

env:
  MY_API_KEY: "value"
  DEBUG: "true"
```

Start with:

```bash
synapse start my-agent
```
