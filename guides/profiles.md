# Profiles

Synapse A2A は `synapse/profiles/*.yaml` の設定を使って CLI エージェントを起動します。
このドキュメントでは、プロファイル設定の詳細を解説します。

---

## 1. プロファイルの概要

```mermaid
flowchart LR
    subgraph Profiles["synapse/profiles/"]
        Claude["claude.yaml"]
        Codex["codex.yaml"]
        Gemini["gemini.yaml"]
        Dummy["dummy.yaml"]
        Custom["custom.yaml"]
    end

    CLI["synapse <profile>"]
    TC["TerminalController"]

    CLI -->|"読み込み"| Profiles
    Profiles -->|"設定適用"| TC
```

---

## 2. YAML スキーマ

### 2.1 基本構造

```yaml
# 必須フィールド
command: "claude"           # 起動する CLI コマンド

# オプションフィールド
args: []                    # コマンドライン引数（現在未使用）
submit_sequence: "\n"       # 送信時に付与するキーシーケンス
idle_detection:            # IDLE 状態検出設定（新形式）
  strategy: "pattern"       # "pattern" | "timeout" | "hybrid"
  pattern: "> $"           # 正規表現パターン
  timeout: 1.5             # 秒数（フォールバック）
env:                        # 環境変数
  TERM: "xterm-256color"
```

**後方互換性**: 古い `idle_regex` フィールドもサポートしていますが、新規作成時は `idle_detection` を使用してください。

---

### 2.2 フィールド詳細

| フィールド | 型 | 必須 | デフォルト | 説明 |
|-----------|-----|------|-----------|------|
| `command` | string | Yes | - | 起動する CLI コマンド |
| `args` | array | No | `[]` | コマンドライン引数 |
| `submit_sequence` | string | No | `\n` | 送信時のキーシーケンス |
| `idle_detection` | object | No | `{strategy: "timeout", timeout: 1.5}` | IDLE 検出戦略 |
| `env` | object | No | `{}` | 追加/上書きする環境変数 |

---

## 3. フィールド解説

### 3.1 command

起動する CLI コマンドを指定します。

```yaml
# 単一コマンド
command: "claude"

# 引数付き
command: "python3 -u dummy_agent.py"

# パス指定
command: "/usr/local/bin/claude"
```

**コマンドの解決**:

1. 環境変数 `PATH` から検索
2. 絶対パスで指定可能
3. スペース区切りで引数を含めることが可能

---

### 3.2 idle_detection

エージェントが待機状態（READY）になったことを検出するための設定です。複数の検出戦略をサポートしています。

```yaml
# 戦略 1: pattern（正規表現ベース）
idle_detection:
  strategy: "pattern"
  pattern: "> $"
  timeout: 1.5

# 戦略 2: timeout（タイムアウトベース）
idle_detection:
  strategy: "timeout"
  timeout: 0.5

# 戦略 3: hybrid（パターン + タイムアウト）
idle_detection:
  strategy: "hybrid"
  pattern: "> $"
  timeout: 1.5
```

**検出戦略**:

| 戦略 | 説明 | 用途 |
|-----|------|------|
| `pattern` | 正規表現マッチングで IDLE を検出 | 一貫したプロンプトを持つ CLI |
| `timeout` | 出力がない時間でアイドル判定 | 不規則なプロンプトの CLI |
| `hybrid` | パターンをまず試し、失敗時にタイムアウト | 初期化シーケンスがある CLI |

**正規表現パターン例**:

```yaml
# プロンプトが "> " で終わる場合
pattern: "> $"

# プロンプトが ">>> " の場合
pattern: ">>> $"

# 複数パターン
pattern: "(> |>>> )$"

# 特殊パターン（Claude Code）
pattern: "BRACKETED_PASTE_MODE"  # BRACKETED_PASTE_MODE エスケープシーケンスで検出
```

**注意点**:

- 正規表現はバイト列に対してマッチングされます（UTF-8 エンコード）
- 出力バッファの最後 1000 バイトに対して検索されます
- パターン検出は出力の最後のマッチのみを使用します

---

### 3.3 submit_sequence

メッセージ送信時に末尾に付与するキーシーケンスです。

```yaml
# readline 系 CLI（標準入力）
submit_sequence: "\n"

# Ink/TUI 系 CLI（Enter キー）
submit_sequence: "\r"

# 特殊シーケンス（Ctrl+J）
submit_sequence: "\x0a"
```

**使い分け**:

```mermaid
flowchart TB
    CLI{"CLI タイプ"}
    Readline["readline 系<br/>(標準入力)"]
    TUI["Ink/TUI 系<br/>(ターミナルUI)"]

    CLI -->|"シンプルな CLI"| Readline
    CLI -->|"リッチな UI"| TUI

    Readline --> LF["\\n (LF)"]
    TUI --> CR["\\r (CR)"]
```

| シーケンス | コード | 用途 |
|-----------|--------|------|
| `\n` | LF (0x0a) | readline 系 CLI |
| `\r` | CR (0x0d) | Ink/TUI 系 CLI |

**エスケープシーケンス**:

YAML ではバックスラッシュはエスケープされるため、以下のように記述します：

```yaml
# 正しい記法
submit_sequence: "\n"    # LF
submit_sequence: "\r"    # CR

# Python での解釈
# "\n" -> 0x0a
# "\r" -> 0x0d
```

---

### 3.4 env

起動時に設定する環境変数です。システム環境変数に追加/上書きされます。

```yaml
env:
  TERM: "xterm-256color"
  PYTHONUNBUFFERED: "1"
  CUSTOM_VAR: "value"
```

**重要な環境変数**:

| 変数 | 推奨値 | 説明 |
|------|--------|------|
| `TERM` | `xterm-256color` | ターミナルタイプ（TUI 必須） |
| `PYTHONUNBUFFERED` | `1` | Python の出力バッファリング無効化 |
| `NO_COLOR` | `1` | カラー出力無効化（オプション） |

---

## 4. デフォルトプロファイル

### 4.1 claude.yaml

```yaml
command: "claude"
args: []
submit_sequence: "\r"
idle_detection:
  strategy: "timeout"
  timeout: 0.5
env:
  TERM: "xterm-256color"
```

**特徴**:

- Claude Code CLI 用
- Ink ベースの TUI のため `\r` を使用
- **timeout 戦略**: TUI 初期化はBRACKETED_PASTE_MODEが一度だけ出るため、以降のアイドル検出はタイムアウトに依存
- 500ms の短いタイムアウト（高速応答性）

---

### 4.2 codex.yaml

```yaml
command: "codex"
args: []
submit_sequence: "\r"
idle_detection:
  strategy: "timeout"
  timeout: 1.5
env:
  TERM: "xterm-256color"
```

**特徴**:

- OpenAI Codex CLI 用
- **timeout 戦略**: 不規則なプロンプト出力
- 1.5 秒のタイムアウト

---

### 4.3 gemini.yaml

```yaml
command: "gemini"
args: []
submit_sequence: "\r"
idle_detection:
  strategy: "timeout"
  timeout: 1.5
env:
  TERM: "xterm-256color"
```

**特徴**:

- Google Gemini CLI 用
- **timeout 戦略**: 会話履歴の中にプロンプトパターンが現れることがあるため、パターンマッチングは不確実
- 1.5 秒のタイムアウト

---

### 4.4 dummy.yaml

```yaml
command: "python3 -u dummy_agent.py"
submit_sequence: "\n"
idle_detection:
  strategy: "pattern"
  pattern: "> $"
  timeout: 1.5
env:
  PYTHONUNBUFFERED: "1"
```

**特徴**:

- テスト用のダミーエージェント
- `python3 -u` で unbuffered モード
- readline 系のため `\n` を使用
- **pattern 戦略**: 一貫したプロンプトを使用するため、パターンマッチングが有効

---

## 5. カスタムプロファイルの作成

### 5.1 作成手順

1. `synapse/profiles/` に YAML ファイルを作成
2. 必須フィールドを設定
3. CLI から起動

```bash
# 1. プロファイル作成
cat > synapse/profiles/myagent.yaml << EOF
command: "myagent"
idle_regex: "\\$ $"
submit_sequence: "\n"
env:
  TERM: "xterm-256color"
EOF

# 2. デフォルトポートを追加（オプション）
# cli.py の DEFAULT_PORTS に追加

# 3. 起動
synapse myagent --port 8200
```

---

### 5.2 プロファイル例：GPT CLI

```yaml
command: "gpt"
submit_sequence: "\n"
idle_detection:
  strategy: "pattern"
  pattern: "gpt> $"
  timeout: 1.5
env:
  TERM: "xterm-256color"
  OPENAI_API_KEY: ""  # 環境変数から継承
```

---

### 5.3 プロファイル例：カスタム Python エージェント

```yaml
command: "python3 -u /path/to/my_agent.py"
submit_sequence: "\n"
idle_detection:
  strategy: "pattern"
  pattern: ">>> $"
  timeout: 1.5
env:
  PYTHONUNBUFFERED: "1"
  MY_CONFIG: "/path/to/config.json"
```

---

## 6. トラブルシューティング

### 6.1 READY にならない

**原因**: `idle_detection` の設定が不適切

**対処**:

#### パターン戦略を使用している場合
1. CLI を手動で起動してプロンプトを確認
2. `idle_detection.pattern` を修正

```bash
# プロンプトを確認
$ claude
> _

# idle_detection を設定
idle_detection:
  strategy: "pattern"
  pattern: "> $"
```

#### タイムアウト戦略を使用している場合
1. タイムアウト値を調整（短すぎると誤検出、長すぎると応答が遅れる）
2. デフォルトは 1.5 秒だが、環境に応じて調整

```yaml
idle_detection:
  strategy: "timeout"
  timeout: 2.0  # 2 秒に増加
```

#### ハイブリッド戦略を使用している場合
1. パターン認識が不可能な場合、タイムアウトにフォールバックする
2. 最初のパターン認識に失敗した場合、タイムアウトで検出されます

---

### 6.2 メッセージが送信されない

**原因**: `submit_sequence` が不正

**対処**:

1. `\n` と `\r` を入れ替えて試す
2. TUI 系 CLI は `\r` を使用

```yaml
# 変更前
submit_sequence: "\n"

# 変更後
submit_sequence: "\r"
```

---

### 6.3 TUI が崩れる

**原因**: `TERM` が設定されていない

**対処**:

```yaml
env:
  TERM: "xterm-256color"
```

---

### 6.4 日本語が文字化けする

**原因**: ロケール設定が不足

**対処**:

```yaml
env:
  LANG: "ja_JP.UTF-8"
  LC_ALL: "ja_JP.UTF-8"
```

---

## 7. 高度な設定

### 7.1 複雑なプロンプトパターン

```yaml
# 複数行プロンプト
idle_regex: "(claude|codex|gemini)> $"

# ANSI エスケープシーケンス付き
idle_regex: "\\x1b\\[0m> $"
```

---

### 7.2 条件付き環境変数

```yaml
env:
  # 開発環境
  DEBUG: "1"
  LOG_LEVEL: "debug"

  # 本番環境では削除または変更
```

---

## 8. プロファイル読み込みの仕組み

```mermaid
sequenceDiagram
    participant CLI as synapse CLI
    participant YAML as yaml.safe_load()
    participant TC as TerminalController
    participant Process as CLI プロセス

    CLI->>YAML: プロファイル読み込み
    YAML-->>CLI: config dict
    CLI->>CLI: submit_sequence デコード
    CLI->>CLI: env マージ
    CLI->>TC: TerminalController(config)
    TC->>Process: pty.spawn(command)
```

**コード参照** (`cli.py`):

```python
with open(profile_path, 'r') as f:
    config = yaml.safe_load(f)

submit_seq = config.get('submit_sequence', '\n')
            .encode().decode('unicode_escape')

env = os.environ.copy()
if 'env' in config:
    env.update(config['env'])
```

---

## 関連ドキュメント

- [architecture.md](architecture.md) - 内部アーキテクチャ
- [troubleshooting.md](troubleshooting.md) - トラブルシューティング
- [references.md](references.md) - 完全リファレンス
