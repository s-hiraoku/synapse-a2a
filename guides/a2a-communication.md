# A2A Communication Guide

エージェント間通信（A2A: Agent-to-Agent）の設定と使い方のガイドです。

## 概要

Synapse A2A では、`@agent` パターンを使って他のエージェントにメッセージを送信できます。通信の応答動作は `a2a.flow` 設定と `--response`/`--no-response` フラグで制御します。

---

## @agent パターン

### 基本構文

```text
@<agent_name> [--response|--no-response] <message>
@<agent_type>-<port> [--response|--no-response] <message>
```

### 例

```text
@gemini このコードをレビューして
@gemini --response 分析結果を教えて    # 結果を待って受け取る
@gemini --no-response 調査を開始して   # 転送のみ、結果を待たない
@claude-8101 このタスクを処理して
@codex テストを書いて
```

---

## A2A Flow 設定

`.synapse/settings.json` で通信の応答動作を制御できます。

### 設定値

| 設定値 | 動作 |
|--------|------|
| `roundtrip` | 常に結果を待つ |
| `oneway` | 常に転送のみ（結果を待たない） |
| `auto` | メッセージごとにフラグで制御（デフォルト） |

### 設定例

```json
{
  "a2a": {
    "flow": "auto"
  }
}
```

---

## 応答制御フラグ

`@agent` パターンで応答を待つかどうかを個別に制御できます。

| フラグ | 動作 |
|--------|------|
| `--response` | 結果を待って受け取る |
| `--no-response` | 転送のみ（結果を待たない） |
| （フラグなし） | `a2a.flow` 設定に従う |

### Flow 設定との組み合わせ

| `a2a.flow` | フラグなし | `--response` | `--no-response` |
|------------|-----------|--------------|-----------------|
| `roundtrip` | 待つ | 待つ | 待たない |
| `oneway` | 待たない | 待つ | 待たない |
| `auto` | 待つ（デフォルト） | 待つ | 待たない |

---

## ユースケース

### 結果を統合して報告

```text
@codex --response ファイルを修正して
```

結果を待ち、完了後に統合して報告できます。

### 並列タスク実行

```text
@gemini --no-response APIドキュメントを調査して
@codex --no-response テストを書いて
```

複数のタスクを並列で実行し、各エージェントが独立して作業を進めます。

### 設定で一括制御

```json
{
  "a2a": {
    "flow": "roundtrip"
  }
}
```

すべての通信で結果を待つようにして、確実に結果を受け取ります。

---

## Priority レベル

| Priority | 動作 | 用途 |
|----------|------|------|
| 1-4 | 通常の stdin 書き込み | 通常メッセージ |
| 5 | SIGINT 送信後に書き込み | 緊急停止 |

CLI ツールでの Priority 指定：

```bash
python3 synapse/tools/a2a.py send --target gemini --priority 3 "メッセージ"
python3 synapse/tools/a2a.py send --target claude --priority 5 "緊急停止"
```

---

## 送信元識別

A2A メッセージには送信元情報が自動的に付与されます。

### PTY 出力形式

```text
[A2A:<task_id>:<sender_id>] <message>
```

### 例

```text
[A2A:abc12345:synapse-claude-8100] この設計をレビューしてください
```

### metadata 構造

```json
{
  "message": {
    "role": "user",
    "parts": [{"type": "text", "text": "メッセージ"}]
  },
  "metadata": {
    "sender": {
      "sender_id": "synapse-claude-8100",
      "sender_type": "claude",
      "sender_endpoint": "http://localhost:8100"
    },
    "response_expected": true
  }
}
```

---

## トラブルシューティング

### 応答が返ってこない

1. `a2a.flow` 設定を確認（`oneway` だと結果を待たない）
2. `--response` フラグを明示的に使用
3. 対象エージェントの状態を確認:
   ```bash
   synapse list
   ```

### メッセージが届かない

1. エージェントが起動しているか確認:
   ```bash
   synapse list
   ```

2. ポートが開いているか確認:
   ```bash
   curl http://localhost:8100/status
   ```

### タイムアウトする

- 対象エージェントが PROCESSING 状態で応答できない可能性
- Priority 5 で緊急停止を送信してリセット

---

## 関連ドキュメント

- [settings.md](settings.md) - 設定ファイルの詳細
- [delegation.md](delegation.md) - 自動タスク委任
- [usage.md](usage.md) - 使い方詳細
