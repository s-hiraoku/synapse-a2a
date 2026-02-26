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
| `--role ROLE` | Agent role description |
| `--skill-set SET` | Activate skill set |
| `--no-setup` | Skip interactive setup |
| `--resume` / `--continue` | Skip initial instructions |
| `--delegate-mode` | Start as coordinator (no file editing) |
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
synapse stop --all           # Stop all agents
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

## Communication

### Send

```bash
synapse send <target> "<message>" [OPTIONS]
```

| Flag | Description |
|------|-------------|
| `--from ID` / `-f ID` | Sender identification (`$SYNAPSE_AGENT_ID`) |
| `--priority N` / `-p N` | Priority 1-5 (default: 3) |
| `--response` | Wait for reply (roundtrip) |
| `--no-response` | Fire-and-forget |
| `--message-file PATH` | Read message from file (`-` for stdin) |
| `--stdin` | Read message from stdin |
| `--attach FILE` | Attach file (repeatable) |
| `--force` | Bypass working_dir mismatch check |

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

Same options as `send`. Targets all agents in the current working directory.

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

**Profile spec format**: `profile[:name[:role[:skill_set]]]`

### Spawn

```bash
synapse spawn <profile> [OPTIONS] [-- TOOL_ARGS]
```

| Flag | Description |
|------|-------------|
| `--port PORT` | Explicit port |
| `--name NAME` | Agent name |
| `--role ROLE` | Agent role |
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
```

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
