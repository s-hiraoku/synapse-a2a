# Investigation: reply_stack empty for AI-spawned agents

**Related**: Issue #237 / file-based reply target fallback implementation

## Summary

When Agent A (AI) spawns Agent B via `synapse spawn` and then sends a message
with `--response`, Agent B's in-memory `reply_stack` may be empty when
`synapse reply` queries it, causing "No reply target" errors.

Normal (manually-started) agents do not exhibit this issue.

## Scope

| Scenario | Expected | Actual | Status |
|----------|----------|--------|--------|
| AI-initiated spawn → send → reply | reply_stack populated | reply_stack empty | **Bug** |
| User-initiated spawn → send → reply | reply_stack empty | reply_stack empty | **By design** |

User-initiated spawn (from terminal, not inside an agent PTY) cannot populate
`sender_info` because the terminal process is not a descendant of any
registered agent. This is acceptable behavior.

## Expected flow (AI-initiated spawn)

```
Agent A (claude, PTY) AI runs:
  1. synapse spawn gemini          → Agent B starts in new tmux pane
  2. synapse send gemini "..." --response  → sends to Agent B

Inside synapse send (step 2):
  _find_sender_by_pid()
    → current PID is descendant of Agent A's registered PID
    → returns {sender_id, sender_endpoint, sender_uds_path}
  send_to_local()
    → metadata.sender = sender_info
    → POST /tasks/send-priority on Agent B's server

Agent B's server (_send_task_message):
  metadata.response_expected = True
  _extract_sender_info(metadata) → SenderInfo with sender_id + endpoint
  has_reply_target() → True
  reply_stack.set(sender_id, ...) → ★ should store here

Agent B AI runs:
  synapse reply "result"
    → build_sender_info() → finds Agent B's own endpoint
    → GET /reply-stack/get → ★ should find the entry
```

## Candidate root causes

### 1. Silent exception in `_find_sender_by_pid()` (HIGH probability)

**File**: `synapse/tools/a2a.py:129-142`

```python
def _find_sender_by_pid() -> dict[str, str]:
    try:
        # ... PID detection logic ...
    except Exception:
        pass          # ← ALL exceptions swallowed silently
    return {}         # ← returns empty dict → sender_info is falsy
```

If ANY exception occurs during PID detection (registry read failure,
`/proc` read error, permission issue, race condition in process tree),
the function silently returns `{}`. Then in `cmd_send`:

```python
sender_info=sender_info or None,   # {} is falsy → becomes None
```

Result: `metadata["sender"]` is never set → receiver's reply_stack
is never populated.

**Why spawn-specific**: Spawn creates additional agents in the registry.
More agents = more iterations in `_find_sender_by_pid()` = more chances
for an exception (e.g., stale PID, permission on `/proc/<pid>/stat`).

### 2. Process tree disconnection via tmux (MEDIUM probability)

The spawned agent runs in a new tmux pane. Depending on tmux configuration
and OS, the process tree might be:

```
tmux server
  ├── bash (pane 1) → synapse claude (Agent A) → claude → synapse send
  └── bash (pane 2) → synapse gemini (Agent B)
```

If `is_descendant_of()` traverses up from `synapse send` and hits the
tmux server before Agent A's synapse PID (due to process reparenting
by tmux), it might fail to find Agent A as an ancestor.

This could happen if tmux uses `setsid()` or process group isolation
when creating new panes, altering the parent-child relationship visible
via `/proc/<pid>/stat`.

### 3. Timing / race condition (MEDIUM probability)

After spawn, Agent A's AI may immediately run `synapse send` before
Agent B's server is fully ready. While `cmd_send` checks port availability,
there's a window where:

- Port is open (uvicorn bound) but
- The A2A router's `_send_task_message` hasn't fully initialized

If the message arrives during this window, it might be processed by
a partially-initialized handler that doesn't populate the reply_stack.

### 4. Spawned agent process restart (LOW probability)

If the spawned agent crashes during initialization and auto-restarts,
the new process has a fresh, empty `reply_stack`. Any previously
stored entries are lost.

## Resolution

Implementing **file-based reply target persistence** (`synapse/reply_target.py`)
as a durable fallback:

1. On message receive: write to both in-memory reply_stack AND file
2. On `synapse reply`: try in-memory first, fallback to file if empty
3. File stored per-agent: `~/.a2a/registry/<agent_id>.reply.json`

This addresses ALL candidate causes because the file persists across:
- Silent exceptions (file written at the server level, not CLI level)
- Process tree issues (file doesn't depend on PID detection)
- Timing issues (file survives partial initialization)
- Process restarts (file persists on disk)

## Reproduction

Requires tmux and two agent types installed:

```bash
# Terminal 1: Start Agent A
synapse claude

# Agent A's AI runs (inside PTY):
synapse spawn gemini
synapse send synapse-gemini-8110 "What files are in this project?" --response

# Agent B (gemini) processes the message and tries:
synapse reply "Here are the files: ..."
# → Error: No reply target. No pending messages to reply to.
```

## Files involved

- `synapse/reply_stack.py` — current in-memory implementation
- `synapse/tools/a2a.py:129-142` — `_find_sender_by_pid()` with silent catch
- `synapse/a2a_compat.py:776-786` — reply_stack population in `_send_task_message`
- `synapse/reply_target.py` — new file-based fallback (to be implemented)
