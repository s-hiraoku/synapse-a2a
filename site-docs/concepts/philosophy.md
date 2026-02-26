# Design Philosophy

## Mission

> **Enable agents to collaborate on tasks without changing their behavior.**

Synapse A2A exists to solve a practical problem: CLI AI agents are powerful individually, but they can't talk to each other. Rather than waiting for each tool to implement A2A natively, Synapse wraps them transparently and adds communication capabilities.

## Core Principles

### 1. Non-Invasive Design

The most important principle. Synapse must never modify or interfere with the agent's native behavior.

- **Transparent PTY wrapping**: Agents run unmodified inside a pseudo-terminal
- **Profile-based configuration**: Per-agent YAML configs handle differences without code changes
- **Argument pass-through**: All CLI flags are forwarded to the underlying tool
- **No side-channel injection**: Messages arrive through the same input channel the user would use

!!! example "In Practice"
    When you run `synapse claude`, Claude Code launches exactly as if you ran `claude` directly. The only difference is that an A2A server runs alongside it, and Synapse routes inter-agent messages through the PTY.

### 2. A2A Protocol First

All inter-agent communication must follow the Google A2A specification.

- Messages use the `Message/Part + Task` format
- Standard endpoints: `/.well-known/agent.json`, `/tasks/send`, `/tasks/{id}`
- Extensions use the `x-` prefix (e.g., `x-synapse-context`)
- Protocol compliance is prioritized over convenience

### 3. Peer-to-Peer Architecture

No central server. Every agent is an equal peer.

```
    Claude ←──A2A──→ Gemini
      ↑                 ↑
      │     A2A         │
      └──────┼──────────┘
             ↓
           Codex
```

- Each agent runs its own A2A server
- File-based registry for discovery (`~/.a2a/registry/`)
- Any agent can send to any other agent
- No single point of failure

### 4. Agent Ignorance Principle

Agents don't need to know they're part of a multi-agent system.

**What Synapse handles (invisible to agents):**

- Message routing and transport
- Reply stack management
- Agent discovery and registration
- Task lifecycle tracking
- File safety coordination

**What agents handle (their normal behavior):**

- Understanding message content
- Executing tasks
- Producing output
- Using `synapse reply` to respond

### 5. Minimal Visibility

Synapse should be as invisible as possible.

- Bootstrap messages are minimal (not lengthy instructions)
- Agent Card provides A2A information (agents can fetch it on demand)
- Logs go to separate files (`~/.synapse/logs/`)
- The user's terminal experience remains clean

### 6. Experimental Validation

Synapse is both a tool and an experiment.

- Test whether the A2A protocol works for real CLI agent coordination
- Discover practical issues through implementation (not theory)
- Feed back findings to the broader A2A ecosystem
- Validate multi-agent patterns that work in practice

## Design Decision Framework

When making implementation choices, follow this priority:

| Aspect | Preferred Approach |
|--------|-------------------|
| **Protocol** | A2A-compliant over custom |
| **Implementation** | Reuse standards over inventing new |
| **UX** | Transparent and minimal over verbose |
| **Agent burden** | Synapse absorbs complexity |
| **Validation** | Working code over theory |

## What Synapse Is NOT

- **Not a framework**: Agents don't need to be built with Synapse in mind
- **Not a central server**: No coordinator, orchestrator, or message broker
- **Not agent-specific**: Works with any CLI tool that can be PTY-wrapped
- **Not invasive**: Never modifies the agent's code, config, or behavior

## Strategic Position

### Now (2025-2026)

- Local CLI agent wrapping and coordination
- A2A protocol learning and validation
- Multi-agent workflow experimentation

### Future (Post CLI-Native A2A)

When CLI tools add native A2A support, Synapse can evolve into:

- A **gateway** between local CLI and external A2A agents
- An **auth/routing hub** for agent communication
- A **privacy boundary** enforcer
- A **legacy adapter** for non-A2A systems
