# LLM Wiki — Knowledge Accumulation Layer

> Karpathy の LLM Wiki パターンを Synapse に搭載する設計ドキュメント

## 背景

[LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) は Karpathy が提唱するパターン。LLM が個人のナレッジベースを永続的な Wiki として段階的に構築・維持する。RAG とは異なり、知識は一度統合され複利的に蓄積される。

### 従来の問題

- RAG は毎回ゼロから知識を再発見する
- `synapse memory save` は KV ストアであり、相互リンクや構造化がない
- エージェントの学んだ知識がセッション間で失われる

### Synapse の強み

- マルチエージェントが協調して知識を蓄積できる
- `~/.synapse`（グローバル）と `.synapse`（プロジェクト）の2層が既にある
- Canvas で知識をリッチに可視化できる
- MCP instruction で全エージェント種別に規約を注入できる

---

## コア設計思想

**エージェントのロジックはゼロ。Schema（指示書）を読ませるだけ。**

Karpathy の原文:

> *The right way to use this is to share it with your LLM agent and work together to instantiate a version that fits your needs.*

Synapse が足す価値:
1. **Schema テンプレート** — llm-wiki.md を Synapse 向けにカスタマイズ（2層、マルチエージェント、file-safety）
2. **CLI** — エージェントが Wiki を操作するための確定的コマンド群
3. **Canvas Knowledge ビュー** — Markdown ファイルをリッチに表示する閲覧 UI
4. **MCP instruction 注入** — 全エージェント種別に Schema を自動配信

---

## 3層アーキテクチャ

```
wiki/
├── schema.md      # Schema 層 — Wiki の構造規約・ワークフロー定義
├── index.md       # 全ページの一覧（1行サマリ付き）
├── log.md         # 時系列の操作ログ
├── sources/       # Raw Sources 層 — 不変の原資料（LLM は読むだけ）
└── pages/         # Wiki 層 — LLM が生成・更新するページ群
```

### Raw Sources 層

不変の原資料。LLM は読むが変更しない。

| プロジェクトスコープ | グローバルスコープ |
|---|---|
| 設計ドキュメント、README | ユーザーが手動で入れた記事・論文 |
| PR、Issue の内容 | 他プロジェクトから昇格した知識 |
| テスト結果、エラーログ | 外部ツールの出力 |

### Wiki 層

LLM が完全にオーナーシップを持つ Markdown ファイル群。

**ページ種別:**

| type | 用途 | 例 |
|---|---|---|
| entity | 具体的な対象 | `entity-controller.md` |
| concept | 抽象的な概念・パターン | `concept-file-locking.md` |
| decision | なぜそうしたか（ADR 形式） | `decision-sqlite-over-jsonl.md` |
| comparison | 2つ以上の選択肢の比較 | `comparison-hook-vs-pty.md` |
| synthesis | 全体を俯瞰するまとめ | `synthesis-overview.md` |
| learning | バグ修正や発見したパターンの記録 | `learning-pty-race-condition.md` |

**Frontmatter:**

```yaml
---
type: entity | concept | decision | comparison | synthesis | learning
title: ページタイトル
created: 2026-04-05
updated: 2026-04-05
sources:
  - path/to/source.md
  - https://example.com/article
links:
  - other-page-name
confidence: 0.8
author: synapse-claude-8100
source_files:                # optional — tracked source code paths
  - synapse/controller.py
source_commit: abc1234       # optional — git SHA when source_files were last reviewed
---
```

**規約:**
- ファイル名: `{type}-{kebab-case-title}.md`
- ページ間リンク: `[[page-name]]` 形式（Obsidian 互換）
- 新ページ作成時は `index.md` に追記
- 既存ページ更新時は `updated` を更新
- すべての操作は `log.md` に追記

### Schema 層

`schema.md` — Wiki の憲法。エージェントがこれを読んで Wiki の構造と運用ルールを理解する。MCP instruction `synapse://instructions/wiki` として配信される。

---

## 2層スコープ

```
~/.synapse/wiki/           # グローバル — Synapse 全体・汎用知識
.synapse/wiki/             # プロジェクト — このリポジトリ固有の知識
```

| | プロジェクトスコープ | グローバルスコープ |
|---|---|---|
| 保存先 | `.synapse/wiki/` | `~/.synapse/wiki/` |
| 内容 | コードベースの設計、パターン、落とし穴 | 汎用的な技術知識、ユーザーの学び |
| 例 | 「controller.py の PTY 管理」 | 「Python asyncio のベストプラクティス」 |
| デフォルト | ○ | `--scope global` で指定 |

---

## 操作モデル — 人間とエージェントの役割分担

```
人間 ──自然言語──→ エージェント ──CLI──→ Wiki
                   「この記事取り込んで」
                        ↓
                   synapse wiki ingest article.md
                        ↓
                   sources/ にコピー → ページ作成・更新 → index/log 更新
```

**人間は CLI を叩かない。エージェントが叩く。**

| 誰が | 何をする |
|---|---|
| 人間 | 自然言語で指示（「取り込んで」「なぜこの設計？」「Wiki 健全？」） |
| エージェント | CLI を実行 + 知的処理（要約、関連ページ更新、回答合成） |
| CLI | 確定的処理（ファイルコピー、index パース、frontmatter 検証、孤立リンク検出） |

---

## 3つの基本操作

### Ingest — ソースを Wiki に取り込む

```bash
synapse wiki ingest <source-path> [--scope project|global]
```

**CLI の責務（確定的）:**
- `sources/` にファイルをコピー
- `log.md` に ingest 記録を追記

**エージェントの責務（知的）:**
- ソースを読解
- 要約ページを作成
- 関連する既存ページを更新（相互参照、矛盾検出）
- `index.md` を更新

### Query — Wiki に質問する

```bash
synapse wiki query "<question>" [--scope project|global]
```

**CLI の責務（確定的）:**
- `index.md` をパースして関連ページ候補を返す

**エージェントの責務（知的）:**
- 関連ページを読み、回答を合成
- 良い回答をエージェント判断でページ化

### Lint — 整合性チェック

```bash
synapse wiki lint [--scope project|global]
```

**CLI の責務（確定的）:**
- frontmatter 検証（必須フィールド、型チェック）
- 孤立リンク検出（`[[link]]` のリンク先が存在しない）
- orphan ページ列挙（どこからもリンクされていない）
- stale ページ検出（`source_files` の変更が `source_commit` 以降にある）

**エージェントの責務（知的）:**
- ページ間の矛盾検出
- 古い情報の判断
- 修正提案

### Status — 状態表示（CLI のみ）

```bash
synapse wiki status [--scope project|global]
```

- ページ数、ソース数、最終更新日時
- 健康度スコア（lint 結果ベース）

### Refresh — 古くなったページを検出・更新

```bash
synapse wiki refresh [--apply] [--scope project|global]
```

`source_files` と `source_commit` を持つページについて、追跡対象ファイルが `source_commit` 以降に変更されたかを検出する。`--apply` を付けると `source_commit` を現在の HEAD に更新する。

### Init — スケルトンページ生成

```bash
synapse wiki init [--scope project|global]
```

Wiki ディレクトリを初期化し、`architecture` と `patterns` のスケルトンページを作成する。

### Graph — ページ間リンクの可視化

```
GET /api/wiki/graph
```

Canvas 向けに Wiki ページ間の `[[wikilink]]` 関係を Mermaid 図として返す。

### エージェント未起動時

CLI の確定的処理のみ実行される。知的処理が必要な部分は `log.md` に「pending」として記録し、次回エージェント起動時に処理される。

---

## 設定

```json
// .synapse/settings.json
{
  "wiki": {
    "enabled": true
  }
}
```

- `wiki.enabled: true`（デフォルト）→ MCP instruction に `synapse://instructions/wiki` を含める
- `wiki.enabled: false` → instruction を注入しない、Canvas Knowledge メニューを非表示

ディレクトリは `wiki.enabled: true` のとき、初回アクセス時に自動作成される（`synapse wiki init` 不要）。

---

## MCP Instruction 注入

`wiki.enabled == true` のとき、`bootstrap_agent()` の `instruction_resources` に `synapse://instructions/wiki` を追加。

```python
# synapse/mcp/server.py
if settings.get("wiki", {}).get("enabled", True):
    resources.append("synapse://instructions/wiki")
```

instruction の内容は `schema.md` のテンプレートをベースに、エージェント ID やスコープ情報を動的に注入。

---

## 蓄積モデル — 明示的操作 + 提案型

Wiki が自然に育つために、2つの蓄積パスを持つ。

### 明示的操作（Step 1）

人間が「取り込んで」「まとめて」と指示したときのみ Wiki を更新。

```
人間: 「この設計ドキュメントを Wiki に入れて」
エージェント: synapse wiki ingest design-doc.md → ページ作成 → index 更新
```

### 提案型（Step 2）

エージェントが作業中に Wiki 更新の候補を検出し、提案する。人間が承認したら書く。

**トリガー条件:**

| 状況 | 提案内容 |
|---|---|
| 設計判断をした | 「この判断を decision ページにしますか？」 |
| バグ修正で原因が非自明 | 「この落とし穴を concept ページにしますか？」 |
| 新しいモジュールの構造を理解した | 「この entity ページを作りますか？」 |
| 2つ以上の選択肢を比較した | 「この比較を comparison ページにしますか？」 |
| 既存ページと矛盾する情報を発見 | 「既存ページを更新しますか？」 |

**提案しない条件:**
- 単純な typo 修正
- 1回限りのデバッグ作業
- 既に Wiki にある情報の繰り返し
- ユーザーが急いでいる（短い指示の連続など）

**提案の形式:**

```
📝 Wiki suggestion: この設計判断を Wiki に記録しますか？
   → decision-sqlite-over-jsonl.md (new)
   → entity-shared-memory.md (update)
   [y/n]
```

エージェントは提案だけ行い、承認なしに Wiki を書き換えない。

### 将来: 自動蓄積（Step 3）

Step 2 で承認パターンが安定したら、`schema.md` を編集して「確認なしで書け」に切り替え可能。Schema をユーザーが直接編集する運用。

---

## Canvas Knowledge ビュー

### バックエンド API

```
GET /api/wiki?scope=project|global       # ページ一覧（frontmatter パース済み）
GET /api/wiki/{scope}/pages/{page}       # ページ内容（Markdown）
GET /api/wiki/stats?scope=project|global # 統計情報
GET /api/wiki/graph                      # ページ間リンクの Mermaid 図
```

### フロントエンド

`#/knowledge` ルート。`wiki.enabled == false` のときサイドバーに表示しない。

**レイアウト:**

```
┌──────────────────────────────────────────────┐
│  Knowledge                                    │
│ ┌──────────┬──────────┐  🔍 Search...        │
│ │ Project  │ Global   │                       │
│ └──────────┴──────────┘                       │
│                                               │
│ ┌─ Stats ────────────────────────────────────┐│
│ │ 23 pages │ 12 sources │ Updated 2m ago     ││
│ └────────────────────────────────────────────┘│
│                                               │
│  Type: [All ▾]   Sort: [Updated ▾]           │
│                                               │
│ ┌────────────────────────────────────────────┐│
│ │ 🏷 entity-controller                       ││
│ │ PTY management, status detection           ││
│ │ 5 links │ 3 sources │ 1h ago               ││
│ ├────────────────────────────────────────────┤│
│ │ 💡 concept-file-locking                    ││
│ │ Multi-agent file conflict prevention       ││
│ │ 3 links │ 2 sources │ 3h ago               ││
│ ├────────────────────────────────────────────┤│
│ │ ⚖ decision-sqlite-over-jsonl              ││
│ │ Why SQLite was chosen for persistence      ││
│ │ 2 links │ 1 source  │ 1d ago               ││
│ └────────────────────────────────────────────┘│
│                                               │
│ ┌─ Recent Activity ──────────────────────────┐│
│ │ 14:32  ingest  design-doc → 4 pages        ││
│ │ 13:15  query   "Why SQLite?" → new page    ││
│ │ 11:00  lint    2 orphans found              ││
│ └────────────────────────────────────────────┘│
└──────────────────────────────────────────────┘
```

**ページ詳細（クリック時）:**
- Markdown レンダリング（既存の `canvas-renderers.js` を再利用）
- frontmatter メタデータ表示（type バッジ、confidence、author、日付）
- `[[wikilink]]` をクリック可能なリンクとしてレンダリング
- Sources 一覧

**UI 機能:**
- Project / Global タブ切り替え
- type フィルタ（entity, concept, decision, comparison, synthesis, learning）
- テキスト検索（ページタイトル + サマリ）
- ソート（Updated, Created, Confidence, Title）

---

## Shared Memory の廃止

LLM Wiki の導入に伴い、`synapse memory save/search` （shared_memory.py）を廃止する。

**理由:**
- Wiki が shared_memory の上位互換として機能する（構造化、相互リンク、confidence）
- shared_memory instruction を廃止することで、Wiki instruction 追加による context window 圧迫を相殺
- 現時点で shared_memory はほぼ使われていない

**移行:**
- `synapse memory save` → Wiki のページとして蓄積（エージェントが自然に行う）
- `synapse memory search` → `synapse wiki query` で代替
- 既存の shared_memory データ → 必要なら Wiki に ingest

---

## 既知の懸念と対策

| # | 懸念 | 対策 |
|---|---|---|
| 1 | Wiki 肥大化 | Schema に閾値明記（一時的デバッグ情報は書かない、2回以上出現したパターンのみ等）。confidence + lint で定期的に刈り込み |
| 2 | index.md/log.md の競合 | append-only 運用 + CLI 側で排他制御 |
| 3 | エージェント間の一貫性 | lint で frontmatter バリデーション。運用しながら調整 |
| 4 | context window 圧迫 | shared-memory instruction 廃止で相殺。`wiki.enabled: false` で完全に外せる |

---

## #442（自己学習パイプライン）との関係

**現時点では切り離す。** 将来の統合ポイント:

- Instinct が成熟（confidence ≥ 0.8）→ Wiki の concept / decision ページとして結晶化
- Wiki のページ種別に `instinct` を追加する可能性
- 観察データ（#442）が Wiki の sources として取り込まれる可能性

これらは #442 の実装が進んだ段階で改めて検討する。

---

## 実装ステップ

### Phase 1: 基盤

- [ ] `synapse/wiki.py` — CLI コマンド実装（ingest, query, lint, status, refresh, init）
- [ ] Wiki ディレクトリ自動作成ロジック
- [ ] `schema.md` テンプレート
- [ ] MCP instruction `synapse://instructions/wiki` の追加
- [ ] `synapse config` に `wiki.enabled` 設定追加
- [ ] テスト

### Phase 2: Canvas UI

- [ ] Wiki API エンドポイント（`/api/wiki/*`）
- [ ] `canvas-knowledge.js` — Knowledge ビュー
- [ ] `canvas-knowledge.css` — スタイリング
- [ ] サイドバーに Knowledge メニュー追加（`wiki.enabled` 連動）
- [ ] ページ一覧（フィルタ、検索、ソート）
- [ ] ページ詳細表示（Markdown レンダリング、wikilink、メタデータ）
- [ ] Recent Activity 表示（log.md パース）
- [ ] テスト

### Phase 3: 磨き込み

- [ ] Obsidian 互換の `[[wikilink]]` レンダリング最適化
- [ ] Canvas SSE 連携（Wiki 更新時のリアルタイム反映）
- [ ] lint 結果の Canvas 表示
- [ ] ページ間ナビゲーション（リンクを辿る）

---

## 対象ファイル

| File | Change |
|------|--------|
| `synapse/wiki.py` | 新規 — Wiki CLI コマンド |
| `synapse/cli.py` | wiki サブコマンド追加 |
| `synapse/mcp/server.py` | `synapse://instructions/wiki` instruction 追加 |
| `synapse/canvas/routes/wiki.py` | 新規 — Wiki API エンドポイント |
| `synapse/canvas/static/canvas-knowledge.js` | 新規 — Knowledge ビュー |
| `synapse/canvas/static/canvas-knowledge.css` | 新規 — Knowledge スタイル |
| `synapse/canvas/static/canvas-core.js` | Knowledge ルート追加 |
| `synapse/canvas/static/canvas-base.css` | サイドバーメニュー追加 |
| `synapse/canvas/server.py` | Wiki ルート登録、wiki.enabled チェック |
| `templates/wiki-schema.md` | 新規 — schema.md テンプレート |
| `tests/test_wiki.py` | 新規 |

---

## 参考

- [LLM Wiki (Karpathy)](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
- [#442 — 自己学習パイプライン](https://github.com/s-hiraoku/synapse-a2a/issues/442)
