# Synapse A2A ドキュメント一覧

このファイルはプロジェクト内の全ドキュメントとその役割を定義する。

## メインドキュメント

| ファイル | 役割 | 更新トリガー |
|---------|------|-------------|
| `README.md` | プロジェクト概要、クイックスタート、主要機能 | 新機能追加、API変更、インストール方法変更 |
| `CLAUDE.md` | Claude Code向け開発ガイド（コマンド、アーキテクチャ、テスト） | コマンド追加、アーキテクチャ変更、テスト方法変更 |
| `GEMINI.md` | Gemini CLI向け指示 | Gemini固有の設定変更 |
| `AGENTS.md` | マルチエージェント環境での共通指示 | エージェント間連携の変更 |
| `CHANGELOG.md` | リリースノート、変更履歴 | 各リリース時 |

## guides/ ディレクトリ

ユーザー向けドキュメント。

| ファイル | 役割 | 更新トリガー |
|---------|------|-------------|
| `README.md` | ガイド全体の目次・ナビゲーション | 新ガイド追加時 |
| `overview.md` | Synapse A2A 全体概要 | アーキテクチャ変更、新機能追加 |
| `multi-agent-setup.md` | セットアップ手順 | インストール方法変更、前提条件変更 |
| `usage.md` | 使い方詳細、CLIコマンド | コマンド追加・変更、新機能 |
| `settings.md` | `.synapse/settings.json` 設定ガイド | 設定項目追加・変更 |
| `profiles.md` | プロファイル設定（YAML） | プロファイル形式変更 |
| `delegation.md` | タスク委任ルール | 委任機能の変更 |
| `architecture.md` | 内部アーキテクチャ | コンポーネント追加・変更 |
| `agent-identity.md` | エージェント識別・ルーティング | ID形式変更、ルーティング変更 |
| `references.md` | API/CLIリファレンス | エンドポイント追加、コマンド追加 |
| `enterprise.md` | エンタープライズ機能（認証、Webhook、gRPC） | 認証方式変更、Webhook機能追加 |
| `troubleshooting.md` | トラブルシューティング | 新しい問題・解決策の発見 |
| `google-a2a-spec.md` | Google A2A プロトコル互換性 | A2A仕様への対応変更 |
| `a2a-communication.md` | エージェント間通信の詳細 | 通信プロトコル変更 |

## docs/ ディレクトリ

技術仕様・設計ドキュメント。

| ファイル | 役割 | 更新トリガー |
|---------|------|-------------|
| `README.md` | docs/の目次 | 新ドキュメント追加時 |
| `project-philosophy.md` | プロジェクト哲学・設計原則 | 設計方針の変更 |
| `a2a-design-rationale.md` | A2Aプロトコル準拠性の設計思想 | A2A対応の変更 |
| `agent-card-context.md` | Agent Card Context拡張 | Agent Card形式変更 |
| `external-agent-connectivity.md` | 外部エージェント連携ビジョン | 外部連携機能の追加 |
| `draft-spec.md` | ドラフト仕様 | プロトコル仕様の検討時 |
| `universal-agent-communication-spec.md` | 汎用エージェント通信仕様 | 通信仕様の変更 |
| `input-routing-spec.md` | 入力ルーティング仕様 | ルーティングロジック変更 |
| `file-safety.md` | File Safety機能の詳細 | ファイル競合防止機能の変更 |
| `release.md` | リリースガイド | リリースプロセスの変更 |
| `HANDOFF_CLAUDE_ENTER_KEY_ISSUE.md` | Claude Code Enterキー問題の技術詳細 | PTY/TUI関連の変更 |
| `a2a-uds-local-transport.md` | UDSローカルトランスポート | 通信方式の変更 |

## synapse/templates/.synapse/ ディレクトリ

`synapse init` でコピーされる初期設定テンプレート。

| ファイル | 役割 | 更新トリガー |
|---------|------|-------------|
| `settings.json` | 設定ファイルテンプレート | 設定項目追加・デフォルト値変更 |
| `default.md` | 全エージェント共通の初期インストラクション | A2Aプロトコル説明の変更 |
| `gemini.md` | Gemini用初期インストラクション | Gemini固有の指示変更 |
| `delegate.md` | タスク委任ルールテンプレート | 委任機能の変更 |
| `file-safety.md` | File Safety指示テンプレート | File Safety機能の変更 |

## plugins/synapse-a2a/ ディレクトリ

Claude Code プラグイン。

| ファイル | 役割 | 更新トリガー |
|---------|------|-------------|
| `README.md` | プラグイン説明、インストール方法 | プラグイン機能変更 |
| `.claude-plugin/plugin.json` | プラグインメタデータ | バージョン更新、スキル追加 |
| `skills/synapse-a2a/SKILL.md` | synapse-a2aスキル本体 | A2A機能変更、コマンド追加 |
| `skills/synapse-a2a/references/*.md` | スキルリファレンス | 詳細仕様の変更 |
| `skills/delegation/SKILL.md` | delegationスキル本体 | 委任機能変更 |
| `skills/delegation/references/*.md` | 委任リファレンス | 委任仕様の変更 |

## 同期が必要なファイル群

以下のファイル群は内容を同期する必要がある：

### スキルの同期

| ソース | 同期先 |
|--------|--------|
| `plugins/synapse-a2a/skills/` | `.claude/skills/` |
| `plugins/synapse-a2a/skills/` | `.codex/skills/` |

### テンプレートの同期

| ソース | 同期先 |
|--------|--------|
| `synapse/templates/.synapse/` | `.synapse/` (ユーザー側) |

### README.md との整合性

以下の情報は `README.md` と各ガイドで一致している必要がある：

- CLIコマンド一覧 (`README.md` ↔ `guides/usage.md` ↔ `guides/references.md`)
- APIエンドポイント (`README.md` ↔ `guides/references.md`)
- ポート範囲 (`README.md` ↔ `guides/multi-agent-setup.md`)
- 環境変数 (`README.md` ↔ `guides/settings.md`)
