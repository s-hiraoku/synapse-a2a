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
| `-- --resume` / `-- --continue` | Pass resume flag to CLI tool (skips initial instructions) |
| `--delegate-mode` | Start as manager/delegator (no file editing) |
| `--port PORT` | Override default port |
| `--worktree [NAME]`, `-w` | Create git worktree for isolated work (optional name) |

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
synapse list
```

Interactive TUI with real-time updates. See [Agent Management](../guide/agent-management.md) for controls.

### Status

```bash
synapse status <target>            # Show detailed agent status
synapse status <target> --json     # Output as JSON
```

Shows a comprehensive view of a single agent including metadata, uptime, current task with elapsed time, recent message history, file locks, and task board assignments. See [Agent Management — Detailed Status](../guide/agent-management.md#detailed-status) for more.

| Flag | Description |
|------|-------------|
| `<target>` | Agent name, ID, type-port, or type |
| `--json` | Output as JSON (machine-readable) |

### Kill

```bash
synapse kill <target>        # Graceful shutdown (30s timeout)
synapse kill <target> -f     # Force kill (immediate SIGKILL)
```

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
| `--silent` | Fire-and-forget (no completion notification) |
| `--message-file PATH` | Read message from file (`-` for stdin) |
| `--stdin` | Read message from stdin |
| `--attach FILE` | Attach file (repeatable) |
| `--force` | Bypass working_dir mismatch check |

!!! tip "Choosing response mode"
    - `--notify` (default): Returns immediately; you get a PTY notification when the receiver completes. Best for most use cases.
    - `--wait`: Blocks until the receiver replies. Use for questions or when you need the result before proceeding.
    - `--silent`: Fire-and-forget with no completion notification. Use for pure notifications or delegated tasks.

### Reply

```bash
synapse reply "<message>"                  # Reply to last sender
synapse reply "<message>" --to <sender>    # Reply to specific sender
synapse reply "<message>" --from ID        # With explicit sender ID
synapse reply --list-targets               # List pending senders
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
| `--worktree [NAME]`, `-w` | Create per-agent git worktrees for isolation |

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
| `--worktree [NAME]`, `-w` | Create git worktree for isolated work |

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

## Task Board

### List Tasks

```bash
synapse tasks list [--status STATUS] [--agent AGENT]
```

### Create Task

```bash
synapse tasks create "<subject>" -d "<description>" [--priority N] [--blocked-by ID]
```

### Assign / Complete / Fail / Reopen

```bash
synapse tasks assign <task_id> <agent>
synapse tasks complete <task_id>
synapse tasks fail <task_id> [--reason "reason"]
synapse tasks reopen <task_id>
```

### Plan Approval

```bash
synapse approve <task_id>
synapse reject <task_id> --reason "reason"
```

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
synapse memory save <key> "<content>" [--tags tag1,tag2] [--notify]
synapse memory list [--author <id>] [--tags <tags>] [--limit N]
synapse memory show <id_or_key>
synapse memory search "<query>"
synapse memory delete <id_or_key> [--force]
synapse memory stats
```

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
synapse workflow run <name> [--project | --user] [--dry-run] [--continue-on-error]
```

Executes workflow steps sequentially via `synapse send`.

| Flag | Description |
|------|-------------|
| `--dry-run` | Preview steps without sending messages |
| `--continue-on-error` | Continue executing remaining steps after a failure |

### Delete Workflow

```bash
synapse workflow delete <name> [--project | --user] [--force]
```

| Flag | Description |
|------|-------------|
| `--force`, `-f` | Delete without confirmation prompt |

## Settings

```bash
synapse init [--scope user|project]
synapse config [--scope user|project]
synapse config show [--scope SCOPE]
synapse reset [--scope user|project|both] [-f]
```

`synapse init` uses a merge strategy: only template files are written. User-generated data (agents, databases, sessions, workflows, worktrees) is preserved. Safe to re-run after upgrades.

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

## Logs

```bash
synapse logs <agent> [-f] [-n LINES]
```

## Low-Level A2A Tool

```bash
python -m synapse.tools.a2a list [--live]
python -m synapse.tools.a2a send --target <agent> --priority N "<message>"
python -m synapse.tools.a2a broadcast "<message>"
python -m synapse.tools.a2a cleanup
```
