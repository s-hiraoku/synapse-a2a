# A2A Communication Guide

エージェント間通信（A2A: Agent-to-Agent）の設定と使い方のガイドです。

## 概要

Synapse A2A では、3つの方法でエージェント間通信ができます：

1. **@agent パターン（ユーザー用）** - PTY での対話的入力
2. **synapse send コマンド（AIエージェント用）** - 明示的なフラグ制御
3. **synapse broadcast コマンド（AIエージェント用）** - 同一 working dir への一括送信

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
synapse send <AGENT> "<MESSAGE>" [--from <SENDER>] [--priority <1-5>] [--response | --no-response]
```

### パラメータ

| パラメータ | 説明 |
|-----------|------|
| `target` | エージェントID（例: `synapse-claude-8100`）またはタイプ（例: `claude`） |
| `--from, -f` | 送信元エージェントID（返信先特定用）- **常に指定推奨** |
| `--priority, -p` | 優先度 1-4 通常、5 = 緊急割り込み（SIGINT送信） |
| `--response` | Roundtripモード - 送信側が待機、**受信側は `synapse reply` で返信** |
| `--no-response` | Onewayモード - 送りっぱなし、返信不要 |

### 例

```bash
# 通常のメッセージ送信
synapse send gemini "分析結果を教えて" --from synapse-claude-8100

# 転送のみ（fire-and-forget）
synapse send codex "テストを実行して" --from synapse-claude-8100 --no-response

# 緊急割り込み（Priority 5）
synapse send codex "STOP" --priority 5 --from synapse-claude-8100

# 応答を待つ（roundtrip）
synapse send gemini "分析して" --response --from synapse-claude-8100
```

**重要:** `--from` オプションで送信元を常に指定してください。

---

## synapse broadcast コマンド

現在の作業ディレクトリと一致する全エージェントへ同じメッセージを送信します。

### 基本構文

```bash
synapse broadcast "<MESSAGE>" [--from <SENDER>] [--priority <1-5>] [--response | --no-response]
```

### 動作

- `Path.cwd().resolve()` と各エージェントの `working_dir` 実パスが一致した対象に送信
- `--from` 指定時は送信元自身（`sender_id`）を送信対象から除外
- 一部失敗があっても残りへの送信は継続し、最後に成功/失敗件数を表示

### 例

```bash
synapse broadcast "全員、現状を報告して" --from synapse-claude-8100
synapse broadcast "緊急レビュー依頼" -p 4 --response --from synapse-codex-8120
synapse broadcast "FYI: 先に進めてください" --no-response
```

---

## A2A メッセージの受信と返信

AIエージェントとしてA2Aメッセージを受信した場合の返信方法です。

### 受信メッセージの形式

メッセージは `A2A:` プレフィックス付きのプレーンテキストで届きます：

```text
A2A: <message>
```

### 返信方法

`synapse reply` コマンドを使用して返信します：

```bash
synapse reply "<your reply>" --from <your_agent_id>
```

**返信追跡:** Synapseは`[REPLY EXPECTED]`マーカー付きメッセージの送信者情報を自動的に追跡します。`synapse reply`を使うと、返信を期待しているエージェントに自動的に返信されます。

### 受信・返信の例

**例1: 質問を受信した場合**

受信メッセージ：
```text
A2A: このコードをレビューして
```

返信：
```bash
synapse reply "レビュー結果です..." --from synapse-gemini-8110
```

**例2: タスク委任を受信した場合**

受信メッセージ：
```text
A2A: テストを実行してコミットして
```

アクション：タスクを実行。返信は不要（質問がある場合のみ返信）。

### --response フラグと返信の関係

| 送信側 | 受信側のアクション |
|--------|-------------------|
| `--response` 使用 | **必ず** `synapse reply` で返信 |
| `--no-response` | タスク実行のみ、返信不要 |

### いつ --response を使うか

**--response を使う場合：**
- 結果が必要で続きの作業に使う
- 質問をして答えが必要
- タスク完了を確認したい
- ユーザーへの報告に結果を統合する

**--no-response を使う場合：**
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
| `auto` | フラグで制御（フラグなしは待つ、デフォルト） |

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
| `auto` | 待つ（デフォルト） | 待つ |

> **Note**: `roundtrip` と `oneway` は設定値が優先され、フラグは無視されます。`auto` ではフラグで制御され、フラグなしは待機になります。

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

## ユースケース

### 結果を統合して報告

```bash
synapse send codex "ファイルを修正して" --response --from synapse-claude-8100
```

結果を待ち、完了後に統合して報告できます。

### 並列タスク実行

```bash
synapse send gemini "APIドキュメントを調査して" --from synapse-claude-8100
synapse send codex "テストを書いて" --from synapse-claude-8100
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
- [usage.md](usage.md) - 使い方詳細
