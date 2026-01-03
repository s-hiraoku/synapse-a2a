# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Flow (Mandatory)

1. When receiving a feature request or modification, write tests first
2. Present the tests to confirm the specification
3. Proceed to implementation only after confirmation
4. Adjust implementation until all tests pass

## Project Overview

Synapse A2A is a framework that wraps CLI agents (Claude Code, Codex, Gemini) with PTY and enables inter-agent communication via Google A2A Protocol. Each agent runs as an A2A server (P2P architecture, no central server).

## Commands

```bash
# Install
uv sync

# Run tests
pytest                                    # All tests
pytest tests/test_a2a_compat.py -v        # Specific file
pytest -k "test_identity" -v              # Pattern match

# Run agent (interactive)
synapse claude
synapse codex
synapse gemini

# List agents
synapse list                              # Show all running agents
synapse list --watch                      # Watch mode (refresh every 2s)
synapse list -w -i 1                      # Watch mode with 1s interval

# Low-level A2A tool
python3 synapse/tools/a2a.py list
python3 synapse/tools/a2a.py send --target claude --priority 1 "message"
```

## Core Design Principle

**A2A Protocol First**: All communication must use Message/Part + Task format per Google A2A spec.

- Standard endpoints: `/.well-known/agent.json`, `/tasks/send`, `/tasks/{id}`
- Extensions use `x-` prefix (e.g., `x-synapse-context`)
- PTY output format: `[A2A:<task_id>:<sender_id>] <message>`

Reference: https://developers.googleblog.com/en/a2a-a-new-era-of-agent-interoperability/

## Architecture

```
synapse/
├── cli.py           # Entry point, profile loading, interactive mode orchestration
├── controller.py    # TerminalController: PTY management, READY/PROCESSING detection
├── server.py        # FastAPI server with A2A endpoints
├── a2a_compat.py    # A2A protocol implementation (Agent Card, Task API)
├── a2a_client.py    # Client for communicating with other A2A agents
├── input_router.py  # @Agent pattern detection and routing
├── registry.py      # File-based agent discovery (~/.a2a/registry/)
├── agent_context.py # Initial instructions generation for agents
└── profiles/        # YAML configs per agent type (claude.yaml, codex.yaml, etc.)
```

## Key Flows

**Startup Sequence**:

1. Load profile YAML → 2. Register in AgentRegistry → 3. Start FastAPI server (background thread) → 4. `pty.spawn()` CLI → 5. On first IDLE, send initial instructions via `[A2A:id:synapse-system]` prefix

**@Agent Routing**:
User types `@codex review this` → InputRouter detects pattern → A2AClient.send_to_local() → POST /tasks/send-priority to target agent

**Agent Status System**:

Agents use a two-state status system:
- **READY**: Agent is idle and waiting for input (detected when `idle_regex` matches PTY output)
- **PROCESSING**: Agent is actively processing (startup, handling requests, or producing output)

Status transitions:
- Initial: `PROCESSING` (startup in progress)
- On idle detection: `PROCESSING` → `READY` (agent is ready for input)
- On output/activity: `READY` → `PROCESSING` (agent is handling work)

Dead processes are automatically cleaned up from the registry and not displayed in `synapse list`.

## Profile Configuration Notes

### Multi-Strategy Idle Detection

Synapse now supports configurable idle detection strategies per agent type in YAML profiles:

#### Detection Strategies

1. **pattern**: Regex-based detection (original behavior)
   - Checks for recurring text patterns in PTY output
   - Best for agents with consistent prompts (Gemini, Codex)

2. **timeout**: Timeout-based detection
   - Detects idle when no output received for N seconds
   - Fallback for agents without consistent prompts

3. **hybrid**: Two-phase detection (pattern then timeout)
   - Uses pattern for first idle detection
   - Falls back to timeout for subsequent idles
   - Ideal for Claude Code which has one-time initialization sequences

#### Configuration Structure

```yaml
idle_detection:
  strategy: "pattern"          # "pattern" | "timeout" | "hybrid"
  pattern: "(> |\\*)"          # Regex pattern or special name
  pattern_use: "always"        # "always" | "startup_only"
  timeout: 1.5                 # Seconds of no output to trigger idle
```

### Claude Code (Ink TUI) - Timeout Strategy

Claude Code uses Ink-based TUI with BRACKETED_PASTE_MODE sequence:

```yaml
# synapse/profiles/claude.yaml
submit_sequence: "\r"          # CR required (not LF or CRLF)

idle_detection:
  strategy: "timeout"          # Pure timeout-based detection
  timeout: 0.5                 # 500ms no output = idle
```

**Why timeout-only?**: BRACKETED_PASTE_MODE only appears once during TUI initialization, not on subsequent idle transitions. Since the pattern is unreliable for detecting ongoing idle states, we use pure timeout-based detection (0.5s) which reliably detects when Claude Code is waiting for input.

- **Submit Sequence**: `\r` (CR only) is required for v2.0.76+. CRLF does not work.
- See `docs/HANDOFF_CLAUDE_ENTER_KEY_ISSUE.md` for technical details.

### Gemini - Pattern Strategy

Gemini uses consistent text prompts:

```yaml
# synapse/profiles/gemini.yaml
idle_detection:
  strategy: "pattern"
  pattern: "(> |\\*)"          # Gemini prompt patterns
  timeout: 1.5                 # Fallback if pattern fails
```

### Codex - Pattern Strategy

Codex uses a consistent prompt character:

```yaml
# synapse/profiles/codex.yaml
idle_detection:
  strategy: "pattern"
  pattern: "›"                 # Codex prompt
  timeout: 1.5                 # Fallback if pattern fails
```

## Port Ranges

| Agent  | Ports     |
| ------ | --------- |
| Claude | 8100-8109 |
| Gemini | 8110-8119 |
| Codex  | 8120-8129 |

## Storage

```
~/.a2a/registry/     # Running agents (auto-cleaned)
~/.a2a/external/     # External A2A agents (persistent)
~/.synapse/logs/     # Log files
```
