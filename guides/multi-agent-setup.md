# Multi-Agent Setup Guide

このガイドでは、Claude / Codex / Gemini / OpenCode のエージェントを同時に起動し、
相互通信できる状態にするまでを **丁寧に** まとめています。

---

## 全体像

- Synapse は各 CLI を **PTY でラップ**して起動します。
- 起動したエージェントは `~/.a2a/registry/` に登録されます。
- 端末内の `@Agent` 入力や HTTP API を介して相互にメッセージ送信できます。
- 外部の Google A2A 互換エージェントとも連携可能です。

### A2A プロトコル準拠

Synapse のエージェント間通信は **Google A2A プロトコル**に準拠しています:

- `@Agent` 記法は内部で `/tasks/send-priority` エンドポイントを使用
- CLI ツール（`synapse send`）は A2A 形式でメッセージを送信
- Task ベースの非同期通信をサポート
- Agent Card（`/.well-known/agent.json`）による能力公開

---

## 1. 前提条件

### 対応 OS / Python

- macOS / Linux（Windows は WSL2 推奨）
- Python 3.10+

### 必須 CLI ツール

| エージェント | CLI コマンド | 公式リンク |
|------------|-------------|-----------|
| Claude | `claude` | https://claude.ai/code |
| Codex | `codex` | https://github.com/openai/codex |
| Gemini | `gemini` | https://github.com/google/gemini-cli |
| OpenCode | `opencode` | https://github.com/opencode-ai/opencode |
| Copilot | `copilot` | https://docs.github.com/en/copilot/github-copilot-in-the-cli |

---

## 2. インストール

### ユーザー向け（推奨）

**macOS / Linux / WSL2（推奨）:**
```bash
pipx install synapse-a2a
```

**Windows (Scoop, 実験的 — pty のために WSL2 が必要):**
```bash
scoop bucket add synapse-a2a https://github.com/s-hiraoku/scoop-synapse-a2a
scoop install synapse-a2a
```

> Windows ネイティブは `pty.spawn()` の制約により動作しません。WSL2 を使用してください。

### 開発者向け（ソースから）

```bash
uv sync
```

pip の場合は editable install を使用します。

```bash
pip install -e .
```

> `uv sync` を使用した場合は自動的に editable install されます。

---

## 3. 起動（インタラクティブ）

各エージェントを **別ターミナル** で起動します。

```bash
# Terminal 1
synapse claude --port 8100

# Terminal 2
synapse codex --port 8120

# Terminal 3
synapse gemini --port 8110

# Terminal 4
synapse opencode --port 8130

# Terminal 5
synapse copilot --port 8140
```

起動後の挙動:

- 各 CLI は通常通り利用可能
- `@Agent` 入力は A2A メッセージとして送信
- 送信先は `~/.a2a/registry/` に登録されたエージェント

補足:
- `@Agent` は **行単位** で判定されます（Enter で送信）
- 正しく判定されない場合は、先頭から `@agent` で書いているか確認してください

---

## 4. 端末内での A2A 送信

インタラクティブ起動中の端末で、以下のように使います。

```text
@codex この設計をレビューして
@claude "PTY 関連の修正案を出して"
```

**内部動作:**
- `@Agent` 記法は内部で `/tasks/send-priority` エンドポイントを呼び出します
- メッセージは A2A Task として作成され、対象エージェントに配信されます
- Priority パラメータにより、通常メッセージ（1-4）と強制介入（5）を区別します

補足:
- `@Agent` パターンはデフォルトで相手の返信を待ちます
- 返信は相手が `READY` になるのをポーリングして取得します
- 返答が長い/処理が長い場合は、戻りが遅くなることがあります
- レスポンスを待たずに送信したい場合は `synapse send --no-response` を使用してください

---

## 5. 外部から送信（CLI / HTTP）

### CLI で送信

```bash
synapse list
synapse send codex "設計を書いて" --priority 1
```

CLI は内部で A2A 形式のメッセージを送信します（`/tasks/send-priority` エンドポイント）。

### HTTP で送信（A2A 形式）

```bash
# Task ベースでメッセージ送信（推奨）
curl -X POST http://localhost:8120/tasks/send \
  -H "Content-Type: application/json" \
  -d '{"message": {"role": "user", "parts": [{"type": "text", "text": "設計を書いて"}]}}'

# Priority 付きで送信（Synapse 拡張）
curl -X POST "http://localhost:8120/tasks/send-priority?priority=1" \
  -H "Content-Type: application/json" \
  -d '{"message": {"role": "user", "parts": [{"type": "text", "text": "設計を書いて"}]}}'
```

> **注意**: `/message` エンドポイントは非推奨です。新しいコードでは `/tasks/send` または `/tasks/send-priority` を使用してください。

---

## 6. ステータス確認

```bash
curl http://localhost:8100/status
# {"status": "PROCESSING", "context": "..."}
```

- `status` は `READY` / `PROCESSING` を返します
- `context` は直近の出力の一部です

---

## 7. 優先度（Priority）

`/tasks/send-priority` エンドポイントで使用する Priority 値:

| Priority | 動作 | 用途 |
|----------|------|------|
| 1-4 | stdin に書き込み | 通常の通信 |
| 5 | SIGINT を送ってから書き込み | 強制介入 / 停止 |

使用例:

```bash
# 通常のメッセージ（priority=1）
curl -X POST "http://localhost:8100/tasks/send-priority?priority=1" \
  -H "Content-Type: application/json" \
  -d '{"message": {"role": "user", "parts": [{"type": "text", "text": "レビューして"}]}}'

# 強制介入（priority=5）- エージェントの処理を中断
curl -X POST "http://localhost:8100/tasks/send-priority?priority=5" \
  -H "Content-Type: application/json" \
  -d '{"message": {"role": "user", "parts": [{"type": "text", "text": "処理を止めて"}]}}'
```

---

## 8. 外部エージェントとの連携

### 外部エージェントの登録

他のマシンや別サービスで動作している Google A2A 互換エージェントと連携できます。
外部エージェントは `/.well-known/agent.json`（Agent Card）を公開している必要があります。

```bash
# 外部エージェントを発見・登録
synapse external add http://other-server:9000 --alias other

# 登録済みエージェント確認
synapse external list
```

### 外部エージェントへのメッセージ送信

```text
# @Agent 記法（登録した alias を使用）
@other タスクを処理して

# CLI から
synapse external send other "Hello!"
```

### HTTP API

```bash
# 外部エージェントを発見・登録
curl -X POST http://localhost:8100/external/discover \
  -H "Content-Type: application/json" \
  -d '{"url": "http://other-server:9000", "alias": "other"}'

# 外部エージェントにメッセージ送信
curl -X POST http://localhost:8100/external/agents/other/send \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello!", "wait_for_completion": true}'
```

### ユースケース例

外部エージェント連携が有効な場面:

| カテゴリ | エージェント例 | 用途 |
|---------|--------------|------|
| **セキュリティ** | 脆弱性スキャン、依存関係監査 | コード変更時の自動セキュリティチェック |
| **コードレビュー** | 言語/フレームワーク特化 | 専門的な観点でのコード品質向上 |
| **DevOps** | CI/CD 制御、インフラ管理 | デプロイ自動化、K8s 操作 |
| **ナレッジ** | 社内ドキュメント検索 | 仕様・設計情報への即時アクセス |
| **外部サービス** | Jira/Slack 連携 | チケット作成・通知の自動化 |

**パイプライン例:**
```
Claude (設計) → Codex (実装) → Security Agent (監査) → Deploy Agent (リリース)
```

各エージェントが専門領域を担当し、処理を連鎖させることで、複雑なワークフローを自動化できます。

---

## 9. よくある問題

- 端末描画が崩れる / 入力欄が乱れる
- ポートが使われている
- エージェントが見つからない
- 外部エージェントに接続できない

詳しくは `guides/troubleshooting.md` を参照してください。

---

## 10. A2A API エンドポイント一覧

Synapse が提供する主な A2A 互換エンドポイント:

| Method | Endpoint | 説明 |
|--------|----------|------|
| GET | `/.well-known/agent.json` | Agent Card（能力情報） |
| POST | `/tasks/send` | Task 作成・メッセージ送信 |
| POST | `/tasks/send-priority` | Priority 付きメッセージ送信（Synapse 拡張） |
| GET | `/tasks/{task_id}` | Task 状態取得 |
| GET | `/status` | エージェント状態（READY/PROCESSING） |

詳細は [guides/google-a2a-spec.md](google-a2a-spec.md) を参照してください。
