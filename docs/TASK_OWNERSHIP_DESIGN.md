# Task Ownership Design

このドキュメントは、`--reply-to`オプションが同一タイプのエージェント間通信で動作しない問題を解決するために行われた設計変更について説明します。

## 背景

### 問題

`synapse send claude "message" --response --from claude` のように、同一タイプのエージェント間で `--reply-to` を使用した返信ができない問題がありました。

**症状:**
```bash
# Claude (8100) から Claude (8101) にメッセージ送信
synapse send claude-8101 "分析して" --response --from claude

# Claude (8101) が返信しようとすると失敗
synapse send claude "結果です" --reply-to abc12345 --from claude
# Error: Task abc12345 not found
```

### 原因

以前の設計では、タスクは**受信側**で作成されていました：

```
送信側 (Claude 8100)                    受信側 (Claude 8101)
        |                                       |
        |  POST /tasks/send                     |
        | ------------------------------------> |
        |                                       | task = task_store.create()
        |                                       | task_id = "abc12345"
        |                                       |
        |  [A2A:abc12345:claude-8100] message   |
        |                                       | (PTYに表示)
```

返信時に `--reply-to abc12345` を使用すると、送信側（Claude 8100）のタスクストアで `abc12345` を探しますが、このタスクは受信側（Claude 8101）で作成されたため存在しません。

## 新しい設計

### タスク所有権の変更

**新しい設計では、タスクは`--response`フラグ使用時に送信側で作成されます。**

```
送信側 (Claude 8100)                    受信側 (Claude 8101)
        |                                       |
        | task = task_store.create()            |
        | sender_task_id = "abc12345"           |
        |                                       |
        |  POST /tasks/send                     |
        |  metadata.sender_task_id = "abc12345" |
        | ------------------------------------> |
        |                                       | receiver_task = task_store.create()
        |                                       |
        |  [A2A:abc12345:claude-8100] message   |
        |                                       | (PTYに sender_task_id を表示)
        |                                       |
        |  POST /tasks/send?reply_to=abc12345   |
        | <------------------------------------ |
        |                                       |
        | task_store.complete("abc12345", reply)|
        |                                       |
```

### 主な変更点

#### 1. 送信側でのタスク作成 (`synapse/a2a_client.py`)

`--response` フラグが指定された場合、送信前にタスクを作成：

```python
# A2AClient.send_to_local()
if response_expected:
    sender_task = task_store.create(message, metadata={
        "response_expected": True,
        "direction": "outgoing",
        "target_endpoint": endpoint,
    })
    sender_task_id = sender_task.id
    metadata["sender_task_id"] = sender_task_id
```

#### 2. 受信側での表示 (`synapse/a2a_compat.py`)

PTY出力には `sender_task_id` を使用：

```python
# handle_tasks_send()
display_task_id = task.id[:8]  # デフォルトは受信側のタスクID
if request.metadata:
    sender_task_id = request.metadata.get("sender_task_id")
    if sender_task_id:
        display_task_id = sender_task_id[:8]  # 送信側のタスクIDを使用

prefixed_content = format_a2a_message(display_task_id, sender_id, text_content)
```

#### 3. タスクID生成ユーティリティ (`synapse/utils.py`)

```python
def generate_task_id() -> str:
    """Generate a unique task ID for A2A messages."""
    return str(uuid4())[:8]
```

### メタデータ構造

```json
{
  "message": {
    "role": "user",
    "parts": [{"type": "text", "text": "メッセージ内容"}]
  },
  "metadata": {
    "sender": {
      "sender_id": "synapse-claude-8100",
      "sender_type": "claude",
      "sender_endpoint": "http://localhost:8100"
    },
    "sender_task_id": "abc12345",
    "response_expected": true
  }
}
```

## 受信側の返信ルール

受信側は送信側が `--response` を使用したかどうかを知ることができません。そのため、以下のフォールバック戦略を推奨します：

### 推奨される返信方法

```bash
# まず --reply-to を付けて試す
synapse send <sender_type> "<reply>" --reply-to <task_id> --from <your_type>

# 失敗した場合は --reply-to なしで再試行
synapse send <sender_type> "<reply>" --from <your_type>
```

### 例

受信メッセージ：
```
[A2A:abc12345:synapse-claude-8100] このコードをレビューして
```

返信：
```bash
synapse send claude "レビュー結果です..." --reply-to abc12345 --from codex
```

## 関連ファイル

| ファイル | 変更内容 |
|---------|---------|
| `synapse/a2a_client.py` | 送信側でのタスク作成ロジック追加 |
| `synapse/a2a_compat.py` | 受信側で `sender_task_id` を使用してPTY表示 |
| `synapse/utils.py` | `generate_task_id()` 関数追加 |
| `tests/test_task_ownership.py` | タスク所有権のテストケース |

## テスト

```bash
# タスク所有権関連のテスト
pytest tests/test_task_ownership.py -v

# 全テスト
pytest
```

## 関連ドキュメント

- [A2A Communication Guide](../guides/a2a-communication.md) - 受信・返信の詳細
- [CLI Command Reference](../guides/references.md) - `synapse send` コマンドリファレンス
