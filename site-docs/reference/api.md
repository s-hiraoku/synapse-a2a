# API Endpoints

Complete reference for all Synapse A2A HTTP endpoints.

## A2A Standard Endpoints

| Method | Endpoint | Description |
|:------:|----------|-------------|
| GET | `/.well-known/agent.json` | Agent Card discovery |
| POST | `/tasks/send` | Send message (subject to Readiness Gate) |
| GET | `/tasks/{id}` | Get task status |

## Synapse Extensions

| Method | Endpoint | Description |
|:------:|----------|-------------|
| POST | `/tasks/send-priority` | Priority message delivery (1-5); 5 = interrupt |
| POST | `/tasks/create` | Create task context without PTY delivery |
| GET | `/tasks` | List all tasks |
| POST | `/tasks/{id}/cancel` | Cancel a task |
| GET | `/status` | Agent status (READY/PROCESSING/WAITING/DONE) |

### Priority Send

```bash
curl -X POST http://localhost:8100/tasks/send-priority \
  -H "Content-Type: application/json" \
  -d '{
    "message": {
      "role": "user",
      "parts": [{"type": "text", "text": "Urgent review needed"}]
    },
    "metadata": {
      "priority": 4,
      "from": "synapse-claude-8100"
    }
  }'
```

## Reply Stack

| Method | Endpoint | Description |
|:------:|----------|-------------|
| GET | `/reply-stack/list` | List pending senders |
| GET | `/reply-stack/get` | Get sender info without removing |
| GET | `/reply-stack/pop` | Pop sender from reply map |

## Task Board (B1)

| Method | Endpoint | Description |
|:------:|----------|-------------|
| GET | `/tasks/board` | List all board tasks |
| POST | `/tasks/board` | Create a board task |
| POST | `/tasks/board/{id}/claim` | Atomic task claim |
| POST | `/tasks/board/{id}/complete` | Complete task + unblock dependents |
| POST | `/tasks/board/{id}/fail` | Mark task failed |
| POST | `/tasks/board/{id}/reopen` | Reopen to pending |

### Create Board Task

```bash
curl -X POST http://localhost:8100/tasks/board \
  -H "Content-Type: application/json" \
  -d '{
    "subject": "Implement feature",
    "description": "OAuth2 authentication",
    "priority": 4,
    "created_by": "synapse-claude-8100"
  }'
```

## Plan Approval (B3)

| Method | Endpoint | Description |
|:------:|----------|-------------|
| POST | `/tasks/{id}/approve` | Approve a plan |
| POST | `/tasks/{id}/reject` | Reject with reason |

## Team & Spawn (B6)

| Method | Endpoint | Description |
|:------:|----------|-------------|
| POST | `/team/start` | Start multiple agents |
| POST | `/spawn` | Spawn a single agent |

### Team Start

```bash
curl -X POST http://localhost:8100/team/start \
  -H "Content-Type: application/json" \
  -d '{
    "agents": ["gemini", "codex"],
    "layout": "split",
    "tool_args": ["--dangerously-skip-permissions"]
  }'
```

### Spawn

```bash
curl -X POST http://localhost:8100/spawn \
  -H "Content-Type: application/json" \
  -d '{
    "profile": "gemini",
    "name": "Helper",
    "role": "test writer",
    "skill_set": "dev-set",
    "tool_args": ["--dangerously-skip-permissions"]
  }'
```

**Response:**

```json
{
  "agent_id": "synapse-gemini-8110",
  "port": 8110,
  "terminal_used": "tmux",
  "status": "spawned"
}
```

## External Agents

| Method | Endpoint | Description |
|:------:|----------|-------------|
| POST | `/external/discover` | Register external A2A agent |
| GET | `/external/agents` | List external agents |
| GET | `/external/agents/{alias}` | Get agent details |
| DELETE | `/external/agents/{alias}` | Remove external agent |
| POST | `/external/agents/{alias}/send` | Send message to external |

## Webhooks

| Method | Endpoint | Description |
|:------:|----------|-------------|
| POST | `/webhooks` | Register notification hook |
| GET | `/webhooks` | List webhooks |
| DELETE | `/webhooks?url=...` | Unregister webhook |
| GET | `/webhooks/deliveries` | Recent delivery attempts |

## SSE Streaming

| Method | Endpoint | Description |
|:------:|----------|-------------|
| GET | `/tasks/{id}/subscribe` | Subscribe to task updates (Server-Sent Events) |

## Readiness Gate

The Readiness Gate blocks incoming requests until the agent completes initialization.

| Condition | Behavior |
|-----------|----------|
| Agent initializing | Wait up to 30s (`AGENT_READY_TIMEOUT`) |
| Still not ready | HTTP **503** + `Retry-After: 5` |
| Priority 5 | **Bypass** gate entirely |
| Reply messages (`in_reply_to`) | **Bypass** gate |

## Long Message Handling

Messages exceeding the threshold (default: 200 chars) are stored in temp files:

```
[LONG MESSAGE - FILE ATTACHED]
The full message content is stored at: /tmp/synapse-a2a/messages/<task_id>.txt
Please read this file to get the complete message.
```

| Setting | Default | Description |
|---------|---------|-------------|
| `SYNAPSE_LONG_MESSAGE_THRESHOLD` | 200 chars | Storage threshold |
| `SYNAPSE_LONG_MESSAGE_TTL` | 3600s | Temp file TTL |

## Error Responses

| Status | Cause | Solution |
|:------:|-------|----------|
| 404 | Agent not found | Check with `synapse list` |
| 409 | Ambiguous target | Use name, full ID, or type-port |
| 503 | Agent initializing | Wait and retry (automatic) |
| 502 | Server not responding | Restart the agent |
