# Port Ranges

## Default Port Assignments

Each agent type has a dedicated port range supporting up to 10 concurrent instances.

| Agent | Port Range | Max Instances |
|-------|:----------:|:---:|
| **Claude Code** | 8100 – 8109 | 10 |
| **Gemini CLI** | 8110 – 8119 | 10 |
| **Codex CLI** | 8120 – 8129 | 10 |
| **OpenCode** | 8130 – 8139 | 10 |
| **Copilot CLI** | 8140 – 8149 | 10 |
| **Dummy (test)** | 8190 – 8199 | 10 |

## Port Auto-Assignment

When you start an agent without specifying a port, Synapse automatically assigns the next available port in the range:

```bash
synapse claude          # Gets 8100 (if available)
synapse claude          # Gets 8101 (next available)
synapse gemini          # Gets 8110
```

## Explicit Port

Override with `--port`:

```bash
synapse claude --port 8105
synapse start gemini --port 8115
```

## Port in Agent ID

The port is embedded in the agent ID:

```
synapse-claude-8100     # Claude on port 8100
synapse-gemini-8110     # Gemini on port 8110
synapse-codex-8121      # Codex on port 8121
```

This enables the type-port shorthand for targeting:

```bash
synapse send claude-8100 "message"
```

## Transport

Synapse supports two transport modes:

| Transport | Protocol | Path |
|-----------|----------|------|
| **UDS** | Unix Domain Socket | `/tmp/synapse-a2a/synapse-{type}-{port}.sock` |
| **TCP** | HTTP over TCP | `http://localhost:{port}` |

UDS is preferred for local communication (lower latency, no port conflicts). TCP is used as fallback.

The `TRANSPORT` column in `synapse list` shows active communication:

```
UDS→    # Sending via UDS
→UDS    # Receiving via UDS
TCP→    # Sending via TCP
→TCP    # Receiving via TCP
-       # No active communication
```
