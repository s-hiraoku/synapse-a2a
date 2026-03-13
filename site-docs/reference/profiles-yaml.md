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
submit_retry_delay: 0.15  # Copilot: retry after 150ms (one React render cycle)
# Default: 0 (disabled — submit_seq sent only once)
```

### bracketed_paste

Wrap PTY data writes in bracketed paste escape sequences (`ESC[200~ ... ESC[201~`). Required for agents whose TUI uses a paste hook (e.g., Ink's `usePaste`) to receive multi-character input atomically instead of character-by-character via `useInput`.

```yaml
bracketed_paste: true   # Copilot CLI (Ink usePaste hook)
# Default: false
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
