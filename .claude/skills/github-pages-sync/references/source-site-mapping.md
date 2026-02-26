# ソースコード ⇔ site-docs 対応表

このファイルはソースコードおよび内部ドキュメントと GitHub Pages サイト（`site-docs/`）の対応関係を定義する。
コードや内部ドキュメントが変更された際、どの site-docs ページを更新すべきかの判断に使用する。

## 内部ドキュメント → site-docs

### メインドキュメント

| ソース | site-docs ページ | 対応内容 |
|--------|-----------------|---------|
| `README.md` | `index.md` | プロジェクト概要、機能ハイライト、クイックスタート |
| `CHANGELOG.md` | `changelog.md` | リリースノート、変更履歴 |

### guides/ → site-docs

| ソース | site-docs ページ | 対応内容 |
|--------|-----------------|---------|
| `guides/usage.md` | `guide/agent-management.md` | エージェント起動・停止・名前付け |
| `guides/usage.md` | `guide/communication.md` | メッセージ送受信、ブロードキャスト |
| `guides/usage.md` | `guide/skills.md` | スキル管理コマンド |
| `guides/usage.md` | `guide/history.md` | 履歴・トレース機能 |
| `guides/profiles.md` | `concepts/profiles.md` | プロファイル概念説明 |
| `guides/profiles.md` | `reference/profiles-yaml.md` | YAML スキーマ詳細 |
| `guides/settings.md` | `guide/settings.md` | 設定ガイド |
| `guides/settings.md` | `reference/configuration.md` | 設定リファレンス |
| `guides/architecture.md` | `concepts/architecture.md` | アーキテクチャ概要 |
| `guides/references.md` | `reference/cli.md` | CLI コマンドリファレンス |
| `guides/references.md` | `reference/api.md` | API エンドポイントリファレンス |
| `guides/enterprise.md` | `advanced/enterprise.md` | エンタープライズ機能 |
| `guides/enterprise.md` | `advanced/authentication.md` | 認証・API キー |
| `guides/enterprise.md` | `advanced/webhooks.md` | Webhook 機能 |
| `guides/troubleshooting.md` | `troubleshooting.md` | トラブルシューティング |
| `guides/multi-agent-setup.md` | `getting-started/installation.md` | インストール手順 |
| `guides/multi-agent-setup.md` | `getting-started/quickstart.md` | クイックスタート |
| `guides/multi-agent-setup.md` | `getting-started/setup.md` | インタラクティブセットアップ |

### docs/ → site-docs

| ソース | site-docs ページ | 対応内容 |
|--------|-----------------|---------|
| `docs/file-safety.md` | `guide/file-safety.md` | ファイル競合防止ガイド |
| `docs/project-philosophy.md` | `concepts/philosophy.md` | プロジェクト哲学・設計原則 |
| `docs/a2a-design-rationale.md` | `concepts/a2a-protocol.md` | A2A プロトコル設計思想 |
| `docs/external-agent-connectivity.md` | `advanced/external-agents.md` | 外部エージェント連携 |
| `docs/claude-code-worktree.md` | `advanced/worktree.md` | Worktree 分離 |

## ソースコード → site-docs

### synapse/ コアモジュール

| ソースファイル | site-docs ページ | 更新内容 |
|---------------|-----------------|---------|
| `synapse/cli.py` | `reference/cli.md`, `guide/agent-management.md` | CLI コマンド、オプション |
| `synapse/controller.py` | `concepts/architecture.md` | PTY 管理、ステータス検出 |
| `synapse/server.py` | `reference/api.md`, `concepts/architecture.md` | API エンドポイント |
| `synapse/a2a_compat.py` | `reference/api.md`, `concepts/a2a-protocol.md` | A2A プロトコル実装 |
| `synapse/a2a_client.py` | `guide/communication.md`, `concepts/architecture.md` | エージェント間通信 |
| `synapse/registry.py` | `concepts/architecture.md` | エージェント登録・検索 |
| `synapse/history.py` | `guide/history.md` | タスク履歴機能 |
| `synapse/file_safety.py` | `guide/file-safety.md` | ファイル競合防止 |
| `synapse/skills.py` | `guide/skills.md` | スキル管理 |
| `synapse/task_board.py` | `guide/task-board.md` | タスクボード |
| `synapse/hooks.py` | `guide/agent-teams.md` | Quality Gates |
| `synapse/approval.py` | `guide/agent-teams.md` | Plan Approval |
| `synapse/spawn.py` | `guide/agent-teams.md`, `reference/cli.md` | エージェント Spawn |
| `synapse/token_parser.py` | `guide/agent-management.md` | トークン・コスト追跡 |
| `synapse/paths.py` | `reference/configuration.md` | パス管理・環境変数 |

### synapse/commands/ ディレクトリ

| ソースファイル | site-docs ページ | 更新内容 |
|---------------|-----------------|---------|
| `commands/start.py` | `reference/cli.md`, `guide/agent-management.md` | `synapse start` コマンド |
| `commands/list.py` | `reference/cli.md`, `guide/agent-management.md` | `synapse list` コマンド |
| `commands/instructions.py` | `reference/cli.md` | `synapse instructions` コマンド |
| `commands/skill_manager.py` | `reference/cli.md`, `guide/skills.md` | `synapse skills` コマンド |

### synapse/profiles/ ディレクトリ

| ソースファイル | site-docs ページ | 更新内容 |
|---------------|-----------------|---------|
| `profiles/claude.yaml` | `concepts/profiles.md`, `reference/profiles-yaml.md` | Claude プロファイル |
| `profiles/codex.yaml` | `concepts/profiles.md`, `reference/profiles-yaml.md` | Codex プロファイル |
| `profiles/gemini.yaml` | `concepts/profiles.md`, `reference/profiles-yaml.md` | Gemini プロファイル |
| `profiles/opencode.yaml` | `concepts/profiles.md`, `reference/profiles-yaml.md` | OpenCode プロファイル |
| `profiles/copilot.yaml` | `concepts/profiles.md`, `reference/profiles-yaml.md` | Copilot プロファイル |
| （全プロファイル） | `reference/ports.md` | ポート範囲 |

### その他

| ソースファイル | site-docs ページ | 更新内容 |
|---------------|-----------------|---------|
| `pyproject.toml` | `changelog.md`, `getting-started/installation.md` | バージョン、依存関係 |
| `mkdocs.yml` | （nav 構造の整合性） | ナビゲーション構造 |

## 変更パターン別ガイド

### 新しい CLI コマンドを追加した場合

1. `reference/cli.md` - コマンド構文、オプション、使用例を追加
2. 関連する `guide/` ページ - ユースケースを追加
3. `getting-started/quickstart.md` - 基本的なコマンドの場合のみ

### 新しい API エンドポイントを追加した場合

1. `reference/api.md` - エンドポイント仕様を追加
2. `advanced/authentication.md` - 認証が必要な場合
3. `concepts/architecture.md` - アーキテクチャに影響する場合

### 新しい設定項目を追加した場合

1. `reference/configuration.md` - 設定リファレンスに追加
2. `guide/settings.md` - 使い方ガイドに追加

### プロファイル設定を変更した場合

1. `concepts/profiles.md` - 概念説明を更新
2. `reference/profiles-yaml.md` - YAML スキーマを更新
3. `reference/ports.md` - ポート範囲の場合

### 新機能を追加した場合

1. `index.md` - 機能ハイライトに追加
2. `guide/` 配下に使い方を追加（既存ページまたは新規）
3. `reference/cli.md` / `reference/api.md` - コマンド/APIを追加
4. `mkdocs.yml` - 新ページの場合はナビゲーションに追加
5. `changelog.md` - 変更履歴に追加

### File Safety 機能を変更した場合

1. `guide/file-safety.md` - ガイドを更新
2. `reference/cli.md` - 関連コマンドを更新

### Agent Teams 機能を変更した場合

1. `guide/agent-teams.md` - チーム機能ガイドを更新
2. `guide/task-board.md` - タスクボードの場合
3. `reference/cli.md` - 関連コマンドを更新
4. `reference/api.md` - チーム API の場合
