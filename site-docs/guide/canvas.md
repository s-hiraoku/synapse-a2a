# Canvas

## Overview

Synapse Canvas is a shared visual output surface for agents. When an agent needs to express something beyond text — diagrams, rich tables, interactive charts, design mockups — it sends a **Canvas Message** via a unified protocol. A local web server renders the content in the browser in real-time.

### Design Principles

1. **Agent-driven**: Canvas is the agent's drawing board — agents decide what to show.
2. **Protocol-first**: One unified JSON protocol for all communication. No type-specific CLI commands.
3. **Expressive**: Agents can render anything — from Mermaid diagrams to raw HTML/CSS.
4. **Template-driven**: Six built-in templates (briefing, comparison, dashboard, steps, slides, plan) provide structured layouts for common use cases.
5. **Dead simple for agents**: One command, one JSON payload. That's it.
6. **Zero-config for users**: `synapse canvas` starts the server. No npm, no build step.

## Quick Start

### Start the Canvas Server

```bash
synapse canvas serve [--port 3000] [--no-open]
```

This starts the Canvas server and opens `http://localhost:3000` in your browser. The server auto-starts in the background when you post your first card, so explicit `serve` is optional.

### Post Content

```bash
# Mermaid diagram
synapse canvas mermaid "graph TD; A-->B; B-->C" --title "Auth Flow"

# Markdown document
synapse canvas markdown "## Design\nThis system uses..." --title "Design Doc"

# Data table
synapse canvas table '{"headers":["a","b"],"rows":[["1","2"]]}' --title "Results"

# Raw HTML (full freedom)
synapse canvas html "<div>anything</div>" --title "Custom"

# Interactive artifact (like Claude.ai Artifacts)
synapse canvas post artifact '<!doctype html>...' --title "Counter App"

# Code with syntax highlighting
synapse canvas code "def foo(): pass" --lang python --title "Impl"

# Unified diff
synapse canvas diff "--- a/f.py\n+++ b/f.py\n..." --title "Changes"

# Chart.js chart
synapse canvas chart '{"type":"bar","data":{...}}' --title "Coverage"

# Image (URL or base64 data URI)
synapse canvas image "https://..." --title "Screenshot"

# Link preview (OGP metadata)
synapse canvas link "https://example.com/article" --title "Reference"

# Briefing (structured report with sections)
synapse canvas briefing '{"title":"Sprint Report","sections":[{"title":"Summary"}],"content":[{"format":"markdown","body":"All tasks done."}]}' --title "Sprint Report"
```

### Common Options

All posting commands accept these options:

```bash
--title "Card Title"          # Card title
--id my-card                  # Stable ID for updates (upsert). Auto-generated if omitted.
--pin                         # Pin to top (exempt from TTL expiry)
--tag design --tag auth       # Tags for filtering
--file ./diagram.mmd          # Read body from file instead of argument
```

## Canvas Message Protocol

All agent-to-Canvas communication uses a single JSON protocol.

### Message Structure

```json
{
  "type": "render",
  "content": {
    "format": "mermaid",
    "body": "graph TD; A-->B; B-->C"
  },
  "agent_id": "synapse-claude-8103",
  "agent_name": "Gojo",
  "title": "Auth Flow Design",
  "card_id": "auth-flow",
  "pinned": false,
  "tags": ["design", "auth"],
  "template": "",
  "template_data": {}
}
```

The `template` and `template_data` fields are optional. When set, the frontend applies a structured layout on top of the content blocks. See [Templates](#templates) for details.

### Message Types

| Type | Purpose |
|---|---|
| `render` | Display content on Canvas |
| `update` | Update existing card (requires `card_id`) |
| `clear` | Remove cards (`card_id` or `agent_id` filter) |
| `notify` | Ephemeral toast notification (disappears after N seconds) |

### Content Formats

The `content.format` field determines how `content.body` is rendered. New formats can be added without protocol changes.

| Format | Body | Renderer | Use Case |
|---|---|---|---|
| `mermaid` | Mermaid source | mermaid.js | Flowcharts, sequence diagrams, ER diagrams |
| `markdown` | Markdown text | Built-in markdown parser | Design docs, explanations, formatted text |
| `html` | Raw HTML string | Sandboxed iframe with theme sync & auto-resize | Full freedom — interactive HTML/JS/CSS artifacts |
| `artifact` | Full HTML document | Sandboxed iframe with theme sync & auto-resize | Interactive apps, counters, forms, games, data visualizations |
| `table` | `{headers, rows}` | Native HTML | Structured data, test results, comparisons |
| `json` | Any JSON | Collapsible tree viewer | API responses, config, data structures |
| `diff` | Unified diff | Side-by-side diff renderer | Code changes, before/after comparisons |
| `chart` | Chart.js config | Chart.js | All chart types: bar, line, pie, doughnut, radar, polarArea, scatter, bubble |
| `image` | Base64 data URI or URL | `<img>` | Screenshots, SVG diagrams, generated images |
| `code` | Source code + `lang` | Highlight.js | Syntax-highlighted code blocks |
| `log` | `[{level, ts, msg}]` | Agent logs | Agent logs with INFO/WARN/ERROR color coding |
| `status` | `{state, label, detail}` | Status badge | Build/task status with colored badge |
| `metric` | `{value, unit, label}` | Single KPI | Single KPI display (large number) |
| `checklist` | `[{text, checked}]` | Checklist | Task progress with checkboxes |
| `timeline` | `[{ts, event, agent}]` | Timeline | Time-series events, task progression |
| `alert` | `{severity, message, source}` | Alert notification | Persistent important notifications |
| `file-preview` | `{path, lang, snippet, start_line}` | Code preview | Code snippet with file path and line numbers |
| `trace` | `[{name, duration_ms, status, children?}]` | A2A trace | A2A routing spans with duration bars |
| `progress` | `{current, total, label, steps, status}` | Progress bar | Progress bar with steps (status: in_progress, completed, failed, paused) |
| `terminal` | Plain text (ANSI supported) | Terminal output | Terminal output with ANSI color support |
| `dependency-graph` | `{nodes: [{id, group}], edges: [{from, to}]}` | Mermaid graph | Dependency graph rendered as Mermaid |
| `tip` | Plain text | Tip callout | Helpful hints and tips |
| `cost` | `{agents: [{name, input_tokens, output_tokens, cost}], total_cost, currency}` | Cost table | Token/cost aggregation table |
| `link-preview` | `{url, og_title?, og_description?, og_image?, og_site_name?}` | Link card | Rich link preview with OGP metadata (also accepts plain aliases: `title`, `description`, `image`, `site_name`) |
| `plan` | `{}` (empty object; data lives in `template_data`) | Plan template | Execution plan with Mermaid DAG, step list, and status tracking |

!!! tip "Mermaid Theme Integration"
    Mermaid diagrams automatically sync with the Canvas dark/light theme toggle. When the theme changes, diagrams re-render using a custom color palette — Catppuccin-inspired tones for dark mode and Indigo tones for light mode, with the brand accent color (`#4051b5`). The original Mermaid source is preserved in a `data-mermaid-source` attribute on each diagram element, enabling seamless re-rendering without re-posting the card.

!!! tip "Enhanced Markdown Rendering"
    The `markdown` format uses the built-in `simpleMarkdown()` parser with support for tables, blockquotes (`>` lines), horizontal rules (`---`), nested ordered and unordered lists, headings (`#` → h2, `##` → h3, `###` → h4), inline code, fenced code blocks, bold, italic, strikethrough, links, and proper paragraph wrapping. Markdown card content is rendered with **Source Sans 3** for body text and **Source Code Pro** for code, with styled heading hierarchy, blockquote accent stripes, and table styling.

!!! tip "The `artifact` Format — Interactive Apps"
    The `artifact` format is purpose-built for interactive HTML/JS/CSS applications — think Claude.ai Artifacts. It shares the same sandboxed iframe renderer as `html` but carries distinct semantic meaning: `artifact` signals an interactive application (counter, form, game, data visualization) whereas `html` is for raw HTML snippets. Use `artifact` when posting self-contained interactive apps.

!!! tip "The `html` Escape Hatch — Raw HTML"
    When no predefined format fits, agents can send raw HTML snippets via the `html` format. Use this for simple markup and content insertion — styled text, embedded widgets, or layout fragments. HTML content is rendered in a sandboxed `<iframe>` (`sandbox="allow-scripts"`, no `allow-same-origin`) for safety. For interactive applications (counters, forms, games), use the `artifact` format instead.

    **Theme Sync**: The iframe automatically receives the Canvas theme via `postMessage`. Agent-generated HTML can use CSS variables `var(--bg)`, `var(--fg)`, and `var(--border)` to adapt to dark/light mode. When the user toggles the theme, all HTML iframes update instantly.

    **Auto-Resize**: In the History view (`#/history`), iframes automatically resize to fit their content height using a `ResizeObserver` inside the iframe that sends `postMessage` notifications to the parent. In the Canvas view (`#/`), the iframe fills the entire content area for immersive display.

    **Full Document Handling**: Both HTML fragments and full documents (with `<!doctype html>`, `<html>`, `<head>`, `<body>`) are accepted. Full documents are normalized — `<head>` and `<body>` contents are extracted and wrapped through the same pipeline as fragments, avoiding CSS cascade conflicts and CSP issues.

!!! tip "Block-Level Metadata (`x_title` / `x_filename`)"
    Supported renderers (`mermaid`, `json`, `code`, `log`, `checklist`, `trace`, and `tip`) accept optional `x_title` and `x_filename` fields that render a styled header above the content. This block-level metadata keeps decorative labels out of the base `body` schema and follows the A2A `x-` extension convention.

    ```json
    {
      "format": "mermaid",
      "body": "graph TD; A-->B",
      "x_title": "Auth Flow",
      "x_filename": "docs/auth.mmd"
    }
    ```

    ```json
    {
      "format": "code",
      "body": "def foo(): pass",
      "lang": "python",
      "x_title": "Implementation",
      "x_filename": "src/foo.py"
    }
    ```

    When either field is set, a metadata row appears above the rendered content showing the title and/or filename. Both fields are optional and independent.

!!! tip "Images: PNG, JPEG, SVG, and more"
    The `image` format accepts any image the browser can render via `<img src>`. Use a URL for large images, or Base64 data URIs for inline embedding (up to 2MB).

    **Supported formats:**

    | Image Type | Data URI prefix | Use case |
    |---|---|---|
    | PNG | `data:image/png;base64,...` | Screenshots, UI mockups |
    | JPEG | `data:image/jpeg;base64,...` | Photos, high-color images |
    | SVG | `data:image/svg+xml;base64,...` | Architecture diagrams, network topology, vector illustrations |
    | GIF | `data:image/gif;base64,...` | Animated demos |
    | WebP | `data:image/webp;base64,...` | Compact screenshots |

    **SVG is particularly powerful** — agents can programmatically generate vector diagrams (architecture layouts, agent network topology, data flow graphs) that scale perfectly at any resolution. SVG files are typically a few KB, well within the 2MB limit.

    **Examples:**

    ```bash
    # URL-based image (no size limit)
    synapse canvas image "https://example.com/screenshot.png" --title "UI Design"

    # Base64 PNG screenshot
    synapse canvas image "data:image/png;base64,iVBOR..." --title "Test Result"

    # SVG diagram (agent-generated)
    synapse canvas image "data:image/svg+xml;base64,PHN2Zy..." --title "System Architecture"

    # From file
    synapse canvas image --file ./diagram.svg --title "Network Diagram"
    ```

### Composite Cards

A single card can contain multiple content sections for rich layouts:

```json
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

This enables agents to compose rich, multi-section cards — like a document with embedded diagrams and tables. Maximum 30 content blocks per card.

## Templates

Templates add structured layouts on top of composite cards. While composite cards let you combine multiple content blocks, templates control **how those blocks are arranged** in the browser.

### Available Templates

Each template has a distinct **accent color** used for left-border highlights, progress bars, and step markers, making it easy to identify the template type at a glance.

| Template | Purpose | Accent Color | Key Fields |
|---|---|---|---|
| `briefing` | Structured report with collapsible sections | Brand indigo | `sections` (title, blocks, summary, collapsed) |
| `comparison` | Side-by-side or stacked N-way comparison (2-4 sides) | Amber | `sides` (label, blocks), `layout` |
| `dashboard` | Grid layout with resizable widgets (1-4 columns) | Warning (amber) | `widgets` (title, blocks, size), `cols` |
| `steps` | Linear workflow with completion tracking | Green (success) | `steps` (title, blocks, done, description) |
| `slides` | Page-by-page navigation with speaker notes | Signal (cyan) | `slides` (title, blocks, notes) |
| `plan` | Execution plan with dependency DAG and status tracking | Purple | `plan_id`, `status`, `steps` (id, subject, agent, status, blocked_by), `mermaid` |

### How Templates Work

Templates use **block indices** to map content blocks to layout positions. Each template's `template_data` references content blocks by their index in the `content` array.

```json
{
  "type": "render",
  "content": [
    { "format": "markdown", "body": "## Overview\nProject status..." },
    { "format": "chart", "body": {"type": "bar", "data": {"labels": ["Q1","Q2"], "datasets": [{"data": [10,20]}]}} },
    { "format": "table", "body": {"headers": ["Task","Status"], "rows": [["Auth","Done"]]} }
  ],
  "template": "briefing",
  "template_data": {
    "summary": "All milestones on track.",
    "sections": [
      { "title": "Overview", "blocks": [0] },
      { "title": "Metrics", "blocks": [1] },
      { "title": "Tasks", "blocks": [2], "collapsed": true }
    ]
  },
  "title": "Sprint Report"
}
```

### Template Data Schemas

#### `briefing`

```json
{
  "summary": "Optional executive summary text",
  "sections": [
    {
      "title": "Section Title",
      "blocks": [0, 1],
      "summary": "Optional section summary",
      "collapsed": false
    }
  ]
}
```

Maximum 20 sections.

#### `comparison`

```json
{
  "summary": "Optional comparison summary",
  "sides": [
    { "label": "Option A", "blocks": [0, 1] },
    { "label": "Option B", "blocks": [2, 3] }
  ],
  "layout": "side-by-side"
}
```

Supports 2-4 sides. Layout options: `"side-by-side"` (default) or `"stacked"`.

#### `dashboard`

```json
{
  "cols": 2,
  "widgets": [
    { "title": "Coverage", "blocks": [0], "size": "1x1" },
    { "title": "Trend", "blocks": [1], "size": "2x1" }
  ]
}
```

Columns: 1-4 (default 2). Widget sizes: `"1x1"`, `"2x1"`, `"1x2"`, `"2x2"`. Maximum 20 widgets.

#### `steps`

```json
{
  "summary": "Optional workflow summary",
  "steps": [
    { "title": "Write Tests", "blocks": [0], "done": true, "description": "Unit tests for auth" },
    { "title": "Implement", "blocks": [1], "done": false }
  ]
}
```

Maximum 30 steps.

#### `slides`

```json
{
  "slides": [
    { "title": "Introduction", "blocks": [0], "notes": "Speaker notes here" },
    { "title": "Architecture", "blocks": [1, 2] }
  ]
}
```

Maximum 30 slides. Each slide must have a `blocks` array.

#### `plan`

```json
{
  "plan_id": "plan-oauth2",
  "status": "proposed",
  "mermaid": "graph TD\n  A[Design] --> B[Implement]\n  A --> C[Test]\n  B --> D[Review]\n  C --> D",
  "steps": [
    { "id": "s1", "subject": "Design auth module", "agent": "claude", "status": "pending" },
    { "id": "s2", "subject": "Implement auth", "agent": "codex", "status": "pending", "blocked_by": ["s1"] },
    { "id": "s3", "subject": "Write tests", "agent": "gemini", "status": "pending", "blocked_by": ["s1"] },
    { "id": "s4", "subject": "Review", "agent": "claude", "status": "pending", "blocked_by": ["s2", "s3"] }
  ]
}
```

Maximum 30 steps. Each step must have `id` and `subject`.

| Field | Required | Description |
|---|:---:|---|
| `plan_id` | Yes | Unique plan identifier (also used as `card_id`) |
| `status` | No | Plan status: `proposed`, `active`, `completed`, `cancelled` (default: `proposed`) |
| `mermaid` | No | Mermaid DAG source for visual dependency graph |
| `steps` | Yes | Array of step objects |
| `steps[].id` | Yes | Unique step identifier |
| `steps[].subject` | Yes | Step description |
| `steps[].agent` | No | Suggested assignee agent |
| `steps[].status` | No | Step status: `pending`, `blocked`, `in_progress`, `completed`, `failed` |
| `steps[].blocked_by` | No | Array of step IDs this step depends on |

The Plan template renders a Mermaid dependency DAG at the top (if `mermaid` is provided) followed by a step list with status indicators. Plan cards are pinned by default.


### CLI: Plan Shortcut

The `plan` template has a dedicated CLI command:

```bash
# From inline JSON
synapse canvas plan '{"plan_id":"plan-oauth2","steps":[{"id":"s1","subject":"Design"}]}'

# From file
synapse canvas plan --file plan.json --title "OAuth2 Plan"

# With options
synapse canvas plan '...' --title "Plan" --card-id plan-oauth2 --pinned --tags "plan,auth"
```

### CLI: Briefing Shortcut

The `briefing` template has a dedicated CLI command for convenience:

```bash
# From inline JSON
synapse canvas briefing '{"title":"Report","sections":[{"title":"Summary"}],"content":[{"format":"markdown","body":"Done."}]}'

# From file
synapse canvas briefing --file report.json --title "Sprint Report"

# With options
synapse canvas briefing '...' --title "Report" --summary "Executive summary" --pinned --tags "sprint,review"
```

The `plan` template also has a CLI shortcut (`synapse canvas plan`). Other templates can be posted via the `post-raw` command with the `template` and `template_data` fields in the JSON payload.

## CLI Commands

### Posting (Full Control)

```bash
synapse canvas post-raw '<Canvas Message JSON>'
```

### Search and Management

```bash
synapse canvas list                    # All cards
synapse canvas list --mine             # Own cards only (filtered by $SYNAPSE_AGENT_ID)
synapse canvas list --search "auth"    # Title search
synapse canvas list --type mermaid     # Filter by format
synapse canvas delete <card_id>        # Delete card (own cards only)
synapse canvas clear                   # Clear all cards
synapse canvas clear --agent claude    # Clear specific agent's cards
```

### Additional Format Shortcuts

```bash
synapse canvas post log '[{"level":"INFO","ts":"10:00","msg":"Started"}]' --title "Logs"
synapse canvas post status '{"state":"success","label":"Build","detail":"All pass"}' --title "Status"
synapse canvas post metric '{"value":98.5,"unit":"%","label":"Coverage"}' --title "KPI"
synapse canvas post checklist '[{"text":"Tests","checked":true},{"text":"Review","checked":false}]' --title "Tasks"
synapse canvas post timeline '[{"ts":"10:00","event":"Started","agent":"claude"}]' --title "Progress"
synapse canvas post alert '{"severity":"error","message":"CI failed","source":"github"}' --title "Alert"
synapse canvas post file-preview '{"path":"server.py","lang":"python","snippet":"def run():","start_line":42}' --title "Preview"
synapse canvas post trace '[{"name":"send","duration_ms":150,"status":"ok"}]' --title "Trace"
synapse canvas post progress '{"current":3,"total":7,"label":"Migration","steps":["Schema","Data","Indexes","Views","Procs","Test","Deploy"],"status":"in_progress"}' --title "Progress"
synapse canvas post terminal 'Building project...\n\033[32m✓ Compiled 42 files\033[0m\n\033[31m✗ 2 errors found\033[0m' --title "Build Output"
synapse canvas post dependency-graph '{"nodes":[{"id":"auth","group":"core"},{"id":"api","group":"core"},{"id":"ui","group":"frontend"}],"edges":[{"from":"ui","to":"api"},{"from":"api","to":"auth"}]}' --title "Dependencies"
synapse canvas post tip 'Remember to run tests before pushing' --title "Reminder"
synapse canvas post cost '{"agents":[{"name":"claude","input_tokens":15000,"output_tokens":8000,"cost":0.12},{"name":"gemini","input_tokens":20000,"output_tokens":5000,"cost":0.05}],"total_cost":0.17,"currency":"USD"}' --title "Token Costs"

# Link preview with OGP metadata (server-side enrichment)
synapse canvas link "https://example.com/article" --title "Reference"
```

## Server Auto-Start

Canvas commands automatically start the server if it is not running. The flow for all posting commands:

1. Check `GET http://localhost:{port}/api/health`
2. If `200 OK` — server is running, proceed to post
3. If connection refused — start server in background, retry health check (max 3s, 500ms interval), then post

The server is detected via the `/api/health` endpoint (which returns `"service": "synapse-canvas"` for identity verification along with an `asset_hash` field). A PID file (`~/.synapse/canvas.pid`) serves as a fallback when the health endpoint is unreachable.

If a stale Canvas process is detected on the port during startup (e.g., from a previous session that was not properly stopped, or when the server's `asset_hash` no longer matches the local frontend assets), it is automatically terminated and replaced with a fresh server instance. The stop sequence sends SIGTERM first, with a SIGKILL fallback if the process does not exit within the grace period.

## HTTP API

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/cards` | Create/update card (Canvas Message Protocol) |
| `GET` | `/api/cards` | List cards (optional `?agent_id=`, `?search=`, `?type=` filters) |
| `GET` | `/api/cards/{id}` | Get single card |
| `GET` | `/api/cards/{id}/download` | Download card as file (optional `?format=` override) |
| `DELETE` | `/api/cards/{id}` | Delete card (own cards only) |
| `DELETE` | `/api/cards` | Clear all cards (optional `?agent_id=` filter) |
| `GET` | `/api/stream` | SSE stream (card events) |
| `GET` | `/api/formats` | List supported formats |
| `GET` | `/api/health` | Health check (returns `service`, `status`, `pid`, `cards`, `version`, `asset_hash`) |
| `GET` | `/api/system` | System panel data (agents, tasks, file locks) |
| `GET` | `/api/admin/agents` | List active agents for Agent Control view |
| `POST` | `/api/admin/send` | Send message to agent via A2A |
| `POST` | `/tasks/send` | Receive agent replies (A2A callback) |
| `GET` | `/api/admin/replies/{id}` | Poll for agent replies by task ID |
| `GET` | `/api/admin/tasks/{id}` | Fallback: proxy task status to target agent |
| `POST` | `/api/admin/jump/{agent_id}` | Jump to agent's terminal pane |
| `POST` | `/api/admin/agents/spawn` | Spawn a new agent |
| `DELETE` | `/api/admin/agents/{id}` | Stop an agent |
| `GET` | `/api/db/list` | List Synapse SQLite databases in `.synapse/` |
| `GET` | `/api/db/{db_name}/{table_name}` | Query table rows (read-only, paginated) |

## System Panel

The Canvas browser UI includes a **System Panel** at the top that shows real-time system state:

| Section | Data Source | Shows |
|---|---|---|
| **Agents** | `~/.a2a/registry/*.json` | Agent name, type, status with colored dots |
| **File Locks** | `.synapse/file_safety.db` | Active file locks with agent assignment |

The system panel is **pull-based** — the Canvas server reads directly from project databases. Agents don't need to explicitly post system state. The panel polls `/api/system` every 10 seconds and also refreshes on SSE `system_update` events.

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

Canvas uses a **dedicated port (3000)** separate from agent servers (8100-8149) because it needs one stable URL that aggregates all agents' output in one place, with a lifecycle independent of any agent.

## Card Lifecycle

- **Ephemeral by default**: Cards are working data. Server restart clears all cards.
- **TTL expiry**: Cards expire after `CANVAS_CARD_TTL` (default 1 hour). Expired cards are cleaned up automatically.
- **Pinned cards**: Exempt from TTL. They stay until manually deleted or server restart.
- **Update resets TTL**: When a card is updated via `card_id`, its expiry is refreshed.

## Card Download

Cards can be downloaded as files directly from the Canvas UI or via the HTTP API. Each content format maps to an optimal download format automatically.

### Browser UI

Every card in the History view and the Canvas spotlight view includes a **download button** (<i class="ph ph-download-simple"></i>). Clicking it triggers a browser download of the card content in its native format.

### HTTP API

```
GET /api/cards/{card_id}/download[?format=<override>]
```

Returns the card content as a downloadable file with an appropriate `Content-Disposition` header and MIME type.

The optional `format` query parameter overrides the default export format. Accepted values: `md`, `json`, `csv`, `html`, `txt`, `native`.

### Format Mapping

Each card format is exported to the most natural file type:

| Card Format | Download As | Extension | MIME Type |
|---|---|---|---|
| `markdown`, `checklist`, `tip`, `alert`, `status`, `metric`, `progress`, `timeline`, `link-preview` | Markdown | `.md` | `text/markdown` |
| `code`, `terminal` | Plain text | `.txt` | `text/plain` |
| `html`, `artifact` | HTML | `.html` | `text/html` |
| `diff` | Unified diff | `.diff` | `text/x-diff` |
| `mermaid` | Mermaid source (or Markdown via `?format=md`) | `.mmd` | `text/plain` |
| `image` | Image (PNG) | `.png` | `image/png` |
| `json`, `dependency-graph`, `trace`, `log`, `file-preview`, `plan` | JSON | `.json` | `application/json` |
| `chart` | Chart.js config (or Markdown via `?format=md`) | `.json` | `application/json` |
| `table`, `cost` | CSV | `.csv` | `text/csv` |

For composite cards (multiple content blocks), the export uses the primary block's format to determine the output type. Template cards include structured metadata in the export.

!!! tip "Mermaid Markdown Export"
    The `mermaid` format defaults to native `.mmd` export, but also supports Markdown export via `?format=md`. When exported as Markdown, the Mermaid source is wrapped in a fenced code block (` ```mermaid `). This is also used automatically when mermaid blocks appear inside composite or template cards.

!!! tip "Chart Markdown Export"
    The `chart` format defaults to native `.json` export, but also supports Markdown export via `?format=md`. When exported as Markdown, a heading with the chart type is added and the Chart.js config is wrapped in a fenced JSON code block. This is also used automatically when chart blocks appear inside composite or template cards.

## Configuration

| Variable | Default | Description |
|---|---|---|
| `SYNAPSE_CANVAS_PORT` | `3000` | Canvas server port |
| `SYNAPSE_CANVAS_DB_PATH` | `~/.synapse/canvas.db` | Database path (user-global) |
| `SYNAPSE_CANVAS_ENABLED` | `true` | Enable/disable Canvas |

Internal limits:

| Setting | Value |
|---|---|
| Max content size | 2MB per content block |
| Max blocks per card | 30 |
| Max cards | 200 (auto-cleanup threshold) |
| Notification TTL | 10 seconds |
| Card TTL | 3600 seconds (1 hour) |
| Max briefing sections | 20 |
| Max comparison sides | 4 |
| Max dashboard widgets | 20 |
| Max steps | 30 |
| Max slides | 30 |
| Max plan steps | 30 |

## Browser UI

Open `http://localhost:3000` to view the Canvas.

The Canvas UI features a **glassmorphism design** with glass panels and `backdrop-filter` blur, **sidebar navigation** (fixed on desktop, hamburger drawer on mobile) with a custom SVG synapse brand icon, and **Phosphor Icons v2** throughout. History is a sub-item under Canvas in the sidebar (indented with `nav-sub` class); when the History route is active, the Canvas parent link also shows as active and the top bar displays "Canvas / History". Colors are managed centrally via `palette.css` with the brand color unified to MkDocs Material indigo (`#4051b5`).

For a static preview of every card format and template, open the standalone [Card Gallery](../assets/card-gallery.html). It renders all supported card types and built-in templates with hardcoded sample data under `site-docs/assets/`.

The UI uses **SPA hash routing** with seven views:

| Route | View | Purpose |
|---|---|---|
| `#/` | **Canvas** (default) | Full-viewport display of the latest card |
| `#/history` | **History** (sub-item of Canvas) | Card grid with live feed, agent messages, and filters |
| `#/dashboard` | **Dashboard** | Operational status overview with expandable summary+detail widgets (Agents, File Locks, Worktrees, Memory, Errors) |
| `#/admin` | **Agent Control** | Command center for sending messages to agents and managing agent lifecycle |
| `#/workflow` | **Workflow** | Split-panel workflow browser with execution support |
| `#/database` | **Database** | Browse Synapse SQLite databases (read-only) |
| `#/system` | **System** | Configuration and setup information (tips, user-scope saved agents, active-project saved agents, skills, skill sets, sessions, workflows, environment) |

### Canvas View (`#/`)

The Canvas view is a **full-viewport projection** of the most recently updated card. It is designed for ambient display — put it on a secondary monitor or share-screen during pairing.

- The latest card fills the entire content area
- A **title bar** at the top shows the card title
- A **template badge** in the title bar shows the active template name (e.g., BRIEFING, PLAN) when the card uses a template
- A **floating info bar** at the bottom shows agent name, status dot, tags, and timestamp in a minimal, fade-on-hover style
- An **ambient glow** border reflects the posting agent's status color (green=READY, yellow=PROCESSING, etc.)
- **Keyboard navigation**: Press ++arrow-right++ / ++arrow-left++ to browse through cards by recency. A navigation indicator (e.g., "2 / 5") appears in the title bar. Press ++escape++ to return to the live (most-recent) view. Keyboard navigation is disabled when an input field is focused.
- HTML cards render inside a sandboxed `<iframe>` that fills the full content area (no auto-resize — uses CSS flex)
- Filter controls are hidden in this view

### Dashboard View (`#/dashboard`)

The Dashboard view provides a real-time operational status overview of the entire Synapse environment. It is designed for monitoring multi-agent systems at a glance.

**Responsive grid layout**: Widgets are arranged in a CSS Grid with `auto-fit` columns (minimum 350px each), automatically adapting from multi-column on wide screens to a single column on mobile (below 768px).

**Two-tier progressive disclosure**: Each widget shows a compact summary row by default (counts, key metrics). Clicking the widget header expands it to reveal the full detail table. This keeps the dashboard scannable while preserving access to granular data. Widget expand/collapse state is preserved across re-renders so the view does not jump while you are reading details. Widget headers are keyboard-accessible (`tabindex`, `aria-expanded`).

**Widgets:**

- **Agents**: Running agents with status dots and metadata
- **File Locks**: Active file locks with agent assignment
- **Worktrees**: Active git worktrees for agent isolation
- **Shared Memory**: Recent shared memory entries
- **Errors**: Registry errors and agent issues

The Dashboard updates via **SSE (Server-Sent Events)** for instant reactivity, with a 10-second fallback polling interval to keep widgets current if events are missed or delayed.

### History View (`#/history`)

The History view shows the traditional card grid with live feed and agent messages. In the sidebar, History appears as an indented sub-item under the Canvas parent link. When this route is active, the Canvas parent also shows as active and the top bar displays "Canvas / History".

**Features:**

- **Live Feed**: Chronological event stream with pulsing dot indicator
- **Card Grid**: All cards in a responsive grid layout
- **Filter bar**: Filter by format type and by agent
- **Dark/light theme**: Manual toggle via sidebar button, persisted in `localStorage("canvas-theme")` (defaults to dark). Mermaid diagrams re-render automatically when the theme changes, using palette-matched colors for each mode.
- **Toast notifications**: `notify` type shows ephemeral messages. Toasts are **batched** within a 300ms window -- when multiple SSE events arrive in a burst, a single summary toast (e.g., "3 cards updated") is shown instead of individual toasts for each event.
- **Agent badges**: Each card shows agent name, type icon/color, and relative timestamp

### Agent Control View (`#/admin`)

The Agent Control view is a **Command Center** for directly interacting with running agents from the Canvas browser UI. It provides a chat-style interface for sending messages to agents and viewing their responses.

**Components:**

- **Agent table**: Clickable rows showing all active agents (auto-populated from the registry) with status dots, name, type, role, and status. Click a row to select the target agent. Double-click a row to jump to that agent's terminal pane (tmux/iTerm2). Right-click a row to open a context menu with a **Kill Agent** action that sends SIGTERM to the agent process (with a confirmation dialog). The agent panel includes a resizable splitter (`role="separator"`, keyboard-accessible via `tabindex`) between the agent table and the response feed.
- **Message input**: Multi-line textarea for composing commands. Press Cmd+Enter (macOS) or Ctrl+Enter to send; plain Enter inserts a newline. The Send button is disabled during pending requests to prevent double-send.
- **Response feed**: Chat-bubble style conversation log showing sent commands (right-aligned) and agent responses (left-aligned) with timestamps.

**How it works:**

1. Click an agent row in the table to select it as the target
2. Type a message/command in the textarea
3. The message is sent via the A2A protocol (`POST /api/admin/send`) with `sender_endpoint` metadata pointing back to Canvas
4. The target agent processes the message and replies via `synapse reply`, which sends a structured response back to Canvas (`POST /tasks/send`)
5. Canvas stores the reply and the frontend polls `GET /api/admin/replies/{task_id}` using adaptive intervals (1s for the first 10 attempts, then 2s, up to 5 minutes)
6. When the reply arrives, it appears in a chat bubble with clean, structured text (no terminal junk since responses bypass PTY output)

The reply-based flow reuses the same `synapse reply` mechanism as inter-agent communication, ensuring clean responses without terminal output parsing (ANSI escapes, status bars, spinner fragments).

The agent list refreshes automatically on SSE `system_update` events, so newly started or stopped agents appear without manual refresh.

!!! tip "Agent Control API Endpoints"
    The Agent Control view is backed by dedicated API endpoints on the Canvas server. See [Canvas Admin API](../reference/api.md#canvas-admin-api) for the full endpoint reference.

### Database View (`#/database`)

The Database view provides a read-only browser for Synapse SQLite databases stored in the project's `.synapse/` directory. It is useful for inspecting file safety records, workflow runs, observations, instincts, and other project-local data without leaving the Canvas UI.

**Layout**: A split-panel interface with a sidebar listing discovered databases and their tables, and a main content area showing paginated query results.

**Left panel -- Database sidebar**: Lists all `.db` files found in `.synapse/` (excluding internal databases like `task_board.db`). Each database expands to show its tables. Click a table name to query it.

**Right panel -- Table viewer**: Displays the selected table's rows in a scrollable HTML table with column headers. Pagination controls (Prev / Next) allow browsing large tables (100 rows per page by default).

**API endpoints:**

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/db/list` | List all SQLite databases in `.synapse/` with table names and file sizes |
| `GET` | `/api/db/{db_name}/{table_name}?limit=N&offset=N` | Query rows from a table (read-only, parameterized) |

All database access is read-only (`?mode=ro` SQLite URI). Table names are validated against `^[a-zA-Z_][a-zA-Z0-9_]*$` to prevent injection.

### Workflow View (`#/workflow`)

The Workflow view provides a split-panel interface for browsing and executing [Workflows](workflow.md) directly from the Canvas browser UI.

**Left panel — Workflow list**: A table of all available workflows showing name, step count, scope, and description. Click a row to select a workflow.

**Right panel — Workflow detail**: Displays the selected workflow's steps, a Mermaid DAG visualization of the execution graph (with message preview and `response_mode` labels on edges), and a **Run** button to trigger execution. The project directory is displayed next to the Run button for context.

**Execution**: Clicking Run sends `POST /api/workflow/run/{name}` to start async background execution. Each step is sent directly from Canvas to the target agent over A2A HTTP using sender metadata `canvas-workflow` / `Workflow` and a Canvas `sender_endpoint`, so the target can reply back to Canvas with `synapse reply`. Real-time progress is streamed via SSE `workflow_update` events, updating step status icons as each step completes:

- **Pending** steps show a hourglass icon
- **Running** steps show a spinner icon
- **Completed** steps show a checkmark — click the "Output" expander to view the accepted task summary
- **Failed** steps show a red error message with a human-readable explanation

When `auto_spawn` is enabled (workflow-level or step-level), Canvas automatically spawns missing agents before sending. A toast notification appears when the entire workflow run completes or fails. Execution history is persisted to a SQLite database (`.synapse/workflow_runs.db`) so that past runs and step results survive server restarts. The in-memory cache holds up to 50 recent runs; older runs remain queryable from the database.

**Error messages**: Canvas translates raw errors into actionable messages. If the target agent exists in a different directory, it reports the name conflict and suggests changing the target or stopping the remote agent. If the agent is simply not found, it suggests starting the agent or enabling `auto_spawn`.

See [Workflows](workflow.md) for the full workflow configuration guide, and [Workflow API](../reference/api.md#workflow-api) for endpoint details.
