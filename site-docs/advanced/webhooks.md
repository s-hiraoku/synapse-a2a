# Webhooks

## Overview

Webhooks enable push notifications for task events. Register a URL to receive HTTP POST callbacks when tasks are completed, failed, created, or canceled. This is the primary integration point for connecting Synapse to CI/CD pipelines, monitoring systems, and external services.

```
Synapse A2A  ── task.completed ──>  Your Server (Webhook URL)
             │
             │  Signature: X-Synapse-Signature (HMAC-SHA256)
             │  Retry: up to 3 attempts with exponential backoff
```

---

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

**Response:**

```json
{
  "id": "wh_abc123",
  "url": "https://example.com/webhook",
  "events": ["task.completed", "task.failed"],
  "active": true,
  "created_at": "2026-02-26T10:30:00Z"
}
```

!!! note "Admin Key Required"
    When authentication is enabled, webhook management endpoints require an Admin API key. See [Authentication](authentication.md) for details.

---

## Authenticated Webhook Management

When `SYNAPSE_AUTH_ENABLED=true`, all webhook management requests must include the Admin key.

### Register

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

### List Webhooks

```bash
curl http://localhost:8100/webhooks \
  -H "X-API-Key: your-admin-key"
```

**Response:**

```json
[
  {
    "id": "wh_abc123",
    "url": "https://your-server.com/webhook",
    "events": ["task.completed", "task.failed"],
    "active": true,
    "created_at": "2026-02-26T10:30:00Z"
  }
]
```

### Remove a Webhook

```bash
curl -X DELETE http://localhost:8100/webhooks/wh_abc123 \
  -H "X-API-Key: your-admin-key"
```

---

## Event Types

| Event | Triggered When | Payload Includes |
|-------|---------------|------------------|
| `task.created` | A new task is created via `/tasks/send` | `task_id`, `subject`, `agent_id` |
| `task.completed` | A task finishes successfully | `task_id`, `status`, `artifacts` |
| `task.failed` | A task fails (error detected or timeout) | `task_id`, `status`, `error` |
| `task.canceled` | A task is canceled via `/tasks/{id}/cancel` | `task_id`, `status` |

---

## Payload Format

All webhook deliveries use the same envelope format:

```json
{
  "event": "task.completed",
  "event_id": "a1b2c3d4-5678-90ab-cdef-1234567890ab",
  "timestamp": "2026-02-26T10:30:00+00:00",
  "data": {
    "task_id": "abc-123",
    "agent_id": "synapse-claude-8100",
    "subject": "Code review",
    "status": "completed"
  }
}
```

### Payload Schemas by Event Type

#### `task.created`

| Field | Type | Description |
|-------|------|-------------|
| `event` | `string` | Always `"task.created"` |
| `task_id` | `string` | UUID of the created task |
| `agent_id` | `string` | Runtime ID of the receiving agent |
| `timestamp` | `string` | ISO 8601 timestamp |
| `data.subject` | `string` | Task subject / first message text |
| `data.status` | `string` | Always `"submitted"` |
| `data.sender` | `string` | Agent ID or name of the sender |

#### `task.completed`

| Field | Type | Description |
|-------|------|-------------|
| `event` | `string` | Always `"task.completed"` |
| `task_id` | `string` | UUID of the completed task |
| `agent_id` | `string` | Runtime ID of the agent |
| `timestamp` | `string` | ISO 8601 timestamp |
| `data.subject` | `string` | Task subject |
| `data.status` | `string` | Always `"completed"` |
| `data.artifacts` | `array` | List of output artifacts (code, text, files) |
| `data.duration_ms` | `number` | Task duration in milliseconds |

#### `task.failed`

| Field | Type | Description |
|-------|------|-------------|
| `event` | `string` | Always `"task.failed"` |
| `task_id` | `string` | UUID of the failed task |
| `agent_id` | `string` | Runtime ID of the agent |
| `timestamp` | `string` | ISO 8601 timestamp |
| `data.subject` | `string` | Task subject |
| `data.status` | `string` | Always `"failed"` |
| `data.error.code` | `string` | Error code (e.g., `PERMISSION_DENIED`, `TIMEOUT`) |
| `data.error.message` | `string` | Human-readable error message |

#### `task.canceled`

| Field | Type | Description |
|-------|------|-------------|
| `event` | `string` | Always `"task.canceled"` |
| `task_id` | `string` | UUID of the canceled task |
| `agent_id` | `string` | Runtime ID of the agent |
| `timestamp` | `string` | ISO 8601 timestamp |
| `data.subject` | `string` | Task subject |
| `data.status` | `string` | Always `"canceled"` |

---

## HMAC Signature Verification

When a `secret` is configured, each delivery includes an HMAC-SHA256 signature in the `X-Synapse-Signature` header:

```
X-Synapse-Signature: sha256=<hex-digest>
```

### Verification Examples

=== "Python"

    ```python
    import hmac
    import hashlib

    def verify_signature(payload: bytes, signature: str, secret: str) -> bool:
        """Verify the HMAC-SHA256 signature of a webhook payload."""
        expected = hmac.new(
            secret.encode(), payload, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(f"sha256={expected}", signature)
    ```

=== "JavaScript"

    ```javascript
    const crypto = require("crypto");

    function verifySignature(payload, signature, secret) {
      const expected = crypto
        .createHmac("sha256", secret)
        .update(payload)
        .digest("hex");
      const expectedBuf = Buffer.from(`sha256=${expected}`);
      const signatureBuf = Buffer.from(signature);
      if (expectedBuf.length !== signatureBuf.length) return false;
      return crypto.timingSafeEqual(expectedBuf, signatureBuf);
    }
    ```

!!! warning "Timing-Safe Comparison"
    Always use a constant-time comparison function (e.g., `hmac.compare_digest` in Python, `crypto.timingSafeEqual` in Node.js) to prevent timing attacks.

---

## Flask Receiver Example

A complete Python Flask application that receives and processes Synapse webhook notifications:

```python
from flask import Flask, request, jsonify
import hmac
import hashlib
import logging

app = Flask(__name__)
WEBHOOK_SECRET = "your-webhook-secret"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def verify_signature(payload: bytes, signature: str) -> bool:
    """Verify the HMAC-SHA256 signature."""
    if not signature:
        return False
    expected = hmac.new(
        WEBHOOK_SECRET.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(signature, f"sha256={expected}")


@app.route("/webhook", methods=["POST"])
def handle_webhook():
    # Verify signature
    signature = request.headers.get("X-Synapse-Signature", "")
    payload = request.get_data()

    if not verify_signature(payload, signature):
        logger.warning("Invalid webhook signature")
        return jsonify({"error": "Invalid signature"}), 401

    # Parse event
    event = request.json
    event_type = event.get("event")
    task_id = event.get("task_id")
    agent_id = event.get("agent_id")

    logger.info(f"Received {event_type} for task {task_id} from {agent_id}")

    # Handle by event type
    if event_type == "task.completed":
        artifacts = event.get("data", {}).get("artifacts", [])
        logger.info(f"Task completed with {len(artifacts)} artifact(s)")
        # Process artifacts...

    elif event_type == "task.failed":
        error = event.get("data", {}).get("error", {})
        logger.error(
            f"Task failed: {error.get('code')} - {error.get('message')}"
        )
        # Alert on failure...

    elif event_type == "task.created":
        logger.info(f"New task created: {event.get('data', {}).get('subject')}")

    elif event_type == "task.canceled":
        logger.info(f"Task canceled: {task_id}")

    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
```

!!! tip "Production Deployment"
    For production use, run the Flask app behind a WSGI server like Gunicorn:

    ```bash
    gunicorn -w 4 -b 0.0.0.0:5000 webhook_receiver:app
    ```

---

## Express Receiver Example

A Node.js Express application for receiving webhooks:

```javascript
const express = require("express");
const crypto = require("crypto");

const app = express();
const WEBHOOK_SECRET = "your-webhook-secret";

app.use(express.json({ verify: (req, _res, buf) => { req.rawBody = buf; } }));

function verifySignature(rawBody, signature) {
  if (!signature) return false;
  const expected = crypto
    .createHmac("sha256", WEBHOOK_SECRET)
    .update(rawBody)
    .digest("hex");
  const expectedSig = `sha256=${expected}`;
  return (
    signature.length === expectedSig.length &&
    crypto.timingSafeEqual(Buffer.from(signature), Buffer.from(expectedSig))
  );
}

app.post("/webhook", (req, res) => {
  const signature = req.headers["x-synapse-signature"];

  if (!verifySignature(req.rawBody, signature)) {
    console.warn("Invalid webhook signature");
    return res.status(401).json({ error: "Invalid signature" });
  }

  const { event, task_id, agent_id, data } = req.body;
  console.log(`Received ${event} for task ${task_id} from ${agent_id}`);

  switch (event) {
    case "task.completed":
      console.log(`Completed with ${(data.artifacts || []).length} artifact(s)`);
      break;
    case "task.failed":
      console.error(`Failed: ${data.error?.code} - ${data.error?.message}`);
      break;
    case "task.created":
      console.log(`Created: ${data.subject}`);
      break;
    case "task.canceled":
      console.log(`Canceled: ${task_id}`);
      break;
  }

  res.json({ status: "ok" });
});

app.listen(5000, () => console.log("Webhook receiver listening on :5000"));
```

---

## Delivery History

Track the status of webhook deliveries.

### View Delivery History

```bash
curl http://localhost:8100/webhooks/deliveries
```

### Delivery Record Format

Each delivery attempt is recorded with the following structure:

```json
[
  {
    "id": "del_xyz789",
    "webhook_id": "wh_abc123",
    "event_type": "task.completed",
    "task_id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "success",
    "status_code": 200,
    "attempts": 1,
    "last_error": null,
    "created_at": "2026-02-26T10:30:00Z",
    "completed_at": "2026-02-26T10:30:01Z"
  },
  {
    "id": "del_abc456",
    "webhook_id": "wh_abc123",
    "event_type": "task.failed",
    "task_id": "660f9500-f39c-52e5-b827-557766551111",
    "status": "failed",
    "status_code": 0,
    "attempts": 3,
    "last_error": "Connection refused",
    "created_at": "2026-02-26T11:00:00Z",
    "completed_at": "2026-02-26T11:05:30Z"
  }
]
```

### Delivery Status Values

| Status | Description |
|--------|-------------|
| `success` | Delivery completed with 2xx response |
| `failed` | All retry attempts exhausted |
| `pending` | Delivery in progress or queued for retry |

---

## Retry Behavior

Failed deliveries are retried with exponential backoff:

| Attempt | Delay | Cumulative |
|:-------:|:-----:|:----------:|
| 1 | Immediate | 0s |
| 2 | 1 second | 1s |
| 3 | 2 seconds | 3s |

!!! note "Retry Conditions"
    Retries are triggered when:

    - The target server returns a 5xx status code
    - The connection times out
    - The connection is refused

    A 4xx response (e.g., 400, 401, 404) is **not** retried, as it indicates a client-side issue.

### Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `SYNAPSE_WEBHOOK_TIMEOUT` | `10` | Delivery timeout in seconds |
| `SYNAPSE_WEBHOOK_MAX_RETRIES` | `3` | Maximum retry attempts |
| `SYNAPSE_WEBHOOK_SECRET` | — | Global webhook secret (used when per-webhook secret is not set) |

---

## Best Practices

!!! tip "Respond Quickly"
    Your webhook endpoint should respond with a `200 OK` within the timeout period (default: 10 seconds). Process the event asynchronously if needed:

    ```python
    @app.route("/webhook", methods=["POST"])
    def handle_webhook():
        event = request.json
        # Queue for async processing
        task_queue.enqueue(process_event, event)
        return "OK", 200
    ```

!!! tip "Idempotency"
    Webhook deliveries may be duplicated due to retries. Use the `task_id` field to deduplicate events in your handler.

!!! warning "Secure Your Endpoint"
    - Always verify the HMAC signature before processing events
    - Use HTTPS for your webhook URL
    - Restrict inbound traffic to known Synapse IP ranges if possible
