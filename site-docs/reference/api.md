# API Endpoints

Complete reference for all Synapse A2A HTTP endpoints.

Every agent starts a local HTTP server (default port range 8100-8149) that exposes the endpoints below. Unless noted otherwise, all endpoints accept and return `application/json`.

## Authentication

When `SYNAPSE_AUTH_ENABLED=true`, most endpoints require an API key. Supply the key via one of the following methods:

| Method | Example |
|--------|---------|
| HTTP header (recommended) | `X-API-Key: your-key` |
| Query parameter | `?api_key=your-key` |

```bash
# Header-based authentication
curl -H "X-API-Key: your-key" http://localhost:8100/tasks

# Query parameter authentication
curl "http://localhost:8100/tasks?api_key=your-key"
```

!!! tip "localhost bypass"
    By default, requests from `localhost` are allowed without a key (`SYNAPSE_ALLOW_LOCALHOST=true`). Set it to `false` in production environments.

!!! note "Admin endpoints"
    Webhook management endpoints (`POST /webhooks`, `DELETE /webhooks`) require an Admin Key set via `SYNAPSE_ADMIN_KEY`.

### Protected Endpoints

| Endpoint | Required Auth |
|----------|---------------|
| `POST /tasks/send` | API Key |
| `POST /tasks/send-priority` | API Key |
| `GET /tasks/{id}` | API Key |
| `GET /tasks` | API Key |
| `POST /tasks/{id}/cancel` | API Key |
| `GET /tasks/{id}/subscribe` | API Key |
| Memory endpoints | API Key |
| Spawn / Team endpoints | API Key |
| `POST /webhooks` | Admin Key |
| `DELETE /webhooks` | Admin Key |

### Error Responses

```json
// 401 Unauthorized - No API key provided
{ "detail": "API key required" }

// 401 Unauthorized - Invalid API key
{ "detail": "Invalid API key" }

// 403 Forbidden - Admin privileges required
{ "detail": "Admin privileges required" }
```

---

## A2A Standard Endpoints

These endpoints follow the [Google A2A specification](https://a2a-protocol.org/latest/specification/).

| Method | Endpoint | Description |
|:------:|----------|-------------|
| GET | `/.well-known/agent.json` | Agent Card discovery |
| POST | `/tasks/send` | Send message (subject to Readiness Gate) |
| GET | `/tasks/{id}` | Get task status |

### Agent Card

Returns the agent's capabilities, skills, and metadata per the A2A Agent Card specification.

```bash
curl http://localhost:8100/.well-known/agent.json
```

**Response:**

```json
{
  "name": "synapse-claude-8100",
  "description": "Claude Code agent wrapped by Synapse A2A",
  "url": "http://localhost:8100",
  "capabilities": {
    "streaming": true,
    "pushNotifications": false
  },
  "skills": []
}
```

### Send Message

Send a message to the agent. The request is subject to the [Readiness Gate](#readiness-gate).

```bash
curl -X POST http://localhost:8100/tasks/send \
  -H "Content-Type: application/json" \
  -d '{
    "message": {
      "role": "user",
      "parts": [{"type": "text", "text": "Review the auth module"}]
    },
    "metadata": {
      "response_mode": "wait",
      "sender": {
        "sender_id": "synapse-gemini-8110",
        "sender_endpoint": "http://localhost:8110"
      }
    }
  }'
```

**Request body:**

| Field | Type | Required | Description |
|-------|------|:--------:|-------------|
| `message` | Message | Yes | The message to send |
| `message.role` | string | Yes | Always `"user"` for incoming messages |
| `message.parts` | Part[] | Yes | Array of message parts |
| `context_id` | string | No | Existing context to continue |
| `metadata` | object | No | Sender info, response_mode, etc. |
| `metadata.response_mode` | string | No | `"wait"`, `"notify"`, or `"silent"` (default: `"notify"`) |

**Response:**

```json
{
  "task": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "submitted",
    "message": {
      "role": "user",
      "parts": [{"type": "text", "text": "Review the auth module"}]
    },
    "artifacts": [],
    "created_at": "2026-03-05T10:00:00",
    "updated_at": "2026-03-05T10:00:00",
    "context_id": null,
    "metadata": {}
  }
}
```

### Get Task

```bash
curl http://localhost:8100/tasks/550e8400-e29b-41d4-a716-446655440000
```

**Response:** Returns a `Task` object with the current status (`submitted`, `working`, `input_required`, `completed`, `failed`, `canceled`), artifacts, and error information if applicable.

---

## Synapse Extensions

| Method | Endpoint | Description |
|:------:|----------|-------------|
| POST | `/tasks/send-priority` | Priority message delivery (1-5); 5 = interrupt |
| POST | `/tasks/create` | Create task context without PTY delivery |
| POST | `/history/update` | Update history observation status (callback) |
| GET | `/tasks` | List all tasks (query: `context_id`) |
| POST | `/tasks/{id}/cancel` | Cancel a task |
| GET | `/status` | Agent status (READY/PROCESSING/WAITING/DONE) |
| GET | `/debug/pty` | Snapshot of the pyte-backed virtual terminal (debug) |
| GET | `/debug/waiting` | Last ~50 WAITING-detection attempts plus `renderer_available` (debug) |

### Priority Send

Send a message with a priority level. Priority 5 sends a SIGINT to the agent before delivering the message, enabling interrupt-style communication.

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

| Priority | Use Case |
|:--------:|----------|
| 1-2 | Low priority, background tasks |
| 3 | Normal tasks (default) |
| 4 | Urgent follow-ups |
| 5 | Critical interrupt (sends SIGINT first) |

### Create Task

Create a task context without sending to PTY. Used internally by `--wait` mode to register a task before sending.

```bash
curl -X POST http://localhost:8100/tasks/create \
  -H "Content-Type: application/json" \
  -d '{
    "message": {
      "role": "user",
      "parts": [{"type": "text", "text": "Analyzing codebase"}]
    },
    "metadata": {
      "response_mode": "wait"
    }
  }'
```

**Response:**

```json
{
  "task": {
    "id": "660f9500-f39c-52e5-b827-557766550000",
    "status": "submitted",
    "message": {
      "role": "user",
      "parts": [{"type": "text", "text": "Analyzing codebase"}]
    },
    "artifacts": [],
    "created_at": "2026-03-05T10:00:00",
    "updated_at": "2026-03-05T10:00:00"
  }
}
```

## History Update (Completion Callback)

| Method | Endpoint | Description |
|:------:|----------|-------------|
| POST | `/history/update` | Update sender-side history status (completion callback) |

Used by the receiver to notify the sender that a `--silent` task has reached a terminal state. The sender's history record is updated from `sent` to the new status.

### Request

```bash
curl -X POST http://localhost:8100/history/update \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "abc123-...",
    "status": "completed",
    "output_summary": "Refactoring complete. 3 files changed."
  }'
```

| Field | Type | Required | Description |
|-------|------|:--------:|-------------|
| `task_id` | string | Yes | Task ID to update in sender's history |
| `status` | string | Yes | New status: `completed`, `failed`, or `canceled` |
| `output_summary` | string | No | Optional output summary text |

### Response

**200 OK:**

```json
{
  "updated": true,
  "task_id": "abc123-...",
  "status": "completed"
}
```

**404 Not Found** — returned if `task_id` does not exist in the sender's history.

### GET /status

Returns the current agent status and a tail of recent PTY output (last 2000 characters).

```bash
curl http://localhost:8100/status
```

**Response:**

```json
{
  "status": "READY",
  "context": "... recent PTY output (last 2000 chars) ..."
}
```

| Status | Description |
|--------|-------------|
| `NOT_STARTED` | Controller has not started yet |
| `PROCESSING` | Agent is actively processing (startup or handling requests) |
| `READY` | Agent is idle, waiting for user input |
| `WAITING` | Agent is showing selection UI, waiting for user choice |
| `DONE` | Task completed (auto-transitions to READY after 10 seconds) |
| `SHUTTING_DOWN` | Graceful shutdown in progress |

### GET /debug/pty

Returns a JSON snapshot of the pyte-backed virtual terminal that Synapse uses to run `waiting_detection` regexes against a rendered screen (not ANSI-stripped raw bytes). Useful when debugging why a ratatui / TUI overlay is — or is not — detected as a WAITING prompt.

```bash
curl http://localhost:8100/debug/pty | jq .display
```

**Response:**

```json
{
  "display": ["... row 1 ...", "... row 2 ..."],
  "cursor": {"x": 12, "y": 4},
  "alt_screen": false,
  "columns": 120,
  "rows": 40
}
```

| Field | Description |
|-------|-------------|
| `display` | Current rendered screen as an array of rendered rows (`string[]`) |
| `cursor` | Cursor position `{x, y}` in cell coordinates |
| `alt_screen` | `true` when the application is on the xterm alternate screen buffer |
| `columns` / `rows` | Virtual terminal dimensions |

The endpoint is exposed by every per-agent A2A server and is intended for human inspection and regression debugging.

### GET /debug/waiting

Returns the in-memory ring of the most recent WAITING-detection attempts plus a top-level `renderer_available` flag. Used by `synapse status <agent> --debug-waiting` and by the Phase 1.5 `synapse waiting-debug collect` CLI to persist snapshots for offline analysis.

```bash
curl http://localhost:8100/debug/waiting | jq .
```

**Response (abridged):**

```json
{
  "renderer_available": true,
  "attempts": [
    {
      "timestamp": "2026-04-22T10:00:00+00:00",
      "profile": "claude",
      "pattern_source": "profile",
      "path_used": "pyte",
      "confidence": 0.92,
      "idle_gate_dropped": false,
      "matched": true
    }
  ],
  "counts": {
    "total": 42,
    "matched": 11,
    "idle_gate_drops": 3
  }
}
```

| Field | Description |
|-------|-------------|
| `renderer_available` | `true` when the pyte renderer is usable on this agent; `false` triggers the `(renderer: off)` status annotation |
| `attempts` | Rolling buffer of the last ~50 detection attempts (oldest first) |
| `counts` | Aggregate counters over the buffer — totals, matches, idle-gate drops |

The ring is in-memory only and empties on process restart. Use [`synapse waiting-debug collect`](cli.md#waiting-debug-phase-15-collection) to persist snapshots across agents.


---

## Plan Approval (B3)

| Method | Endpoint | Description |
|:------:|----------|-------------|
| POST | `/tasks/{id}/approve` | Approve a plan |
| POST | `/tasks/{id}/reject` | Reject with reason |

### Approve Plan

```bash
curl -X POST http://localhost:8100/tasks/550e8400-.../approve \
  -H "Content-Type: application/json" \
  -d '{}'
```

**Response:**

```json
{
  "approved": true,
  "task_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

### Reject Plan

```bash
curl -X POST http://localhost:8100/tasks/550e8400-.../reject \
  -H "Content-Type: application/json" \
  -d '{"reason": "Use a different approach for error handling"}'
```

**Response:**

```json
{
  "rejected": true,
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "reason": "Use a different approach for error handling"
}
```

---

## Team & Spawn (B6)

| Method | Endpoint | Description |
|:------:|----------|-------------|
| POST | `/team/start` | Start multiple agents |
| POST | `/spawn` | Spawn a single agent |

### POST /team/start -- Start Team

Start multiple agents in split terminal panes. Detects the current terminal environment (tmux, iTerm2, Terminal.app, Ghostty, zellij) and creates split panes for each agent. Falls back to background process spawning when no supported terminal is detected.

**Request body:**

| Field | Type | Required | Default | Description |
|-------|------|:--------:|---------|-------------|
| `agents` | string[] | Yes | -- | Agent profiles to start (min 1) |
| `layout` | string | No | `"split"` | Pane layout: `"split"`, `"horizontal"`, or `"vertical"` |
| `terminal` | string | No | auto-detect | Terminal app to use |
| `tool_args` | string[] | No | `null` | Extra CLI arguments passed to all agents |

```bash
curl -X POST http://localhost:8100/team/start \
  -H "Content-Type: application/json" \
  -d '{
    "agents": ["gemini", "codex"],
    "layout": "split",
    "tool_args": ["--dangerously-skip-permissions"]
  }'
```

**Response:**

```json
{
  "started": [
    {
      "agent_type": "gemini",
      "status": "submitted",
      "reason": null
    },
    {
      "agent_type": "codex",
      "status": "submitted",
      "reason": null
    }
  ],
  "terminal_used": "tmux"
}
```

!!! note "Agent status"
    Each agent entry in `started` has a `status` field that is either `"submitted"` (successfully started) or `"failed"` (with a `reason` string explaining the failure).

### POST /spawn -- Spawn Single Agent

Spawn a single agent in a new terminal pane. Supports optional worktree isolation.

**Request body:**

| Field | Type | Required | Default | Description |
|-------|------|:--------:|---------|-------------|
| `profile` | string | Yes | -- | Agent profile name (claude, gemini, codex, etc.) |
| `port` | integer | No | auto-assign | Explicit port number |
| `name` | string | No | `null` | Custom agent name |
| `role` | string | No | `null` | Agent role description |
| `skill_set` | string | No | `null` | Skill set to activate |
| `terminal` | string | No | auto-detect | Terminal app to use |
| `tool_args` | string[] | No | `null` | Extra CLI arguments (e.g., `["--dangerously-skip-permissions"]`) |
| `worktree` | bool or string | No | `null` | `true` for auto-generated worktree name, or a string for an explicit name |

```bash
curl -X POST http://localhost:8100/spawn \
  -H "Content-Type: application/json" \
  -d '{
    "profile": "gemini",
    "port": 8115,
    "name": "Gem",
    "role": "test writer",
    "skill_set": "dev-set",
    "terminal": "tmux",
    "worktree": true,
    "tool_args": ["--dangerously-skip-permissions"]
  }'
```

**Response:**

```json
{
  "agent_id": "synapse-gemini-8115",
  "port": 8115,
  "terminal_used": "tmux",
  "status": "submitted",
  "worktree_path": "/repo/.synapse/worktrees/bold-hawk",
  "worktree_branch": "worktree-bold-hawk"
}
```

| Response Field | Type | Description |
|----------------|------|-------------|
| `agent_id` | string | Runtime ID of the spawned agent |
| `port` | integer | Port the agent is listening on |
| `terminal_used` | string | Terminal used to create the pane |
| `status` | string | `"submitted"` or `"failed"` |
| `reason` | string | Error message (only present when `status` is `"failed"`) |
| `worktree_path` | string | Filesystem path to the worktree (only if requested) |
| `worktree_branch` | string | Git branch name for the worktree (only if requested) |

!!! tip "Worktree isolation"
    When `worktree` is set, the agent runs inside a dedicated git worktree at `.synapse/worktrees/<name>`. This provides filesystem isolation so agents cannot interfere with each other's work.

---

## Shared Memory

Cross-agent knowledge sharing via a project-local SQLite database. Supports UPSERT semantics on keys, tag-based filtering, and full-text search.

| Method | Endpoint | Description |
|:------:|----------|-------------|
| GET | `/memory/list` | List memories (query: `author`, `tags`, `limit`) |
| POST | `/memory/save` | Save or update a memory (UPSERT on key) |
| GET | `/memory/search` | Search memories (query: `q`, `limit` [default: 100]) |
| GET | `/memory/{id_or_key}` | Get a specific memory by ID or key |
| DELETE | `/memory/{id_or_key}` | Delete a memory |

### POST /memory/save -- Save Memory

Save or update a memory entry. If a memory with the same `key` already exists, it is updated (UPSERT).

**Request body:**

| Field | Type | Required | Default | Description |
|-------|------|:--------:|---------|-------------|
| `key` | string | Yes | -- | Unique key for the memory |
| `content` | string | Yes | -- | Memory content text |
| `author` | string | Yes | -- | Agent ID of the author |
| `tags` | string[] | No | `[]` | Tags for categorization |
| `notify` | boolean | No | `false` | Broadcast notification to other agents |

```bash
curl -X POST http://localhost:8100/memory/save \
  -H "Content-Type: application/json" \
  -d '{
    "key": "auth-pattern",
    "content": "Use OAuth2 with PKCE flow",
    "author": "synapse-claude-8100",
    "tags": ["security", "auth"],
    "notify": true
  }'
```

**Response:**

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "key": "auth-pattern",
  "content": "Use OAuth2 with PKCE flow",
  "author": "synapse-claude-8100",
  "tags": ["security", "auth"],
  "created_at": "2026-03-05T10:00:00",
  "updated_at": "2026-03-05T10:00:00"
}
```

!!! tip "Notify flag"
    When `notify` is `true`, the agent broadcasts a notification about the saved memory to all other running agents in the project. This is useful for sharing discoveries or decisions across the team.

### GET /memory/list -- List Memories

List memories with optional filters.

**Query parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `author` | string | -- | Filter by author agent ID |
| `tags` | string | -- | Comma-separated tags (matches memories containing any listed tag) |
| `limit` | integer | `50` | Maximum results (capped at 100) |

```bash
# List all memories
curl http://localhost:8100/memory/list

# Filter by author
curl "http://localhost:8100/memory/list?author=synapse-claude-8100"

# Filter by tags
curl "http://localhost:8100/memory/list?tags=security,auth&limit=10"
```

**Response:**

```json
{
  "memories": [
    {
      "id": "a1b2c3d4-...",
      "key": "auth-pattern",
      "content": "Use OAuth2 with PKCE flow",
      "author": "synapse-claude-8100",
      "tags": ["security", "auth"],
      "created_at": "2026-03-05T10:00:00",
      "updated_at": "2026-03-05T10:00:00"
    }
  ]
}
```

### GET /memory/search -- Search Memories

Full-text search across key, content, and tags using LIKE matching.

**Query parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `q` | string | (required) | Search query string |
| `limit` | integer | `100` | Maximum results |

```bash
curl "http://localhost:8100/memory/search?q=OAuth2"
```

**Response:**

```json
{
  "memories": [
    {
      "id": "a1b2c3d4-...",
      "key": "auth-pattern",
      "content": "Use OAuth2 with PKCE flow",
      "author": "synapse-claude-8100",
      "tags": ["security", "auth"],
      "created_at": "2026-03-05T10:00:00",
      "updated_at": "2026-03-05T10:00:00"
    }
  ]
}
```

### GET /memory/{id_or_key} -- Get Memory

Retrieve a single memory by its UUID or unique key.

```bash
curl http://localhost:8100/memory/auth-pattern
```

**Response:** Returns the memory object (same shape as items in the list endpoint). Returns HTTP 404 if not found.

### DELETE /memory/{id_or_key} -- Delete Memory

Delete a memory by its UUID or unique key.

```bash
curl -X DELETE http://localhost:8100/memory/auth-pattern
```

**Response:**

```json
{
  "deleted": true,
  "id_or_key": "auth-pattern"
}
```

Returns HTTP 404 if the memory does not exist.

---

## Reply Stack

The reply stack tracks pending senders so agents can route replies to the correct originator.

| Method | Endpoint | Description |
|:------:|----------|-------------|
| GET | `/reply-stack/list` | List pending sender IDs |
| GET | `/reply-stack/get` | Get sender info without removing |
| GET | `/reply-stack/pop` | Pop sender from reply map |

### GET /reply-stack/list

```bash
curl http://localhost:8100/reply-stack/list
```

**Response:**

```json
{
  "sender_ids": ["synapse-claude-8100", "synapse-gemini-8110"]
}
```

### GET /reply-stack/get

Peek at a reply target without removing it. Returns the most recent entry (LIFO) if no `sender_id` is specified.

```bash
curl "http://localhost:8100/reply-stack/get?sender_id=synapse-claude-8100"
```

**Response:**

```json
{
  "sender_endpoint": "http://localhost:8100",
  "sender_uds_path": "/tmp/synapse-a2a/uds/synapse-claude-8100.sock",
  "sender_task_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

### GET /reply-stack/pop

Pop (retrieve and remove) a reply target. Same query parameter and response shape as `/reply-stack/get`.

---

## External Agents

Manage connections to external A2A-compatible agents.

| Method | Endpoint | Description |
|:------:|----------|-------------|
| POST | `/external/discover` | Register external A2A agent |
| GET | `/external/agents` | List external agents |
| GET | `/external/agents/{alias}` | Get agent details |
| DELETE | `/external/agents/{alias}` | Remove external agent |
| POST | `/external/agents/{alias}/send` | Send message to external |

### Discover External Agent

```bash
curl -X POST http://localhost:8100/external/discover \
  -H "Content-Type: application/json" \
  -d '{
    "url": "http://remote-host:9000",
    "alias": "remote-assistant"
  }'
```

### Send to External Agent

```bash
curl -X POST http://localhost:8100/external/agents/remote-assistant/send \
  -H "Content-Type: application/json" \
  -d '{
    "message": {
      "role": "user",
      "parts": [{"type": "text", "text": "Analyze the dataset"}]
    }
  }'
```

---

## Webhooks

Register HTTP callback URLs to receive notifications about task lifecycle events.

| Method | Endpoint | Description |
|:------:|----------|-------------|
| POST | `/webhooks` | Register notification hook (Admin Key required) |
| GET | `/webhooks` | List webhooks |
| DELETE | `/webhooks?url=...` | Unregister webhook (Admin Key required) |
| GET | `/webhooks/deliveries` | Recent delivery attempts |

### Register Webhook

```bash
curl -X POST http://localhost:8100/webhooks \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-admin-key" \
  -d '{
    "url": "https://your-server.com/webhook",
    "events": ["task.completed", "task.failed"],
    "secret": "your-webhook-secret"
  }'
```

**Response:**

```json
{
  "id": "wh_abc123",
  "url": "https://your-server.com/webhook",
  "events": ["task.completed", "task.failed"],
  "active": true,
  "created_at": "2026-03-05T12:00:00Z"
}
```

### Webhook Event Types

| Event | Trigger | Payload Fields |
|-------|---------|----------------|
| `task.completed` | Task finished successfully | `task_id`, `artifacts` |
| `task.failed` | Task failed | `task_id`, `error` |
| `task.canceled` | Task was canceled | `task_id` |

### Webhook Payload

All webhook deliveries include an `X-Webhook-Signature` header for HMAC-SHA256 signature verification.

```json
{
  "event_type": "task.completed",
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2026-03-05T12:00:00Z",
  "data": {
    "status": "completed",
    "artifacts": [
      {
        "type": "text",
        "data": {"content": "Task output..."}
      }
    ]
  }
}
```

### Delivery Retries

Failed deliveries are retried with exponential backoff:

| Retry | Delay |
|:-----:|:-----:|
| 1st | 1 second |
| 2nd | 2 seconds |
| 3rd | 4 seconds |

### List Deliveries

```bash
curl http://localhost:8100/webhooks/deliveries \
  -H "X-API-Key: your-admin-key"
```

**Response:**

```json
[
  {
    "id": "del_xyz789",
    "webhook_id": "wh_abc123",
    "event_type": "task.completed",
    "status": "success",
    "status_code": 200,
    "attempts": 1,
    "created_at": "2026-03-05T12:00:00Z"
  }
]
```

---

## SSE Streaming

Subscribe to real-time task updates via Server-Sent Events.

| Method | Endpoint | Description |
|:------:|----------|-------------|
| GET | `/tasks/{id}/subscribe` | Subscribe to task updates (Server-Sent Events) |

### Subscribe to Task Updates

Opens a long-lived connection and streams events as the task progresses. The response uses `text/event-stream` content type with the following headers:

- `Cache-Control: no-cache`
- `Connection: keep-alive`
- `X-Accel-Buffering: no` (disables nginx buffering)

```bash
curl -N http://localhost:8100/tasks/550e8400-.../subscribe
```

### SSE Event Types

| Event | Description | Payload Shape |
|-------|-------------|---------------|
| `output` | New CLI output data | `{"type": "output", "data": "..."}` |
| `status` | Task status changed | `{"type": "status", "status": "working"}` |
| `done` | Task completed (final event) | `{"type": "done", "status": "completed", "artifacts": [...]}` |
| `error` | Task not found / error | `{"type": "error", "message": "..."}` |

### SSE Event Stream Example

```text
data: {"type": "status", "status": "working"}

data: {"type": "output", "data": "Processing request..."}

data: {"type": "output", "data": "Generated file: main.py"}

data: {"type": "done", "status": "completed", "artifacts": [{"type": "text", "data": {"content": "..."}}]}
```

### SSE with Authentication

When authentication is enabled, pass the API key via header or query parameter:

```bash
# Header
curl -N -H "X-API-Key: your-key" \
  http://localhost:8100/tasks/550e8400-.../subscribe

# Query parameter (useful for EventSource in browsers)
curl -N "http://localhost:8100/tasks/550e8400-.../subscribe?api_key=your-key"
```

!!! tip "JavaScript EventSource"
    The browser `EventSource` API cannot send custom headers. Use the query parameter approach instead:
    ```javascript
    const es = new EventSource(
      `http://localhost:8100/tasks/${taskId}/subscribe?api_key=your-key`
    );
    ```

### Done Event with Error

When a task fails, the `done` event includes an `error` field:

```json
{
  "type": "done",
  "status": "failed",
  "artifacts": [],
  "error": {
    "code": "PERMISSION_DENIED",
    "message": "Permission denied"
  }
}
```

---

## Readiness Gate

The Readiness Gate blocks incoming requests until the agent completes initialization (identity instruction sending).

| Condition | Behavior |
|-----------|----------|
| Agent initializing | Wait up to 30s (`AGENT_READY_TIMEOUT`) |
| Still not ready | HTTP **503** + `Retry-After: 5` |
| Priority 5 | **Bypass** gate entirely |
| Reply messages (`in_reply_to`) | **Bypass** gate |

!!! note
    The Readiness Gate protects `/tasks/send` and `/tasks/send-priority` endpoints. Other endpoints like `/status` and `/.well-known/agent.json` are available immediately.

---

## Long Message Handling

Messages exceeding the threshold (default: 200 chars) are stored in temp files and a short reference is sent to the PTY instead:

```
[LONG MESSAGE - FILE ATTACHED]
The full message content is stored at: /tmp/synapse-a2a/messages/<task_id>.txt
Please read this file to get the complete message.
```

| Setting | Default | Description |
|---------|---------|-------------|
| `SYNAPSE_LONG_MESSAGE_THRESHOLD` | 200 chars | Storage threshold |
| `SYNAPSE_LONG_MESSAGE_TTL` | 3600s | Temp file TTL |

---

## File Safety

!!! note "CLI-only feature"
    File Safety is a CLI-only feature with no HTTP API endpoints. It tracks file modifications made by agents in a project-local SQLite database (`.synapse/file_safety.db`) and is accessed exclusively through `synapse trace` and internal controller hooks. There are no REST endpoints to query or manage file safety records directly.

---

## MCP Tools

The Synapse MCP server (`synapse mcp serve` / `python -m synapse.mcp`) exposes tools via the Model Context Protocol. These tools are called using JSON-RPC `tools/call`.

| Tool | Description |
|------|-------------|
| `bootstrap_agent` | Returns runtime context (agent_id, port, available features) |
| `list_agents` | Lists all running Synapse agents with status and connection info |

### list_agents

List all running Synapse agents with status and connection info. This is the MCP equivalent of `synapse list --json`.

**Input schema:**

| Parameter | Type | Required | Description |
|-----------|------|:--------:|-------------|
| `status` | string | No | Filter by agent status (`READY`, `PROCESSING`, `WAITING`, `DONE`, etc.) |

**Example call:**

```json
{
  "name": "list_agents",
  "arguments": {
    "status": "READY"
  }
}
```

**Response:**

```json
{
  "agents": [
    {
      "agent_id": "synapse-claude-8100",
      "agent_type": "claude",
      "name": "my-claude",
      "role": "code reviewer",
      "skill_set": null,
      "port": 8100,
      "status": "READY",
      "pid": 12345,
      "working_dir": "/path/to/project",
      "endpoint": "http://localhost:8100",
      "transport": "-",
      "current_task_preview": null,
      "task_received_at": null
    }
  ]
}
```

**Response fields:**

| Field | Type | Description |
|-------|------|-------------|
| `agent_id` | string | Runtime agent identifier (e.g., `synapse-claude-8100`) |
| `agent_type` | string | Agent profile type (`claude`, `gemini`, `codex`, etc.) |
| `name` | string | Custom agent name (if assigned) |
| `role` | string | Agent role description |
| `skill_set` | string | Active skill set (if any) |
| `port` | integer | HTTP server port |
| `status` | string | Current status (`READY`, `PROCESSING`, `WAITING`, `DONE`, etc.) |
| `pid` | integer | Process ID |
| `working_dir` | string | Agent's working directory |
| `endpoint` | string | HTTP endpoint URL |
| `transport` | string | Transport display value (`UDS→`, `TCP→`, or `-`) |
| `current_task_preview` | string\|null | Preview of the current task (if processing) |
| `task_received_at` | number\|null | Unix epoch timestamp when the current task was received |

---

## Canvas Admin API

The Canvas server exposes admin endpoints for the [Agent Control](../guide/canvas.md#agent-control-view-admin) browser view. These endpoints run on the Canvas port (default `3000`), not on individual agent ports.

| Method | Endpoint | Description |
|:------:|----------|-------------|
| GET | `/api/admin/agents` | List active agents from registry |
| POST | `/api/admin/send` | Send a message to an agent via A2A protocol (includes `sender_endpoint`) |
| POST | `/tasks/send` | Receive agent replies via A2A callback (`synapse reply`) |
| GET | `/api/admin/replies/{task_id}` | Poll for agent replies by task ID |
| GET | `/api/admin/tasks/{task_id}?target=` | Fallback: proxy task status to target agent |
| POST | `/api/admin/start` | Start the administrator agent |
| POST | `/api/admin/stop` | Stop the administrator agent |
| POST | `/api/admin/jump/{agent_id}` | Jump to the agent's terminal (tmux, VS Code, Ghostty, iTerm2, Terminal.app) |
| POST | `/api/admin/agents/spawn` | Spawn a new agent from a profile |
| DELETE | `/api/admin/agents/{agent_id}` | Stop an agent by ID |

### List Admin Agents

```bash
curl http://localhost:3000/api/admin/agents
```

**Response:**

```json
{
  "agents": [
    {
      "agent_id": "synapse-claude-8100",
      "name": "Gojo",
      "agent_type": "claude",
      "status": "READY",
      "port": 8100,
      "endpoint": "http://localhost:8100"
    }
  ]
}
```

### Send Message to Agent

```bash
curl -X POST http://localhost:3000/api/admin/send \
  -H "Content-Type: application/json" \
  -d '{"target": "synapse-claude-8100", "message": "What files are in the project?"}'
```

The `target` field accepts an agent ID, agent name, or agent type (if unique). The message is forwarded via the A2A protocol with `response_mode=notify` and includes `sender_endpoint` metadata so the agent can reply back to Canvas.

**Response:**

```json
{
  "task_id": "task-abc123",
  "status": "submitted"
}
```

### Poll for Agent Reply

After sending a message, poll for the agent's reply. The agent responds via `synapse reply`, which sends a structured response back to Canvas's `POST /tasks/send` endpoint. The reply is stored in memory and made available here.

If the receiver hits a quota or limit error before it can produce a reply, the task is marked failed instead of returning a normal reply body.

```bash
curl "http://localhost:3000/api/admin/replies/task-abc123"
```

**Response (waiting):**

```json
{
  "task_id": "task-abc123",
  "status": "waiting",
  "output": ""
}
```

**Response (completed):**

```json
{
  "task_id": "task-abc123",
  "status": "completed",
  "output": "The project contains the following files..."
}
```

Replies are clean, structured text from the agent (no terminal junk since they bypass PTY output). Replies are also broadcast as `admin_reply` SSE events to connected Canvas clients.

### Poll Task Status (Fallback)

Fallback endpoint that proxies a task status request directly to the target agent. Used when the reply-based mechanism is not available (e.g., agent does not support `synapse reply`).

```bash
curl "http://localhost:3000/api/admin/tasks/task-abc123?target=synapse-claude-8100"
```

**Response:**

```json
{
  "task_id": "task-abc123",
  "status": "completed",
  "output": "The project contains the following files...",
  "error": null
}
```

### Spawn Agent

```bash
curl -X POST http://localhost:3000/api/admin/agents/spawn \
  -H "Content-Type: application/json" \
  -d '{"profile": "claude", "name": "Reviewer", "role": "code-review"}'
```

**Response:**

```json
{
  "status": "started",
  "agent_id": "synapse-claude-8101",
  "pid": 12345,
  "port": 8101
}
```

### Stop Agent

```bash
curl -X DELETE http://localhost:3000/api/admin/agents/synapse-claude-8101
```

**Response:**

```json
{
  "status": "stopped",
  "agent_id": "synapse-claude-8101",
  "pid": 12345
}
```

### Jump to Agent Terminal

Switch focus to the terminal pane running the specified agent. Supports tmux, VS Code, Ghostty, iTerm2, and Terminal.app. In the Agent Control view, double-clicking an agent row triggers this action.

```bash
curl -X POST http://localhost:3000/api/admin/jump/synapse-claude-8100
```

**Response (success):**

```json
{
  "ok": true
}
```

**Response (failure):**

```json
{
  "ok": false,
  "error": "terminal=tmux, tty=/dev/ttys003, pid=12345"
}
```

---

## Database Browser API

The Canvas server exposes read-only endpoints for browsing Synapse SQLite databases in the project's `.synapse/` directory. These power the [Database View](../guide/canvas.md#database-view-database).

| Method | Endpoint | Description |
|:------:|----------|-------------|
| GET | `/api/db/list` | List all SQLite databases with table names and file sizes |
| GET | `/api/db/{db_name}/{table_name}` | Query rows from a table (read-only, paginated) |

### GET /api/db/list -- List Databases

Returns all `.db` files in `.synapse/` (excluding internal databases like `task_board.db`). Each entry includes the database name, absolute path, table list, and file size in bytes.

```bash
curl http://localhost:3000/api/db/list
```

**Response:**

```json
[
  {
    "name": "file_safety.db",
    "path": "/path/to/.synapse/file_safety.db",
    "tables": ["file_locks", "file_history"],
    "size": 32768
  }
]
```

### GET /api/db/{db_name}/{table_name} -- Query Table

Returns paginated rows from a table. All access is read-only (`?mode=ro` SQLite URI). Table names are validated against `^[a-zA-Z_][a-zA-Z0-9_]*$` to prevent SQL injection.

```bash
curl "http://localhost:3000/api/db/file_safety.db/file_locks?limit=50&offset=0"
```

**Query parameters:**

| Parameter | Default | Description |
|-----------|---------|-------------|
| `limit` | 100 | Maximum rows to return |
| `offset` | 0 | Row offset for pagination |

**Response:**

```json
{
  "columns": ["id", "file", "agent", "locked_at"],
  "rows": [{"id": 1, "file": "src/main.py", "agent": "claude", "locked_at": "2026-03-29T10:00:00"}],
  "total": 1,
  "limit": 100,
  "offset": 0
}
```

---

## Workflow API

The Canvas server exposes workflow management endpoints for the [Workflow View](../guide/canvas.md#workflow-view-workflow). These endpoints run on the Canvas port (default `3000`).

| Method | Endpoint | Description |
|:------:|----------|-------------|
| GET | `/api/workflow` | List all workflows with steps |
| GET | `/api/workflow/{name}` | Get single workflow detail |
| POST | `/api/workflow/run/{name}` | Start async workflow execution |
| GET | `/api/workflow/runs` | List active and recent runs |
| GET | `/api/workflow/runs/{run_id}` | Get individual run status |

### GET /api/workflow -- List Workflows

Returns all available workflows with their step definitions. The response includes a `project_dir` field indicating the project directory used for workflow resolution.

```bash
curl http://localhost:3000/api/workflow
```

**Response fields:**

| Field | Type | Description |
|-------|------|-------------|
| `workflows` | array | List of workflow objects |
| `project_dir` | string | Absolute path to the project directory used for workflow discovery |

### GET /api/workflow/{name} -- Workflow Detail

Returns a single workflow by name, including its full step list and metadata.

```bash
curl http://localhost:3000/api/workflow/deploy-pipeline
```

### POST /api/workflow/run/{name} -- Run Workflow

Start async background execution of a workflow. Steps are executed sequentially and progress is broadcast via SSE `workflow_update` events.

Canvas sends each workflow step directly to the target agent's A2A endpoint with sender metadata:

- `sender_id: "canvas-workflow"`
- `sender_name: "Workflow"`
- `sender_endpoint: "http://localhost:<canvas-port>"`
- `sender_task_id: "<uuid>"` for reply correlation

This allows the target agent to use `synapse reply` and route the response back to Canvas instead of to whichever shell launched the Canvas server.

```bash
curl -X POST http://localhost:3000/api/workflow/run/deploy-pipeline
```

**Response:**

```json
{
  "run_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "workflow": "deploy-pipeline",
  "status": "running"
}
```

### GET /api/workflow/runs -- List Runs

Returns active and recent workflow runs (up to 50 most recent, stored in server memory).

```bash
curl http://localhost:3000/api/workflow/runs
```

### GET /api/workflow/runs/{run_id} -- Run Status

Returns the status of an individual workflow run, including per-step progress.

```bash
curl http://localhost:3000/api/workflow/runs/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

---

## Wiki API

The Canvas server exposes wiki endpoints for the [Knowledge View](../guide/canvas.md). These endpoints run on the Canvas port (default `3000`) and are available when `wiki.enabled` is `true` in settings.

| Method | Endpoint | Description |
|:------:|----------|-------------|
| GET | `/api/wiki` | List all wiki pages with parsed frontmatter |
| GET | `/api/wiki/enabled` | Check if the wiki feature is enabled |
| GET | `/api/wiki/{scope}/pages/{page}` | Get a single wiki page content |
| GET | `/api/wiki/stats` | Get wiki statistics |
| GET | `/api/wiki/graph` | Get page link graph as Mermaid source |

### GET /api/wiki -- List Pages

Returns all wiki pages with parsed frontmatter metadata.

```bash
curl "http://localhost:3000/api/wiki?scope=project"
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `scope` | `project` | `project` or `global` |

**Response fields (per page):**

| Field | Type | Description |
|-------|------|-------------|
| `filename` | string | Markdown filename |
| `slug` | string | Filename without extension |
| `type` | string | Page type (`entity`, `concept`, `decision`, `comparison`, `synthesis`, `learning`) |
| `title` | string | Page title from frontmatter |
| `created` | string | Creation date |
| `updated` | string | Last update date |
| `confidence` | string/number | Confidence level |
| `author` | string | Author agent ID |
| `summary` | string | First non-heading line (up to 200 chars) |
| `link_count` | number | Number of `[[wikilink]]` references |
| `source_count` | number | Number of sources |

### GET /api/wiki/enabled -- Check Enabled

```bash
curl http://localhost:3000/api/wiki/enabled
```

**Response:**

```json
{ "enabled": true }
```

### GET /api/wiki/{scope}/pages/{page} -- Get Page

Returns a single wiki page with full content and parsed frontmatter.

```bash
curl http://localhost:3000/api/wiki/project/pages/entity-controller
```

**Response fields:**

| Field | Type | Description |
|-------|------|-------------|
| `slug` | string | Page slug |
| `filename` | string | Markdown filename |
| `type` | string | Page type |
| `title` | string | Page title |
| `body` | string | Markdown content (without frontmatter) |
| `links` | array | List of `[[wikilink]]` targets found in body |
| `sources` | array | Source references from frontmatter |

### GET /api/wiki/stats -- Statistics

Returns wiki statistics including page count, source count, and recent activity.

```bash
curl "http://localhost:3000/api/wiki/stats?scope=project"
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `scope` | `project` | `project` or `global` |

**Response fields:**

| Field | Type | Description |
|-------|------|-------------|
| `scope` | string | Requested scope |
| `exists` | boolean | Whether the wiki directory exists |
| `page_count` | number | Total pages |
| `source_count` | number | Total source files |
| `last_updated` | string | ISO 8601 timestamp of most recently modified page |
| `recent_activity` | array | Last 10 log entries (timestamp, operation, detail) |

### GET /api/wiki/graph -- Link Graph

Returns a Mermaid graph representing `[[wikilink]]` connections between wiki pages.

```bash
curl "http://localhost:3000/api/wiki/graph?scope=project"
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `scope` | `project` | `project` or `global` |

**Response:**

```json
{
  "scope": "project",
  "mermaid": "graph LR\n  entity-controller --> concept-file-locking\n  entity-server --> entity-controller",
  "node_count": 3,
  "edge_count": 2
}
```

The `mermaid` field contains valid Mermaid graph source that can be rendered directly in the Canvas Knowledge view.

---

## Error Responses

All endpoints use standard HTTP status codes with JSON error details.

| Status | Cause | Solution |
|:------:|-------|----------|
| 401 | Missing or invalid API key | Provide a valid `X-API-Key` header |
| 403 | Admin privileges required | Use the Admin Key |
| 404 | Agent/task/memory not found | Check with `synapse list` |
| 409 | Ambiguous target or conflict | Use name, full ID, or type-port format |
| 503 | Agent initializing or feature disabled | Wait and retry (automatic) |
| 500 | Internal server error | Check agent logs at `~/.synapse/logs/` |
