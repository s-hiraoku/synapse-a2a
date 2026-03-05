# Agent Identity

This guide explains how Synapse A2A identifies agents and routes messages between them. Understanding agent identity is essential when running multiple agents and coordinating their work.

## Overview

Every Synapse agent receives a unique identity at startup. This identity is used for:

- **Self-awareness** -- the agent knows who it is and can distinguish messages addressed to it from messages intended for other agents.
- **Routing** -- Synapse routes messages to the correct agent based on the target identifier.
- **Disambiguation** -- when multiple instances of the same agent type are running, each has a distinct identity.

## Runtime ID

When an agent starts, Synapse generates a **Runtime ID** in the format:

```
synapse-{agent_type}-{port}
```

For example:

| Agent | Port | Runtime ID |
|-------|------|------------|
| Claude Code | 8100 | `synapse-claude-8100` |
| Gemini CLI | 8110 | `synapse-gemini-8110` |
| Codex CLI | 8120 | `synapse-codex-8120` |

The Runtime ID is guaranteed to be unique among simultaneously running instances on a single machine. The `synapse-` prefix prevents collisions with file references, and the port number ensures no two active agents share the same ID. Note that ports can be reused over time once an agent shuts down.

## Custom Names and Roles

### The `--name` Flag

You can assign a human-friendly name to any agent at startup:

```bash
synapse claude --name my-claude
synapse gemini --name test-writer
```

Custom names become the **highest-priority target** when sending messages, killing agents, or jumping to terminals. They are case-sensitive.

### The `--role` Flag

The `--role` flag assigns a purpose description that is included in the agent's initial instructions:

```bash
synapse claude --name reviewer --role "Senior code reviewer. Focus on security and performance."
synapse gemini --name analyst --role "Data analyst specializing in log analysis."
```

The role text is sent to the agent at startup as part of the identity instruction so the underlying LLM understands its purpose within the team.

### Role from File with `@` Prefix

For long or reusable role descriptions, load the content from a file by prefixing the path with `@`:

```bash
synapse claude --name reviewer --role "@./roles/reviewer.md"
synapse gemini --role "@~/my-roles/analyst.md"
```

The file content replaces the `@path` value and is sent as the role text.

### Renaming a Running Agent

You can update an agent's name or role after it has started:

```bash
synapse rename claude --name my-claude          # Assign name
synapse rename my-claude --role "test writer"   # Update role only
synapse rename my-claude --clear                # Clear name and role
```

## Target Resolution

When you use commands like `synapse send`, `synapse kill`, `synapse jump`, `synapse interrupt`, `synapse rename`, or `synapse skills apply`, Synapse resolves the target in this priority order:

| Priority | Format | Example | Notes |
|----------|--------|---------|-------|
| 1 (highest) | Custom name | `my-claude` | Case-sensitive |
| 2 | Full Runtime ID | `synapse-claude-8100` | Always unique |
| 3 | Type-port shorthand | `claude-8100` | Omits the `synapse-` prefix |
| 4 (lowest) | Agent type | `claude` | Only if a single instance is running |

### Examples

```bash
# Single Claude running -- all of these resolve to the same agent
synapse send claude "Hello"
synapse send claude-8100 "Hello"
synapse send synapse-claude-8100 "Hello"

# Two Claude instances running -- type alone is ambiguous
synapse send claude-8100 "Task A"     # Specific instance
synapse send claude-8101 "Task B"     # Other instance

# Custom name takes priority
synapse claude --name reviewer --port 8100
synapse send reviewer "Review this code" --wait
```

!!! warning "Ambiguous targets"
    If multiple instances of the same agent type are running and you specify only the type (e.g., `claude`), Synapse will report an error. Use a more specific target such as the custom name, Runtime ID, or type-port shorthand.

## Interactive Setup

When you start an agent without `--name` or `--role`, Synapse offers an interactive setup flow:

```
$ synapse claude
? Enter a name for this agent (optional): reviewer
? Enter a role for this agent (optional): Senior code reviewer
Starting claude as 'reviewer' (Senior code reviewer)...
```

To skip the interactive prompt entirely:

```bash
synapse claude --no-setup
```

## Saved Agent Definitions

For frequently used name/role/skill-set combinations, save them as **agent definitions** and reuse them with the `--agent` (`-A`) flag.

### Creating a Definition

```bash
synapse agents add calm-lead \
  --name "Calm Lead" \
  --profile claude \
  --role "Calm, methodical lead developer. Reviews code thoroughly." \
  --skill-set architect \
  --scope project
```

### Using a Saved Definition

```bash
# By ID
synapse claude --agent calm-lead

# By display name (short flag)
synapse claude -A "Calm Lead"

# Override a saved value at startup
synapse claude --agent calm-lead --role "temporary override"
```

!!! note "Profile matching"
    The saved agent's `profile` must match the startup shortcut. A saved agent with `profile: gemini` cannot be used with `synapse claude`.

### Managing Definitions

```bash
# List all saved agents
synapse agents list

# Show details
synapse agents show calm-lead

# Delete
synapse agents delete calm-lead
```

Definitions can be scoped to a project (`.synapse/agents/`) or to the user (`~/.synapse/agents/`).

## How Identity Instructions Work

At startup, Synapse sends an identity instruction to the agent through the PTY. This instruction tells the agent:

1. **Who it is** -- its Runtime ID, agent type, and optional custom name and role.
2. **Routing rules** -- how to determine whether a message is addressed to it or to another agent.
3. **Other active agents** -- the identifiers of other running agents so it can route messages appropriately.

```
[SYNAPSE A2A] Your identity:
- ID: synapse-claude-8100
- Type: claude

Routing rules:
- @synapse-claude-8100 -> This is for you. Execute it.
- @synapse-gemini-8110 -> For another agent. Forward via A2A only.
```

!!! info "Readiness Gate"
    The identity instruction must be sent before the agent accepts incoming tasks. Until it completes, both `/tasks/send` and `/tasks/send-priority` return HTTP 503 (Service Unavailable) with a `Retry-After: 5` header. Priority-5 (emergency) messages and replies (`in_reply_to`) bypass the gate. The timeout is 30 seconds.

### Skill Set in Identity

If the agent has an active skill set, the identity instruction also includes the skill set details:

```
========================================================================
SKILL SET
========================================================================

Active skill set: architect
Purpose: System architecture and design

Available skills:
  - synapse-a2a
  - system-design
  - api-design
  - code-review
  - project-docs

Use these skills to guide your work.
```

## Agent Card

Each agent exposes an **Agent Card** at `/.well-known/agent.json` following the Google A2A specification. The card includes identity extensions:

```json
{
  "name": "Synapse Claude",
  "url": "http://localhost:8100",
  "extensions": {
    "synapse": {
      "agent_id": "synapse-claude-8100",
      "addressable_as": [
        "@synapse-claude-8100",
        "@claude"
      ]
    }
  }
}
```

Other agents and external tools can discover running agents by reading their Agent Cards from the registry.

## Practical Patterns

### Single-Agent Setup

When only one agent is running, use the simplest target form:

```bash
synapse claude
synapse send claude "Review this code" --wait
```

### Multi-Agent Team with Names

Assign names to make communication clear:

```bash
synapse claude --name reviewer --role "code reviewer"
synapse gemini --name researcher --role "search and analysis"

synapse send reviewer "Check the auth module" --wait
synapse send researcher "Find examples of JWT refresh patterns" --wait
```

### Using Saved Definitions in Teams

Combine saved agent definitions with `synapse team start`:

```bash
# Create definitions
synapse agents add reviewer --name Reviewer --profile claude --role "code reviewer"
synapse agents add researcher --name Researcher --profile gemini --role "search specialist"

# Start a team using extended spec
synapse team start claude:Reviewer gemini:Researcher
```

## Limitations

- Identity instructions are sent as plain text through the PTY. Whether the agent follows the routing rules depends on the underlying LLM's behavior.
- If the agent's startup time exceeds the profile's configured timeout, instruction delivery may be delayed.
- Custom names are stored in the registry file and are not persisted across agent restarts unless you use saved agent definitions.
