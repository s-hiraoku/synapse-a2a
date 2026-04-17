# Agent Permission Modes Guide

各 CLI エージェントの承認モード一覧と、Synapse の自動承認機能の解説。

## 概要

Synapse でエージェントを spawn / team start すると、デフォルトで各 CLI の承認スキップモードが有効化される。これにより、エージェントは承認待ちで停止せずに自動的に作業を進める。

```bash
# デフォルト: 自動承認有効
synapse spawn claude
synapse team start claude gemini codex

# オプトアウト: 手動承認モード
synapse spawn claude --no-auto-approve
synapse team start claude gemini --no-auto-approve
```

## CLI 別承認モード比較表

| CLI | 自動承認フラグ | サンドボックス | セッション中切替 | 設定ファイル |
|-----|--------------|-------------|----------------|------------|
| Claude Code | `--dangerously-skip-permissions` (= `--permission-mode bypassPermissions`) | なし | `Shift+Tab` | Hooks (PreToolUse) |
| Codex CLI | `--full-auto` | ワークスペース制限 | なし | `~/.codex/config.toml` |
| Gemini CLI | `--yolo` | Docker (デフォルト) | `Ctrl+Y` | `~/.gemini/settings.json` |
| OpenCode | env var | なし | なし | `opencode.json` |
| Copilot CLI | `--allow-all` | なし | `/allow-all` コマンド | なし |

## Claude Code

パーミッションモード:

1. **default** — 起動時のデフォルト。編集とコマンド実行前に確認、読み取りは許可。
2. **acceptEdits** — ファイル編集と fs 系コマンド (mkdir/mv/cp/touch/rm/rmdir/sed) を自動承認、bash は確認。
3. **plan** — 読み取り専用の計画モード。変更を適用せず提案のみ。
4. **auto** — バックグラウンドクラシファイアによる安全性チェック (Research Preview; Sonnet/Opus 4.6+、対象プランのみ)。
5. **dontAsk** — `permissions.allow` と読み取り専用 Bash 以外を全拒否。
6. **bypassPermissions** — 保護パス以外の承認をすべてバイパス。隔離環境 (VM/コンテナ) 専用。

起動フラグ: `--permission-mode <mode>` (例 `--permission-mode acceptEdits`)。
`--dangerously-skip-permissions` は `--permission-mode bypassPermissions` のエイリアス。
設定ファイル: `settings.json` の `permissions.defaultMode` に同名の文字列を指定。
セッション中 `Shift+Tab` で default → acceptEdits → plan を循環 (起動時に bypassPermissions / auto を有効にすると末尾に追加; dontAsk は循環対象外)。

**Synapse での動作:** `--dangerously-skip-permissions` が自動注入される。WAITING 検知時は `y` + Enter を送信。

**v2.0 推奨:** Hooks（PreToolUse イベント）でツール単位の条件付き制御が可能。`--dangerously-skip-permissions` の安全な代替。

## Codex CLI

2軸制御: `approval_policy` × `sandbox_mode`

| モード | フラグ | 説明 |
|--------|-------|------|
| full-auto | `--full-auto` | ワークスペース内の読み書き・コマンド実行は自動承認 |
| never | `-a never` | 承認を一切求めない（サンドボックス制限は有効） |
| yolo | `--dangerously-bypass-approvals-and-sandbox` | 承認とサンドボックスの両方をバイパス |

**Synapse での動作:** `--full-auto`（サンドボックス付き自動承認）が自動注入される。ただしユーザーが `tool_args` に別系統の承認フラグ（`--dangerously-bypass-approvals-and-sandbox`、`--ask-for-approval`、`-a`、`--sandbox`、`-s`）を渡した場合は `--full-auto` 注入をスキップし、フラグ衝突による起動失敗を防ぐ。WAITING 検知時は `y` + Enter を送信。

```bash
# ユーザー指定フラグを優先（--full-auto は注入されない）
synapse spawn codex -- --dangerously-bypass-approvals-and-sandbox
synapse spawn codex -- --ask-for-approval never --sandbox workspace-write
```

設定: `~/.codex/config.toml` のプロファイルで `approval_policy = "never"` を定義し、`codex --profile <name>` で切替可能。

## Gemini CLI

| モード | フラグ | 説明 |
|--------|-------|------|
| yolo | `--yolo` / `-y` | 全ツールコール自動承認。Docker サンドボックスがデフォルト有効 |
| auto_edit | `--approval-mode=auto_edit` | ファイル読み書きのみ自動承認 |
| 特定ツール | `--allowed-tools "ShellTool(git status)"` | 指定ツールのみバイパス |

**Synapse での動作:** `--yolo` が自動注入される。ユーザーが `-y` または `--approval-mode` を明示的に渡した場合は `--yolo` 注入をスキップする。WAITING 検知時は Enter（第一選択肢 "Allow once" を選択）を送信。

セッション中 `Ctrl+Y` でトグル可能。設定: `~/.gemini/settings.json` で `"approvalMode": "auto_edit"` 等。

## OpenCode

| 方法 | 説明 |
|------|------|
| `opencode.json` → `"permission": "allow"` | 全ツール自動承認 |
| env `OPENCODE_DANGEROUSLY_SKIP_PERMISSIONS=true` | 環境変数でも同等 |

**Synapse での動作:** `OPENCODE_DANGEROUSLY_SKIP_PERMISSIONS=true` 環境変数が自動設定される。WAITING 検知時は `a`（Allow）+ Enter を送信。

CLI フラグ（`--dangerously-skip-permissions`）は Feature Request としてオープン中（2026年3月時点）。

## GitHub Copilot CLI

| モード | フラグ | 説明 |
|--------|-------|------|
| yolo | `--yolo` / `--allow-all` | ツール/パス/URL 全許可 |
| no-ask-user | `--no-ask-user` | 明確化質問の抑制 |
| Autopilot | Autopilot モード | 各ステップを自律実行。`--allow-all` との併用で完全自律 |

**Synapse での動作:** `--allow-all` が自動注入される。ユーザーが別名の `--yolo` を明示的に渡した場合は `--allow-all` 注入をスキップする。WAITING 検知時は `1`（Yes）+ Enter を送信。

セッション中 `/yolo` または `/allow-all` コマンドでも有効化可能。

## Synapse の自動承認機構

### 2層構造

1. **起動時（CLI フラグ注入）:** `spawn_agent()` / `prepare_spawn()` がプロファイルの `auto_approve.cli_flag` を `tool_args` に自動追加。これにより CLI 自体のパーミッションシステムがバイパスされる。ユーザーが `tool_args` に `cli_flag` もしくは `alternative_flags` のいずれかを既に指定している場合は注入をスキップし、フラグ衝突を避ける（`--flag` と `--flag=value` の両形式を検出）。

2. **実行時（WAITING 自動応答）:** フラグが効かないケース（一部のプロンプトタイプ、CLI のバージョン差異）に対応。コントローラーが WAITING ステータスを検知し、プロファイル固有の承認応答を PTY に送信。

### 安全制御

| 制御 | デフォルト | 説明 |
|------|-----------|------|
| `max_consecutive` | 0（無制限） | 連続自動承認の上限。0 = 無制限、正の整数で上限設定 |
| `cooldown` | 0.0秒 | 承認間の最小間隔。0.0 = クールダウンなし |
| 安定化遅延 | 0.3秒 | WAITING UI のレンダリング完了を待つ |
| 環境変数 | `SYNAPSE_AUTO_APPROVE=false` | グローバル無効化 |

### プロファイル設定

各プロファイル YAML (`synapse/profiles/*.yaml`) の `auto_approve` セクション:

```yaml
auto_approve:
  cli_flag: "--dangerously-skip-permissions"  # 起動時に注入する CLI フラグ
  # 同一 CLI が受け付ける代替承認フラグ。ユーザーがこれらを tool_args に
  # 渡している場合、cli_flag の注入をスキップしてフラグ衝突を防ぐ。
  # 例（Codex）: --dangerously-bypass-approvals-and-sandbox, -a, --sandbox …
  alternative_flags: []
  runtime_response: "y\r"                      # WAITING 時に送信する応答
  max_consecutive: 0                            # 連続承認上限（0 = 無制限）
  cooldown: 0.0                                # 承認間隔（秒、0.0 = なし）
```

各プロファイルの現在の `alternative_flags`:

| Profile | cli_flag | alternative_flags |
|---------|----------|-------------------|
| Claude Code | `--dangerously-skip-permissions` | （なし） |
| Codex CLI | `--full-auto` | `--dangerously-bypass-approvals-and-sandbox`, `--ask-for-approval`, `-a`, `--sandbox`, `-s` |
| Gemini CLI | `--yolo` | `-y`, `--approval-mode` |
| OpenCode | （env var） | （なし） |
| Copilot CLI | `--allow-all` | `--yolo` |

### 無効化方法

```bash
# コマンド単位
synapse spawn claude --no-auto-approve
synapse team start claude gemini --no-auto-approve

# 環境変数（グローバル）
SYNAPSE_AUTO_APPROVE=false synapse spawn claude

# 手動フラグ指定（auto-approve の CLI フラグ注入をスキップし、自分で指定）
synapse spawn claude --no-auto-approve -- --enable-auto-mode

# auto-approve は有効のまま別系統の承認フラグへ差し替え（Codex 例）
# alternative_flags にマッチするため --full-auto は注入されない
synapse spawn codex -- --dangerously-bypass-approvals-and-sandbox
```

## 権限確認の検知と承認 (Permission Detection)

auto-approve を無効にした場合、spawn したエージェントが権限確認で止まることがある。Synapse はこの状態を検知し、呼び出し元に通知する。

### ステータスの種類

| Synapse status | A2A TaskState | 意味 |
|----------------|---------------|------|
| PROCESSING | working | エージェントが作業中 |
| READY | completed | タスク完了 |
| DONE | completed | タスク完了（直後） |
| **WAITING** | **input_required** | **権限確認やユーザー入力で停止中** |

### 仕組み

```
親エージェント                         子エージェント (spawn)
    |                                      |
    |-- synapse send worker "task" --notify -->|
    |                                      |-- 作業中...
    |                                      |-- 権限確認ダイアログ表示
    |                                      |-- status: WAITING
    |                                      |
    |<-- input_required 通知 (自動) -------|
    |    (permission metadata 付き)         |
    |                                      |
    |-- Approval Gate または承認 API -----> |
    |                                      |-- 実行再開
```

**ポイント:** 子エージェント自身は権限確認中にメッセージを送れない（PTY がブロック中）。代わりに Synapse の FastAPI サーバーが status 変化を検知し、自動的に呼び出し元へ通知する。親側では Approval Gate が structured escalation metadata を受け取り、自動 approve/deny できる。自動処理できない場合だけ従来どおり人手で判断する。

### ユーザーの確認方法

```bash
# 全エージェントの状態確認
synapse list
# → WAITING 状態のエージェントが権限確認で止まっている

# 特定エージェントの詳細
synapse status <agent> --json
# → task の status が "input_required" ならば権限確認待ち
```

Canvas ダッシュボードでもエージェントカードに WAITING 状態が表示される。

### 承認/拒否 API

```bash
# 承認（エージェントの PTY に承認キーストロークが送信される）
curl -X POST http://localhost:<port>/tasks/<task_id>/permission/approve

# 拒否（エージェントの PTY に拒否キーストロークが送信される）
curl -X POST http://localhost:<port>/tasks/<task_id>/permission/deny
```

### エージェント別の承認/拒否キーストローク

| CLI | 承認 (runtime_response) | 拒否 (deny_response) |
|-----|------------------------|---------------------|
| Claude Code | `y` + Enter | `n` + Enter |
| Codex CLI | `y` + Enter | Esc |
| Gemini CLI | Enter | Esc |
| OpenCode | `a` + Enter | `d` + Enter |
| Copilot CLI | `1` + Enter | Esc |

### 通知の受け取り方

| 送信モード | 通知の受け取り |
|-----------|--------------|
| `--notify` (デフォルト) | `input_required` ステータス変更時に自動通知される |
| `--wait` | `input_required` を表示したあと親の介入を待ち続け、承認・拒否・追加入力で終端状態になるまでポーリングする。既定タイムアウトは `SYNAPSE_PARENT_INTERVENTION_TIMEOUT`（1800秒） |
| `--silent` | 通知なし。`synapse list` で手動確認 |
