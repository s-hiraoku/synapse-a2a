# Enterprise Features

## Overview

Synapse A2A includes enterprise-ready features for production deployments: API authentication, webhook notifications, SSE streaming, output analysis, and gRPC support.

## API Key Authentication

Secure all endpoints with API key authentication.

```bash
# Setup
synapse auth setup

# Generate keys
synapse auth generate-key -n 3 -e
```

```bash
# Enable
export SYNAPSE_AUTH_ENABLED=true
export SYNAPSE_API_KEYS="key1,key2,key3"
export SYNAPSE_ADMIN_KEY="admin-key"
```

See [Authentication](authentication.md) for full details.

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

## SSE Streaming

Subscribe to real-time task updates via Server-Sent Events:

```bash
curl -N http://localhost:8100/tasks/<task_id>/subscribe
```

## Output Analysis

Synapse can detect patterns in agent output:

- **Error detection**: Recognize error patterns from PTY output
- **Completion signals**: Detect when tasks finish
- **input_required**: Detect interactive prompts

## gRPC Support

Protocol Buffers definitions for gRPC communication:

```protobuf
service SynapseAgent {
  rpc SendTask (TaskRequest) returns (TaskResponse);
  rpc GetTaskStatus (TaskId) returns (TaskStatus);
  rpc SubscribeUpdates (TaskId) returns (stream TaskUpdate);
}
```

## Security Checklist

- [ ] Enable API authentication (`SYNAPSE_AUTH_ENABLED=true`)
- [ ] Use separate keys per agent/service
- [ ] Disable localhost bypass in production (`SYNAPSE_ALLOW_LOCALHOST=false`)
- [ ] Configure webhook secrets for signature verification
- [ ] Rotate API keys regularly
- [ ] Monitor webhook delivery logs
- [ ] Use HTTPS for external agent connections
- [ ] Review and restrict network access

## Deployment Patterns

### Single Machine (Development)

```bash
# All agents on one machine, localhost communication
synapse claude
synapse gemini
synapse codex
```

### Multi-Machine (Production)

```bash
# Machine A: Claude manager
SYNAPSE_AUTH_ENABLED=true synapse claude --delegate-mode

# Machine B: Gemini worker
SYNAPSE_AUTH_ENABLED=true synapse gemini

# Register cross-machine agents
synapse external add https://machine-b:8110 --alias remote-gemini
```

### CI/CD Integration

```bash
# Start agents in CI pipeline
synapse start claude --port 8100
synapse start gemini --port 8110

# Run coordinated tasks
synapse send claude "Run integration tests" --response

# Collect results
synapse history export --format json > results.json
```
