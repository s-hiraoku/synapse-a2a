# MCP Bootstrap Design for Synapse

Synapse の初期インストラクション配布を、どこまで MCP (Model Context Protocol) に寄せるべきかを整理した設計メモ。

このドキュメントの結論は次の 1 行に集約される。

> Synapse 全体を MCP 化するのではなく、初期インストラクション配布だけを MCP に切り出すのが最もきれいで現実的。

---

## なぜ MCP を使うのか

現状の Synapse は、エージェント起動後に PTY 経由で初期インストラクションを注入する方式を取っている。この方式は CLI 主体の Synapse と相性がよく、完全に失敗しているわけではない。一方で、次の問題がある。

- 初期インストラクションが長くなりやすく、トークン消費が大きい
- PTY の表示ノイズや TUI の再描画が混ざると、注入内容や応答回収が不安定になる
- `/clear` や `--resume` 後の再注入フローが分かりにくい
- agent ごとの差分、role ごとの差分、project ごとの差分が混ざりやすい
- Claude Code や Codex のような MCP 対応クライアントでは、よりきれいな配布手段がある

要するに、問題は Synapse 全体ではなく、主に bootstrap の配布層に集中している。

---

## 現状方式の評価

現状方式にも利点はある。

- CLI 主体の設計と整合する
- MCP 非対応の agent でも同じ方式で起動できる
- 追加のサーバーや transport を必須にしない
- ローカル完結で動作する

したがって、全面置換は過剰である。捨てるべきなのは CLI ではなく、初期インストラクション配布の重さと不安定さである。

---

## 検討した選択肢

### 1. 現状維持

最も安全だが、初期インストラクションの重さと PTY 依存の問題は残る。

### 2. Synapse 全体を MCP 化

設計としては一見きれいに見えるが、実際にはやりすぎである。

- task board
- memory
- canvas
- file safety
- process 管理
- tmux / worktree 運用

まで一気に巻き込むことになり、CLI の強みを失いやすい。

### 3. 初期インストラクションだけ MCP resources 化

最小の変更で大きな改善が得られる。

- 長い instructions を prompt に埋め込まなくてよい
- 静的な文書を resource として再利用できる
- Claude / Codex のような MCP 対応 client にだけ先行導入できる

### 4. resources + bootstrap tool の併用

最終形として最もきれい。静的な instruction は resources、動的な runtime context は tools に分離できる。

---

## 推奨アーキテクチャ

推奨は次の三層構成である。

1. Synapse Core
2. Synapse CLI
3. Synapse MCP Layer

### Synapse Core

Synapse の状態と実務機能を保持する中心層。

- registry
- task board
- shared memory
- file safety
- canvas
- history

### Synapse CLI

人間と agent が日常的に使う主操作面。CLI 主体は維持する。

- `synapse start`
- `synapse stop`
- `synapse send`
- `synapse tasks`
- `synapse memory`
- `synapse canvas`

### Synapse MCP Layer

MCP 対応 client 向けの integration layer。初期化と参照に責務を絞る。

- 初期インストラクション配布
- runtime context の取得
- 将来的な lightweight state access

この構成では、CLI 主体を保ったまま bootstrap をきれいに切り出せる。

---

## MCP サーバ構成

MCP サーバは 1 つで十分であり、内部は `resources` と `tools` に分ける。

### resources

静的または半静的な instruction / policy / 参照情報を提供する。

候補 URI:

- `synapse://instructions/default`
- `synapse://instructions/file-safety`
- `synapse://instructions/shared-memory`
- `synapse://instructions/learning`
- `synapse://instructions/role/<role>`
- `synapse://instructions/agent/<agent_id>`

resources に向いている情報:

- 共通の初期インストラクション
- file safety の運用ルール
- shared memory のルール
- role 固有の行動方針
- agent 固有の補足

### tools

動的な runtime context や、その時点の状態取得を担当する。

最小構成の候補:

- `bootstrap_agent(agent_id)`
- `get_runtime_context(agent_id)`

将来の拡張候補:

- `get_peers()`
- `get_task_board()`
- `get_file_locks()`
- `search_memory(query)`
- `get_canvas_summary()`

重要なのは、静的な information を resources、動的な information を tools に分けること。

---

## bootstrap の責務

bootstrap は「長い説明文」ではなく、「必要な resources と runtime context を解決する入口」にする。

最小 prompt のイメージ:

```text
You are synapse-codex-8120.
Role: developer.
Read synapse://instructions/default and synapse://instructions/role/developer.
Then call bootstrap_agent("synapse-codex-8120").
Follow safety rules before any file or task operations.
```

`bootstrap_agent()` が返す情報のイメージ:

```json
{
  "agent_id": "synapse-codex-8120",
  "role": "developer",
  "instruction_resources": [
    "synapse://instructions/default",
    "synapse://instructions/file-safety",
    "synapse://instructions/role/developer"
  ],
  "runtime": {
    "working_dir": "/repo",
    "features": ["tasks", "memory", "canvas", "file_safety"]
  }
}
```

この方式なら、prompt は短く保ちつつ、必要な instruction を構造化して取得できる。

---

## なぜ一気に実装しないのか

一気に実装すると、次のものを同時に変えることになる。

- prompt 設計
- PTY bootstrap
- MCP resources
- MCP tools
- agent ごとの対応差
- fallback
- resume / reinst の再注入フロー

これでは切り分けが難しい。特に Claude / Codex と Gemini / OpenCode / Copilot では MCP 対応状況が異なるため、一括移行は壊れたときの影響範囲が大きい。

したがって、設計は最終形を見据えつつ、実装は段階的に進めるべきである。

---

## 段階的な導入計画

### Phase 1: resources only

最初にやるべき段階。

- `synapse://instructions/default` などの resources を追加
- Claude / Codex だけ opt-in で利用
- 非 MCP client は現状維持

狙い:

- bootstrap 文の短縮
- 長文 prompt 注入の削減
- resource 配布モデルの検証

### Phase 2: bootstrap tool

次に、動的な runtime context 取得を導入する。

- `bootstrap_agent(agent_id)`
- `get_runtime_context(agent_id)`

狙い:

- role / agent / working_dir / available features を構造化して返す
- `/clear` や resume 後の復旧を明確にする

### Phase 3: optional state tools

必要性が明確になったら追加する。

- peers
- task board
- file locks
- memory search

この段階は bootstrap の改善とは分離して判断するべきである。

---

## fallback 方針

MCP 非対応 client がいる以上、fallback はしばらく残る。

推奨方針:

- MCP 対応 client
  - resources / tools を利用
- 非 MCP client
  - 現行の PTY bootstrap を維持
- ただし両者とも、bootstrap prompt 自体は短く寄せる

つまり、完全な一本化ではなく、配布手段だけを二系統にする。

---

## 判断ポイント

この設計で重視している判断基準は次の通り。

- CLI 主体を壊さない
- 初期インストラクション配布だけをきれいにする
- 静的情報と動的情報を分離する
- MCP 対応 client から先に改善する
- 非対応 client の運用を壊さない

最終的に最もきれいなのは、CLI 主体の Synapse を残したまま、bootstrap と参照だけを MCP に切り出す構成である。

---

## 結論

Synapse を全面的に MCP 化する必要はない。

ただし、初期インストラクション配布は MCP と非常に相性がよい。したがって、次の方針を採るのが妥当である。

- Synapse Core はそのまま
- CLI 主体もそのまま
- 初期インストラクション配布だけを MCP resources に移す
- 必要に応じて bootstrap tools を追加する
- 非 MCP client には fallback を残す

これが、実装コスト、移行リスク、将来の拡張性のバランスが最もよい構成である。
