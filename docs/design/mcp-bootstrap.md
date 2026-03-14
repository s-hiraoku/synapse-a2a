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

#### Phase 1 の実装メモ

Phase 1 はあくまで暫定であり、既存の PTY 初期注入を置き換えない。

- `synapse mcp serve` を追加する
- `synapse://instructions/default` を返す
- optional instruction files が存在する場合のみ
  - `synapse://instructions/file-safety`
  - `synapse://instructions/shared-memory`
  - `synapse://instructions/learning`
  - `synapse://instructions/proactive`
  を列挙する
- `default` resource は base instruction のみを返し、optional files は別 resource に分ける

起動例:

```bash
synapse mcp serve --agent-id synapse-codex-8120 --agent-type codex --port 8120
```

この段階ではまだやらないこと:

- peers / tasks / memory / locks の MCP tool 化

#### 現時点の実装状態

この設計メモに対応する最初の実装では、次だけを追加する。

- `synapse mcp serve`
- MCP stdio transport 上の `initialize`
- `resources/list`
- `resources/read`
- instruction resources の読み出し

実装済みのもの:

- `bootstrap_agent()` tool
- PTY bootstrap の自動切り替え — `has_mcp_bootstrap_config()` により Claude Code, Codex, Gemini CLI, OpenCode, Copilot で MCP 設定検出時に PTY instruction injection を自動スキップ

まだ未実装のもの:

- bootstrap prompt の自動短縮
- project 固有 context や peers/tasks の動的取得

つまり、現時点の実装は「instruction resources の配布」「bootstrap_agent による runtime context 取得」「MCP 検出時の PTY 自動スキップ」までである。

#### MCP client から見た最小フロー

MCP client 側の最小フローは次の通り。

1. `initialize`
2. `resources/list`
3. `resources/read` で `synapse://instructions/default` を取得
4. 必要に応じて `file-safety` や `shared-memory` を追加で取得

この段階では、agent が自動的にどの resources を読むかまでは Synapse 側で強制しない。まずは「読める状態」を作り、その後に client integration を追加する。

#### 参考: `resources/read` の返り値イメージ

```json
{
  "contents": [
    {
      "uri": "synapse://instructions/default",
      "mimeType": "text/markdown",
      "text": "[SYNAPSE INSTRUCTIONS - DO NOT EXECUTE - READ ONLY]\n..."
    }
  ]
}
```

#### Claude Code / Codex での設定例

Phase 2 の検証では、MCP client 側が `synapse mcp serve` を subprocess として起動する想定で試す。

Claude Code の例 (`.mcp.json` or `~/.claude.json`):

```json
{
  "mcpServers": {
    "synapse": {
      "command": "synapse",
      "args": ["mcp", "serve", "--agent-id", "synapse-claude-8100", "--agent-type", "claude", "--port", "8100"]
    }
  }
}
```

最小形は `"args": ["mcp", "serve"]` で、追加の `--agent-id` や `--agent-type` は検証時に上乗せする。

Codex CLI の例 (`~/.codex/config.toml`):

```toml
[mcp_servers.synapse]
command = "/path/to/uv"
args = ["run", "--directory", "/path/to/repo", "python", "-m", "synapse.mcp", "--agent-id", "synapse-codex-8120", "--agent-type", "codex", "--port", "8120"]
```

最小形は `args = ["mcp", "serve"]`。

この設定は最終形ではない。現状は `bootstrap_agent()` が導入されたとはいえ、接続時の agent context を明示した方が試験しやすいため、設定例では `agent-id` と `agent-type` を渡している。

#### 手動試験手順

最低限の疎通確認は次の順で行う。

1. `initialize`
2. `resources/list`
3. `resources/read` for `synapse://instructions/default`
4. `tools/list`
5. `tools/call` for `bootstrap_agent`

期待する確認点:

- `default` resource は静的 instruction を返す
- `bootstrap_agent` は `agent_id`, `working_dir`, `instruction_resources` を返す
- optional resource (`file-safety`, `shared-memory` など) が必要に応じて列挙される

テスト実行:

```bash
pytest tests/test_mcp_bootstrap.py -q
```

---

## エージェント別の MCP 設定

ここでは、Synapse MCP を各クライアントから利用できる状態にするための設定場所、書式、実運用上の注意点をまとめる。

### 共通方針

今回の Synapse MCP は、古いグローバル synapse バイナリではなく、現在の repo checkout を直接使う方が安全である。

理由:

- グローバル `synapse` が古い version を指すことがある
- `synapse.cli` 経由より `python -m synapse.mcp` の方が stdio 汚染を避けやすい
- `uv run --directory <repo>` にすると、今の checkout の実装で MCP server を起動できる

推奨の起動形は次の 1 つに揃える。

```bash
/path/to/uv run --directory /path/to/repo python -m synapse.mcp --agent-id <agent-id> --agent-type <agent-type> --port <port>
```

### Claude Code

公式ドキュメント:

- Claude Code MCP docs: https://code.claude.com/docs/en/mcp

設定場所:

- local scope: `~/.claude.json`
- user scope: `~/.claude.json`
- project scope: `.mcp.json`

Claude Code の project scope は `.mcp.json` が正であり、`.claude/mcp.json` ではない。project scope を使う場合は approval が必要になる。

公式 docs では次のように整理されている。

- `~/.claude.json` に local/user scope を保存
- project-scoped server は project root の `.mcp.json`

推奨設定例:

```json
{
  "mcpServers": {
    "synapse-user": {
      "type": "stdio",
      "command": "/path/to/uv",
      "args": [
        "run",
        "--directory",
        "/path/to/repo",
        "python",
        "-m",
        "synapse.mcp",
        "--agent-id",
        "synapse-claude-8100",
        "--agent-type",
        "claude",
        "--port",
        "8100"
      ],
      "env": {}
    }
  }
}
```

注意点:

- `claude mcp add --scope user` で user config に入れられる
- project scope は `.mcp.json`
- Claude Code は newline-delimited JSON-RPC を使うので、server 側もそれに合わせる必要がある

### Codex

参考:

- OpenAI MCP docs: https://developers.openai.com/resources/docs-mcp

設定場所:

- `~/.codex/config.toml`

Codex の MCP server は `[mcp_servers.<name>]` で定義する。今回の環境でもその形で稼働している。

推奨設定例:

```toml
[mcp_servers.synapse]
command = "/path/to/uv"
args = [
  "run",
  "--directory",
  "/path/to/repo",
  "python",
  "-m",
  "synapse.mcp",
  "--agent-id",
  "synapse-codex-8120",
  "--agent-type",
  "codex",
  "--port",
  "8120",
]
```

注意点:

- `command = "synapse"` だと古いグローバル `synapse` を掴むことがある
- そのため Codex では `uv run --directory ... python -m synapse.mcp` に寄せる方が安全

### Gemini CLI

公式ドキュメント:

- Gemini CLI MCP docs: https://geminicli.com/docs/tools/mcp-server

設定場所:

- user scope: `~/.gemini/settings.json`
- project scope: `.gemini/settings.json`

Gemini CLI docs では、`settings.json` の `mcpServers` に server を定義するとされている。

公式の基本構造:

```json
{
  "mcpServers": {
    "serverName": {
      "command": "path/to/server",
      "args": ["--arg1", "value1"],
      "env": {},
      "cwd": "./server-directory",
      "timeout": 30000,
      "trust": false
    }
  }
}
```

Gemini CLI の公式 docs に合わせるなら、`~/.gemini/settings.json` の `mcpServers` 形式へ寄せる方がよい。

現時点の結論:

- Gemini のために Synapse MCP server 側へ追加実装を入れる必要はない
- 課題は server ではなく Gemini 側の設定場所・設定形式の整理である
- したがって、まずは Gemini の公式本線である `~/.gemini/settings.json` / `.gemini/settings.json` に寄せて接続確認するのが次の作業になる

公式準拠の推奨設定例:

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
        "synapse-gemini-8110",
        "--agent-type",
        "gemini",
        "--port",
        "8110"
      ],
      "timeout": 5000,
      "trust": true
    }
  }
}
```

### OpenCode

公式ドキュメント:

- OpenCode config docs: https://opencode.ai/docs/config
- OpenCode MCP docs: https://opencode.ai/docs/mcp-servers

設定場所:

- global: `~/.config/opencode/opencode.json`
- project: `opencode.json`

OpenCode docs では global config を `~/.config/opencode/opencode.json` としている。MCP server は `mcp` オブジェクトで管理する。

推奨設定例:

```json
{
  "mcp": {
    "synapse": {
      "type": "local",
      "command": [
        "/path/to/uv",
        "run",
        "--directory",
        "/path/to/repo",
        "python",
        "-m",
        "synapse.mcp",
        "--agent-id",
        "synapse-opencode-8130",
        "--agent-type",
        "opencode",
        "--port",
        "8130"
      ],
      "enabled": true,
      "timeout": 5000
    }
  }
}
```

### Copilot

設定場所:

- `~/.copilot/mcp-config.json`

Copilot CLI は MCP をサポートしており、`~/.copilot/mcp-config.json` に server を定義する。

推奨設定例:

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

注意点:

- MCP 設定が存在する場合、PTY instruction injection は自動スキップされる
- MCP 設定がない場合は従来通り PTY フォールバックで動作する

## 参考リンク

- Claude Code MCP docs: https://code.claude.com/docs/en/mcp
- OpenAI MCP docs: https://developers.openai.com/resources/docs-mcp
- Gemini CLI MCP docs: https://geminicli.com/docs/tools/mcp-server
- OpenCode config docs: https://opencode.ai/docs/config
- OpenCode MCP docs: https://opencode.ai/docs/mcp-servers

### Phase 2: bootstrap tool

次に、動的な runtime context 取得を導入する。

- `bootstrap_agent(agent_id)`
- `get_runtime_context(agent_id)`

狙い:

- role / agent / working_dir / available features を構造化して返す
- `/clear` や resume 後の復旧を明確にする

Phase 2 では、resource は静的、agent 固有値は tool に寄せる。

- `synapse://instructions/default` は静的な instruction document にする
- agent ID や port や working directory は `bootstrap_agent()` で返す
- `tools/list` で bootstrap tool を列挙する
- `tools/call` で runtime context を返す

この切り分けにより、MCP resource がテンプレート展開 API になるのを避けられる。次の実装では `default resource を静的に` し、agent 固有値は tool へ移す。

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
