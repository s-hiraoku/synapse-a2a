# Usage

このドキュメントでは、Synapse A2A の使い方を詳細に説明します。

---

## 1. 起動モード

Synapse A2A には 2 つの起動モードがあります。

```mermaid
flowchart LR
    subgraph Interactive["インタラクティブモード"]
        I1["端末で直接操作"]
        I2["@Agent 入力可能"]
        I3["TUI 対応"]
    end

    subgraph Background["バックグラウンドモード"]
        B1["デーモン起動"]
        B2["API のみ操作"]
        B3["ログ出力"]
    end

    User["ユーザー"] --> Interactive
    User --> Background
```

---

### 1.1 インタラクティブモード（推奨）

端末内で直接 CLI を操作しながら、`@Agent` による A2A 通信も可能なモードです。

```bash
synapse claude --port 8100
```

**特徴**:

| 項目 | 説明 |
|------|------|
| 操作 | 端末で直接入力可能 |
| @Agent | `@codex メッセージ` で送信可能 |
| TUI | Ink ベースの TUI も動作（一部制限あり） |
| PTY | `pty.spawn()` でラップ |

**起動時の表示**:

起動時にアニメーション付きのバナーが表示されます：

```
 ███████╗██╗   ██╗███╗   ██╗ █████╗ ██████╗ ███████╗███████╗
 ██╔════╝╚██╗ ██╔╝████╗  ██║██╔══██╗██╔══██╗██╔════╝██╔════╝
 ███████╗ ╚████╔╝ ██╔██╗ ██║███████║██████╔╝███████╗█████╗
 ╚════██║  ╚██╔╝  ██║╚██╗██║██╔══██║██╔═══╝ ╚════██║██╔══╝
 ███████║   ██║   ██║ ╚████║██║  ██║██║     ███████║███████╗
 ╚══════╝   ╚═╝   ╚═╝  ╚═══╝╚═╝  ╚═╝╚═╝     ╚══════╝╚══════╝

 Agent-to-Agent Communication Framework

 ────────────────────────────────────────────────────────────

 Agent Configuration
   Type:     claude
   ID:       synapse-claude-8100
   Port:     8100

 A2A Endpoints
   Agent Card: http://localhost:8100/.well-known/agent.json
   Tasks API:  http://localhost:8100/tasks/send

 Quick Reference
   synapse list              Show running agents
   synapse send <agent> "msg"  Send message to agent
   Ctrl+C (twice)            Exit

 ────────────────────────────────────────────────────────────
```

続いて承認プロンプト（`approvalMode: required` の場合）が表示されます：

```
[Synapse] Agent: synapse-claude-8100 | Port: 8100
[Synapse] Initial instructions will be sent to configure A2A communication.

Proceed? [Y/n/s(skip)]:
```

**ショートカット構文**:

```bash
# 以下は同じ意味
synapse claude
synapse claude --port 8100
```

---

### 1.2 バックグラウンドモード（サーバモード）

端末を使わずにデーモンとして起動するモードです。

```bash
synapse start claude --port 8100
```

**特徴**:

| 項目 | 説明 |
|------|------|
| 操作 | HTTP API / CLI のみ |
| @Agent | 使用不可 |
| ログ | `~/.synapse/logs/<profile>.log` |
| 終了 | `synapse stop claude` |

**フォアグラウンド起動**:

```bash
synapse start claude --port 8100 --foreground
```

---

### 1.3 コンテキストの再開（Resume Mode）

エージェントがクラッシュした場合や、既存のセッション（会話履歴）を引き継いで再起動する場合、通常起動すると A2A プロトコルの初期説明が再度送信され、コンテキストが無駄に長くなってしまいます。

Resume Mode（再開モード）を使用すると、**初期インストラクションの送信をスキップ** し、スムーズに作業を継続できます。

```bash
# Claude: --continue / --resume / -c / -r
synapse claude -- --resume

# Gemini: --resume / -r
synapse gemini -- --resume

# Codex: resume サブコマンド
synapse codex -- resume

# セッションID指定（Claude）
synapse claude -- --resume=SESSION_ID
```

> **Note**: `synapse <agent> --` の後の引数は、エージェントの CLI ツールに直接渡されます。

**動作**:
- 指定されたフラグ（`--resume` 等）を検知すると、Synapse は「これは再開である」と判断します。
- A2A プロトコルの初期説明（Available Agents や使い方の説明）を送信しません。
- エージェントは前回の続きとして即座に待機状態に入ります。

**対応フラグ（デフォルト）**:

| エージェント | フラグ |
|--------------|--------|
| **Claude** | `--resume`, `--continue`, `-r`, `-c` |
| **Gemini** | `--resume`, `-r` |
| **Codex** | `resume` |
| **OpenCode** | `--continue`, `-c` |

これらのフラグは `.synapse/settings.json` でカスタマイズ可能です。

---

### 1.4 インストラクション管理

Resume Mode で起動した場合など、初期インストラクションが送信されなかった状況で、後からインストラクションを送信したい場合に使用します。

```bash
# インストラクション内容を確認
synapse instructions show claude

# 利用されるインストラクションファイル一覧
synapse instructions files claude

# 実行中のエージェントに初期インストラクションを送信
synapse instructions send claude

# 送信前にプレビュー（実際には送信しない）
synapse instructions send claude --preview

# 特定のエージェントIDを指定して送信
synapse instructions send synapse-claude-8100
```

**ユースケース**:

| シチュエーション | 対応 |
|----------------|------|
| `--resume` 後に A2A 機能が必要になった | `synapse instructions send <agent>` |
| エージェントがインストラクションを忘れた | `synapse instructions send <agent>` |
| インストラクション内容の確認 | `synapse instructions show <agent>` |
| 設定ファイルの確認 | `synapse instructions files <agent>` |

---

### 1.5 エージェントの初期化 (Agent Card Context Extension)

Synapse では、ターミナル（PTY）に長いインストラクションを表示せず、A2A プロトコル準拠の **Agent Card** を使用してエージェントに初期設定（コンテキスト）を渡します。

**動作**:
1. 起動時に、PTY に最小限の「ブートストラップメッセージ」が送信されます。
2. メッセージには、`x-synapse-context` 拡張を含む Agent Card を取得するための `curl` コマンドが含まれています。
3. AI エージェントはこのコマンドを実行して、自分の ID、転送ルール、他のエージェント情報などを取得します。

**メリット**:
- **ターミナルのクリーン化**: 画面が長い説明テキストで埋まりません。
- **標準準拠**: A2A プロトコルのエージェント発見メカニズムを活用しています。

詳細は [a2a-communication.md](a2a-communication.md) を参照してください。

---

## 2. CLI コマンド

### 2.1 コマンド一覧

```mermaid
flowchart TB
    synapse["synapse"]

    subgraph Shortcuts["ショートカット"]
        claude["claude"]
        codex["codex"]
        gemini["gemini"]
        opencode["opencode"]
        copilot["copilot"]
    end

    subgraph Commands["サブコマンド"]
        start["start"]
        stop["stop"]
        team["team"]
        spawn["spawn"]
        kill["kill"]
        jump["jump"]
        rename["rename"]
        list["list"]
        send["send"]
        interrupt["interrupt"]
        broadcast["broadcast"]
        reply["reply"]
        trace["trace"]
        logs["logs"]
        instructions["instructions"]
        history["history"]
        external["external"]
        skills["skills"]
        config["config"]
        memory["memory"]
        agents["agents"]
        tasks["tasks"]
        session["session"]
        workflow["workflow"]
        approve["approve"]
        reject["reject"]
        init["init"]
        reset["reset"]
        auth["auth"]
        learn["learn"]
        instinct["instinct"]
        evolve["evolve"]
    end

    subgraph Memory["memory サブコマンド"]
        mem_save["save"]
        mem_list["list"]
        mem_show["show"]
        mem_search["search"]
        mem_delete["delete"]
        mem_stats["stats"]
    end

    subgraph Instructions["instructions サブコマンド"]
        inst_show["show"]
        inst_files["files"]
        inst_send["send"]
    end

    subgraph External["external サブコマンド"]
        ext_add["add"]
        ext_list["list"]
        ext_remove["remove"]
        ext_send["send"]
        ext_info["info"]
    end

    subgraph History["history サブコマンド"]
        hist_list["list"]
        hist_show["show"]
        hist_search["search"]
        hist_cleanup["cleanup"]
        hist_stats["stats"]
        hist_export["export"]
    end

    subgraph Skills["skills サブコマンド"]
        sk_list["list"]
        sk_show["show"]
        sk_delete["delete"]
        sk_move["move"]
        sk_deploy["deploy"]
        sk_import["import"]
        sk_add["add"]
        sk_create["create"]
        sk_set["set"]
        sk_apply["apply"]
    end

    subgraph Agents["agents サブコマンド"]
        ag_list["list"]
        ag_show["show"]
        ag_add["add"]
        ag_delete["delete"]
    end

    subgraph Tasks["tasks サブコマンド"]
        ts_list["list"]
        ts_create["create"]
        ts_assign["assign"]
        ts_complete["complete"]
        ts_fail["fail"]
        ts_reopen["reopen"]
    end

    subgraph SessionCmds["session サブコマンド"]
        sess_save["save"]
        sess_list["list"]
        sess_show["show"]
        sess_restore["restore"]
        sess_delete["delete"]
    end

    subgraph WorkflowCmds["workflow サブコマンド"]
        wf_create["create"]
        wf_list["list"]
        wf_show["show"]
        wf_run["run"]
        wf_delete["delete"]
    end

    synapse --> Shortcuts
    synapse --> Commands
    memory --> Memory
    instructions --> Instructions
    external --> External
    history --> History
    skills --> Skills
    agents --> Agents
    tasks --> Tasks
    session --> SessionCmds
    workflow --> WorkflowCmds
```

| コマンド | 説明 |
|---------|------|
| `synapse <profile>` | インタラクティブ起動（ショートカット） |
| `synapse start <profile>` | バックグラウンド起動 |
| `synapse stop <profile\|id>` | エージェント停止（ID指定も可） |
| `synapse team start <specs...>` | 1番目=handoff、他=新ペイン。`--all-new` で全員新ペイン |
| `synapse kill <target>` | グレースフルシャットダウン（デフォルト30秒、`-f` で即時終了） |
| `synapse jump <target>` | エージェントのターミナルにジャンプ |
| `synapse rename <target>` | エージェントに名前・ロールを設定 |
| `synapse init` | Synapse 設定の初期化（`.synapse/settings.json` 作成） |
| `synapse reset` | 設定をデフォルトに戻す（`--force` で確認スキップ） |
| `synapse --version` | バージョン情報表示 |
| `synapse list` | 実行中エージェント一覧 |
| `synapse send` | メッセージ送信 |
| `synapse interrupt` | ソフト割り込み送信 |
| `synapse broadcast` | カレントディレクトリの全エージェントにメッセージ送信 |
| `synapse logs <profile>` | ログ表示 |
| `synapse instructions` | インストラクション管理 |
| `synapse external` | 外部エージェント管理 |
| `synapse memory` | 共有メモリ管理（エージェント間の知識共有） |
| `synapse agents` | 保存済みエージェント定義の管理 |
| `synapse tasks` | 共有タスクボードの管理 |
| `synapse approve/reject` | プランの承認/却下 |
| `synapse skills` | スキル管理（インタラクティブTUI / サブコマンド） |
| `synapse skills apply <target> <set_name>` | 稼働中のエージェントにスキルセットを適用（`--dry-run` でプレビュー） |
| `synapse session` | セッション保存/復元（チーム構成のスナップショット管理） |
| `synapse workflow` | ワークフロー管理（保存済みメッセージシーケンスの作成・実行） |
| `synapse config` | 設定管理（インタラクティブTUI） |
| `synapse auth` | API キー認証の管理（`setup` / `generate-key`） |
| `synapse learn` | 観測データを分析しインスティンクト（学習パターン）を生成 |
| `synapse instinct` | 学習済みインスティンクトの一覧表示（`--scope`, `--domain`, `--min-confidence` フィルタ対応） |
| `synapse instinct promote <id>` | プロジェクトスコープのインスティンクトをグローバルに昇格 |
| `synapse evolve` | インスティンクトからスキル候補を発見（`--generate` でスキルファイル生成） |

---

### 2.2 起動/停止

```bash
# インタラクティブ起動
synapse claude --port 8100

# 名前とロールを指定して起動（対話型セットアップをスキップ）
synapse claude --name my-claude --role "コードレビュー担当"

# 保存済みエージェント定義を使用して起動（--agent / -A）
synapse claude --agent calm-lead        # 保存済みエージェントIDで指定
synapse claude -A Claud                       # 表示名で指定（短縮フラグ）
synapse claude --agent calm-lead --role "一時的なロール上書き"  # CLI引数で上書き可能

# 対話型セットアップをスキップ（名前・ロールなし）
synapse claude --no-setup

# バックグラウンド起動
synapse start claude --port 8100

# フォアグラウンド起動（デバッグ用）
synapse start claude --port 8100 --foreground

# 停止
synapse stop claude

# IDを指定して停止（推奨：より確実です）
synapse stop synapse-claude-8100

# 全インスタンスを停止
synapse stop claude --all

# グレースフルシャットダウン（HTTP停止リクエスト → SIGTERM → SIGKILL）
synapse kill claude
synapse kill my-claude    # カスタム名で指定
synapse kill claude -f    # 即時終了（SIGKILL）

# エージェントのターミナルにジャンプ
synapse jump claude
synapse jump my-claude    # カスタム名で指定
```

### 2.2.1 エージェント命名

エージェントにカスタム名とロールを設定できます。

```bash
# 起動時に対話形式で設定（デフォルト動作）
synapse claude
# → 名前とロールの入力プロンプトが表示される

# CLI オプションで設定
synapse claude --name my-claude --role "コードレビュー担当"

# ファイルからロールを読み込み（@プレフィックス）
synapse claude --name reviewer --role "@./roles/reviewer.md"

# 保存済みエージェント定義を使用
synapse claude --agent calm-lead
synapse claude -A Claud                       # 短縮フラグ

# 対話型セットアップをスキップ
synapse claude --no-setup

# 起動後に名前・ロールを変更
synapse rename synapse-claude-8100 --name my-claude --role "テスト担当"
synapse rename my-claude --role "ドキュメント担当"  # ロールのみ変更
synapse rename my-claude --clear                    # 名前・ロールをクリア
```

**`--agent` / `-A` フラグ:**

保存済みエージェント定義を使用してエージェントを起動します。名前、ロール、スキルセットが自動的に解決されます。

```bash
synapse claude --agent calm-lead        # 保存済みIDで起動
synapse claude -A Claud                       # 表示名で起動
synapse claude --agent calm-lead --role "上書きロール"  # CLI引数が優先
```

> **Note**: 保存済み定義の `profile` と起動コマンドのプロファイルが一致する必要があります（例: `profile=gemini` の定義を `synapse claude` では使用不可）。

**ロールファイルの推奨ディレクトリ:**

| スコープ | パス | 用途 |
|---------|------|------|
| プロジェクト | `./roles/` | チームで共有するロール定義（Gitにコミット） |
| 個人 | `~/my-roles/` または `~/.synapse/roles/` | 個人用ロールテンプレート |

ロールファイルは Markdown 形式で、エージェントの責務やワークフローを記述します：

```markdown
# Code Reviewer

You are an expert at reviewing code for correctness and security.

## Responsibilities
- Review pull requests for bugs and security issues
- Suggest improvements for readability and performance
```

**名前を設定すると、すべての操作で使用可能:**

```bash
synapse send my-claude "コードをレビューして"
synapse kill my-claude
synapse jump my-claude
```

**ターゲット解決の優先順位:**

1. カスタム名（最優先）: `my-claude`
2. ランタイムID: `synapse-claude-8100`
3. タイプ-ポート短縮形: `claude-8100`
4. タイプ（インスタンスが1つの場合のみ）: `claude`

**名前 vs ID:**

| 用途 | 使用される値 |
|-----|-------------|
| 表示・プロンプト | 名前があれば名前、なければID（例: `Kill my-claude?`） |
| 内部処理 | 常にランタイムID（`synapse-claude-8100`） |
| `synapse list` NAME列 | カスタム名、なければタイプ |

**終了時の保存プロンプト（再利用用定義）**:

```text
Save this agent definition for reuse? [y/N]:
```

- `synapse <profile>` の対話起動終了時のみ表示されます（名前が設定されている場合）。
- `--headless` または非TTY環境では表示されません。
- `synapse stop ...` / `synapse kill ...` で停止した場合は表示されません。
- 無効化: `SYNAPSE_AGENT_SAVE_PROMPT_ENABLED=false`

---

### 2.2.2 チーム起動（分割ペイン）

複数エージェントを現在のターミナル環境でまとめて起動します。

**デフォルト動作**: 1番目のエージェントが現在のターミナルを引き継ぎ（handoff）、2番目以降が新しいペインで起動します。`--all-new` を指定すると、全エージェントが新しいペインで起動します（現在のターミナルはそのまま残ります）。

```bash
synapse team start <agent_spec1> <agent_spec2> ... [--layout split|horizontal|vertical] [--all-new]
```

**エージェント指定の拡張形式**:

`profile:name:role:skill_set:port` の形式で、各ペインの起動時に名前やロール、スキルセット、ポートを一括で指定できます（コロン区切り）。ポートは通常自動割り当てされるため、手動指定は不要です。
`profile` の代わりに、保存済みエージェントの ID / 名前（例: `steady-builder`, `expert`）も指定できます。

```bash
# 基本（claude=現在のターミナル、gemini,codex=新しいペイン）
synapse team start claude gemini codex

# 保存済みエージェントID/名前で起動
synapse team start steady-builder gemini
synapse team start expert gemini:analyst

# 名前とスキルセットを指定して起動
synapse team start claude:Coder:dev gemini:Reviewer::review-set

# ロールのみ指定して起動
synapse team start codex::tester

# 全員を新しいペインで起動（現在のターミナルは残る）
synapse team start claude gemini --all-new

# ツール固有の引数を '--' の後に渡す（全エージェントに適用）
synapse team start claude gemini -- --dangerously-skip-permissions

# Synapse ネイティブ worktree 分離で起動（全エージェント対応）
synapse team start claude gemini --worktree

# worktree に名前プレフィックスを指定（task-claude-0, task-gemini-1 のように生成）
synapse team start claude gemini --worktree task

# Claude Code 固有の --worktree（従来の方法、Claude のみ対応）
synapse team start claude -- --worktree
```

**例**:

```bash
synapse team start claude gemini codex                    # claude=ここ、他=新ペイン
synapse team start claude gemini --layout horizontal      # 水平分割
synapse team start claude gemini --all-new                # 全員新ペイン
synapse team start claude gemini -- --dangerously-skip-permissions  # 権限プロンプトをスキップ
```

**対応ターミナル**:
- `tmux`
- `iTerm2`
- `Terminal.app`（タブで起動）
- `Ghostty`（AppleScript Cmd+D による分割ペイン）
  - **制約**: Ghostty は AppleScript でフォーカス中のウィンドウ/タブを対象にするため、`spawn` や `team start` の実行中にタブを切り替えると、意図しないタブにエージェントがスポーンされます。コマンド完了まで操作を待ってください。
- `zellij`

**レイアウトの扱い**:
- `horizontal`: 右方向分割を優先
- `vertical`: 下方向分割を優先
- `split`: 自動タイル（環境に応じた分割）

**重複名ガード**:
- `team start` は起動前に name 重複を検証し、重複する場合は起動を中止します
- 保存済みエージェントを指定した場合も、解決後の name で同じ検証を行います

---

### 2.2.3 エージェント単体起動 (synapse spawn) — サブエージェント委任

**spawn はサブエージェント委任です。** 親エージェントが子エージェントを生成してサブタスクを委任します。目的：

- **コンテキスト保護** — 親のコンテキストウィンドウをメインタスクに集中させる
- **効率化・時間短縮** — 独立したサブタスクを並列実行して合計時間を削減
- **精度向上** — 専門ロール付きエージェントに委任して結果の質を高める

親エージェントが常にライフサイクルを管理します: **spawn → send → evaluate → kill**

#### クロスモデル生成の推奨

spawn する際は、**異なるモデルタイプ**を優先してください:

```bash
# Claude が Gemini を spawn（クロスモデル）
synapse spawn gemini --worktree --name Tester --role "テスト担当"
```

**理由**:
1. 異なるモデルの強みを活用（品質向上）
2. プロバイダー間でトークン使用量を分散（レート制限回避）
3. コードレビューや問題解決に新鮮な視点を提供

#### ワーカーエージェントの自律性

マネージャーだけでなく、**ワーカーエージェントもサブタスクの委任・生成が可能**です:
- 独立したサブタスクがある場合、ヘルパーを spawn（異なるモデルタイプを推奨）
- レビューが必要な場合、別のエージェントに依頼（異なるモデルで新鮮な視点）
- スコープ外の作業を発見した場合、自分でやらずに委任
- **必須**: spawn したエージェントは完了後に必ず kill: `synapse kill <name> -f`

#### いつ spawn するか

| 状況 | アクション | 理由 |
|------|------------|------|
| タスクが小さく自分の専門内 | **自分で実行** | オーバーヘッドなし |
| 別のエージェントが稼働中で READY | **`synapse send` で既存エージェントに依頼** | spawn 前に既存を再利用 |
| タスクが大きく自分のコンテキストを消費する | **`synapse spawn` で新規生成（異なるモデル推奨）** | コンテキスト保護 + 専門ロールで精度向上 |
| 独立した並列サブタスクがある | **`synapse spawn` で N 体生成（異なるモデル推奨）** | 並列実行で時間短縮 + レート制限分散 |

**エージェント数のルール:**
1. ユーザーが数を指定 → **その数に従う（最優先）**
2. 指定なし → 親エージェントがタスク構造から適切な数と役割を決定

#### 基本ライフサイクル

```bash
# 1. ヘルパーを spawn
synapse spawn gemini --name Tester --role "テスト担当"

# 2. READY 確認（送信前に必ず確認）
synapse list   # Tester が STATUS=READY になるまで待機

# 3. タスクを送信（結果を待つ）
synapse send Tester "src/auth.py のユニットテストを書いて" --wait

# 4. 結果を評価 — 不十分なら再送信（kill して再 spawn しない）
synapse send Tester "期限切れトークンのエッジケースも追加して" --wait

# 5. 完了 — 必ず kill する（親がライフサイクルを管理）
synapse kill Tester -f
```

#### 結果の評価方法

1. **返答内容を読む** — 依頼した内容に対応しているか？
2. **成果物を検証** — 必要に応じて `git diff`、`pytest`、ファイル確認
3. **判断:**
   - 十分 → `synapse kill <child> -f`
   - 不十分 → 追加指示を re-send（kill して再 spawn しない）

#### CLI コマンド

```bash
synapse spawn claude                          # 新しいペインで Claude を起動
synapse spawn Cody                            # 保存済みエージェント名で起動
synapse spawn steady-builder                  # 保存済みエージェントIDで起動
synapse spawn gemini --port 8115              # ポートを指定して起動
synapse spawn claude --name Tester --role "テスト担当"  # 名前とロールを指定
synapse spawn claude --terminal tmux          # 使用するターミナルを指定
# デフォルトで layout="auto"（スポーンゾーンタイリング）でペインが作成されます
# 最初の spawn でゾーンペインを作成し、以降の spawn はそのゾーン内でタイリング
# SYNAPSE_SPAWN_PANES 環境変数（tmux セッション環境）でゾーンペイン ID を追跡
# tmux ペインには自動的に "synapse(profile)" タイトルが設定されます

# ツール固有の引数を '--' の後に渡す
synapse spawn claude -- --dangerously-skip-permissions

# Synapse ネイティブ worktree 分離で起動（全エージェント対応）
synapse spawn claude --worktree
synapse spawn claude --worktree feature-auth --name Auth --role "auth implementation"
synapse spawn gemini -w                          # 短縮フラグ

# Claude Code 固有の --worktree（従来の方法、Claude のみ対応）
synapse spawn claude --name Worker --role "機能実装担当" -- --worktree
synapse spawn expert                           # 保存済みエージェント名で起動
```

#### 保存済みエージェント定義（`synapse agents`）

保存済みエージェント定義を作成すると、`--agent` / `-A` フラグや `synapse spawn` / `synapse team start` で再利用できます。

```bash
# 追加（id は petname 形式: 小文字+ハイフン区切り、例: sharp-checker, calm-lead）
synapse agents add sharp-checker --name Rex --profile codex --role @./roles/tester.md --skill-set developer --scope project

# 一覧（TTYでは見やすいRich TUI表示）
synapse agents list

# 詳細確認
synapse agents show Rex

# 削除
synapse agents delete sharp-checker

# 起動時に使用
synapse codex --agent sharp-checker              # プロファイルショートカットで使用
synapse spawn sharp-checker                      # spawn で使用
synapse team start sharp-checker steady-builder  # team start で使用
```

**保存先とスコープ:**

| スコープ | パス | 優先順位 |
|---------|------|---------|
| Project | `.synapse/agents/*.agent` | 高（優先） |
| User | `~/.synapse/agents/*.agent` | 低（フォールバック） |

IDが重複する場合、Project スコープが User スコープより優先されます。

#### Worktree の注意事項

**Synapse ネイティブ worktree（推奨）**:

- `--worktree` / `-w` は **Synapse のフラグ**であり、`--` の前に指定します（例: `synapse spawn gemini --worktree`）。
- **全エージェント対応**: Claude, Gemini, Codex, OpenCode, Copilot のすべてで使用可能です。
- Worktree は `.synapse/worktrees/<name>/` に作成され、ブランチ `worktree-<name>` で動作します。
- `synapse list` で `[WT]` プレフィックスにより worktree エージェントを識別できます。
- 環境変数 `SYNAPSE_WORKTREE_PATH`、`SYNAPSE_WORKTREE_BRANCH`、`SYNAPSE_WORKTREE_BASE_BRANCH` がエージェントプロセスに設定されます。
- `.synapse/worktrees/` を `.gitignore` に追加することを推奨します。

**プロファイルショートカット**:

```bash
# 現在のターミナルで worktree 内のエージェントを直接起動
synapse claude --worktree my-feature
synapse gemini --worktree review --name Reviewer --role "code reviewer"
```

**Claude Code 固有の --worktree（従来の方法）**:

- `-- --worktree` は Claude Code のフラグであり、Claude のみが対応します。Worktree は `.claude/worktrees/` に作成されます。
- 通常は Synapse ネイティブの `--worktree` を使用してください（エージェント非依存）。

**共通の注意事項**:

- `.gitignore` に記載されたファイル（`.env`、`.venv/`、`node_modules/`）は worktree にコピーされません。必要に応じて `uv sync`、`npm install`、`.env` のコピーを実行してください。
- 終了時: 未コミットの変更 **およびベースブランチ以降の新規コミット** がない worktree は自動削除されます。変更またはコミットがある場合、対話モードでは保持/削除の確認プロンプトが表示され、非対話モード（headless）では worktree を保持してパスとブランチを出力します。
- ブランチのクリーンアップ: kill 後、worktree ブランチが残る場合があります。メインブランチにマージするか、不要なら削除してください:
  ```bash
  git merge worktree-feature-auth    # マージ
  git branch -d worktree-feature-auth # 削除
  ```

#### 技術的な注意事項

- **Headless モード**: `synapse spawn` は自動的に `--no-setup --headless` を付与し、対話型セットアップと承認をスキップします。A2A サーバーと初期指示は有効です。
- **Readiness 確認**: spawn 後、エージェントが登録されるまで待機し、未登録の場合は `synapse send` のコマンド例を含む警告を表示します。
- **ペイン自動クローズ**: エージェント終了時、対応するペインは自動的に閉じます（tmux, zellij, iTerm2, Terminal.app, Ghostty）。
- **既知の制限 ([#237](https://github.com/s-hiraoku/synapse-a2a/issues/237))**: spawn されたエージェントは `synapse reply` が使用できません（PTY インジェクションで送信者情報が登録されないため）。`synapse send <target> "message" --from <spawned-agent-id>` を使用してください。
- **終了時保存プロンプト**: 対話起動終了時に保存確認が表示されます。無効化する場合は `SYNAPSE_AGENT_SAVE_PROMPT_ENABLED=false` を設定してください。

---

### 2.3 一覧表示

```bash
synapse list
```

**Rich TUI モード（デフォルト）**:

`synapse list` は常に Rich TUI によるインタラクティブな表示で起動します。ファイルウォッチャーにより、エージェントのステータス変更時に自動更新されます（10秒間隔のフォールバックポーリング）。

```bash
synapse list                      # 自動更新 Rich TUI
synapse list --json               # JSON 配列出力（AI/スクリプト向け）
```

**Rich TUI モードの機能**:
- 色付きステータス表示（READY=緑、PROCESSING=黄）
- ファイルウォッチャーによる自動更新（変更検出時に即座に反映）
- **インタラクティブ操作**: 数字キー（1-9）または ↑/↓ キーでエージェントを選択
- **ターミナルジャンプ**: Enter または j キーで選択したエージェントのターミナルに移動
- **エージェント終了**: k キーで選択したエージェントを終了（確認ダイアログあり）
- **フィルタ**: / キーで TYPE / NAME / WORKING_DIR による絞り込み
- `ESC` キーでフィルタ/選択解除、`q` で終了

**出力例（Rich TUI モード）**:

```
╭─────────────── Synapse A2A v0.3.11 - Agent List ───────────────╮
│ ╭───┬──────────────────────┬──────────┬────────────┬───────────┬───────────┬────────────┬──────────────╮ │
│ │ # │ ID                   │ NAME     │ STATUS     │ CURRENT   │ TRANSPORT │ WORKING_DIR│ EDITING_FILE │ │
│ ├───┼──────────────────────┼──────────┼────────────┼───────────┼───────────┼────────────┼──────────────┤ │
│ │ 1 │ synapse-claude-8100  │ my-claude│ PROCESSING │ Reviewing │ UDS→      │ project    │ auth.py      │ │
│ │ 2 │ synapse-gemini-8110  │ -        │ PROCESSING │ -         │ →UDS      │ other      │ -            │ │
│ │ 3 │ synapse-codex-8120   │ tester   │ READY      │ -         │ -         │ third      │ -            │ │
│ ╰───┴──────────────────────┴──────────┴────────────┴───────────┴───────────┴────────────┴──────────────┘ │
╰────────────────────── Last updated: 2024-01-15 10:30:45 ─────────────────────╯
[1-3/↑↓: select] [Enter/j: jump] [K: kill] [/: filter] [ESC: clear] [q: quit]
```

**表示カラム（`list.columns`）**:

| カラム | 説明 |
|--------|------|
| ID | ランタイムID（例: `synapse-claude-8100`） |
| NAME | カスタム名（設定されている場合） |
| TYPE | エージェントタイプ (claude, gemini, codex など) |
| ROLE | ロール説明（設定されている場合） |
| STATUS | 現在のステータス (READY, WAITING, PROCESSING, DONE) |
| TRANSPORT | 通信トランスポート表示 |
| CURRENT | 現在のタスクプレビュー |
| WORKING_DIR | 作業ディレクトリ |
| SKILL_SET | 適用されているスキルセット名（任意） |
| EDITING_FILE | 編集中のファイル（File Safety有効時のみ表示） |

**JSON 出力モード**:

`synapse list --json` は、エージェント一覧を JSON 配列として出力します。AI やスクリプトからのプログラム的な消費に適しています。各オブジェクトには `agent_id`, `agent_type`, `name`, `role`, `skill_set`, `port`, `status`, `pid`, `working_dir`, `endpoint`, `transport`, `current_task_preview`, `task_received_at`、および任意で `editing_file` が含まれます。

**Note**: **TRANSPORT 列**は通信状態をリアルタイム表示します。
- `UDS→` / `TCP→`: エージェントが UDS/TCP で送信中
- `→UDS` / `→TCP`: エージェントが UDS/TCP で受信中
- `-`: 通信なし

**Note**: 行を選択すると詳細パネルが表示され、Port/PID/Endpoint/フルパスなどが確認できます。

---

### 2.4 メッセージ送信

```bash
synapse send <agent> "メッセージ" [--from AGENT_ID] [--priority <n>] [--wait | --notify | --silent]
```

**オプション**:

| オプション | 短縮形 | デフォルト | 説明 |
|-----------|--------|-----------|------|
| `target` | - | 必須 | 送信先エージェント |
| `message` | - | - | メッセージ内容（positional / `--message-file` / `--stdin` のいずれか） |
| `--message-file` | `-F` | - | ファイルからメッセージ読み込み（`-` で stdin） |
| `--stdin` | - | false | 標準入力からメッセージ読み込み |
| `--from` | `-f` | - | 送信元エージェントID（省略可: `SYNAPSE_AGENT_ID` から自動検出） |
| `--priority` | `-p` | 3 | 優先度 (1-5) |
| `--attach` | `-a` | - | ファイル添付（複数指定可） |
| `--wait` | - | - | 同期待機モード - 送信側がブロックして `synapse reply` を待つ |
| `--notify` | - | - | 非同期通知モード - タスク完了時に通知を受け取る（デフォルト） |
| `--silent` | - | - | ワンウェイモード - 送りっぱなし、返信・通知不要 |
| `--force` | - | false | 作業ディレクトリの不一致チェックをバイパスして送信 |

**Note**: `a2a.flow=auto`（デフォルト）の場合、フラグなしは `--notify`（非同期通知）になります。待たない場合は `--silent` を指定してください。`--silent` でも受信側完了時に sender 側 history のステータスは best-effort で更新されます（`sent` → `completed` / `failed` / `canceled`、通知不達時は `sent` のまま）。

**レスポンスモードの使い分け**:

| メッセージ種類 | モード | 例 |
|---------------|--------|-----|
| 質問 | `--wait` | "現在のステータスは？" |
| 分析依頼 | `--wait` | "このコードをレビューして" |
| 結果を期待するタスク | `--notify` | "テストを実行して結果を報告して" |
| 委任タスク（fire-and-forget） | `--silent` | "このバグを修正してコミットして" |
| 通知 | `--silent` | "FYI: ビルドが完了しました" |

デフォルトは `--notify`（非同期通知）です。

**作業ディレクトリの不一致チェック**: `synapse send` は送信元の CWD とターゲットエージェントの `working_dir` が一致するか自動的に確認します。異なる場合は警告を表示し、終了コード 1 で終了します。同一ディレクトリのエージェント一覧、または `synapse spawn` の提案が表示されます。`--force` でチェックをバイパスできます。

**例**:

```bash
# 結果を期待するタスク（非同期通知 - デフォルト）
synapse send codex "結果を教えて" --notify

# 同期待機（レスポンスを待つ）
synapse send codex "現在の進捗を報告して" --wait

# 委任タスク、fire-and-forget
synapse send codex "設計を書いて" --silent

# 緊急停止
synapse send claude "処理を止めて" --priority 5

# ファイルから送信（'-' は stdin）
synapse send codex --message-file ./message.txt --silent
cat ./message.txt | synapse send codex --message-file - --silent

# 添付ファイル付き（同期待機）
synapse send codex "このファイルを見て" -a ./a.py -a ./b.txt --wait

# 作業ディレクトリが異なるエージェントに強制送信
synapse send codex "設計して" --force

# 明示指定（サンドボックス環境向け）
synapse send codex "設計して" --from synapse-claude-8100
```

**関連**:

```bash
synapse trace <task_id>
```

### 2.5 メッセージへの返信

```bash
synapse reply "返信メッセージ" [--from <your_agent_id>] [--to SENDER_ID] [--list-targets] [--fail REASON]
```

Synapseは返信を期待する送信者情報を自動的に追跡し、適切な送信者に返信します。

**オプション**:

| オプション | 説明 |
|-----------|------|
| `--from`, `-f` | 送信元エージェントID（省略可: 自動検出。サンドボックス環境で必要） |
| `--to` | 返信先の sender_id を指定（複数の送信者がいる場合に使用） |
| `--list-targets` | 返信可能なターゲット一覧を表示 |
| `--fail` | 通常のテキスト返信の代わりに失敗返信を送信（理由を指定） |

**例**:

```bash
# 最新の送信者に返信（デフォルト）
synapse reply "分析結果です..."

# 特定の送信者に返信
synapse reply "タスク完了しました" --to synapse-claude-8100

# 返信可能なターゲットを確認
synapse reply --list-targets
```

---

### 2.6 ログ表示

```bash
# 最新 50 行を表示
synapse logs claude

# 最新 200 行を表示
synapse logs claude -n 200

# リアルタイム監視（tail -f）
synapse logs claude --follow
```

---

### 2.6 外部エージェント管理

外部の Google A2A 互換エージェントを管理するコマンドです。

#### 外部エージェントの発見・登録

```bash
synapse external add <url> [--alias ALIAS]
```

**例**:

```bash
synapse external add http://other-agent:9000
synapse external add https://ai.example.com --alias myai
```

Agent Card (`/.well-known/agent.json`) を取得してエージェント情報を登録します。

#### 登録済みエージェント一覧

```bash
synapse external list
```

**出力例**:

```
ALIAS           NAME                 URL                                      LAST SEEN
------------------------------------------------------------------------------------------
myai            Example AI           https://ai.example.com                   2025-01-15T10:30:00
other           Other Agent          http://other-agent:9000                  Never
```

#### 外部エージェントにメッセージ送信

```bash
synapse external send <alias> <message> [--wait]
```

**例**:

```bash
synapse external send myai "Hello!"
synapse external send myai "Process this task" --wait
```

`--wait` オプションで完了まで待機します。

#### 外部エージェント情報表示

```bash
synapse external info <alias>
```

#### 外部エージェント削除

```bash
synapse external remove <alias>
```

---

### 2.7 スキル管理

Synapse にはスキルの発見・管理・デプロイを行う統合スキルマネージャーが内蔵されています。

#### スキルスコープ

| スコープ | パス | 説明 |
|---------|------|------|
| **Synapse** | `~/.synapse/skills/` | 中央ストア（ここから各エージェントにデプロイ） |
| **User** | `~/.claude/skills/`, `~/.agents/skills/` 等 | ユーザー全体で共有 |
| **Project** | `./.claude/skills/`, `./.agents/skills/` 等 | プロジェクトローカル |
| **Plugin** | `./plugins/*/skills/` | プラグイン付属（読み取り専用） |

#### TUI モード

```bash
synapse skills
```

インタラクティブ TUI が起動し、以下の操作が可能です：

- **Manage Skills** - スコープ別にスキルを閲覧・削除・移動・デプロイ
- **Skill Sets** - 名前付きグループの管理
- **Install Skill** - スキルのインポート・新規作成
- **Deploy Skills** - 中央ストアからエージェントへのデプロイ
- **Create Skill** - Anthropic 方法論によるスキル作成ガイド

**Manage Skills** ではまずスコープを選択し、そのスコープのスキルだけを表示します。
各スキル行には `[C✓ A✓]` インジケーターが付き、どのエージェントディレクトリに存在するかが一目で分かります：

| 記号 | ディレクトリ | 対象エージェント |
|------|-------------|-----------------|
| **C** | `.claude/skills/` | Claude |
| **A** | `.agents/skills/` | Codex, OpenCode, Copilot, Gemini |

スキルの詳細画面では **Deploy Status** セクションが表示され、User / Project 両スコープでの各エージェントへのデプロイ状態を確認できます。

#### 非インタラクティブコマンド

```bash
# 一覧・詳細
synapse skills list                               # 全スコープのスキル一覧
synapse skills list --scope synapse               # 中央ストアのみ
synapse skills show <name>                        # スキル詳細

# 管理
synapse skills delete <name> [--force]            # スキル削除
synapse skills move <name> --to <scope>           # スコープ間移動

# 中央ストア操作
synapse skills import <name> [--from user|project]  # エージェントdirから中央ストアへコピー
synapse skills deploy <name> --agent claude,codex --scope user  # 中央ストアからデプロイ
synapse skills add <repo>                         # リポジトリからインストール（npx skills ラッパー）
synapse skills create                             # スキル作成ガイド表示（anthropic-skill-creator使用）

# スキルセット（名前付きグループ）
synapse skills set list                           # スキルセット一覧
synapse skills set show <name>                    # スキルセット詳細
synapse skills apply <target> <set_name>          # 稼働中のエージェントにスキルセットを適用
synapse skills apply <target> <set_name> --dry-run  # 変更をプレビュー（適用しない）
```

#### デフォルトスキルセット

Synapse には 6 つの組み込みスキルセットが用意されています（`.synapse/skill_sets.json` で定義）：

| スキルセット | 説明 | スキル |
|-------------|------|--------|
| **architect** | システムアーキテクチャと設計 — 設計ドキュメント、API 設計、コードレビュー | synapse-a2a, system-design, api-design, code-review, project-docs |
| **developer** | 実装と品質 — テストファースト開発、リファクタリング、コード簡素化 | synapse-a2a, test-first, refactoring, code-simplifier, agent-memory |
| **reviewer** | コードレビューとセキュリティ — 構造化レビュー、セキュリティ監査、コード簡素化 | synapse-a2a, code-review, security-audit, code-simplifier |
| **frontend** | フロントエンド開発 — React/Next.js パフォーマンス、コンポーネント構成、デザインシステム、アクセシビリティ | synapse-a2a, react-performance, frontend-design, react-composition, web-accessibility |
| **manager** | マルチエージェント管理 — タスク委任、進捗監視、品質検証、クロスレビュー、再インストラクション | synapse-a2a, synapse-manager, task-planner, agent-memory, code-review, synapse-reinst |
| **documentation** | ドキュメンテーション専門 — 監査、再構成、同期、プロジェクトドキュメントの維持 | synapse-a2a, project-docs, api-design, agent-memory |

#### デプロイフロー

```
synapse skills add <repo>  ─┐
                            ├→ npx skills add <repo> → ~/.claude/skills/
                            └→ 自動インポート → ~/.synapse/skills/ (中央ストア)
                                                    ↓ [deploy]
                              ~/.claude/skills/, ~/.agents/skills/ ...  (ユーザ)
                              ./.claude/skills/, ./.agents/skills/ ...  (プロジェクト)
```

---

### 2.8 セッション管理（Session Save/Restore）

実行中のエージェント構成を名前付きスナップショットとして保存し、後から復元できます。チーム構成の再利用に便利です。

#### 基本操作

```bash
# 現在のディレクトリで動作中のエージェントをセッションとして保存
synapse session save my-team

# 保存済みセッション一覧
synapse session list

# セッション詳細（エージェント構成）を確認
synapse session show my-team

# セッションを復元（保存されたエージェントを spawn）
synapse session restore my-team

# セッションを削除
synapse session delete my-team
synapse session delete my-team --force  # 確認なし
```

#### スコープ

| スコープ | パス | 説明 |
|---------|------|------|
| **Project**（デフォルト） | `.synapse/sessions/` | プロジェクトローカル |
| **User** | `~/.synapse/sessions/` | ユーザー全体で共有 |

```bash
# ユーザースコープに保存
synapse session save my-team --user

# ユーザースコープのセッションのみ表示
synapse session list --user

# 特定ディレクトリを project スコープとして保存
synapse session save my-team --workdir /path/to/project
```

#### 復元オプション

```bash
# worktree 分離で復元
synapse session restore my-team --worktree

# 各エージェントの CLI 会話セッションを再開して復元
synapse session restore my-team --resume

# worktree + resume を併用
synapse session restore my-team --worktree --resume

# ツール固有の引数を追加して復元
synapse session restore my-team -- --dangerously-skip-permissions
```

**`--resume` の動作**:
- 保存時にレジストリから取得した `session_id` を使い、各エージェントの CLI 会話を再開します
- エージェントごとの resume 引数: claude (`--resume`/`--continue`), gemini (`--resume`), codex (`resume`/`resume --last`), copilot (`--resume`), opencode (未対応)
- `session_id` が保存されている場合はそのIDで再開、ない場合は最新セッションを再開
- resume に失敗した場合（10秒以内にプロセスが終了）、resume 引数なしで自動リトライします

#### 保存される情報

各エージェントについて以下が保存されます:
- **profile**: エージェントタイプ（claude, gemini, codex 等）
- **name**: カスタム名
- **role**: ロール
- **skill_set**: スキルセット
- **worktree**: worktree 使用の有無
- **session_id**: CLI 会話セッションID（`--resume` 復元に使用）

---

### 2.9 ワークフロー管理（Workflow）

YAML ベースのメッセージシーケンスを定義し、複数のエージェントに順番にメッセージを送信するワークフローを作成・実行できます。繰り返し行うマルチエージェント操作の自動化に便利です。

#### 基本操作

```bash
# ワークフローテンプレートを作成
synapse workflow create my-pipeline

# 保存済みワークフロー一覧
synapse workflow list

# ワークフロー詳細を確認
synapse workflow show my-pipeline

# ワークフローを実行（ステップを順番に実行）
synapse workflow run my-pipeline

# ドライランで実行内容をプレビュー（実際には送信しない）
synapse workflow run my-pipeline --dry-run

# エラー発生時も残りのステップを継続
synapse workflow run my-pipeline --continue-on-error

# ワークフローを削除
synapse workflow delete my-pipeline
synapse workflow delete my-pipeline --force  # 確認なし

# 全ワークフローからスキルを再生成（孤立スキルも削除）
synapse workflow sync
```

#### スコープ

| スコープ | パス | 説明 |
|---------|------|------|
| **Project**（デフォルト） | `.synapse/workflows/` | プロジェクトローカル |
| **User** | `~/.synapse/workflows/` | ユーザー全体で共有 |

```bash
# ユーザースコープに作成
synapse workflow create my-pipeline --user

# ユーザースコープのワークフローのみ表示
synapse workflow list --user
```

#### YAML 定義の形式

`synapse workflow create` で生成されるテンプレートを編集します:

```yaml
name: my-pipeline
description: コードレビューパイプライン
trigger: "code review pipeline"   # スキル自動生成時のトリガーキーワード（任意）
auto_spawn: true                  # 対象エージェント未起動時に自動スポーン（任意）
steps:
  - target: claude
    message: "src/auth.py のコードレビューを実施して"
    priority: 3
    response_mode: notify
  - target: gemini
    message: "src/auth.py のセキュリティ監査を実施して"
    priority: 3
    response_mode: notify
  - target: codex
    message: "src/auth.py のテストを書いて"
    priority: 3
    response_mode: silent
  - kind: subworkflow
    workflow: post-impl-checks
```

#### ワークフローレベルのフィールド

| フィールド | 必須 | デフォルト | 説明 |
|-----------|------|-----------|------|
| `name` | Yes | - | ワークフロー名 |
| `description` | No | - | ワークフローの説明 |
| `trigger` | No | `""` | スキル自動生成時のトリガーキーワード（例: `"code review pipeline"`） |
| `auto_spawn` | No | `false` | `true` の場合、対象エージェントが未起動なら自動でスポーンする |

#### ステップのフィールド

| フィールド | 必須 | デフォルト | 説明 |
|-----------|------|-----------|------|
| `kind` | No | `send` | ステップ種別。`send` または `subworkflow` |
| `target` | Yes | - | 送信先エージェント（名前、ID、タイプ） |
| `message` | Yes | - | 送信メッセージ |
| `priority` | No | 3 | 優先度（1-5） |
| `response_mode` | No | notify | `wait`（タスク完了までポーリング）/ `notify` / `silent` |
| `workflow` | `subworkflow` のとき必須 | - | 呼び出す子 workflow 名 |

`kind: send` では従来どおり `target` と `message` を使います。

`kind: subworkflow` では `workflow` を指定し、`target` / `message` は省略します:

```yaml
steps:
  - kind: subworkflow
    workflow: review-and-test
```

ネストした workflow は再帰的に展開されます。`A -> B -> A` のような循環参照はエラーになり、ネスト深さは 10 までです。

#### Canvas からの実行

Canvas のブラウザ UI（`#/workflow`）からもワークフローを実行できます。ワークフローを選択して **Run** ボタンをクリックします。

- Canvas サーバーが A2A HTTP で各 step を直接送信します
- 送信元は `canvas-workflow` / `Workflow` として識別され、`synapse reply` は Canvas に返ります
- 各ステップの進捗がリアルタイムで更新されます（SSE 経由）
- 成功したステップの受理結果は「Output」セクションで展開表示可能
- エラーは人間が読みやすいメッセージに変換されます
- `response_mode: wait` のステップはターゲットエージェントのタスク完了までポーリングします（最大 10 分）
- ターゲットがビジー（HTTP 409）の場合、自動リトライを行います
- `auto_spawn` 設定（ワークフローレベル・ステップレベル）が反映されます
- 完了時にトースト通知が表示されます

> **注意**: 別ディレクトリで同名のエージェントが動作中の場合、名前衝突エラーが表示されます。ワークフローの `target` を変更するか、既存のエージェントを停止してください。

#### スキル自動生成

ワークフローを作成（`synapse workflow create`）すると、自動的に SKILL.md が `.claude/skills/<name>/` と `.agents/skills/<name>/` に生成されます。これにより、ワークフローがスラッシュコマンドスキルとして検出可能になります。

- 自動生成されたスキルには `<!-- synapse-workflow-autogen -->` マーカーが付与され、手動作成のスキルと区別されます
- 手動作成のスキルは上書きされません（マーカーが存在しないディレクトリはスキップ）
- ワークフロー削除時（`synapse workflow delete`）は対応するスキルも自動削除されます
- `synapse workflow sync` で全ワークフローからスキルを一括再生成し、対応するワークフローが存在しない孤立スキルを削除します

---

## 3. @Agent 記法

インタラクティブモードで他のエージェントにメッセージを送信する記法です。

### 3.1 基本構文

```
@<agent_name> <message>
```

**パターン**:

```mermaid
flowchart LR
    At["@"]
    Agent["agent_name"]
    Message["message"]

    At --> Agent --> Message
```

> **Note**: `@Agent` パターンはデフォルトでレスポンスを待ちます。レスポンスを待たない場合は `synapse send` コマンドを使用してください。

### 3.2 通常送信

```text
# ローカルエージェント
@codex 設計をレビューして
@gemini このコードを最適化して
@claude バグを修正して

# 外部エージェント（事前に synapse external add で登録）
@myai タスクを処理して
```

**フィードバック**:

```
[→ codex (local)]     # ローカルエージェント（緑色）
[→ myai (ext)]        # 外部エージェント（マゼンタ色）
```

送信に成功するとフィードバックが表示されます。

---

### 3.3 レスポンス付き送信

```text
@codex "設計を書いて"
@claude "コードレビューして"
```

**動作**:

1. メッセージを送信
2. 相手が `READY` になるまでポーリング（最大 60 秒）
3. 新しい出力をこの端末に表示

**フィードバック**:

```
[→ codex]
[← codex]
（レスポンス内容）
```

---

### 3.4 クォート処理

メッセージに空白が含まれる場合は、クォートで囲むことができます。

```text
@codex "設計を レビューして"
@codex '設計を レビューして'
```

クォートは自動的に除去されます。

---

### 3.5 エラーケース

**エージェントが見つからない場合**:

```
[✗ unknown not found]
```

赤色のエラーメッセージが表示されます。

---

## 4. HTTP API

### 4.1 メッセージ送信（A2A プロトコル）

#### Task ベースでメッセージ送信

```bash
curl -X POST http://localhost:8100/tasks/send \
  -H "Content-Type: application/json" \
  -d '{"message": {"role": "user", "parts": [{"type": "text", "text": "Hello"}]}}'
```

**リクエスト**:

```json
{
  "message": {
    "role": "user",
    "parts": [{"type": "text", "text": "メッセージ内容"}]
  }
}
```

**レスポンス**:

```json
{
  "task": {
    "id": "uuid-task-id",
    "status": "working",
    "artifacts": [],
    "created_at": "2025-01-15T10:00:00Z",
    "updated_at": "2025-01-15T10:00:00Z"
  }
}
```

`task.id` で状態を追跡可能です。

> **Readiness Gate**: エージェントの初期化完了前に `/tasks/send` や `/tasks/send-priority` にリクエストすると、HTTP 503（`Retry-After: 5`）が返されます。Priority 5（緊急割り込み）と返信メッセージ（`in_reply_to`）はゲートをバイパスします。

#### ステータス確認

```bash
curl http://localhost:8100/status
```

**レスポンス**:

```json
{
  "status": "READY",
  "context": "...最新の出力（最大2000文字）..."
}
```

**status の値**:

| 値 | 説明 |
|----|------|
| `PROCESSING` | 処理中・起動中 |
| `READY` | 待機中（プロンプト表示中） |
| `NOT_STARTED` | 未起動 |

---

### 4.2 Google A2A 互換 API（推奨）

Google A2A プロトコルに準拠した API です。エージェント間通信の標準的な方法として、こちらの使用を推奨します。

#### Agent Card 取得

```bash
curl http://localhost:8100/.well-known/agent.json
```

エージェントの能力やスキルを公開します。

#### Task ベースでメッセージ送信

```bash
curl -X POST http://localhost:8100/tasks/send \
  -H "Content-Type: application/json" \
  -d '{
    "message": {
      "role": "user",
      "parts": [{"type": "text", "text": "Hello!"}]
    }
  }'
```

**レスポンス**:

```json
{
  "task": {
    "id": "uuid-...",
    "status": "working",
    "artifacts": [],
    "created_at": "2025-01-15T10:00:00Z",
    "updated_at": "2025-01-15T10:00:00Z"
  }
}
```

#### Task 状態取得

```bash
curl http://localhost:8100/tasks/{task_id}
```

---

### 4.3 外部エージェント管理 API

#### 外部エージェントを発見・登録

```bash
curl -X POST http://localhost:8100/external/discover \
  -H "Content-Type: application/json" \
  -d '{"url": "http://other-agent:9000", "alias": "other"}'
```

#### 外部エージェント一覧

```bash
curl http://localhost:8100/external/agents
```

#### 外部エージェントにメッセージ送信

```bash
curl -X POST http://localhost:8100/external/agents/other/send \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello!", "wait_for_completion": true}'
```

---

## 5. Priority（優先度）

### 5.1 優先度レベル

```mermaid
flowchart TB
    subgraph Normal["通常 (1-4)"]
        N["stdin に書き込み"]
    end

    subgraph Emergency["緊急 (5)"]
        E1["SIGINT 送信"]
        E2["stdin に書き込み"]
        E1 --> E2
    end
```

| Priority | 動作 | 用途 |
|----------|------|------|
| 1-4 | stdin に直接書き込み | 通常のメッセージ送信 |
| 5 | SIGINT を送ってから書き込み | 緊急停止・強制介入 |

---

### 5.2 緊急停止の例

**CLI から**:

```bash
synapse send claude "処理を止めて" --priority 5
```

**HTTP API から**:

```bash
# 推奨: A2A プロトコル
curl -X POST "http://localhost:8100/tasks/send-priority?priority=5" \
  -H "Content-Type: application/json" \
  -d '{"message": {"role": "user", "parts": [{"type": "text", "text": "止まれ"}]}}'
```

**@Agent から**:

現在の実装では、`@Agent` 記法は常に priority 1 で送信されます。
緊急停止には CLI または HTTP API を使用してください。

---

## 6. 運用パターン

### 6.1 開発チーム構成

```mermaid
flowchart LR
    Human["人間<br/>（マネージャー）"]
    Claude["Claude<br/>（コード担当）"]
    Codex["Codex<br/>（設計担当）"]
    Gemini["Gemini<br/>（レビュー担当）"]
    OpenCode["OpenCode<br/>（補助担当）"]

    Human -->|"@claude 実装して"| Claude
    Human -->|"@codex 設計して"| Codex
    Human -->|"@opencode 調査して"| OpenCode
    Claude -->|"@codex 設計確認"| Codex
    Claude -->|"@gemini レビュー依頼"| Gemini
    Gemini -->|"@claude 修正依頼"| Claude
```

---

### 6.2 1 端末から横断指示

```text
# Claude の端末から
@codex アーキテクチャ設計をして
@gemini 設計のレビューをして
```

---

### 6.3 CI/スクリプトからの自動指示

```bash
#!/bin/bash

# テスト実行を Claude に依頼（A2A プロトコル）
RESULT=$(curl -s -X POST "http://localhost:8100/tasks/send" \
  -H "Content-Type: application/json" \
  -d '{"message": {"role": "user", "parts": [{"type": "text", "text": "テストを実行して"}]}}')

TASK_ID=$(echo $RESULT | jq -r '.task.id')

# タスクの完了をポーリング
while true; do
  TASK=$(curl -s "http://localhost:8100/tasks/$TASK_ID")
  STATUS=$(echo $TASK | jq -r '.status')
  if [ "$STATUS" = "completed" ]; then
    echo "Done!"
    echo $TASK | jq -r '.artifacts[0].data'
    break
  fi
  sleep 5
done
```

---

### 6.4 ウォッチドッグパターン

別のエージェントを監視し、必要に応じて介入する。

```bash
# ステータス確認
curl http://localhost:8120/status

# READY なのに作業が終わっていない場合に nudge
synapse send codex "進捗を報告して" --priority 1

# 応答がない場合は緊急介入
synapse send codex "状況を報告して" --priority 5
```

---

### 6.5 プロアクティブコラボレーション

エージェントはタスク開始前に、コラボレーションの機会を自動的に評価します。

**コラボレーション判断フレームワーク:**

| 状況 | アクション |
|------|------------|
| 小さなタスク（5分以内）、自分の専門内 | 自分で実行 |
| 自分の専門外、READY なエージェントが存在 | `synapse send` で委任 |
| 適切なエージェントが存在しない | `synapse spawn` で新規生成（異なるモデル推奨） |
| 行き詰まった、専門外の助けが必要 | `synapse send --wait` で質問 |
| マイルストーン完了 | `synapse send --silent` で進捗報告 |
| パターンや知見を発見 | `synapse memory save` で共有 |

**クロスモデル生成の推奨:**

```bash
# Claude が Gemini を spawn（異なるモデルタイプ）
synapse spawn gemini --worktree --name Tester --role "テスト担当"

# レート制限回避: 1つのモデルが制限された場合、別のモデルに委任
synapse spawn codex --name Helper --role "実装補助"
```

**Synapse 機能の積極的な活用:**

| 機能 | コマンド | 用途 |
|------|---------|------|
| タスクボード | `synapse tasks create/assign/complete` | 作業の透明な追跡 |
| 共有メモリ | `synapse memory save/search` | チーム全体の知識構築 |
| ファイル安全 | `synapse file-safety lock/unlock` | マルチエージェント環境での排他制御 |
| ワークツリー | `synapse spawn --worktree` | ファイル編集の分離 |
| ブロードキャスト | `synapse broadcast` | チーム全体への通知 |
| 履歴 | `synapse history list` | 過去の作業一覧表示 |
| トレース | `synapse trace <task_id>` | タスク横断の追跡 |

**必須クリーンアップ:**
spawn したエージェントは、作業完了後に**必ず** kill してください:
```bash
synapse kill <spawn したエージェント名> -f
synapse list  # クリーンアップを確認
```

---

## 7. 注意事項

### 7.1 IME の挙動

インタラクティブモードでは入力が 1 文字ずつ処理されるため、日本語入力（IME）の挙動が変わる場合があります。

### 7.2 TUI の制限

Ink ベースの TUI（Claude Code など）では、以下の問題が発生する場合があります：

- 画面の再描画が乱れる
- 入力欄が複数表示される

詳細は [troubleshooting.md](troubleshooting.md) を参照してください。

### 7.3 レスポンス待ちのタイムアウト

`@Agent` パターンはデフォルトでレスポンスを待ちます（最大 60 秒）。レスポンスを待たずに送信のみ行いたい場合は、`synapse send --silent` を使用してください。`--silent` では完了通知を待ちませんが、受信側の完了時に sender 側 history の該当タスク（`sent`）を `completed` / `failed` / `canceled` へ best-effort で更新します。

---

## 関連ドキュメント

- [multi-agent-setup.md](multi-agent-setup.md) - セットアップガイド
- [references.md](references.md) - API/CLI リファレンス
- [troubleshooting.md](troubleshooting.md) - トラブルシューティング
