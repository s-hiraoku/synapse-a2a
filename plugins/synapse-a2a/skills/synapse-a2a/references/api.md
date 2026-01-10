# A2A Protocol Reference

## Endpoints

Standard Google A2A endpoints:

| Endpoint | URL |
|----------|-----|
| Agent Card | `http://localhost:<port>/.well-known/agent.json` |
| Send Task | `http://localhost:<port>/tasks/send` |
| Send Priority | `http://localhost:<port>/tasks/send-priority?priority=<1-5>` |
| Task Status | `http://localhost:<port>/tasks/<id>` |

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
    "response_required": true
  }
}
```

## Priority Levels

| Priority | Use Case | Behavior |
|----------|----------|----------|
| 1-2 | Low priority, background tasks | Standard message delivery |
| 3 | Normal tasks | Default priority |
| 4 | Urgent follow-ups | Prioritized delivery |
| 5 | Critical/emergency tasks | Sends SIGINT first, then message |

**Priority 5 sequence:**
1. Sends SIGINT to target agent (interrupts current task)
2. Waits briefly for interrupt processing
3. Sends the message

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

### Send with Priority

```bash
curl -X POST "http://localhost:8100/tasks/send-priority?priority=5" \
  -H "Content-Type: application/json" \
  -d '{"message": {"role": "user", "parts": [{"type": "text", "text": "Stop!"}]}}'
```

### Get Task Status

```bash
curl http://localhost:8100/tasks/<task_id>
```
