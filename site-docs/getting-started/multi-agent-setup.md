# Multi-Agent Setup

Set up multiple agents to collaborate on tasks together.

!!! abstract "What you'll learn"
    - How to start multiple agents side by side
    - How to use `synapse team start` for quick multi-agent launches
    - How to send messages between agents with different response modes
    - How to monitor agent status and track tasks
    - How to fix Codex sandbox networking issues

## Prerequisites

Before setting up a multi-agent workflow, make sure you have:

- **Synapse A2A installed** — See [Installation](installation.md)
- **At least 2 CLI tools installed** — For example, [Claude Code](https://claude.ai/code) and [Gemini CLI](https://github.com/google/gemini-cli)
- **A terminal with pane support** — tmux, iTerm2, Terminal.app, Ghostty, or Zellij (required for `synapse team start` and `synapse spawn`)

## Starting Multiple Agents

There are two ways to get agents running: start them individually or use the team command.

### Option A: Start Agents Individually

Open separate terminals and start each agent:

```bash
# Terminal 1
synapse claude

# Terminal 2
synapse gemini
```

Each agent registers itself in the Synapse registry and starts an A2A server on its assigned port range. Claude uses ports 8100-8109, Gemini uses 8110-8119.

### Option B: Use Team Start

Launch multiple agents at once with automatic pane creation:

```bash
synapse team start claude gemini
```

This opens each agent in its own terminal pane. The first agent takes over the current terminal, and additional agents get new panes.

To put all agents in new panes (keeping your current terminal free):

```bash
synapse team start claude gemini --all-new
```

!!! tip "Layout Options"
    Use `--layout horizontal` or `--layout split` to control how panes are arranged:

    ```bash
    synapse team start claude gemini codex --layout horizontal
    ```

!!! warning "Ghostty Limitation"
    Ghostty uses AppleScript to target the **currently focused window/tab**. Do not switch tabs while `team start` is running, or agents may be created in the wrong tab.

### Naming Your Agents

Give agents descriptive names and roles so they are easy to identify and target:

```bash
synapse claude --name reviewer --role "code reviewer"
synapse gemini --name researcher --role "research specialist"
```

With `team start`, you can use the extended spec format (`profile:Name:role:skill-set`):

```bash
synapse team start claude:Reviewer:reviewer:code-review gemini:Searcher
```

### Verifying Agents Are Running

Open another terminal and run:

```bash
synapse list
```

You will see a live-updating TUI table showing all running agents:

```
┌────┬──────────────────────┬──────────┬────────┬────────┬──────────┐
│ #  │ ID                   │ NAME     │ STATUS │ TYPE   │ PORT     │
├────┼──────────────────────┼──────────┼────────┼────────┼──────────┤
│ 1  │ synapse-claude-8100  │ reviewer │ READY  │ claude │ 8100     │
│ 2  │ synapse-gemini-8110  │ researcher│ READY │ gemini │ 8110     │
└────┴──────────────────────┴──────────┴────────┴────────┴──────────┘
```

!!! tip "Interactive Controls"
    In `synapse list`, use ++up++ / ++down++ to select an agent, ++enter++ or `j` to jump to its terminal, `k` to kill it, and `/` to filter.

## Sending Messages Between Agents

Use `synapse send` to have agents communicate:

```bash
synapse send gemini "What are the best practices for Python error handling?" --wait
```

### Response Modes

Choose the right response mode for your use case:

| Flag | Mode | Behavior | Best For |
|------|------|----------|----------|
| `--wait` | Synchronous | Blocks until the agent replies | Questions, reviews, analysis |
| `--notify` | Async notification | Returns immediately, notifies on completion | Default mode |
| `--silent` | Fire-and-forget | Returns immediately, no notification | Delegated tasks |

!!! info "When in Doubt"
    Use `--wait` if you need a result. Use `--silent` when delegating a task where you do not need the response (e.g., "Fix this bug and commit").

### Examples

**Ask for a code review (wait for the response):**

```bash
synapse send gemini "Review the authentication module for security issues" --wait
```

**Delegate a task (fire-and-forget):**

```bash
synapse send codex "Refactor the auth module and commit" --silent
```

**Send an urgent follow-up:**

```bash
synapse send gemini "Drop what you're doing and check the failing tests" \
  --priority 4 --wait
```

### Priority Levels

| Priority | Use Case |
|----------|----------|
| 1-2 | Low priority, background tasks |
| 3 | Normal tasks (default) |
| 4 | Urgent follow-ups |
| 5 | Emergency interrupt (sends SIGINT first) |

!!! warning "Priority 5"
    Priority 5 sends a SIGINT to the agent before delivering the message, interrupting whatever it is currently doing. Use it only for genuine emergencies.

### Broadcasting to All Agents

Send a message to every agent in the current working directory at once:

```bash
synapse broadcast "Status check — what are you working on?"
```

## Checking Status

### Live Agent Dashboard

`synapse list` provides a real-time view of all agents. It automatically updates when agent status changes (via filesystem events).

### Agent Status States

| Status | Meaning |
|--------|---------|
| **READY** (green) | Idle, waiting for input |
| **PROCESSING** (yellow) | Actively working |
| **WAITING** (cyan) | Showing a selection UI, waiting for a user choice |
| **DONE** (blue) | Task completed (auto-transitions to READY after 10 seconds) |

### Task History

Synapse automatically records task history. View recent tasks and filter by agent:

```bash
# List recent tasks
synapse history list

# Filter by agent
synapse history list --agent gemini

# Show details for a specific task
synapse history show <task_id>
```

## Codex Sandbox Network Fix

!!! warning "Codex Users"
    OpenAI Codex runs inside a network-restricted sandbox by default. This blocks A2A communication between agents. You need to enable network access for Synapse to work with Codex.

### Quick Fix: Environment Variable

Set `CODEX_SANDBOX_NETWORK=true` before starting Codex:

```bash
CODEX_SANDBOX_NETWORK=true synapse codex
```

### Persistent Fix: config.toml

Add the following to your Codex configuration file (`~/.codex/config.toml`):

```toml
[sandbox]
network = true
```

This enables network access for all Codex sessions without needing the environment variable each time.

!!! info "More Details"
    See the [Troubleshooting](../troubleshooting.md) page for additional Codex sandbox issues and other common problems.

## Next Steps

Now that you have multiple agents running and communicating, explore these guides for more advanced workflows:

- **[Agent Teams](../guide/agent-teams.md)** — Team spawning, delegation mode, and auto-spawn panes
- **[Task Board](../guide/task-board.md)** — Shared task board for coordinating work across agents
- **[Communication](../guide/communication.md)** — All messaging patterns, reply routing, and file attachments
- **[Shared Memory](../guide/shared-memory.md)** — Cross-agent knowledge sharing with persistent memory
