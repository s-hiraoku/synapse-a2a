# Task Ownership Design

このドキュメントは、`--reply-to`オプションが動作しない問題を解決するための設計変更について説明します。

## 問題概要

### 症状

`synapse send` コマンドで `--response` フラグを使用してメッセージを送信し、受信側が `--reply-to` で返信しようとすると、常に「Task not found」エラーが発生します。

```bash
# Terminal 1: Claude 起動
synapse claude --port 8100

# Terminal 2: Codex 起動
synapse codex --port 8120

# Terminal 3: Claude から Codex にメッセージ送信
synapse send codex "分析して" --response --from claude
# → sender_task_id: abc12345 が生成される

# Codex の PTY に表示:
# [A2A:abc12345:synapse-claude-8100] 分析して

# Codex で返信しようとすると失敗:
synapse send claude "結果です" --reply-to abc12345 --from codex
# Error: Task abc12345 not found  ← 常に失敗！
```

### 根本原因

以前の実装では、`sender_task_id` は `synapse send --response` を実行する **CLIプロセス** のインメモリ `task_store` に作成されていました：

```
問題のあるフロー:

[synapse send --response]
    ↓
プロセス起動
    ↓
task_store.create() → sender_task_id 作成
    ↓
POST /tasks/send-priority to target
    ↓
プロセス終了 → task_store も消滅！ ← 問題点
    ↓
後で --reply-to で参照しても見つからない
```

`synapse send` コマンドは短命なCLIプロセスとして実行されるため、タスクを作成してもプロセス終了とともにメモリから消えてしまいます。

## 解決策

### アプローチ: 送信元エージェントのサーバーにタスクを登録

**新しい設計では、`--response` フラグ使用時に送信元エージェントの長時間稼働サーバーにタスクを作成します。**

```
新しいフロー:

[synapse send codex "msg" --response --from claude]
    ↓
1. POST /tasks/create to Claude's server (localhost:8100)
   → Claude の task_store に sender_task_id が作成される（永続的）
    ↓
2. POST /tasks/send-priority to Codex's server
   → metadata に sender_task_id を含める
    ↓
3. Codex の PTY に表示:
   [A2A:abc12345:synapse-claude-8100] msg
    ↓
4. synapse send claude "reply" --reply-to abc12345 --from codex
    ↓
5. POST /tasks/send to Claude's server
   → metadata に in_reply_to=abc12345 を含める
    ↓
6. Claude のサーバーで task_store.get(abc12345) → 見つかる！
    ↓
7. task_store.add_artifact() + update_status("completed")
    ↓
成功！
```

## 実装詳細

### 1. 新しいエンドポイント: POST /tasks/create

`synapse/a2a_compat.py` に追加:

```python
class CreateTaskRequest(BaseModel):
    """Request to create a task (without sending to PTY)."""
    message: Message
    metadata: dict[str, Any] | None = None

class CreateTaskResponse(BaseModel):
    """Response with created task."""
    task: Task

@router.post("/tasks/create", response_model=CreateTaskResponse)
async def create_task(request: CreateTaskRequest) -> CreateTaskResponse:
    """
    Create a task without sending to PTY.

    Used by --response flag to create a task on the sender's server
    before sending to the target agent.
    """
    task = task_store.create(request.message, metadata=request.metadata)
    task_store.update_status(task.id, "working")
    return CreateTaskResponse(task=task)
```

### 2. send_to_local の更新

`synapse/a2a_client.py` の `send_to_local()` メソッドを更新:

```python
if response_expected:
    sender_endpoint = sender_info.get("sender_endpoint")
    sender_uds_path = sender_info.get("sender_uds_path")

    if sender_endpoint:
        create_payload = {
            "message": asdict(a2a_message),
            "metadata": {
                "response_expected": True,
                "direction": "outgoing",
                "target_endpoint": endpoint,
            },
        }

        # Try UDS first, fallback to HTTP
        if sender_uds_path and Path(sender_uds_path).exists():
            # UDS経由で /tasks/create を呼び出し
            ...
        else:
            # HTTP経由で /tasks/create を呼び出し
            create_url = f"{sender_endpoint}/tasks/create"
            response = requests.post(create_url, json=create_payload)
            sender_task_id = response.json()["task"]["id"]

        metadata["sender_task_id"] = sender_task_id
```

### 3. build_sender_info の更新

`synapse/tools/a2a.py` の `build_sender_info()` を更新して `sender_endpoint` と `sender_uds_path` を含める:

```python
def build_sender_info(explicit_sender: str | None = None) -> dict:
    """
    Build sender info using Registry PID matching.

    Returns dict with sender_id, sender_type, sender_endpoint, sender_uds_path.
    """
    sender_info: dict[str, str] = {}

    if explicit_sender:
        # Look up endpoint and uds_path from registry
        reg = AgentRegistry()
        agents = reg.list_agents()
        if explicit_sender in agents:
            info = agents[explicit_sender]
            sender_info["sender_id"] = explicit_sender
            sender_info["sender_endpoint"] = info.get("endpoint")
            sender_info["sender_uds_path"] = info.get("uds_path")
            return sender_info

    # ... PID matching logic also includes endpoint and uds_path
```

## メタデータ構造

### 送信時 (--response)

```json
{
  "message": {
    "role": "user",
    "parts": [{"type": "text", "text": "分析して"}]
  },
  "metadata": {
    "sender": {
      "sender_id": "synapse-claude-8100",
      "sender_type": "claude",
      "sender_endpoint": "http://localhost:8100",
      "sender_uds_path": "/tmp/synapse-claude-8100.sock"
    },
    "sender_task_id": "abc12345-...",
    "response_expected": true
  }
}
```

### 返信時 (--reply-to)

```json
{
  "message": {
    "role": "agent",
    "parts": [{"type": "text", "text": "結果です"}]
  },
  "metadata": {
    "sender": {
      "sender_id": "synapse-codex-8120"
    },
    "in_reply_to": "abc12345-..."
  }
}
```

## シーケンス図

```
synapse send            Claude Server           Codex Server           synapse send
(--response)            (port 8100)             (port 8120)            (--reply-to)
     |                       |                       |                      |
     |  POST /tasks/create   |                       |                      |
     | --------------------> |                       |                      |
     |                       | task_store.create()   |                      |
     |                       | status="working"      |                      |
     | <-------------------- |                       |                      |
     | sender_task_id        |                       |                      |
     |                       |                       |                      |
     |  POST /tasks/send-priority                    |                      |
     | --------------------------------> ----------> |                      |
     |                       |                       | PTY: [A2A:abc12345:...|
     |                       |                       |                      |
     |                       |                       |                      |
     |                       |                       |  POST /tasks/send    |
     |                       | <-------------------- | <------------------- |
     |                       | in_reply_to=abc12345  |                      |
     |                       |                       |                      |
     |                       | task_store.get()      |                      |
     |                       | → Found!              |                      |
     |                       | add_artifact()        |                      |
     |                       | status="completed"    |                      |
     |                       | --------------------> | ------------------- >|
     |                       |                       |                      | Success!
```

## テスト

```bash
# 新しいテストケース
pytest tests/test_reply_to_task_registration.py -v

# 全テスト
pytest
```

## 関連ファイル

| ファイル | 変更内容 |
|---------|---------|
| `synapse/a2a_compat.py` | `POST /tasks/create` エンドポイント追加 |
| `synapse/a2a_client.py` | 送信元サーバーへの `/tasks/create` 呼び出し |
| `synapse/tools/a2a.py` | `sender_endpoint`, `sender_uds_path` を sender_info に追加 |
| `tests/test_reply_to_task_registration.py` | 新機能のテスト |

## 関連ドキュメント

- [A2A Communication Guide](../guides/a2a-communication.md) - 受信・返信の詳細
- [CLI Command Reference](../guides/references.md) - `synapse send` コマンドリファレンス
