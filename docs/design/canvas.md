# Synapse Canvas - Design Document

## Overview

Synapse Canvas is a shared visual output surface for agents. When an agent needs to express something beyond text (diagrams, rich tables, interactive charts, design mockups), it sends a **Canvas Message** via a unified protocol. A local web server renders it in the browser in real-time.

### Design Principles

1. **Agent-driven**: Canvas is the agent's drawing board — agents decide what to show.
2. **Protocol-first**: One unified JSON protocol for all communication. No type-specific CLI commands.
3. **Expressive**: Agents can render anything — from Mermaid diagrams to raw HTML/CSS.
4. **Dead simple for agents**: One command, one JSON payload. That's it.
5. **Zero-config for users**: `synapse canvas` starts the server. No npm, no build step.

---

## Core Idea: Canvas Message Protocol

All agent-to-Canvas communication uses a single JSON protocol.

### The Protocol

```jsonc
{
  // Required
  "type": "render",                    // Message type (see below)
  "content": {                         // What to render
    "format": "mermaid",               // Renderer to use
    "body": "graph TD; A-->B; B-->C"   // Content body
  },

  // Identity (auto-populated by CLI)
  "agent_id": "synapse-claude-8103",
  "agent_name": "Gojo",

  // Optional metadata
  "title": "Auth Flow Design",
  "card_id": "auth-flow",             // Stable ID for updates
  "pinned": false,
  "tags": ["design", "auth"]
}
```

### Message Types

| Type | Purpose |
|---|---|
| `render` | Display content on Canvas |
| `update` | Update existing card (requires `card_id`) |
| `clear` | Remove cards (`card_id` or `agent_id` filter) |
| `notify` | Ephemeral toast notification (disappears after N seconds) |

### Content Formats

The `content.format` field determines how `content.body` is rendered. This is the expressiveness layer — new formats can be added without protocol changes.

| Format | Body | Renderer | Use Case |
|---|---|---|---|
| `mermaid` | Mermaid source | mermaid.js | Flowcharts, sequence diagrams, ER diagrams, Gantt |
| `markdown` | Markdown text | marked.js + highlight.js | Design docs, explanations, formatted text |
| `html` | Raw HTML string | Sandboxed iframe | Full freedom — any visual expression |
| `table` | `{headers: [...], rows: [[...]]}` | Native HTML | Structured data, test results, comparisons |
| `json` | Any JSON | Collapsible tree viewer | API responses, config, data structures |
| `diff` | Unified diff | diff2html | Code changes, before/after |
| `chart` | Chart.js config object | Chart.js | Bar, line, pie, radar charts |
| `image` | Base64 data URI or URL | `<img>` | Screenshots, generated images |
| `code` | Source code string + `lang` | highlight.js | Syntax-highlighted code blocks |

**Key: `html` format** — This is the escape hatch. When no predefined format fits, agents can send raw HTML. This makes expression essentially unlimited.

```jsonc
// Agent can render ANYTHING via html format
{
  "type": "render",
  "content": {
    "format": "html",
    "body": "<div style='display:grid;grid-template-columns:1fr 1fr;gap:1rem'><div><h3>Before</h3><pre>old code</pre></div><div><h3>After</h3><pre>new code</pre></div></div>"
  },
  "title": "Refactoring Comparison"
}
```

### Composite Cards (Multiple Sections)

A single card can contain multiple content sections for rich layouts:

```jsonc
{
  "type": "render",
  "content": [
    { "format": "markdown", "body": "## Architecture Overview\nThis system uses..." },
    { "format": "mermaid", "body": "graph TD; API-->DB; API-->Cache" },
    { "format": "table", "body": {"headers": ["Component","Status"], "rows": [["API","Done"],["DB","WIP"]]} }
  ],
  "title": "System Design",
  "card_id": "system-design"
}
```

This enables agents to compose rich, multi-section cards — like a document with embedded diagrams and tables.

---

## CLI Interface

All commands are available to both agents and humans. No distinction.

### Server

```bash
synapse canvas serve [--port 3000] [--no-open]    # Start Canvas server (auto-opens browser)
```

### Server Auto-Start

Canvas サーバーの多重起動を防ぎつつ、手動起動の手間をなくす。

**フロー**（すべての投稿コマンドで共通）:

```
synapse canvas mermaid "..."
  │
  ├─ GET http://localhost:{port}/api/health
  │
  ├─ 200 OK → サーバー起動済み → そのまま POST /api/cards
  │
  └─ Connection refused → 未起動
       │
       ├─ バックグラウンドでサーバー起動（--no-open 相当）
       ├─ health check をリトライ（最大 3 秒、500ms 間隔）
       └─ 起動確認後 → POST /api/cards
```

**ルール**:
- `synapse canvas serve` (明示起動): フォアグラウンド実行 + ブラウザ自動オープン
- 自動起動: バックグラウンドプロセス + ブラウザは開かない
- PID ファイル (`.synapse/canvas.pid`) で多重起動を防止
- `synapse canvas serve` 実行時も PID ファイルをチェックし、既に起動中ならポートを表示して終了

**Health endpoint**:
```
GET /api/health → 200 {"status": "ok", "port": 3000, "cards": 5}
```

### Card Posting (Shortcuts)

Shortcuts generate Canvas Message Protocol JSON internally and POST to `/api/cards`.
All posting commands trigger auto-start if server is not running.

```bash
synapse canvas mermaid "graph TD; A-->B" --title "Auth Flow"
synapse canvas markdown "## Design\nThis is..." --title "Design Doc"
synapse canvas table '{"headers":["a","b"],"rows":[...]}' --title "Results"
synapse canvas html "<div>anything</div>" --title "Custom"
synapse canvas code "def foo(): pass" --lang python --title "Impl"
synapse canvas diff "--- a/f.py\n+++ b/f.py\n..." --title "Changes"
synapse canvas chart '{"type":"bar","data":{...}}' --title "Coverage"
synapse canvas image "https://..." --title "Screenshot"
```

### Card Posting (Full Control)

```bash
synapse canvas post '<Canvas Message JSON>'       # Raw protocol JSON
```

### Common Options (all posting commands)

```bash
--title "Card Title"          # Card title
--id my-card                  # Stable ID for updates (upsert). Auto-generated (8-char UUID) if omitted.
--pin                         # Pin to top (exempt from TTL expiry)
--tag design --tag auth       # Tags for filtering
--file ./diagram.mmd          # Read body from file instead of argument
```

### Search & Management

```bash
synapse canvas list                    # All cards
synapse canvas list --mine             # Own cards only (auto-filter by $SYNAPSE_AGENT_ID)
synapse canvas list --search "auth"    # Title search
synapse canvas list --type mermaid     # Filter by format
synapse canvas list --mine --search "auth"  # Combine filters
synapse canvas delete <card_id>        # Delete card (own cards only)
synapse canvas clear                   # Clear all cards
synapse canvas clear --agent claude    # Clear specific agent's cards
```

Output example:

```
CARD_ID     TYPE      TITLE              AGENT         UPDATED
auth-flow   mermaid   Auth Flow          Gojo          2 min ago
e3f1a2b0    table     Test Results       gemini-8110   5 min ago
```

### ID Strategy

- `--id` specified: Use as `card_id` for upsert (same as Shared Memory's `key`)
- `--id` omitted: Auto-generate 8-char UUID (same format as A2A Task ID: `uuid4()[:8]`)
- Agents can recover forgotten IDs via `synapse canvas list --mine`

### How Shortcuts Map to Protocol

```bash
synapse canvas mermaid "graph TD; A-->B" --title "Flow" --id auth
```

Internally generates and sends to `POST /api/cards`:
```json
{
  "type": "render",
  "content": {"format": "mermaid", "body": "graph TD; A-->B"},
  "title": "Flow",
  "card_id": "auth",
  "agent_id": "$SYNAPSE_AGENT_ID",
  "agent_name": "$SYNAPSE_AGENT_NAME"
}
```

### Browser UI (human only)

```
http://localhost:3000
```

Agents don't see the browser. This is the only human-exclusive interface.

| Feature | Method |
|---|---|
| View cards | Just open the page (SSE auto-updates) |
| Filter | By format type, by agent, by tag |
| Pin/unpin | Pin icon on card header |
| Delete card | X button on card header |
| Theme toggle | Dark/light switch |

### HTTP API (programmatic)

```
POST   /api/cards          Create/update card (Canvas Message Protocol)
GET    /api/cards           List cards (JSON, optional ?agent_id=&search=&type= filters)
GET    /api/cards/{id}      Get single card
DELETE /api/cards/{id}      Delete card (own cards only, matched by agent_id)
DELETE /api/cards           Clear all cards (optional ?agent_id= filter)
GET    /api/stream          SSE stream (card_created, card_updated, card_deleted events)
GET    /api/formats         List supported formats (format registry)
```

---

## Architecture

```
                         Browser (localhost:3000)
                              |
                         SSE (EventSource)
                              |
               +--------------+---------------+
               |    Canvas Server (FastAPI)    |
               |    Port: 3000 (dedicated)     |
               +---------+----+----+-----------+
                    POST  |    |    | GET
                 /api/cards    |    /api/cards
                         |    |    |
                         v    v    v
                       canvas.db  registry/
                       (cards)    (agents)

    Agent PTY                          Agent PTY
    +----------+                       +----------+
    | claude   |                       | gemini   |
    +----------+                       +----------+
         |                                  |
    synapse canvas post {...}          synapse canvas post {...}
         |                                  |
         +---- POST /api/cards ----->-------+
                (Canvas Message Protocol)
```

### Key Decision: Separate Server (port 3000)

- Agent servers (8100-8149) are per-agent; Canvas needs one stable URL
- Canvas aggregates all agents' output in one place
- Decoupled lifecycle: Canvas runs independently of any agent

---

## Data Model

### cards table

```sql
CREATE TABLE cards (
    id          TEXT PRIMARY KEY,                -- UUID (internal)
    card_id     TEXT UNIQUE,                     -- Stable ID for upserts (user-specified)
    agent_id    TEXT NOT NULL,                    -- synapse-claude-8103
    agent_name  TEXT,                             -- Custom name (e.g., "Gojo")
    type        TEXT NOT NULL DEFAULT 'render',   -- render | notify
    content     TEXT NOT NULL,                    -- JSON: {format, body} or [{format, body}, ...]
    title       TEXT,
    pinned      INTEGER DEFAULT 0,
    tags        TEXT,                             -- JSON array: ["design", "auth"]
    expires_at  DATETIME,                         -- NULL = use default TTL. Pinned cards: NULL (no expiry)
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_cards_card_id ON cards(card_id);
CREATE INDEX idx_cards_agent ON cards(agent_id);
CREATE INDEX idx_cards_expires ON cards(expires_at);
```

`content` is stored as JSON string. Single format: `{"format":"mermaid","body":"..."}`. Composite: `[{"format":"mermaid","body":"..."},{"format":"table","body":{...}}]`.

### Lifecycle

- **Ephemeral by default**: Cards are in-memory working data. Server restart clears all cards (SQLite DB is recreated).
- **TTL expiry**: Cards expire after `CANVAS_CARD_TTL` (default 1 hour). Expired cards are cleaned up on read or by a background sweep.
- **Pinned cards**: Exempt from TTL. They stay until manually deleted or server restart.
- **Update resets TTL**: When a card is updated via `card_id`, its `expires_at` is refreshed.

---

## Browser UI Details

### SSE Events

```
event: card_created
data: {"id":"...","card_id":"auth","type":"render","content":{...},...}

event: card_updated
data: {"id":"...","card_id":"auth","content":{...},...}

event: card_deleted
data: {"card_id":"auth"}

event: notification
data: {"agent_name":"Gojo","message":"Tests passed!","level":"success"}
```

### Layout

```
+--[Synapse Canvas]--[Filter: All | mermaid | table | ...]--[Agents: All | Gojo | gemini]--+
|                                                                                           |
|  +-- Gojo (claude-8103) ---------- 14:23 -- [pin] [x] --+                                |
|  | System Design                                  pinned |                                |
|  | +---------------------------------------------------+ |                                |
|  | | ## Architecture Overview          (markdown)       | |                                |
|  | | This system uses a layered...                      | |                                |
|  | +---------------------------------------------------+ |                                |
|  | +---------------------------------------------------+ |                                |
|  | | graph TD                          (mermaid)        | |                                |
|  | |   API --> DB                                       | |                                |
|  | |   API --> Cache                                    | |                                |
|  | +---------------------------------------------------+ |                                |
|  | +---------------------------------------------------+ |                                |
|  | | Component | Status               (table)          | |                                |
|  | | API       | Done                                   | |                                |
|  | | DB        | WIP                                    | |                                |
|  | +---------------------------------------------------+ |                                |
|  +--------------------------------------------------------+                                |
|                                                                                           |
|  +-- gemini-8110 ------------- 14:25 -- [pin] [x] ------+                                |
|  | Test Coverage Report                                   |                                |
|  | +---------------------------------------------------+ |                                |
|  | |  [Chart.js bar chart]             (chart)         | |                                |
|  | |  auth: 92%  api: 75%  db: 98%                     | |                                |
|  | +---------------------------------------------------+ |                                |
|  +--------------------------------------------------------+                                |
|                                                                                           |
+-------------------------------------------------------------------------------------------+
```

### Agent Badge

Each card shows:
- Agent name (or ID if no name) with color indicator
- Agent type icon/color (claude=purple, gemini=blue, codex=green)
- Timestamp (relative: "2 min ago")
- Pin/delete controls
- Tags as small badges

### Features
- **Real-time**: SSE auto-updates, smooth card insert/update animations
- **Filter bar**: By format type, by agent, by tag
- **Dark/light theme**: `prefers-color-scheme` + manual toggle
- **Responsive**: Cards reflow on resize
- **Toast notifications**: `notify` type shows ephemeral messages

---

## File Structure

```
synapse/
  canvas/
    __init__.py              # Public API exports
    store.py                 # CanvasStore (SQLite, Card dataclass)
    server.py                # FastAPI app, SSE, endpoints
    protocol.py              # CanvasMessage dataclass, validation, format registry
    renderer.py              # Server-side format validation + metadata
    templates/
      index.html             # Main page (Jinja2)
    static/
      canvas.js              # SSE, card rendering, format dispatching
      canvas.css             # Card grid, badges, theme, animations
  commands/
    canvas.py                # CLI: serve, post, mermaid, table, ..., list, clear, delete

tests/
  test_canvas_store.py       # Store CRUD tests
  test_canvas_protocol.py    # Protocol validation tests
  test_canvas_server.py      # API endpoint tests
  test_canvas_cli.py         # CLI integration tests
```

---

## Protocol Details

### CanvasMessage Schema

```python
@dataclass
class ContentBlock:
    format: str                 # mermaid | markdown | html | table | json | diff | chart | image | code
    body: str | dict | list     # Content (string for most, dict for table/chart)
    lang: str | None = None     # Language hint for code format

@dataclass
class CanvasMessage:
    type: str                           # render | update | clear | notify
    content: ContentBlock | list[ContentBlock]  # Single or composite
    agent_id: str = ""                  # Auto-populated
    agent_name: str = ""                # Auto-populated
    title: str = ""
    card_id: str = ""                   # For upserts
    pinned: bool = False
    tags: list[str] = field(default_factory=list)
```

### Validation Rules

- `type` must be one of: `render`, `update`, `clear`, `notify`
- `content.format` must be a registered format (extensible registry)
- `content.body` max size: 500KB per block
- `card_id` if provided, must be unique per agent (allows cross-agent same IDs)
- Composite cards: max 10 content blocks per card

### Format Registry (Extensible)

```python
FORMAT_REGISTRY: dict[str, FormatSpec] = {
    "mermaid":  FormatSpec(body_type="string", cdn="mermaid/11.4.1/mermaid.min.js"),
    "markdown": FormatSpec(body_type="string", cdn="marked/15.0.0/marked.min.js"),
    "html":     FormatSpec(body_type="string", cdn=None, sandboxed=True),
    "table":    FormatSpec(body_type="object", cdn=None),  # {headers, rows}
    "json":     FormatSpec(body_type="any",    cdn=None),
    "diff":     FormatSpec(body_type="string", cdn="diff2html/3.4.48/diff2html.min.js"),
    "chart":    FormatSpec(body_type="object", cdn="chart.js/4.4.7/chart.umd.min.js"),
    "image":    FormatSpec(body_type="string", cdn=None),   # data URI or URL
    "code":     FormatSpec(body_type="string", cdn="highlight.js/11.11.1/highlight.min.js"),
}
```

Adding a new format = adding one entry to the registry + a JS render function. No protocol change.

---

## Dependency Changes

```toml
# pyproject.toml - ONE new dependency
dependencies = [
    # ... existing ...
    "jinja2>=3.1.0",
]
```

---

## Configuration

| Variable | Default | Description |
|---|---|---|
| `SYNAPSE_CANVAS_PORT` | `3000` | Canvas server port |
| `SYNAPSE_CANVAS_DB_PATH` | `.synapse/canvas.db` | Database path |
| `SYNAPSE_CANVAS_ENABLED` | `true` | Enable/disable |

```python
# config.py
CANVAS_DEFAULT_PORT: int = 3000
CANVAS_MAX_CONTENT_SIZE: int = 500_000      # 500KB per content block
CANVAS_MAX_BLOCKS_PER_CARD: int = 10        # Max sections in composite card
CANVAS_MAX_CARDS: int = 200                 # Auto-cleanup threshold
CANVAS_NOTIFICATION_TTL: int = 10           # Seconds for toast notifications
CANVAS_CARD_TTL: int = 3600                 # Card expiry: 1 hour (seconds)
```

---

## Implementation Phases

### Phase 1: Protocol + Store + Server + Mermaid

- [ ] `CanvasMessage` protocol dataclass + validation
- [ ] `CanvasStore` (SQLite CRUD with upsert)
- [ ] Canvas FastAPI server (HTML + POST/GET + SSE)
- [ ] `synapse canvas serve` command
- [ ] `synapse canvas post` command (raw JSON)
- [ ] `synapse canvas mermaid` shortcut
- [ ] `index.html` with card grid + Mermaid rendering + SSE
- [ ] Agent badge with name/type/timestamp
- [ ] Tests for protocol, store, and API

**Deliverable**: Agents post Mermaid diagrams via protocol, rendered live in browser.

### Phase 2: All Formats

- [ ] `markdown`, `table`, `json`, `code`, `diff`, `html` renderers
- [ ] Corresponding CLI shortcuts
- [ ] Composite cards (multi-block)
- [ ] `chart` format with Chart.js
- [ ] `image` format
- [ ] Filter bar in browser UI

### Phase 3: UX Polish

- [ ] Card pinning + tag filtering
- [ ] Toast notifications (`notify` type)
- [ ] Dark/light theme toggle
- [ ] Card animations (insert/update/delete)
- [ ] Auto-cleanup of old cards
- [ ] `--file` flag for all shortcuts

### Phase 4: Integration

- [ ] `/canvas/cards` proxy endpoint on agent A2A server
- [ ] Auto-start Canvas server on first `synapse canvas post`
- [ ] Agent instructions update (teach agents about Canvas)
- [ ] Skill update (add Canvas commands to synapse-a2a skill)

---

## Design Decisions (Resolved)

1. **Port**: Default 3000. Configurable via `SYNAPSE_CANVAS_PORT`.

2. **Persistence**: Cards are **ephemeral** — cleared on server restart. Additionally, cards expire after `CANVAS_CARD_TTL` (default 1 hour). Pinned cards are exempt from TTL expiry. Rationale: Canvas is a live working surface, not an archive. Stale cards clutter the view.

3. **HTML sandboxing**: `html` format renders in sandboxed `<iframe>` (no access to parent page). Sufficient for localhost-only use.

4. **CDN vs vendored**: CDN for Phase 1. `--offline` flag for vendored assets in future.

5. **Card ownership**: Agents can only update/delete their own cards (matched by `agent_id`). `synapse canvas clear` without filter clears all (admin operation from CLI).

---

## Related Technology Assessment

A2UI (Google) と MCP Apps (Anthropic/MCP) を Canvas の設計に活かせるか検討した。
Generative UI 全体の技術動向は [generative-ui-landscape.md](./generative-ui-landscape.md) を参照。

### A2UI (Agent-to-User Interface)

- **概要**: Google 発の宣言的 UI プロトコル (v0.8-0.9, Public Preview)。エージェントが JSON でコンポーネント（Button, Text, Chart 等）を宣言し、クライアントがネイティブウィジェットにマッピングして描画する。
- **特徴**: コンポーネントカタログ方式、adjacency list model（フラットなコンポーネント定義）、A2A プロトコルの Extension として `DataPart` に `application/json+a2ui` で埋め込み可能。
- **判断: 見送り**
  - Synapse のエージェントは CLI ツール（Claude Code, Codex 等）。adjacency list model で UI を組み立てるのはエージェントにとって複雑すぎる。
  - Canvas の目的は「図や表をブラウザに出す」であって「対話的 UI を構築する」ではない。
  - A2UI が想定する「LLM が直接 JSON UI を生成する」ユースケースと、CLI コマンドで投稿する Synapse のモデルが合わない。
- **将来の再検討ポイント**: A2A プロトコルに A2UI Extension が標準化され、Synapse の A2A 通信結果を自動的に Canvas に表示したくなった時。
- **参考**:
  - https://a2ui.org/
  - https://a2ui.org/specification/v0.8-a2ui/
  - https://a2ui.org/specification/v0.8-a2a-extension/
  - https://github.com/google/A2UI

### MCP Apps

- **概要**: MCP の official extension (v1.1)。MCP サーバーが HTML バンドルを `ui://` リソースとして提供し、MCP クライアント（Claude Desktop 等）が sandboxed iframe で会話内に描画する。
- **特徴**: HTML/CSS/JS で表現力無制限、postMessage による双方向通信（UI からツール呼び出し可能）、`_meta.ui.resourceUri` でツールと UI を紐付け。
- **判断: 見送り**
  - MCP クライアントの会話内に UI を埋め込む仕組み。Synapse のエージェントは MCP クライアントではなく PTY で動いている。
  - postMessage 双方向通信も今は不要（Canvas は表示専用）。
  - npm / ビルドステップが前提の設計で、Synapse の Python-only 方針と合わない。
- **採用した部分**: `html` format を sandboxed iframe で描画するアプローチは MCP Apps と同じ考え方。セキュリティモデルとして参考にした。
- **将来の再検討ポイント**: Canvas カードにインタラクション（ボタン押下でエージェントにアクション送信等）を追加する時、MCP Apps の双方向通信パターンが参考になる。
- **参考**:
  - https://modelcontextprotocol.io/extensions/apps/overview
  - http://blog.modelcontextprotocol.io/posts/2026-01-26-mcp-apps/
  - https://github.com/modelcontextprotocol/ext-apps

### 比較まとめ

| | A2UI | MCP Apps | Synapse Canvas |
|---|---|---|---|
| アプローチ | 宣言的 JSON コンポーネント | HTML バンドル (iframe) | format + body JSON + iframe |
| 表現力 | カタログ内に制限 | 無制限 (HTML/CSS/JS) | format 指定 + html 脱出ハッチ |
| エージェント側の複雑さ | 高 (adjacency list) | 中 (HTML 生成) | **低 (CLI 1コマンド)** |
| セキュリティ | コード実行なし | sandboxed iframe | sandboxed iframe |
| 依存 | A2A + クライアント実装 | MCP + npm | **Python のみ (jinja2)** |
| 双方向通信 | userAction | postMessage | なし (表示専用) |
| 対象 | LLM ネイティブ UI 構築 | MCP クライアント内 UI | **CLI エージェントの描画出力** |

### 結論

今やりたいことは「エージェントが `synapse canvas mermaid "..."` の1コマンドでブラウザに図を出せる」こと。A2UI も MCP Apps もそのユースケースに対してオーバースペック。現在の Canvas Message Protocol 設計で十分。将来、A2A に A2UI が標準統合された時点、またはカードに双方向インタラクションが必要になった時点で再検討する。
