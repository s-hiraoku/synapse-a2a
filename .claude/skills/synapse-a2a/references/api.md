# A2A Protocol Reference

This document provides technical details for developers and advanced users.
**For normal agent communication, use `synapse send` and `synapse reply` commands.**

## Message Format

### Receiving Messages

Messages arrive with a simple `A2A:` prefix:

```text
A2A: <message content>
```

### Replying to Messages

Use `synapse reply` to respond:

```bash
synapse reply "<your response>" --from <your_agent_type>
```

The framework automatically handles routing - you don't need to know where the message came from.

## Priority Levels

| Priority | Use Case |
|----------|----------|
| 1-2 | Low priority, background tasks |
| 3 | Normal tasks (default) |
| 4 | Urgent follow-ups |
| 5 | Emergency interrupt (sends SIGINT first) |

## Error Handling

### Agent Not Found

```text
Error: No agent found matching 'xyz'
```
**Solution:** Use `synapse list` to see available agents.

### Multiple Agents Found

```text
Error: Ambiguous target 'codex'. Multiple agents found.
```
**Solution:** Use specific identifier like `codex-8120`.

### Agent Not Responding

```text
Error: Agent 'synapse-claude-8100' server on port 8100 is not responding.
```
**Solution:** Restart the agent with `synapse claude`.
