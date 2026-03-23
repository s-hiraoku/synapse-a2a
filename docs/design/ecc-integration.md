# ECC Integration Plan — PTY Observation Layer

> everything-claude-code (ECC) のパターンを Synapse に統合する設計ドキュメント

## 背景

[everything-claude-code](https://github.com/affaan-m/everything-claude-code) は Claude Code 向けのパフォーマンス最適化システム。28 エージェント、116+ スキル、59 コマンド、Hook ベースの自動化を統合している。

### ECC の強み
- 自己学習パイプライン（操作観察 → パターン抽出 → スキル化）
- セットアップ自動化（plan → apply → doctor の 3 段階）
- Hook プロファイル（minimal/standard/strict の切替）
- セッション永続化（NanoClaw: Markdown をDBとして使う永続 REPL）

### ECC の限界
- **Claude Code 専用** — Hook 機構に依存するため他の CLI エージェントに適用できない
- 単一セッション内で閉じた学習 — エージェント間で知識を共有できない
- サブエージェントは Claude の Task tool（プロセス内委譲）のみ

### Synapse の強み
- **マルチ CLI 対応** — Claude, Codex, Gemini, OpenCode, Copilot
- **PTY 制御レイヤー** — 全エージェントの入出力を外側から監視
- **A2A プロトコル** — エージェント間の構造化通信
- **shared_memory** — SQLite ベースの cross-agent 知識共有

---

## 方式 A: PTY 観察レイヤー（採用）

エージェント側の Hook に依存せず、Synapse Controller の PTY 監視で全エージェント共通の学習パイプラインを実現する。

### 設計判断の経緯

| 方式 | 概要 | 判定 |
|------|------|------|
| A: PTY 観察 | Controller が PTY 出力を観察 → パターン抽出 | **採用** |
| B: A2A 注入 | タスク完了時に学習分析タスクを発行 | 却下（エージェントに負荷） |
| C: MCP 統一 | MCP tool 経由で学習機能提供 | 却下（非対応エージェントに fallback 必要） |

**方式 A を採用した理由:**
- `controller.py` が既に全エージェントの PTY 入出力を監視している
- ステータス検知（idle_detection）の仕組みを拡張するだけ
- エージェント側に何も要求しない — Hook の有無に関係なく動作
- Claude が学んだパターンを Codex/Gemini にも共有できる（ECC にはない差別化）

### アーキテクチャ

```
PTY 出力 ──→ controller.py
               ├── idle_detection (既存) → ステータス更新
               └── observation_collector (新規)
                     ├── 操作ログ収集
                     ├── パターン抽出（Haiku or ルールベース）
                     └── shared_memory 保存
                           └── A2A broadcast で他エージェントに共有
```

### Hook 対応状況と方式 A の優位性

| CLI エージェント | 独自 Hook | 方式 A で対応 |
|---|---|---|
| Claude Code | あり（PreToolUse, PostToolUse, Stop） | PTY 観察で代替 |
| Codex | なし | PTY 観察で対応 |
| Gemini CLI | なし | PTY 観察で対応 |
| OpenCode | なし | PTY 観察で対応 |
| Copilot | なし | PTY 観察で対応 |

---

## 取り込み機能の詳細

### P1: 自己学習パイプライン

ECC の Continuous Learning v2 を Synapse 向けに再設計。
観察 → パターン検出 → Instinct 生成 → **スキル/コマンド自動生成** → エージェント横断共有までの完全なパイプラインを構築する。

#### ECC の完全なフロー（参考）

```
① Hook で操作キャプチャ → observations.jsonl
② Background Observer (Haiku) がパターン検出
   → ユーザーの修正、エラー解決、繰り返しパターン
③ Atomic Instinct 生成（1トリガー + 1アクション、confidence 0.3〜0.9）
④ /evolve でクラスタリング → skill/command/agent に昇格
   → 2+ instinct が集まったら自動生成
   → evolved/{skills,commands,agents}/ に .md ファイル出力
⑤ /promote で 2+ プロジェクト & confidence ≥ 0.8 → グローバル昇格
```

#### Synapse のフロー（方式 A）

```
① PTY 出力観察
   → observation テーブル (SQLite) に蓄積
   → イベント: タスク受信/完了、エラー、ステータス変化、ファイル操作

② パターン分析（タスク完了時 or 定期）
   → ルールベース（Phase 1）→ LLM 分析（Phase 2）
   → ユーザーの修正、エラー解決、繰り返しパターンを検出

③ Instinct 生成
   → Atomic Instinct（1トリガー + 1アクション）
   → confidence score (0.3〜0.9)
   → プロジェクトスコープ or グローバルスコープ

④ shared_memory に保存 + A2A broadcast
   → 全エージェントが学習結果を共有

⑤ /evolve でクラスタリング → 自動生成
   → 2+ instinct が集まったら:
     - Skills (.claude/skills/ + .agents/skills/ に自動配布)
     - Commands (synapse コマンドとして登録)
   → evolved/ ディレクトリに .md ファイル生成

⑥ /promote でグローバル昇格
   → 2+ プロジェクトで出現 & confidence ≥ 0.8
   → プロジェクトスコープ → グローバルスコープ
```

#### 差別化ポイント

| | ECC | Synapse |
|---|---|---|
| 観察対象 | Claude の Tool 操作のみ | 全エージェントの PTY 入出力 |
| 共有範囲 | 単一 Claude セッション | 全エージェント横断 (A2A) |
| 永続化 | JSONL ファイル | SQLite (shared_memory + observation) |
| スコープ | プロジェクト or グローバル | プロジェクト + エージェント種別 |
| スキル配布 | ~/.claude/skills/ のみ | .claude/skills/ + .agents/skills/ 自動展開 |

**最大の差別化**: Claude が発見したパターン → skill 自動生成 → `.agents/skills/` にも配布 → **Codex/Gemini でも使える**

#### Confidence Scoring

| スコア | 意味 | 適用 |
|--------|------|------|
| 0.3 | Tentative — 提案のみ | 初回検出 |
| 0.5 | Moderate — コンテキストに合えば適用 | 2回目の検出 |
| 0.7 | Strong — 自動適用 | 繰り返し確認済み |
| 0.9 | Core — 基本動作 | ユーザー承認済み |

スコアの変動:
- **上昇**: 繰り返し観察、ユーザーによる承認
- **下降**: ユーザーによる修正、矛盾するパターン

#### コマンド体系

```bash
synapse learn                      # 現セッションからパターン抽出
synapse instinct status            # 全 instinct 表示（confidence 付き）
synapse instinct list              # 一覧（フィルタ可能）
synapse instinct promote <id>      # グローバルに昇格
synapse evolve                     # クラスタリング → skill/command 候補表示
synapse evolve --generate          # 候補から .md ファイル自動生成
synapse instinct export            # instinct エクスポート
synapse instinct import <file>     # instinct インポート
```

#### 実装ステップ

**Phase 1: 観察基盤**

1. `synapse/observation.py` — 観察データの収集・保存モジュール（SQLite）
2. `controller.py` に `ObservationCollector` を接続
3. 観察イベントの定義（タスク受信/完了、エラー、ステータス変化）

**Phase 2: パターン分析 + Instinct**

4. パターン分析エンジン（ルールベース）
5. `synapse/instinct.py` — Instinct データモデル（trigger, action, confidence, scope）
6. `shared_memory.py` に confidence scoring フィールドを追加
7. A2A broadcast で他エージェントへ知識共有
8. `synapse learn` / `synapse instinct` コマンド

**Phase 3: 進化 + スキル自動生成**

9. `synapse/evolve.py` — instinct クラスタリングエンジン
10. Skill 自動生成（SKILL.md フォーマットで出力）
11. `.claude/skills/` + `.agents/skills/` への自動配布
12. `synapse instinct promote` — グローバル昇格
13. `synapse instinct export/import`

**Phase 4: LLM 分析（将来）**

14. Haiku/小型モデルによるパターン分析
15. 自然言語での instinct 記述生成

#### 観察対象のイベント

| イベント | 収集データ | 用途 |
|----------|-----------|------|
| タスク受信 | message, sender, priority | タスクパターン分析 |
| タスク完了 | duration, status, output summary | 成功パターン学習 |
| エラー発生 | error type, recovery action | エラー対処パターン |
| ステータス変化 | from → to, trigger | ワークフロー最適化 |
| ファイル操作 | path, operation type | コーディングパターン |

---

### P2: セットアップ自動化

ECC の 3 段階インストールパイプラインを Synapse に適用。

#### 現状の `synapse init`
- テンプレートファイルのコピーのみ
- 言語コンテキストなし
- 検証ステップなし

#### 改善後

```bash
# Phase 1: Plan — 環境を診断して計画を立てる
synapse init --lang python
  → Python プロジェクト検出（pyproject.toml, requirements.txt）
  → 必要な設定を計画表示

# Phase 2: Apply — 設定を適用
  → プロファイル設定
  → スキル配布
  → 言語固有のルール追加

# Phase 3: Verify — 健全性チェック
synapse doctor
  → 設定ファイルの整合性
  → エージェント接続テスト
  → スキル同期チェック
  → ポート競合チェック
```

#### `synapse doctor` チェック項目

| チェック | 内容 |
|----------|------|
| 設定ファイル | settings.json, プロファイル YAML の妥当性 |
| エージェント接続 | 登録済みエージェントの到達性 |
| ポート競合 | 8100-8149 範囲の使用状況 |
| スキル同期 | plugins/ → .claude/skills/ の一致 |
| 依存関係 | Python, uv, 各 CLI ツールの存在 |
| メモリ DB | shared_memory, history, task_board の整合性 |

---

### P3: Hook プロファイル

Synapse の既存 Hook 機構にプロファイル切替を追加。

```yaml
# profiles/claude.yaml に追加
hook_profile: standard  # minimal | standard | strict

hooks:
  minimal:
    on_task_completed: null
  standard:
    on_task_completed: "echo 'Task done: $SYNAPSE_LAST_TASK_ID'"
    on_status_change: null
  strict:
    on_task_completed: "python -m synapse.hooks.quality_gate"
    on_status_change: "python -m synapse.hooks.status_logger"
    on_idle: "python -m synapse.hooks.observation_flush"
```

環境変数での制御:
```bash
SYNAPSE_HOOK_PROFILE=strict      # プロファイル切替
SYNAPSE_DISABLED_HOOKS=on_idle   # 個別無効化
```

---

### P4: セッション永続化

NanoClaw の永続化・分岐の概念を Synapse Shell に適用。

#### 実装方針
- Shell の入出力を `history.db` に記録（既存の history テーブルを活用）
- `synapse shell --resume` で前回セッションのコンテキストを復元
- 分岐は Canvas Workflow で代替可能（別エージェントに A 案/B 案を投げる）

#### NanoClaw との違い

| | NanoClaw | Synapse Shell |
|---|---|---|
| 実行方式 | `claude -p` ワンショット × N 回 | インタラクティブ PTY |
| 永続化 | .md ファイル | SQLite (history.db) |
| 分岐 | `/branch` でファイル複製 | Canvas Workflow で別エージェントに委譲 |
| マルチエージェント | Claude のみ | 全 CLI エージェント |

---

## P5: ハーネスパッケージマネージャー (`synapse harness`)

ECC の skills.sh / Anthropic Marketplace のようなハーネス配布の仕組みを Synapse に導入。
**1つのハーネス定義で、全サポートエージェントに統一的に適用する。**

### 課題

現状、ハーネス（CLAUDE.md, rules, skills, hooks 等）の導入方法にデファクトスタンダードがない。
- 自分で手書き → GitHub に置く → 手動コピー
- エージェントごとに配置先が異なる（.claude/ vs .agents/ vs .cursor/）
- 更新の追従は手動

### コマンド体系

```bash
synapse harness install s-hiraoku/my-harness          # GitHub から導入
synapse harness install s-hiraoku/my-harness@v1.2.0   # バージョン指定
synapse harness list                                    # インストール済み一覧
synapse harness update my-harness                       # 更新
synapse harness remove my-harness                       # 削除
synapse harness create my-harness                       # 新規作成

# 切替・レイヤー
synapse harness use react-harness                       # 切替
synapse harness use my-team-harness react-harness       # レイヤー重ね
synapse harness disable review-harness                  # 一時無効化
synapse harness enable review-harness                   # 再有効化

# ステータス確認
synapse harness status                                  # 概要
synapse harness status --verbose                        # 詳細
synapse harness status --json                           # JSON 出力
synapse harness info react-harness                      # 特定ハーネス詳細
synapse harness diff my-team-harness                    # ソースとの乖離チェック
```

### harness.yaml マニフェスト

GitHub リポジトリのルートに配置:

```yaml
name: my-team-harness
version: 1.0.0
description: チーム標準のコーディング規約とワークフロー
author: s-hiraoku
license: MIT

agents: [claude, codex, gemini, opencode, copilot]

contents:
  instructions:
    - src: instructions/default.md
      target: .synapse/default.md
  skills:
    - src: skills/code-review/
      target: skills/code-review/
  rules:
    - src: rules/coding-style.md
    - src: rules/git-workflow.md
  workflows:
    - src: workflows/post-impl.yaml
      target: .synapse/workflows/
  hooks:
    on_task_completed: scripts/quality-gate.sh

# レイヤー・互換性
layer_hint: base              # base | overlay | phase
compatible_with: [react-harness]
conflicts_with: [old-harness]

dependencies: []
```

### 全エージェント自動展開

Synapse の差別化ポイント:

```
harness.yaml の skills/ を:
  → .claude/skills/    (Claude Code 用)
  → .agents/skills/    (Codex, OpenCode, Gemini, Copilot 用)
に自動展開

harness.yaml の rules/ を:
  → .claude/rules/     (Claude Code 用)
  → .synapse/instructions/ に結合 (MCP 経由で全エージェントに配布)
```

### レイヤー方式

複数ハーネスを重ねて使える:

```
Layer 3: review-harness     ← 作業フェーズ（一時的）
Layer 2: react-harness       ← 技術スタック
Layer 1: my-team-harness     ← チーム規約（ベース）
```

競合解決ルール:
- 同名ファイルは上位レイヤーが優先
- skills/ は全レイヤーから集約（競合なし）
- instructions は全レイヤーを結合（上位が先に適用）
- hooks は全レイヤーから集約（同名フックは上位優先）

### ステータス確認

```
synapse harness status
══════════════════════════════════════════

  Active layers:
    L3  review-harness      v1.3.0  phase     (disabled)
    L2  react-harness        v2.1.0  overlay   ✔ active
    L1  my-team-harness      v1.0.0  base      ✔ active

  Installed (inactive):
    python-harness           v1.5.0  overlay
    legacy-rules             v0.9.0  base

  Agents receiving harness:
    Claude  (8100)  ✔ synced
    Codex   (8120)  ✔ synced
    Gemini  (8110)  ⚠ stale (restart needed)

  Files managed: 23
  Last updated: 2026-03-23 10:30:00
```

`synapse harness diff` でソースとの乖離を検出:

```
my-team-harness — drift check
══════════════════════════════════════════
  Local modifications:
    M  .claude/rules/coding-style.md    (3 lines changed)
    !  .claude/skills/code-review/      (missing reference/api.md)

  Run 'synapse harness update my-team-harness' to pull latest
  Run 'synapse harness restore my-team-harness' to discard local changes
```

Canvas Admin パネル (#/admin) にもハーネスレイヤー状態を表示。
`synapse harness status --json` でスクリプト・MCP からも参照可能。

### ロックファイル

```json
// .synapse/harness-lock.json
{
  "active_layers": [
    { "name": "my-team-harness", "layer": 1, "enabled": true },
    { "name": "react-harness", "layer": 2, "enabled": true }
  ],
  "harnesses": {
    "my-team-harness": {
      "source": "github:s-hiraoku/my-harness",
      "version": "v1.0.0",
      "commit": "abc1234",
      "installed_at": "2026-03-23T10:00:00Z",
      "files": [ ... ]
    }
  }
}
```

### 進化パス

| Phase | 内容 |
|-------|------|
| Phase 1 | GitHub ベース — `synapse harness install user/repo` |
| Phase 2 | レジストリ — `synapse harness install code-review` (名前解決) |
| Phase 3 | Marketplace — Web UI で検索・カテゴリ・レーティング |

---

## 取り込み不要と判断した機能

| ECC 機能 | 理由 |
|----------|------|
| Claude 内サブエージェント委譲 (Task tool) | Synapse は独立プロセス間 A2A 通信で上位互換 |
| NanoClaw REPL 本体 | Synapse Shell が PTY ベースで上位互換 |
| ファイルベース Memory Persistence | shared_memory.py (SQLite) が上位互換 |
| Context 動的切り替え (dev/review/research) | プロファイル + MCP で対応済み |
| 言語別レビュアーエージェント (28 個) | Synapse は実際の CLI エージェントを使い分ける設計 |

---

## 参考リソース

- [everything-claude-code](https://github.com/affaan-m/everything-claude-code)
- ECC Continuous Learning v2: `skills/continuous-learning-v2/SKILL.md`
- ECC Autonomous Loops: `skills/autonomous-loops/SKILL.md`
- ECC Agent Definition: `agents/*.md` (frontmatter: name, description, tools, model)
