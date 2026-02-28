# Agent Management

## Starting Agents

### Interactive Mode (Foreground)

```bash
synapse claude                              # Start Claude Code
synapse gemini                              # Start Gemini CLI
synapse codex                               # Start Codex CLI
synapse opencode                            # Start OpenCode
synapse copilot                             # Start GitHub Copilot CLI
```

Each shortcut loads the corresponding profile and starts the agent interactively.

### With Name and Role

```bash
synapse claude --name my-claude --role "code reviewer"
synapse gemini --name test-writer --role "test specialist"
```

### Skip Interactive Setup

```bash
synapse claude --no-setup
```

### Background Mode

```bash
synapse start claude --port 8100
synapse start claude --port 8100 -f   # Foreground (don't detach)
```

### Resume Mode

Pass resume flags to the underlying CLI tool via `--` to skip initial instructions (useful after context reset):

```bash
synapse claude -- --resume
synapse claude -- --continue   # Same as --resume
```

Synapse detects these flags and automatically skips sending initial instructions.

## Monitoring Agents

### synapse list

The Rich TUI agent monitor with real-time updates:

```bash
synapse list
```

Displays a live table with:

| Column | Description |
|--------|-------------|
| `#` | Row number (for keyboard selection) |
| `ID` | Agent identifier |
| `NAME` | Custom name (if set) |
| `STATUS` | Current state with color coding |
| `CURRENT` | Current task preview |
| `TRANSPORT` | Active communication (`UDS→` / `→UDS` / `-`) |
| `WORKING_DIR` | Agent's working directory |
| `EDITING_FILE` | Locked file name (shown when File Safety is enabled) |

Optional columns (`list.columns`): `TYPE`, `ROLE`.

**Interactive controls:**

| Key | Action |
|-----|--------|
| ++up++ / ++down++ | Select agent row |
| `1`-`9` | Jump to row number |
| ++enter++ / `j` | Jump to agent's terminal |
| `K` | Kill agent (with confirmation) |
| `/` | Filter by TYPE, NAME, or WORKING_DIR |
| ++escape++ | Clear filter |
| `q` | Quit |

!!! info "Real-Time Updates"
    `synapse list` uses file watchers (fsevents on macOS, inotify on Linux) to detect registry changes instantly. Falls back to 10-second polling if watchers are unavailable.

## Stopping Agents

### Graceful Shutdown

```bash
synapse kill my-claude            # Graceful (30s timeout)
```

Graceful shutdown phases:

1. Send HTTP shutdown request to the agent
2. Wait for grace period (30s default)
3. Send SIGTERM
4. If still running, send SIGKILL

### Force Kill

```bash
synapse kill my-claude -f         # Immediate SIGKILL
```

### Stop Background Agent

```bash
synapse stop my-claude
synapse stop claude -a            # Stop all Claude instances
```

## Terminal Jump

Jump to an agent's terminal window from `synapse list` or via CLI:

```bash
synapse jump my-claude
```

**Supported terminals:**

| Terminal | Jump Support |
|----------|:---:|
| tmux | :material-check: |
| iTerm2 | :material-check: |
| Terminal.app | :material-check: |
| Ghostty | :material-check: |
| VS Code Terminal | :material-check: |
| Zellij | :material-check: |

## Naming and Roles

### Assign Name and Role

```bash
# At startup
synapse claude --name reviewer --role "security code review"

# After startup
synapse rename claude --name reviewer --role "security code review"
```

### Role from File

Use the `@` prefix to load role content from a file:

```bash
synapse claude --name reviewer --role "@./roles/reviewer.md"
synapse rename my-claude --role "@./roles/architect.md"
```

### Update Role Only

```bash
synapse rename my-claude --role "architecture review"
```

### Clear Name and Role

```bash
synapse rename my-claude --clear
```

### Target Resolution Priority

When using `synapse send`, `synapse kill`, `synapse jump`, or other commands:

1. **Custom name** (highest): `my-claude`
2. **Full agent ID**: `synapse-claude-8100`
3. **Type-port shorthand**: `claude-8100`
4. **Agent type** (only if single instance): `claude`

!!! warning
    Custom names are case-sensitive. If multiple agents share the same type, you must use a name, full ID, or type-port to disambiguate.

## Agent Status

| Status | Color | Meaning |
|--------|:---:|---------|
| **READY** | :material-circle:{ .status-ready } | Idle, waiting for input |
| **PROCESSING** | :material-circle:{ .status-processing } | Actively working |
| **WAITING** | :material-circle:{ .status-waiting } | Showing selection UI |
| **DONE** | :material-circle:{ .status-done } | Task completed (auto-clears 10s) |
| **SHUTTING_DOWN** | :material-circle:{ .status-shutdown } | Shutdown in progress |

Dead processes are automatically cleaned from the registry and hidden from `synapse list`.
