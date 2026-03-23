# Smart Suggest & Plan Canvas Design

Synapse の利用率向上を目的とした設計メモ。壁打ちの結果、次の根本課題が特定された。

> ユーザーが「いつ Synapse を使うべきか」を判断できない。結果として、機能があっても使われない。

この課題に対し、**Synapse 側から能動的に提案する仕組み**を導入する。

---

## 設計方針

### 介入レベルの棲み分け

| レベル | 介入の形 | コスト | 担当 |
|--------|----------|--------|------|
| 0 | 何もしない | なし | — |
| 1 | 情報表示のみ | ほぼゼロ | (将来) |
| 2 | **提案（確認付き）** | 低い | **今回のスコープ** |
| 3 | 自動実行 | 高い | proactive 設定 |

レベル 2 を今回実装する。proactive（レベル 3）との重複を避け、**提案するが実行はユーザー承認後**とする。

### 介入タイミング

**作業開始時に一度だけ**提案する。作業中の割り込みは効率低下を招くため行わない。

---

## 全体フロー

```
ユーザーがエージェントに指示を出す
  → エージェントが MCP bootstrap_agent() を呼ぶ
  → 続けて analyze_task(prompt) を呼ぶ（bootstrap 指示文で誘導）
  → Synapse 側で指示内容を解析
  → トリガー条件を判定
  → 条件マッチ:
      1. 提案を生成（チーム構成 + タスク分割案）
      2. Canvas に Plan Card を表示（Mermaid DAG + ステップリスト）
      3. エージェントにも提案テキストを返す
      4. ユーザーが承認
      5. Task Board にタスクを自動登録 + エージェント割り当て
      6. 実行中も Canvas Plan Card が進捗を反映
  → 条件マッチしない:
      通常応答のみ（提案なし）
```

---

## コンポーネント設計

### 1. analyze_task MCP ツール

MCP server に新しい tool を追加する。

```python
# synapse/mcp/server.py に追加

def _tool_analyze_task(self, prompt: str) -> dict[str, object]:
    """Analyze user prompt and suggest team/task split if beneficial."""
```

**入力:**

```json
{
  "prompt": "このプロジェクトの認証をOAuth2に移行して"
}
```

**出力（提案あり）:**

```json
{
  "suggestion": {
    "type": "team_split",
    "summary": "この作業は設計・実装・テストに分割すると効率的です",
    "tasks": [
      {
        "subject": "OAuth2 設計",
        "description": "認証フローの設計とインターフェース定義",
        "suggested_agent": "claude",
        "priority": 4,
        "blocked_by": []
      },
      {
        "subject": "OAuth2 実装",
        "description": "設計に基づく実装",
        "suggested_agent": "codex",
        "priority": 3,
        "blocked_by": ["OAuth2 設計"]
      },
      {
        "subject": "OAuth2 テスト",
        "description": "実装のテスト作成と検証",
        "suggested_agent": "gemini",
        "priority": 3,
        "blocked_by": ["OAuth2 実装"]
      }
    ],
    "canvas_plan_card_id": "plan-oauth2-migration",
    "approve_command": "synapse tasks accept-plan plan-oauth2-migration",
    "team_command": "synapse team start --plan plan-oauth2-migration"
  },
  "triggered_by": ["keyword:移行", "multi_directory"]
}
```

**出力（提案なし）:**

```json
{
  "suggestion": null,
  "reason": "no_trigger_matched"
}
```

### 2. トリガー条件

以下の条件を **OR** で判定する（1 つでもマッチすれば提案）。

| 条件 | 判定方法 | 例 |
|------|----------|-----|
| **変更ファイル数 ≥ N** | git status / diff の解析 | N=10（初期値、設定可能） |
| **複数ディレクトリにまたがる** | 指示文中のパス解析 + git status | `src/auth/` と `tests/` と `docs/` |
| **テストがない実装を検知** | 対象ファイルに対応するテストファイルの有無 | `src/auth.py` に `tests/test_auth.py` がない |
| **大きなタスク記述** | プロンプトの文字数・複雑度 | 200文字以上 or 複数の動詞 |
| **特定キーワード** | 正規表現マッチ | リファクタ、移行、レビュー、設計、大規模 |

トリガー条件は `.synapse/suggest.yaml` で設定可能にする。

```yaml
# .synapse/suggest.yaml
suggest:
  enabled: true
  triggers:
    min_files: 10
    multi_directory: true
    missing_tests: true
    min_prompt_length: 200
    keywords:
      - "リファクタ"
      - "移行"
      - "レビュー"
      - "設計"
      - "大規模"
      - "refactor"
      - "migrate"
      - "review"
      - "redesign"
```

### 3. Plan Card（Canvas 新テンプレート）

Canvas に `plan` テンプレートと `plan` format を新規追加する。

#### テンプレートデータ構造

```json
{
  "type": "render",
  "content": {
    "format": "plan",
    "body": ""
  },
  "template": "plan",
  "template_data": {
    "title": "OAuth2 移行計画",
    "plan_id": "plan-oauth2-migration",
    "status": "proposed",
    "mermaid": "graph TD\n  A[設計] --> B[実装]\n  A --> C[テスト準備]\n  B --> D[テスト実行]\n  C --> D\n  D --> E[レビュー]",
    "steps": [
      {
        "id": "task-001",
        "subject": "OAuth2 設計",
        "agent": "claude",
        "status": "pending",
        "blocked_by": []
      },
      {
        "id": "task-002",
        "subject": "OAuth2 実装",
        "agent": "codex",
        "status": "pending",
        "blocked_by": ["task-001"]
      },
      {
        "id": "task-003",
        "subject": "OAuth2 テスト",
        "agent": "gemini",
        "status": "pending",
        "blocked_by": ["task-002"]
      }
    ],
    "actions": ["approve", "edit", "cancel"]
  },
  "card_id": "plan-oauth2-migration",
  "pinned": true
}
```

#### 表示レイアウト

```
┌─────────────────────────────────────────┐
│  Plan: OAuth2 移行計画     [PROPOSED]   │
├─────────────────────────────────────────┤
│                                         │
│  ┌──────┐    ┌──────┐                   │
│  │ 設計 │───→│ 実装 │──┐               │
│  └──────┘    └──────┘  │               │
│       │                 ↓               │
│       └──→ ┌────────┐  ┌────────┐      │
│            │テスト準備│─→│テスト実行│      │
│            └────────┘  └────────┘      │
│                              │          │
│                         ┌────────┐      │
│                         │ レビュー │      │
│                         └────────┘      │
│  (Mermaid DAG)                          │
├─────────────────────────────────────────┤
│  Steps                       Status     │
│  1. OAuth2 設計 (Claude)     ⏳ pending  │
│  2. OAuth2 実装 (Codex)      🔒 blocked  │
│  3. OAuth2 テスト (Gemini)   🔒 blocked  │
└─────────────────────────────────────────┘
```

#### ステータス表示

Plan Card 全体のステータス:

| status | 意味 |
|--------|------|
| `proposed` | 提案中（承認待ち） |
| `active` | 承認済み・実行中 |
| `completed` | 全タスク完了 |
| `cancelled` | キャンセル済み |

各ステップのステータスは Task Board の状態と同期:

| status | 表示 |
|--------|------|
| `pending` | ⏳ pending |
| `blocked` | 🔒 blocked |
| `in_progress` | 🔄 in_progress |
| `completed` | ✅ completed |
| `failed` | ❌ failed |

### 4. 提案 → Task Board 連携

ユーザーが提案を承認すると、Plan の各ステップを Task Board に自動登録する。

```bash
# 承認コマンド
synapse tasks accept-plan <plan_id>
```

処理フロー:

1. Canvas から Plan Card を取得（`plan_id` で検索）
2. `template_data.steps` を順に Task Board へ登録
3. `blocked_by` の依存関係を設定
4. `suggested_agent` を `assignee_hint` に設定
5. Plan Card のステータスを `proposed` → `active` に更新
6. Canvas Plan Card を再描画

### 5. 進捗同期

Task Board の状態変化を Canvas Plan Card に反映する。

実装方式: **ポーリング or イベント駆動**

- **短期（MVP）:** `synapse tasks list` 実行時に Plan Card も更新
- **中期:** Task Board の `complete_task()` / `fail_task()` 内で Canvas 更新を hook

```python
# task_board.py の complete_task() に追加
def complete_task(self, task_id, agent_id):
    unblocked = ...  # 既存処理
    self._sync_plan_card(task_id)  # Plan Card 更新
    return unblocked
```

### 6. bootstrap 指示文更新

MCP bootstrap の instruction resource に、`analyze_task` の呼び出し指示を追加する。

```markdown
## Smart Suggest

新しいタスクを受け取ったとき、まず `analyze_task` ツールにユーザーの指示を渡してください。
提案が返ってきた場合は、その内容をユーザーに共有し、承認を求めてください。
提案がない場合は、通常通り作業を進めてください。
```

この指示は `synapse://instructions/default` resource に含める。

### 7. Copilot MCP 対応

`synapse/settings.py` の `_mcp_config_paths()` に Copilot を追加する。

```python
# settings.py
def _mcp_config_paths(self) -> list[Path]:
    ...
    if self.agent_type == "copilot":
        return [
            Path.home() / ".copilot" / "mcp-config.json",
        ]
```

加えて、`has_mcp_bootstrap_config()` で Copilot の MCP 設定を検出できるようにし、MCP 設定が存在する場合は full instructions の代わりに最小 PTY bootstrap を送信する（approval は維持）。

Copilot の MCP 設定例:

```json
{
  "mcpServers": {
    "synapse": {
      "command": "/path/to/uv",
      "args": [
        "run",
        "--directory",
        "/path/to/repo",
        "python",
        "-m",
        "synapse.mcp",
        "--agent-id",
        "synapse-copilot-8140",
        "--agent-type",
        "copilot",
        "--port",
        "8140"
      ]
    }
  }
}
```

> **注意:** Copilot CLI の MCP サポート状況を確認する必要がある。MCP 未サポートの場合は PTY フォールバックを維持する。

---

## 実装フェーズ

### Phase 1: Copilot MCP 対応

スコープが最小で、単体で完結する。

- [ ] `_mcp_config_paths()` に Copilot 追加
- [ ] Copilot MCP 設定の検出テスト追加
- [ ] ドキュメント更新（mcp-bootstrap.md に Copilot セクション追加）

### Phase 2: Plan Card（Canvas）

提案の表示先を先に用意する。

- [ ] `plan` format を `protocol.py` に追加
- [ ] `plan` テンプレートを `server.py` / `index.html` に追加
- [ ] Plan Card の CRUD（作成・更新・取得）
- [ ] ステータス表示の実装（Mermaid DAG + ステップリスト）
- [ ] CLI コマンド `synapse canvas plan` 追加
- [ ] テスト追加

### Phase 3: analyze_task MCP ツール

提案エンジン本体。

- [ ] `analyze_task` tool を MCP server に追加
- [ ] トリガー条件の判定ロジック実装
- [ ] `.synapse/suggest.yaml` の読み込み
- [ ] 提案生成ロジック（タスク分割 + チーム構成）
- [ ] 提案時に Canvas Plan Card を自動投稿
- [ ] bootstrap 指示文に `analyze_task` 呼び出しルールを追加
- [ ] テスト追加

### Phase 4: Task Board 連携 + 進捗同期

提案を実行に移す仕組み。

- [ ] `synapse tasks accept-plan <plan_id>` コマンド実装
- [ ] Plan → Task Board 自動登録ロジック
- [ ] 進捗同期（Task Board → Canvas Plan Card）
- [ ] テスト追加

---

## 今後の拡張（スコープ外）

- Canvas のエージェント参照機能（エージェントが Canvas を読む）
- レベル 1（情報表示のみ）の介入
- Plan Card のインタラクティブ操作（ブラウザ上での承認/却下）
- 提案の学習（過去の承認/却下パターンから精度向上）

---

## 参考

- [MCP Bootstrap Design](mcp-bootstrap.md)
- [Canvas Design](canvas.md)
- [Task Board 実装](../../synapse/task_board.py)
