# CLI Cheatsheet

Quick reference for the most commonly used Synapse A2A commands. For full details on every flag and option, see the [CLI Commands](cli.md) reference.

## Quick Reference

### Agent Lifecycle

| Command | Description |
|---------|-------------|
| `synapse claude` | Start Claude Code interactively |
| `synapse gemini` | Start Gemini CLI interactively |
| `synapse codex` | Start Codex CLI interactively |
| `synapse opencode` | Start OpenCode interactively |
| `synapse copilot` | Start GitHub Copilot CLI interactively |
| `synapse list` | Live TUI showing all running agents |
| `synapse list --json` | Output agent list as JSON array |
| `synapse status <target>` | Detailed status for a single agent |
| `synapse kill <target>` | Graceful shutdown (30 s timeout) |
| `synapse kill <target> -f` | Force kill (immediate SIGKILL) |
| `synapse merge <agent>` | Merge worktree agent branch into current branch |
| `synapse merge --all` | Merge all worktree agent branches |
| `synapse worktree prune` | Remove orphan worktrees (missing directories) |
| `synapse jump <target>` | Jump to agent terminal |

### Communication

| Command | Description |
|---------|-------------|
| `synapse send <target> "msg"` | Send message (default `--notify`) |
| `synapse send <target> "msg" --wait` | Send and wait for reply |
| `synapse send <target> "msg" --silent` | Fire-and-forget |
| `synapse reply "msg"` | Reply to sender |
| `synapse broadcast "msg"` | Send to all agents in current directory |
| `synapse interrupt <target> "msg"` | Soft interrupt (priority 4) |

### Skills

| Command | Description |
|---------|-------------|
| `synapse skills` | Interactive TUI skill manager |
| `synapse skills list` | List all discovered skills |
| `synapse skills show <name>` | Show skill details |
| `synapse skills deploy <name> --agent claude` | Deploy skill to agent |
| `synapse skills import <name>` | Import to central store |
| `synapse skills set list` | List skill sets |
| `synapse skills apply <target> <set>` | Apply skill set to agent |

### Memory

| Command | Description |
|---------|-------------|
| `synapse memory save <key> <content> [--scope SCOPE]` | Save a memory entry |
| `synapse memory list [--scope SCOPE]` | List entries |
| `synapse memory show <id_or_key>` | Show entry |
| `synapse memory search <query> [--scope SCOPE]` | Search entries |
| `synapse memory delete <id_or_key>` | Delete entry |
| `synapse memory stats` | Show statistics |

### Session & Restore

| Command | Description |
|---------|-------------|
| `synapse session save <name>` | Save session snapshot |
| `synapse session list` | List saved sessions |
| `synapse session restore <name>` | Restore session |
| `synapse session delete <name>` | Delete session |
| `synapse session sessions` | List CLI tool sessions from filesystem |

### Workflow

| Command | Description |
|---------|-------------|
| `synapse workflow create <name>` | Create workflow template YAML |
| `synapse workflow list` | List saved workflows |
| `synapse workflow show <name>` | Show workflow details |
| `synapse workflow run <name>` | Execute workflow steps |
| `synapse workflow run <name> --auto-spawn` | Execute with auto-spawn for missing agents |
| `synapse workflow run <name> --async` | Run in background (returns run ID) |
| `synapse workflow status <run_id>` | Check background workflow run status |
| `synapse workflow sync` | Sync workflow YAMLs to skill directories |
| `synapse workflow delete <name>` | Delete a workflow |

### Canvas

| Command | Description |
|---------|-------------|
| `synapse canvas serve` | Start Canvas server |
| `synapse canvas post mermaid "..." --title T` | Post Mermaid diagram |
| `synapse canvas post markdown "..." --title T` | Post Markdown document |
| `synapse canvas post table '{...}' --title T` | Post data table |
| `synapse canvas post code "..." --lang py` | Post syntax-highlighted code |
| `synapse canvas post chart '{...}' --title T` | Post Chart.js chart |
| `synapse canvas link "https://..." --title T` | Post link preview with OGP metadata |
| `synapse canvas post-raw '{raw JSON}'` | Post raw Canvas Message JSON |
| `synapse canvas briefing '{...}'` | Post structured briefing report |
| `synapse canvas plan '{...}'` | Post execution plan (Mermaid DAG + steps) |
| `synapse canvas list` | List all cards |
| `synapse canvas delete <id>` | Delete a card |
| `synapse canvas clear` | Clear all cards |
| `synapse canvas open` | Open Canvas in browser |
| `synapse canvas status` | Show server status (PID, version, cards, asset staleness) |
| `synapse canvas stop` | Stop Canvas server |

### Self-Learning

| Command | Description |
|---------|-------------|
| `synapse learn` | Extract instincts from PTY observations |
| `synapse instinct status` | Show instincts by confidence |
| `synapse instinct list` | List instincts (filterable) |
| `synapse instinct promote <id>` | Promote instinct to global scope |
| `synapse evolve` | Discover skill candidates from instincts |
| `synapse evolve --generate` | Auto-generate skill files |

### Configuration

| Command | Description |
|---------|-------------|
| `synapse config` | Interactive config editor |
| `synapse config show` | Show merged settings (read-only) |
| `synapse init` | Initialize configuration |
| `synapse reset` | Reset settings to defaults |
| `synapse auth setup` | Generate API keys |

---

## Agent Lifecycle

### Starting Agents

```bash
# Basic startup
synapse claude
synapse gemini

# With name and role
synapse claude --name my-claude --role "code reviewer"

# Role from file (@prefix reads file contents)
synapse claude --role "@./roles/reviewer.md"

# With saved agent definition
synapse claude --agent calm-lead
synapse claude -A Claud

# Skip interactive setup
synapse claude --no-setup

# Delegate mode (manager, no file editing)
synapse claude --delegate-mode --name manager --role "coordinator"
```

!!! tip "Resume an existing CLI session"
    Pass `--resume` or `--continue` after `--` to skip Synapse initial instructions:
    ```bash
    synapse claude -- --resume
    synapse claude -- --continue
    ```

### Monitoring and Managing

```bash
# Live agent dashboard (auto-refreshes)
synapse list

# JSON output for AI/scripts
synapse list --json

# Detailed status for a single agent (uptime, current task, history, locks)
synapse status my-claude
synapse status my-claude --json    # Machine-readable JSON output

# Jump to an agent's terminal
synapse jump my-claude

# Rename / update role
synapse rename claude --name my-claude
synapse rename my-claude --role reviewer

# Kill agent
synapse kill my-claude        # Graceful (30 s)
synapse kill my-claude -f     # Force
```

### Spawning in New Panes

```bash
# Spawn in a new terminal pane
synapse spawn claude
synapse spawn gemini --name Helper --role "search specialist"

# Spawn and send a task immediately (waits for agent to be ready)
synapse spawn claude --name Reviewer --task "Review src/auth.py for security issues" --notify

# Recommended: use --task-file for complex instructions, --task-timeout for slow startups
synapse spawn codex --task-file /tmp/instructions.md --task-timeout 600 --notify

# With worktree isolation
synapse spawn claude --worktree feature-auth

# With worktree on a specific base branch (--branch implies --worktree)
synapse spawn codex --branch renovate/major-eslint-monorepo

# Pass tool-specific flags after '--'
synapse spawn claude -- --dangerously-skip-permissions
```

### Agent Teams

```bash
# Start a multi-agent team (worktree isolation is the default)
synapse team start claude gemini
synapse team start claude gemini codex --layout horizontal

# All agents in new panes (keep current terminal free)
synapse team start claude gemini --all-new

# Opt out of worktree isolation
synapse team start claude gemini --no-worktree

# With worktree on a specific base branch
synapse team start claude gemini --branch feature/api

# Extended spec  profile:Name:role:skill-set
synapse team start claude:Reviewer:reviewer:code-review gemini:Searcher
```

---

## Communication

### Sending Messages

```bash
# Default (--notify): async notification on completion
synapse send my-claude "Review this code"

# Wait for reply (blocking)
synapse send gemini "Analyze this" --wait

# Fire-and-forget
synapse send codex "Fix this bug and commit" --silent

# With priority (1-5)
synapse send gemini "Urgent check" --priority 4 --wait

# Attach files
synapse send claude "Review these" --attach src/a.py --attach src/b.py --wait

# Long messages via file or stdin
synapse send claude --message-file /tmp/review.txt --silent
echo "long message" | synapse send claude --stdin --silent
```

!!! info "Working Directory Check"
    `synapse send` warns if the sender's CWD differs from the target's `working_dir`. Use `--force` to bypass.

### Replying

```bash
# Auto-routes to the sender
synapse reply "Here are the results"

# Explicit sender ID (sandboxed environments)
synapse reply "Done" --from $SYNAPSE_AGENT_ID

# Reply to a specific sender
synapse reply "Done" --to synapse-claude-8100
```

### Broadcasting

```bash
synapse broadcast "Status check"
synapse broadcast "Urgent update" -p 4
synapse broadcast "FYI" --silent
```

### Soft Interrupt

```bash
synapse interrupt claude "Stop and review"
synapse interrupt gemini "Check status"
synapse interrupt claude "Stop" --force
```

---

## Target Resolution

When specifying a target for `send`, `kill`, `jump`, `rename`, `interrupt`, or `skills apply`, Synapse resolves in this order:

| Priority | Format | Example |
|----------|--------|---------|
| 1 (highest) | Custom name | `my-claude` |
| 2 | Full Runtime ID | `synapse-claude-8100` |
| 3 | Type-port shorthand | `claude-8100` |
| 4 (lowest) | Agent type (single instance only) | `claude` |

!!! warning "Agent type resolution"
    Using just the agent type (e.g., `claude`) only works when there is a single running instance of that type.

---

## History & Tracing

```bash
# List recent history
synapse history list
synapse history list --agent claude

# Show task details
synapse history show <task_id>

# Trace a task across history and file modifications
synapse trace <task_id>
```

---

## Skills Management

```bash
# Interactive TUI
synapse skills

# List and inspect
synapse skills list
synapse skills list --scope synapse
synapse skills show <name>

# Deploy and import
synapse skills deploy <name> --agent claude,codex --scope user
synapse skills import <name>

# Install from repository
synapse skills add <repo>

# Create new skill template
synapse skills create [name]

# Skill sets
synapse skills set list
synapse skills set show <name>
synapse skills apply <target> <set_name>
synapse skills apply <target> <set_name> --dry-run

# Move / delete
synapse skills move <name> --to <scope>
synapse skills delete <name> --force
```

---

## Shared Memory

!!! warning "Deprecated — use LLM Wiki"
    Shared Memory is deprecated. Prefer `synapse wiki` commands for new knowledge. See [LLM Wiki](../design/llm-wiki.md).

```bash
# Save with optional tags, scope, and notification
synapse memory save api-spec "REST API uses JWT auth" --tags api,auth --notify
synapse memory save repo-tip "Use uv" --scope project

# List and filter (scope: global|project|private)
synapse memory list
synapse memory list --scope project
synapse memory list --author synapse-claude-8100 --tags api --limit 10

# Show and search
synapse memory show api-spec
synapse memory search "authentication"
synapse memory search "auth" --scope project

# Delete
synapse memory delete api-spec --force

# Statistics
synapse memory stats
```

---

## Session Save/Restore

```bash
# Save current team session
synapse session save my-session
synapse session save my-session --project    # Project scope
synapse session save my-session --user       # User scope

# List and show
synapse session list
synapse session show my-session

# Restore
synapse session restore my-session
synapse session restore my-session --worktree --resume
synapse session restore my-session -- --dangerously-skip-permissions

# Delete
synapse session delete my-session --force

# List CLI tool sessions from filesystem
synapse session sessions
synapse session sessions --profile claude --limit 10
```

---

## Workflows

```bash
# Create workflow template (YAML)
synapse workflow create deploy-pipeline

# List and show
synapse workflow list
synapse workflow show deploy-pipeline

# Run
synapse workflow run deploy-pipeline
synapse workflow run deploy-pipeline --dry-run
synapse workflow run deploy-pipeline --continue-on-error
synapse workflow run deploy-pipeline --auto-spawn
synapse workflow run deploy-pipeline --async    # Background execution
synapse workflow status <run_id>                # Check background run status

# Sync workflows to skill directories
synapse workflow sync

# Delete
synapse workflow delete deploy-pipeline --force
```

---

## Canvas

```bash
# Start Canvas server (auto-starts on first post, so usually optional)
synapse canvas serve
synapse canvas serve --port 3001 --no-open

# Post content with format shortcuts
synapse canvas post mermaid "graph TD; A-->B; B-->C" --title "Auth Flow"
synapse canvas post markdown "## Design\nThis system uses..." --title "Design Doc"
synapse canvas post table '{"headers":["a","b"],"rows":[["1","2"]]}' --title "Results"
synapse canvas post code "def foo(): pass" --lang python --title "Impl"
synapse canvas post chart '{"type":"bar","data":{"labels":["Q1","Q2"],"datasets":[{"data":[10,20]}]}}' --title "Coverage"
synapse canvas post image "https://example.com/screenshot.png" --title "Screenshot"

# Post link preview (OGP metadata fetched server-side)
synapse canvas link "https://example.com/article" --title "Reference"

# Post a briefing (structured report with sections)
synapse canvas briefing '{"title":"Sprint Report","sections":[{"title":"Summary"}],"content":[{"format":"markdown","body":"All tasks done."}]}'
synapse canvas briefing --file report.json --title "Sprint Report" --summary "Executive summary"

# Post a plan card (Mermaid DAG + step list with status tracking)
synapse canvas plan '{"plan_id":"plan-auth","steps":[{"id":"s1","subject":"Design"},{"id":"s2","subject":"Implement","blocked_by":["s1"]}]}'
synapse canvas plan --file plan.json --title "Auth Plan"

# Post raw Canvas Message JSON (composite cards, templates)
synapse canvas post-raw '{"type":"render","content":[...],"template":"dashboard","template_data":{...}}'

# Common options (all posting commands)
synapse canvas post mermaid "..." --title "T" --card-id my-card --pinned --tags design,auth

# List and manage cards
synapse canvas list
synapse canvas list --mine --search "auth" --type mermaid
synapse canvas delete <card_id>
synapse canvas clear
synapse canvas clear --agent claude

# Server management
synapse canvas status                     # Show server status (PID, version, cards, asset staleness)
synapse canvas stop                       # Stop the Canvas server (SIGTERM with SIGKILL fallback)
```

!!! tip "Templates"
    Six built-in templates (`briefing`, `comparison`, `dashboard`, `steps`, `slides`, `plan`) add structured layouts on top of composite cards. The `briefing` and `plan` templates have dedicated CLI shortcuts; other templates are posted via `synapse canvas post` with `template` and `template_data` in the JSON payload. See the [Canvas Guide](../guide/canvas.md#templates) for template data schemas.

---

## Saved Agent Definitions

```bash
# List saved agents
synapse agents list

# Show details
synapse agents show calm-lead

# Add a new definition
synapse agents add calm-lead --name "Calm Lead" --profile claude \
  --role "Calm, methodical lead developer" --skill-set architect

# Delete
synapse agents delete calm-lead

# Use at startup
synapse claude --agent calm-lead
synapse claude -A "Calm Lead"
```

---

## Configuration

```bash
# Interactive config editor (shows effective values with sources)
synapse config

# Read-only view
synapse config show
synapse config show --scope user
synapse config show --scope project
synapse config show --scope merged

# Initialize (merge strategy — preserves user data, updates templates only)
synapse init --scope user       # ~/.synapse/settings.json
synapse init --scope project    # ./.synapse/settings.json

# Reset
synapse reset --scope user
synapse reset --scope both -f
```

---

## Instructions

```bash
synapse instructions show                 # Default instruction
synapse instructions show claude          # Claude-specific
synapse instructions files claude         # List instruction files
synapse instructions send claude          # Send to running agent
synapse instructions send claude --preview  # Preview only
```

---

## Authentication

```bash
synapse auth setup                  # Generate keys + show setup instructions
synapse auth generate-key           # Generate a single API key
synapse auth generate-key -n 3 -e   # Generate 3 keys in export format
```

---

## Permission Skip Flags

When spawning agents with full autonomy, pass the appropriate flag after `--`:

| CLI Tool | Flag | Example |
|----------|------|---------|
| Claude Code | `--dangerously-skip-permissions` | `synapse spawn claude -- --dangerously-skip-permissions` |
| Gemini CLI | `-y` | `synapse spawn gemini -- -y` |
| Codex CLI | `--full-auto` | `synapse spawn codex -- --full-auto` |
| Copilot CLI | `--allow-all` | `synapse spawn copilot -- --allow-all` |

---

## Port Ranges

| Agent | Ports |
|-------|-------|
| Claude | 8100-8109 |
| Gemini | 8110-8119 |
| Codex | 8120-8129 |
| OpenCode | 8130-8139 |
| Copilot | 8140-8149 |
