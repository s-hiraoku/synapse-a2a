# Synapse A2A ドキュメント

このディレクトリには、Synapse A2A の設計・運用・トラブルシューティングに関する詳細ドキュメントをまとめています。

---

## ドキュメント構成

```mermaid
flowchart TD
    README["README.md<br/>このファイル"]

    subgraph Getting_Started["入門"]
        Setup["multi-agent-setup.md<br/>セットアップガイド"]
        Usage["usage.md<br/>使い方詳細"]
    end

    subgraph Configuration["設定"]
        Profiles["profiles.md<br/>プロファイル設定"]
    end

    subgraph Technical["技術詳細"]
        Arch["architecture.md<br/>アーキテクチャ"]
        Refs["references.md<br/>API/CLI リファレンス"]
    end

    subgraph External["外部連携"]
        Google["google-a2a-spec.md<br/>Google A2A 互換性"]
    end

    subgraph Support["サポート"]
        Trouble["troubleshooting.md<br/>トラブルシューティング"]
    end

    README --> Getting_Started
    README --> Configuration
    README --> Technical
    README --> External
    README --> Support
```

---

## 1. 入門ガイド

### [multi-agent-setup.md](multi-agent-setup.md)
**マルチエージェントセットアップガイド**

- 前提条件（OS、Python、CLI ツール）
- インストール手順
- 複数エージェントの起動方法
- @Agent 記法の基本的な使い方
- 外部からの API/CLI 操作

> 初めての方はこちらから始めてください

### [usage.md](usage.md)
**使い方詳細**

- インタラクティブモードとバックグラウンドモード
- CLI コマンド一覧
- @Agent 記法の詳細
- HTTP API の使い方
- Priority（優先度）の意味
- 運用パターン例

---

## 2. 設定リファレンス

### [profiles.md](profiles.md)
**プロファイル設定ガイド**

- YAML スキーマの解説
- 各フィールドの意味
  - `command`: CLI コマンド
  - `idle_regex`: IDLE 状態検出パターン
  - `submit_sequence`: 送信キーシーケンス
  - `env`: 環境変数
- デフォルトプロファイル（claude, codex, gemini, dummy）
- カスタムプロファイルの作成方法

---

## 3. 技術ドキュメント

### [architecture.md](architecture.md)
**内部アーキテクチャ**

- コンポーネント構成図
- TerminalController: PTY 管理
- InputRouter: @Agent パターン検出
- AgentRegistry: サービス検出
- FastAPI Server: HTTP API
- スレッドモデル
- 通信フロー詳細
- 設計方針

### [references.md](references.md)
**API/CLI リファレンス**

- CLI コマンド完全リファレンス
- HTTP API エンドポイント仕様
- Registry ファイル構造
- プロファイル YAML スキーマ

---

## 4. 外部連携

### [google-a2a-spec.md](google-a2a-spec.md)
**Google A2A プロトコル互換性**

- Google A2A プロトコル概要
- Agent Card / Task の概念
- Synapse A2A の互換機能
- 外部エージェントへの接続方法
- API エンドポイント一覧

---

## 5. サポート

### [troubleshooting.md](troubleshooting.md)
**トラブルシューティング**

- PTY/TUI 描画の問題
- エージェントが見つからない
- ポート競合
- IDLE 検出の問題
- Claude Code 固有の問題
- デバッグ方法

---

## クイックリファレンス

### デフォルトポート

| エージェント | ポート | プロファイル |
|-------------|--------|-------------|
| Claude | 8100 | `claude.yaml` |
| Codex | 8101 | `codex.yaml` |
| Gemini | 8102 | `gemini.yaml` |
| Dummy | 8199 | `dummy.yaml` |

### 主要コマンド

```bash
# インタラクティブ起動
synapse claude --port 8100

# バックグラウンド起動
synapse start claude --port 8100

# エージェント一覧
synapse list

# メッセージ送信
synapse send --target codex --priority 1 "メッセージ"

# 停止
synapse stop claude
```

### 外部エージェント管理

```bash
# 外部エージェントを発見・登録
synapse external add http://other-agent:9000 --alias other

# 登録済み外部エージェント一覧
synapse external list

# 外部エージェントにメッセージ送信
synapse external send other "Hello!"

# 外部エージェント詳細表示
synapse external info other

# 外部エージェント削除
synapse external remove other
```

### @Agent 記法

```text
# ローカルエージェント
@agent_name メッセージ

# 外部エージェント（事前に登録が必要）
@external_alias メッセージ

# レスポンスを受け取る
@agent_name --response "メッセージ"
```

### HTTP API

```bash
# メッセージ送信（従来 API）
curl -X POST http://localhost:8100/message \
  -H "Content-Type: application/json" \
  -d '{"content": "Hello", "priority": 1}'

# ステータス確認
curl http://localhost:8100/status

# Google A2A 互換 API
curl http://localhost:8100/.well-known/agent.json
curl -X POST http://localhost:8100/tasks/send \
  -H "Content-Type: application/json" \
  -d '{"message": {"role": "user", "parts": [{"type": "text", "text": "Hello"}]}}'
```

---

## ファイル構成

```
guides/
├── README.md              # このファイル（ドキュメントインデックス）
├── multi-agent-setup.md   # セットアップガイド
├── usage.md               # 使い方詳細
├── profiles.md            # プロファイル設定
├── architecture.md        # アーキテクチャ
├── references.md          # API/CLI リファレンス
├── troubleshooting.md     # トラブルシューティング
└── google-a2a-spec.md     # Google A2A 比較
```
