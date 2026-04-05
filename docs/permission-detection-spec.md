# Permission Detection Spec

spawn/team start で呼び出したエージェントが権限確認で止まった場合に、呼び出し元が status で気づき承認/拒否できる仕組み。

## 背景

### 問題

エージェントを `--no-auto-approve` で spawn した場合、ワーカーが権限確認ダイアログを出すと PTY がブロックされ、ワーカー自身はメッセージを送れない。呼び出し元は `--notify` でタスク完了を待っているが、現在の `--notify` は `READY`/`DONE` でしか通知しないため、ワーカーが止まっていることに気づけない。

### ゴール

1. ワーカーが権限確認で止まったとき、呼び出し元エージェントに `input_required` 通知を自動送信する
2. 通知には「何で止まっているか」（PTY コンテキスト）を含める
3. 呼び出し元が API で承認/拒否できる
4. ユーザーは status 表示（Canvas / `synapse list`）で気づける

## アーキテクチャ

```
呼び出し元エージェント                    ワーカー (spawn)
    |                                      |
    |-- synapse send worker "task" --notify -->|
    |                                      |
    |                                      |-- PTY: ツール実行
    |                                      |-- PTY: "Allow Bash: rm -rf? [Y/n]"
    |                                      |-- controller: WAITING 検知
    |                                      |-- FastAPI: _on_status_change(WAITING)
    |                                      |
    |<-- input_required 通知 (自動) -------|  (FastAPI が HTTP で送信)
    |    permission.pty_context:            |
    |    "Allow Bash: rm -rf? [Y/n]"       |
    |                                      |
    |-- 判断: 安全 → approve API ---------->|
    |    POST /tasks/{id}/permission/approve|
    |                                      |-- controller.write("y\r")
    |                                      |-- PTY: 承認 -> 実行再開
    |                                      |
    |<-- completed 通知 (既存) ------------|
```

### ワーカーの構成

```
synapse start claude --port 8101

  [PTY プロセス]  Claude Code CLI   <- 権限確認で止まる（ブロック）
  [FastAPI]       port 8101          <- 止まらない。status 監視 + 通知送信
  [controller]    status monitor     <- daemon スレッドで PTY 出力を監視
```

PTY がブロックされても FastAPI サーバーと controller の daemon スレッドは動き続ける。`_on_status_change` コールバックが WAITING を検知し、HTTP で呼び出し元に通知する。

## API

### タスク状態マッピング

| Synapse status | A2A TaskState |
|----------------|---------------|
| STARTING | submitted |
| PROCESSING | working |
| **WAITING** | **input_required** |
| READY | completed |
| DONE | completed |

### GET /tasks/{task_id}

WAITING 状態のとき、`metadata.permission` フィールドが付与される:

```json
{
  "id": "task-123",
  "status": "input_required",
  "metadata": {
    "permission": {
      "pty_context": "Allow Bash: rm -rf /tmp/test? [Y/n]",
      "agent_type": "claude",
      "detected_at": 1712345678.9
    },
    "sender": { "..." }
  }
}
```

### POST /tasks/{task_id}/permission/approve

権限確認を承認する。プロファイルの `auto_approve.runtime_response` を PTY に送信。

```
POST /tasks/{task_id}/permission/approve
Content-Type: application/json

Response: {"status": "approved", "task_id": "task-123"}
```

### POST /tasks/{task_id}/permission/deny

権限確認を拒否する。プロファイルの `auto_approve.deny_response` を PTY に送信。

```
POST /tasks/{task_id}/permission/deny
Content-Type: application/json

Response: {"status": "denied", "task_id": "task-123"}
```

## 通知フォーマット

`_on_status_change` で WAITING を検知したとき、`--notify`/`--wait` の呼び出し元に送信されるメッセージ:

```json
{
  "message": {
    "role": "agent",
    "parts": [
      {
        "type": "text",
        "text": "[Task task-123] Status: input_required\nPermission context: Allow Bash: rm -rf /tmp/test? [Y/n]\nApprove: POST http://localhost:8101/tasks/task-123/permission/approve\nDeny: POST http://localhost:8101/tasks/task-123/permission/deny"
      }
    ]
  },
  "metadata": {
    "sender": { "sender_id": "synapse-claude-8101" },
    "response_mode": "silent",
    "in_reply_to": "sender-task-id",
    "_reply_status": "input_required"
  }
}
```

## プロファイル設定

各プロファイルの `auto_approve` セクションに `deny_response` を追加:

| Profile | runtime_response (承認) | deny_response (拒否) |
|---------|------------------------|---------------------|
| Claude | `"y\r"` | `"n\r"` |
| Codex | `"y\r"` | `"\x1b"` (Esc) |
| Gemini | `"\r"` | `"\x1b"` (Esc) |
| OpenCode | `"a\r"` | `"d\r"` |
| Copilot | `"1\r"` | `"\x1b"` (Esc) |

## エージェント行動指針

Synapse instructions に追記する承認フロー:

```
PERMISSION HANDLING - When Spawned Agents Need Approval:
  When you receive an input_required notification from an agent you spawned:
  1. Read the permission context to understand what tool/action is requested
  2. Evaluate: is this expected for the task you delegated?
  3. If safe: POST /tasks/{task_id}/permission/approve to the agent's endpoint
  4. If unsafe: POST /tasks/{task_id}/permission/deny
  5. If unsure: Ask the user
```

## auto-approve との関係

- `auto-approve` 有効時: controller が直接 PTY に承認を送信。`_on_status_change` は発火するが、WAITING 状態が短時間で解消されるため `input_required` 通知は実質的に送られない（WAITING → PROCESSING が高速に遷移）
- `auto-approve` 無効時（`--no-auto-approve`）: WAITING が持続し、`_on_status_change` が `input_required` 通知を呼び出し元に送信。呼び出し元が approve/deny API で応答するまで待機

## 変更ファイル

| ファイル | 変更内容 |
|---------|---------|
| `synapse/a2a_compat.py` | WAITING→input_required マッピング、_on_status_change 拡張、permission metadata、approve/deny API |
| `synapse/server.py` | deny_response の配線 |
| `synapse/profiles/*.yaml` | deny_response 追加（全5プロファイル） |
| Synapse instructions | 承認フローの行動指針 |
