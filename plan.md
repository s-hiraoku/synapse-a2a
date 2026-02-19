# Plan: Fix `synapse reply` for Spawned Agents (Issue #237)

## Problem Analysis

When a message with `--response` is sent to a spawned agent, the agent's `synapse reply`
fails with "No reply target. No pending messages to reply to."

### Current Flow (Broken)

```
Sender → HTTP POST /tasks/send → Receiver Server
         ├─ reply_stack.set(sender_info)  [in-memory, SHOULD work]
         └─ controller.write("A2A: [REPLY EXPECTED] ...")  → PTY

Spawned Agent's Claude Code → `synapse reply "answer"`
         ├─ build_sender_info() → finds own endpoint via PID ancestry
         └─ GET /reply-stack/get → 404 (reply_stack is empty!)
```

### Root Causes Identified

1. **In-memory reply_stack is fragile**: If `build_sender_info()` on the sender
   returns `{}` (empty dict — happens when running `synapse send` from outside a
   synapse agent without `--from`), the metadata has no `sender` field. The receiver's
   server then skips `reply_stack.set()` because `has_reply_target()` returns False.

2. **No file-based fallback**: The reply_stack is purely in-memory. If it's not
   populated (edge cases, race conditions, missing sender info), there's no durable
   fallback.

## Solution: File-Based Reply Target Persistence

### Approach: Dual storage (in-memory + file)

When `/tasks/send` receives a message with `response_expected=True`, persist sender
info to a file **in addition to** the existing in-memory reply_stack. The
`/reply-stack/get` endpoint falls back to the file if the in-memory stack is empty.

### Changes

#### 1. New module: `synapse/reply_target.py`

File-based reply target storage using the agent's registry directory:
- Path: `~/.a2a/registry/<agent_id>.reply.json`  (co-located with registry files)
- Atomic writes (write to .tmp, rename) for safety
- Methods: `save()`, `load()`, `pop()`, `list_targets()`
- Storage format: `{<sender_id>: {sender_endpoint, sender_uds_path, sender_task_id, timestamp}}`

#### 2. Update `synapse/a2a_compat.py`

- In `_send_task_message()`: After `reply_stack.set(...)`, also call `reply_target.save()`
- Also save when sender info has at least sender_task_id (even without full endpoint)
- In `/reply-stack/get`: If in-memory stack returns None, check `reply_target.load()`
- In `/reply-stack/pop`: Also call `reply_target.pop()` for cleanup
- In `/reply-stack/list`: Include file-based targets in the list

#### 3. Update `synapse/tools/a2a.py` (cmd_reply)

- No changes needed if the `/reply-stack/get` endpoint handles the fallback internally
- (The endpoint already returns the data; the client doesn't need to know the source)

#### 4. Tests: `tests/test_reply_target.py`

- Test file-based save/load/pop operations
- Test atomic write safety
- Test fallback: in-memory stack empty → file has data → returns file data
- Test cleanup after pop
- Test concurrent access (thread safety)
- Test the full flow: send with response_expected → reply_stack/get returns data from file

#### 5. Tests: Update `tests/test_a2a_compat.py`

- Add test: reply_stack populated AND file persisted when response_expected=True
- Add test: file-based fallback works when in-memory stack is cleared
- Add test: pop cleans both in-memory and file storage

### File Summary

| File | Action | Description |
|------|--------|-------------|
| `synapse/reply_target.py` | **New** | File-based reply target storage |
| `synapse/a2a_compat.py` | **Edit** | Add file persistence + fallback in endpoints |
| `tests/test_reply_target.py` | **New** | Unit tests for file-based storage |
| `tests/test_a2a_compat.py` | **Edit** | Integration tests for fallback behavior |
