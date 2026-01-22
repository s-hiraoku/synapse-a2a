# OpenCode Agents Reference

## Agent Types

OpenCode has two categories of agents:

### Primary Agents

Main assistants that interact directly with users. Switch between them using `Tab` key.

### Subagents

Specialized assistants invoked by primary agents or via `@` mentions.

## Built-in Agents

### Build Agent

The default agent with full development capabilities.

**Characteristics:**
- All tools enabled by default
- Full file edit permissions
- Unrestricted bash command execution
- Designed for active development work

**Best for:**
- Writing and editing code
- Running commands and scripts
- Making changes to the codebase
- Full development workflows

### Plan Agent

A restricted agent for analysis and planning.

**Characteristics:**
- Read-only by default
- File edits require approval (`ask` mode)
- Bash commands require approval (`ask` mode)
- Prevents unintended changes

**Best for:**
- Reviewing implementation strategy
- Code analysis and exploration
- Understanding existing code
- Planning before making changes

**Switching:**
Press `Tab` to toggle between Build and Plan agents.

## Subagents

### General Subagent

A versatile agent for complex research tasks.

**Invoke:** `@general`

**Capabilities:**
- Full tool access (except todo)
- Multi-step task execution
- Complex question research
- Cross-file analysis

**Use cases:**
- "Research how authentication is implemented"
- "Find all places where this API is called"
- "Investigate this error across the codebase"

### Explore Subagent

A fast, read-only agent for codebase navigation.

**Invoke:** `@explore`

**Capabilities:**
- Read-only operations only
- Optimized for speed
- Pattern-based file search
- Code question answering

**Use cases:**
- "Find all files matching *.test.ts"
- "Search for usages of this function"
- "Show me how this component works"

## Creating Custom Agents

### Interactive Creation

```bash
opencode agent create
```

Guides you through:
1. Storage location selection
2. Purpose definition
3. Prompt generation
4. Tool access configuration

### Configuration File

Define agents in `opencode.json`:

```json
{
  "agents": {
    "my-agent": {
      "description": "Custom agent for specific tasks",
      "model": "claude-3-5-sonnet",
      "temperature": 0.7,
      "system": "You are a specialized assistant for...",
      "tools": {
        "bash": "ask",
        "write": "allow",
        "read": "allow"
      }
    }
  }
}
```

### Markdown Definition

Create agent files in:
- `~/.config/opencode/agents/<name>.md`
- `.opencode/agents/<name>.md`

Format:

```markdown
---
name: my-agent
description: Agent description
model: claude-3-5-sonnet
temperature: 0.7
---

# System Prompt

You are a specialized assistant that...

## Guidelines

- Always check before making changes
- Follow the coding standards
```

## Agent Configuration Options

| Option | Type | Description |
|--------|------|-------------|
| `name` | string | Agent identifier |
| `description` | string | What the agent does |
| `model` | string | LLM model to use |
| `temperature` | number | Creativity (0.0-1.0) |
| `system` | string | System prompt |
| `tools` | object | Tool permissions |

## Tool Permission Levels

| Level | Behavior |
|-------|----------|
| `allow` | Execute without confirmation |
| `ask` | Require user approval |
| `deny` | Block tool usage |

### Default Permissions

**Build Agent:**
```json
{
  "tools": {
    "read": "allow",
    "write": "allow",
    "edit": "allow",
    "bash": "allow",
    "grep": "allow",
    "glob": "allow",
    "list": "allow"
  }
}
```

**Plan Agent:**
```json
{
  "tools": {
    "read": "allow",
    "write": "ask",
    "edit": "ask",
    "bash": "ask",
    "grep": "allow",
    "glob": "allow",
    "list": "allow"
  }
}
```

## Agent Selection

### Via Command Line

```bash
# Start with specific agent
opencode --agent build
opencode --agent plan
opencode --agent my-custom-agent
```

### Via Keyboard

Press `Tab` to cycle through primary agents during a session.

### Via Subagent Mention

Prefix with `@` to invoke subagents:

```
@general Research how this works
@explore Find all test files
```

## Best Practices

### Use Plan Mode First

Start with Plan agent to understand the codebase and plan changes before switching to Build mode.

### Create Task-Specific Agents

For repetitive specialized tasks, create custom agents with:
- Focused system prompts
- Appropriate tool permissions
- Task-specific temperature settings

### Leverage Subagents

Use `@explore` for quick searches and `@general` for complex research to keep main context clean.

### Configure Permissions Thoughtfully

For production codebases:
- Use `ask` mode for destructive operations
- Limit bash permissions appropriately
- Consider read-only agents for auditing
