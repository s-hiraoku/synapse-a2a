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
| `synapse jump <target>` | Jump to agent terminal |

### Communication

| Command | Description |
|---------|-------------|
| `synapse send <target> "msg"` | Send message (default `--notify`) |
| `synapse send <target> "msg" --wait` | Send and wait for reply |
| `synapse send <target> "msg" --silent` | Fire-and-forget |
| `synapse send <target> "msg" --task` | Send and auto-create a linked board task (auto-claim/complete) |
| `synapse reply "msg"` | Reply to sender |
| `synapse broadcast "msg"` | Send to all agents in current directory |
| `synapse interrupt <target> "msg"` | Soft interrupt (priority 4) |

### Task Board

| Command | Description |
|---------|-------------|
| `synapse tasks list` | List all tasks |
| `synapse tasks list --group-by status` | List tasks grouped by status |
| `synapse tasks list --component backend` | Filter by component |
| `synapse tasks list --format json` | Output as JSON |
| `synapse tasks create "subject" -d "desc"` | Create a task |
| `synapse tasks create "subject" --group sprint-3 --component backend` | Create with metadata |
| `synapse tasks assign <id> <agent>` | Assign task to agent |
| `synapse tasks complete <id>` | Mark task completed |
| `synapse tasks fail <id>` | Mark task failed |
| `synapse tasks purge [--status STATUS] [--force]` | Remove tasks (prompts for confirmation; `--force` to skip) |
| `synapse tasks purge --older-than 7d --dry-run` | Preview stale task cleanup |
| `synapse approve <id>` | Approve a plan |
| `synapse reject <id> --reason "..."` | Reject with reason |
| `synapse tasks accept-plan <plan_id>` | Accept a Plan Card and create board tasks |
| `synapse tasks sync-plan <plan_id>` | Sync board progress back to Plan Card |

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
| `synapse memory save <key> <content>` | Save a memory entry |
| `synapse memory list` | List entries |
| `synapse memory show <id_or_key>` | Show entry |
| `synapse memory search <query>` | Search entries |
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

# With worktree isolation
synapse spawn claude --worktree feature-auth

# Pass tool-specific flags after '--'
synapse spawn claude -- --dangerously-skip-permissions
```

### Agent Teams

```bash
# Start a multi-agent team (first agent in current terminal)
synapse team start claude gemini
synapse team start claude gemini codex --layout horizontal

# All agents in new panes (keep current terminal free)
synapse team start claude gemini --all-new

# With worktree isolation for every agent
synapse team start claude gemini --worktree

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

## Task Board

```bash
# Create a task
synapse tasks create "Implement auth module" -d "Add JWT-based auth" --priority 4

# Create with grouping metadata
synapse tasks create "Add user endpoint" -d "REST CRUD" \
  --group sprint-3 --component backend --milestone v1.0

# List tasks
synapse tasks list
synapse tasks list --status pending
synapse tasks list --component backend --milestone v1.0
synapse tasks list --group-by status       # Grouped view
synapse tasks list --format json           # JSON output
synapse tasks list --verbose               # Full UUIDs and timestamps

# Assign, complete, fail, reopen
synapse tasks assign <task_id> claude
synapse tasks complete <task_id>
synapse tasks fail <task_id> --reason "dependency missing"
synapse tasks reopen <task_id>

# Purge with safety options
synapse tasks purge --force                       # Skip confirmation
synapse tasks purge --dry-run                     # Preview only
synapse tasks purge --older-than 7d               # Age-based cleanup
synapse tasks purge --older-than 2h --status completed  # Combine filters

# Task-linked messaging (creates board task, auto-claim on receive, auto-complete on finalize)
synapse send gemini "Implement feature" --task
synapse send gemini "Implement feature" -T

# Plan approval
synapse approve <task_id>
synapse reject <task_id> --reason "Use a different approach"

# Plan Card integration
synapse tasks accept-plan <plan_id>      # Register plan steps as board tasks
synapse tasks sync-plan <plan_id>        # Sync board progress back to Canvas
```

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

```bash
# Save with optional tags and notification
synapse memory save api-spec "REST API uses JWT auth" --tags api,auth --notify

# List and filter
synapse memory list
synapse memory list --author synapse-claude-8100 --tags api --limit 10

# Show and search
synapse memory show api-spec
synapse memory search "authentication"

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
# Interactive config editor
synapse config
synapse config --scope user
synapse config --scope project

# Read-only view
synapse config show
synapse config show --scope user

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
| Copilot CLI | `--allow-all-tools` | `synapse spawn copilot -- --allow-all-tools` |

---

## Port Ranges

| Agent | Ports |
|-------|-------|
| Claude | 8100-8109 |
| Gemini | 8110-8119 |
| Codex | 8120-8129 |
| OpenCode | 8130-8139 |
| Copilot | 8140-8149 |
