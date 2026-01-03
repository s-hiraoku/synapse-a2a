# Codebase Structure

## Main Directory Layout

```text
synapse/
├── cli.py           # Entry point, profile loading, interactive mode orchestration
├── controller.py    # TerminalController: PTY management, READY/PROCESSING detection
├── server.py        # FastAPI server with A2A endpoints
├── a2a_compat.py    # A2A protocol implementation (Agent Card, Task API)
├── a2a_client.py    # Client for communicating with other A2A agents
├── input_router.py  # @Agent pattern detection and routing
├── registry.py      # File-based agent discovery (~/.a2a/registry/)
├── agent_context.py # Initial instructions generation for agents
├── profiles/        # YAML configs per agent type (claude.yaml, codex.yaml, etc.)
└── tools/
    └── a2a.py       # Low-level A2A tool for listing and sending messages

tests/               # pytest test suite with async support
docs/                # Design documents and specifications
guides/              # User guides and reference documentation
```

<!-- CodeRabbit fix: Added language identifier to text code block (MD040) -->

## Key Concepts

### Agent Status System
Agents use a two-state status system:
- **READY**: Agent is idle and waiting for input (detected when `idle_regex` matches PTY output)
- **PROCESSING**: Agent is actively processing (startup, handling requests, or producing output)

Status transitions:
- Initial: `PROCESSING` (startup in progress)
- On idle detection: `PROCESSING` → `READY` (agent is ready for input)
- On output/activity: `READY` → `PROCESSING` (agent is handling work)

### Startup Sequence
1. Load profile YAML → 2. Register in AgentRegistry → 3. Start FastAPI server (background thread) → 4. `pty.spawn()` CLI → 5. On first IDLE, send initial instructions via `[A2A:id:synapse-system]` prefix

### @Agent Routing
User types `@codex review this` → InputRouter detects pattern → A2AClient.send_to_local() → POST /tasks/send-priority to target agent

### Profile Configuration
Each agent has specific configuration (e.g., Claude Code uses `BRACKETED_PASTE_MODE` for idle detection and requires `\r` submit sequence).
