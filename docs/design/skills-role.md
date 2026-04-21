# Skills の役割再定義

> Issue #610 に対応する設計メモ。Synapse における "skills" の責務を、
> MCP / CLI / `gh skill` / workflow との関係の中で定義しなおす。

このドキュメントの結論は次の 1 行に集約される。

> **Skills は A2A プリセット（= 人間が書いた再利用可能なエージェント向け指示テンプレート）である。配布は `gh skill` が、動的な runtime context 配信は MCP が、状態を持つ操作は CLI が担う。**

---

## なぜ再定義するのか

`plugins/synapse-a2a/skills/` には現時点で 23 個の SKILL.md が置かれて
いる。同じ内容がビルド工程で `.claude/skills/` と `.agents/skills/`
にミラーされ、さらに `synapse workflow sync` は `.synapse/workflows/*.yaml`
を自動的に skill 化する。

この "skills" の概念が育つ過程で、次の3つの層と責務が被るようになった。

| 層 | 機能 |
|---|---|
| `gh skill` (GitHub CLI v2.90+) | skill の install / publish / pin / update |
| MCP (`synapse/mcp/server.py`) | instruction resource の URI 配信 + runtime tool |
| `synapse workflow` | YAML ワークフローの定義と自動 skill 生成 |

結果として、新しいエージェントを立ち上げる開発者にも、RFC を読む将来
の自分にも、「skill ってつまり何なのか」が一意に説明できない状況が
生まれている。#610 はこの曖昧さを解消するためのチケットである。

---

## 現状の観察

### "skill" と呼ばれているものは 3 種類ある

1. **手書き skill** — `plugins/synapse-a2a/skills/<name>/SKILL.md`
   として人間が書いたエージェント向け指示集。例: `synapse-a2a`,
   `synapse-manager`, `code-review`, `release`。
2. **Workflow 自動生成 skill** — `.synapse/workflows/<name>.yaml`
   から `synapse workflow sync` が `<!-- synapse-workflow-autogen -->`
   マーカー付きで生成する SKILL.md。例: `post-impl-codex`,
   `parallel-docs-simplify-sync`。
3. **ローカル複製** — `.claude/skills/` と `.agents/skills/` は上の
   1 と 2 の実行環境向けコピー。正本は `plugins/synapse-a2a/skills/`。

### "skill のように見える" が別物のもの

- **MCP Resource** — `synapse://instructions/default` などの URI で
  配る instruction 資源。Markdown という点は skill に似るが、**LLM が
  URI 経由で引く機械可読な配信単位**であり、配布チャネルである。
- **MCP Tool** — `bootstrap_agent`, `list_agents`, `analyze_task`,
  `canvas_post`。LLM が呼び出せる動的 API。**実行可能な関数**であり、
  人間が読む指示集ではない。
- **CLI コマンド** — `synapse send`, `spawn`, `kill`, `wiki query`。
  副作用と状態を持つ操作。**命令型の制御面**であり、再利用可能な
  プリセットとは役割が違う。

### 現状の曖昧さが生む具体的な不便

- `.claude/skills/` には **3 系統の skill が混在** している: 外部配布
  される authored、workflow から自動生成される autogen、このリポジトリ
  だけで使われる local dev。どれがどれかは SKILL.md を開かないと
  分からない。
- `plugins/synapse-a2a/skills/` と `.claude/skills/` の **ミラー関係**
  が手動運用で、片方だけ更新される事故（drift）が何度か起きている。
  v0.26.5 で 23 skill 全部に `license: MIT` を入れたのは、`gh skill
  publish` 対応の布石であり、配布は `gh skill` に寄せる方針の裏返し。
- autogen skill の**生成元 YAML が消えた「残骸」が実際に発生している**:
  2026-04-20 時点で `.claude/skills/my-review/` と
  `.claude/skills/user-wf/` は `synapse-workflow-autogen` マーカー付き
  だが、`.synapse/workflows/` に対応する YAML がない。責務が曖昧な
  ままでは lifecycle 判断ができずこの種の drift が累積する。
- 新規参加者が「MCP にも skill があるの?」と誤解しやすい。実際には
  MCP が配るのは **instruction resource** であって skill ではない。

---

## 検討した選択肢

### 1. 現状維持

最も安全だが、上記の曖昧さと drift リスクがそのまま残る。#610 の
DoD（責務のドキュメント化）を満たさない。

### 2. 全部を MCP Resource にする

「SKILL.md も MCP 経由で配ればよい」という案。

- Claude Code / Codex のような MCP 対応クライアントに限れば成立する。
- しかし Copilot CLI のような **MCP tools-only** 環境や、MCP 非対応の
  エージェントでは skill を読めなくなる。
- `gh skill` が提供する version pinning / provenance メタデータ /
  `--agent` ターゲティングを自前で再実装することになる。
- → **過剰**。配布は既に `gh skill` がある。

### 3. 全部を `gh skill` に寄せる

`synapse workflow sync` の自動生成をやめて、すべて手書き SKILL.md
として `gh skill` 経由で配る案。

- workflow YAML の価値（1つの YAML から SKILL.md を導出できる一貫性）
  を捨てることになる。
- workflow のコード生成ロジック自体は便利なので、単に出力先を整理
  すれば済む話。
- → **もったいない**。workflow は残したい。

### 4. 責務を層ごとに切り分ける（採用）

skill は「behavior preset」、MCP resource は「URI で配る静的
instruction」、MCP tool は「LLM が呼ぶ動的 API」、CLI は「状態を持つ
命令型操作」、`gh skill` は「skill 配布 CLI」と明示的に分ける。

skill の中身は生成元と配布範囲で **3 サブカテゴリ** に整理する:

- **Published authored skill** — `plugins/synapse-a2a/skills/` に置か
  れて `gh skill publish` で外に配る、人が書いた SKILL.md。
- **Workflow-autogen skill** — `.synapse/workflows/*.yaml` を正本と
  して `synapse workflow sync` が生成する、機械生成の SKILL.md。外に
  は配らない。
- **Local dev skill** — このリポジトリの開発作業用に `.claude/skills/`
  や `.agents/skills/` に直接置く、人が書いた SKILL.md。外には配らない。

この整理のもとでは、どこに何が属すかが 1 枚の表で説明でき、drift
（たとえば生成元 YAML が消えた orphan autogen skill）の検出ルールも
機械的に書き下せる。

---

## 推奨アーキテクチャ

### 責務マトリクス

| 層 | 役割 | 誰が書く | いつ読む | 代表例 |
|---|---|---|---|---|
| **Skill** | 再利用可能な behavior preset (人間が読む Markdown 指示集) | 人間 or workflow sync | Skill tool 呼び出し時 | `synapse-a2a`, `code-review`, `post-impl-codex` |
| **MCP Resource** | 静的 instruction の URI 配信 | 人間 (`instructions/*.md`) | エージェント起動時の bootstrap | `synapse://instructions/default` |
| **MCP Tool** | LLM が呼ぶ動的 API | 人間 (Python) | LLM が能動的に呼び出す | `list_agents`, `analyze_task` |
| **CLI** | 命令型の制御面 (副作用 / 状態) | 人間 (Python) | 人間 or エージェントが明示的に呼ぶ | `synapse send`, `synapse spawn` |
| **`gh skill`** | Skill の配布 CLI | GitHub CLI 公式 | install / publish / update 時 | `gh skill install <repo> <name>` |

### Skill の内訳（3サブカテゴリ）

Skill そのものは 3 種類に分解して整理する。いずれも「behavior preset」
という同じ責務を持つが、**生成元と配布範囲が違う**。

| サブカテゴリ | 生成元 | 置き場 (正本) | 配布 | マーカー | 例 |
|---|---|---|---|---|---|
| **Published authored skill** | 人間が直接書く SKILL.md | `plugins/synapse-a2a/skills/<name>/` | `gh skill publish` で**外部配布** | なし | `synapse-a2a`, `code-review`, `release` |
| **Workflow-autogen skill** | `.synapse/workflows/<name>.yaml` から `synapse workflow sync` で生成 | YAML が正本、SKILL.md は `.claude/skills/` 等の派生 | **配布しない** (このリポジトリのランタイム専用) | `<!-- synapse-workflow-autogen -->` | `post-impl`, `post-impl-claude`, `post-impl-codex` |
| **Local dev skill** | 人間が直接書く SKILL.md、このリポジトリの開発作業用 | `.claude/skills/<name>/` と `.agents/skills/<name>/` | **配布しない** (手元だけ) | なし | `my-review`, `user-wf` |

ポイント:

- **Published** と **Local dev** はどちらも「人が書く」点では同じだが、
  置き場で配布の有無を切り分ける。`plugins/synapse-a2a/skills/` に
  置けば `gh skill publish` の対象になり、`.claude/skills/` 等だけに
  置けばランタイムでしか使われない。
- **Workflow-autogen** は「同じ skill の皮をかぶった、生成スクリプトの
  出力物」。正本は `.synapse/workflows/` の YAML、SKILL.md は派生物で
  ありビルド成果物と同じ扱い。
- **Local dev skill が必要な理由**: リポジトリの開発ワークフローだけ
  に意味があり、外の利用者に配る価値がないプリセット（レビュー
  チェックリスト、社内ルーティン等）が存在する。Published との差は
  "外に出すか" だけで、SKILL.md の書式は同一。

### Drift の定義と検出ルール

上記 3 サブカテゴリを明示すると、**drift（残骸 skill）を 1 行ルールで
検出できる**ようになる。

- `.claude/skills/<name>/SKILL.md` に `synapse-workflow-autogen` マーカー
  が入っているのに、対応する `.synapse/workflows/<name>.yaml` が
  存在しない → **orphan autogen skill**。YAML を復元するか、または
  Local dev skill として「autogen マーカーを外して手書き扱いに昇格
  させる」かのどちらかで解消する。
- `.claude/skills/<name>/` にだけ存在し、`plugins/synapse-a2a/skills/<name>/`
  にも `.synapse/workflows/<name>.yaml` にも存在しない → **Local dev
  skill として正規化**する。該当ファイルの README かコミットログで
  「これは local dev skill である」と明示するのが望ましい。

過去の実例: 本 RFC の初版時点 (2026-04-20) で `my-review` と `user-wf`
が autogen マーカー付きながら YAML 正本がない orphan 状態にあった。
いずれも `description` と本文がひな形テンプレートのまま（"Workflow:
Describe what this workflow does"）で、どこからも参照されていなかった
ため、本 PR で 4 ファイル (`.claude/skills/{my-review,user-wf}` と
`.agents/skills/{my-review,user-wf}`) を削除した。

### ディレクトリ規約

| ディレクトリ | 役割 | 正本/派生 |
|---|---|---|
| `plugins/synapse-a2a/skills/` | Published authored skill の正本 | **正本** |
| `.synapse/workflows/` | Workflow YAML の正本 | **正本** |
| `.claude/skills/` | Claude Code ランタイム用コピー。Published のミラー + Workflow-autogen の派生 + Local dev (このディレクトリが正本) が同居 | 派生 (Local dev のみ正本) |
| `.agents/skills/` | 他エージェントランタイム用コピー。`.claude/skills/` と同構成・同内容 | 派生 (Local dev のみ正本) |

`.claude/skills/` と `.agents/skills/` のうち、Published authored のミラー
と Workflow-autogen の派生は **「ビルド成果物」** として扱い、人間は
編集しない。Local dev skill は同じディレクトリ内にあるが、そこが正本
なので人間が直接編集してよい。サブカテゴリを SKILL.md frontmatter や
マーカーで識別できるようにするのは後続タスク。

---

## Issue #610 の "wrapper = A2A プリセット" をどう読むか

作者の原文は以下:

> 以下のいずれかに統一：
> - **wrapper（推奨）**: A2A プリセットとして扱う

これは上の責務マトリクスの **Skill 行** の定義そのものである。つまり:

- skill は「A2A を使うエージェントの振る舞いを記述した再利用可能な
  プリセット」である
- 独立したプログラム層ではなく、MCP や CLI の**上に乗る薄いラッパー**
  である（だから "wrapper"）
- 配布は `gh skill` に任せ、生成元は人間 (authored) または workflow
  (autogen) の 2 経路に閉じる

この定義を採ると、MCP / CLI / `gh skill` との「被り」は解消する。
被りではなく**役割分担**として記述できる。

---

## Definition of Done に対するマッピング

Issue #610 の DoD は 2 項目:

1. **skills の責務がドキュメント化される** → **本ドキュメントが該当**
2. **実装がその責務に沿って整理される** → 本 PR で **orphan autogen
   skill (`my-review`, `user-wf`) の削除**までを実施。残りの整理
   (GENERATED.md 配置、workflow sync の orphan 検出強化、README 追記
   など) は後続タスク (下記)

### 後続タスクの候補

この RFC が合意されたら、以下を別 PR で進められる。

- [ ] `guides/skills.md` の新設または `docs/skills-management.md` の
      冒頭に「Skill とは」セクションを足し、本 RFC の責務マトリクス
      と 3 サブカテゴリ (Published / Workflow-autogen / Local dev) を
      1 画面で見えるよう要約する。既存のコマンドリファレンスはその
      まま残す。
- [ ] `plugins/synapse-a2a/skills/` の README に「ここに置いた skill
      は `gh skill publish` で外部配布される」旨を明記し、Local dev
      skill はここには置かないルールを文書化。
- [ ] `.claude/skills/` と `.agents/skills/` に `GENERATED.md` もしくは
      類似のREADME を置き、派生物 (Published のコピー / Workflow-autogen)
      は手編集禁止であること、Local dev skill (正本がここにしかない
      SKILL.md) は手編集可であることを明示する。
- [ ] `synapse workflow sync` の出力 SKILL.md に、先頭コメントとして
      「これは `.synapse/workflows/<name>.yaml` からの自動生成物です」
      を明示する一行を足す（現状のマーカー `<!-- synapse-workflow-autogen -->`
      は機械可読だが人間向けの説明ではない）。加えて、生成元 YAML が
      存在しない orphan autogen skill を検出する軽量チェックを
      `synapse workflow sync` に追加する。
- [x] 現存する orphan autogen skill (`my-review`, `user-wf`) を整理する
      → 本 PR で削除済み (`.claude/skills/` と `.agents/skills/` の両方)。
- [ ] MCP resource と skill の混同を避けるため、MCP resource 側の
      description を「instruction resource (not a skill)」のように
      明示する。

---

## 非目標

本 RFC では次は扱わない。

- `gh skill` の内部仕様や cross-repo 配布戦略。これは GitHub CLI 側
  の責任で、Synapse 側では `gh skill publish` に適合するフロント
  マターを用意するだけで十分。
- MCP tool の拡張（`list_skills` のような新 tool の追加）。skill
  は静的な Markdown 配布物として `gh skill` に任せる方針なので、
  MCP 経由で skill 一覧を提供する必要は当面ない。
- `.claude/skills/` の自動同期 CI 化。手動 `synapse workflow sync`
  で運用できている。

---

## 参考

- Issue #610: skills の役割再定義 (documentation + discussion)
- `docs/design/mcp-bootstrap.md` — MCP を "配布層" に限定した設計判断
- `docs/skills-management.md` — `gh skill` 運用の How
- `docs/design/llm-wiki.md` — 「ロジックはゼロ、Schema を読ませるだけ」
  という Synapse の一貫した設計思想の先行例
