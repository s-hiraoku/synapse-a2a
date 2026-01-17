# 設定ファイル (.synapse) ガイド

Synapse A2A の設定ファイルについての詳細ガイドです。

## 概要

`.synapse/settings.json` を使用して、以下をカスタマイズできます：

- **環境変数**: エージェント起動時に設定される環境変数
- **初期インストラクション**: エージェント起動時に送信される指示

## ディレクトリ構造

```
~/.synapse/                              # User スコープ（グローバル）
└── settings.json

./.synapse/                              # Project スコープ
├── settings.json                        # チーム共有設定（git管理）
└── settings.local.json                  # 個人設定（gitignore推奨）
```

## スコープと優先順位

設定は3つのスコープで管理され、高優先度が低優先度を上書きします。

| スコープ | パス | 優先度 | 用途 |
|----------|------|--------|------|
| User | `~/.synapse/settings.json` | 低 | 全プロジェクト共通の個人設定 |
| Project | `./.synapse/settings.json` | 中 | プロジェクト固有のチーム共有設定 |
| Local | `./.synapse/settings.local.json` | 高 | 個人のローカル上書き |

### マージ動作

```
最終設定 = User + Project + Local（後から上書き）
```

例：
- User: `SYNAPSE_HISTORY_ENABLED=false`
- Project: `SYNAPSE_HISTORY_ENABLED=true`
- → 結果: `SYNAPSE_HISTORY_ENABLED=true`（Project が優先）

## コマンド

### synapse init

`.synapse/` ディレクトリを対話的に作成します。テンプレートから全ファイルをコピーします。

```bash
$ synapse init

? Where do you want to create .synapse/?
  ❯ User scope (~/.synapse/)
    Project scope (./.synapse/)

✔ Created ~/.synapse
```

**コピーされるファイル**:

| ファイル | 説明 |
|----------|------|
| `settings.json` | 環境変数・初期インストラクション設定 |
| `default.md` | 全エージェント共通の初期インストラクション |
| `gemini.md` | Gemini 用の初期インストラクション |
| `delegate.md` | タスク委任ルール |
| `file-safety.md` | File Safety の指示 |

既に `.synapse/` ディレクトリが存在する場合は、上書き確認のプロンプトが表示されます：

```bash
$ synapse init

/path/to/.synapse already exists. Overwrite? (y/N): y
✔ Created /path/to/.synapse
```

### synapse reset

設定ファイルをデフォルトに戻します。

```bash
$ synapse reset

? Which settings do you want to reset?
  ❯ User scope (~/.synapse/settings.json)
    Project scope (./.synapse/settings.json)
    Both

? This will overwrite existing settings. Continue? (y/N) y

✔ Reset ~/.synapse/settings.json to defaults
```

### synapse config

インタラクティブな TUI で設定を編集します。

```bash
$ synapse config

? Which settings file do you want to edit?
  ❯ User settings (~/.synapse/settings.json)
    Project settings (./.synapse/settings.json)
    ────────────────────────────────────────────
    Cancel

Editing: /Users/you/.synapse/settings.json

? Select a category to configure:
  ❯ Environment Variables - Configure SYNAPSE_* environment variables
    Instructions - Configure agent-specific instruction files
    A2A Protocol - Configure inter-agent communication settings
    Delegation - Configure task delegation settings
    Resume Flags - Configure CLI flags that indicate resume mode
    ────────────────────────────────────────────
    Save and exit
    Exit without saving
```

**カテゴリ**:

| カテゴリ | 説明 |
|----------|------|
| Environment Variables | `SYNAPSE_HISTORY_ENABLED` などの環境変数 |
| Instructions | エージェント別の初期インストラクション |
| A2A Protocol | `flow` モード（auto/roundtrip/oneway） |
| Delegation | タスク委任の有効/無効 |
| Resume Flags | セッション再開を示すフラグ |

**オプション**:

```bash
# スコープを直接指定（プロンプトをスキップ）
synapse config --scope user     # ユーザー設定を編集
synapse config --scope project  # プロジェクト設定を編集
```

### synapse config show

現在の設定をマージ済みの状態で表示します（読み取り専用）。

```bash
$ synapse config show

Current settings (merged from all scopes):
------------------------------------------------------------
{
  "env": {
    "SYNAPSE_HISTORY_ENABLED": "true",
    ...
  },
  "instructions": { ... },
  "a2a": { "flow": "auto" },
  "delegation": { "enabled": false },
  "resume_flags": { ... }
}
```

**オプション**:

```bash
synapse config show                  # マージ済み設定を表示
synapse config show --scope user     # ユーザー設定のみ表示
synapse config show --scope project  # プロジェクト設定のみ表示
```

## Skills のインストール

Synapse A2A の機能をエージェントに教え込むための「スキル」の導入方法は、エージェントによって異なります。

### Claude Code

Claude Code の場合、**プラグイン marketplace からのインストールを強く推奨します**。これにより、最新のスキルと機能（File Safety, Delegation など）が自動的に適用されます。

```bash
# Claude Code 内で実行
/plugin marketplace add s-hiraoku/synapse-a2a
/plugin install synapse-a2a@s-hiraoku/synapse-a2a
```

### Legacy Skills (手動インストール)

`synapse` コマンド起動時に、`~/.claude/skills/` に基本的なスキルファイルが自動的に配置される場合があります。これは旧バージョンとの互換性のための動作です。

> **Note**: `synapse init` は現在、個別のプロジェクトディレクトリへのスキルファイルのコピーは行いません。プロジェクト単位でスキルを管理したい場合は、プラグイン機能を使用してください。

### Gemini

Gemini はエージェント側のスキル機能に対応していないため、起動時に Synapse が直接 A2A プロトコルの指示（Initial Instructions）を送信することで機能を実現します。

### Codex

Codex もプラグインには対応していませんが、展開された skills（`SKILL.md` など）をプロジェクトの `.codex/skills/` ディレクトリに配置することで、Claude Code と同様に高度な機能を教え込むことが可能です。

## settings.json の構造

### 完全な例

```json
{
  "env": {
    "SYNAPSE_HISTORY_ENABLED": "false",
    "SYNAPSE_FILE_SAFETY_ENABLED": "false",
    "SYNAPSE_FILE_SAFETY_RETENTION_DAYS": "30",
    "SYNAPSE_AUTH_ENABLED": "false",
    "SYNAPSE_API_KEYS": "",
    "SYNAPSE_ADMIN_KEY": "",
    "SYNAPSE_ALLOW_LOCALHOST": "true",
    "SYNAPSE_USE_HTTPS": "false",
    "SYNAPSE_WEBHOOK_SECRET": "",
    "SYNAPSE_WEBHOOK_TIMEOUT": "10",
    "SYNAPSE_WEBHOOK_MAX_RETRIES": "3"
  },
  "instructions": {
    "default": "[SYNAPSE INSTRUCTIONS...]",
    "claude": "",
    "gemini": "[SYNAPSE INSTRUCTIONS...]",
    "codex": ""
  },
  "resume_flags": {
    "claude": ["--continue", "--resume", "-c", "-r"],
    "codex": ["resume"],
    "gemini": ["--resume", "-r"]
  },
  "a2a": {
    "flow": "auto"
  },
  "delegation": {
    "enabled": false
  }
}
```


## 環境変数 (env)

`env` セクションで設定した環境変数は、エージェント起動時に自動的に設定されます。

### 利用可能な変数

| 変数 | 説明 | デフォルト |
|------|------|-----------|
| `SYNAPSE_HISTORY_ENABLED` | タスク履歴を有効化 | `false` |
| `SYNAPSE_AUTH_ENABLED` | API Key 認証を有効化 | `false` |
| `SYNAPSE_API_KEYS` | 有効な API キー（カンマ区切り） | - |
| `SYNAPSE_ADMIN_KEY` | 管理者用 API キー | - |
| `SYNAPSE_ALLOW_LOCALHOST` | localhost からのアクセスで認証をスキップ | `true` |
| `SYNAPSE_USE_HTTPS` | HTTPS を使用 | `false` |
| `SYNAPSE_WEBHOOK_SECRET` | Webhook 署名用シークレット | - |
| `SYNAPSE_WEBHOOK_TIMEOUT` | Webhook タイムアウト（秒） | `10` |
| `SYNAPSE_WEBHOOK_MAX_RETRIES` | Webhook リトライ回数 | `3` |

### 例: 履歴を常に有効にする

```json
{
  "env": {
    "SYNAPSE_HISTORY_ENABLED": "true"
  }
}
```

### 例: 認証を有効にする

```json
{
  "env": {
    "SYNAPSE_AUTH_ENABLED": "true",
    "SYNAPSE_API_KEYS": "my-secret-key-1,my-secret-key-2",
    "SYNAPSE_ADMIN_KEY": "admin-secret-key"
  }
}
```

## コンテキスト再開フラグ (resume_flags)

エージェント起動時に、これらのフラグが引数に含まれている場合、Synapse は「セッション再開」と判断し、初期インストラクションの送信をスキップします。

### デフォルト設定

```json
{
  "resume_flags": {
    "claude": ["--continue", "--resume", "-c", "-r"],
    "codex": ["resume"],
    "gemini": ["--resume", "-r"]
  }
}
```

### カスタマイズ例

独自のエイリアスや新しいフラグを追加する場合：

```json
{
  "resume_flags": {
    "claude": ["--my-resume-flag", "-z"]
  }
}
```

**仕様**:
- **完全一致**: リスト内の文字列と完全に一致する引数を検知します。
- **値付きフラグ**: ハイフンで始まるフラグ（例: `--resume`）の場合、`--resume=123` のような形式も自動的に検知します。

## 初期インストラクション (instructions)

`instructions` セクションで、エージェント起動時に送信される指示をカスタマイズできます。

### 解決ロジック

```
if instructions.{agent_type} が設定されている:
    → それを使用
elif instructions.default が設定されている:
    → default を使用
else:
    → 初期インストラクションを送信しない
```

### プレースホルダー

以下のプレースホルダーは実行時に置換されます：

| プレースホルダー | 説明 | 例 |
|------------------|------|-----|
| `{{agent_id}}` | エージェントID | `synapse-claude-8100` |
| `{{port}}` | ポート番号 | `8100` |

### 例: 日本語で応答させる

```json
{
  "instructions": {
    "default": "[SYNAPSE INSTRUCTIONS...]\n\n必ず日本語で応答してください。"
  }
}
```

### 例: エージェント毎にカスタマイズ

```json
{
  "instructions": {
    "default": "共通の指示...",
    "claude": "Claude用: コードレビューに集中してください",
    "gemini": "Gemini用: 簡潔に回答してください",
    "codex": "Codex用: テストコードを必ず書いてください"
  }
}
```

### Gemini の注意点

Gemini は Claude Code の Skills に対応していないため、デフォルトでは SKILL 行を除いた指示が設定されています。

## A2A 通信設定 (a2a)

エージェント間通信の応答動作を制御します。

### 設定値

| 設定 | 説明 |
|------|------|
| `flow: roundtrip` | 常に結果を待つ |
| `flow: oneway` | 常に転送のみ（結果を待たない） |
| `flow: auto` | AIエージェントがタスクに応じて判断、またはフラグで明示的に制御（デフォルト） |

### 例

```json
{
  "a2a": {
    "flow": "auto"
  }
}
```

詳細は [a2a-communication.md](a2a-communication.md) を参照してください。

## 委任設定 (delegation)

自動タスク委任を制御します。

### 設定値

| 設定 | 説明 |
|------|------|
| `enabled: true` | `.synapse/delegate.md` を読み込み、委任ルールを有効化 |
| `enabled: false` | 委任を無効化（デフォルト） |

### 例

```json
{
  "delegation": {
    "enabled": true
  }
}
```

委任を有効にするには、`.synapse/delegate.md` に委任ルールを記述してください。

詳細は [delegation.md](delegation.md) を参照してください。

## ユースケース

### プロジェクト全体で履歴を有効化

`.synapse/settings.json`（git 管理）:
```json
{
  "env": {
    "SYNAPSE_HISTORY_ENABLED": "true"
  }
}
```

### 個人の API キーを設定

`.synapse/settings.local.json`（gitignore）:
```json
{
  "env": {
    "SYNAPSE_API_KEYS": "my-personal-key"
  }
}
```

### 全プロジェクトで共通の指示

`~/.synapse/settings.json`:
```json
{
  "instructions": {
    "default": "全プロジェクト共通: 日本語で応答してください"
  }
}
```

### プロジェクト固有の指示で上書き

`.synapse/settings.json`:
```json
{
  "instructions": {
    "default": "このプロジェクトでは Python 3.11 を使用しています"
  }
}
```

## .gitignore 推奨設定

```gitignore
# Synapse local settings (contains secrets)
.synapse/settings.local.json
```

## トラブルシューティング

### 設定が反映されない

1. ファイルパスを確認（`~/.synapse/` または `./.synapse/`）
2. JSON 構文を確認（`jq . settings.json` でバリデーション）
3. エージェントを再起動

### 初期インストラクションが送信されない

1. `instructions.default` または `instructions.{agent_type}` が設定されているか確認
2. 空文字列 `""` は「送信しない」と解釈される

### 環境変数が上書きされる

シェルで設定した環境変数は `settings.json` より優先されます：

```bash
# settings.json の SYNAPSE_HISTORY_ENABLED=true を上書き
SYNAPSE_HISTORY_ENABLED=false synapse claude
```
