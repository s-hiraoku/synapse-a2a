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
| `--no-setup` | Skip interactive setup |
| `-- --resume` / `-- --continue` | Pass resume flag to CLI tool (skips initial instructions) |
| `--delegate-mode` | Start as manager/delegator (no file editing) |
| `--port PORT` | Override default port |

### Background Start

```bash
synapse start <profile> [--port PORT] [-f]
```

| Flag | Description |
|------|-------------|
| `--port PORT` | Explicit port number |
| `-f` | Foreground mode (don't detach) |

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
| `<id>` | Petname-format identifier (e.g. `silent-snake`) |
| `--name NAME` | Display name (required) |
| `--profile PROFILE` | Agent profile: `claude`, `codex`, `gemini`, `opencode`, `copilot` (required) |
| `--role ROLE` | Role description or `@path` file reference |
| `--skill-set SET` / `-S SET` | Skill set name |
| `--scope SCOPE` | `project` (default) or `user` |

### Delete Saved Agent

```bash
synapse agents delete <id_or_name>
```

!!! tip "Using Saved Agents with Spawn"
    Once defined, saved agents can be spawned by ID or name:
    ```bash
    synapse spawn silent-snake
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
| `--response` | Wait for reply (roundtrip) |
| `--no-response` | Fire-and-forget |
| `--callback CMD` | Shell command to run on sender after task completion (requires `--no-response`) |
| `--message-file PATH` | Read message from file (`-` for stdin) |
| `--stdin` | Read message from stdin |
| `--attach FILE` | Attach file (repeatable) |
| `--force` | Bypass working_dir mismatch check |

!!! tip "Choosing --response vs --no-response"
    Use `--response` when the message expects a reply (questions, result requests). Use `--no-response` for fire-and-forget tasks (notifications, delegated work). **If unsure, use `--response`** — it is the safer default.

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

Shorthand for `synapse send -p 4 --no-response`.

## Team Operations

### Team Start

```bash
synapse team start <profiles...> [OPTIONS] [-- TOOL_ARGS]
```

| Flag | Description |
|------|-------------|
| `--layout LAYOUT` | `split`, `horizontal`, or `vertical` |
| `--all-new` | All agents in new panes |

**Profile spec format**: `profile[:name[:role[:skill_set[:port]]]]`

!!! note
    Ports are typically pre-allocated automatically by `team start` to avoid race conditions. You only need to specify a port explicitly if you want to override the default.

### Spawn

```bash
synapse spawn <profile_or_saved_agent> [OPTIONS] [-- TOOL_ARGS]
```

The `<profile_or_saved_agent>` argument accepts:

- A built-in profile name (`claude`, `gemini`, `codex`, `opencode`, `copilot`)
- A saved agent ID (petname format, e.g. `silent-snake`)
- A saved agent display name (e.g. a custom name set via `synapse agents add`)

When a saved agent is used, its profile, name, role, and skill set are resolved from the definition. CLI flags (`--name`, `--role`, etc.) override saved values.

| Flag | Description |
|------|-------------|
| `--port PORT` | Explicit port |
| `--name NAME` | Agent name |
| `--role ROLE` | Agent role (supports `@path` file reference) |
| `--terminal TERM` | Terminal app override |

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
synapse history search "<query>" [--agent AGENT] [--logic AND|OR]
synapse history stats [--agent AGENT]
synapse history export --format json|csv
synapse history cleanup --days N
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
synapse skills show <name>
synapse skills delete <name> [--force]
synapse skills move <name> --to <scope>
synapse skills deploy <name> --agent <types> [--scope SCOPE]
synapse skills import <name>
synapse skills add <repo>
synapse skills create
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

## Settings

```bash
synapse init [--scope user|project]
synapse config [--scope user|project]
synapse config show [--scope SCOPE]
synapse reset [--scope user|project|both] [-f]
```

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
python -m synapse.tools.a2a list
python -m synapse.tools.a2a send --target <agent> --priority N "<message>"
python -m synapse.tools.a2a broadcast "<message>"
python -m synapse.tools.a2a cleanup
```
