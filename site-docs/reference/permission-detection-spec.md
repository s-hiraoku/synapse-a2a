# Permission Detection Spec

spawn/team start で呼び出したエージェントが権限確認で止まった場合に、呼び出し元が status で気づき承認/拒否できる仕組み。現在は parent-side Approval Gate が structured escalation metadata を受け取り、自動 approve/deny/escalate を判断できる。

## 背景

### 問題

エージェントを `--no-auto-approve` で spawn した場合、ワーカーが権限確認ダイアログを出すと PTY がブロックされ、ワーカー自身はメッセージを送れない。呼び出し元は `--notify` でタスク完了を待っているが、現在の `--notify` は `READY`/`DONE` でしか通知しないため、ワーカーが止まっていることに気づけない。

### ゴール

1. ワーカーが権限確認で止まったとき、呼び出し元エージェントに `input_required` 通知を自動送信する
2. 通知には「何で止まっているか」（PTY コンテキスト）を含める
3. 呼び出し元が API で承認/拒否できる
4. ユーザーは status 表示（Canvas / `synapse list`）で気づける
5. `synapse send --wait` は `input_required` を終端失敗とみなさず、親の介入後に最終状態まで待ち続ける

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
    |    permission_escalation:             |
    |    {task_id, child_endpoint, ...}     |
    |                                      |
    |-- Approval Gate: decide/apply ------->|
    |    approve / deny / escalate          |
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
    "_reply_status": "input_required",
    "permission_escalation": {
      "task_id": "task-123",
      "child_endpoint": "http://localhost:8101",
      "child_agent_id": "synapse-claude-8101",
      "child_agent_type": "claude",
      "permission": {
        "pty_context": "Allow Bash: rm -rf /tmp/test? [Y/n]"
      }
    }
  }
}
```

親サーバーはこの `permission_escalation` を受け取ると Approval Gate に渡し、ポリシーに従って `approve` / `deny` / `escalate` を選ぶ。Gate が失敗した場合でも、従来どおり artifact テキストを見て人手で対応できる。

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
- `auto-approve` 無効時（`--no-auto-approve`）: WAITING が持続し、`_on_status_change` が `input_required` 通知を呼び出し元に送信する。親は Approval Gate で自動応答するか、人手で approve/deny API を叩く。`synapse send --wait` はこの介入を待ってから完了/失敗を返す

## 通知の sanitisation と dedupe (#582 / #586, v0.26.4)

`_build_permission_metadata` は `pty_context` を以下の手順で組み立てる:

1. **sanitisation** — `synapse/_pty_sanitize.py` の `strip_control_bytes` で ANSI / CSI / OSC / C0 / C1 制御バイト（8-bit CSI `\x9b...` / OSC `\x9d...` および末尾の途中切れ含む）を除去。TAB/LF は保持、CR は除去。
2. **fallback chain** — レンダリング後の virtual terminal → 生 `controller.get_context()` → `current_task_preview` → `_sent_message[:200]` → `[permission context unavailable]` プレースホルダ。各候補も sanitise した上で `_PERMISSION_CONTEXT_MIN_PRINTABLE` 閾値で「実質的に空」を判定する。
3. **dedupe** — `_on_status_change` の WAITING 分岐は `(task_id + pty_context)` を sha256 16桁 でハッシュし、`task.metadata.permission` に `hash + send timestamp + count` を保持する。`_PERMISSION_NOTIFICATION_MIN_INTERVAL_SECONDS` (5 秒) 以内の再送信は抑止し、ハッシュが変化していてもこの最小間隔は維持される。ウィンドウ満了後に同じハッシュが再観測されれば 1 度だけ再送信する。

これにより、controller が WAITING/READY を高頻度に振動した場合でも親は同一通知の連投を受けず、PTY が壊れたバッファを長文ファイルとしてディスクに書き出すこともない。

## 検出される approval overlay (Codex, #529, v0.26.4)

`synapse/profiles/codex.yaml` の `waiting_detection.regex` は以下の Codex CLI 系 overlay 系統をカバーする:

- 旧来の inline approval プロンプト
- permissions overlay
- host allow/block overlay
- patch-files overlay
- `No, continue without running it` exec オプション

これらが `openai/codex` の `approval_overlay.rs` でラベル変更された場合、READY のまま PTY だけがブロックされる症状が発生していた。検出ラベルは `tests/test_codex_profile.py` で固定し、Codex CLI のリリースに追随する。

## 変更ファイル

| ファイル | 変更内容 |
|---------|---------|
| `synapse/a2a_compat.py` | WAITING→input_required マッピング、structured permission escalation metadata、Approval Gate dispatch |
| `synapse/approval_gate.py` | 親側の approve / deny / escalate ポリシー判定と API dispatch |
| `synapse/tools/a2a.py` | `synapse send --wait` が親の介入後までポーリング継続 |
| `synapse/server.py` | deny_response の配線 |
| `synapse/profiles/*.yaml` | deny_response 追加（全5プロファイル） |
| Synapse instructions | 承認フローの行動指針 |
