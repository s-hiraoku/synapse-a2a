# コード⇔ドキュメント対応表

このファイルはソースコードとドキュメントの対応関係を定義する。
コードが変更された際、どのドキュメントを更新すべきかの判断に使用する。

## synapse/ ディレクトリ

### コアモジュール

| ソースファイル | 関連ドキュメント | 更新内容 |
|---------------|-----------------|---------|
| `cli.py` | `README.md`, `guides/usage.md`, `guides/references.md`, `CLAUDE.md` | CLIコマンド、オプション、使用例 |
| `controller.py` | `guides/architecture.md`, `guides/profiles.md` | PTY管理、READY/PROCESSING検出 |
| `server.py` | `README.md`, `guides/references.md`, `guides/enterprise.md` | APIエンドポイント、認証 |
| `a2a_compat.py` | `README.md`, `guides/google-a2a-spec.md`, `docs/a2a-design-rationale.md` | A2Aプロトコル実装 |
| `a2a_client.py` | `guides/architecture.md`, `guides/a2a-communication.md` | エージェント間通信 |
| `input_router.py` | `README.md`, `guides/usage.md`, `docs/input-routing-spec.md` | @Agentパターン、ルーティング |
| `registry.py` | `guides/architecture.md`, `guides/references.md` | エージェント登録・検索 |
| `agent_context.py` | `guides/settings.md`, `docs/agent-card-context.md` | 初期インストラクション生成 |
| `history.py` | `README.md`, `guides/usage.md`, `CLAUDE.md` | タスク履歴機能 |
| `file_safety.py` | `README.md`, `docs/file-safety.md`, `guides/usage.md` | ファイル競合防止 |
| `shell.py` | `guides/architecture.md` | シェル統合 |
| `shell_hook.py` | `guides/architecture.md` | シェルフック |

### commands/ ディレクトリ

| ソースファイル | 関連ドキュメント | 更新内容 |
|---------------|-----------------|---------|
| `commands/start.py` | `README.md`, `guides/usage.md` | `synapse start` コマンド |
| `commands/list.py` | `README.md`, `guides/usage.md`, `CLAUDE.md` | `synapse list` コマンド |
| `commands/instructions.py` | `README.md`, `guides/usage.md` | `synapse instructions` コマンド |

### profiles/ ディレクトリ

| ソースファイル | 関連ドキュメント | 更新内容 |
|---------------|-----------------|---------|
| `profiles/claude.yaml` | `guides/profiles.md`, `guides/troubleshooting.md` | Claudeプロファイル設定 |
| `profiles/codex.yaml` | `guides/profiles.md` | Codexプロファイル設定 |
| `profiles/gemini.yaml` | `guides/profiles.md` | Geminiプロファイル設定 |

### templates/ ディレクトリ

| ソースファイル | 関連ドキュメント | 更新内容 |
|---------------|-----------------|---------|
| `templates/.synapse/settings.json` | `guides/settings.md`, `README.md` | 設定項目、デフォルト値 |
| `templates/.synapse/default.md` | `guides/settings.md` | 初期インストラクション |
| `templates/.synapse/delegate.md` | `guides/delegation.md` | 委任ルールテンプレート |
| `templates/.synapse/file-safety.md` | `docs/file-safety.md` | File Safety指示 |

## plugins/ ディレクトリ

| ソースファイル | 関連ドキュメント | 更新内容 |
|---------------|-----------------|---------|
| `plugins/synapse-a2a/.claude-plugin/plugin.json` | `plugins/synapse-a2a/README.md`, `README.md` | プラグインバージョン、メタデータ |
| `plugins/synapse-a2a/skills/synapse-a2a/SKILL.md` | 同期: `.claude/skills/`, `.codex/skills/` | スキル内容 |
| `plugins/synapse-a2a/skills/delegation/SKILL.md` | 同期: `.claude/skills/`, `.codex/skills/` | 委任スキル内容 |

## tests/ ディレクトリ

テストファイルの変更は通常ドキュメント更新不要だが、以下の場合は例外：

| 条件 | 更新すべきドキュメント |
|------|----------------------|
| テスト数が大幅に変化 | `README.md` のテストバッジ |
| 新しいテストカテゴリ追加 | `CLAUDE.md` のテストコマンド例 |

## pyproject.toml

| 変更内容 | 更新すべきドキュメント |
|---------|----------------------|
| バージョン更新 | `CHANGELOG.md` |
| 依存関係追加 | `README.md` (前提条件), `guides/multi-agent-setup.md` |
| 新しいCLIエントリポイント | `README.md`, `guides/usage.md` |

## 変更パターン別ガイド

### 新しいCLIコマンドを追加した場合

1. `README.md` - コマンド一覧テーブルに追加
2. `guides/usage.md` - 詳細な使い方を追加
3. `guides/references.md` - リファレンスに追加
4. `CLAUDE.md` - 開発者向け情報（必要に応じて）

### 新しいAPIエンドポイントを追加した場合

1. `README.md` - APIエンドポイントテーブルに追加
2. `guides/references.md` - 詳細仕様を追加
3. `guides/enterprise.md` - エンタープライズ機能の場合

### 新しい環境変数を追加した場合

1. `README.md` - 設定ファイルセクションに追加
2. `guides/settings.md` - 詳細説明を追加
3. `synapse/templates/.synapse/settings.json` - デフォルト値を追加

### 新しいプロファイル設定を追加した場合

1. `guides/profiles.md` - 設定項目を追加
2. `CLAUDE.md` - 必要に応じてプロファイル説明を更新

### File Safety機能を変更した場合

1. `README.md` - 機能概要を更新
2. `docs/file-safety.md` - 詳細仕様を更新
3. `guides/usage.md` - CLIコマンドを更新
4. `synapse/templates/.synapse/file-safety.md` - テンプレートを更新
5. `plugins/synapse-a2a/skills/synapse-a2a/references/file-safety.md` - スキルリファレンスを更新

### タスク履歴機能を変更した場合

1. `README.md` - 機能概要を更新
2. `guides/usage.md` - CLIコマンドを更新
3. `CLAUDE.md` - 開発者向け情報を更新

### スキルを変更した場合

1. `plugins/synapse-a2a/skills/*/SKILL.md` - ソースを更新
2. `.claude/skills/*/SKILL.md` - 同期
3. `.codex/skills/*/SKILL.md` - 同期
4. `plugins/synapse-a2a/README.md` - 必要に応じて更新
