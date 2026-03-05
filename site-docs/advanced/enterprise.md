# Enterprise Features

## Overview

Synapse A2A includes enterprise-ready features for production deployments: API authentication, webhook notifications, SSE streaming, output analysis, gRPC support, and comprehensive security controls.

| Feature | Description | Use Case |
|---------|-------------|----------|
| **API Key Auth** | Endpoint access control | Production security |
| **Webhook Notifications** | Push notifications on task events | CI/CD integration, monitoring |
| **SSE Streaming** | Real-time output delivery | Output monitoring, progress tracking |
| **Output Analysis** | Error detection and artifact generation | Automated error handling, structured output |
| **gRPC** | High-performance binary protocol | High-throughput, low-latency requirements |

---

## API Key Authentication

Secure all endpoints with API key authentication.

### Quick Setup

```bash
# Generate keys and display setup instructions
synapse auth setup

# Generate multiple keys in export format
synapse auth generate-key -n 3 -e
```

### Enable Authentication

```bash
export SYNAPSE_AUTH_ENABLED=true
export SYNAPSE_API_KEYS="key1,key2,key3"
export SYNAPSE_ADMIN_KEY="admin-key"
```

### Making Authenticated Requests

=== "curl (Header)"

    ```bash
    curl -H "X-API-Key: my-secret-key-1" \
      http://localhost:8100/tasks
    ```

=== "curl (Query Parameter)"

    ```bash
    curl "http://localhost:8100/tasks?api_key=my-secret-key-1"
    ```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SYNAPSE_AUTH_ENABLED` | Enable authentication | `false` |
| `SYNAPSE_API_KEYS` | Valid API keys (comma-separated) | — |
| `SYNAPSE_ADMIN_KEY` | Admin API key | — |
| `SYNAPSE_ALLOW_LOCALHOST` | Allow localhost access without auth | `true` |

### Key Types

| Key Type | Scope | Example Endpoints |
|----------|-------|-------------------|
| **API Key** | Task operations | `POST /tasks/send`, `GET /tasks/{id}` |
| **Admin Key** | All operations including webhook management | `POST /webhooks`, `DELETE /webhooks/{id}` |

### Protected Endpoints

| Endpoint | Required Auth |
|----------|---------------|
| `POST /tasks/send` | API Key |
| `GET /tasks/{id}` | API Key |
| `GET /tasks` | API Key |
| `POST /tasks/{id}/cancel` | API Key |
| `GET /tasks/{id}/subscribe` | API Key |
| `POST /tasks/send-priority` | API Key |
| `POST /webhooks` | Admin Key |
| `DELETE /webhooks/{id}` | Admin Key |

See [Authentication](authentication.md) for full details.

---

## Webhook Notifications

Push event notifications to external systems.

```bash
curl -X POST http://localhost:8100/webhooks \
  -d '{"url": "https://monitoring.internal/hook", "events": ["task.completed"]}'
```

Features:

- Event filtering (task.completed, task.failed, etc.)
- HMAC-SHA256 signature verification
- Exponential backoff retry (3 attempts)
- Delivery tracking and history

See [Webhooks](webhooks.md) for full details.

---

## SSE Streaming

Subscribe to real-time task updates via Server-Sent Events. SSE eliminates polling overhead and enables efficient monitoring of long-running agent tasks.

```
Client  ─── GET /tasks/{id}/subscribe ──>  Synapse A2A
        <── SSE events (output, status, done)
```

### Subscribing to a Task

```bash
# Submit a task and capture the ID
TASK_ID=$(curl -s -X POST http://localhost:8100/tasks/send \
  -H "Content-Type: application/json" \
  -d '{"message": {"role": "user", "parts": [{"type": "text", "text": "Hello"}]}}' \
  | jq -r '.task.id')

# Subscribe to real-time updates
curl -N http://localhost:8100/tasks/${TASK_ID}/subscribe
```

### SSE Event Types

| Event | Description | Payload |
|-------|-------------|---------|
| `output` | New CLI output line | `{"type": "output", "data": "..."}` |
| `status` | Status transition | `{"type": "status", "status": "working"}` |
| `done` | Task finished | `{"type": "done", "status": "completed", "artifacts": [...]}` |

### Event Stream Example

```text
data: {"type": "output", "data": "Processing request..."}

data: {"type": "status", "status": "working"}

data: {"type": "output", "data": "Generated file: main.py"}

data: {"type": "done", "status": "completed", "artifacts": [{"type": "text", "data": {...}}]}
```

### Client Examples

=== "JavaScript"

    ```javascript
    const taskId = "550e8400-e29b-41d4-a716-446655440000";
    const eventSource = new EventSource(
      `http://localhost:8100/tasks/${taskId}/subscribe`
    );

    eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data);

      switch (data.type) {
        case "output":
          console.log("Output:", data.data);
          break;
        case "status":
          console.log("Status changed:", data.status);
          break;
        case "done":
          console.log("Task completed:", data.status);
          if (data.error) {
            console.error("Error:", data.error);
          }
          eventSource.close();
          break;
      }
    };

    eventSource.onerror = (error) => {
      console.error("SSE connection error:", error);
      // Implement reconnection logic
      setTimeout(() => {
        // Re-create EventSource to reconnect
      }, 5000);
    };
    ```

=== "Python"

    ```python
    import httpx
    import json

    task_id = "550e8400-e29b-41d4-a716-446655440000"

    with httpx.Client() as client:
        with client.stream(
            "GET",
            f"http://localhost:8100/tasks/{task_id}/subscribe",
        ) as response:
            for line in response.iter_lines():
                if line.startswith("data: "):
                    event = json.loads(line[6:])

                    if event["type"] == "output":
                        print(f"Output: {event['data']}")
                    elif event["type"] == "status":
                        print(f"Status: {event['status']}")
                    elif event["type"] == "done":
                        print(f"Done: {event['status']}")
                        break
    ```

=== "Python (with reconnect)"

    ```python
    import httpx
    import json
    import time

    def subscribe_with_reconnect(
        task_id: str,
        base_url: str = "http://localhost:8100",
        max_retries: int = 5,
    ):
        """Subscribe to SSE events with automatic reconnection."""
        retries = 0
        while retries < max_retries:
            try:
                with httpx.Client(timeout=None) as client:
                    url = f"{base_url}/tasks/{task_id}/subscribe"
                    with client.stream("GET", url) as response:
                        retries = 0  # Reset on successful connection
                        for line in response.iter_lines():
                            if not line.startswith("data: "):
                                continue
                            event = json.loads(line[6:])
                            yield event
                            if event["type"] == "done":
                                return
            except (httpx.ConnectError, httpx.ReadTimeout):
                retries += 1
                wait = min(2 ** retries, 30)
                print(f"Connection lost. Retrying in {wait}s...")
                time.sleep(wait)
    ```

### Authenticated SSE

When authentication is enabled, include the API key:

```bash
curl -N -H "X-API-Key: your-key" \
  http://localhost:8100/tasks/${TASK_ID}/subscribe
```

!!! note "Browser EventSource Limitation"
    The standard `EventSource` API does not support custom headers. Use a query parameter instead:

    ```javascript
    const eventSource = new EventSource(
      `http://localhost:8100/tasks/${taskId}/subscribe?api_key=your-key`
    );
    ```

    For production use, consider a library like `eventsource` (Node.js) or `fetch`-based SSE to send proper headers.

---

## Output Analysis

Synapse automatically analyzes CLI output to detect errors, identify interactive prompts, and extract structured artifacts.

### Capabilities

| Capability | Description | Use Case |
|------------|-------------|----------|
| **Error detection** | Recognize error patterns from PTY output | Automatic error handling |
| **input_required detection** | Detect interactive prompts and questions | Interactive task management |
| **Output parser** | Convert output to structured artifacts | Code block and file reference extraction |

### Error Detection

CLI output is scanned for error patterns, and tasks are automatically transitioned to `failed` status when errors are detected.

#### Detected Error Patterns

| Category | Example Patterns | Error Code |
|----------|-----------------|------------|
| System errors | `command not found`, `permission denied` | `COMMAND_NOT_FOUND`, `PERMISSION_DENIED` |
| Network | `connection refused`, `timeout` | `CONNECTION_REFUSED`, `TIMEOUT` |
| API errors | `rate limit`, `unauthorized` | `RATE_LIMITED`, `AUTH_ERROR` |
| AI refusal | `I cannot`, `I'm unable to` | `AGENT_REFUSED` |
| Generic errors | `error:`, `failed:`, `exception:` | `CLI_ERROR`, `EXECUTION_FAILED` |

#### Error Response Example

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "failed",
  "error": {
    "code": "PERMISSION_DENIED",
    "message": "Permission denied",
    "data": {
      "context": "...cannot write to /etc/hosts: permission denied...",
      "pattern": "permission denied"
    }
  }
}
```

!!! tip "Receive Error Notifications via Webhook"
    Subscribe to `task.failed` events to get immediate notifications when errors occur:

    ```bash
    curl -X POST http://localhost:8100/webhooks \
      -H "Content-Type: application/json" \
      -d '{
        "url": "https://your-server.com/errors",
        "events": ["task.failed"],
        "secret": "your-secret"
      }'
    ```

### input_required Detection

Synapse detects when a CLI agent is waiting for user input and transitions the task to `input_required` status.

**Detected patterns include:**

- Questions ending with `?`
- Confirmation prompts (`[y/n]`, `[yes/no]`)
- Input requests (`Enter ...:`)
- Waiting messages (`waiting for input`, `press enter`)

#### Status Flow

```
working ──[question pattern detected]──> input_required
input_required ──[additional input received]──> working
working ──[normal completion]──> completed
working ──[error detected]──> failed
```

#### Responding to input_required Tasks

```bash
# Send additional input using the same context_id
curl -X POST http://localhost:8100/tasks/send \
  -H "Content-Type: application/json" \
  -d '{
    "context_id": "original-context-id",
    "message": {
      "role": "user",
      "parts": [{"type": "text", "text": "yes"}]
    }
  }'
```

### Output Parser (Artifact Generation)

CLI output is parsed into structured artifacts for programmatic consumption.

#### Extracted Segment Types

| Type | Description | Metadata |
|------|-------------|----------|
| `code` | Markdown code blocks | `language` |
| `file` | File operation references | `action` (created/modified/deleted) |
| `error` | Error messages | `error_type` |
| `text` | Plain text | — |

#### Example: Input and Output

**Raw CLI output:**

```text
Processing your request...

Created file `main.py`:
```python
def hello():
    print("Hello!")
```

Modified `README.md` with new instructions.
```

**Generated artifacts:**

```json
{
  "artifacts": [
    {
      "index": 0,
      "parts": [{"type": "text", "text": "Processing your request..."}]
    },
    {
      "index": 1,
      "parts": [{"type": "file", "file": {"path": "main.py", "action": "created"}}]
    },
    {
      "index": 2,
      "parts": [{"type": "code", "code": "def hello():\n    print(\"Hello!\")", "language": "python"}]
    },
    {
      "index": 3,
      "parts": [{"type": "file", "file": {"path": "README.md", "action": "modified"}}]
    }
  ]
}
```

!!! note "Receiving Artifacts via SSE"
    The `done` event includes the generated artifacts:

    ```text
    data: {"type": "done", "status": "completed", "artifacts": [...]}
    ```

### Token Usage Parsing

Synapse includes a token parser registry that extracts token usage and cost information from agent output.

=== "Python"

    ```python
    from synapse.token_parser import parse_tokens

    # Parse token usage from CLI output
    usage = parse_tokens("claude", output_text)
    if usage:
        print(f"Input tokens: {usage.input_tokens}")
        print(f"Output tokens: {usage.output_tokens}")
        print(f"Total cost: ${usage.cost:.4f}")
    ```

=== "CLI"

    ```bash
    # View token statistics for recent tasks
    synapse history stats --agent claude
    ```

---

## gRPC Support

!!! warning "Development Status"
    gRPC support is currently under development. Proto definitions and the server skeleton exist, but full functionality is not yet operational. Track progress at [Issue #22](https://github.com/s-hiraoku/synapse-a2a/issues/22).

### Overview

gRPC provides an HTTP/2-based high-performance RPC framework. It is suitable for scenarios requiring high throughput or low latency.

```
gRPC Client  <── Protocol Buffers / HTTP/2 ──>  Synapse gRPC Server
(any language)                                   Port: REST + 1 (e.g., 8101)
```

### Installation

gRPC is an optional dependency. Install only when needed:

```bash
# uv
uv pip install synapse-a2a[grpc]

# pip
pip install synapse-a2a[grpc]
```

### Service Definition

Protocol Buffers definition (`synapse/proto/a2a.proto`):

```protobuf
service A2AService {
    // Agent discovery
    rpc GetAgentCard(GetAgentCardRequest) returns (GetAgentCardResponse);

    // Task management
    rpc SendMessage(SendMessageRequest) returns (SendMessageResponse);
    rpc GetTask(GetTaskRequest) returns (GetTaskResponse);
    rpc ListTasks(ListTasksRequest) returns (ListTasksResponse);
    rpc CancelTask(CancelTaskRequest) returns (CancelTaskResponse);

    // Streaming (alternative to SSE)
    rpc Subscribe(SubscribeRequest) returns (stream TaskStreamEvent);

    // Priority extension
    rpc SendPriorityMessage(SendPriorityMessageRequest) returns (SendMessageResponse);
}
```

### Message Definitions

```protobuf
message Task {
    string id = 1;
    string context_id = 2;
    string status = 3;  // submitted, working, completed, failed, canceled
    Message message = 4;
    repeated Artifact artifacts = 5;
    TaskError error = 6;
    google.protobuf.Timestamp created_at = 7;
    google.protobuf.Timestamp updated_at = 8;
    google.protobuf.Struct metadata = 9;
}

message Message {
    string role = 1;  // "user" or "agent"
    repeated Part parts = 2;
}

message Part {
    oneof part {
        TextPart text_part = 1;
        FilePart file_part = 2;
    }
}
```

### Client Example

=== "Python"

    ```python
    import grpc
    from synapse.proto import a2a_pb2, a2a_pb2_grpc

    # Create channel (REST port + 1)
    channel = grpc.insecure_channel("localhost:8101")
    stub = a2a_pb2_grpc.A2AServiceStub(channel)

    # Get Agent Card
    response = stub.GetAgentCard(a2a_pb2.GetAgentCardRequest())
    print(f"Agent: {response.agent_card.name}")

    # Send a message
    request = a2a_pb2.SendMessageRequest(
        message=a2a_pb2.Message(
            role="user",
            parts=[
                a2a_pb2.Part(
                    text_part=a2a_pb2.TextPart(
                        type="text",
                        text="Hello from gRPC!",
                    )
                )
            ],
        )
    )
    response = stub.SendMessage(request)
    print(f"Task ID: {response.task.id}")

    # Subscribe to streaming updates
    for event in stub.Subscribe(
        a2a_pb2.SubscribeRequest(task_id=response.task.id)
    ):
        print(f"Event: {event.event_type}")
        if event.event_type == "done":
            break
    ```

### Port Configuration

| Protocol | Port | Notes |
|----------|------|-------|
| REST (HTTP) | 8100 | Main port |
| gRPC | 8101 | REST + 1 |

### REST vs gRPC Comparison

| Aspect | REST | gRPC |
|--------|------|------|
| Protocol | HTTP/1.1 | HTTP/2 |
| Data format | JSON | Protocol Buffers |
| Streaming | SSE (server-only) | Bidirectional |
| Client generation | Manual | Auto-generated (protoc) |
| Browser support | Full | Requires grpc-web |
| Performance | Good | Faster |

!!! tip "When to Use gRPC"
    - **REST** is recommended for most use cases, browser clients, and simple integrations.
    - **gRPC** is recommended for high-performance requirements, polyglot client environments, and bidirectional streaming needs.

---

## Security Best Practices

### Production Checklist

- [x] Enable API authentication (`SYNAPSE_AUTH_ENABLED=true`)
- [x] Use separate keys per agent/service
- [x] Disable localhost bypass in production (`SYNAPSE_ALLOW_LOCALHOST=false`)
- [x] Configure webhook secrets for signature verification
- [x] Rotate API keys regularly
- [x] Monitor webhook delivery logs
- [x] Use HTTPS for external agent connections
- [x] Review and restrict network access

### API Key Management

!!! warning "Key Rotation"
    API keys should be rotated regularly. Follow this procedure to avoid downtime:

```bash
# Step 1: Generate a new key
NEW_KEY=$(synapse auth generate-key)

# Step 2: Add the new key alongside the old one
export SYNAPSE_API_KEYS="old-key,${NEW_KEY}"

# Step 3: Update all clients to use the new key

# Step 4: Remove the old key
export SYNAPSE_API_KEYS="${NEW_KEY}"
```

#### Key Generation Methods

=== "synapse auth (Recommended)"

    ```bash
    # Single key
    synapse auth generate-key
    # Output: synapse_NzwQDYhGm_fqDIxb4h3WDtBu74ABs6pZSaSXwDck9vg

    # Multiple keys
    synapse auth generate-key --count 3

    # Export format (paste into shell config)
    synapse auth generate-key --export
    ```

=== "openssl"

    ```bash
    openssl rand -hex 32
    ```

=== "Python"

    ```python
    from synapse.auth import generate_api_key

    key = generate_api_key()
    print(key)  # "synapse_..." format
    ```

### Network Isolation

```bash
# Local-only (default) -- agents listen on localhost
synapse claude --port 8100

# For production with external access, use a reverse proxy
# nginx/caddy -> synapse (localhost)
```

!!! example "Nginx Reverse Proxy Configuration"

    ```nginx
    upstream synapse_claude {
        server 127.0.0.1:8100;
    }

    server {
        listen 443 ssl;
        server_name agents.example.com;

        ssl_certificate /etc/ssl/certs/agents.pem;
        ssl_certificate_key /etc/ssl/private/agents.key;

        location /claude/ {
            proxy_pass http://synapse_claude/;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

            # SSE support
            proxy_buffering off;
            proxy_cache off;
            proxy_read_timeout 86400s;
        }
    }
    ```

### TLS Configuration

For direct HTTPS without a reverse proxy:

```bash
synapse start claude \
  --ssl-cert /path/to/cert.pem \
  --ssl-key /path/to/key.pem
```

### Audit Logging

```bash
# Enable detailed logging
export SYNAPSE_LOG_LEVEL=DEBUG

# Authentication events are logged via the synapse.auth module
# Check logs at:
tail -f ~/.synapse/logs/*.log
```

!!! tip "Log Aggregation"
    Forward Synapse logs to your centralized logging system (e.g., ELK, Datadog, Splunk) by configuring a log file watcher on `~/.synapse/logs/`.

---

## Deployment Patterns

### Single Machine (Development)

All agents run on one machine with localhost communication. No authentication required.

```bash
# Start multiple agents -- they discover each other automatically
synapse claude
synapse gemini
synapse codex
```

### Multi-Machine (Production)

Agents run on separate machines with authentication and external agent registration.

```bash
# Machine A: Claude manager
export SYNAPSE_AUTH_ENABLED=true
export SYNAPSE_API_KEYS="shared-secret-key"
synapse claude --delegate-mode

# Machine B: Gemini worker
export SYNAPSE_AUTH_ENABLED=true
export SYNAPSE_API_KEYS="shared-secret-key"
synapse gemini

# Register cross-machine agents
synapse external add https://machine-b:8110 --alias remote-gemini
```

!!! note "Network Requirements"
    Ensure the agent ports (8100-8149) are accessible between machines. Use a VPN or private network for security.

### Docker-Based Deployment

=== "docker-compose.yml"

    ```yaml
    version: "3.8"
    services:
      claude-agent:
        image: synapse-a2a:latest
        command: synapse claude --port 8100
        ports:
          - "8100:8100"
        environment:
          - SYNAPSE_AUTH_ENABLED=true
          - SYNAPSE_API_KEYS=${API_KEY}
        volumes:
          - agent-registry:/root/.a2a/registry
          - ./workspace:/workspace
        working_dir: /workspace

      gemini-agent:
        image: synapse-a2a:latest
        command: synapse gemini --port 8110
        ports:
          - "8110:8110"
        environment:
          - SYNAPSE_AUTH_ENABLED=true
          - SYNAPSE_API_KEYS=${API_KEY}
        volumes:
          - agent-registry:/root/.a2a/registry
          - ./workspace:/workspace
        working_dir: /workspace

    volumes:
      agent-registry:
    ```

=== "Dockerfile"

    ```dockerfile
    FROM python:3.12-slim

    WORKDIR /app
    RUN pip install synapse-a2a

    # Create workspace directory
    RUN mkdir -p /workspace

    ENTRYPOINT ["synapse"]
    ```

### CI/CD Integration

```bash
# Start agents in CI pipeline
synapse start claude --port 8100
synapse start gemini --port 8110

# Run coordinated tasks
synapse send claude "Run integration tests" --wait

# Collect results
synapse history export --format json > results.json
```

!!! example "GitHub Actions Example"

    ```yaml
    jobs:
      agent-review:
        runs-on: ubuntu-latest
        steps:
          - uses: actions/checkout@v4
          - name: Install Synapse
            run: pip install synapse-a2a
          - name: Start review agent
            run: |
              synapse start claude --port 8100 &
              sleep 5
          - name: Request code review
            run: |
              synapse send claude "Review the changes in this PR" --wait
          - name: Export results
            run: synapse history export --format json > review.json
          - uses: actions/upload-artifact@v4
            with:
              name: review-results
              path: review.json
    ```

---

## Monitoring and Observability

### Health Checks

Verify agent availability using the agent card endpoint:

```bash
# Check if an agent is healthy
curl -s http://localhost:8100/.well-known/agent.json | jq '.name, .status'

# Check all registered agents
synapse list
```

### Metrics Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /.well-known/agent.json` | Agent card with status |
| `GET /tasks` | List active tasks |
| `GET /webhooks/deliveries` | Webhook delivery history |

### Log Aggregation

All Synapse logs are written to `~/.synapse/logs/`. Key log files:

| Log Source | Content |
|------------|---------|
| Agent logs | PTY output, status transitions, task processing |
| Auth logs | Authentication attempts, key validation |
| Webhook logs | Delivery attempts, retries, failures |

```bash
# Monitor all agent logs in real-time
tail -f ~/.synapse/logs/*.log

# Filter for errors
grep -i "error\|failed\|exception" ~/.synapse/logs/*.log
```

### History and Tracing

Use the built-in history and trace commands for task observability:

```bash
# View recent task history
synapse history list

# Filter by agent
synapse history list --agent claude

# Show detailed task information
synapse history show <task_id>

# Trace a task across history and file modifications
synapse trace <task_id>

# Task statistics
synapse history stats
synapse history stats --agent gemini
```

---

## Troubleshooting

### Authentication Errors

```bash
# 401 Unauthorized -- check the X-API-Key header
curl -v http://localhost:8100/tasks

# Verify the API key is set
echo $SYNAPSE_API_KEYS

# Check if localhost bypass is enabled (development only)
echo $SYNAPSE_ALLOW_LOCALHOST
```

### Webhook Delivery Failures

```bash
# Check delivery history
curl http://localhost:8100/webhooks/deliveries

# Common causes:
# - URL is unreachable
# - Timeout exceeded (default: 10s)
# - Signature verification mismatch
```

### gRPC Connection Errors

```bash
# Verify gRPC is installed
python -c "import grpc; print(grpc.__version__)"

# Check the port (REST + 1)
curl http://localhost:8100/status  # REST on 8100
# gRPC on 8101
```

### SSE Connection Issues

```bash
# Test SSE connectivity
curl -N http://localhost:8100/tasks/<task_id>/subscribe

# Common causes:
# - Task ID does not exist
# - Proxy buffering is enabled (disable proxy_buffering in nginx)
# - Connection timeout (increase proxy_read_timeout)
```

---

## Error Responses

| Status Code | Body | Cause |
|-------------|------|-------|
| `401 Unauthorized` | `{"detail": "API key required"}` | No API key provided |
| `401 Unauthorized` | `{"detail": "Invalid API key"}` | Invalid API key |
| `403 Forbidden` | `{"detail": "Admin privileges required"}` | Non-admin key used for admin endpoint |
| `503 Service Unavailable` | `{"detail": "Agent not ready"}` | Agent still initializing (retry after `Retry-After` header) |
