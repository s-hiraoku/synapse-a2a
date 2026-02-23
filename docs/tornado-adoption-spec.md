# tornado 機能採用仕様書

[mizchi/tornado](https://github.com/mizchi/tornado) の設計を分析し、Synapse A2A に取り入れるべき機能を特定・設計した仕様書です。

---

## 目次

- [1. 概要](#1-概要)
- [2. tornado の分析](#2-tornado-の分析)
- [3. 設計判断: 何を取り入れ、何を取り入れないか](#3-設計判断-何を取り入れ何を取り入れないか)
- [4. 採用機能仕様: TaskBoard 拡張](#4-採用機能仕様-taskboard-拡張)
  - [4.1 fail_task()](#41-fail_task)
  - [4.2 reopen_task()](#42-reopen_task)
  - [4.3 priority カラム](#43-priority-カラム)
- [5. ワークフロー実行パターン: Coordinator + TaskBoard](#5-ワークフロー実行パターン-coordinator--taskboard)
- [6. 具体的なシナリオ](#6-具体的なシナリオ)
- [7. CLI 変更](#7-cli-変更)
- [8. スキーマ マイグレーション](#8-スキーマ-マイグレーション)
- [9. 設計原則チェック](#9-設計原則チェック)
- [10. 参考資料](#10-参考資料)

---

## 1. 概要

### 1.1 背景

[tornado](https://github.com/mizchi/tornado) は mizchi 氏が開発したマルチエージェント開発オーケストレーター（MIT ライセンス、2026-02-20 公開）。"Review by codex, develop by claude-code" をコンセプトに、dev エージェントと review エージェントの自動ループを実現しています。

### 1.2 目的

- tornado の設計から Synapse A2A に価値をもたらす要素を抽出
- **既存モジュールの最小限の拡張** で同等以上の機能を実現
- プロジェクト哲学（[project-philosophy.md](./project-philosophy.md)）との整合性を維持

### 1.3 アーキテクチャの根本的な違い

```
tornado                          Synapse A2A
─────────────                    ───────────────
中央集権型オーケストレーター        P2P アーキテクチャ
2エージェント固定ペア              N エージェント動的チーム
Claude/Codex SDK 直接呼出         PTY ラッピング + A2A プロトコル
MoonBit → JS (Node.js)           Python
JSONL over stdout                Google A2A Protocol
サブプロセス per invocation        Persistent PTY
```

---

## 2. tornado の分析

### 2.1 コアアーキテクチャ

tornado は 6 フェーズの状態マシンでワークフローを制御します:

```
[ユーザー入力 or plan.md]
        │
        ▼
┌──────────────────┐
│  1. Decomposing  │  dev agent がタスクをサブタスクに分解
└───────┬──────────┘
        ▼
┌──────────────────┐
│  2. Assigning    │  サブタスクを dev agent にラウンドロビン割当
└───────┬──────────┘
        ▼
┌──────────────────┐
│  3. Executing    │  dev agent がタスク実行
└───────┬──────────┘
        ▼
┌──────────────────┐
│  4. Reviewing    │  review agent が 3 観点レビュー
└───────┬──────────┘
        │
  ┌─────┴──────┐
  │            │
approved   needs_changes
  │            │
  ▼            ▼
┌────────┐ ┌──────────────┐
│ 次タスク │ │ 5. Iterating │  フィードバック付き rework
└────────┘ │  (最大 N 回)  │  → 4. Reviewing に戻る
           └──────────────┘
                 │ rejected or 上限到達
                 ▼
           ┌──────────────┐
           │ 6. Finalizing│
           └──────────────┘
```

### 2.2 主要機能一覧

| # | 機能 | 概要 |
|---|------|------|
| 1 | Multi-Perspective Review | 3 観点（Code Quality / Performance / Security）の構造化レビュー |
| 2 | Dev-Review Loop | dev → review → rework の自動ループ |
| 3 | Plan File Mode | Markdown チェックリストからタスク順次実行 |
| 4 | RLM (Improvement Loop) | ベースライン計測 → 改善 → 検証 → commit/revert |
| 5 | User Interrupt | stdin 監視 → ファイル書き込み → ソフト割り込み |
| 6 | Token/Cost Tracking | イテレーションごとのトークン・コスト追跡 |
| 7 | Session Persistence | `.tornado/session.json` にフェーズ・タスク保存 |
| 8 | SDK Adapter Pattern | AgentAdapter で Claude/Codex を統一 |
| 9 | Git Context Awareness | レビュー前に git diff/log を自動収集 |
| 10 | Task Decomposition | dev agent による自動サブタスク分解 |

### 2.3 レビューシステムの詳細

tornado のレビューは XML タグベースの構造化判定を使用:

```
プロンプト → review agent に送信:
  "Your job is to identify issues and write them as a TODO list
   — do NOT attempt to fix or resolve the issues yourself."

レスポンスパース:
  <approved>          → Approved
  <needs_changes>..., ...</needs_changes>  → NeedsChanges(items)
  <rejected>...</rejected>  → Rejected(reason)
  タグなし            → デフォルト Approved（安全側にフォールバック）

3 観点マージ:
  1 つでも Rejected  → 全体 Rejected
  NeedsChanges あり  → "[観点名] 項目" 形式で統合
  全部 Approved      → 全体 Approved
```

### 2.4 安全設計パターン

tornado から学ぶべき安全設計:

1. **レビューパースのフォールバック**: タグ解析失敗 → デフォルト Approved（開発の流れを止めない）
2. **rework 失敗時のレビュー保全**: rework が失敗しても元のレビュー結果を復元（監査証跡の保全）
3. **max_review_cycles**: 無限 rework ループを防ぐ安全弁（デフォルト 2 回）

---

## 3. 設計判断: 何を取り入れ、何を取り入れないか

### 3.1 設計方針

**ワークフローエンジンは作らない。TaskBoard を拡張するだけ。**

Synapse A2A は P2P アーキテクチャであり、中央集権的なワークフローエンジンはプロジェクト哲学に反します。代わりに、coordinator エージェント（delegate-mode）が既存の TaskBoard を監視し、各エージェントに `synapse send` でタスクを指示する **Kanban パターン** を採用します。

```
coordinator (delegate-mode)                各エージェント
  │                                          │
  ├─ TaskBoard を監視（READY のたびに確認）    │
  ├─ available tasks を見て assign            │
  ├─ synapse send で指示 ──────────────────→ タスク実行
  │                                          │
  │  ←──────────────────────────────────────── synapse tasks complete
  │                                          │
  ├─ unblock されたタスクを確認               │
  ├─ 次のエージェントに assign                │
  └─ 全完了で終了                             │
```

### 3.2 採用・不採用の判断

| # | 機能 | 判断 | 理由 |
|---|------|------|------|
| 1 | Multi-Perspective Review | **不採用** | レビューに特化する必要なし。汎用基盤を提供し、ユーザーがスキルで自由に定義 |
| 2 | Dev-Review Loop | **不採用（専用エンジン）** | coordinator + TaskBoard の Kanban パターンで代替 |
| 3 | Plan File Import | **将来検討** | TaskBoard への Markdown インポートは便利だが今回スコープ外 |
| 4 | User Interrupt | **将来検討** | controller.py の拡張として別タスクで対応可 |
| 5 | Token/Cost Tracking | **将来検討** | history.py の拡張として別タスクで対応可 |
| 6 | RLM | **不採用** | ユーザーがスキルとして定義すべきもの |
| 7 | Session Persistence | **不採用** | coordinator の LLM が文脈を保持。TaskBoard 自体が SQLite で永続化済み |
| 8 | SDK Adapter Pattern | **不採用** | Synapse は PTY ラッピング方式であり SDK 不要 |
| 9 | Git Context | **不採用** | エージェントが自分で git コマンドを実行できる |
| 10 | Task Decomposition | **不採用（専用機能）** | coordinator がタスク分解し TaskBoard に登録する運用で代替 |

### 3.3 採用するもの

**TaskBoard の拡張（3 点のみ）:**

1. `fail_task()` — タスク失敗の報告
2. `reopen_task()` — タスクの巻き戻し（completed/failed → pending）
3. `priority` カラム — 同列タスクの優先度制御

---

## 4. 採用機能仕様: TaskBoard 拡張

### 4.1 fail_task()

#### 背景

現在の TaskBoard は `pending → in_progress → completed` の一方通行。エージェントがタスクに失敗した場合、ボードに報告する手段がない。

#### 仕様

```python
def fail_task(self, task_id: str, agent_id: str, reason: str = "") -> None:
    """タスクを失敗状態にする。

    Args:
        task_id: 失敗したタスクの ID。
        agent_id: タスクを実行していたエージェントの ID。
        reason: 失敗理由（オプション）。

    Raises:
        なし（静かに失敗）。

    状態遷移:
        in_progress → failed

    動作:
        - status を 'failed' に更新
        - reason を fail_reason カラムに記録
        - updated_at を更新
        - assignee は維持（誰が失敗したかの記録）
        - blocked_by でこのタスクに依存するタスクは unblock しない
    """
```

#### スキーマ変更

```sql
ALTER TABLE board_tasks ADD COLUMN fail_reason TEXT DEFAULT '';
```

#### 状態遷移図

```
                    claim_task()
    pending ────────────────────→ in_progress
       ▲                            │   │
       │                            │   │
       │         reopen_task()      │   │  complete_task()
       ├────────────────────────────┘   │
       │                                ▼
       │         reopen_task()      completed
       ├────────────────────────────────┘
       │
       │         reopen_task()
       ├──────────────────────────── failed
       │                               ▲
       │                               │
       │                               │  fail_task()
       │                           in_progress
```

### 4.2 reopen_task()

#### 背景

レビューで rejected された場合や、失敗したタスクを再試行する場合、タスクを pending に戻す手段が必要。

#### 仕様

```python
def reopen_task(self, task_id: str, agent_id: str) -> bool:
    """タスクを pending に戻す。

    Args:
        task_id: 再オープンするタスクの ID。
        agent_id: 操作を行うエージェントの ID（監査用）。

    Returns:
        True: 成功、False: タスクが見つからないか既に pending。

    状態遷移:
        completed → pending
        failed → pending

    動作:
        - status を 'pending' に更新
        - assignee を NULL にクリア
        - completed_at を NULL にクリア
        - fail_reason を空文字にクリア
        - updated_at を更新
        - pending からの reopen は無視（False を返す）
        - in_progress からの reopen は無視（False を返す）

    注意:
        - このタスクに blocked_by で依存していた downstream タスクが
          既に completed の場合、それらは巻き戻さない（影響範囲を限定）
        - ただし downstream タスクが pending のままなら、
          このタスクが再度 complete されるまで unblock されない
    """
```

### 4.3 priority カラム

#### 背景

TaskBoard の `get_available_tasks()` は `created_at` 順で返す。同時に available なタスクの中で「どれを先にやるべきか」をデータとして表現する手段がない。

#### 仕様

```sql
ALTER TABLE board_tasks ADD COLUMN priority INTEGER DEFAULT 3;
```

| 値 | 意味 | 用途 |
|----|------|------|
| 1 | 最低 | バックグラウンドタスク |
| 2 | 低 | 急ぎでないタスク |
| 3 | 通常 | デフォルト |
| 4 | 高 | 優先タスク |
| 5 | 最高 | 緊急・クリティカル |

`synapse send` の priority（1-5）と同じスケールで一貫性を確保。

#### 変更箇所

```python
def create_task(
    self,
    subject: str,
    description: str,
    created_by: str,
    blocked_by: list[str] | None = None,
    priority: int = 3,                     # 追加
) -> str:

def get_available_tasks(self) -> list[dict[str, Any]]:
    # ORDER BY を変更:
    # 旧: ORDER BY created_at
    # 新: ORDER BY priority DESC, created_at
```

#### _row_to_dict 変更

```python
def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        # ... 既存フィールド ...
        "priority": row["priority"],       # 追加
        "fail_reason": row["fail_reason"], # 追加
    }
```

---

## 5. ワークフロー実行パターン: Coordinator + TaskBoard

### 5.1 概要

tornado のワークフローを Synapse A2A で実現するパターン。ワークフローエンジンは不要。

```
coordinator (delegate-mode, スキルで動作ルールを定義)
  │
  ├─ READY になるたびに TaskBoard を確認
  │   └─ synapse tasks list --status pending
  │
  ├─ available tasks があれば適切なエージェントに assign
  │   └─ synapse tasks assign <task_id> <agent>
  │   └─ synapse send <agent> "タスクの内容" --no-response
  │
  ├─ 完了通知を受けたら（または定期確認で）
  │   └─ synapse tasks list --status completed
  │   └─ 必要なら次のタスクを assign
  │
  ├─ 失敗を検知したら
  │   └─ synapse tasks list --status failed
  │   └─ 判断: reopen して再割当 or 新タスク作成 or 停止
  │
  └─ 全タスク完了で終了
```

### 5.2 coordinator のスキル定義（例）

coordinator に渡すスキル指示の例:

```
あなたは TaskBoard を監視する coordinator です。

ルール:
1. READY になったら `synapse tasks list` でボードを確認
2. pending タスクがあれば `synapse list` で空いているエージェントを確認し、
   `synapse send <agent> "タスク内容"` で指示
3. failed タスクがあれば原因を確認し、reopen するか新タスクを作成
4. 全タスクが completed になったら報告
5. タスクの priority が高いものを優先的に assign
6. blocked_by の依存関係を尊重する（get_available_tasks が自動で処理）
```

### 5.3 各エージェントの動作

各エージェントは通常通りタスクを実行し、完了時にボードを更新するだけ:

```bash
# タスク成功時
synapse tasks complete <task_id>

# タスク失敗時
synapse tasks fail <task_id> --reason "テストが通らない"
```

---

## 6. 具体的なシナリオ

### 6.1 テスト → 実装 → レビュー

```bash
# coordinator がタスクを作成
synapse tasks create "認証機能のテスト作成" -d "JWT 認証のユニットテスト" --priority 4
# → task-1

synapse tasks create "認証機能の実装" -d "テストに合わせて実装" --blocked-by task-1 --priority 4
# → task-2

synapse tasks create "認証機能のレビュー" -d "実装のコードレビュー" --blocked-by task-2 --priority 3
# → task-3
```

```
時刻    TaskBoard                              動作
────    ─────────                              ────
T0      task-1: pending (available)            coordinator → dev-1 に assign
        task-2: pending (blocked by task-1)
        task-3: pending (blocked by task-2)

T1      task-1: in_progress (dev-1)            dev-1 がテスト作成中
        task-2: pending (blocked)
        task-3: pending (blocked)

T2      task-1: completed                      dev-1 完了 → task-2 が unblock
        task-2: pending (available)            coordinator → dev-1 に assign
        task-3: pending (blocked)

T3      task-2: in_progress (dev-1)            dev-1 が実装中
        task-3: pending (blocked)

T4      task-2: completed                      dev-1 完了 → task-3 が unblock
        task-3: pending (available)            coordinator → reviewer に assign

T5      task-3: in_progress (reviewer)         reviewer がレビュー中

T6a     task-3: completed                      全完了 → coordinator が報告
    or
T6b     task-3: failed (reason: "テスト不足")   coordinator が判断:
        → task-2 を reopen? 新タスク作成?
```

### 6.2 並列タスク + 優先度

```bash
synapse tasks create "認証のテスト" --priority 5           # task-1
synapse tasks create "API のテスト" --priority 3            # task-2
synapse tasks create "認証の実装" --blocked-by task-1 --priority 5  # task-3
synapse tasks create "API の実装" --blocked-by task-2 --priority 3  # task-4
```

```
T0: get_available_tasks() → [task-1 (pri=5), task-2 (pri=3)]
    coordinator: task-1 を dev-1 に、task-2 を dev-2 に assign（並列実行）

T1: task-1 完了 → task-3 が unblock
    get_available_tasks() → [task-3 (pri=5)]
    coordinator: task-3 を dev-1 に assign（優先度が高い）

T2: task-2 完了 → task-4 が unblock
    coordinator: task-4 を dev-2 に assign
```

### 6.3 失敗 → reopen → 再試行

```
T0: task-1 (in_progress, dev-1)

T1: dev-1 がタスク失敗
    synapse tasks fail task-1 --reason "依存ライブラリが見つからない"

T2: coordinator が failed を検知
    判断: "依存を先にインストールすべき"
    synapse tasks create "依存ライブラリのインストール" --priority 5  # task-new
    synapse tasks reopen task-1
    # task-1 は pending に戻り、task-new の完了後に再試行

    ※ blocked_by は coordinator が判断して設定する
```

---

## 7. CLI 変更

### 7.1 新規サブコマンド

```bash
# タスク失敗報告
synapse tasks fail <task_id> [--reason "失敗理由"]

# タスク再オープン
synapse tasks reopen <task_id>
```

### 7.2 既存コマンド変更

```bash
# create に --priority オプション追加
synapse tasks create "タスク名" -d "説明" --priority 4

# list 出力に priority と fail_reason カラム追加
synapse tasks list
# ID        SUBJECT              STATUS       PRIORITY  ASSIGNEE      BLOCKED_BY
# task-1    認証テスト作成         completed    4         dev-1         -
# task-2    認証実装              in_progress  4         dev-1         task-1
# task-3    レビュー              pending      3         -             task-2
```

### 7.3 A2A エンドポイント変更

```
POST /tasks/board/{task_id}/fail
Body: { "agent_id": "synapse-claude-8100", "reason": "テスト失敗" }

POST /tasks/board/{task_id}/reopen
Body: { "agent_id": "synapse-claude-8100" }
```

---

## 8. スキーマ マイグレーション

### 8.1 方針

SQLite の `ALTER TABLE ADD COLUMN` はテーブルの再作成なしに安全に実行できます。既存データに影響なし。

### 8.2 マイグレーション SQL

```sql
-- priority カラム追加
ALTER TABLE board_tasks ADD COLUMN priority INTEGER DEFAULT 3;

-- fail_reason カラム追加
ALTER TABLE board_tasks ADD COLUMN fail_reason TEXT DEFAULT '';

-- priority ソート用インデックス
CREATE INDEX IF NOT EXISTS idx_board_priority ON board_tasks(priority);
```

### 8.3 実装方法

`task_board.py` の `_init_db()` 内で、既存テーブルにカラムが存在しない場合のみ ALTER TABLE を実行:

```python
# カラム存在チェック
columns = [row[1] for row in conn.execute("PRAGMA table_info(board_tasks)")]
if "priority" not in columns:
    conn.execute("ALTER TABLE board_tasks ADD COLUMN priority INTEGER DEFAULT 3")
if "fail_reason" not in columns:
    conn.execute("ALTER TABLE board_tasks ADD COLUMN fail_reason TEXT DEFAULT ''")
```

---

## 9. 設計原則チェック

[project-philosophy.md](./project-philosophy.md) との整合性確認:

| 原則 | 適合 | 説明 |
|------|------|------|
| Non-Invasive | OK | エージェントの挙動を変えない。TaskBoard のスキーマ拡張のみ |
| A2A-First | OK | 既存の A2A エンドポイントパターンに準拠 |
| Collaborative | OK | coordinator + worker の Kanban パターンで協調を実現 |
| Agent Ignorance | OK | エージェントは `synapse tasks complete/fail` を呼ぶだけ。ワークフローの全体像を知る必要なし |
| Minimal Visibility | OK | 新モジュール不要。既存 TaskBoard の拡張のみ |

### エージェント無知の原則チェックリスト

- [x] エージェントが新しい構文やフォーマットを学ぶ必要があるか？ → `synapse tasks fail` と `synapse tasks reopen` のみ
- [x] task_id や sender_id をエージェントが扱う必要があるか？ → task_id のみ（既存パターンと同じ）
- [x] 返信時にエージェントが宛先を指定する必要があるか？ → 不要

---

## 10. 参考資料

- [mizchi/tornado](https://github.com/mizchi/tornado) — 分析対象リポジトリ
- [agent-teams-adoption-spec.md](./agent-teams-adoption-spec.md) — Agent Teams 採用仕様書（B1-B6 の設計元）
- [project-philosophy.md](./project-philosophy.md) — Synapse A2A プロジェクト哲学
- [file-safety.md](./file-safety.md) — File Safety 設計（SQLite パターンの先行実装）
