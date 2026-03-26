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
typing_char_delay: float           # Optional: delay between typed chars for short messages
typing_max_chars: integer          # Optional: max length that uses typed input instead of paste
submit_confirm_timeout: float      # Optional: poll window for post-submit confirmation (seconds)
submit_confirm_poll_interval: float # Optional: poll interval for submit confirmation (seconds)
submit_confirm_retries: integer    # Optional: extra submit attempts after confirmation failures
long_submit_confirm_timeout: float # Optional: confirmation timeout override for long messages
long_submit_confirm_retries: integer # Optional: confirmation retries override for long messages

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

### write_delay

Delay in seconds between writing message data and sending the submit sequence.

```yaml
write_delay: 0.5    # Copilot (explicit in profile — Ink TUI needs time)
# Other profiles omit write_delay; the default (0.5s) is used
```

### submit_retry_delay

Send the submit sequence a second time after a short gap. This is a safety net for TUI frameworks where the first submit may fire before React state updates complete.

```yaml
submit_retry_delay: 0.15  # Generic example: retry after 150ms
# Default: 0 (disabled — submit_seq sent only once)
```

### bracketed_paste

Wrap PTY data writes in bracketed paste escape sequences (`ESC[200~ ... ESC[201~`). Useful for agents whose TUI uses a paste hook to receive multi-character input atomically instead of character-by-character via `useInput`. Not all Ink TUIs enable bracketed paste mode; check whether the agent emits `ESC[?2004h` before enabling this.

```yaml
bracketed_paste: true   # Only if the agent enables bracketed paste mode
# Default: false
# Note: Copilot CLI does not enable bracketed paste mode, so this is false for Copilot.
```

### typing_char_delay / typing_max_chars

Optional typed-input mode for short single-line messages. When enabled, Synapse writes the message one character at a time instead of using bracketed paste. This can help profiles whose TUI reacts poorly to pasted short prompts, but it is not used by the bundled Copilot profile.

```yaml
typing_char_delay: 0.01   # Delay between typed characters
typing_max_chars: 400     # Use typed input up to this length
# Default: not set (typed input disabled)
```

### submit_confirm_timeout / submit_confirm_poll_interval / submit_confirm_retries

Bounded post-submit confirmation for TUIs where text may land in the input box without executing. Synapse polls recent context after the normal submit sequence and, if the text still appears pending, sends extra submit keys up to the configured retry limit. For Copilot, WAITING or PROCESSING alone is not enough: confirmation stays pending while the prompt still shows the original text, file-reference markers, or paste placeholders such as `[Paste #1 - 12 lines]` and `[Saved pasted content to workspace ...]`, including cases where the same placeholder label is shown again on a subsequent send.

```yaml
submit_confirm_timeout: 1.5         # Per confirmation round
submit_confirm_poll_interval: 0.05  # Poll every 50ms
submit_confirm_retries: 3           # Extra submit attempts after initial retry
```

### long_submit_confirm_timeout / long_submit_confirm_retries

Override the confirmation timeout and retry count for long multiline or file-reference messages. These messages take longer for TUI frameworks to reconcile, so a larger budget prevents premature confirmation failure.

```yaml
long_submit_confirm_timeout: 3.0   # Copilot: longer window for multiline pastes
long_submit_confirm_retries: 5     # More retries for long messages
# Default: not set (uses submit_confirm_timeout / submit_confirm_retries)
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
bracketed_paste: false
submit_confirm_timeout: 1.5
submit_confirm_poll_interval: 0.05
submit_confirm_retries: 3
long_submit_confirm_timeout: 3.0
long_submit_confirm_retries: 5
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
