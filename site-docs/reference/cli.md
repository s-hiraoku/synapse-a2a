# CLI Commands

Complete reference for all Synapse A2A CLI commands.

## Agent Startup

### Profile Shortcuts

```bash
synapse claude [OPTIONS]     # Start Claude Code
synapse gemini [OPTIONS]     # Start Gemini CLI
synapse codex [OPTIONS]      # Start Codex CLI
synapse opencode [OPTIONS]   # Start OpenCode
synapse copilot [OPTIONS]    # Start GitHub Copilot CLI
```

**Options:**

| Flag | Description |
|------|-------------|
| `--name NAME` | Custom agent name |
| `--role ROLE` | Agent role description (use `@path` to read from file, e.g., `@./roles/reviewer.md`) |
| `--skill-set SET` | Activate skill set |
| `--agent ID_OR_NAME`, `-A` | Use a [saved agent definition](#saved-agent-definitions) (resolves name, role, skill set) |
| `--no-setup` | Skip interactive setup |
| `-- --resume` / `-- --continue` | Pass resume flags to agents that support flag-based resume, such as Claude Code and Gemini CLI (skips initial instructions). Codex uses the `resume` subcommand form instead. When a Synapse MCP server config is detected, Synapse sends a minimal PTY bootstrap instead of the full payload (approval prompts still apply unless resuming) |

Codex resume examples:

```bash
synapse codex -- resume --last
synapse codex -- resume <sessionId>
```
| `--delegate-mode` | Start as manager/delegator (no file editing) |
| `--port PORT` | Override default port |
| `--worktree [NAME]`, `-w` | Create git worktree for isolated work (optional name) |
| `--branch BRANCH`, `-b` | Base branch for worktree creation (implies `--worktree`) |

!!! tip "Using Saved Agent Definitions at Startup"
    The `--agent` / `-A` flag resolves a saved agent definition by ID or display name:
    ```bash
    synapse claude --agent calm-lead        # By saved agent ID
    synapse claude -A Claud                       # By saved agent display name
    synapse claude --agent calm-lead --role "override"  # CLI flags override saved values
    ```
    The saved agent's profile must match the shortcut profile (e.g., a `gemini` saved agent cannot be used with `synapse claude`). See [Saved Agent Definitions](../guide/agent-teams.md#saved-agent-definitions) for details.

### Background Start

```bash
synapse start <profile> [--port PORT] [-f] [--ssl-cert CERT] [--ssl-key KEY]
```

| Flag | Description |
|------|-------------|
| `--port PORT` | Explicit port number |
| `-f`, `--foreground` | Foreground mode (don't detach) |
| `--ssl-cert CERT` | SSL certificate file for HTTPS |
| `--ssl-key KEY` | SSL private key file for HTTPS |

### Stop

```bash
synapse stop <target>        # Stop specific agent
synapse stop <target> -a     # Stop all instances of that profile
```

## Agent Management

### List

```bash
synapse list                 # Interactive TUI with real-time updates
synapse list --plain         # One-shot plain text (no TUI)
synapse list --json          # Output agent list as JSON array
```

Interactive TUI with real-time updates. See [Agent Management](../guide/agent-management.md) for controls.

| Flag | Description |
|------|-------------|
| `--json` | Output agent list as a JSON array for AI/programmatic consumption (no TUI) |
| `--plain` | Force one-shot plain-text output without entering the Rich TUI |

For AI-controlled terminals, do not use bare `synapse list`. Use `synapse list --json`, `synapse list --plain`, `synapse status <target> --json`, or the MCP `list_agents` tool.

### Status

```bash
synapse status <target>            # Show detailed agent status
synapse status <target> --json     # Output as JSON
```

Shows a comprehensive view of a single agent including metadata, uptime, current task with elapsed time, recent message history, and file locks. See [Agent Management — Detailed Status](../guide/agent-management.md#detailed-status) for more.

| Flag | Description |
|------|-------------|
| `<target>` | Agent name, ID, type-port, or type |
| `--json` | Output as JSON (machine-readable) |

### Kill

```bash
synapse kill <target>        # Graceful shutdown (30s timeout)
synapse kill <target> -f     # Force kill (immediate SIGKILL)
```

### Merge

```bash
synapse merge <agent>        # Merge a worktree agent's branch into the current branch
synapse merge --all          # Merge all worktree agent branches
```

Merges worktree agent branches into the current branch. The agent must have a worktree branch (created via `--worktree` at spawn time). This is the same merge logic used by `synapse kill` auto-merge, but can be run independently while the agent is still alive or after it has exited.

| Flag | Description |
|------|-------------|
| `<agent>` | Target agent (name, ID, type-port, or type) |
| `--all` | Merge all live worktree agent branches in the current repo |
| `--dry-run` | Preview the merge without making changes |
| `--resolve-with <agent>` | Delegate conflict resolution to the specified agent (cannot be used with `--all`) |

!!! tip "Conflict resolution"
    When `--resolve-with` is specified and the merge encounters conflicts, Synapse sends the conflict details to the resolver agent via A2A, waits for the resolution, and completes the merge automatically.

### Jump

```bash
synapse jump <target>        # Jump to agent's terminal
```

### Rename

```bash
synapse rename <target> --name NAME [--role ROLE]
synapse rename <target> --clear    # Clear name and role
```

## Saved Agent Definitions

### List Saved Agents

```bash
synapse agents list
```

Displays a Rich TUI table in interactive terminals, plain text otherwise.

### Show Saved Agent

```bash
synapse agents show <id_or_name>
```

### Add Saved Agent

```bash
synapse agents add <id> --name NAME --profile PROFILE [OPTIONS]
```

| Flag | Description |
|------|-------------|
| `<id>` | Agent ID identifier (e.g. `sharp-checker`) |
| `--name NAME` | Display name (required) |
| `--profile PROFILE` | Agent profile: `claude`, `codex`, `gemini`, `opencode`, `copilot` (required) |
| `--role ROLE` | Role description or `@path` file reference |
| `--skill-set SET` / `-S SET` | Skill set name |
| `--scope SCOPE` | `project` (default) or `user` |

### Delete Saved Agent

```bash
synapse agents delete <id_or_name>
```

### Save Prompt on Interactive Exit

When an interactive `synapse <profile>` session exits (with a configured name),
Synapse can prompt to save the current agent definition:

```text
Save this agent definition for reuse? [y/N]:
```

- Not shown in `--headless` mode or non-TTY sessions.
- Not shown when stopping agents via `synapse stop ...` or `synapse kill ...`.
- Disable with `SYNAPSE_AGENT_SAVE_PROMPT_ENABLED=false`.

!!! tip "Using Saved Agents with Spawn"
    Once defined, saved agents can be spawned by ID or name:
    ```bash
    synapse spawn sharp-checker
    ```
    See [Saved Agent Definitions](../guide/agent-teams.md#saved-agent-definitions) for details.

## Communication

### Send

```bash
synapse send <target> "<message>" [OPTIONS]
```

| Flag | Description |
|------|-------------|
| `--from ID` / `-f ID` | Sender identification (optional — auto-detected from `$SYNAPSE_AGENT_ID`) |
| `--priority N` / `-p N` | Priority 1-5 (default: 3) |
| `--wait` | Wait for reply (synchronous blocking) |
| `--notify` | Return immediately, receive PTY notification on completion (**default**) |
| `--silent` | Fire-and-forget (no PTY notification; sender history updated via completion callback) |
| `--message-file PATH` | Read message from file (`-` for stdin) |
| `--stdin` | Read message from stdin |
| `--attach FILE` | Attach file (repeatable) |
| `--force` | Bypass working_dir mismatch check and skip PROCESSING wait |

**PROCESSING wait**: When the target agent's status is `PROCESSING`, `synapse send` automatically waits (polling every 1 second) for the agent to become `READY` before delivering the message. This prevents messages from being queued behind an in-progress task. The wait is skipped for `--silent` sends, priority-5 (critical) sends, and when `--force` is specified. The timeout is controlled by `SYNAPSE_SEND_WAIT_TIMEOUT` (default: 30 seconds).

!!! tip "Choosing response mode"
    - `--notify` (default): Returns immediately; you get a PTY notification when the receiver completes. Best for most use cases.
    - `--wait`: Blocks until the receiver replies. Use for questions or when you need the result before proceeding.
    - `--silent`: Fire-and-forget with no PTY notification. Use for pure notifications or delegated tasks; sender history is still updated best-effort on completion.

### Reply

```bash
synapse reply "<message>"                  # Reply to last sender
synapse reply "<message>" --to <sender>    # Reply to specific sender
synapse reply "<message>" --from ID        # With explicit sender ID
synapse reply --list-targets               # List pending senders
synapse reply --fail "reason"              # Send a failed reply
```

### Broadcast

```bash
synapse broadcast "<message>" [OPTIONS]
```

Same options as `send`, but default priority is **1** (not 3). Targets all agents in the current working directory.

### Interrupt

```bash
synapse interrupt <target> "<message>" [--from ID] [--force]
```

Shorthand for `synapse send -p 4 --silent`.

## Team Operations

### Team Start

```bash
synapse team start <profiles...> [OPTIONS] [-- TOOL_ARGS]
```

| Flag | Description |
|------|-------------|
| `--layout LAYOUT` | `split`, `horizontal`, or `vertical` |
| `--all-new` | All agents in new panes |
| `--worktree [NAME]`, `-w` | Create per-agent git worktrees for isolation (**default: enabled**) |
| `--no-worktree` | Opt out of worktree isolation |
| `--branch BRANCH`, `-b` | Base branch for worktree creation |

**Profile spec format**: `profile[:name[:role[:skill_set[:port]]]]`

!!! note
    Ports are typically pre-allocated automatically by `team start` to avoid race conditions. You only need to specify a port explicitly if you want to override the default.

### Spawn

```bash
synapse spawn <profile_or_saved_agent> [OPTIONS] [-- TOOL_ARGS]
```

The `<profile_or_saved_agent>` argument accepts:

- A built-in profile name (`claude`, `gemini`, `codex`, `opencode`, `copilot`)
- A saved agent ID (Agent ID format, e.g. `sharp-checker`)
- A saved agent display name (e.g. a custom name set via `synapse agents add`)

When a saved agent is used, its profile, name, role, and skill set are resolved from the definition. CLI flags (`--name`, `--role`, etc.) override saved values.

| Flag | Description |
|------|-------------|
| `--port PORT` | Explicit port |
| `--name NAME` | Agent name |
| `--role ROLE` | Agent role (supports `@path` file reference) |
| `--terminal TERM` | Terminal app override |
| `--task MESSAGE` | Send a task message after the spawned agent becomes ready |
| `--task-file PATH` | Read the task message from a file (`-` for stdin). Mutually exclusive with `--task` |
| `--task-timeout SECONDS` | Seconds to wait for the spawned agent before sending the task (default: 30) |
| `--wait` | Wait synchronously for the task response (blocks until done) |
| `--notify` | Return immediately, receive PTY notification on task completion |
| `--silent` | Fire-and-forget (no notification) |
| `--worktree [NAME]`, `-w` | Create git worktree for isolated work |
| `--branch BRANCH`, `-b` | Base branch for worktree creation (implies `--worktree`) |

## Session Save/Restore

### Save Session

```bash
synapse session save <name> [--project | --user | --workdir DIR]
```

Saves running agents in the current working directory as a named snapshot.

| Flag | Description |
|------|-------------|
| `--project` | Project scope (default): `.synapse/sessions/` |
| `--user` | User scope: `~/.synapse/sessions/` |
| `--workdir DIR` | Use project scope rooted at `DIR` (`DIR/.synapse/sessions/`) |

### List Sessions

```bash
synapse session list [--project | --user | --workdir DIR]
```

### Show Session

```bash
synapse session show <name> [--project | --user | --workdir DIR]
```

### Restore Session

```bash
synapse session restore <name> [--project | --user | --workdir DIR] [--worktree [NAME]] [--resume] [-- TOOL_ARGS]
```

Spawns all agents from the saved session.

| Flag | Description |
|------|-------------|
| `--worktree [NAME]`, `-w` | Create per-agent git worktrees (overrides saved settings) |
| `--resume` | Resume each agent's previous CLI conversation session (uses saved session_id when available, falls back to latest) |
| `-- TOOL_ARGS` | Pass CLI-specific arguments to spawned agents |

### Delete Session

```bash
synapse session delete <name> [--project | --user | --workdir DIR] [--force]
```

| Flag | Description |
|------|-------------|
| `--force`, `-f` | Delete without confirmation prompt |

### Browse CLI Sessions

```bash
synapse session sessions [--profile PROFILE] [--limit N]
```

Lists CLI tool session files from the filesystem (Claude, Gemini, Codex, Copilot). Sessions are sorted by modification time, newest first.

| Flag | Description |
|------|-------------|
| `--profile PROFILE` | Filter by CLI tool: `claude`, `gemini`, `codex`, `copilot` |
| `--limit N` | Maximum number of sessions to show (default: 20) |

## History

```bash
synapse history list [--agent AGENT] [--limit N]
synapse history show <task_id>
synapse history search "<query>" [--agent AGENT] [--logic AND|OR] [--case-sensitive]
synapse history stats [--agent AGENT]
synapse history export [--format json|csv] [--agent AGENT] [--limit N] [--output PATH]
synapse history cleanup [--days N] [--max-size MB] [--no-vacuum] [--dry-run] [--force]
```

## Shared Memory

```bash
synapse memory save <key> "<content>" [--tags tag1,tag2] [--scope global|project|private] [--notify]
synapse memory list [--author <id>] [--tags <tags>] [--scope global|project|private] [--limit N]
synapse memory show <id_or_key>
synapse memory search "<query>" [--scope global|project|private]
synapse memory delete <id_or_key> [--force]
synapse memory stats
```

Memory scopes control visibility: `global` (default, all agents everywhere), `project` (same working directory only), `private` (saving agent only). See [Shared Memory](../guide/shared-memory.md#memory-scopes) for details.

## Tracing

```bash
synapse trace <task_id>
```

## File Safety

```bash
synapse file-safety status
synapse file-safety locks [--file PATH] [--agent AGENT]
synapse file-safety lock <file> <agent> [--intent "..."] [--duration N]
synapse file-safety unlock <file> <agent> [--force]
synapse file-safety history <file> [--limit N]
synapse file-safety recent [--agent AGENT] [--limit N]
synapse file-safety record <file> <agent> <task_id> --type CREATE|MODIFY|DELETE [--intent "..."]
synapse file-safety cleanup --days N [--force]
synapse file-safety cleanup-locks [--force]
synapse file-safety debug
```

## Instructions

```bash
synapse instructions show [agent]              # View instruction content
synapse instructions files <agent>             # List instruction files
synapse instructions send <agent> [--preview]  # Send to running agent
```

## Skills

```bash
synapse skills                                 # Interactive TUI
synapse skills list [--scope SCOPE]
synapse skills show <name> [--scope SCOPE]
synapse skills delete <name> [--force] [--scope SCOPE]
synapse skills move <name> --to <scope>
synapse skills deploy <name> --agent <types> [--scope SCOPE]
synapse skills import <name> [--from SCOPE]
synapse skills add <repo>
synapse skills create [name]                   # Create new skill template
synapse skills set list
synapse skills set show <name>
synapse skills apply <target> <set_name> [--dry-run]
```

### Apply Skill Set

Apply a skill set to a running agent. Copies skill files to the agent's skill directory, updates the registry, and sends skill set info via A2A.

```bash
synapse skills apply <target> <set_name> [--dry-run]
```

| Flag | Description |
|------|-------------|
| `<target>` | Agent name, ID, type-port, or type |
| `<set_name>` | Skill set name (e.g., `manager`, `developer`, `reviewer`) |
| `--dry-run` | Preview changes without applying |

## Workflows

### Create Workflow

```bash
synapse workflow create <name> [--project | --user] [--force]
```

Creates a template YAML file for a new workflow.

| Flag | Description |
|------|-------------|
| `--project` | Project scope (default): `.synapse/workflows/` |
| `--user` | User scope: `~/.synapse/workflows/` |
| `--force` | Overwrite existing workflow |

### List Workflows

```bash
synapse workflow list [--project | --user]
```

### Show Workflow

```bash
synapse workflow show <name> [--project | --user]
```

### Run Workflow

```bash
synapse workflow run <name> [--project | --user] [--dry-run] [--continue-on-error] [--auto-spawn]
```

Executes workflow steps sequentially, sending A2A requests directly to target agents. Steps with `response_mode: wait` poll for task completion before proceeding to the next step.
If a step is `kind: subworkflow`, the child workflow is expanded inline. Cycles are rejected and nesting depth is limited to 10.

| Flag | Description |
|------|-------------|
| `--dry-run` | Preview steps without sending messages |
| `--continue-on-error` | Continue executing remaining steps after a failure |
| `--auto-spawn` | Auto-spawn agents that are not running (target is used as profile name) |

### Delete Workflow

```bash
synapse workflow delete <name> [--project | --user] [--force]
```

| Flag | Description |
|------|-------------|
| `--force`, `-f` | Delete without confirmation prompt |

### Sync Workflows to Skills

```bash
synapse workflow sync
```

Auto-generates `SKILL.md` files from all workflow YAML definitions into `.claude/skills/` and `.agents/skills/`. Removes orphaned auto-generated skills whose workflow YAML no longer exists. Hand-written skills are never overwritten.

## Settings

```bash
synapse init [--scope user|project]
synapse config
synapse config show [--scope SCOPE]
synapse reset [--scope user|project|both] [-f]
```

`synapse init` uses a merge strategy: template files are updated, and `settings.json` is **smart-merged** (new keys added, your customized values preserved). User-generated data (agents, databases, sessions, workflows, worktrees) is preserved. Safe to re-run after upgrades.

`synapse config` opens the interactive editor and shows effective values with their sources, using precedence in this order: `os.environ > local > project > user > default`. The editor writes changes to the scope that currently provides the effective value. Settings overridden by `os.environ` are shown as read-only. Use `synapse config show --scope user|project|merged` for explicit read-only scope views.

## External Agents

```bash
synapse external add <url> [--alias NAME]
synapse external list
synapse external info <alias>
synapse external send <alias> "<message>" [--wait]
synapse external remove <alias>
```

## Authentication

```bash
synapse auth setup                             # Generate keys + instructions
synapse auth generate-key [-n COUNT] [-e]      # Generate key(s)
```

## Canvas

### Serve

```bash
synapse canvas serve [--port PORT] [--no-open]
```

Starts the Canvas server and opens the browser. The server auto-starts in the background when you post your first card, so explicit `serve` is optional.

| Flag | Description |
|------|-------------|
| `--port PORT` | Canvas server port (default: 3000) |
| `--no-open` | Don't open browser automatically |

### Post (Format Shortcuts)

```bash
synapse canvas post <format> "<body>" [OPTIONS]
```

| Format | Body | Description |
|--------|------|-------------|
| `mermaid` | Mermaid source | Flowcharts, sequence diagrams |
| `markdown` | Markdown text | Formatted documents |
| `table` | `{headers, rows}` JSON | Structured data |
| `html` | Raw HTML | Full freedom (sandboxed iframe) |
| `artifact` | Full HTML document | Interactive HTML/JS/CSS application (sandboxed iframe) |
| `code` | Source code | Syntax-highlighted code |
| `diff` | Unified diff | Side-by-side diff view |
| `chart` | Chart.js config JSON | All chart types |
| `image` | URL or base64 data URI | Screenshots, SVG diagrams |
| `progress` | `{current, total, label, steps, status}` JSON | Progress bar with steps |
| `terminal` | Plain text (ANSI supported) | Terminal output with ANSI colors |
| `dependency-graph` | `{nodes, edges}` JSON | Dependency graph (rendered as Mermaid subgraph) |
| `cost` | `{agents, total_cost, currency}` JSON | Token/cost aggregation table |
| `link-preview` | URL string | Rich link preview with OGP metadata |

For structured cards or any block metadata such as `x_title` / `x_filename`, use `synapse canvas post-raw` with a full Canvas Message JSON payload. This is the preferred path for structured cards that should preserve typed `body` data instead of sending a plain string.

**Common options** (all posting commands):

| Flag | Description |
|------|-------------|
| `--title TITLE` | Card title |
| `--id ID` | Stable card ID for upsert (auto-generated if omitted) |
| `--pin` | Pin card (exempt from TTL expiry) |
| `--tag TAG` | Tag for filtering (repeatable) |
| `--file PATH` | Read body from file instead of argument |
| `--lang LANG` | Language hint (for `code` format) |

### Post Raw

```bash
synapse canvas post-raw '<Canvas Message JSON>'
```

Post a full Canvas Message Protocol JSON payload. Supports composite cards (multiple content blocks), templates, and all protocol fields.

### Link Preview

```bash
synapse canvas link "<url>" [OPTIONS]
```

Posts a link preview card with OGP metadata. The server fetches Open Graph metadata from the URL using streaming reads and renders a rich link card. Only `http://` and `https://` URLs are accepted; private/loopback addresses are rejected (SSRF protection), and redirect targets are validated at each hop. Multiple link-preview blocks in a composite card are fetched in parallel.

The enriched body uses `og_`-prefixed field names (`og_title`, `og_description`, `og_image`, `og_site_name`). The renderer also accepts plain aliases (`title`, `description`, `image`, `site_name`) for non-OGP payloads.

| Flag | Description |
|------|-------------|
| `--title TITLE` | Card title (overrides OGP title) |
| `--id ID` | Stable card ID for upsert |
| `--pin` | Pin card |
| `--tag TAG` | Tag for filtering (repeatable) |

### Plan

```bash
synapse canvas plan '<JSON>' [OPTIONS]
synapse canvas plan --file plan.json [OPTIONS]
```

Shortcut for posting a `plan` template card with Mermaid DAG and step list.

| Flag | Description |
|------|-------------|
| `--title TITLE` | Card title |
| `--file PATH` | Read plan JSON from file |
| `--card-id ID` | Card ID for upsert (defaults to `plan_id`) |
| `--agent-id ID` | Agent ID |
| `--agent-name NAME` | Agent display name |
| `--pin` | Pin card (default: pinned) |
| `--tag TAG` | Tag for filtering (repeatable) |

### Briefing

```bash
synapse canvas briefing '<JSON>' [OPTIONS]
synapse canvas briefing --file report.json [OPTIONS]
```

Shortcut for posting a `briefing` template card with structured sections.

| Flag | Description |
|------|-------------|
| `--title TITLE` | Card title (overrides JSON `title`) |
| `--summary TEXT` | Executive summary (overrides JSON `summary`) |
| `--file PATH` | Read briefing JSON from file |
| `--pin` | Pin card |
| `--tag TAG` | Tag for filtering (repeatable) |

### List

```bash
synapse canvas list [OPTIONS]
```

| Flag | Description |
|------|-------------|
| `--mine` | Show own cards only (filtered by `$SYNAPSE_AGENT_ID`) |
| `--search QUERY` | Filter by title |
| `--type FORMAT` | Filter by content format |
| `--agent-id ID` | Filter by agent ID |

### Delete / Clear

```bash
synapse canvas delete <card_id>            # Delete a single card
synapse canvas clear                       # Clear all cards
synapse canvas clear --agent <agent_id>    # Clear specific agent's cards
```

### Open

```bash
synapse canvas open [--port PORT]
```

Opens the Canvas UI in the default browser. If the server is not running, it is started automatically before opening.

| Flag | Description |
|------|-------------|
| `--port PORT` | Canvas server port (default: 3000) |

### Status

```bash
synapse canvas status [--port PORT]
```

Shows Canvas server status including URL, running state, PID (with alive/dead indicator), port, version, card count, asset hash, hash match indicator, and log file path. Detects PID mismatches between the PID file (`~/.synapse/canvas.pid`) and the `/api/health` endpoint. When the server's `asset_hash` differs from the local assets, a **STALE** warning is displayed, indicating the server should be restarted to pick up updated frontend assets.

| Flag | Description |
|------|-------------|
| `--port PORT` | Canvas server port to check (default: 3000) |

### Stop

```bash
synapse canvas stop [--port PORT]
```

Stops the Canvas server. Detection uses the `/api/health` endpoint first (verifying `"service": "synapse-canvas"` identity), falling back to the PID file (`~/.synapse/canvas.pid`) if the health endpoint is unreachable. Before sending SIGTERM, the command verifies that the target PID is actually a Canvas process to avoid killing unrelated processes. If the process does not exit within the grace period after SIGTERM, a SIGKILL is sent as a fallback to ensure cleanup.

| Flag | Description |
|------|-------------|
| `--port PORT`, `-p PORT` | Canvas server port to stop (default: 3000) |

## Logs

```bash
synapse logs <agent> [-f] [-n LINES]
```

## MCP Server (Experimental)

```bash
synapse mcp serve [OPTIONS]
```

Serves Synapse bootstrap resources (instructions, skills) over MCP stdio transport. Intended for MCP-aware clients that can consume Synapse context as MCP resources.

| Flag | Description |
|------|-------------|
| `--agent-id ID` | Agent ID for instruction resolution (default: `$SYNAPSE_AGENT_ID` or `synapse-mcp`) |
| `--agent-type TYPE` | Agent type for instruction resolution (inferred from agent ID if omitted) |
| `--port PORT` | Port for instruction placeholder resolution |

MCP tools exposed: `bootstrap_agent`, `list_agents`, `analyze_task`. The `analyze_task` tool returns a `recommended_worktree` field indicating whether worktree isolation is advisable for the given task. See [MCP Bootstrap Setup](../guide/mcp-setup.md#mcp-tools) for tool documentation.

!!! warning "Experimental"
    This command is in early development (Phase 1). The interface may change in future releases.

## Self-Learning Pipeline

### Learn

```bash
synapse learn
```

Analyzes PTY observations from the current project and extracts atomic instincts (trigger + action pairs with confidence scores). See [Self-Learning Pipeline](../guide/self-learning.md) for details.

### Instinct

```bash
synapse instinct [--scope SCOPE] [--domain DOMAIN]         # List instincts with filters
synapse instinct promote <id>                              # Promote to global scope
synapse instinct export                                    # Export instincts
synapse instinct import <file>                             # Import instincts
```

| Flag | Description |
|------|-------------|
| `--scope SCOPE` | Filter by `project` or `global` |
| `--domain DOMAIN` | Filter by domain |
| `--min-confidence N` | Minimum confidence threshold |
| `--limit N` | Maximum results (default: 50) |

### Evolve

```bash
synapse evolve                    # Discover skill/command candidates from instincts
synapse evolve --generate         # Auto-generate skill .md files
```

| Flag | Description |
|------|-------------|
| `--generate` | Generate `.md` skill files from candidates |
| `--output-dir DIR` | Output directory for generated files |

## Low-Level A2A Tool

```bash
python -m synapse.tools.a2a list [--live]
python -m synapse.tools.a2a send --target <agent> --priority N "<message>"
python -m synapse.tools.a2a broadcast "<message>"
python -m synapse.tools.a2a cleanup
```
