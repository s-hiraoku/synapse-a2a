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
| `mermaid` | Mermaid source string | mermaid.js | Flowcharts, sequence diagrams, ER diagrams, Gantt |
| `markdown` | Markdown text | Built-in `simpleMarkdown` parser | Design docs, explanations, formatted text (tables, blockquotes, ordered/unordered lists, headings, code blocks, horizontal rules, inline formatting) |
| `html` | Raw HTML string | Sandboxed iframe | Full freedom — any visual expression |
| `table` | `{headers: [...], rows: [[...]]}` | Native HTML | Structured data, test results, comparisons |
| `json` | Any JSON | Collapsible tree viewer | API responses, config, data structures |
| `diff` | Unified diff | Side-by-side diff renderer | Code changes, before/after |
| `chart` | Chart.js config object | Chart.js | bar, line, pie, doughnut, radar, polarArea, scatter, bubble |
| `image` | Base64 data URI or URL | `<img>` | Screenshots, SVG diagrams, generated images |
| `code` | Source code string + `lang` | highlight.js | Syntax-highlighted code blocks |
| `log` | `[{level, ts, msg}]` | Agent logs | Agent logs with INFO/WARN/ERROR color coding |
| `status` | `{state, label, detail}` | Status badge | Build/task status with colored badge |
| `metric` | `{value, unit, label}` | Single KPI | Single KPI display (large number) |
| `checklist` | `[{text, checked}]` | Checklist | Task progress with checkboxes |
| `timeline` | `[{ts, event, agent}]` | Timeline | Time-series events, task progression |
| `alert` | `{severity, message, source}` | Alert notification | Persistent important notifications |
| `file-preview` | `{path, lang, snippet, start_line}` | Code preview | Code snippet with file path and line numbers |
| `trace` | `[{name, duration_ms, status, children?}]` | A2A trace | A2A routing spans with duration bars |
| `progress` | `{current, total, label, steps, status}` | Progress bar + steps | Task/build progress tracking |
| `terminal` | Raw string (ANSI escapes) | Terminal emulator | Command output with color support |
| `dependency-graph` | `{nodes: [{id, group}], edges: [{from, to}]}` | Mermaid graph | Dependency visualization |
| `cost` | `{agents: [{name, input_tokens, output_tokens, cost}], total_cost, currency}` | Cost table | Token/cost aggregation |
| `tip` | String | Styled tip card | System tips and suggestions |
| `link-preview` | `{url}` (enriched with `og_title`, `og_description`, `og_image`, `og_site_name`, `og_type`, `favicon`, `domain`, `fetched`) | Embed card | OGP link previews with title, description, image |

**Link-preview OGP fetch details**:
- **URL validation**: Only `http` and `https` URLs are accepted; the CLI command exits with a non-zero status on invalid input.
- **SSRF protection**: HTTP redirects are followed manually with each redirect target validated against the same allowlist, preventing open-redirect SSRF attacks.
- **Streaming read with size cap**: HTML is read via `aiter_bytes()` with a 64 KB ceiling, avoiding unbounded memory consumption on large pages.
- **Parallel fetch**: When a card contains multiple `link-preview` blocks, OGP metadata is fetched concurrently via `asyncio.gather`.

**Block-level metadata**: Any content block can carry optional `x_title` and `x_filename` fields. Renderers (mermaid, json, code, log, checklist, trace, tip) use `buildMetaRow()` to display this metadata above the rendered content. This replaces the earlier body-embedded metadata pattern (`{source, title?, filename?}`) and `parseBodyWithKey()` helper, which have been removed.

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

When `--no-open` is **not** set, the CLI schedules browser auto-open via `_open_canvas_browser()` on a 1-second `threading.Timer`, giving the server time to bind the port before launching the browser.

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
- PID ファイル (`~/.synapse/canvas.pid`) で多重起動を防止（絶対パス — CWD に依存しない）
- `synapse canvas serve` 実行時も PID ファイルをチェックし、既に起動中ならポートを表示して終了
- `ensure_server_running()` は stale プロセスを自動検出・置換（PID 不一致、プロセス消失、asset_hash 不一致を検知）
- `synapse canvas stop` は `/api/health` エンドポイントでサービス識別（`"service": "synapse-canvas"`）を確認し、プロセス identity を検証してから停止。SIGTERM で停止しない場合は SIGKILL にエスカレート。ポート解放も確認。PID ファイルにフォールバック

**Health endpoint**:
```
GET /api/health → 200 {"service": "synapse-canvas", "status": "ok", "pid": 12345, "cards": 5, "version": "0.1.0", "asset_hash": "a1b2c3d4e5f6"}
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
synapse canvas link "https://example.com/article" --title "Reference"
synapse canvas briefing '{"sections":[...],"content":[...]}' --title "Report"
synapse canvas briefing --file report.json --title "CI Report"
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
| Canvas view | `#/` — full-viewport latest card |
| History view | `#/history` — system panel + live feed + agent messages |
| Filter | By format type and by agent (History view only) |
| Theme toggle | Dark/light switch (Mermaid diagrams re-render with theme-matched palettes) |

### HTTP API (programmatic)

```
POST   /api/cards          Create/update card (Canvas Message Protocol)
GET    /api/cards           List cards (JSON, optional ?agent_id=&search=&type= filters)
GET    /api/cards/{card_id}      Get single card
DELETE /api/cards/{card_id}      Delete card (own cards only, matched by agent_id)
DELETE /api/cards           Clear all cards (optional ?agent_id= filter)
GET    /api/cards/{card_id}/download  Download card as file (?format=md|json|csv|html|native|txt)
GET    /api/stream          SSE stream (card_created, card_updated, card_deleted events)
GET    /api/formats         List supported formats (format registry)
GET    /api/system          System state summary (Agents, User/Active-Project Saved Agents, Tasks, File Locks, Shared Memory, Worktrees, Recent History)
```

#### `/api/cards/{card_id}/download` — Card Download

カードをファイルとしてエクスポートする。`?format=` クエリパラメータで出力形式を指定可能（省略時はフォーマットに応じた最適形式）。

**対応フォーマット**: `md`, `json`, `csv`, `html`, `native`, `txt`

全 26 コンテンツフォーマットは `FORMAT_DOWNLOAD_MAP`（`synapse/canvas/export.py`）で 4 グループに分類される:

| グループ | フォーマット | デフォルト出力 |
|---------|------------|---------------|
| Markdown (A) | markdown, checklist, tip, alert, status, metric, progress, timeline, link-preview | `.md` |
| Native (B) | code, html, artifact, diff, mermaid, terminal, image | 元形式（言語別拡張子, `.html`, `.diff`, `.mmd`, `.txt`, `.png`） |
| JSON (C) | json, chart, dependency-graph, trace, log, file-preview, plan | `.json` |
| CSV (D) | table, cost | `.csv` |

テンプレートカード（briefing, comparison, dashboard, steps, slides, plan）はデフォルトで Markdown にエクスポートされる。`?format=json` で生カードデータを JSON 出力可能。

**UI**: カードグリッドヘッダーと Spotlight タイトルバーにダウンロードボタンを配置。

**実装**: `synapse/canvas/export.py` — `export_card()` 関数がカード辞書を受け取り `(content_bytes, filename, content_type)` を返す。

#### `/api/system` Response Details
The `/api/system` endpoint aggregates state from across the project:
- `agents`: List of active agents. Added fields: `pid`, `role`, `skill_set`, `working_dir`, `endpoint`, `current_task_preview`, `task_received_at`.
- `user_agent_profiles`: User-scope saved agent definitions from `~/.synapse/agents/`. Fields: `id`, `name`, `profile`, `role`, `skill_set`, `scope`.
- `active_project_agent_profiles`: Saved agent definitions from active projects only, derived from running agents' `working_dir` values and normalized so worktrees resolve to the base repo. Fields: `id`, `name`, `profile`, `role`, `skill_set`, `scope`.
- `skills`: Discovered skills from project, user, synapse central store, and plugin scopes. Each entry includes `name`, `description`, `scope` (`user` / `project` / `synapse` / `plugin`), `agent_dirs` (target agent directory slugs), `path` (absolute skill directory), `source_file` (backing `SKILL.md`), and `project_root` (anchor used for grouping). Consumed by the Skills viewer (`#/harnesses/skills`).
- `mcp_servers`: MCP server entries scanned from every supported agent harness.
  - **Project scope** — `<project>/.mcp.json` (Claude Code, shared).
  - **User scope (per agent)** — `~/.claude.json` (Claude Code), `~/.codex/config.toml` (Codex, TOML), `~/.gemini/settings.json` (Gemini), `~/.config/opencode/opencode.json` (OpenCode; `command` may be an argv array which the server flattens into `command` + `args`), and `~/Library/Application Support/Claude/claude_desktop_config.json` (Claude Desktop).
  - Each entry includes `name`, `scope` (`project` / `claude` / `codex` / `gemini` / `opencode` / `claude_desktop`), `type` (default `stdio`), `command`, `args`, `cwd`, `env_keys` (keys only — values are never exposed), `url`, `source_file`, and `project_root` (for `project` scope: the active project root; for user-scope: the agent label).
  - Consumed by the MCP Servers viewer (`#/harnesses/mcp`).
- `project_roots`: Every active project root Canvas scanned (cwd + unique `working_dir` values from live agent registry entries, worktree-aware). The MCP viewer uses this to render an empty "no `.mcp.json`" row for projects that exist but have no MCP config — so the user can tell "not configured" from "not seen".
- `file_locks`: Active file locks.
- `memories`: Latest 20 shared memory entries.
- `worktrees`: Active worktrees from the registry.
- `history`: Latest 20 events from the history database.

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
                 /api/cards    |    /api/system
                         |    |    |
                         v    v    v
                       canvas.db  registry/ & .synapse/*.db
                       (cards)    (system state)

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

### Cache-Busting Strategy

To ensure browsers always load the latest static assets during development and after server updates, Canvas uses a three-layer cache-busting strategy:

1. **Query string versioning**: CSS and JS references in `index.html` are rewritten with `?v=<timestamp>` on each server start (e.g., `/static/canvas.css?v=1709900000`). The `_cache_version` is generated once at startup via `int(time.time())`.
2. **`Cache-Control: no-store` on HTML**: The main `index.html` response includes `Cache-Control: no-store` to prevent browsers from caching the page itself. This guarantees the `?v=` versioned asset URLs are always fetched.
3. **`NoCacheStaticMiddleware`**: A custom `BaseHTTPMiddleware` adds `Cache-Control: no-cache` to all `/static/` responses, forcing browsers to revalidate on every request.

### Mermaid SVG Sizing

Mermaid.js sets fixed `height` attributes on generated SVGs, which can cause clipping or oversized whitespace. The `runMermaid()` helper in `canvas.js` fixes this after rendering:

- Removes the `height` attribute from all `.format-mermaid svg` elements
- Sets `display: block` via CSS so SVGs flow naturally within their container
- Preserves Mermaid's inline `max-width` style to respect diagram complexity

### Mermaid Theme Sync

Mermaid diagrams automatically synchronize with the Canvas dark/light theme toggle:

- **`MERMAID_THEMES`** config defines custom palettes for each theme: a GitHub Dark-inspired dark palette (`#0d1117` base) and an Indigo-accented light palette, both using the brand color `#4051b5`.
- **`initMermaidTheme(theme)`** initializes Mermaid with the active Canvas theme, applying the corresponding palette from `MERMAID_THEMES`.
- **`reRenderMermaid()`** rebuilds all Mermaid diagrams from their stored source (preserved in `data-mermaid-source` attributes) when the theme changes, ensuring colors update without a page reload.
- The theme toggle click handler calls `initMermaidTheme(next)` + `reRenderMermaid()` so diagrams reflect the new theme immediately.

### Markdown Rendering

Markdown cards are rendered client-side by a built-in `simpleMarkdown()` line-based state machine (no external library). An `inlineMarkdown()` helper handles inline formatting within each line.

**Supported elements**:
- Headings (`#`, `##`, `###`)
- Fenced code blocks (``` with language hint)
- Tables (`|` syntax with column alignment via `:---`, `:---:`, `---:`)
- Blockquotes (`>` lines, rendered with accent stripe)
- Ordered lists (`1. 2.`), unordered lists (`- *`), and nested lists (indent-aware)
- Horizontal rules (`---`)
- Paragraph wrapping (`<p>`)
- Inline: bold, italic, inline code, links, strikethrough (`~~`)

**Typography**: Markdown card content uses Source Sans 3 (body) and Source Code Pro (code), loaded via Google Fonts alongside the UI fonts (Inter, JetBrains Mono). The UI itself continues to use Inter.

**CSS highlights**: Heading hierarchy with `border-bottom` on `h2`, blockquote with accent left stripe, table styling with uppercase headers and hover rows, `del`/strikethrough support, proper `<p>` margins.

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
    template    TEXT DEFAULT '',                   -- Template name: briefing | comparison | dashboard | steps | slides
    template_data TEXT DEFAULT '{}',              -- JSON: template-specific layout metadata
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

event: system_update
data: {"timestamp": "..."} // Triggers /api/system refetch
```

#### SSE Reconnection

When the SSE connection drops (e.g., server restart, network interruption), `EventSource` auto-reconnects. A `_sseHasConnected` guard ensures that `es.onopen` only triggers `loadCards()` on **re**-connections, not on the initial connect (which already loads cards during page init). This prevents a redundant double-load on first page open while still ensuring the browser UI never shows stale data after a reconnection.

#### SSE + Fallback Polling

Real-time updates are delivered via SSE events. The `system_update` event triggers a `/api/system` refetch in the Dashboard view. Additionally, the Dashboard uses a 10-second `setInterval` fallback poll to ensure widgets stay current even if SSE events are missed or delayed. Both SSE-triggered and poll-triggered updates use `updateDashWidget()` for in-place DOM updates that preserve widget expand/collapse state.

#### Toast Batching

Toast notifications are batched within a 300ms window (`TOAST_BATCH_MS`) to prevent burst flooding when multiple cards arrive in quick succession. `showToast()` enqueues messages and resets the batch timer; `_flushToasts()` fires after the window closes. A single-message batch shows the card title and agent label. A multi-message batch shows a summary count (e.g., "3 cards updated").

### Mermaid Panel Wrapper

When a mermaid block carries `x_title` or `x_filename` metadata, the renderer wraps the `<pre class="mermaid">` element inside a `<div class="mermaid-panel">` container. The metadata row (built by `buildMetaRow("mermaid", block)`) is placed above the diagram inside this panel. The same `buildMetaRow()` pattern is used by json, code, log, checklist, trace, and tip renderers with their own CSS class prefixes.

### SPA Routing

The browser UI uses hash-based SPA routing with the following views:

| Route | View | Icon | Description |
|---|---|---|---|
| `#/` | **Canvas view** | `ph-projector-screen` | Full-viewport projection of the latest card. Designed for immersive content display. |
| `#/dashboard` | **Dashboard view** | `ph-squares-four` | Operational status overview: agents, tasks, file locks, worktrees, shared memory, and registry errors. Each widget uses a summary+detail expand/collapse pattern. |
| `#/history` | **History view** | `ph-clock-counter-clockwise` | Live Feed + Agent Messages. The traditional card overview. |
| `#/admin` | **Agent Control** | `ph-crown` | Interactive agent management: send messages, inspect responses, and control the fleet. |
| `#/harnesses` | **Harnesses landing** | `ph-toolbox` | Parent page for agent harness resources. Links into sub-views (currently: Skills, MCP Servers). |
| `#/harnesses/skills` | **Skills viewer** | `ph-puzzle-piece` | Tree-table of discovered skills grouped by scope (User Global, Project, Synapse Central Store, Plugin) with project-root inference. Columns: NAME / DESCRIPTION / LOCATION. The LOCATION cell is two rows — targets (`agent_dirs`) as small badges on top, absolute skill directory path below. Incremental name filter hides empty groups; parent rows are collapsible (click or Enter/Space). Nested under the **Harnesses** sidebar parent. |
| `#/harnesses/mcp` | **MCP Servers viewer** | `ph-plugs-connected` | Tree-table of MCP servers configured in project `.mcp.json` plus every supported user-scope agent config — Claude Code (`~/.claude.json`), Codex (`~/.codex/config.toml`, TOML), Gemini (`~/.gemini/settings.json`), OpenCode (`~/.config/opencode/opencode.json`), and Claude Desktop (`~/Library/Application Support/Claude/claude_desktop_config.json`). Grouped into **User Global** (per-agent sub-groups) and **Projects** (per-project sub-groups; projects with no `.mcp.json` render as a dashed-folder "no `.mcp.json`" row). Shows the resolved command line (`command` + `args`), `cwd`, `type`, and the sorted list of `env` keys (values are never sent to the browser). Same incremental filter + collapsible parent rows as the Skills viewer. Nested under the **Harnesses** sidebar parent. |
| `#/system` | **System view** | `ph-gear` | Configuration panel: tips, user-scope saved agents, active-project saved agents, skills, skill sets, sessions, workflows, and environment. |

Navigation uses a sidebar (fixed on desktop, hamburger drawer on mobile) with Phosphor Icons. History is a sub-item under Canvas in the sidebar (indented with `nav-sub` class); when the History route is active, the Canvas parent link also shows as active and the topbar displays "Canvas / History". The URL hash updates accordingly and the browser back/forward buttons work as expected.

### Canvas View (`#/`)

The Canvas view displays the most recent card in a full-viewport layout. Key behaviors:

- **Full viewport**: The latest card fills the entire content area below the sidebar.
- **HTML iframe**: When the latest card is `html` format, the iframe expands to fill the Canvas view content area (no fixed `minHeight`). In History view, iframes auto-resize to their content height.
- **Code highlighting**: `code` format cards use highlight.js for syntax highlighting.
- **Auto-update**: When a new card arrives via SSE, the spotlight automatically switches to it.

Format and agent filters are hidden in Canvas view (they apply only to History view).

### History View (`#/history`)

The History view is divided into three sections: the **System Panel** (top), **Live Feed** (middle), and **Agent Messages** (bottom). Navigation is via a sidebar (fixed on desktop, hamburger drawer on mobile) using Phosphor Icons v2.

```
+--[Synapse Canvas]--[Canvas | History]--[Filter: All | mermaid | ...]--[Agents: All | ...]--+
|                                                                                               |
|  [System Panel (Control Panel)]                                                               |
|  +-----------------------------------------------------------------------------------------+  |
|  | [Agents] [User Scope Saved Agents] [Active-Project Saved Agents] [Tasks] [File Locks] [Shared Memory] [Worktrees] [History]      |  |
|  +-----------------------------------------------------------------------------------------+  |
|                                                                                               |
|  [Live Feed]                                                                                  |
|  +-----------------------------------------------------------------------------------------+  |
|  | 14:23  Gojo posted "System Design"                                                      |  |
|  | 14:21  DocWriter posted "Test Results"                                                   |  |
|  +-----------------------------------------------------------------------------------------+  |
|                                                                                               |
|  [Agent Messages]                                                                             |
|                                                                                               |
|  +-- v [●] DocWriter (synapse-gemini-8110) ----------------------------- [2 cards] ------+    |
|  |                                                                                        |   |
|  |  +-- System Design (auth-flow) ----------------------------------------- 14:23 --+  |   |
|  |  | +-----------------------------------------------------------------------------+ |  |   |
|  |  | | ## Architecture Overview          (markdown)                                | |  |   |
|  |  | | ...                                                                         | |  |   |
|  |  | +-----------------------------------------------------------------------------+ |  |   |
|  |  +--------------------------------------------------------------------------------+  |   |
|  |                                                                                        |   |
|  +----------------------------------------------------------------------------------------+   |
|                                                                                               |
|  +-- > [●] Gojo (synapse-claude-8103) ---------------------------------- [0 cards] ------+    |
|  +----------------------------------------------------------------------------------------+   |
|                                                                                               |
+-----------------------------------------------------------------------------------------------+
```

### Agent Messages
Cards are grouped into panels per agent, sorted by the latest activity.
- **Panel Header**: Displays agent name, status dot, `agent_id`, card count, and a folding toggle.
- **Empty State**: Agents without cards are shown as empty panels to provide a complete view of the team.
- **Persistence**: Panel collapse state is saved in `localStorage`.

### Dashboard View (`#/dashboard`)

The Dashboard view provides an operational status overview, updated in real-time via SSE with a 10-second fallback polling interval. READY/PROCESSING/WAITING/DONE status counters update in-place rather than rebuilding the full DOM, so values refresh without triggering entry animations. Each widget uses a two-tier **summary+detail** display pattern built with the `createDashWidget()` helper:

- **Summary** (always visible): A compact overview rendered in the widget header area (e.g., status strip for agents, bar chart for tasks, counts for others).
- **Detail** (expandable): Full content revealed by clicking the widget header. Expand/collapse state is persisted across both SSE and polling re-renders via `_dashExpandState`.

On subsequent updates (SSE or polling), the `updateDashWidget()` helper performs in-place DOM updates on existing widgets rather than destroying and rebuilding them via `innerHTML`. This preserves the user's expand/collapse state across the 10-second polling cycle. `updateDashWidget()` updates the title text, replaces the summary element, and rebuilds the detail content only if the detail panel is currently expanded. If no existing widget element is found, it falls through to `createDashWidget()` for initial creation.

Widget IDs:

| Widget ID | Summary | Detail |
|---|---|---|
| `dash-agents` | Status strip (agent counts by status) | Active agents table (status dot, TYPE, NAME, ROLE, STATUS, PORT, DIR, CURRENT) |
| `dash-tasks` | Bar chart of task counts by status | Kanban view of `pending`, `in_progress`, `completed`, and `failed` tasks |
| `dash-file-locks` | Lock count | Active file locks (FILE, AGENT) |
| `dash-worktrees` | Worktree count | Active worktrees (AGENT, PATH, BRANCH, BASE) |
| `dash-memory` | Memory entry count | Latest shared memory entries (KEY, AUTHOR, TAGS, UPDATED) |
| `dash-errors` | Error count | Registry errors and warnings |

**Removed widgets** (previously present):
- `dash-status-strip` — top-level summary strip; replaced by per-widget summaries (the agent status strip is now embedded in the `dash-agents` widget summary via `buildStatusStrip()`).
- `dash-attention` — attention alerts widget.
- `dash-activity` — recent activity feed widget.

### System View (`#/system`)

The System view shows configuration and environment information (no operational data):

1. **Tips**: Contextual usage tips.
2. **User Scope Saved Agents**: Displays ID, NAME, PROFILE, ROLE, SKILL SET, and SCOPE for configurations in `~/.synapse/agents/`.
3. **Active-Project Saved Agents**: Displays saved agent definitions from projects that currently have running agents. Worktree agents are attributed to their base repository.
4. **Skills**: Discovered skills from all scopes.
5. **Skill Sets**: Defined skill set configurations.
6. **Sessions**: Saved session configurations.
7. **Workflows**: Saved workflow definitions.
8. **Environment**: Environment variables and runtime configuration.

### Harnesses / Skills Viewer (`#/harnesses/skills`)

The Skills view is a dedicated browsing surface for the skills that back agent harnesses. It complements the flat "Skills" block in the System view with a richer tree-table that makes location and ownership obvious.

- **Sidebar placement**: top-level `Harnesses` entry (`ph-toolbox`) with `Skills` (`ph-puzzle-piece`) as a `nav-sub` child. `#/harnesses` is the landing page; `#/harnesses/skills` renders the viewer. Activating the child also lights the parent link and sets the topbar breadcrumb to `Harnesses / Skills`.
- **Data source**: `/api/system` response. Each skill entry carries `name`, `description`, `scope`, `agent_dirs` (target agent directory slugs), `path` (absolute skill directory), `source_file` (absolute path to the backing `SKILL.md`), and `project_root` (inferred anchor used for grouping). The server-side payload was extended to include `path`, `source_file`, and `project_root` specifically for this viewer.
- **Two-level hierarchy** (大分類 → 中分類 → スキル):
  1. **Top-level sections** render as separate tables: **User Global** (上), **Projects**, **Synapse Central Store**.
  2. **User Global** subdivides by agent harness via `agent_dirs`: **Claude Code** (`.claude/skills/**`) and **Codex / OpenCode / Gemini / Copilot** (shared `.agents/skills/**`). Each agent bucket is a collapsible group.
  3. **Projects** subdivides by inferred project root (directory basename + absolute path as sub-title). Within each project, skills further sub-group by agent bucket (`.claude` / `.agents`) when both apply; single-bucket projects skip the inner header for density.
  4. Project roots come from active agents' `working_dir` values (worktree-aware) plus Canvas's own cwd.
- **Columns**: `NAME`, `DESCRIPTION`, `LOCATION`. `LOCATION` is a two-row cell — the top row shows `agent_dirs` targets as small badges (`.claude`, `.agents`, `plugins/<name>`), and the bottom row shows the absolute directory path rendered as monospace text.
- **Collapsible parent rows**: every group header is a keyboard-accessible toggle (`click`, `Enter`, or `Space`) that hides/shows its children. Initial state is expanded.
- **Incremental filter**: a name-filter textbox performs substring matching on skill names. Groups with no visible children are hidden entirely so the tree stays compact while you search.
- **YAML parsing**: skill descriptions come from `parse_skill_frontmatter()` in `synapse/skills.py`. The parser now delegates to PyYAML (`yaml.safe_load`), so full YAML frontmatter is supported — including block scalars (`>`, `>-`, `>+`, `|`, `|-`, `|+`) and their continuation lines. Long descriptions no longer truncate to the literal `>-` token.
- **Asset caching**: Canvas caches HTML/JS at startup, so after upgrading or hot-editing viewer assets, run `synapse canvas restart` to reload. `synapse canvas status` reports `STALE` when the running server's asset hash no longer matches the on-disk hash.

### Harnesses / MCP Servers Viewer (`#/harnesses/mcp`)

Sibling to the Skills viewer, the MCP Servers view lists every Model Context Protocol server configured for the current project or for any supported agent harness.

- **Sidebar placement**: sibling `nav-sub` under `Harnesses` (`ph-plugs-connected`). Activating it also lights the `Harnesses` parent link and sets the breadcrumb to `Harnesses / MCP Servers`.
- **Data source**: `mcp_servers` + `project_roots` fields on `/api/system`. The server collects entries from every supported agent harness via `_collect_mcp_servers()` in `synapse/canvas/server.py`:
  - **Project scope** — `<project>/.mcp.json` (JSON, `mcpServers` key). Scanned for every active project root.
  - **Claude Code** — `~/.claude.json` (JSON, `mcpServers` key).
  - **Codex** — `~/.codex/config.toml` (**TOML**, `[mcp_servers.<name>]` tables).
  - **Gemini** — `~/.gemini/settings.json` (JSON, `mcpServers` key).
  - **OpenCode** — `~/.config/opencode/opencode.json` (JSON, `mcp` key; entries' `command` may be an argv list which the server flattens to `command` + `args`).
  - **Claude Desktop** — `~/Library/Application Support/Claude/claude_desktop_config.json` (JSON, `mcpServers` key; macOS path).
- **Payload shape**: `name`, `scope` (`project` / `claude` / `codex` / `gemini` / `opencode` / `claude_desktop`), `type` (default `stdio`), `command`, `args`, `cwd`, `url`, `env_keys` (sorted list of keys — values are intentionally withheld so secrets never leave the process), `source_file`, `project_root`.
- **Two-level hierarchy** (大分類 → 中分類 → サーバ):
  1. **User Global** (大分類, 上) groups servers by agent harness as a subsection each — Claude Code, Codex, Gemini, OpenCode, Claude Desktop — so "どのエージェントに登録された MCP か" が一目で分かります。
  2. **Projects** (大分類, 下) groups by project root. Every active project root from `/api/system.project_roots` is rendered, even when it has no `.mcp.json` — those projects appear as a single dashed-folder row with a `no .mcp.json` badge so "not configured" is distinguished from "not seen".
- **Columns**: NAME / COMMAND / DETAILS. `COMMAND` renders the resolved `command args…` in monospace. `DETAILS` is a two-row cell — the top row is a chip list starting with the transport `type` (default `stdio`) followed by `env:KEY` chips for each declared environment variable (**keys only, values are never rendered**), and the bottom row shows the backing `source_file` path. Same collapsible parent rows and incremental name filter as the Skills viewer.

### CSS Design System
The UI adheres to a strict design system for consistency and accessibility:
- **Glassmorphism**: Glass panels with `backdrop-filter: blur` for depth and visual hierarchy.
- **Brand color**: Unified to MkDocs Material indigo `#4051b5`, managed centrally via `palette.css`.
- **Sidebar navigation**: Fixed sidebar on desktop with SVG synapse brand icon; hamburger drawer on mobile.
- **Icons**: Phosphor Icons v2 used throughout the UI.
- **Spacing**: 4px base scale using variables `--sp-1` (4px) through `--sp-8` (32px).
- **Colors**: Semantic tokens including `--color-bg`, `--color-bg-raised`, `--color-bg-inset`, and `--color-accent-subtle`.
- **Fonts**: Inter for UI display/headings; Source Sans 3 for markdown card body text; Source Code Pro / JetBrains Mono for code. Loaded via Google Fonts.
- **Motion/Interaction**: Full support for `prefers-reduced-motion` and `focus-visible` states. Card entry animations (e.g., `scaleIn`) use an `.is-new` CSS modifier class so they only play on first render; subsequent SSE/polling updates skip the animation to prevent visual replay.

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
      canvas.js              # SSE, card rendering, format dispatching, SPA routing
      canvas.css             # Card grid, badges, theme, animations, Canvas/History views
      palette.css            # Centralized color management (brand color #4051b5)
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
    format: str                 # mermaid | markdown | html | table | json | diff | chart | image | code | progress | terminal | dependency-graph | cost | ...
    body: str | dict | list     # Content (string for most, dict for table/chart/progress/cost)
    lang: str | None = None     # Language hint for code format
    x_title: str | None = None      # Block-level title (shown by buildMetaRow in renderers)
    x_filename: str | None = None   # Block-level filename (shown by buildMetaRow in renderers)

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
    template: str = ""                  # Template name (briefing | comparison | dashboard | steps | slides | plan)
    template_data: dict = field(default_factory=dict)  # Template-specific layout metadata
```

### Validation Rules

- `type` must be one of: `render`, `update`, `clear`, `notify`
- `content.format` must be a registered format (extensible registry)
- `content.body` max size: 2MB per block
- `card_id` must be globally unique (schema: `card_id TEXT UNIQUE`). If a different agent reuses an existing `card_id`, the server returns 403
- Composite cards: max 30 content blocks per card
- `template` must be one of: `briefing`, `comparison`, `dashboard`, `steps`, `slides`, `plan` (or empty for no template)
- Template cards require composite content (list of blocks); `template_data` defines how blocks are grouped

### Templates

Templates add structured layout semantics on top of composite cards. The `template` field selects the layout, and `template_data` provides template-specific metadata that maps content blocks (by index) into sections, sides, widgets, steps, or slides.

| Template | Purpose | Limits |
|---|---|---|
| `briefing` | Structured report with collapsible sections | MAX_SECTIONS = 20 |
| `comparison` | 2–N-way side-by-side or stacked comparison | MAX_SIDES = 4 |
| `dashboard` | Flexible grid of widgets with size hints | MAX_WIDGETS = 20, cols 1–4 |
| `steps` | Linear workflow with completion tracking | MAX_STEPS = 30 |
| `slides` | Page-by-page slide navigation | MAX_SLIDES = 30 |
| `plan` | Task plan with Mermaid DAG + step list and status tracking | MAX_STEPS = 30 |

#### Template Schemas

**briefing**:
```jsonc
{
  "summary": "Executive summary (optional)",
  "sections": [
    {
      "title": "Section Title",        // required
      "blocks": [0, 1],               // indices into content[] (optional)
      "summary": "Section summary",   // optional
      "collapsed": false              // optional, default false
    }
  ]
}
```

**comparison**:
```jsonc
{
  "summary": "Comparison overview (optional)",
  "sides": [
    {"label": "Option A", "blocks": [0, 1]},  // label required, blocks required
    {"label": "Option B", "blocks": [2, 3]}
  ],
  "layout": "side-by-side"  // optional: "side-by-side" (default) | "stacked"
}
```

**dashboard**:
```jsonc
{
  "cols": 2,  // optional: 1–4 (default 2)
  "widgets": [
    {
      "title": "Widget Title",  // required
      "blocks": [0],           // indices into content[]
      "size": "1x1"            // optional: "1x1" | "2x1" | "1x2" | "2x2"
    }
  ]
}
```

**steps**:
```jsonc
{
  "summary": "Workflow overview (optional)",
  "steps": [
    {
      "title": "Step Title",        // required
      "blocks": [0],               // indices into content[] (optional)
      "done": true,                // optional, default false
      "description": "Details"     // optional
    }
  ]
}
```

**slides**:
```jsonc
{
  "slides": [
    {
      "title": "Slide Title",  // optional
      "blocks": [0, 1],       // indices into content[] (required)
      "notes": "Speaker notes" // optional
    }
  ]
}
```

#### CLI: `synapse canvas briefing`

```bash
# Post briefing from inline JSON
synapse canvas briefing '{"title":"Sprint Report","sections":[{"title":"Overview","blocks":[0]}],"content":[{"format":"markdown","body":"## Summary\n..."}]}' --pinned

# Post briefing from file
synapse canvas briefing --file report.json --title "CI Report"

# Options
--title "Override title"       # Override title from JSON data
--summary "Executive summary"  # Add/override summary
--card-id my-report            # Stable ID for upsert
--pinned                       # Pin to top
--tags "sprint,weekly"         # Comma-separated tags
```

**plan**:
```jsonc
{
  // Note: title belongs to CanvasMessage.title, not template_data
  "plan_id": "plan-oauth2-migration",    // Unique plan identifier
  "status": "proposed",                  // proposed | active | completed | cancelled
  "mermaid": "graph TD\n  A[Design] --> B[Implement]\n  B --> C[Test]",
  "steps": [
    {
      "id": "task-001",
      "subject": "OAuth2 Design",
      "agent": "claude",                 // Suggested agent
      "status": "pending",               // pending | blocked | in_progress | completed | failed
      "blocked_by": []                   // IDs of blocking steps
    }
  ]
  // actions (approve, edit, cancel) are rendered by the CanvasMessage layer
}
```

CLI shortcut:
```bash
# Post plan card
synapse canvas plan '{"title":"Migration Plan","plan_id":"plan-001","status":"proposed","mermaid":"...","steps":[...]}'

# Post from file
synapse canvas plan --file plan.json
```

Plan steps include dependency tracking and status updates that sync back to the Canvas Plan Card.

See [Smart Suggest & Plan Canvas Design](smart-suggest-plan-canvas.md) for the full design.

Other templates (`comparison`, `dashboard`, `steps`, `slides`) can be posted via `synapse canvas post` with the full Canvas Message Protocol JSON including `template` and `template_data` fields.

### Format Registry (Extensible)

```python
FORMAT_REGISTRY: dict[str, FormatSpec] = {
    "mermaid":  FormatSpec(body_type="string", cdn="mermaid/11.4.1/mermaid.min.js"),
    "markdown": FormatSpec(body_type="string", cdn=None),  # Rendered by built-in simpleMarkdown() + inlineMarkdown() — no external library
    "html":     FormatSpec(body_type="string", cdn=None, sandboxed=True),
    "table":    FormatSpec(body_type="object", cdn=None),  # {headers, rows}
    "json":     FormatSpec(body_type="any",    cdn=None),
    "diff":     FormatSpec(body_type="string", cdn="diff2html/3.4.48/diff2html.min.js"),  # Rendered as side-by-side diff
    "chart":    FormatSpec(body_type="object", cdn="chart.js/4.4.7/chart.umd.min.js"),
    "image":    FormatSpec(body_type="string", cdn=None),   # data URI or URL
    "code":     FormatSpec(body_type="string", cdn="highlight.js/11.11.1/highlight.min.js"),
    "log":      FormatSpec(body_type="any",    cdn=None),
    "status":   FormatSpec(body_type="object", cdn=None),
    "metric":   FormatSpec(body_type="object", cdn=None),
    "checklist":FormatSpec(body_type="any",    cdn=None),
    "timeline": FormatSpec(body_type="any",    cdn=None),
    "alert":    FormatSpec(body_type="object", cdn=None),
    "file-preview": FormatSpec(body_type="object", cdn=None),
    "trace":    FormatSpec(body_type="any",    cdn=None),
    "progress": FormatSpec(body_type="object", cdn=None),
    "terminal": FormatSpec(body_type="string", cdn=None),
    "dependency-graph": FormatSpec(body_type="object", cdn=None),
    "cost":     FormatSpec(body_type="object", cdn=None),
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
| `SYNAPSE_CANVAS_DB_PATH` | `~/.synapse/canvas.db` | Database path (user-global) |
| `SYNAPSE_CANVAS_ENABLED` | `true` | Enable/disable |

```python
# config.py
CANVAS_DEFAULT_PORT: int = 3000
CANVAS_MAX_CONTENT_SIZE: int = 2_000_000    # 2MB per content block
CANVAS_MAX_BLOCKS_PER_CARD: int = 30        # Max sections in composite card
CANVAS_MAX_CARDS: int = 200                 # Auto-cleanup threshold
CANVAS_NOTIFICATION_TTL: int = 10           # Seconds for toast notifications
CANVAS_CARD_TTL: int = 3600                 # Card expiry: 1 hour (seconds)
```

---

## Implementation Phases

### Phase 1: Protocol + Store + Server + Mermaid
- [x] `CanvasMessage` protocol dataclass + validation
- [x] `CanvasStore` (SQLite CRUD with upsert)
- [x] Canvas FastAPI server (HTML + POST/GET + SSE)
- [x] `synapse canvas serve` command
- [x] `synapse canvas post` command (raw JSON)
- [x] `synapse canvas mermaid` shortcut
- [x] `index.html` with card grid + Mermaid rendering + SSE
- [x] Agent badge with name/type/timestamp
- [x] Tests for protocol, store, and API

### Phase 2: All Formats
- [x] `markdown`, `table`, `json`, `code`, `diff`, `html` renderers
- [x] Corresponding CLI shortcuts
- [x] Composite cards (multi-block)
- [x] `chart` format with Chart.js (all types: bar, line, pie, doughnut, radar, polarArea, scatter, bubble)
- [x] `image` format
- [x] Filter bar in browser UI
- [x] highlight.js integration for `code` format syntax highlighting
- [x] Side-by-side diff renderer (replaces unified diff)
- [x] HTML iframe fills Canvas view content area
- [x] All 23 card formats verified on Canvas view

### Phase 3: UX Polish
- [x] SPA routing: `#/` (Canvas view), `#/dashboard` (Dashboard view), `#/history` (History view), `#/admin` (Agent Control), `#/harnesses` (Harnesses landing), `#/harnesses/skills` (Skills viewer), `#/harnesses/mcp` (MCP Servers viewer), and `#/system` (System view)
- [ ] Card pinning + tag filtering
- [x] Toast notifications (`notify` type) with batching (300ms window)
- [x] Dark/light theme toggle (includes theme-synced Mermaid diagrams)
- [x] Card animations: `scaleIn` on first render via `.is-new` CSS modifier; suppressed on polling/SSE updates. Dashboard widgets update in-place (no DOM rebuild) and preserve expand/collapse state across 10-second polling via `updateDashWidget()`
- [ ] Auto-cleanup of old cards
- [ ] `--file` flag for all shortcuts

### Phase 4: Integration
- [ ] `/canvas/cards` proxy endpoint on agent A2A server
- [ ] Auto-start Canvas server on first `synapse canvas post`
- [ ] Agent instructions update (teach agents about Canvas)
- [ ] Skill update (add Canvas commands to synapse-a2a skill)

### Phase 5: New Card Formats
Documented 12 new formats added to FORMAT_REGISTRY including `log`, `status`, `metric`, `checklist`, `timeline`, `alert`, `file-preview`, `trace`, `progress`, `terminal`, `dependency-graph`, and `cost`.

### Phase 6: Template System
- [x] `template` and `template_data` fields added to `CanvasMessage`
- [x] 6 templates: `briefing`, `comparison`, `dashboard`, `steps`, `slides`, `plan`
- [x] Per-template validation (`_validate_briefing`, `_validate_comparison`, `_validate_dashboard`, `_validate_steps`, `_validate_slides`, `_validate_plan`)
- [x] `template` / `template_data` columns added to `cards` table (with migration)
- [x] POST/GET endpoints pass template fields through
- [x] `synapse canvas briefing` / `synapse canvas plan` CLI subcommands (`post_briefing()`, `post_plan()`)
- [x] Client-side renderers: `renderBriefing`, `renderComparison`, `renderDashboardTemplate`, `renderStepsTemplate`, `renderSlidesTemplate`, `renderPlanTemplate`
- [x] CSS styles for all 6 templates

---

## Design Decisions (Resolved)

1. **Port**: Default 3000. Configurable via `SYNAPSE_CANVAS_PORT`.
2. **Persistence**: Cards are **ephemeral** — cleared on server restart. Additionally, cards expire after `CANVAS_CARD_TTL` (default 1 hour). Pinned cards are exempt from TTL expiry.
3. **HTML sandboxing**: `html` format renders in sandboxed `<iframe>`. In Canvas view, the iframe fills the content area via CSS flex; in History view, it auto-resizes to content height.
4. **CDN vs vendored**: CDN for Phase 1. `--offline` flag for vendored assets in the future.
5. **Card ownership**: Agents can only update/delete their own cards.
6. **SPA routing**: Hash-based (`#/`, `#/history`, `#/dashboard`, `#/admin`, `#/harnesses`, `#/harnesses/skills`, `#/harnesses/mcp`, `#/system`) for zero-server-config client-side routing. Canvas view is the default route for an immersive card display experience; History is a sub-route under Canvas in the sidebar. Dashboard shows operational status; Agent Control (`#/admin`) provides interactive agent management; Harnesses is a landing page whose Skills (`#/harnesses/skills`) and MCP Servers (`#/harnesses/mcp`) sub-routes browse discovered skills and configured MCP servers respectively; System shows configuration.
7. **Diff rendering**: Built-in side-by-side diff renderer instead of unified diff. Parses unified diff format and renders old/new lines in a two-column layout.
8. **Code highlighting**: highlight.js integrated for `code` format cards. Configured with `ignoreUnescapedHTML: true`.

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
