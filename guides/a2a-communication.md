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
synapse send <AGENT> "<MESSAGE>" [--from <SENDER>] [--priority <1-5>] [--response | --no-response] [--callback "<COMMAND>"]
```

### パラメータ

| パラメータ | 説明 |
|-----------|------|
| `target` | エージェント名（例: `my-claude`）、ID（例: `synapse-claude-8100`）またはタイプ（例: `claude`） |
| `--from, -f` | 送信元エージェントID（省略可: `SYNAPSE_AGENT_ID` から自動検出） |
| `--priority, -p` | 優先度 1-4 通常、5 = 緊急割り込み（SIGINT送信） |
| `--response` | Roundtripモード - 送信側が待機、**受信側は `synapse reply` で返信** |
| `--no-response` | Onewayモード - 送りっぱなし、返信不要 |
| `--callback` | タスク完了時（completed/failed）に送信側で実行するシェルコマンド（--no-response 時のみ有効） |
| `--force` | 作業ディレクトリの不一致チェックをバイパスして送信 |

**作業ディレクトリチェック**: 送信元の CWD とターゲットの `working_dir` が異なる場合、警告を表示して終了コード 1 で終了します。`--force` でバイパスできます。

### 例

```bash
# 通常のメッセージ送信（--from は自動検出）
synapse send gemini "分析結果を教えて"

# 転送のみ（fire-and-forget）
synapse send codex "テストを実行して" --no-response

# 緊急割り込み（Priority 5）
synapse send codex "STOP" --priority 5

# 応答を待つ（roundtrip）
synapse send gemini "分析して" --response

# 作業ディレクトリが異なるエージェントに強制送信
synapse send codex "テストして" --force

# 明示指定（サンドボックス環境向け）
synapse send gemini "分析して" --from synapse-claude-8100
```

**送信元の自動検出:** `--from` は省略可能です。Synapse は `SYNAPSE_AGENT_ID` 環境変数（起動時に自動設定）から送信元を検出し、次にプロセス祖先のマッチングにフォールバックします。サンドボックス環境（Codex など）では明示的に `--from` を指定してください。

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
synapse broadcast "全員、現状を報告して"                        # --from 自動検出（自身を除外）
synapse broadcast "緊急レビュー依頼" -p 4 --response
synapse broadcast "FYI: 先に進めてください" --no-response
```

---

## A2A メッセージの受信と返信

AIエージェントとしてA2Aメッセージを受信した場合の返信方法です。

### 受信メッセージの形式

メッセージは `A2A:` プレフィックス付きで届きます。送信元の識別情報が含まれる場合があります：

```text
A2A: [From: NAME (SENDER_ID)] [REPLY EXPECTED] <message content>
```

- **From**: 送信元の名前（カスタム名）とエージェントIDが表示されます。
- **REPLY EXPECTED**: 送信側が応答を待機している（ブロッキング）ことを示します。

識別情報が不完全な場合のフォールバック：
- `A2A: [From: SENDER_ID] <message content>`
- `A2A: <message content>` (旧形式)

### 返信方法

`synapse reply` コマンドを使用して返信します：

```bash
synapse reply "<your reply>"
```

**返信追跡の永続化**: Synapseは返信先（`in_reply_to`）の情報を `~/.a2a/reply/` ディレクトリに永続化します。エージェントが再起動しても、最後に受信したメッセージへの返信が可能です。

### 受信・返信の例

**例1: 質問を受信した場合**

受信メッセージ：
```text
A2A: このコードをレビューして
```

返信：
```bash
synapse reply "レビュー結果です..."
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

メッセージの内容を分析し、返信が必要かどうかを判断してください：
- 返信が期待される、または返信があると有益 → `--response`
- 純粋な通知で返信不要 → `--no-response`
- **迷った場合は `--response`**（安全なデフォルト）
- **重要:** 「報告して」「教えて」「ステータスは？」など結果を期待する表現がある場合 → `--response`

| メッセージ種類 | フラグ | 例 |
|---------------|--------|-----|
| 質問 | `--response` | "現在のステータスは？" |
| 分析依頼 | `--response` | "このコードをレビューして" |
| 結果を期待するタスク | `--response` | "テストを実行して結果を報告して" |
| 委任タスク（fire-and-forget） | `--no-response` | "このバグを修正してコミットして" |
| 通知 | `--no-response` | "FYI: ビルドが完了しました" |

**--response を使う場合：**
- 結果が必要で続きの作業に使う
- 質問をして答えが必要
- タスク完了を確認したい
- ユーザーへの報告に結果を統合する

**--no-response を使う場合：**
- バックグラウンドで実行するタスク（結果は git log 等で確認）
- 別の手段で結果を受け取る
- 並列で複数タスクを委譲し、結果をポーリングで確認する

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

> **Note**: Priority 5 は Readiness Gate をバイパスします。エージェント初期化中でも緊急メッセージを配信できます。

---

## ユースケース

### 結果を統合して報告

```bash
synapse send codex "ファイルを修正して" --response
```

結果を待ち、完了後に統合して報告できます。

### 並列タスク実行

```bash
synapse send gemini "APIドキュメントを調査して"
synapse send codex "テストを書いて"
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

3. **HTTP 503 が返る場合**: エージェントが初期化中（identity instruction 送信完了前）です。Readiness Gate により、初期化が完了するまで `/tasks/send` と `/tasks/send-priority` は 503 を返します。`Retry-After: 5` ヘッダーに従い再試行してください。Priority 5（緊急割り込み）と返信メッセージ（`in_reply_to`）はゲートをバイパスします。

### タイムアウトする

- 対象エージェントが PROCESSING 状態で応答できない可能性
- Priority 5 で緊急停止を送信してリセット

---

## 関連ドキュメント

- [settings.md](settings.md) - 設定ファイルの詳細
- [usage.md](usage.md) - 使い方詳細
