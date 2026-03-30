# Channel Protocol Integration & Agent Summary

> Design document for issue #472: Features inspired by [claude-peers-mcp](https://github.com/louislva/claude-peers-mcp).

## Overview

This document covers two features:

1. **Agent Summary** — persistent work description visible in `synapse list` and Canvas
2. **Channel Protocol** — Claude Code's `claude/channel` MCP capability for message delivery

---

## 1. Agent Summary

### What It Is

Each agent can have a **summary** — a persistent description of what it's working on (up to 120 characters). Unlike `current_task_preview` (30 chars, cleared automatically when a task completes), summary persists until explicitly changed or cleared.

### User Guide

#### Setting a summary

```bash
# Manual summary
synapse set-summary claude "Working on auth refactor for issue #123"
synapse set-summary my-claude "Reviewing PR #456"

# Auto-generate from git info (branch + recent files)
synapse set-summary claude --auto
# Output: "branch: feature/auth | recent: auth.py, middleware.py, tests.py"

# Clear
synapse set-summary claude --clear
```

#### Target resolution

Same as other commands — custom name, full ID, type-port, or type:

```bash
synapse set-summary my-claude "..."         # Custom name
synapse set-summary synapse-claude-8100 "..." # Full ID
synapse set-summary claude-8100 "..."       # Type-port
synapse set-summary claude "..."            # Type (single instance only)
```

#### Viewing summaries

**CLI** — add SUMMARY to your column config:

```bash
# One-time
synapse list --columns ID,NAME,STATUS,SUMMARY

# Persistent (in synapse settings)
# Set list.columns to include SUMMARY
```

**Canvas** — summary appears in:
- Dashboard (`#/dashboard`) → Agents widget (expanded view)
- System (`#/system`) → agent table
- Admin (`#/admin`) → agent control panel

**JSON output**:

```bash
synapse list --json
# Each agent object includes "summary": "..." or "summary": null
```

**MCP** — `list_agents` tool returns `summary` field.

**Agent Card** — available in `extensions.synapse.summary` at `/.well-known/agent.json`.

### Architecture

```
synapse set-summary <target> "text"
  → registry.update_summary(agent_id, "text")
    → atomic write to ~/.a2a/registry/{agent_id}.json
      → { "summary": "text", "summary_updated_at": 1710000000.0 }

synapse list / Canvas / MCP list_agents
  → reads "summary" from registry JSON
```

Summary is stored alongside existing registry fields and follows the same atomic update pattern.

---

## 2. Channel Protocol Integration

### What It Is

Claude Code v2.1.80+ supports a **channel protocol**: MCP servers that can push events directly into a Claude Code session via `notifications/claude/channel`. This is an alternative to PTY stdin injection for message delivery.

Reference: [Claude Code Channels Reference](https://code.claude.com/docs/en/channels-reference)

### Why Use Channels

| | PTY Injection (Current) | Channel Protocol (New) |
|---|---|---|
| **Delivery** | `os.write(master_fd, data)` — text into stdin | MCP notification — structured data into context |
| **Format** | `A2A: [From: sender] message` plain text | `<channel source="synapse" task_id="...">message</channel>` |
| **Completion** | Implicit — PTY output pattern monitoring | Explicit — Claude calls `synapse_reply` tool |
| **Metadata** | Encoded in text prefix | Structured as XML attributes |
| **Reliability** | Depends on TUI paste handling | Direct MCP protocol |

### User Guide

#### Enabling channel mode

```bash
# Start Claude with channel support
synapse start claude --channel

# Channel is opt-in, off by default
# Without --channel, behavior is identical to before
```

#### Requirements

- **Claude Code v2.1.80+** (channel protocol support)
- **claude.ai login** (API key authentication not supported)
- **Research preview**: requires `--dangerously-load-development-channels` flag (Synapse adds this automatically when `--channel` is used)

#### What happens internally

1. Synapse creates a channel MCP server config in `.mcp.json`
2. Claude Code spawns the channel server as a subprocess
3. Messages from `synapse send` are delivered via channel instead of PTY
4. If channel delivery fails, falls back to PTY automatically
5. Non-Claude agents (Gemini, Codex, Copilot) are unaffected — always use PTY

#### For message senders

No changes needed. `synapse send` works exactly the same:

```bash
synapse send claude "Review this PR" --wait
synapse send claude "FYI: tests passed" --silent
```

The transport selection (channel vs PTY) is handled server-side and is transparent to the sender.

### Architecture

#### Current Pipeline (PTY — unchanged)

```
synapse send → A2AClient (UDS/TCP) → /tasks/send-priority
  → _send_task_message()
    → _prepare_pty_message() → format_a2a_message()
      → controller.write() → PTY stdin
        → PTY output monitoring → status change callback → Task completion
```

#### Channel Pipeline (Claude + `--channel` only)

```
synapse send → A2AClient (UDS/TCP) → /tasks/send-priority
  → _send_task_message()
    ├─ channel.is_available()?
    │   → channel_transport.deliver()
    │     → file queue (~/.synapse/channels/{agent_id}/pending/)
    │       → Channel MCP Server watches directory
    │         → notifications/claude/channel → Claude receives as <channel> tag
    │           → Claude calls synapse_reply tool with task_id + response
    │             → Channel Server POSTs to /tasks/send with in_reply_to
    │               → Existing reply path → Task completion
    │
    └─ Channel unavailable/failed
        → controller.write() (PTY fallback — always available)
```

#### Transport Abstraction

```
synapse/transport.py

  MessageTransport (Protocol)
    ├─ PTYTransport      — wraps controller.write() (existing behavior)
    └─ ChannelTransport  — writes to file queue for Channel MCP Server
```

The divergence point is `a2a_compat.py` L1453-1471, where `_prepare_pty_message()` and `controller.write()` are called.

#### Channel MCP Server

```
synapse/mcp/channel.py

  - Declares claude/channel capability
  - Watches file queue for pending messages
  - Sends notifications/claude/channel events to Claude
  - Exposes synapse_reply tool for Claude to signal completion
  - Calls back to agent's /tasks/send endpoint for reply routing
```

### Task Lifecycle with Channels

| Phase | PTY (unchanged) | Channel |
|-------|----------------|---------|
| Create | `task_store.create()` → "working" | Same |
| Deliver | `controller.write()` → PTY stdin | `channel_transport.deliver()` → MCP notification |
| Complete | PTY output monitoring → callback | Claude calls `synapse_reply` → `/tasks/send` + `in_reply_to` |
| Reply | `_send_response_to_sender()` | Same (merges into existing `in_reply_to` path) |

### Response Modes

| Mode | Channel Behavior |
|------|-----------------|
| `--wait` | Same. Sender polls `sender_task_id`. Channel reply arrives via existing path. |
| `--notify` | Same. `synapse_reply` → task finalization → `_send_response_to_sender()` |
| `--silent` | Falls back to PTY status monitoring. Timeout-based auto-complete. |

### Fallback Design

PTY is always alive (Claude Code runs under PTY). Fallback is immediate and transparent:

```python
if agent_type == "claude" and channel_transport.is_available():
    ok = channel_transport.deliver(...)
    if ok:
        return  # Channel delivery succeeded
    log.warning("Channel delivery failed, falling back to PTY")

# PTY delivery (default / fallback / non-Claude)
controller.write(prefixed_content, submit_seq=submit_seq)
```

Fallback triggers when:
- Channel MCP server crashed or didn't start
- File queue write failed
- Claude Code didn't load the channel (version too old, not logged in)

### Constraints

- **claude.ai login required** — API key auth not supported by channel protocol
- **Claude Code v2.1.80+** — older versions don't support channels
- **Research preview** — custom channels need `--dangerously-load-development-channels`
- **Claude only** — Gemini, Codex, Copilot continue using PTY (no change)

### Implementation Phases

1. **Phase A**: Transport abstraction (`transport.py` + `PTYTransport`). Pure refactoring, no behavior change. Gate: all existing tests pass.
2. **Phase B**: `ChannelTransport` + `mcp/channel.py` behind `--channel` flag. Gate: existing tests pass + channel-specific tests.
3. **Phase C** (future): Auto-detect Claude Code version and channel capability. Promote from opt-in to auto-enabled.

---

## Related Files

| File | Role |
|------|------|
| `synapse/registry.py` | `update_summary()` method |
| `synapse/commands/renderers/rich_renderer.py` | SUMMARY column definition |
| `synapse/commands/list.py` | Data pipeline (summary in agent data + JSON) |
| `synapse/cli.py` | `set-summary` command, `--channel` flag |
| `synapse/a2a_compat.py` | Transport divergence point (L1453), Agent Card extension |
| `synapse/mcp/server.py` | MCP `list_agents` includes summary |
| `synapse/canvas/server.py` | `/api/system` includes summary |
| `synapse/canvas/static/canvas-system.js` | `buildAgentRow()` renders summary |
| `synapse/transport.py` (NEW) | Transport abstraction |
| `synapse/mcp/channel.py` (NEW) | Channel MCP server |
