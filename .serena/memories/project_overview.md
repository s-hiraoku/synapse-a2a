# Synapse A2A Project Overview

## Purpose
Synapse A2A is a framework that wraps CLI agents (Claude Code, Codex, Gemini) with PTY and enables inter-agent communication via Google A2A Protocol. Each agent runs as an A2A server in a P2P architecture (no central server).

## Tech Stack
- **Language**: Python
- **Framework**: FastAPI (for A2A endpoints)
- **Protocol**: Google A2A Protocol (Agent-to-Agent)
- **Terminal Management**: PTY (pseudo-terminal)
- **Configuration**: YAML profiles for each agent type
- **Testing**: pytest with async support

## Core Design Principle
**A2A Protocol First**: All communication must use Message/Part + Task format per Google A2A spec.
- Standard endpoints: `/.well-known/agent.json`, `/tasks/send`, `/tasks/{id}`
- Extensions use `x-` prefix (e.g., `x-synapse-context`)
- PTY output format: `[A2A:<task_id>:<sender_id>] <message>`

## Agent Port Ranges
| Agent  | Ports     |
| ------ | --------- |
| Claude | 8100-8109 |
| Gemini | 8110-8119 |
| Codex  | 8120-8129 |

## Storage Locations
```
~/.a2a/registry/     # Running agents (auto-cleaned)
~/.a2a/external/     # External A2A agents (persistent)
~/.synapse/logs/     # Log files
```
