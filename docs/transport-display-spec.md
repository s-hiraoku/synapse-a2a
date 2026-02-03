# Transport Display Specification

## Overview

`synapse list` の表示で、エージェント間通信が発生している間の通信方式（UDS または TCP）をリアルタイム表示する機能の仕様。TRANSPORT 列は `list.columns` 設定に含まれる場合のみ表示されます（デフォルトで有効）。

## Requirements

1. **列設定で表示制御** - `list.columns` に TRANSPORT が含まれる場合のみ表示（デフォルトで表示）
2. **送信側に表示** - `UDS→` または `TCP→` 形式で表示
3. **受信側に表示** - `→UDS` または `→TCP` 形式で表示
4. **通信完了後はクリア** - 通信が終了したら `-` に戻る（短時間の保持表示あり）

## Display Format

### List Output

```
Synapse A2A v0.2.11 - Agent List
Last updated: 2024-01-15 10:30:45

ID                     NAME    STATUS       CURRENT         TRANSPORT   WORKING_DIR   EDITING_FILE
synapse-claude-8100     -       PROCESSING   Sending...      UDS→        project       -
synapse-gemini-8110     -       PROCESSING   Receiving...    →UDS        other         -
synapse-codex-8120      -       READY        -               -           third         -
```

> 表示列は `list.columns` で制御されます。`EDITING_FILE` は File Safety 有効時のみ表示されます。

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
  → list UI reads and displays

Communication Complete
  → Clear sender registry: "active_transport": null
  → Clear receiver registry: "active_transport": null
  → list UI may show the last value briefly (retention)
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

- TRANSPORT は `list.columns` 設定で表示可否を制御
- デフォルト列に TRANSPORT を含む（`synapse/settings.py` の `DEFAULT_SETTINGS`）
- 列幅は 10 文字（Rich renderer の column 定義）

## Usage

```bash
# Start agents
synapse claude  # Terminal 1
synapse gemini  # Terminal 2

# List UI (auto-updates on changes)
synapse list  # Terminal 3

# Send message from Claude to Gemini (Terminal 1)
@gemini hello

# Observe in Terminal 3:
# - Claude shows "UDS→" (sending)
# - Gemini shows "→UDS" (receiving)
# - Both return to "-" after completion (short retention)
```

## Notes

- `synapse list` はファイルウォッチャーで自動更新され、10 秒間隔のフォールバックポーリングがあります
- 通信完了後は `active_transport` がクリアされますが、表示は最大 3 秒保持されます
- If UDS is unavailable, TCP fallback is used automatically, displaying `TCP→`/`→TCP`
- TRANSPORT を非表示にしたい場合は `list.columns` から外します
