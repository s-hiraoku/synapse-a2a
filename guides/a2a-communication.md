# A2A Communication Guide

エージェント間通信（A2A: Agent-to-Agent）の設定と使い方のガイドです。

## 概要

Synapse A2A では、2つの方法でエージェント間通信ができます：

1. **@agent パターン（ユーザー用）** - PTY での対話的入力
2. **a2a.py send コマンド（AIエージェント用）** - 明示的なフラグ制御

通信の応答動作は `a2a.flow` 設定で制御します。

---

## @agent パターン（ユーザー用）

PTY でユーザーが他のエージェントにメッセージを送信する際に使用します。

### 基本構文

```text
@<agent_name> <message>
@<agent_type>-<port> <message>
```

### 例

```text
@gemini このコードをレビューして
@claude-8101 このタスクを処理して
@codex テストを書いて
```

### ターゲット解決

1. **完全ID一致**: `@synapse-claude-8100` で正確にマッチ
2. **タイプ-ポート短縮**: `@claude-8100` でタイプとポートでマッチ
3. **タイプマッチ（単一）**: `@claude` で該当タイプが1つの場合にマッチ
4. **タイプマッチ（複数）**: 複数ある場合は `@type-port` 形式を使うよう提案

---

## synapse send コマンド（推奨）

AIエージェントが他のエージェントにメッセージを送信する際に使用します。
サンドボックス環境でも動作します。

### 基本構文

```bash
synapse send <AGENT> "<MESSAGE>" [--from <SENDER>] [--priority <1-5>] [--response | --no-response] [--reply-to <TASK_ID>]
```

### パラメータ

| パラメータ | 説明 |
|-----------|------|
| `target` | エージェントID（例: `synapse-claude-8100`）またはタイプ（例: `claude`） |
| `--from, -f` | 送信元エージェントID（返信先特定用） |
| `--priority, -p` | 優先度 1-4 通常、5 = 緊急割り込み（SIGINT送信） |
| `--response` | Roundtripモード - 送信側が待機、**受信側は `--reply-to` で返信必須** |
| `--no-response` | Onewayモード - 送りっぱなし、返信不要（デフォルト） |
| `--reply-to` | 特定のタスクIDへの返信として紐付け（`--response` への返信時に使用） |

### 例

```bash
# 通常のメッセージ送信
synapse send gemini "分析結果を教えて" --from claude

# 転送のみ（fire-and-forget）
synapse send codex "テストを実行して" --from claude

# 緊急割り込み（Priority 5）
synapse send codex "STOP" --priority 5 --from claude

# 応答を待つ（roundtrip）
synapse send gemini "分析して" --response --from claude

# --response リクエストへの返信（task_idは [A2A:task_id:sender] から取得）
synapse send claude "分析結果です..." --reply-to abc123 --from gemini
```

**重要:** `--from` オプションで送信元を指定してください。`--response` への返信時は `--reply-to <task_id>` を使用して返信を紐付けます。

---

## A2A メッセージの受信と返信

AIエージェントとしてA2Aメッセージを受信した場合の返信方法です。

### 受信メッセージの形式

```text
[A2A:<task_id>:<sender_id>] <message>
```

### 返信のルール

返信方法は送信側が `--response` を使用したかどうかで異なります：

- 送信側が `--response` を使用 → 送信側が待機中 → `--reply-to <task_id>` を使用
- 送信側が `--response` を不使用 → 送信側は待機していない → `--reply-to` を使用しない

しかし、受信側は送信側が `--response` を使用したかどうかを知ることができません。

**そのため、以下のフォールバック戦略を推奨します：**

1. まず `--reply-to` を付けて返信を試みる
2. 失敗した場合は `--reply-to` なしで再試行する

```bash
# まず --reply-to を付けて試す
synapse send <sender_type> "<your reply>" --reply-to <task_id> --from <your_agent_type>

# 失敗した場合は --reply-to なしで再試行
synapse send <sender_type> "<your reply>" --from <your_agent_type>
```

### 受信・返信の例

受信メッセージ：
```text
[A2A:abc12345:synapse-claude-8100] このコードをレビューして
```

返信：
```bash
synapse send claude "レビュー結果です..." --reply-to abc12345 --from gemini
```

### いつ --response を使うか

**--response を使う場合：**
- 結果が必要で続きの作業に使う
- 質問をして答えが必要
- タスク完了を確認したい
- ユーザーへの報告に結果を統合する

**--response を使わない場合（デフォルト）：**
- バックグラウンドで実行するタスク
- 別の手段で結果を受け取る
- 並列で複数タスクを委譲する

---

## A2A Flow 設定

`.synapse/settings.json` で通信の応答動作を制御できます。

### 設定値

| 設定値 | 動作 |
|--------|------|
| `roundtrip` | 常に結果を待つ（フラグは無視） |
| `oneway` | 常に転送のみ（フラグは無視） |
| `auto` | AIエージェントがフラグで制御（デフォルト） |

### 設定例

```json
{
  "a2a": {
    "flow": "auto"
  }
}
```

### Flow 設定とフラグの組み合わせ

| `a2a.flow` | フラグなし | `--response` |
|------------|-----------|------------|
| `roundtrip` | 待つ | 待つ |
| `oneway` | 待たない | 待たない（上書き） |
| `auto` | 待たない（デフォルト） | 待つ |

> **Note**: `roundtrip` と `oneway` は設定値が優先され、フラグは無視されます。`auto` ではAIエージェントが `--response` フラグで明示的に制御します。

---

## Priority レベル

| Priority | 動作 | 用途 |
|----------|------|------|
| 1-4 | 通常の stdin 書き込み | 通常メッセージ |
| 5 | SIGINT 送信後に書き込み | 緊急停止 |

### Priority 5 の動作

1. 対象エージェントに SIGINT を送信
2. 短時間待機
3. メッセージを送信

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

## ユースケース

### 結果を統合して報告

```bash
synapse send codex "ファイルを修正して" --response --from claude
```

結果を待ち、完了後に統合して報告できます。

### 並列タスク実行

```bash
synapse send gemini "APIドキュメントを調査して" --from claude
synapse send codex "テストを書いて" --from claude
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
