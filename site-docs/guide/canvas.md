# Canvas

## Overview

Synapse Canvas is a shared visual output surface for agents. When an agent needs to express something beyond text — diagrams, rich tables, interactive charts, design mockups — it sends a **Canvas Message** via a unified protocol. A local web server renders the content in the browser in real-time.

### Design Principles

1. **Agent-driven**: Canvas is the agent's drawing board — agents decide what to show.
2. **Protocol-first**: One unified JSON protocol for all communication. No type-specific CLI commands.
3. **Expressive**: Agents can render anything — from Mermaid diagrams to raw HTML/CSS.
4. **Dead simple for agents**: One command, one JSON payload. That's it.
5. **Zero-config for users**: `synapse canvas` starts the server. No npm, no build step.

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

# Code with syntax highlighting
synapse canvas code "def foo(): pass" --lang python --title "Impl"

# Unified diff
synapse canvas diff "--- a/f.py\n+++ b/f.py\n..." --title "Changes"

# Chart.js chart
synapse canvas chart '{"type":"bar","data":{...}}' --title "Coverage"

# Image (URL or base64 data URI)
synapse canvas image "https://..." --title "Screenshot"
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

The `content.format` field determines how `content.body` is rendered. New formats can be added without protocol changes.

| Format | Body | Renderer | Use Case |
|---|---|---|---|
| `mermaid` | Mermaid source | mermaid.js | Flowcharts, sequence diagrams, ER diagrams |
| `markdown` | Markdown text | marked.js + Highlight.js | Design docs, explanations, formatted text |
| `html` | Raw HTML string | Sandboxed iframe (fills Canvas view) | Full freedom — any visual expression |
| `table` | `{headers, rows}` | Native HTML | Structured data, test results, comparisons |
| `json` | Any JSON | Collapsible tree viewer | API responses, config, data structures |
| `diff` | Unified diff | Side-by-side diff renderer | Code changes, before/after comparisons |
| `chart` | Chart.js config | Chart.js | All chart types: bar, line, pie, doughnut, radar, polarArea, scatter, bubble |
| `image` | Base64 data URI or URL | `<img>` | Screenshots, generated images |
| `code` | Source code + `lang` | Highlight.js | Syntax-highlighted code blocks |
| `log` | `[{level, ts, msg}]` | Agent logs | Agent logs with INFO/WARN/ERROR color coding |
| `status` | `{state, label, detail}` | Status badge | Build/task status with colored badge |
| `metric` | `{value, unit, label}` | Single KPI | Single KPI display (large number) |
| `checklist` | `[{text, checked}]` | Checklist | Task progress with checkboxes |
| `timeline` | `[{ts, event, agent}]` | Timeline | Time-series events, task progression |
| `alert` | `{severity, message, source}` | Alert notification | Persistent important notifications |
| `file-preview` | `{path, lang, snippet, start_line}` | Code preview | Code snippet with file path and line numbers |
| `trace` | `[{name, duration_ms, status, children?}]` | A2A trace | A2A routing spans with duration bars |
| `task-board` | `{columns: [...]}` | Kanban board | Kanban board view |

!!! tip "The `html` Escape Hatch"
    When no predefined format fits, agents can send raw HTML via the `html` format. This makes expression essentially unlimited, though HTML content is rendered in a sandboxed `<iframe>` for safety. In the Canvas view (`#/`), the iframe fills the entire content area for immersive display. In the Dashboard view (`#/dashboard`), the iframe auto-resizes to fit its content.

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

This enables agents to compose rich, multi-section cards — like a document with embedded diagrams and tables. Maximum 10 content blocks per card.

## CLI Commands

### Posting (Full Control)

```bash
synapse canvas post '<Canvas Message JSON>'
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
synapse canvas post task-board '{"columns":[{"name":"Todo","items":[{"id":"1","subject":"Review"}]}]}' --title "Board"
```

## Server Auto-Start

Canvas commands automatically start the server if it is not running. The flow for all posting commands:

1. Check `GET http://localhost:{port}/api/health`
2. If `200 OK` — server is running, proceed to post
3. If connection refused — start server in background, retry health check (max 3s, 500ms interval), then post

A PID file (`.synapse/canvas.pid`) prevents multiple server instances.

## HTTP API

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/cards` | Create/update card (Canvas Message Protocol) |
| `GET` | `/api/cards` | List cards (optional `?agent_id=`, `?search=`, `?type=` filters) |
| `GET` | `/api/cards/{id}` | Get single card |
| `DELETE` | `/api/cards/{id}` | Delete card (own cards only) |
| `DELETE` | `/api/cards` | Clear all cards (optional `?agent_id=` filter) |
| `GET` | `/api/stream` | SSE stream (card events) |
| `GET` | `/api/formats` | List supported formats |
| `GET` | `/api/health` | Health check |
| `GET` | `/api/system` | System panel data (agents, tasks, file locks) |

## System Panel

The Canvas browser UI includes a **System Panel** at the top that shows real-time system state:

| Section | Data Source | Shows |
|---|---|---|
| **Agents** | `~/.a2a/registry/*.json` | Agent name, type, status with colored dots |
| **Tasks** | `.synapse/task_board.db` | Pending/in-progress/completed in kanban columns |
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

## Configuration

| Variable | Default | Description |
|---|---|---|
| `SYNAPSE_CANVAS_PORT` | `3000` | Canvas server port |
| `SYNAPSE_CANVAS_DB_PATH` | `.synapse/canvas.db` | Database path |
| `SYNAPSE_CANVAS_ENABLED` | `true` | Enable/disable Canvas |

Internal limits:

| Setting | Value |
|---|---|
| Max content size | 500KB per content block |
| Max blocks per card | 10 |
| Max cards | 200 (auto-cleanup threshold) |
| Notification TTL | 10 seconds |
| Card TTL | 3600 seconds (1 hour) |

## Browser UI

Open `http://localhost:3000` to view the Canvas.

The Canvas UI uses **SPA hash routing** with two views:

| Route | View | Purpose |
|---|---|---|
| `#/` | **Canvas** (default) | Full-viewport display of the latest card |
| `#/dashboard` | **Dashboard** | Card grid with system panel, live feed, and filters |

### Canvas View (`#/`)

The Canvas view is a **full-viewport projection** of the most recently updated card. It is designed for ambient display — put it on a secondary monitor or share-screen during pairing.

- The latest card fills the entire content area
- A **title bar** at the top shows the card title
- A **floating info bar** at the bottom shows agent name, status dot, tags, timestamp, and card ID
- An **ambient glow** border reflects the posting agent's status color (green=READY, yellow=PROCESSING, etc.)
- HTML cards render inside a sandboxed `<iframe>` that fills the full content area (no auto-resize — uses CSS flex)
- Filter controls are hidden in this view

### Dashboard View (`#/dashboard`)

The Dashboard view shows the traditional card grid alongside system state.

**Features:**

- **System Panel**: Real-time agents, tasks, and file locks (see [System Panel](#system-panel))
- **Live Feed**: Chronological event stream with pulsing dot indicator
- **Card Grid**: All cards in a responsive grid layout
- **Filter bar**: Filter by format type and by agent
- **Dark/light theme**: Follows `prefers-color-scheme` with manual toggle
- **Toast notifications**: `notify` type shows ephemeral messages
- **Agent badges**: Each card shows agent name, type icon/color, and relative timestamp
- **Pin/delete controls**: Pin icon and X button on card headers
