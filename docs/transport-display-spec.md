# Transport Display Specification

## Overview

`synapse list --watch` モードで、エージェント間通信が発生している間、使用中の通信方式（UDS または TCP）をリアルタイム表示する機能の仕様。

## Requirements

1. **watch モードでのみ表示** - 通常の `synapse list` では TRANSPORT 列を表示しない
2. **送信側に表示** - `UDS→` または `TCP→` 形式で表示
3. **受信側に表示** - `→UDS` または `→TCP` 形式で表示
4. **通信完了後はクリア** - 通信が終了したら `-` に戻る

## Display Format

### Watch Mode Output

```
Synapse A2A v0.2.11 - Agent List (refreshing every 2s)
Last updated: 2024-01-15 10:30:45

TYPE       PORT     STATUS       TRANSPORT   PID      WORKING_DIR              ENDPOINT
claude     8100     PROCESSING   UDS→       12345    /home/user/project       http://localhost:8100
gemini     8110     PROCESSING   →UDS       12346    /home/user/other         http://localhost:8110
codex      8120     READY        -           12347    /home/user/third         http://localhost:8120
```

### Transport Values

| Value | Meaning |
|-------|---------|
| `UDS→` | Agent is sending via Unix Domain Socket |
| `TCP→` | Agent is sending via TCP/HTTP |
| `→UDS` | Agent is receiving via Unix Domain Socket |
| `→TCP` | Agent is receiving via TCP/HTTP |
| `-` | No active communication |

## Data Flow

```
Communication Start
  → Update sender registry: "active_transport": "UDS→"
  → Update receiver registry: "active_transport": "→UDS"
  → Watch mode reads and displays

Communication Complete
  → Clear sender registry: "active_transport": null
  → Clear receiver registry: "active_transport": null
```

## Registry JSON Changes

### Sender (e.g., Claude sending to Gemini)
```json
{
  "agent_id": "synapse-claude-8100",
  "agent_type": "claude",
  "port": 8100,
  "status": "PROCESSING",
  "active_transport": "UDS→",
  "pid": 12345,
  "working_dir": "/home/user/project",
  "endpoint": "http://localhost:8100",
  "uds_path": "/tmp/synapse-a2a/synapse-claude-8100.sock"
}
```

### Receiver (e.g., Gemini receiving from Claude)
```json
{
  "agent_id": "synapse-gemini-8110",
  "agent_type": "gemini",
  "port": 8110,
  "status": "PROCESSING",
  "active_transport": "→UDS",
  "pid": 12346,
  "working_dir": "/home/user/other",
  "endpoint": "http://localhost:8110",
  "uds_path": "/tmp/synapse-a2a/synapse-gemini-8110.sock"
}
```

## Implementation Details

### New Registry Method

```python
def update_transport(self, agent_id: str, transport: str | None) -> bool:
    """
    Update the active transport method for an agent.

    Args:
        agent_id: The agent identifier
        transport: Transport string (e.g., "UDS→", "→UDS", "TCP→", "→TCP")
                   or None to clear

    Returns:
        True if updated successfully
    """
```

### A2A Client Changes

The `send_to_local` method receives additional parameters:
- `registry`: AgentRegistry instance for updating transport status
- `sender_agent_id`: ID of the sending agent
- `target_agent_id`: ID of the receiving agent

Transport is updated:
1. Before communication: Set sender to `UDS→`/`TCP→`, receiver to `→UDS`/`→TCP`
2. After communication (in finally block): Clear both to `None`

### List Command Changes

- `_render_agent_table` receives `is_watch_mode` parameter
- TRANSPORT column is only rendered when `is_watch_mode=True`
- Column width: 10 characters

## Usage

```bash
# Start agents
synapse claude  # Terminal 1
synapse gemini  # Terminal 2

# Watch mode with fast refresh
synapse list -w -i 0.5  # Terminal 3

# Send message from Claude to Gemini (Terminal 1)
@gemini hello

# Observe in Terminal 3:
# - Claude shows "UDS→" (sending)
# - Gemini shows "→UDS" (receiving)
# - Both return to "-" after completion
```

## Notes

- Communication typically completes within seconds, so use short refresh intervals (`-i 0.5`) for better observation
- If UDS is unavailable, TCP fallback is used automatically, displaying `TCP→`/`→TCP`
- The TRANSPORT column is intentionally hidden in non-watch mode to keep output concise
