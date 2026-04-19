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
最終設定 = デフォルト + User + Project + Local（後から上書き）
```

マージはセクション単位（`env`, `instructions`, `a2a` 等）で行われ、各セクション内のキーは個別にマージされます。**高優先度スコープに存在するキーだけが上書きされ、存在しないキーは低優先度スコープの値がそのまま残ります。**

#### 例1: 特定のキーだけ上書き

User scope に全設定を書き、Project scope に1つだけ書いた場合：

```
User:    env: { HISTORY_ENABLED: "true", LEARNING_MODE_ENABLED: "false", LOG_LEVEL: "INFO", ... }
Project: env: { LEARNING_MODE_ENABLED: "true" }
```

結果：
```
env: { HISTORY_ENABLED: "true", LEARNING_MODE_ENABLED: "true", LOG_LEVEL: "INFO", ... }
```

→ Project scope の `LEARNING_MODE_ENABLED` だけが上書きされ、残りは User scope の値がそのまま使われます。

#### 例2: 意図しない上書き

User scope で個人の好みとして有効にした設定が、Project scope のテンプレートデフォルトで無効に戻されるケース：

```
User:    env: { LEARNING_MODE_ENABLED: "true" }     ← 個人で有効化
Project: env: { LEARNING_MODE_ENABLED: "false" }     ← テンプレートのデフォルト
→ 結果:  LEARNING_MODE_ENABLED = "false"              ← Project が優先して無効に
```

**対処法**: プロジェクト全体で制御する必要がないキーは、Project scope から削除するか、`settings.local.json`（Local scope）で上書きしてください。

#### 推奨される使い分け

| スコープ | 書くべき設定 | 例 |
|----------|-------------|-----|
| User | 個人の好み・グローバルなデフォルト | Learning mode、Log level、DB パス |
| Project | プロジェクト固有・チーム共有の設定 | File safety、Approval mode、A2A flow |
| Local | 個人のプロジェクト固有の上書き | User scope の設定をこのプロジェクトだけ変えたい場合 |

## コマンド

### synapse init

`.synapse/` ディレクトリを対話的に作成します。テンプレートファイルをマージ方式でコピーします。

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
| `file-safety.md` | File Safety の指示 |
| `learning.md` | Learning Mode の指示（構造化されたプロンプト改善・学習フィードバック） |
| `shared-memory.md` | Shared Memory の指示（エージェント間の知識共有コマンド） |

既に `.synapse/` ディレクトリが存在する場合は、マージ方式で更新されます。`settings.json` は**スマートマージ**（新しいキーを追加し、ユーザーの値を保持）、その他のテンプレートファイルは上書きされます。ユーザーが生成したデータ（`agents/`、`sessions/`、`workflows/`、`worktrees/`、SQLite データベースなど）は保持されます：

```bash
$ synapse init

/path/to/.synapse already exists. Merge template files? (y/N): y
✔ Updated /path/to/.synapse (user data preserved)
```

### アップグレード手順

Synapse を更新した後、`synapse init` を再実行することで新しい設定キーを取り込めます：

```bash
pip install --upgrade synapse-a2a   # または: pipx upgrade synapse-a2a
synapse init --scope project        # スマートマージ: 新キー追加、既存値保持
synapse init --scope user           # ユーザースコープも同様
```

マージ結果の確認：

```bash
synapse config show --scope merged
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

インタラクティブな TUI で設定を編集します。`--scope` は不要で、TUI が各設定の実効値とそのソースを表示し、編集対象のスコープを自動判定します。

```bash
$ synapse config

? Select a category to configure:
  ❯ Environment Variables - Configure SYNAPSE_* environment variables
    Instructions - Configure agent-specific instruction files
    A2A Protocol - Configure inter-agent communication settings
    Resume Flags - Configure CLI flags that indicate resume mode
    ────────────────────────────────────────────
    Save and exit
    Exit without saving

? Select a setting to edit:
  ❯ LEARNING_MODE_ENABLED: ON (user) [env: ON]
    HISTORY_ENABLED: ON (project)
    FILE_SAFETY_ENABLED: ON (default)
```

**カテゴリ**:

| カテゴリ | 説明 |
|----------|------|
| Environment Variables | `SYNAPSE_HISTORY_ENABLED` などの環境変数 |
| Instructions | エージェント別の初期インストラクション |
| A2A Protocol | `flow` モード（auto/roundtrip/oneway） |
| Resume Flags | セッション再開を示すフラグ |

**動作**:

- 各項目は実効値とそのソースを表示します。例: `LEARNING_MODE_ENABLED: ON (user) [env: ON]`
- 項目を編集すると、実効値のソースになっているスコープの `settings.json` が直接更新されます
- `os.environ` で上書きされている項目は変更不可として表示されます
- スコープを明示して表示だけ確認したい場合は `synapse config show --scope user|project|merged` を使います

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

Claude Code の場合、**GitHub CLI (`gh skill install`) 経由でのインストールを強く推奨します**（`gh` 2.90.0+ が必要）。これにより、最新のスキルと機能（File Safety, Delegation など）が自動的に適用され、バージョン固定と出所追跡も可能になります。

```bash
# gh skill install 経由でインストール
gh skill install s-hiraoku/synapse-a2a synapse-a2a
gh skill install s-hiraoku/synapse-a2a synapse-manager
gh skill install s-hiraoku/synapse-a2a synapse-reinst

# バージョンをピン留め
gh skill install s-hiraoku/synapse-a2a synapse-a2a --pin v0.26.4

# 特定のエージェントランタイムを対象にインストール
gh skill install s-hiraoku/synapse-a2a synapse-a2a --agent claude-code
```

詳細と移行マトリクスは [`docs/skills-management.md`](../docs/skills-management.md) を参照してください。旧来の `npx skills add s-hiraoku/synapse-a2a`（skills.sh）も引き続き動作しますが、推奨ではありません。

### Legacy Skills (手動インストール)

`synapse` コマンド起動時に、`~/.claude/skills/` に基本的なスキルファイルが自動的に配置される場合があります。これは旧バージョンとの互換性のための動作です。

> **Note**: `synapse init` は現在、個別のプロジェクトディレクトリへのスキルファイルのコピーは行いません。プロジェクト単位でスキルを管理したい場合は、`gh skill install` を使用してください。

### Gemini

Gemini はエージェント側のスキル機能に対応していないため、起動時に Synapse が直接 A2A プロトコルの指示（Initial Instructions）を送信することで機能を実現します。

### Codex

Codex もプラグインには対応していませんが、展開された skills（`SKILL.md` など）をプロジェクトの `.agents/skills/` ディレクトリに配置することで、Claude Code と同様に高度な機能を教え込むことが可能です。OpenCode も `.agents/skills/` を自動スキャンするため、同じディレクトリで共有できます。

## settings.json の構造

### 完全な例

```json
{
  "env": {
    "SYNAPSE_HISTORY_ENABLED": "true",
    "SYNAPSE_FILE_SAFETY_ENABLED": "true",
    "SYNAPSE_FILE_SAFETY_RETENTION_DAYS": "30",
    "SYNAPSE_AUTH_ENABLED": "false",
    "SYNAPSE_API_KEYS": "",
    "SYNAPSE_ADMIN_KEY": "",
    "SYNAPSE_ALLOW_LOCALHOST": "true",
    "SYNAPSE_USE_HTTPS": "false",
    "SYNAPSE_WEBHOOK_SECRET": "",
    "SYNAPSE_WEBHOOK_TIMEOUT": "10",
    "SYNAPSE_WEBHOOK_MAX_RETRIES": "3",
    "SYNAPSE_SHARED_MEMORY_ENABLED": "true",
    "SYNAPSE_SHARED_MEMORY_DB_PATH": "~/.synapse/memory.db"
  },
  "instructions": {
    "default": "[SYNAPSE INSTRUCTIONS...]",
    "claude": "",
    "gemini": "[SYNAPSE INSTRUCTIONS...]",
    "codex": ""
  },
  "approvalMode": "required",
  "resume_flags": {
    "claude": ["--continue", "--resume", "-c", "-r"],
    "codex": ["resume"],
    "gemini": ["--resume", "-r"]
  },
  "a2a": {
    "flow": "auto"
  },
  "list": {
    "columns": [
      "ID",
      "NAME",
      "STATUS",
      "CURRENT",
      "TRANSPORT",
      "WORKING_DIR",
      "EDITING_FILE"
    ]
  }
}
```


## 環境変数 (env)

`env` セクションで設定した環境変数は、エージェント起動時に自動的に設定されます。

### 利用可能な変数

| 変数 | 説明 | デフォルト |
|------|------|-----------|
| `SYNAPSE_HISTORY_ENABLED` | タスク履歴を有効化 | `true` (v0.3.13+) |
| `SYNAPSE_AUTH_ENABLED` | API Key 認証を有効化 | `false` |
| `SYNAPSE_API_KEYS` | 有効な API キー（カンマ区切り） | - |
| `SYNAPSE_ADMIN_KEY` | 管理者用 API キー | - |
| `SYNAPSE_ALLOW_LOCALHOST` | localhost からのアクセスで認証をスキップ | `true` |
| `SYNAPSE_USE_HTTPS` | HTTPS を使用 | `false` |
| `SYNAPSE_WEBHOOK_SECRET` | Webhook 署名用シークレット | - |
| `SYNAPSE_WEBHOOK_TIMEOUT` | Webhook タイムアウト（秒） | `10` |
| `SYNAPSE_WEBHOOK_MAX_RETRIES` | Webhook リトライ回数 | `3` |
| `SYNAPSE_FILE_SAFETY_ENABLED` | File Safety 機能を有効化 | `true` |
| `SYNAPSE_FILE_SAFETY_DB_PATH` | SQLite データベースファイルのパス | `.synapse/file_safety.db` |
| `SYNAPSE_FILE_SAFETY_RETENTION_DAYS` | ロック履歴の保持日数 | `30` |
| `SYNAPSE_LONG_MESSAGE_THRESHOLD` | ファイル保存の文字数閾値 | `200` |
| `SYNAPSE_LONG_MESSAGE_TTL` | メッセージファイルの有効期間（秒） | `3600` |
| `SYNAPSE_LONG_MESSAGE_DIR` | メッセージファイル保存先 | システム一時ディレクトリ |
| `SYNAPSE_SEND_MESSAGE_THRESHOLD` | `synapse send` の自動 temp file 化の閾値（バイト） | `102400` |
| `SYNAPSE_LEARNING_MODE_ENABLED` | Prompt Improvement セクションを有効化（Goal/Problem/Fix、推奨リライト、詳細レベル別オプション）。TRANSLATION と独立して動作。どちらかが有効なら `learning.md` 注入と Tips が有効化される | `false` |
| `SYNAPSE_LEARNING_MODE_TRANSLATION` | JP→EN Learning セクションを有効化（再利用可能な英語パターンとスロットマッピング）。LEARNING_MODE_ENABLED と独立して動作。どちらかが有効なら `learning.md` 注入と Tips が有効化される | `false` |
| `SYNAPSE_PROACTIVE_MODE_ENABLED` | Proactive Mode を有効化。すべてのタスクで Synapse 機能（共有メモリ、キャンバス、ファイルセーフティ、委任、ブロードキャスト）の使用を必須にする。起動時に `.synapse/proactive.md` を注入 | `false` |
| `SYNAPSE_SHARED_MEMORY_ENABLED` | エージェント間の共有メモリ機能を有効化 | `true` |
| `SYNAPSE_SHARED_MEMORY_DB_PATH` | 共有メモリ SQLite データベースのパス | `~/.synapse/memory.db` |
| `SYNAPSE_REGISTRY_DIR` | ローカル Registry ディレクトリのパス | `~/.a2a/registry` |
| `SYNAPSE_EXTERNAL_REGISTRY_DIR` | 外部エージェント Registry ディレクトリのパス | `~/.a2a/external` |
| `SYNAPSE_HISTORY_DB_PATH` | 履歴データベースのパス | `~/.synapse/history/history.db` |

### 例: 履歴を無効にする

v0.3.13 以降、履歴はデフォルトで有効です。無効にする場合：

```json
{
  "env": {
    "SYNAPSE_HISTORY_ENABLED": "false"
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
| `{{agent_id}}` | ランタイムID | `synapse-claude-8100` |
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
| `flow: auto` | フラグで制御（フラグなしは待つ、デフォルト） |

### 例

```json
{
  "a2a": {
    "flow": "auto"
  }
}
```

詳細は [a2a-communication.md](a2a-communication.md) を参照してください。

## リスト表示設定 (list)

`synapse list` コマンドで表示するカラムをカスタマイズできます。

### 利用可能なカラム

| カラム | 説明 |
|--------|------|
| `ID` | ランタイムID（例: `synapse-claude-8100`） |
| `NAME` | カスタム名 |
| `TYPE` | エージェント種別（claude, gemini, codex 等） |
| `ROLE` | エージェントの役割説明 |
| `STATUS` | 現在の状態（READY, PROCESSING 等） |
| `CURRENT` | 現在のタスクプレビュー |
| `TRANSPORT` | 通信状態（UDS/TCP） |
| `WORKING_DIR` | 作業ディレクトリ |
| `EDITING_FILE` | 編集中のファイル（File Safety有効時のみ） |

### デフォルト設定

```json
{
  "list": {
    "columns": [
      "ID",
      "NAME",
      "STATUS",
      "CURRENT",
      "TRANSPORT",
      "WORKING_DIR",
      "EDITING_FILE"
    ]
  }
}
```

### カスタマイズ例

コンパクトな表示にする場合：

```json
{
  "list": {
    "columns": ["ID", "NAME", "STATUS", "EDITING_FILE"]
  }
}
```

**Note**: `EDITING_FILE` カラムは `SYNAPSE_FILE_SAFETY_ENABLED=true` の場合のみ表示されます。

## 承認モード (approvalMode)

初期インストラクション送信前に確認プロンプトを表示するかを制御します。

### 設定値

| 設定 | 説明 |
|------|------|
| `approvalMode: required` | 起動時に確認プロンプトを表示（デフォルト） |
| `approvalMode: auto` | プロンプトなしで自動的にインストラクションを送信 |

### プロンプト表示

`required` 設定時、以下のようなプロンプトが表示されます：

```
[Synapse] Agent: synapse-claude-8100 | Port: 8100
[Synapse] Initial instructions will be sent to configure A2A communication.

Proceed? [Y/n/s(skip)]:
```

### 選択肢

| 入力 | 動作 |
|------|------|
| `Y` または Enter | 初期インストラクションを送信してエージェントを起動 |
| `n` | 起動を中止 |
| `s` | 初期インストラクションなしでエージェントを起動 |

### 例

```json
{
  "approvalMode": "auto"
}
```

**ユースケース**:
- **チーム環境**: `required` で各メンバーが確認できるようにする
- **自動化/CI**: `auto` でプロンプトをスキップする

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

# Synapse worktrees (created by synapse --worktree / synapse spawn --worktree)
.synapse/worktrees/

# Claude Code worktrees (created by -- --worktree flag, Claude only)
.claude/worktrees/
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
