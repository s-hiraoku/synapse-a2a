# Agent Profiles

## Overview

Each CLI agent has a YAML profile that defines how Synapse interacts with it. Profiles configure the command to run, idle detection strategy, submit sequence, and environment variables.

Profiles are stored in `synapse/profiles/` and loaded automatically when you start an agent.

## Default Profiles

| Profile | Command | Port Range | Submit | Idle Strategy | Write Delay |
|---------|---------|:----------:|:------:|:-------------:|:-----------:|
| **Claude** | `claude` | 8100-8109 | `\r` (CR) | Hybrid (0.5s) | — (default 0.5s) |
| **Gemini** | `gemini` | 8110-8119 | `\r` (CR) | Hybrid (3.0s) | — (default 0.5s) |
| **Codex** | `codex` | 8120-8129 | `\r` (CR) | Timeout (3.0s) | — (default 0.5s) |
| **OpenCode** | `opencode` | 8130-8139 | `\r` (CR) | Timeout (1.0s) | — (default 0.5s) |
| **Copilot** | `copilot` | 8140-8149 | `\r` (CR) | Timeout (0.5s) | 0.5s |

## Profile Structure

```yaml
# Example: claude.yaml
command: claude                    # CLI command to run
args: []                          # Additional arguments
submit_sequence: "\r"             # How to send Enter (CR/LF)

idle_detection:
  strategy: "hybrid"              # pattern | timeout | hybrid
  pattern: "BRACKETED_PASTE_MODE" # Regex or special name
  pattern_use: "startup_only"     # always | startup_only | never
  timeout: 0.5                    # Seconds of no output = idle

waiting_detection:
  regex: "❯ Use arrow keys"      # Detect selection UI
  require_idle: true
  idle_timeout: 0.5

env:                              # Extra environment variables
  SOME_VAR: "value"
```

## Idle Detection Strategies

### Pattern Strategy

Matches a regex pattern in PTY output to detect idle state.

```yaml
idle_detection:
  strategy: "pattern"
  pattern: "›"          # Example: prompt character
  timeout: 1.5          # Fallback if pattern fails
```

**Best for**: Agents with a consistent prompt character.

### Timeout Strategy

Detects idle when no PTY output is received for a configurable duration.

```yaml
idle_detection:
  strategy: "timeout"
  pattern_use: "never"
  timeout: 0.5          # 500ms of silence = idle
```

**Best for**: Agents with TUI interfaces that don't have consistent prompts (Codex, OpenCode, Copilot).

### Hybrid Strategy

Uses pattern detection for the first idle (startup complete), then switches to timeout for subsequent idle states.

```yaml
idle_detection:
  strategy: "hybrid"
  pattern: "BRACKETED_PASTE_MODE"  # TUI input ready signal
  pattern_use: "startup_only"
  timeout: 3.0                     # After first idle, use timeout
```

**Best for**: Agents where a specific signal indicates TUI readiness but isn't repeated (Claude Code, Gemini).

## Submit Sequence and Write Delay

### Submit Sequence

The character sent after a message to "press Enter":

- `\r` (CR) — Required for Ink-based TUI apps (Claude Code, Copilot)
- `\n` (LF) — For simple command-line interfaces

### Write Delay

Time between writing the message data and sending the submit sequence:

```yaml
write_delay: 0.5  # Wait 500ms before sending CR
```

!!! info "Why Write Delay?"
    Ink TUI apps use bracketed paste mode. If CR is sent too quickly after the data, it gets trapped inside the paste boundary and ignored. The delay gives the TUI time to process the pasted text before CR is sent as a submit action.

### Split Write Strategy

Synapse writes data and submit sequence as **separate** `os.write()` calls:

```
os.write(fd, message_data)    # Step 1: Write message
time.sleep(write_delay)        # Step 2: Wait
os.write(fd, submit_sequence)  # Step 3: Send Enter
```

This prevents the submit sequence from being consumed as part of the paste content.

## Per-Agent Details

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

- Uses Ink-based TUI with bracketed paste mode
- `BRACKETED_PASTE_MODE` (ESC[?2004h) indicates idle at startup
- Hybrid approach: pattern for fast startup detection, 0.5s timeout for subsequent idles
- No `write_delay` in profile — uses the global default (`WRITE_PROCESSING_DELAY = 0.5s`)

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

- `BRACKETED_PASTE_MODE` indicates TUI input area is ready
- Pattern used only for first READY detection
- Subsequent idle states detected via 3.0s timeout

### Codex CLI

```yaml
command: codex
submit_sequence: "\r"

idle_detection:
  strategy: "timeout"
  timeout: 3.0
```

- Timeout-based detection (3.0s) is more reliable than pattern matching
- Pattern matching is unreliable because prompt patterns may appear in conversation history
- Uses `input_ready_pattern: "›"` only for initial instruction delivery

### OpenCode

```yaml
command: opencode
submit_sequence: "\r"

idle_detection:
  strategy: "timeout"
  pattern_use: "never"
  timeout: 1.0
```

- Uses Bubble Tea TUI (no consistent prompt patterns)
- Timeout detection (1.0s) works reliably

### GitHub Copilot CLI

```yaml
command: copilot
args: []
submit_sequence: "\r"
write_delay: 0.5
bracketed_paste: true
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

- Interactive TUI without consistent prompt patterns
- Requires explicit `write_delay: 0.5` — Ink TUI needs time to finish rendering before CR
- `bracketed_paste: true` wraps input in paste escape sequences so Ink's `usePaste` hook receives the full text atomically
- Copilot sends stay on paste plus Enter; the bundled profile does not rely on typed-input tuning or `Ctrl+S` fallbacks
- Submit confirmation watches the prompt itself, not only status changes; placeholders such as `[Paste #1 - 12 lines]`, `[Saved pasted content to workspace ...]`, or file-reference banners keep the send pending until they clear, even when the same placeholder label reappears on a later send
- `long_submit_confirm_timeout: 3.0` and `long_submit_confirm_retries: 5` give multiline/file-reference sends a larger confirmation budget without changing the submit key path

## Custom Profiles

You can create custom profiles by adding YAML files to your project's `.synapse/profiles/` directory or `~/.synapse/profiles/`.

```yaml
# .synapse/profiles/my-agent.yaml
command: my-custom-agent
args: ["--verbose"]
submit_sequence: "\n"
write_delay: 0

idle_detection:
  strategy: "pattern"
  pattern: "\\$ "        # Shell prompt
  timeout: 2.0

env:
  MY_AGENT_KEY: "value"
```

Then start it with:

```bash
synapse start my-agent
```
