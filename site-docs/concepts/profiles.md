# Agent Profiles

## Overview

Each CLI agent has a YAML profile that defines how Synapse interacts with it. Profiles configure the command to run, idle detection strategy, submit sequence, and environment variables.

Profiles are stored in `synapse/profiles/` and loaded automatically when you start an agent.

## Default Profiles

| Profile | Command | Port Range | Submit | Idle Strategy | Write Delay |
|---------|---------|:----------:|:------:|:-------------:|:-----------:|
| **Claude** | `claude` | 8100-8109 | `\r` (CR) | Timeout (0.5s) | 0.5s |
| **Gemini** | `gemini` | 8110-8119 | `\r` (CR) | Hybrid | 0s |
| **Codex** | `codex` | 8120-8129 | `\r` (CR) | Pattern (`›`) | 0s |
| **OpenCode** | `opencode` | 8130-8139 | `\r` (CR) | Timeout (1.0s) | 0s |
| **Copilot** | `gh copilot` | 8140-8149 | `\r` (CR) | Timeout (0.5s) | 0.5s |

## Profile Structure

```yaml
# Example: claude.yaml
command: claude                    # CLI command to run
args: []                          # Additional arguments
submit_sequence: "\r"             # How to send Enter (CR/LF)
write_delay: 0.5                  # Delay between data and submit (seconds)

idle_detection:
  strategy: "timeout"             # pattern | timeout | hybrid
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
  pattern: "›"          # Codex prompt character
  timeout: 1.5          # Fallback if pattern fails
```

**Best for**: Agents with a consistent prompt character (Codex).

### Timeout Strategy

Detects idle when no PTY output is received for a configurable duration.

```yaml
idle_detection:
  strategy: "timeout"
  pattern_use: "never"
  timeout: 0.5          # 500ms of silence = idle
```

**Best for**: Agents with TUI interfaces that don't have consistent prompts (Claude Code, OpenCode, Copilot).

### Hybrid Strategy

Uses pattern detection for the first idle (startup complete), then switches to timeout for subsequent idle states.

```yaml
idle_detection:
  strategy: "hybrid"
  pattern: "BRACKETED_PASTE_MODE"  # TUI input ready signal
  pattern_use: "startup_only"
  timeout: 3.0                     # After first idle, use timeout
```

**Best for**: Agents where a specific signal indicates TUI readiness but isn't repeated (Gemini).

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
write_delay: 0.5

idle_detection:
  strategy: "timeout"
  timeout: 0.5
```

- Uses Ink-based TUI with bracketed paste mode
- `BRACKETED_PASTE_MODE` appears once during TUI initialization (not reliable for ongoing detection)
- Pure timeout detection (0.5s) reliably detects idle state

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
  strategy: "pattern"
  pattern: "›"
  timeout: 1.5
```

- Consistent `›` prompt character after each response
- Pattern matching is reliable for this agent

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
command: gh
args: ["copilot"]
submit_sequence: "\r"
write_delay: 0.5

idle_detection:
  strategy: "timeout"
  pattern_use: "never"
  timeout: 0.5
```

- Interactive TUI without consistent prompt patterns
- Requires write delay (0.5s) for Ink TUI paste handling

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
