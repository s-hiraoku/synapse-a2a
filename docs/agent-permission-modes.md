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
| Claude Code | `--dangerously-skip-permissions` | なし | `Shift+Tab` | Hooks (PreToolUse) |
| Codex CLI | `--full-auto` | ワークスペース制限 | なし | `~/.codex/config.toml` |
| Gemini CLI | `--yolo` | Docker (デフォルト) | `Ctrl+Y` | `~/.gemini/settings.json` |
| OpenCode | env var | なし | なし | `opencode.json` |
| Copilot CLI | `--yolo` | なし | `/yolo` コマンド | なし |

## Claude Code

6段階のパーミッションモード:

1. **default** — 全ツール使用前に確認
2. **acceptEdits** — ファイル編集のみ自動承認、bash コマンドは確認
3. **auto** — AI クラシファイア（Sonnet 4.6）が各アクションを評価。`--enable-auto-mode` で起動。Team/Enterprise/API プラン限定
4. **bypassPermissions** — `--dangerously-skip-permissions` で全承認バイパス。サンドボックス環境専用

**Synapse での動作:** `--dangerously-skip-permissions` が自動注入される。WAITING 検知時は `y` + Enter を送信。

**v2.0 推奨:** Hooks（PreToolUse イベント）でツール単位の条件付き制御が可能。`--dangerously-skip-permissions` の安全な代替。

## Codex CLI

2軸制御: `approval_policy` × `sandbox_mode`

| モード | フラグ | 説明 |
|--------|-------|------|
| full-auto | `--full-auto` | ワークスペース内の読み書き・コマンド実行は自動承認 |
| never | `-a never` | 承認を一切求めない（サンドボックス制限は有効） |
| yolo | `--dangerously-bypass-approvals-and-sandbox` | 承認とサンドボックスの両方をバイパス |

**Synapse での動作:** `--full-auto`（サンドボックス付き自動承認）が自動注入される。WAITING 検知時は `y` + Enter を送信。

設定: `~/.codex/config.toml` のプロファイルで `approval_policy = "never"` を定義し、`codex --profile <name>` で切替可能。

## Gemini CLI

| モード | フラグ | 説明 |
|--------|-------|------|
| yolo | `--yolo` / `-y` | 全ツールコール自動承認。Docker サンドボックスがデフォルト有効 |
| auto_edit | `--approval-mode=auto_edit` | ファイル読み書きのみ自動承認 |
| 特定ツール | `--allowed-tools "ShellTool(git status)"` | 指定ツールのみバイパス |

**Synapse での動作:** `--yolo` が自動注入される。WAITING 検知時は Enter（第一選択肢 "Allow once" を選択）を送信。

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

**Synapse での動作:** `--yolo` が自動注入される。WAITING 検知時は `1`（Yes）+ Enter を送信。

セッション中 `/yolo` または `/allow-all` コマンドでも有効化可能。

## Synapse の自動承認機構

### 2層構造

1. **起動時（CLI フラグ注入）:** `spawn_agent()` / `prepare_spawn()` がプロファイルの `auto_approve.cli_flag` を `tool_args` に自動追加。これにより CLI 自体のパーミッションシステムがバイパスされる。

2. **実行時（WAITING 自動応答）:** フラグが効かないケース（一部のプロンプトタイプ、CLI のバージョン差異）に対応。コントローラーが WAITING ステータスを検知し、プロファイル固有の承認応答を PTY に送信。

### 安全制御

| 制御 | デフォルト | 説明 |
|------|-----------|------|
| `max_consecutive` | 20 | 連続自動承認の上限。超過で自動承認停止 |
| `cooldown` | 2.0秒 | 承認間の最小間隔。高速ループ防止 |
| 安定化遅延 | 0.3秒 | WAITING UI のレンダリング完了を待つ |
| 環境変数 | `SYNAPSE_AUTO_APPROVE=false` | グローバル無効化 |

### プロファイル設定

各プロファイル YAML (`synapse/profiles/*.yaml`) の `auto_approve` セクション:

```yaml
auto_approve:
  cli_flag: "--dangerously-skip-permissions"  # 起動時に注入する CLI フラグ
  runtime_response: "y\r"                      # WAITING 時に送信する応答
  max_consecutive: 20                          # 連続承認上限
  cooldown: 2.0                                # 承認間隔（秒）
```

### 無効化方法

```bash
# コマンド単位
synapse spawn claude --no-auto-approve
synapse team start claude gemini --no-auto-approve

# 環境変数（グローバル）
SYNAPSE_AUTO_APPROVE=false synapse spawn claude

# 手動フラグ指定（auto-approve の CLI フラグ注入をスキップし、自分で指定）
synapse spawn claude --no-auto-approve -- --enable-auto-mode
```
