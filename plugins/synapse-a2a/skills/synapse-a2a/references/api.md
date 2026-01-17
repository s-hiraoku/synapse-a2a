# A2A Protocol Reference

## Endpoints

### Standard Google A2A Endpoints

These endpoints follow the official Google A2A specification:

| Endpoint | Path | Description |
|----------|------|-------------|
| Agent Card | `/.well-known/agent.json` | Agent capabilities and metadata |
| Send Task | `/tasks/send` | Send a task to the agent |
| Task Status | `/tasks/{id}` | Get task status by ID |

### Synapse Extension Endpoints

These are Synapse-specific extensions (not part of standard A2A):

| Endpoint | Path | Description |
|----------|------|-------------|
| Send with Priority | `/tasks/send-priority?priority=<1-5>` | Send task with priority level |

> **Naming Convention Note:** The endpoint path `/tasks/send-priority` follows Google A2A spec guidelines which recommend extensions use clear, scoped naming. The `x-` prefix convention is used for metadata fields, while endpoint paths use descriptive names. Metadata fields like `sender` and `response_expected` are nested in the `metadata` object per A2A spec.

> **Note:** Priority 5 triggers SIGINT before message delivery (emergency interrupt).

## Transport Layer

Synapse supports dual transport: **Unix Domain Sockets (UDS)** and **HTTP/TCP**.

### UDS (Preferred for Local Communication)

UDS provides faster, more secure inter-agent communication on the same machine.

**Socket path:** `/tmp/synapse-a2a/{agent_id}.sock`

Examples:
```text
/tmp/synapse-a2a/synapse-claude-8100.sock
/tmp/synapse-a2a/synapse-gemini-8110.sock
/tmp/synapse-a2a/synapse-codex-8120.sock
```

**Customization:** Set `SYNAPSE_UDS_DIR` environment variable to change the socket directory.

### HTTP/TCP (Fallback)

HTTP endpoints are available when UDS is not accessible (e.g., cross-machine communication).

**Base URL:** `http://localhost:<port>`

### Routing Precedence

When `synapse send` or the A2A client sends a message, routing follows this order:

1. **Check UDS socket existence:** Look for `/tmp/synapse-a2a/{agent_id}.sock`
2. **If socket exists:** Use UDS (faster, no network overhead)
3. **If socket missing:** Fall back to HTTP using the agent's registered port

```text
┌─────────────────────────────────────────────────────┐
│  synapse send codex "message"                       │
└─────────────────┬───────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────┐
│  Does /tmp/synapse-a2a/synapse-codex-8120.sock      │
│  exist?                                             │
└─────────────────┬───────────────────────────────────┘
                  │
         ┌────────┴────────┐
         │                 │
         ▼ Yes             ▼ No
┌─────────────────┐ ┌─────────────────────────────────┐
│  Use UDS        │ │  Use HTTP localhost:8120        │
│  (local_only)   │ │  (network fallback)             │
└─────────────────┘ └─────────────────────────────────┘
```

**Why UDS preferred:**
- Works in sandboxed environments (Codex) where network may be restricted
- No port conflicts or firewall issues
- Lower latency for local communication

## Message Format

### PTY Output Format

```text
[A2A:<task_id>:<sender_id>] <message_content>
```

Example:
```text
[A2A:abc12345:synapse-claude-8100] Please review this code
```

### JSON Payload

Standard Google A2A message format with Synapse extensions in the metadata object:

```json
{
  "message": {
    "role": "user",
    "parts": [{"type": "text", "text": "<message>"}]
  },
  "metadata": {
    "sender": {
      "sender_id": "synapse-claude-8100",
      "sender_type": "claude",
      "sender_endpoint": "http://localhost:8100"
    },
    "response_expected": true,
    "in_reply_to": "task-id-optional"
  }
}
```

**Metadata fields explained:**
- `sender`: Synapse-specific sender identification
  - `sender_type`: Agent type - `"claude"`, `"gemini"`, or `"codex"`
  - `sender_id`: Full agent identifier (e.g., `"synapse-gemini-8110"`)
  - `sender_endpoint`: Agent's HTTP endpoint for replies
- `response_expected`: Whether the sender is waiting for a response
- `in_reply_to`: Task ID this message is replying to (for `--reply-to` responses)

## Priority Levels

| Priority | Use Case | Behavior |
|----------|----------|----------|
| 1-2 | Low priority, background tasks | Standard message delivery |
| 3 | Normal tasks | Default priority |
| 4 | Urgent follow-ups | Prioritized delivery |
| 5 | Critical/emergency tasks | Sends SIGINT first, then message |

**Priority 5 sequence:**
1. Calls `controller.interrupt()` to send SIGINT to target agent
2. Immediately calls `controller.write()` to send the message (no waiting)

## Error Handling

### Agent Not Found

```text
Error: No agent found matching 'xyz'
```
**Solution:** Use `synapse list` to see available agents.

### Multiple Agents Found

```text
Error: Ambiguous target 'codex'. Multiple agents found.
```
**Solution:** Use specific identifier like `@codex-8120`.

### Agent Not Responding

```text
Error: Agent 'synapse-claude-8100' server on port 8100 is not responding.
```
**Solution:** Restart the agent with `synapse claude`.

## HTTP API Examples

### Send Message

```bash
curl -X POST http://localhost:8100/tasks/send \
  -H "Content-Type: application/json" \
  -d '{"message": {"role": "user", "parts": [{"type": "text", "text": "Hello!"}]}}'
```

### Send with Priority (Synapse Extension)

```bash
curl -X POST "http://localhost:8100/tasks/send-priority?priority=5" \
  -H "Content-Type: application/json" \
  -d '{"message": {"role": "user", "parts": [{"type": "text", "text": "Stop!"}]}}'
```

### Get Task Status

```bash
curl http://localhost:8100/tasks/<task_id>
```
