# Profile YAML Schema

## Complete Schema

```yaml
# Agent profile configuration
command: string                    # CLI command to execute (required)
args: [string]                     # Additional CLI arguments (optional)
submit_sequence: "\r" | "\n"       # Submit key: CR or LF (default: "\r")
write_delay: float                 # Delay between data and submit (seconds, default: 0)

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
command: gh              # GitHub Copilot (with args: ["copilot"])
command: opencode        # OpenCode
command: codex           # Codex CLI
```

### args

Additional arguments passed to the command.

```yaml
args: ["copilot"]        # For Copilot: gh copilot
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
write_delay: 0.5    # Claude, Copilot (Ink TUI needs time)
write_delay: 0      # Gemini, Codex, OpenCode (no delay needed)
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
| `"BRACKETED_PASTE_MODE"` | `ESC[?2004h` sequence (TUI ready) |
| `"›"` | Codex prompt character |
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
write_delay: 0.5
idle_detection:
  strategy: "timeout"
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
  strategy: "pattern"
  pattern: "›"
  timeout: 1.5
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
command: gh
args: ["copilot"]
submit_sequence: "\r"
write_delay: 0.5
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
