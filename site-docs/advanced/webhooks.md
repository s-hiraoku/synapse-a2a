# Webhooks

## Overview

Webhooks enable push notifications for task events. Register a URL to receive HTTP POST callbacks when tasks are completed, failed, or updated.

## Register a Webhook

```bash
curl -X POST http://localhost:8100/webhooks \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com/webhook",
    "events": ["task.completed", "task.failed"],
    "secret": "my-webhook-secret"
  }'
```

## List Webhooks

```bash
curl http://localhost:8100/webhooks
```

## Remove a Webhook

```bash
curl -X DELETE "http://localhost:8100/webhooks?url=https://example.com/webhook"
```

## View Delivery History

```bash
curl http://localhost:8100/webhooks/deliveries
```

## Event Types

| Event | Triggered When |
|-------|---------------|
| `task.completed` | A task finishes successfully |
| `task.failed` | A task fails |
| `task.created` | A new task is created |
| `task.canceled` | A task is canceled |

## Payload Format

```json
{
  "event": "task.completed",
  "task_id": "abc-123",
  "agent_id": "synapse-claude-8100",
  "timestamp": "2026-02-26T10:30:00Z",
  "data": {
    "subject": "Code review",
    "status": "completed"
  }
}
```

## HMAC Signature Verification

When a `secret` is configured, each delivery includes an HMAC-SHA256 signature:

```
X-Synapse-Signature: sha256=<hex-digest>
```

Verify in your handler:

```python
import hmac
import hashlib

def verify_signature(payload: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(
        secret.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)
```

## Retry Behavior

Failed deliveries are retried with exponential backoff:

| Attempt | Delay |
|:-------:|:-----:|
| 1 | Immediate |
| 2 | 30 seconds |
| 3 | 5 minutes |

Configuration:

| Variable | Default | Description |
|----------|---------|-------------|
| `SYNAPSE_WEBHOOK_TIMEOUT` | 10s | Delivery timeout |
| `SYNAPSE_WEBHOOK_MAX_RETRIES` | 3 | Max retry count |
| `SYNAPSE_WEBHOOK_SECRET` | — | Global webhook secret |
