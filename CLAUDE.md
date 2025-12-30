# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

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
├── controller.py    # TerminalController: PTY management, IDLE/BUSY detection
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

**IDLE Detection**:
`idle_regex` in profile YAML matches PTY output to detect when agent is ready for input.

## Port Ranges

| Agent  | Ports     |
|--------|-----------|
| Claude | 8100-8109 |
| Gemini | 8110-8119 |
| Codex  | 8120-8129 |

## Storage

```
~/.a2a/registry/     # Running agents (auto-cleaned)
~/.a2a/external/     # External A2A agents (persistent)
~/.synapse/logs/     # Log files
```
